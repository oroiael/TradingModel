"""Import band_lab/live modules WITHOUT putting its directory on sys.path.

`overnight/` and `band_lab/live/` both contain `config.py` and `features.py`.
Putting both directories on `sys.path` makes which one wins depend on insertion
order, and the loser is silently shadowed — `run.py` imported band_lab's
`config` and failed with "cannot import name OvernightConfig", which is the
polite version of this failure. The rude version is a module that imports
successfully and is the wrong one.

So band_lab's modules are loaded by explicit file path and registered under
prefixed names. `overnight/` keeps sys.path to itself.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from types import ModuleType

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
LIVE = os.path.join(_ROOT, "band_lab", "live")
PHASE1 = os.path.join(_ROOT, "band_lab", "phase1")


def load(name: str, directory: str = LIVE) -> ModuleType:
    """Load `<directory>/<name>.py` as `bandlab_<name>`, once."""
    key = f"bandlab_{name}"
    if key in sys.modules:
        return sys.modules[key]
    path = os.path.join(directory, f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    # band_lab's modules import each other by bare name, so its directories must
    # be importable WHILE they execute — but only then, and restored after.
    saved = list(sys.path)
    for p in (PHASE1, LIVE):
        if p not in sys.path:
            sys.path.append(p)          # append, never insert: ours keep priority
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = saved
    return mod
