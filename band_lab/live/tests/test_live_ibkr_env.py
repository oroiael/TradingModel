"""Tests for the missing-client diagnosis.

This message is the entire user experience of a failed IBKR import, and it is
read by someone who has just lost a run. The version that named only the module
sent a user through four rounds of `pip install` before the real fault -- the
wrong interpreter -- was visible at all, so the wording is worth asserting on:
it must name the interpreter, the virtualenv, and which of the two cases the
reader is in.
"""

from __future__ import annotations

import ast
import os
import sys

import pytest

import ibkr_env

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(HERE))


# ------------------------------------------------------------------ wording
def test_a_mismatched_virtualenv_is_named_as_the_fault(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", os.path.join(os.sep, "somewhere", "else"))
    msg = ibkr_env.diagnosis("ib_async")

    assert "NOT its interpreter" in msg
    assert sys.executable in msg          # which Python actually ran
    assert "python3" in msg               # and why that is the usual cause
    # The install command is NOT the advice here: pip already succeeded.
    assert "pip install ib_async\n" not in msg


def test_no_virtualenv_means_the_package_really_is_missing(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    msg = ibkr_env.diagnosis("ib_async")

    assert "not installed" in msg
    assert f"{sys.executable} -m pip install ib_async" in msg
    assert "NOT its interpreter" not in msg


def test_the_active_virtualenv_is_not_reported_as_the_wrong_one(monkeypatch):
    # VIRTUAL_ENV set and matching is the healthy case; calling it a mismatch
    # would send the reader hunting for an interpreter problem that isn't there.
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    assert "NOT its interpreter" not in ibkr_env.diagnosis("ib_async")


def test_the_failing_script_is_named(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["fetch_1min.py"])
    assert "fetch_1min.py" in ibkr_env.diagnosis("ib_async")


def test_an_unknown_module_still_produces_a_message():
    msg = ibkr_env.diagnosis("some_module_nobody_has")
    assert "some_module_nobody_has" in msg


# ----------------------------------------------------------------- behaviour
def test_require_returns_the_module_when_it_imports():
    assert ibkr_env.require("os") is os


def test_require_exits_rather_than_raising_importerror():
    # SystemExit, so the caller prints instructions instead of a traceback --
    # and still exits non-zero, so a shell loop over six symbols stops.
    with pytest.raises(SystemExit) as exc:
        ibkr_env.require("some_module_nobody_has")
    assert "some_module_nobody_has" in str(exc.value)


# -------------------------------------------------------------------- report
def test_report_names_the_running_interpreter_and_the_venv(monkeypatch, tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "python.exe").write_text("")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path))
    out = ibkr_env.report(modules=("os",))

    assert sys.executable in out
    assert str(tmp_path) in out
    assert str(scripts / "python.exe") in out
    # The fact that settles whether `python3` can reach the venv at all.
    assert "python3.exe ABSENT" in out
    assert "NOT its interpreter" in out


def test_report_says_so_when_the_interpreter_is_the_venv(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    out = ibkr_env.report(modules=("os",))
    assert "This IS the active virtualenv" in out
    assert "NOT its interpreter" not in out


def test_report_marks_a_missing_package(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    out = ibkr_env.report(modules=("os", "some_module_nobody_has"))
    assert "some_module_nobody_has MISSING" in out.replace("  ", " ")
    assert "MISSING" not in out.split("os")[1].split("\n")[0]


def test_wrong_interpreter_is_only_true_on_a_real_mismatch(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    assert ibkr_env.wrong_interpreter() is False
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    assert ibkr_env.wrong_interpreter() is False
    monkeypatch.setenv("VIRTUAL_ENV", os.path.join(os.sep, "nope"))
    assert ibkr_env.wrong_interpreter() is True


def test_venv_python_prefers_whichever_layout_is_on_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path))
    assert ibkr_env.venv_python() is None          # nothing there yet
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "python").write_text("")
    assert ibkr_env.venv_python() == str(tmp_path / "bin" / "python")


# --------------------------------------------------------------------- drift
def _normalized_ast(path: str) -> str:
    """The module's code with its docstring and the two intended differences
    removed, so the copies can be compared for real drift."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        tree.body.pop(0)                                  # module docstring
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # The live copy points at its own requirements.txt and runbook.
            node.value = (node.value.replace("band_lab/live/requirements.txt",
                                             "requirements.txt")
                                    .replace("band_lab/live/RUNBOOK_WINDOWS.md",
                                             "RUNBOOK_WINDOWS.md"))
    return ast.dump(tree)


def test_the_two_copies_have_not_drifted():
    """`band_lab/live/ibkr_env.py` is a deliberate copy of the root module.

    The live tree does not import from outside itself -- putting the repository
    root on `sys.path` would let root-level scripts shadow imports in here.
    Duplication is the accepted cost; silent divergence is not.
    """
    root_copy = os.path.join(ROOT, "ibkr_env.py")
    if not os.path.exists(root_copy):
        pytest.skip("running outside the repository; nothing to compare")
    assert _normalized_ast(root_copy) == _normalized_ast(ibkr_env.__file__), (
        "ibkr_env.py and band_lab/live/ibkr_env.py have diverged; "
        "change both or neither")
