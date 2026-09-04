#!/usr/bin/env python3
"""Preflight — tells you exactly what is missing before you run anything.

    python ccp_lab/doctor.py
"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ccp_lab.compat import (ROOT, CACHE, PARQUET, NEEDED, cache_path, safe_stdout,
                            check_sources, is_lfs_pointer, SOURCES, HOWTO)

safe_stdout()
ok = True
print(f"python      {sys.version.split()[0]}  ({sys.platform})")
print(f"working dir {os.getcwd()}")
print(f"repo root   {ROOT}\n")

print("packages")
for mod, needed in [("pandas", True), ("numpy", True),
                    ("pyarrow", False), ("fastparquet", False)]:
    try:
        m = __import__(mod)
        print(f"  [ok]   {mod} {getattr(m, '__version__', '')}")
    except ImportError:
        if needed:
            ok = False
            print(f"  [MISS] {mod} — required.  pip install {mod}")
        else:
            print(f"  [--]   {mod} not installed (optional)")
if not PARQUET:
    print("  note: no parquet engine, so the cache will use pickle. That works;\n"
          "        `pip install pyarrow` makes it smaller and faster to load.")

print("\nsource data")
for f in SOURCES:
    p = os.path.join(ROOT, f)
    if not os.path.exists(p):
        ok = False
        print(f"  [MISS] {f}")
    elif is_lfs_pointer(p):
        ok = False
        print(f"  [LFS]  {f} — still a pointer, {os.path.getsize(p)} bytes")
    else:
        print(f"  [ok]   {f}  {os.path.getsize(p)/1e6:,.0f} MB")
n = len(glob.glob(os.path.join(ROOT, "raw_data", "SOXL_intraday_5m_exp_*.csv")))
ptr = sum(1 for x in glob.glob(os.path.join(ROOT, "raw_data",
                                            "SOXL_intraday_5m_exp_*.csv"))
          if is_lfs_pointer(x))
print(f"  {'[ok]  ' if n and not ptr else '[LFS] '} raw_data intraday files: "
      f"{n} found, {ptr} still LFS pointers")
if ptr:
    print("         these are optional — without them every option is priced by\n"
          "         model rather than by a real 10:00 trade print")

print("\ncache")
for nme in NEEDED + ["prints_1000"]:
    p = cache_path(nme)
    if p is None:
        print(f"  [--]   {nme} — will be built on first run")
    elif p.endswith(".parquet") and not PARQUET:
        print(f"  [!]    {nme} — parquet, unreadable here; will rebuild as pickle")
    else:
        print(f"  [ok]   {os.path.basename(p)}  {os.path.getsize(p)/1e6:,.1f} MB")

if check_sources():
    print(HOWTO)
print("\nVERDICT:", "ready" if ok else "fix the [MISS]/[LFS] items above")
sys.exit(0 if ok else 1)
