"""Report a missing IBKR client as an instruction, not a traceback.

A deliberate copy of the repository root's `ibkr_env.py`. The live engine is
the deployable trading unit and does not import from outside its own directory:
putting the repository root on `sys.path` would let root-level scripts shadow
imports in here (`test.py` alone shadows the stdlib `test` package), and a
shadowed import inside `broker.py` is not a failure mode worth accepting to
save forty lines.

Why it exists at all: when `ib_async` fails to import, the traceback names the
wrong problem. It says "no module named ib_async", which reads as "install it"
— but the package is usually already installed and the real fault is **which
interpreter is running**:

    (env) PS C:\\Users\\...\\TradingModel> python3 fetch_1min.py
    ModuleNotFoundError: No module named 'ib_async'

`pip` resolves to the ACTIVE VENV while `python3` resolves to the Microsoft
Store shim or a system Python, so `pip install ib_async` answers "already
satisfied" and the script still cannot import it. RUNBOOK_WINDOWS.md says it in
one line — **invoke Python as `python`, not `python3`**.

Keep the two copies in step; `tests/test_live_ibkr_env.py` asserts they agree.
"""

from __future__ import annotations

import importlib
import os
import sys

#: pip name where it differs from the import name, plus what each is used for.
KNOWN = {
    "ib_async": ("ib_async", "the IBKR client the current scripts use"),
    "ibapi": ("ibapi", "IBKR's own client, used by the older 5-minute fetchers"),
    "requests": ("requests", "the ThetaData REST path"),
}


def _same_path(a: str, b: str) -> bool:
    """Windows paths differ in case and separator and still name one place."""
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.realpath(p)))
    return norm(a) == norm(b)


def diagnosis(module: str) -> str:
    """The message for a failed import: what ran, and what to do about it.

    Pure and importable, so the wording is covered by the offline self-test
    rather than only discovered when a fetch dies six hours in.
    """
    pip_name, purpose = KNOWN.get(module, (module, ""))
    script = os.path.basename(sys.argv[0]) or "this script"
    venv = os.environ.get("VIRTUAL_ENV")
    in_venv = sys.prefix != sys.base_prefix

    lines = [
        f"{module} is not importable from THIS interpreter"
        + (f" ({purpose})." if purpose else "."),
        "",
        f"  script      : {script}",
        f"  interpreter : {sys.executable}",
        f"  sys.prefix  : {sys.prefix}",
        f"  VIRTUAL_ENV : {venv or '(not set)'}",
        "",
    ]

    if venv and not _same_path(venv, sys.prefix):
        # The case that produced this module. Say which Python is wrong rather
        # than printing two paths and leaving the comparison to the reader.
        lines += [
            "  -> A virtualenv is active but this is NOT its interpreter, so you",
            "     are running the wrong Python. `pip` installs into the venv while",
            "     `python3` on Windows resolves to the Microsoft Store shim or a",
            f"     system Python -- which is why `pip install {pip_name}` can say",
            "     \"already satisfied\" while the import still fails.",
            "",
            "  Run it with the venv's interpreter instead:",
            "",
            f"      python {script}      # Windows: `python`, never `python3`",
        ]
        # Name the one that is actually on disk; printing both Windows and
        # POSIX layouts makes the reader pick, and picking is the mistake.
        candidates = [os.path.join(venv, "Scripts", "python.exe"),
                      os.path.join(venv, "bin", "python")]
        found = [c for c in candidates if os.path.exists(c)] or candidates
        lines += [f"      {c} {script}" for c in found]
    else:
        where = "this virtualenv" if in_venv else "this interpreter"
        lines += [
            f"  -> That is the environment you are running, so {pip_name} is simply",
            f"     not installed in {where}.",
            "",
            "  Install it there:",
            "",
            f"      {sys.executable} -m pip install {pip_name}",
            f"      {sys.executable} -m pip install -r requirements.txt",
        ]

    lines += [
        "",
        "  RUNBOOK_WINDOWS.md is the reference for the trading box.",
    ]
    return "\n".join(lines)


def require(module: str):
    """Import `module`, or exit with the diagnosis above.

    Raises SystemExit, not ImportError: this is for entry points a person is
    watching, where a traceback is noise and the exit code still says failed.
    """
    try:
        return importlib.import_module(module)
    except ImportError:
        raise SystemExit(diagnosis(module))


def require_ib_async():
    return require("ib_async")


def require_ibapi():
    return require("ibapi")
