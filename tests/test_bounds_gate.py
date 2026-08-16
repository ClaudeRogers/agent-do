#!/usr/bin/env python3
"""Bounds: declaration gate, drift against the authority, totals audit, outward scan.

Every check here is a fixture, never the live registry, with one deliberate
exception: the repo's own gate must stay green, so the last test runs it. That
mirrors how the contracts gate is tested and keeps a regression from hiding
behind a passing fixture suite.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import bounds  # noqa: E402


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ScannerTests(unittest.TestCase):
    """Detection is evidence-based: a literal in a bounding position, or nothing."""

    def test_finds_kwargs_shell_sql_and_fallback_defaults(self):
        text = (
            "resp = client.messages.create(max_tokens=4096)\n"
            'local max_tokens="8000"\n'
            "cur.execute('SELECT * FROM notes LIMIT 50')\n"
            "  max_tokens: request.max_tokens || 1024,\n"
        )
        found = {(item["parameter"], item["value"], item["syntax"])
                 for item in bounds.scan_text("a.py", text, require_family=False)}
        self.assertIn(("max_tokens", 4096, "assignment"), found)
        self.assertIn(("max_tokens", 8000, "assignment"), found)
        self.assertIn(("limit", 50, "sql_limit"), found)
        self.assertIn(("max_tokens", 1024, "or_default"), found)

    def test_comment_and_help_lines_are_documentation_not_bounds(self):
        text = "# --limit N   Max results (default: 10)\n  agent-do sessions search --limit 10\n"
        kinds = {item["site_kind"] for item in bounds.scan_text("h.sh", text, require_family=False)}
        self.assertEqual(kinds, {"doc"})

    def test_non_quantity_parameters_are_not_bounds(self):
        text = "timeout = 30\nretries = 3\nport = 8080\n"
        self.assertEqual(bounds.scan_text("a.py", text, require_family=False), [])

    def test_zero_is_a_sentinel_not_a_cap(self):
        self.assertEqual(bounds.scan_text("a.py", "limit = 0\n", require_family=False), [])

    def test_verb_attribution_names_the_enclosing_command(self):
        text = "cmd_search() {\n  local limit=25\n}\n"
        self.assertEqual(bounds.attribute_verb(text, 2, ["search", "list"]), "search")

    def test_verb_attribution_refuses_rather_than_guesses(self):
        text = "helper_function() {\n  local limit=25\n}\n"
        self.assertIsNone(bounds.attribute_verb(text, 2, ["search", "list"]))


class DeclarationShapeTests(unittest.TestCase):
    def test_source_must_be_known_and_why_must_exist(self):
        codes = {item["code"] for item in
                 bounds.validate_bound_shape("t", "v", {"source": "vibes"})}
        self.assertIn("unknown_bound_source", codes)
        self.assertIn("bound_without_why", codes)

    def test_a_citing_source_must_carry_a_ref(self):
        codes = {item["code"] for item in
                 bounds.validate_bound_shape("t", "v", {"source": "registry", "why": "x"})}
        self.assertIn("bound_without_ref", codes)

    def test_none_may_not_cite_a_ceiling(self):
        codes = {item["code"] for item in bounds.validate_bound_shape(
            "t", "v", {"source": "none", "why": "x", "ref": "anthropic.a.max_tokens"})}
        self.assertIn("bound_ref_on_none", codes)

    def test_a_ref_is_arithmetic_over_keys_and_nothing_else(self):
        values = {"anthropic.a.max_tokens": 128000}
        ok = bounds.resolve_ref("anthropic.a.max_tokens / 2", lambda k: values[k], values)
        self.assertEqual(ok["value"], 64000)
        for hostile in ("__import__('os').system('true')", "open('/etc/passwd').read()",
                        "anthropic.a.max_tokens.__class__"):
            verdict = bounds.resolve_ref(hostile, lambda k: values[k], values)
            self.assertFalse(verdict["ok"], hostile)

    def test_a_well_formed_declaration_is_clean(self):
        self.assertEqual(bounds.validate_bound_shape(
            "t", "v", {"source": "none", "why": "caller-facing default"}), [])


class GateTests(unittest.TestCase):
    """Verification 1 and 2: an undeclared bound fails, a declared one passes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write(self.root, "tools/agent-widget",
              "#!/usr/bin/env bash\ncmd_fetch() {\n  local max_tokens=4096\n}\n")
        self.addCleanup(self.tmp.cleanup)

    def registry(self, bounds_block=None):
        info = {"commands": {"fetch": "Fetch things"}, "concurrency": "read"}
        if bounds_block is not None:
            info["bounds"] = bounds_block
        return {"tools": {"widget": info}}

    def test_undeclared_bound_fails_naming_the_command_and_the_site(self):
        report = bounds.validate_bounds(self.registry(), self.root)
        self.assertEqual(report["errors"], 1)
        error = report["results"][0]["errors"][0]
        self.assertEqual(error["code"], "undeclared_bound")
        self.assertEqual(error["verb"], "fetch")
        self.assertIn("tools/agent-widget:3", error["site"])
        self.assertIn("max_tokens=4096", error["message"])

    def test_a_declaration_clears_it(self):
        report = bounds.validate_bounds(
            self.registry({"fetch": {"source": "none", "why": "caller default"}}), self.root)
        self.assertEqual(report["errors"], 0)
        self.assertEqual(report["gated_sites"], 1)

    def test_a_bound_declared_for_a_verb_the_tool_lacks_fails(self):
        report = bounds.validate_bounds(
            self.registry({"fetch": {"source": "none", "why": "ok"},
                           "nonesuch": {"source": "none", "why": "ok"}}), self.root)
        codes = {error["code"] for item in report["results"] for error in item["errors"]}
        self.assertIn("bound_unknown_command", codes)

    def test_gate_reach_equals_authority_reach(self):
        """A unit the authority cannot answer in is inventoried, never demanded."""
        write(self.root, "tools/agent-widget",
              "#!/usr/bin/env bash\ncmd_fetch() {\n  local limit=25\n}\n")
        report = bounds.validate_bounds(self.registry(), self.root)
        self.assertEqual(report["errors"], 0, "rows are not an authority unit today")
        self.assertEqual(report["ceilings_owed"], 1)
        self.assertIn("rows", report["ceilings_owed_units"])


class DriftTests(unittest.TestCase):
    """Verification 3: a bound far below its ceiling fails with both numbers."""

    AUTHORITY = {
        "models": {
            "anthropic/claude-sonnet-5": {
                "provider": "anthropic", "max_input_tokens": 1000000, "max_tokens": 128000,
            },
        },
        "roles": {"deep": {"chain": ["anthropic/claude-sonnet-5"]}},
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def registry(self, declaration, literal=128000):
        write(self.root, "tools/agent-widget",
              f"#!/usr/bin/env bash\ncmd_fetch() {{\n  local max_tokens={literal}\n}}\n")
        return {"tools": {"widget": {"commands": {"fetch": "Fetch"}, "bounds": {"fetch": declaration}}}}

    def drift(self, declaration, literal=128000):
        registry = self.registry(declaration, literal)
        return bounds.drift_bounds(registry, self.root, config=self.AUTHORITY)

    def test_the_floor_is_derived_from_the_authority_not_stored(self):
        floor = bounds.authority_delivery_floor(self.AUTHORITY)
        self.assertAlmostEqual(floor["ratio"], 128000 / 1000000)
        self.assertEqual(floor["from_record"], "anthropic/claude-sonnet-5")
        # Move the authority and the floor moves with it, with no code change.
        moved = bounds.authority_delivery_floor({"models": {
            "x/y": {"provider": "x", "max_input_tokens": 200000, "max_tokens": 64000}}})
        self.assertAlmostEqual(moved["ratio"], 0.32)

    def test_a_bound_at_its_ceiling_passes(self):
        report = self.drift({"source": "registry", "why": "the published ceiling",
                             "ref": "anthropic.claude-sonnet-5.max_tokens"})
        self.assertTrue(report["ok"], report["findings"])

    def test_a_stale_copy_fails_with_both_numbers_and_the_ratio(self):
        report = self.drift({"source": "registry", "why": "the published ceiling",
                             "ref": "anthropic.claude-sonnet-5.max_tokens"}, literal=6000)
        finding = next(item for item in report["findings"] if item["code"] == "stale_copy")
        self.assertEqual(finding["expected"], 128000)
        self.assertEqual(finding["actual"], 6000)
        self.assertAlmostEqual(finding["ratio"], 6000 / 128000)
        self.assertIn("128000", finding["message"])
        self.assertIn("6000", finding["message"])

    def test_a_stated_factor_is_an_explanation_when_it_computes(self):
        report = self.drift({"source": "derived", "why": "half the window",
                             "ref": "anthropic.claude-sonnet-5.max_input_tokens * 0.5"},
                            literal=500000)
        self.assertTrue(report["ok"], report["findings"])

    def test_integer_rounding_is_the_only_tolerance(self):
        self.assertEqual(bounds.INTEGER_ROUNDING_TOLERANCE, 0.5)
        ok = self.drift({"source": "derived", "why": "a third",
                         "ref": "anthropic.claude-sonnet-5.max_input_tokens / 3"}, literal=333333)
        self.assertTrue(ok["ok"], ok["findings"])
        bad = self.drift({"source": "derived", "why": "a third",
                          "ref": "anthropic.claude-sonnet-5.max_input_tokens / 3"}, literal=333332)
        self.assertTrue(any(item["code"] == "expression_mismatch" for item in bad["findings"]))

    def test_a_stated_factor_below_the_derived_floor_still_fails(self):
        """The inject-at-6000-against-a-window case, dressed as a derivation."""
        report = self.drift({"source": "derived", "why": "a slice of the window",
                             "ref": "anthropic.claude-sonnet-5.max_input_tokens * 0.006"},
                            literal=6000)
        finding = next(item for item in report["findings"] if item["code"] == "below_authority_floor")
        self.assertAlmostEqual(finding["ratio"], 0.006)
        self.assertAlmostEqual(finding["floor"], 0.128)
        self.assertIn("0.128", finding["message"])
        self.assertIn("anthropic/claude-sonnet-5", finding["message"])

    def test_a_dangling_ref_fails(self):
        report = self.drift({"source": "registry", "why": "x", "ref": "anthropic.no-such.max_tokens"})
        self.assertTrue(any(item["code"] == "dangling_ref" for item in report["findings"]))

    def test_measured_may_not_ship_a_literal(self):
        report = self.drift({"source": "measured", "why": "counted at call time",
                             "ref": "census rows --via 'manna list --json'"})
        self.assertTrue(any(item["code"] == "measured_bound_ships_literal"
                            for item in report["findings"]))

    def test_none_is_exempt_from_the_capacity_checks(self):
        report = self.drift({"source": "none", "why": "caller-facing default"}, literal=1)
        self.assertTrue(report["ok"], report["findings"])

    def test_router_coverage_fails_on_a_reachable_model_with_no_record(self):
        """mn-b7cb18: a chain that can select a model the authority cannot answer for."""
        config = {**self.AUTHORITY,
                  "roles": {"deep": {"chain": ["anthropic/claude-sonnet-5", "anthropic/claude-opus-5"]}}}
        coverage = bounds.check_router_coverage(config)
        self.assertFalse(coverage["ok"])
        self.assertEqual(coverage["missing"], [{"role": "deep", "model": "anthropic/claude-opus-5"}])
        self.assertIn("claude-opus-5", coverage["message"])

    def test_router_coverage_passes_when_every_chain_entry_has_a_record(self):
        self.assertTrue(bounds.check_router_coverage(self.AUTHORITY)["ok"])


class AuditTests(unittest.TestCase):
    """Verification 4: a cut without magnitude is flagged; `N of M` passes."""

    def test_a_payload_with_no_total_cannot_be_told_from_complete(self):
        verdict = bounds.audit_payload({"lessons": [1, 2, 3]})
        self.assertEqual(verdict["outcome"], "fail")
        self.assertIn("cannot tell a complete set from a capped one", verdict["reason"])

    def test_a_payload_carrying_its_total_passes(self):
        verdict = bounds.audit_payload({"lessons": [1, 2, 3], "total": 197})
        self.assertEqual(verdict["outcome"], "ok")
        self.assertEqual(verdict["total"], 197)

    def test_declaring_a_cut_without_its_magnitude_fails(self):
        verdict = bounds.audit_payload({"lessons": [1, 2, 3], "has_more": True})
        self.assertEqual(verdict["outcome"], "fail")
        self.assertIn("bare fact of a cut", verdict["reason"])

    def test_a_total_below_the_rows_returned_is_incoherent(self):
        verdict = bounds.audit_payload({"lessons": [1, 2, 3], "total": 2})
        self.assertEqual(verdict["outcome"], "fail")

    def test_text_truncation_must_carry_magnitude(self):
        self.assertEqual(bounds.audit_text("[truncated: 30 of 197 shown]")["outcome"], "ok")
        naked = bounds.audit_text("... output truncated")
        self.assertEqual(naked["outcome"], "fail")
        self.assertIn("must say N of M", naked["reason"])

    def test_output_with_no_marker_is_not_graded(self):
        self.assertEqual(bounds.audit_text("all 197 lessons")["outcome"], "skip")

    def test_audit_only_probes_verbs_the_registry_declares_read_only(self):
        calls = []

        def runner(*args):
            calls.append(args)
            raise AssertionError("a write verb must never be probed")

        registry = {"tools": {"manna": {"commands": {"create": "Create an issue"},
                                        "bounds": {"create": {"source": "none", "why": "x"}}}}}
        report = bounds.audit_bounds(registry, REPO_ROOT, runner)
        self.assertEqual(calls, [])
        self.assertEqual(report["results"][0]["outcome"], "skip")


class OutwardScanTests(unittest.TestCase):
    """Verification 5: literals near a model call are reported with the real ceiling."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_literal_beside_an_anthropic_call_is_reported_with_its_ceiling(self):
        write(self.root, "app/agent.py",
              "import anthropic\n"
              "client = anthropic.Anthropic()\n"
              "resp = client.messages.create(model='claude-sonnet-5', max_tokens=4096)\n")
        report = bounds.scan_project(self.root)
        finding = next(item for item in report["findings"] if item["parameter"] == "max_tokens")
        self.assertEqual(finding["value"], 4096)
        self.assertIn("llm", finding["families"])
        self.assertEqual(finding["ceiling"]["key"], "anthropic.claude-sonnet-5.max_tokens")
        self.assertEqual(finding["ceiling"]["value"], 128000)

    def test_a_model_the_authority_has_no_record_for_is_named_as_owed(self):
        write(self.root, "app/agent.py",
              "import anthropic\n"
              "client.messages.create(model='claude-opus-5', max_tokens=4096)\n")
        report = bounds.scan_project(self.root)
        self.assertIn("anthropic.claude-opus-5.max_tokens", report["ceilings_owed"])

    def test_a_file_with_no_bounds_is_silent(self):
        write(self.root, "app/util.py", "import anthropic\n\ndef greet():\n    return 'hi'\n")
        self.assertEqual(bounds.scan_project(self.root)["findings"], [])

    def test_a_literal_with_no_client_nearby_is_a_preference_not_a_bound(self):
        write(self.root, "app/config.py", "limit = 50\n")
        self.assertEqual(bounds.scan_project(self.root)["findings"], [])

    def test_the_scan_never_writes(self):
        source = write(self.root, "app/agent.py",
                       "import anthropic\nclient.messages.create(max_tokens=4096)\n")
        before = source.read_text(encoding="utf-8")
        bounds.scan_project(self.root)
        self.assertEqual(source.read_text(encoding="utf-8"), before)


class LiveRepoTests(unittest.TestCase):
    """Verification 2 and 6 against repo truth: the gate stays green, drift is clean."""

    def run_harness(self, *args):
        return subprocess.run(
            [str(REPO_ROOT / "agent-do"), "harness", *args],
            cwd=REPO_ROOT, text=True, capture_output=True, check=False, timeout=180,
        )

    def test_contracts_validate_passes_with_bounds_folded_in(self):
        result = self.run_harness("contracts", "validate", "--json")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload.get("bounds"))
        self.assertEqual(payload["errors"], 0)
        self.assertEqual(payload["warnings"], 0)
        self.assertEqual(payload["declared"], payload["tools"])
        self.assertEqual(payload["bounds"]["errors"], 0)
        self.assertGreater(payload["bounds"]["gated_sites"], 0)
        self.assertEqual(result.returncode, 0)

    def test_caps_outside_any_tool_are_named_rather_than_hidden(self):
        """lib/ and bin/ have no declaration home; the gate says so instead of skipping them."""
        result = self.run_harness("contracts", "validate", "--json")
        payload = json.loads(result.stdout)["bounds"]
        self.assertGreater(payload["shared_code_sites"], 0)
        self.assertTrue(all(item["file"].startswith(("lib/", "bin/"))
                            for item in payload["shared_code"]))

    def test_bounds_drift_is_clean_and_states_its_derivation(self):
        result = self.run_harness("bounds", "drift", "--json")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"], payload["findings"])
        self.assertIn("min(max_tokens / max_input_tokens)", payload["floor"]["derivation"])
        self.assertTrue(payload["coverage"]["ok"], payload["coverage"]["message"])
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
