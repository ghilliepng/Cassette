"""Checks the companion's file protocol against a stand-in for the addon, without WoW.

The stand-in reads files the way WoW does: each file once, remembered until a "reload". It
follows the same rules as Live.lua (mail -> record -> art and view, checksum with the session
number, and the reading pace that lets the companion know where it is without check-ins).
Run with the companion's Python:  companion\\.venv\\Scripts\\python.exe tools\\sim_protocol.py
"""
import os
import shutil
import struct
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "companion"))

import live as live_pool  # noqa: E402
import tga   # noqa: E402
from spotify import Player  # noqa: E402

FONT = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\EllesmereUI\media\fonts\Expressway.TTF"


class Clock:
    """A clock the test moves by hand."""
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


class FakeAddon:
    def __init__(self, live_dir, nonce, clock):
        self.dir, self.nonce, self.clock = live_dir, nonce, clock
        self.cache = {}
        self.mail, self.record, self.art, self.view = 0, 1, 1, 1
        self.applied, self.applied_view = 0, 0
        self.state, self.page = None, None
        self.anchor = None

    def size(self, name):
        if name not in self.cache:  # WoW reads a file once
            with open(os.path.join(self.dir, name + ".tga"), "rb") as f:
                head = f.read(18)
            self.cache[name] = struct.unpack("<HH", head[12:16])
        return self.cache[name]

    def value(self, name):
        w, h = self.size(name)
        return tga.number_value(w, h)

    def send(self, live, ppu=120):
        """Any message: says where we are, and anchors the reading pace (Strip.lua)."""
        now = int(self.clock())
        self.anchor = (self.mail, now)
        return live.hello(self.nonce, self.mail, self.record, self.art, self.view, ppu, now)

    def poll(self):
        if self.anchor:  # never behind the pace (Live.lua)
            pace = self.anchor[0] + int((int(self.clock()) - self.anchor[1]) / live_pool.IDLE)
            self.mail = max(self.mail, pace)
        k = self.mail
        self.mail += 1
        r = self.value(f"m{k}")
        if r >= self.record:
            self.record = r + 1
        if r > self.applied:
            v = [self.value(f"r{r}_{f}") for f in range(7)]
            if (sum(v[:6]) + self.nonce) % 4096 != v[6]:
                return "rejected"
            self.applied = r
            art, dur, pos, when, flags, view = v[:6]
            self.state = dict(art=art, duration=dur, position=pos, when=when, playing=bool(flags & 1),
                              available=bool(flags & 8), volume=(flags >> 4) & 127, account=bool(flags & 2048), view=view)
            if art:
                self.art = max(self.art, art + 1)
                self.state["sizes"] = [self.size(f"{p}{art}") for p in ("cv", "ti", "ar")]
            if view > self.applied_view:
                self.view = max(self.view, view + 1)
                f = [self.value(f"v{view}_{i}") for i in range(5)]
                if (sum(f[:4]) + self.nonce) % 4096 == f[4]:
                    self.applied_view = view
                    self.page = dict(kind=f[0], page=f[1], pages=f[2], rows=f[3],
                                     size=self.size(f"pg{view}") if f[0] != 5 else None)
            return "applied"
        return "nothing new"


def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        global failed
        failed = True


def settle(live):
    """Wait until the companion has finished publishing (it waits 0.15 s for more changes first)."""
    time.sleep(0.05)
    if live.debounce:
        live.debounce.join(10)


failed = False


def main():
    tmp = tempfile.mkdtemp(prefix="cassette-sim-")
    clock = Clock()
    try:
        live = live_pool.Live(tmp, FONT, lambda m: None, os.path.join(tmp, "session.json"), clock=clock)
        t0 = time.time()
        made = live.ensure_pools()
        print(f"made {made} placeholder files in {time.time() - t0:.1f} s")
        live_dir = os.path.join(tmp, "live")

        song = Player(available=True, key="Still Waiting|Sum 41|Does This Look Infected?", title="Still Waiting",
                      artist="Sum 41", album="Does This Look Infected?", cover=b"", duration=158.7,
                      position=3.7, sample=time.time(), playing=True, volume=70)

        a = FakeAddon(live_dir, 1234, clock)
        check("before the companion hears anything, mail is empty", a.poll() == "nothing new")
        a.send(live)
        live.update(song)
        settle(live)
        check("first song arrives", a.poll() == "applied" and a.state["art"] == 1 and a.state["duration"] == 159)
        check("volume and play state carried", a.state["volume"] == 70 and a.state["playing"] and a.state["available"])
        cv, ti, ar = a.state["sizes"]
        check(f"cover drawn at 40 units x 1.2 = 48 px ({cv})", cv == (48, 48))
        check(f"title strip 16 units high ({ti})", ti[1] == round(16 * 1.2) and ti[0] > 20)
        check("nothing new on the next poll", a.poll() == "nothing new")

        # two idle hours, no messages at all; songs change every 200 s, and the addon reads
        # faster for a few seconds around each change, as Live.lua does
        missed, latest = 0, 1
        for i in range(36):
            for _ in range(49):  # ~196 s of idle reading, one mail every 4 s
                clock.t += live_pool.IDLE
                a.poll()
            live.update(Player(**{**song.__dict__, "key": f"song {i}", "title": f"Song {i}", "sample": clock()}))
            settle(live)
            latest = live.record
            got = False
            for _ in range(10):  # the song-end burst: every 0.5 s
                clock.t += 0.5
                a.poll()
                got = got or a.applied == latest
            if not got:
                for _ in range(2):  # or the next idle reads
                    clock.t += live_pool.IDLE
                    a.poll()
                    got = got or a.applied == latest
            missed += not got
        check(f"two idle hours without check-ins: every song change seen ({36 - missed}/36)", missed == 0)
        low, high = live.window()
        check(f"and the companion's window stays small ({high - low} mails)", high - low < 700)

        # the browser: a page, then a click's answer
        from PIL import Image
        n = live.publish_view(Image.new("RGBA", (422, 328)), 1, 0, 4, 8)
        clock.t += 0.25
        check("a browser page arrives with its numbers and picture",
              a.poll() == "applied" and a.page == dict(kind=1, page=0, pages=4, rows=8, size=(422, 328)) and a.applied_view == n)
        live.publish_view(None, 5, 0, 1, 0)
        clock.t += 0.25
        check("the 'connect Spotify' page needs no picture", a.poll() == "applied" and a.page["kind"] == 5)

        a.send(live)
        before = a.record
        live.ack(clock() + 1)
        clock.t += 0.25
        check("ack publishes a record", a.poll() == "applied" and a.record == before + 1)

        # a /reload: new session, cache cleared, cursors back to the start
        b = FakeAddon(live_dir, 999, clock)
        stale = b.poll()  # reads leftovers from the old session before the companion hears from it
        check(f"old session's records are ignored after a reload ({stale})", stale in ("rejected", "nothing new"))
        b.send(live)
        live.update(Player(**{**song.__dict__, "title": "After reload", "key": "after", "sample": clock()}))
        settle(live)
        got = None
        for _ in range(5):
            clock.t += 0.25
            got = b.poll()
            if got == "applied":
                break
        check("new session gets the current song", got == "applied" and b.state["art"] >= 1)

        # the companion restarts mid-session: it carries on without waiting for a check-in
        live.save_session()
        if live.cleaner:
            live.cleaner.stop = True
            live.cleaner.join(5)
        live = live_pool.Live(tmp, FONT, lambda m: None, live.state_path, clock=clock)
        check("restart restores the session", live.restore_session())
        clock.t += 60
        live.update(Player(**{**song.__dict__, "title": "After restart", "key": "restart", "playing": False, "sample": clock()}))
        settle(live)
        got = None
        for _ in range(3):
            clock.t += live_pool.IDLE
            got = b.poll()
            if got == "applied":
                break
        check("after a companion restart the widget keeps updating", got == "applied" and not b.state["playing"])
    finally:
        if live.cleaner:
            live.cleaner.stop = True
            live.cleaner.join(5)
        shutil.rmtree(tmp, ignore_errors=True)
    print("ALL PASSED" if not failed else "SOME CHECKS FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
