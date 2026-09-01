#!/usr/bin/env python3
"""Fast, offline regressions for DPT's honesty boundaries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DPT = ROOT / "tools" / "agent-dpt"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    *args: str,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_color_math() -> None:
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8') +
  '\n;globalThis.__DPT_UTILS = DPT_UTILS;';
const context = {};
vm.createContext(context);
vm.runInContext(source, context);
const u = context.__DPT_UTILS;

const neutral = u.parseColor('oklch(0.5 0 0 / 50%)');
if (!neutral || Math.max(neutral.r, neutral.g, neutral.b) - Math.min(neutral.r, neutral.g, neutral.b) > 1) {
  throw new Error(`neutral oklch conversion failed: ${JSON.stringify(neutral)}`);
}
if (Math.abs(neutral.a - 0.5) > 0.001) throw new Error(`oklch alpha failed: ${neutral.a}`);

const srgb = u.parseColor('color(srgb 1 0 0 / 25%)');
if (!srgb || srgb.r !== 255 || srgb.g !== 0 || srgb.b !== 0 || Math.abs(srgb.a - 0.25) > 0.001) {
  throw new Error(`color(srgb) conversion failed: ${JSON.stringify(srgb)}`);
}

const p3 = u.parseColor('color(display-p3 0 1 0)');
if (!p3 || p3.g < 240 || p3.r > 10 || p3.b > 10) {
  throw new Error(`display-p3 conversion failed: ${JSON.stringify(p3)}`);
}

const hsl = u.parseColor('hsl(158, 30%, 55%)');
if (!hsl || hsl.g <= hsl.r || hsl.g <= hsl.b) {
  throw new Error(`hsl conversion failed: ${JSON.stringify(hsl)}`);
}

if (u.effectiveSaturation({ h: 40, s: 21, l: 88 }) >= 20) {
  throw new Error('warm near-white must not count as a chromatic accent');
}
if (u.effectiveSaturation({ h: 165, s: 60, l: 50 }) < 20) {
  throw new Error('midtone accent must remain chromatic');
}

const variableRange = u.fontWeightRange('200 900');
if (variableRange[0] !== 200 || variableRange[1] !== 900 || !(700 >= variableRange[0] && 700 <= variableRange[1])) {
  throw new Error(`variable font weight range failed: ${JSON.stringify(variableRange)}`);
}

if (u.parseColor('lab(50% 0 0)') !== null) throw new Error('unsupported lab() should not fabricate RGB');
const diagnostics = u.colorParseDiagnostics();
if (diagnostics.unparseable_count !== 1 || !diagnostics.samples[0].includes('lab(')) {
  throw new Error(`unsupported color was not surfaced: ${JSON.stringify(diagnostics)}`);
}
"""
    result = run("node", "-e", script, str(DPT / "src" / "utils.js"))
    require(result.returncode == 0, f"DPT color math failed: {result.stderr}")


def test_session_scoped_baselines() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state"
        project_a = Path(tmp) / "project-a"
        project_b = Path(tmp) / "project-b"
        project_a.mkdir()
        project_b.mkdir()

        source = DPT / "bin" / "agent-dpt"
        bash = f"""
set -euo pipefail
export AGENT_DO_HOME={json.dumps(str(state))}
export AGENT_BROWSER_SESSION=session-a
source <(sed '$d' {json.dumps(str(source))})
a1="$(baseline_file_for_project {json.dumps(str(project_a))})"
a2="$(baseline_file_for_project {json.dumps(str(project_b))})"
BROWSE_SESSION=session-b
b1="$(baseline_file_for_project {json.dumps(str(project_a))})"
printf '%s\n%s\n%s\n' "$a1" "$a2" "$b1"
"""
        result = run("bash", "-lc", bash)
        require(result.returncode == 0, f"baseline helper failed: {result.stderr}")
        paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
        require(len(paths) == 3, f"expected three baseline paths, got: {paths}")
        require(len(set(paths)) == 3, f"session and project must both scope baselines: {paths}")
        require(all(str(path).startswith(str(state)) for path in paths), f"baselines escaped state dir: {paths}")
        require(all("/tmp/dpt-baseline.json" not in str(path) for path in paths), f"global baseline survived: {paths}")


def test_installed_hook_is_thin_wrapper() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["HOME"] = tmp
        env["AGENT_DO_REPO"] = str(ROOT)
        result = run("bash", str(DPT / "install.sh"), "--hook-only", env=env)
        require(result.returncode == 0, f"DPT hook install failed: {result.stderr}")
        wrapper = Path(tmp) / ".claude" / "hooks" / "dpt-post-edit.sh"
        require(wrapper.is_file(), "DPT hook installer did not create the wrapper")
        text = wrapper.read_text()
        require("tools/agent-dpt/hooks/dpt-post-edit.sh" in text, "wrapper lost canonical hook path")
        require('exec "$canonical" "$@"' in text, "installed hook does not delegate with exec")
        require("agent-do dpt score" not in text, "installed wrapper copied scoring policy instead of delegating")


def test_false_positive_guards_are_structural() -> None:
    typography = (DPT / "src" / "layers" / "typographic-skeleton.js").read_text()
    require(
        "if (familyFaces.length === 0)" in typography and "unverifiable++" in typography,
        "system fonts without FontFace inventory must remain unknown instead of faux",
    )
    require(
        "synthesisingWeight || !hasMatchingFace" not in typography,
        "font-synthesis permission is still being treated as proof of faux bold",
    )
    spatial = (DPT / "src" / "layers" / "spatial-rhythm.js").read_text()
    require("effective_left_space" in spatial, "sr09 lost rendered side-space evidence")
    require("parent_padding_left" not in spatial, "sr09 fell back to direct-parent padding")
    hook = (DPT / "hooks" / "dpt-post-edit.sh").read_text()
    require("--for-file" in hook, "DPT hook can score without proving project-page association")


def test_generated_engine_is_current() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        copied = Path(tmp) / "agent-dpt"
        shutil.copytree(DPT, copied)
        result = run("bash", str(copied / "bin" / "build"), cwd=copied)
        require(result.returncode == 0, f"temporary DPT build failed: {result.stderr}")
        expected = (copied / "dist" / "dpt-engine.js").read_bytes()
        require(expected.startswith(b"// Design Perception Tensor"), "DPT build emitted an invalid engine")

        # dist/ is intentionally ignored. A developer checkout may have a local
        # engine to freshness-check, while a clean CI checkout must still pass
        # after proving the canonical build can create it from tracked sources.
        actual_path = DPT / "dist" / "dpt-engine.js"
        if actual_path.is_file():
            actual = actual_path.read_bytes()
            require(actual == expected, "dist/dpt-engine.js is stale; run agent-do dpt build")


def test_rule_count_claims() -> None:
    paths = [
        ROOT / "README.md",
        ROOT / "CLAUDE.md",
        ROOT / "CHANGELOG.md",
        ROOT / "registry.yaml",
        ROOT / "docs" / "TOOLS.md",
        DPT / "README.md",
        DPT / "install.sh",
        DPT / "bin" / "agent-dpt",
        DPT / "bin" / "dpt-report",
    ]
    stale = []
    for path in paths:
        text = path.read_text()
        if any(stale_claim in text for stale_claim in ("72 rules", "72-rule", "all 72", "70+ rules")):
            stale.append(str(path.relative_to(ROOT)))
    require(not stale, f"stale DPT rule-count claims remain in: {', '.join(stale)}")


def main() -> int:
    test_color_math()
    test_session_scoped_baselines()
    test_installed_hook_is_thin_wrapper()
    test_false_positive_guards_are_structural()
    test_generated_engine_is_current()
    test_rule_count_claims()
    print("dpt offline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
