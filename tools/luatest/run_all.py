r"""Runs the addon's offline checks: Lua syntax, then the widget and dip tests against a
stand-in for WoW (wowmock.lua, with real timing). Needs the `lupa` package:

    python -m venv .luavenv && .luavenv\Scripts\python -m pip install lupa
    .luavenv\Scripts\python tools\luatest\run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(os.path.dirname(os.path.dirname(HERE)), "addon", "Cassette")
MOCK = os.path.join(HERE, "wowmock.lua")

failed = 0
for script, args in [("syntax.py", [ADDON]), ("test_widget.py", [ADDON, MOCK]), ("test_duck.py", [ADDON, MOCK]), ("test_live.py", [ADDON, MOCK]), ("test_strip.py", [ADDON, MOCK]), ("test_options.py", [ADDON, MOCK])]:
    print(f"== {script}")
    failed += subprocess.call([sys.executable, os.path.join(HERE, script), *args]) != 0
print("ALL PASSED" if not failed else f"{failed} SUITE(S) FAILED")
sys.exit(1 if failed else 0)
