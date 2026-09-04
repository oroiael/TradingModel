"""Portability helpers so the lab runs on a bare Windows/macOS/Linux install.

Three things bite outside a Linux container:
  * pandas needs pyarrow or fastparquet for parquet; neither is in the stdlib.
    We fall back to pickle, which is.
  * Windows consoles and open() default to cp1252, which cannot encode the
    em-dashes and arrows in the reports. Everything here is forced to UTF-8.
  * The data lives in Git LFS. An un-pulled checkout leaves 130-byte pointer
    files that fail with an unhelpful parser error 20 minutes into a run.
"""
import os, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "ccp_lab", "cache")

# --------------------------------------------------------------- console/IO
def safe_stdout():
    """Make stdout tolerate the reports' unicode on a cp1252 console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def write_text(path, txt):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)


# ------------------------------------------------------------ cache format
def _parquet_ok():
    for mod in ("pyarrow", "fastparquet"):
        try:
            __import__(mod)
            return True
        except ImportError:
            continue
    return False


PARQUET = _parquet_ok()


def save_df(df, name):
    """Write a cache table in whatever format this machine can actually read."""
    os.makedirs(CACHE, exist_ok=True)
    if PARQUET:
        p = os.path.join(CACHE, name + ".parquet")
        df.to_parquet(p, index=False)
    else:
        p = os.path.join(CACHE, name + ".pkl")
        df.to_pickle(p)
    return p


def cache_path(name):
    """The cache file for `name` this machine can actually read, or None.

    A pickle is preferred over a parquet when no parquet engine is installed,
    so a mixed cache directory still works on both kinds of machine.
    """
    exts = (".parquet", ".pkl") if PARQUET else (".pkl", ".parquet")
    for ext in exts:
        p = os.path.join(CACHE, name + ext)
        if os.path.exists(p):
            return p
    return None


def load_df(name):
    import pandas as pd
    p = cache_path(name)
    if p is None:
        raise FileNotFoundError(name)
    if p.endswith(".parquet"):
        if not PARQUET:
            raise ImportError(
                f"{os.path.basename(p)} is a parquet file but neither pyarrow nor "
                f"fastparquet is installed.\n"
                f"Either  pip install pyarrow   (recommended)\n"
                f"or delete ccp_lab/cache and re-run build_cache.py to rebuild it "
                f"in a pickle format that needs no extra package.")
        return pd.read_parquet(p)
    return pd.read_pickle(p)


# ------------------------------------------------------------- data checks
LFS_MAGIC = b"version https://git-lfs"

SOURCES = ["SOXL_1min.csv"] + [f"SOXL_Options_{y}.csv" for y in
                               (2022, 2023, 2024, 2025, 2026)]


def is_lfs_pointer(path):
    try:
        with open(path, "rb") as f:
            return f.read(len(LFS_MAGIC)) == LFS_MAGIC
    except OSError:
        return False


def check_sources(need_intraday=True):
    """Return a list of human-readable problems with the raw data, [] if fine."""
    missing, pointers = [], []
    for f in SOURCES:
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            missing.append(f)
        elif is_lfs_pointer(p):
            pointers.append(f)
    problems = []
    if missing:
        problems.append("These data files are not in the working tree: "
                        + ", ".join(missing))
    if pointers:
        problems.append(
            "These files are still Git LFS pointers, not real data: "
            + ", ".join(pointers[:4])
            + (f" (+{len(pointers)-4} more)" if len(pointers) > 4 else ""))
    if need_intraday:
        n = len(glob.glob(os.path.join(ROOT, "raw_data",
                                       "SOXL_intraday_5m_exp_*.csv")))
        if n == 0:
            problems.append("No raw_data/SOXL_intraday_5m_exp_*.csv files found.")
    return problems


HOWTO = """
The option and price data live in Git LFS and must be pulled before anything
here will run:

    git lfs install
    git lfs pull

(If `git lfs` is not a command, install Git LFS first:
 Windows  -> winget install GitHub.GitLFS      or https://git-lfs.com
 macOS    -> brew install git-lfs
 Debian   -> sudo apt-get install git-lfs)
"""

NEEDED = ["underlying_1min_1000", "underlying_daily", "chains"]


def cache_missing():
    """Names with no cache file, or one this machine cannot read.

    A parquet cache on a box without pyarrow counts as missing: it will be
    rebuilt as pickle rather than dead-ending the run.
    """
    out = []
    for n in NEEDED:
        p = cache_path(n)
        if p is None or (p.endswith(".parquet") and not PARQUET):
            out.append(n)
    return out


def ensure_cache(auto=True):
    """Build the cache if it is not there. Returns True when it is usable."""
    miss = cache_missing()
    if not miss:
        return True
    problems = check_sources()
    if problems:
        print("Cannot build the cache:\n", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        print(HOWTO, file=sys.stderr)
        return False
    if not auto:
        print(f"Cache missing ({', '.join(miss)}). Run:\n"
              f"    python ccp_lab/build_cache.py", file=sys.stderr)
        return False
    if not PARQUET and any(cache_path(n) for n in miss):
        print("The cache on disk is in parquet format but neither pyarrow nor "
              "fastparquet is installed.\n"
              "Rebuilding it as pickle, which needs no extra package. "
              "(`pip install pyarrow` would be faster and smaller.)\n", flush=True)
    else:
        print(f"Cache not found ({', '.join(miss)}). Building it now - this reads "
              f"~1GB and takes 15-25 minutes. It only happens once.\n", flush=True)
    from ccp_lab import build_cache
    if "underlying_1min_1000" in miss or "underlying_daily" in miss:
        build_cache.build_underlying()
    if "chains" in miss:
        build_cache.build_chains()
    pp = cache_path("prints_1000")
    if pp is None or (pp.endswith(".parquet") and not PARQUET):
        build_cache.build_prints()
    print("\nCache built.\n", flush=True)
    return True
