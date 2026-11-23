"""Getting live information into the game.

WoW only sees files that existed when the game (or the last /reload) started, and reads each
file once, keeping its copy until the next /reload. So the companion keeps pools of placeholder
files in the addon's live folder and fills each one in just before the addon reads it, once:

  m<k>.tga        mail, read in turn. Each holds the number of the newest record (0: nothing).
  r<n>_<f>.tga    record n, fields 0-6: art, length, position, when, flags, view, checksum.
                  flags: 1 playing, 2 shuffle, 4 muted, 8 music app open, volume x 16,
                  2048 Spotify account connected (for the browser).
  cv/ti/ar<a>.tga art a: cover, title strip, artist strip.
  v<n>_<f>.tga    view n (a page of the in-game browser), fields 0-4: kind, page, pages, rows,
                  checksum; pg<n>.tga is its picture.
  app_0, app_1    this app's version and the newest one on GitHub (0: none known), as
                  updates.code numbers. Not a pool: the addon reads them once after connecting.

Numbers travel as picture sizes (see tga). Every message from the addon (through the strip)
says where it is: its session number (nonce, new each load), the next mail, record, art and view
it will read. The companion only ever writes at or after those, so nothing the addon has already
read (and cached) is changed. Checksums include the nonce, so leftovers from an earlier session
are ignored.

Knowing where the addon is without being told: between messages, the addon reads at least one
mail every IDLE seconds by the clock (it skips ahead if WoW was held up), counted from the time
and mail number in its last message. So the next mail it reads is never below
  anchor mail + (seconds since that message) / IDLE
and rarely much above it (fast reading only happens just after a click, which sends a message,
and near the end of a song). The companion keeps a band of mails filled around that point, and
the addon needs no "still here" messages at all.
"""
import json
import os
import threading
import time

import render
import tga
from spotify import Player

MAIL, RECORDS, ART, VIEWS = 15000, 1500, 600, 1000   # pool sizes; must match Live.lua
IDLE = 4             # seconds between the addon's mail reads when idle; must match Live.lua
AHEAD = 150          # mails kept filled ahead of the addon's slowest possible position
PER_SONG = 12        # extra mails the addon may read around each song change (it reads faster then)
BEHIND = 3           # and a few behind it, for clock rounding


class Session:
    def __init__(self, nonce, mail, record, art, view, ppu, when):
        self.nonce, self.record, self.art, self.view, self.ppu = nonce, record, art, view, ppu
        self.anchor_mail, self.anchor_time = mail, when   # from the addon's last message
        self.songs = 0                                    # song changes published since then


class Live:
    def __init__(self, addon_dir, ui_font, log, state_path=None, clock=time.time):
        self.dir = os.path.join(addon_dir, "live")
        self.ui_font, self.log, self.clock = ui_font, log, clock
        self.state_path = state_path  # where the game session is remembered across restarts
        self.lock = threading.RLock()
        self.session = None
        self.player = None
        self.record = 0          # last record written this session
        self.art = 0             # art of the current song this session
        self.art_key = None      # (song key, cover hash, ppu) the current art was drawn for
        self.view = 0            # newest view written this session
        self.next_record = 1
        self.next_art = 1
        self.next_view = 1
        self.mail_value = {}     # mail index -> value written this session
        self.window_end = 0
        self.cleaner = None
        self.debounce = None
        self.last_publish = 0.0
        self.spotify_account = lambda: False  # set by the companion: is the Spotify account connected?
        self.cover_units = render.COVER_UNITS  # the widget's cover size, from the game's LOOK message
        self.look = "ellesmere"                   # the addon's theme (text colours, shadow)
        self.accent = render.GREEN_RGB         # the accent colour (kept for the browser's pages)

    def set_look(self, cover_units, font, look="ellesmere", accent=None):
        """The player's layout changed its cover size, or the font or theme changed: redraw the art."""
        with self.lock:
            if accent:
                self.accent = tuple(accent)
                self.save_session()
            if (cover_units, font, look) == (self.cover_units, self.ui_font, self.look):
                return
            self.cover_units, self.ui_font, self.look = cover_units, font, look
            self.art_key = None
            self._publish()

    # -- pools --
    def path(self, name):
        return os.path.join(self.dir, name + ".tga")

    def ensure_pools(self, progress=None):
        """Create any missing placeholder files. Slow the first time (about 30,000 tiny files),
        quick afterwards. These must exist before WoW starts, or the player has to /reload."""
        os.makedirs(self.dir, exist_ok=True)
        have = set(os.listdir(self.dir))
        names = [f"m{k}" for k in range(MAIL)]
        names += [f"r{n}_{f}" for n in range(RECORDS) for f in range(7)]
        names += [f"{p}{a}" for a in range(ART) for p in ("cv", "ti", "ar")]
        names += [f"v{n}_{f}" for n in range(VIEWS) for f in range(5)]
        names += [f"pg{n}" for n in range(VIEWS)]
        names += ["app_0", "app_1"]
        missing = [n for n in names if n + ".tga" not in have]
        placeholder = tga.number(0)
        for i, name in enumerate(missing):
            with open(self.path(name), "wb") as f:
                f.write(placeholder)
            if progress and i % 2000 == 0:
                progress(i, len(missing))
        return len(missing)

    def set_app_info(self, version, newest):
        """The app's version and the newest release's, as updates.code numbers (newest 0: none).
        WoW keeps its first read of them until a /reload."""
        with self.lock:
            tga.write(self.path("app_0"), tga.number(version))
            tga.write(self.path("app_1"), tga.number(newest))

    # -- remembering the game session across a companion restart --
    def save_session(self):
        s = self.session
        if not self.state_path or s is None:
            return
        data = dict(nonce=s.nonce, mail=s.anchor_mail, when=s.anchor_time, songs=s.songs, ppu=s.ppu,
                    record=self.next_record, art=self.next_art, view=self.next_view, saved=self.clock(),
                    cover=self.cover_units, font=self.ui_font, look=self.look, accent=list(self.accent))
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass

    def restore_session(self):
        """Carry on with the game session from before a restart, if it's recent. If WoW has
        restarted meanwhile, its first message replaces this one anyway."""
        try:
            with open(self.state_path, encoding="utf-8") as f:
                d = json.load(f)
            d["when"], d["view"]  # sessions saved by older versions don't have these
        except (OSError, ValueError, TypeError, KeyError):
            return False
        if self.clock() - d.get("saved", 0) > 12 * 3600:
            return False
        with self.lock:
            self.session = Session(d["nonce"], d["mail"], d["record"], d["art"], d["view"], d["ppu"], d["when"])
            self.session.songs = d.get("songs", 0)
            self.next_record, self.next_art, self.next_view = d["record"], d["art"], d["view"]
            self.cover_units = d.get("cover", self.cover_units)
            self.look = d.get("look", self.look)
            if d.get("accent"):
                self.accent = tuple(d["accent"])
            if d.get("font") and os.path.exists(d["font"]):
                self.ui_font = d["font"]
        self.log(f"carrying on with game session {d['nonce']} (next record {d['record']}, art {d['art']})")
        return True

    def ppu(self):
        """Screen pixels per UI unit of the widget, as the addon last reported."""
        s = self.session
        return (s.ppu if s else 100) / 100

    # -- what the addon tells us (with every message) --
    def hello(self, nonce, mail, record, art, view, ppu, when=None):
        """`when`: the message's time (the addon's clock, whole seconds)."""
        when = self.clock() if when is None else when
        with self.lock:
            s = self.session
            new = s is None or s.nonce != nonce
            if new:
                self.log(f"game session {nonce}: next mail {mail}, record {record}, art {art}, view {view}")
                self.session = Session(nonce, mail, record, art, view, ppu, when)
                self.record, self.art, self.art_key, self.view = 0, 0, None, 0
                self.next_record, self.next_art, self.next_view = record, art, view
                self.mail_value, self.window_end = {}, mail
            else:
                if mail >= s.anchor_mail:
                    s.anchor_mail, s.anchor_time, s.songs = mail, when, 0
                if ppu != s.ppu:
                    s.ppu = ppu
                    self.art_key = None  # redraw the text at the new size
                self.next_record = max(self.next_record, record)
                self.next_art = max(self.next_art, art)
                self.next_view = max(self.next_view, view)
            if new or self.art_key is None:
                self._publish()
            else:
                self._fill_window()
            if new:
                self._start_cleaner()
            self.save_session()
            return new

    # -- what Spotify tells us --
    def update(self, player):
        """Spotify changed: publish shortly (several changes often come together)."""
        with self.lock:
            self.player = player
            if self.debounce:
                self.debounce.cancel()
            self.debounce = threading.Timer(0.15, self.publish)
            self.debounce.daemon = True
            self.debounce.start()

    def publish(self):
        with self.lock:
            self._publish()

    def ack(self, since):
        """After a command: if nothing has been published since, publish anyway, so the addon
        knows we heard it (volume up at 100 changes nothing, for example)."""
        with self.lock:
            if self.last_publish < since:
                self._publish()

    def publish_view(self, image, kind, page, pages, rows):
        """A new page for the in-game browser. Returns its view number (0 if it couldn't)."""
        with self.lock:
            s = self.session
            if s is None or self.next_view >= VIEWS:
                return 0
            n = self.next_view
            self.next_view += 1
            if image is not None:
                tga.write(self.path(f"pg{n}"), tga.from_image(image))
            fields = [kind, page, min(4095, pages), rows]
            fields.append((sum(fields) + s.nonce) % 4096)
            for f, v in enumerate(fields):
                tga.write(self.path(f"v{n}_{f}"), tga.number(v))
            self.view = n
            self._publish()
            return n

    # -- writing --
    def _publish(self):
        s = self.session
        if s is None:
            return
        p = self.player or Player()
        if self.next_record >= RECORDS or self.next_art >= ART:
            self.log("pools used up for this session; the addon will ask for a /reload")
            return
        art = 0
        if p.available and p.title:
            key = (p.key, hash(p.cover), s.ppu)
            if key != self.art_key:
                if self.art_key is None or key[0] != self.art_key[0]:
                    s.songs += 1  # the addon reads faster around a song change
                self._write_art(self.next_art, p, s.ppu / 100)
                self.art, self.art_key = self.next_art, key
                self.next_art += 1
            art = self.art
        n = self.next_record
        self.next_record += 1
        flags = ((p.playing * 1) | (p.shuffle * 2) | (p.muted * 4) | (p.available * 8)
                 | (max(0, min(100, p.volume)) << 4) | (bool(self.spotify_account()) * 2048))
        now = self.clock()
        when = int(now)  # whole seconds, like the addon's time(); the position is as of then
        position = max(0.0, p.position_now() - ((now - when) if p.playing else 0))
        fields = [art, min(4095, round(p.duration)), min(4095, int(position)), when % 4096, flags, self.view]
        fields.append((sum(fields) + s.nonce) % 4096)
        for f, v in enumerate(fields):
            tga.write(self.path(f"r{n}_{f}"), tga.number(v))
        self.record = n
        self.last_publish = now
        self._fill_window(rewrite=True)
        self.save_session()

    def _write_art(self, a, p, ppu):
        tga.write(self.path(f"cv{a}"), tga.from_image(render.cover(p.cover, ppu, self.cover_units)))
        T = render.theme(self.look)
        tga.write(self.path(f"ti{a}"), tga.from_image(render.text_strip(
            p.title, render.TITLE_UNITS, render.TITLE_FONT_UNITS, T["title"], ppu, self.ui_font, T["shadow"])))
        tga.write(self.path(f"ar{a}"), tga.from_image(render.text_strip(
            p.artist, render.ARTIST_UNITS, render.ARTIST_FONT_UNITS, T["artist"], ppu, self.ui_font, T["shadow"])))

    def window(self):
        """The mails the addon may read next: from its slowest possible position, onwards."""
        s = self.session
        slowest = s.anchor_mail + int(max(0.0, self.clock() - s.anchor_time) / IDLE)
        low = max(s.anchor_mail, slowest - BEHIND)
        high = min(MAIL, slowest + AHEAD + PER_SONG * s.songs)
        return low, high

    def _fill_window(self, rewrite=False):
        """Point the mails the addon will read next at the newest record."""
        s = self.session
        if s is None or not self.record:
            return
        low, high = self.window()
        self.window_end = max(self.window_end, high)
        number = tga.number(self.record)
        for k in range(low, high):
            if rewrite or self.mail_value.get(k) != self.record:
                tga.write(self.path(f"m{k}"), number)
                self.mail_value[k] = self.record

    def top_up(self):
        """Called every few seconds: the window moves on with the clock."""
        with self.lock:
            self._fill_window()

    def _start_cleaner(self):
        """Mails past the window may hold numbers from an earlier session. Reset them to 0,
        from the far end back towards the window, in the background."""
        if self.cleaner and self.cleaner.is_alive():
            self.cleaner.stop = True
        nonce = self.session.nonce
        zero = tga.number(0)

        def clean():
            me = threading.current_thread()
            for k in range(MAIL - 1, -1, -1):
                if getattr(me, "stop", False):
                    return
                with self.lock:
                    if self.session is None or self.session.nonce != nonce or k < self.window_end + AHEAD:
                        return
                    if self.mail_value.get(k, -1) != 0:
                        tga.write(self.path(f"m{k}"), zero)
                        self.mail_value[k] = 0
                time.sleep(0)  # let publishing in between

        self.cleaner = threading.Thread(target=clean, daemon=True, name="mail-cleaner")
        self.cleaner.start()
