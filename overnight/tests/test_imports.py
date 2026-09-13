"""Regression guard for a bug that imported the wrong module and still "worked".

`overnight/` and `band_lab/live/` both contain `config.py` and `features.py`.
When both directories were on `sys.path`, band_lab's won and `run.py` died with
"cannot import name OvernightConfig from config". That was the lucky version:
the unlucky one is a module that imports cleanly and is the wrong file.

These tests assert the modules under test are the ones on disk here, and that
loading a band_lab module cannot change that.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _in_overnight(mod):
    return os.path.dirname(os.path.abspath(mod.__file__)) == HERE


def test_our_modules_are_ours_before_anything_else_loads():
    import config, constants, core, features, schedule, state
    for m in (config, constants, core, features, schedule, state):
        assert _in_overnight(m), f"{m.__name__} resolved to {m.__file__}"


def test_loading_bandlab_does_not_shadow_ours():
    import bandlab
    bandlab.load("store")
    import config, features
    assert _in_overnight(config)
    assert _in_overnight(features)


def test_bandlab_modules_load_from_bandlab():
    import bandlab
    store = bandlab.load("store")
    assert store.__file__.replace("\\", "/").endswith("band_lab/live/store.py")
    assert hasattr(store, "Store")


def test_bandlab_load_is_idempotent():
    import bandlab
    assert bandlab.load("store") is bandlab.load("store")


def test_bandlab_load_leaves_sys_path_clean():
    """It appends its directories only while executing, then restores."""
    import bandlab
    before = list(sys.path)
    bandlab.load("config")            # band_lab's config, not ours
    assert sys.path == before


def test_the_two_configs_are_genuinely_different_files():
    import bandlab, config
    theirs = bandlab.load("config")
    assert theirs.__file__ != config.__file__
    assert hasattr(config, "OvernightConfig")
    assert hasattr(theirs, "EngineConfig")
