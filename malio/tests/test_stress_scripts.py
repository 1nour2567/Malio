"""Runs the standalone stress scripts inside pytest.

`test_persona_stress.py` and `test_skip_fatigue.py` assert 24 and 25 conditions
respectively and exit non-zero on failure, but they are plain scripts — pytest
never collects them. Wrapping them here means a single `pytest tests/` run
covers them, and CI can gate on them.

Both scripts are deterministic: no LLM, no network.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPTS = [
    ("test_persona_stress.py", 24),
    ("test_skip_fatigue.py", 25),
]


@pytest.mark.parametrize("script,expected", SCRIPTS, ids=[s for s, _ in SCRIPTS])
def test_stress_script_passes(script, expected):
    """The standalone script must exit 0 and report exactly `expected` passes."""
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=180,
    )
    output = (result.stdout or "") + (result.stderr or "")
    tail = output[-3000:]
    assert result.returncode == 0, f"{script} exited {result.returncode}\n{tail}"
    assert "ALL PASSED" in output, f"{script} did not report ALL PASSED\n{tail}"
    assert f"{expected} passed" in output, f"{script} expected {expected} passes\n{tail}"
    assert "0 failed" in output, f"{script} reported failures\n{tail}"
