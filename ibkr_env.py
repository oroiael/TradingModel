"""Report a missing IBKR client as an instruction, not a traceback.

`ib_async` and `ibapi` are imported by a dozen scripts here, and when the
import fails the traceback names the wrong problem. It says "no module named
ib_async", which reads as "install it" — but on Windows the package is usually
already installed and the real fault is **which interpreter is running**:

    (env) PS C:\\Users\\...\\TradingModel> python3 fas_1min_fetch.py
    ModuleNotFoundError: No module named 'ib_async'

`pip` resolves to the ACTIVE VENV while `python3` resolves to the Microsoft
Store shim or a system Python, so `pip install ib_async` answers "already
satisfied" and the script still cannot import it. `band_lab/live/RUNBOOK_WINDOWS.md`
says it in one line — **invoke Python as `python`, not `python3`** — and
`band_lab/v2_dev/option_spread_probe.py` diagnosed it once, in that one file,
after it had already cost a user their time. This module is that diagnosis
made available to every entry point instead of one.

Usage, at the point of use rather than at module import, so `--help` and the
offline self-tests still run without a broker client installed:

    from ibkr_env import require_ib_async

    def connect(...):
        require_ib_async()                  # exits with instructions if absent
        from ib_async import IB, Stock

`band_lab/live/` carries its own copy rather than importing this one: putting
the repository root on `sys.path` would let root-level scripts shadow imports
inside the live engine (`test.py` alone shadows the stdlib `test` package), and
that tree is the deployable trading unit — it does not reach outside itself.
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
        # An absolute path, and `&` in front of it: PowerShell reads a bare
        # `.env\Scripts\python.exe` as a module name, not a program, and
        # answers "The module '.env' could not be loaded" -- which sends the
        # reader off after a third, imaginary problem.
        vp = venv_python(venv)
        if vp:
            lines.append('      & "%s" %s' % (vp, script))
        lines += [
            "",
            f"  `{script} --check-env` prints where everything actually is.",
        ]
    else:
        where = "this virtualenv" if in_venv else "this interpreter"
        lines += [
            f"  -> That is the environment you are running, so {pip_name} is simply",
            f"     not installed in {where}.",
            "",
            "  Install it there:",
            "",
            f"      {sys.executable} -m pip install {pip_name}",
            f"      {sys.executable} -m pip install -r band_lab/live/requirements.txt",
        ]

    lines += [
        "",
        "  band_lab/live/RUNBOOK_WINDOWS.md is the reference for the trading box.",
    ]
    return "\n".join(lines)


def venv_python(venv: str | None = None) -> str | None:
    """The interpreter that belongs to `venv`, if it is on disk."""
    venv = venv or os.environ.get("VIRTUAL_ENV")
    if not venv:
        return None
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        candidate = os.path.join(venv, *rel)
        if os.path.exists(candidate):
            return candidate
    return None


def wrong_interpreter() -> bool:
    """Is a virtualenv active that this interpreter is not part of?"""
    venv = os.environ.get("VIRTUAL_ENV")
    return bool(venv) and not _same_path(venv, sys.prefix)


def _module_line(name: str) -> str:
    """One line per dependency: where it is, or that it is missing."""
    try:
        mod = importlib.import_module(name)
    except ImportError:
        return f"  {name:<10} MISSING from this interpreter"
    version = getattr(mod, "__version__", "")
    where = getattr(mod, "__file__", "(built-in)") or "(namespace package)"
    return f"  {name:<10} {version or 'ok':<10} {os.path.dirname(where)}"


def report(modules=("pandas", "numpy", "ib_async", "requests")) -> str:
    """Where everything actually is.

    Written for the question a person asks when a script fails on a machine
    where `pip` and `python3` disagree: *where is my environment?* Printing the
    answer beats four rounds of guessing at it.
    """
    venv = os.environ.get("VIRTUAL_ENV")
    lines = [
        "INTERPRETER",
        f"  running     {sys.executable}",
        f"  version     {sys.version.split()[0]}",
        f"  sys.prefix  {sys.prefix}",
        f"  base_prefix {sys.base_prefix}",
        "",
        "VIRTUALENV",
        f"  VIRTUAL_ENV {venv or '(not set)'}",
    ]
    if venv:
        vp = venv_python(venv)
        lines.append(f"  its python  {vp or '(no interpreter found under it)'}")
        scripts = os.path.join(venv, "Scripts")
        if os.path.isdir(scripts):
            # Windows venvs ship python.exe and pythonw.exe. Whether python3.exe
            # is there decides whether `python3` reaches this venv at all, which
            # is the whole failure this module exists for -- so show it.
            has3 = os.path.exists(os.path.join(scripts, "python3.exe"))
            lines.append(f"  python3.exe {'present' if has3 else 'ABSENT'}"
                         f"  ({scripts})")
            if not has3:
                lines.append("              -> `python3` cannot reach this venv; "
                             "it falls through PATH")
    lines += ["", "PACKAGES (in the interpreter above)"]
    lines += [_module_line(m) for m in modules]

    lines += ["", "VERDICT"]
    if wrong_interpreter():
        vp = venv_python(venv)
        lines += [
            "  A virtualenv is active and this is NOT its interpreter.",
            "  `pip` installs into the venv; this Python cannot see any of it.",
            "",
            f"  Use:  python {os.path.basename(sys.argv[0]) or '<script>'}",
        ]
        if vp:
            script = os.path.basename(sys.argv[0]) or "<script>"
            lines.append('  Or:   & "%s" %s' % (vp, script))
    elif venv:
        lines.append("  This IS the active virtualenv's interpreter.")
    else:
        lines.append("  No virtualenv is active; this is a bare interpreter.")
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
