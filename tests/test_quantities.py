#!/usr/bin/env python3
"""Quantity authority tests — looked-up ceilings and measured totals.

The invariant under test is refusal, not arithmetic: an unknown key must fail
loudly rather than return a default, and a census must fail loudly rather than
return an estimate. Every assertion that a number is right is paired with an
assertion that no number is returned when it cannot be right.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import quantities  # noqa: E402
from quantities import CensusRefusal, QuantityError  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_harness(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("AGENT_DO_HOME", str(ROOT / ".dev" / "test-home"))
    return subprocess.run(
        [str(ROOT / "agent-do"), "harness", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_key_grammar_survives_dotted_subjects() -> None:
    """Model IDs carry dots; only the first and last segments are delimiters."""
    require(
        quantities.parse_key("openai.gpt-5.6-sol.max_tokens") == ("openai", "gpt-5.6-sol", "max_tokens"),
        "dotted subject was split incorrectly",
    )
    require(
        quantities.parse_key("anthropic.claude-sonnet-5.max_tokens")
        == ("anthropic", "claude-sonnet-5", "max_tokens"),
        "simple key was split incorrectly",
    )
    for bad in ("", "max_tokens", "anthropic.max_tokens"):
        try:
            quantities.parse_key(bad)
        except QuantityError:
            continue
        raise AssertionError(f"malformed key accepted: {bad!r}")


def test_lookup_returns_value_with_provenance() -> None:
    record = quantities.lookup("anthropic.claude-sonnet-5.max_tokens")
    require(record["value"] == 128000, f"unexpected ceiling: {record}")
    require(record["kind"] == "looked_up", f"wrong kind: {record}")
    require(record["provenance"]["record"] == "models.anthropic/claude-sonnet-5", f"bad record: {record}")
    require(record["provenance"]["field"] == "max_tokens", f"bad field: {record}")


def test_hand_entered_limit_carries_its_citation() -> None:
    """A number nobody machine-refreshes must say where it came from."""
    record = quantities.lookup("anthropic.models_list.page_limit")
    require(record["value"] == 1000, f"unexpected page limit: {record}")
    require(record["provenance"].get("source"), "hand-entered limit has no source")
    require(record["provenance"].get("verified"), "hand-entered limit has no verified date")


def test_unknown_key_raises_and_names_itself() -> None:
    try:
        quantities.lookup("anthropic.claude-opus-9.max_tokens")
    except QuantityError as exc:
        require("anthropic.claude-opus-9.max_tokens" in str(exc), f"error did not name the key: {exc}")
        return
    raise AssertionError("unknown key returned a value instead of raising")


def test_unknown_key_exits_nonzero_with_no_number() -> None:
    result = run_harness("quantity", "lookup", "anthropic.claude-opus-9.max_tokens")
    require(result.returncode != 0, "unknown key exited zero")
    require(result.stdout.strip() == "", f"unknown key printed something: {result.stdout!r}")
    require("anthropic.claude-opus-9.max_tokens" in result.stderr, f"key not named: {result.stderr}")

    payload = json.loads(run_harness("quantity", "lookup", "nope.nope.nope", "--json").stdout)
    require(payload["ok"] is False, f"json refusal claimed ok: {payload}")
    require("value" not in payload, f"json refusal carried a value: {payload}")


def test_keys_enumerates_every_declared_quantity() -> None:
    keys = [item["key"] for item in quantities.authority_entries()]
    require(len(keys) == len(set(keys)), "duplicate authority keys")
    require(keys == sorted(keys), "authority keys are not sorted")
    require("anthropic.models_list.page_limit" in keys, "limits block missing from keys")
    require("anthropic.claude-sonnet-5.max_tokens" in keys, "model ceiling missing from keys")

    listed = run_harness("quantity", "keys").stdout.split()
    require(listed == keys, "CLI key listing diverged from the module")


def test_census_lines_matches_wc() -> None:
    target = ROOT / "registry.yaml"
    expected = subprocess.run(["wc", "-l", str(target)], capture_output=True, text=True, check=True)
    require(
        quantities.census_lines(str(target))["total"] == int(expected.stdout.split()[0]),
        "line census diverged from wc -l",
    )


def test_census_lines_flags_an_unterminated_tail_instead_of_guessing() -> None:
    """`wc -l` counts terminators; the missing final line is reported, not added."""
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "partial.txt"
        path.write_text("a\nb\nc", encoding="utf-8")  # no trailing newline
        result = quantities.census_lines(str(path))
        require(result["total"] == 2, f"count drifted from wc -l semantics: {result}")
        require(result["final_line_unterminated"] is True, f"unterminated tail not reported: {result}")


def test_census_entries_matches_a_shell_count() -> None:
    found = subprocess.run(
        ["find", "tools", "-maxdepth", "1", "-name", "agent-*"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = len([line for line in found.stdout.splitlines() if line.strip()])
    result = quantities.census_entries(str(ROOT / "tools"), glob="agent-*")
    require(result["total"] == expected, f"entry census diverged from find: {result} vs {expected}")
    require(result["method"] == "dir-scan", f"method not reported: {result}")


def test_census_refuses_a_paginated_payload() -> None:
    """The core refusal: one page of a larger set is not a total.

    This is the shape that produced a confident wrong answer before — a capped
    list read as if it were complete. A partial count is worse than none.
    """
    for payload in (
        {"data": [1, 2, 3], "has_more": True},
        {"data": [1, 2, 3], "next_page": "cursor-abc"},
        {"data": [1, 2, 3], "limit": 3},
    ):
        def runner(argv, timeout, body=payload):
            return {"returncode": 0, "stdout": json.dumps(body), "stderr": ""}

        try:
            quantities.census_rows("manna list --json", runner=runner)
        except CensusRefusal as exc:
            require(exc.reason in {"paginated", "page_boundary"}, f"wrong refusal reason: {exc.reason}")
            continue
        raise AssertionError(f"counted a truncated payload as a total: {payload}")


def test_census_counts_an_unpaginated_payload_exactly() -> None:
    def runner(argv, timeout):
        return {"returncode": 0, "stdout": json.dumps({"issues": [1, 2, 3, 4]}), "stderr": ""}

    result = quantities.census_rows("manna list --json", runner=runner)
    require(result["total"] == 4, f"exact count wrong: {result}")
    require(result["exact"] is True, f"exact flag wrong: {result}")
    require(result["json_path"] == "issues", f"counted the wrong array: {result}")


def test_census_refuses_an_ambiguous_payload() -> None:
    def runner(argv, timeout):
        return {"returncode": 0, "stdout": json.dumps({"a": [1], "b": [1, 2]}), "stderr": ""}

    try:
        quantities.census_rows("manna list --json", runner=runner)
    except CensusRefusal as exc:
        require(exc.reason == "ambiguous_array", f"wrong reason: {exc.reason}")
        return
    raise AssertionError("picked one of two arrays instead of refusing")


def test_bad_path_is_a_caller_error_not_a_refusal() -> None:
    """Exit 1 means the request could not run as asked; exit 2 means no exact count exists."""
    def runner(argv, timeout):
        return {"returncode": 0, "stdout": json.dumps({"issues": [1, 2]}), "stderr": ""}

    for bad_path, fragment in (("nope", "no value at --path"), ("issues.deeper", "no value at --path")):
        try:
            quantities.census_rows("manna list --json", path=bad_path, runner=runner)
        except QuantityError as exc:
            require(fragment in str(exc), f"unexpected error: {exc}")
            continue
        except CensusRefusal as exc:
            raise AssertionError(f"a caller error was reported as a refusal: {exc}")
        raise AssertionError(f"bad --path {bad_path} was accepted")


def test_census_refuses_to_run_a_write_verb() -> None:
    """Read-only is enforced from declared contracts, not a list kept here."""
    def runner(argv, timeout):
        raise AssertionError("census executed a write verb")

    try:
        quantities.census_rows("manna claim mn-000000 --json", runner=runner)
    except QuantityError as exc:
        require("write verb" in str(exc), f"unexpected error: {exc}")
        return
    raise AssertionError("write verb was accepted")


def test_census_refuses_an_undeclared_verb() -> None:
    """Unknown safety is not the same as safe."""
    def runner(argv, timeout):
        raise AssertionError("census executed an undeclared verb")

    try:
        quantities.census_rows("manna definitely-not-a-verb --json", runner=runner)
    except QuantityError as exc:
        require("no declared contract verb" in str(exc), f"unexpected error: {exc}")
        return
    raise AssertionError("undeclared verb was accepted")


def test_census_rejects_shell_metacharacters() -> None:
    try:
        quantities.census_rows("manna list --json | head -1")
    except QuantityError as exc:
        require("never a shell" in str(exc), f"unexpected error: {exc}")
        return
    raise AssertionError("shell metacharacters were accepted")


def test_refusal_exits_two_and_emits_no_total() -> None:
    """Refused and crashed must not look alike to a caller."""
    result = run_harness("census", "lines", "tools")
    require(result.returncode == 2, f"refusal did not exit 2: {result.returncode}")
    require(result.stdout.strip() == "", f"refusal printed a number: {result.stdout!r}")

    payload = json.loads(run_harness("census", "lines", "tools", "--json").stdout)
    require(payload["refused"] is True, f"refusal not flagged: {payload}")
    require(payload["exact"] is False, f"refusal claimed exactness: {payload}")
    require("total" not in payload, f"refusal carried a total: {payload}")


def test_bare_output_is_shell_substitutable() -> None:
    """A caller writes $(...) around this; anything but the number breaks it."""
    for args in (
        ("quantity", "lookup", "anthropic.claude-sonnet-5.max_tokens"),
        ("census", "lines", "registry.yaml"),
    ):
        stdout = run_harness(*args).stdout
        require(stdout.endswith("\n"), f"{args} output not newline-terminated")
        require(stdout.strip().isdigit(), f"{args} printed more than a number: {stdout!r}")


def test_model_page_limit_comes_from_the_authority() -> None:
    """The consumer proves the layer: no page size is typed into the request."""
    import models

    captured: list[str] = []

    def fake_request(provider, url):
        captured.append(url)
        return {"data": [{"id": "claude-opus-5"}], "has_more": False}

    original = models._provider_request
    models._provider_request = fake_request
    try:
        models.fetch_provider_models("anthropic")
    finally:
        models._provider_request = original

    expected = quantities.lookup("anthropic.models_list.page_limit")["value"]
    require(captured and f"limit={expected}" in captured[0], f"page limit not read from authority: {captured}")


def test_missing_page_limit_fails_loudly() -> None:
    """A guessed page size can silently truncate a listing; absent must raise."""
    import models

    original = models.load_config
    models.load_config = lambda: {"models": {}}
    try:
        models._declared_limit("anthropic", "models_list", "page_limit")
    except models.ProviderProbeError as exc:
        require("is missing from" in str(exc), f"unexpected error: {exc}")
        return
    finally:
        models.load_config = original
    raise AssertionError("missing page limit returned a default instead of raising")


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"quantity authority tests passed ({len(tests)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
