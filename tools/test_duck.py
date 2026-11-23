"""Checks the companion's music dip against a fake Windows mixer (your real volume isn't touched).
Run with the companion's Python:  companion\\.venv\\Scripts\\python.exe tools\\test_duck.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "companion"))

import spotify as spotify_mod  # noqa: E402


class FakeVolume:
    def __init__(self, level):
        self.level, self.muted, self.history = level, 0, []

    def GetMasterVolume(self):
        return self.level

    def SetMasterVolume(self, level, _):
        self.level = level
        self.history.append(round(level, 3))

    def GetMute(self):
        return self.muted

    def SetMute(self, on, _):
        self.muted = on


class FakeSession:
    def __init__(self, vol):
        self.SimpleAudioVolume = vol


class FakeSpotify:
    def __init__(self):
        self.shown = None

    def set_volume(self, volume, muted):
        self.shown = volume


failed = False


def check(label, ok):
    global failed
    print(("PASS " if ok else "FAIL ") + label)
    failed |= not ok


def make(level, duck_file):
    vol = FakeVolume(level)
    spotify = FakeSpotify()
    m = spotify_mod.Mixer(spotify, lambda msg: print("   log:", msg), duck_file)
    m._sessions = lambda: [FakeSession(vol)]
    return m, vol, spotify


def main():
    duck_file = os.path.join(tempfile.mkdtemp(), "duck.json")
    m, vol, spotify = make(0.70, duck_file)
    m._read()
    check("reads the player's volume (70)", m.volume == 70 and spotify.shown == 70)

    m._set_duck(30)
    check(f"dips to 30% of 70 = 0.21 ({vol.level:.3f})", abs(vol.level - 0.21) < 0.001)
    check(f"fades down in steps ({len(vol.history)} steps)", len(vol.history) >= 10)
    check("volume is remembered on disk during the dip", os.path.exists(duck_file))
    m._read()
    check("widget still shows 70 while dipped", m.volume == 70 and spotify.shown == 70)

    m._step(1)
    check(f"volume up while dipped: 75, still dipped ({vol.level:.4f})", m.volume == 75 and abs(vol.level - 0.225) < 0.001)

    m._set_duck(30)
    lease = m.duck_until
    check("asking again just extends the dip", lease > time.time() + 30)

    vol.history.clear()
    m._set_duck(100)
    check(f"back to full: 0.75 ({vol.level:.3f})", abs(vol.level - 0.75) < 0.001)
    check(f"fades up more slowly ({len(vol.history)} steps)", len(vol.history) >= 20)
    check("remembered volume cleared", not os.path.exists(duck_file))

    # the game stops asking: the lease runs out
    m._set_duck(30)
    m.duck_until = time.time() - 1
    if m.duck < 0.999 and time.time() > m.duck_until:  # what the mixer loop does each second
        m._set_duck(100)
    check("an expired dip goes back to full", m.duck == 1.0 and abs(vol.level - 0.75) < 0.001)

    # a crash in the middle of a dip, then a fresh start
    m._set_duck(30)
    m2, vol2, _ = make(0.225, duck_file)  # Windows still has the dipped level
    m2._recover()
    check(f"after a crash mid-dip, the volume is put back to 75 ({vol2.level:.3f})", abs(vol2.level - 0.75) < 0.001)
    check("and the file is cleared", not os.path.exists(duck_file))

    print("ALL PASSED" if not failed else "SOME CHECKS FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
