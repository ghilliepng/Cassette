"""Cassette companion: Spotify in WoW.

Runs in the system tray. Reads the Cassette addon's commands off the screen (strip), works
Spotify through Windows' media controls and mixer (spotify), and sends the song, cover and
play state back into the game through files in the addon's folder (live).

  pythonw cassette.py          normal start (tray icon, no window)
  python cassette.py --console same, and print the log to the console too
"""
import ctypes
import json
import struct
import os
import sys
import threading
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import browse    # noqa: E402
import live      # noqa: E402
import render    # noqa: E402
import connect_window     # noqa: E402
import spotify   # noqa: E402
import strip     # noqa: E402
import web       # noqa: E402

VERSION = "0.1.0"
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "Cassette")
OLD_NAME = "Jukebox"  # the working name before release: its data and autostart are carried over
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "companion.log")
ADDON = "Cassette"     # the addon's folder name
FLAVOR = "_forever_"  # WoW Forever
DEFAULTS = {
    "addon_dir": "",  # found at start-up (find_addon_dir) unless set here
    "ui_font": "",    # a font file to use when the game's own can't be read
}
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STALE_SECONDS = 5  # commands older than this were drawn while we couldn't see them: drop them

_console = "--console" in sys.argv
_log_lock = threading.Lock()


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with _log_lock:
        if _console:
            print(line, flush=True)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def find_addon_dir():
    """Where the addon lives in WoW Forever: the WoW install found from the registry, the
    usual folders, or Battle.net's. '' if WoW Forever isn't installed."""
    try:
        import casc
        root = casc.find_wow_root(FLAVOR)
    except Exception:
        return ""
    flavor = os.path.join(root, FLAVOR)
    if not os.path.isdir(flavor):
        return ""
    return os.path.join(flavor, "Interface", "AddOns", ADDON)


def _toc_version(folder):
    """The addon's version (## Version in its .toc), as a tuple; () if none."""
    try:
        for name in os.listdir(folder):
            if name.lower().endswith(".toc"):
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.lower().startswith("## version:"):
                            raw = line.split(":", 1)[1].strip()
                            return tuple(int(p) for p in raw.split(".") if p.isdigit())
    except OSError:
        pass
    return ()


def install_addon(addon_dir):
    """Put the addon this app ships with (an 'addon' folder beside it) into the game, if the
    game has none or an older one, keeping the companion's files (live). Returns what it did."""
    import shutil
    base = getattr(sys, "_MEIPASS", HERE)
    bundled = os.path.join(base, "addon", ADDON)
    if not addon_dir or not os.path.isdir(bundled):
        return ""
    have, ship = _toc_version(addon_dir), _toc_version(bundled)
    if os.path.isdir(addon_dir) and have >= ship:
        return ""
    for dirpath, dirnames, filenames in os.walk(bundled):
        rel = os.path.relpath(dirpath, bundled)
        if rel.split(os.sep)[0] == "live":
            continue
        os.makedirs(os.path.join(addon_dir, rel), exist_ok=True)
        for name in filenames:
            shutil.copy2(os.path.join(dirpath, name), os.path.join(addon_dir, rel, name))
    return "updated" if have else "installed"


def carry_over_old_name():
    """Bring the working name's data (Spotify sign-in, settings, the game's fonts) and its
    start-with-Windows entry over to this name, once."""
    import shutil
    old = os.path.join(os.path.dirname(DATA_DIR), OLD_NAME)
    if not os.path.isdir(DATA_DIR) and os.path.isdir(old):
        shutil.copytree(old, DATA_DIR, ignore=shutil.ignore_patterns("*.log", "*.old", "*.tmp"))
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as k:
            try:
                winreg.QueryValueEx(k, OLD_NAME)
            except OSError:
                return
            winreg.DeleteValue(k, OLD_NAME)
            winreg.SetValueEx(k, ADDON, 0, winreg.REG_SZ, autostart_command())
    except OSError:
        pass


def load_config():
    carry_over_old_name()
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
        os.replace(LOG_PATH, LOG_PATH + ".old")
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    # the game moved, never found yet, or the addon's name changed: look for it again
    if (not cfg.get("addon_dir") or not os.path.isdir(os.path.dirname(cfg["addon_dir"]))
            or os.path.basename(os.path.normpath(cfg["addon_dir"])) != ADDON):
        found = find_addon_dir()
        if found:
            cfg["addon_dir"] = found
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass
    return cfg


def appdata_redirected():
    """Programs started from a packaged Windows app (the Claude desktop app, for one) can have
    their AppData writes kept private to that app. Cassette's settings and sign-in would then
    vanish when it's started normally. Returns the package's folder name if that's happening:
    a probe file written to our data folder turns up in the package's private copy."""
    probe = f"probe-{os.getpid()}.tmp"
    path = os.path.join(DATA_DIR, probe)
    try:
        open(path, "w").close()
        packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
        for name in os.listdir(packages):
            if os.path.exists(os.path.join(packages, name, "LocalCache", "Local", "Cassette", probe)):
                return name
    except OSError:
        pass
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return None


def single_instance():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\CassetteCompanion")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# -- start with Windows (per-user Run key, off unless turned on from the tray) --
def autostart_command():
    if getattr(sys, "frozen", False):  # the installed app
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw}" "{os.path.join(HERE, "cassette.py")}"'


def autostart_on():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, "Cassette")[0] == autostart_command()
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "Cassette", 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, "Cassette")
            except OSError:
                pass
    log(f"start with Windows: {'on' if on else 'off'}")


class Companion:
    def __init__(self, cfg):
        self.cfg = cfg
        self.status = "starting"
        self.last_game = 0.0
        self.live = live.Live(cfg["addon_dir"], cfg["ui_font"], log, os.path.join(DATA_DIR, "session.json"))
        self.spotify = spotify.Spotify(self.on_spotify, log)
        self.mixer = spotify.Mixer(self.spotify, log, os.path.join(DATA_DIR, "duck.json"))
        self.strip = strip.StripReader(self.on_message, log)
        self.web = web.WebApi(os.path.join(DATA_DIR, "spotify.bin"), log)
        self.live.spotify_account = self.web.signed_in
        self.last_look = None  # the addon's last LOOK, to redraw once the game's fonts are read
        self.browser = browse.Browser(self.web, self.live, self.spotify.open_spotify, cfg["ui_font"], log)
        self.icon = None

    def open_setup(self):
        connect_window.open_setup(self.web, log, self.on_spotify_account)

    def on_spotify_account(self):
        """Signed in or out: the tray menu and the game show it."""
        try:
            if self.icon:
                self.icon.update_menu()
        except Exception:
            pass
        self.live.publish()

    def on_spotify(self, player, reason):
        if reason in ("song", "spotify opened", "spotify closed"):
            log(f"{reason}: {player.title} - {player.artist}" if player.available else reason)
        self.live.update(player)
        if reason == "song":
            self.browser.song_changed()

    GAME_FONTS = ("FRIZQT__.TTF", "ARIALN.TTF")  # WoW's own fonts, read from its data once

    def game_root(self):
        return os.path.dirname(os.path.dirname(os.path.dirname(self.cfg["addon_dir"])))  # ...\_forever_

    def font_file(self, wow_path):
        """A font path as WoW names it ("Interface\\AddOns\\X\\font.ttf") -> the file on this PC.
        WoW's own fonts (Fonts\\...) live inside its data: the copies read from there at start-up
        (game_fonts) are used, else the configured font."""
        parts = wow_path.replace("/", "\\").split("\\")
        path = os.path.join(self.game_root(), *parts)
        if os.path.isfile(path):
            return path
        copy = os.path.join(DATA_DIR, "fonts", parts[-1].upper())
        if os.path.isfile(copy) and os.path.getsize(copy) > 0:
            return copy
        if self.cfg.get("ui_font") and os.path.isfile(self.cfg["ui_font"]):
            return self.cfg["ui_font"]
        return os.path.join(DATA_DIR, "fonts", "FRIZQT__.TTF")  # the game's own (if it's been read)

    def game_fonts(self):
        """Read WoW's own fonts out of the player's game files, once (kept in our folder), so song
        names can be drawn in the game's font. Then redraw with it if it's the one in use."""
        try:
            import casc
        except Exception as e:
            log(f"can't read the game's fonts ({e})")
            return
        flavor = os.path.basename(self.game_root())
        got = []
        for name in self.GAME_FONTS:
            try:
                if casc.font_file(os.path.join(DATA_DIR, "fonts"), name, flavor=flavor):
                    got.append(name)
            except Exception as e:
                log(f"couldn't read {name} from the game files: {e}")
        if got:
            log("the game's fonts are ready: " + ", ".join(got))
            if self.last_look:
                self.on_look(self.last_look)

    def on_look(self, args):
        """LOOK <cover units> <r> <g> <b> <theme> <font path>: the player's layout, accent colour,
        theme and font. (Older addons send no theme.)"""
        if len(args) < 5 or not all(a.isdigit() for a in args[:4]):
            return
        self.last_look = list(args)
        cover, r, g, b = (int(a) for a in args[:4])
        rest = args[4:]
        look = "ellesmere"
        if rest and rest[0] in render.THEMES:
            look, rest = rest[0], rest[1:]
        font = self.font_file(" ".join(rest))
        log(f"look: cover {cover}, accent {r},{g},{b}, theme {look}, font {os.path.basename(font)}")
        self.browser.set_look((r, g, b), font, look)
        self.live.set_look(max(8, min(400, cover)), font, look, (r, g, b))

    def take_shot(self, args):
        """SHOT <name> <x> <y> <w> <h>: the addon's showcase (/cassette showcase) asks for a picture of
        part of the game window (pixels, from its top-left): saved to the showcase folder for
        the download pages. Only what's on screen there is read; nothing is sent to the game."""
        import re
        from PIL import Image
        if len(args) < 5 or not all(a.isdigit() for a in args[1:5]):
            return
        name = re.sub(r"[^a-z0-9-]", "", args[0].lower())[:40] or "shot"
        x, y, w, h = (int(a) for a in args[1:5])
        hwnd = strip.wow_window()
        if not hwnd or w < 8 or h < 8 or w > 4000 or h > 3000:
            return
        im = Image.frombuffer("RGBA", (w, h), strip.grab(hwnd, w, h, x, y), "raw", "BGRA", 0, 1).convert("RGB")
        folder = os.path.join(DATA_DIR, "showcase")
        os.makedirs(folder, exist_ok=True)
        self.shots = getattr(self, "shots", 0) + 1
        path = os.path.join(folder, f"{time.strftime('%H%M%S')}-{self.shots:02d}-{name}.png")
        im.save(path)
        log(f"showcase: saved {os.path.basename(path)} ({w}x{h})")

    def on_message(self, data):
        """A message from the addon (see Strip.lua): seven 16-bit numbers - time, session, next
        mail, record, art, view, pixels per unit x100 - then the command as text."""
        parts = data[14:].decode("utf-8", "replace").split()
        if len(data) < 15 or not parts:
            log(f"unreadable message: {data!r}")
            return
        t, nonce, mail, record, art, view, ppu = struct.unpack(">7H", data[:14])
        cmd, args = parts[0], parts[1:]
        now = int(time.time())
        age = (now - t) % 65536
        if age > STALE_SECONDS:
            log(f"dropped a {age} s old {cmd} (WoW was covered when it was sent)")
            return
        self.last_game = time.time()
        if self.live.hello(nonce, mail, record, art, view, ppu, now - age) and self.mixer.duck < 0.999:
            self.mixer.do("set_duck", 100)  # a new game session (a /reload) starts undipped
        if cmd == "SHOT":
            self.take_shot(args)
            return
        if cmd == "LOOK":
            self.on_look(args)
            return
        if cmd in ("BR", "PG", "OP", "PL", "PS", "BK", "FD"):
            log(f"browser {cmd} {' '.join(args)}".rstrip())
            nums = [int(a) for a in args if a.isdigit()]
            if cmd == "BR":
                self.browser.do("browse", (args or ["P"])[0])
            elif cmd == "FD" and args:
                self.browser.do("search", " ".join(args)[:100])
            elif cmd == "BK" and nums:
                self.browser.do("back", nums[0])
            # (a third number, from newer addons: the kind of list the view showed)
            kind = nums[2] if len(nums) >= 3 else None
            if cmd in ("PG", "OP") and len(nums) >= 2:
                self.browser.do({"PG": "page", "OP": "open"}[cmd], nums[0], nums[1], kind)
            elif cmd in ("PL", "PS") and len(nums) >= 2:
                self.browser.do("play", nums[0], nums[1], cmd == "PS", kind)
            # the new page or the song changing answers these; a slow Spotify (search) mustn't
            # look like the companion stopped, so say we heard if nothing's out in a moment
            timer = threading.Timer(1.2, self.live.ack, (time.time(),))
            timer.daemon = True
            timer.start()
            return
        if cmd == "D":
            if args and args[0].isdigit():
                if (int(args[0]) < 100) != (self.mixer.duck < 0.999):
                    log("music dip " + ("on" if int(args[0]) < 100 else "off"))
                self.mixer.do("set_duck", int(args[0]))
            return  # no ack needed: the widget shows the dip itself
        if cmd != "H":
            log(f"command {cmd} {' '.join(args)}".rstrip())
        if cmd == "P":
            self.spotify.command("toggle")
        elif cmd == "N":
            self.spotify.command("next")
        elif cmd == "B":
            self.spotify.command("prev")
        elif cmd == "S":
            self.spotify.command("shuffle")
        elif cmd == "VU":
            self.mixer.do("step", 1)
        elif cmd == "VD":
            self.mixer.do("step", -1)
        elif cmd == "V" and args and args[0].isdigit():
            self.mixer.do("set", int(args[0]))
        elif cmd == "M":
            self.mixer.do("mute")
        elif cmd == "SETUP":
            self.open_setup()
            return
        # answered even when nothing changes; a check-in (H) too: the addon may be asking if we're there
        timer = threading.Timer(1.2, self.live.ack, (time.time(),))
        timer.daemon = True
        timer.start()

    def keep_window_filled(self):
        while True:
            time.sleep(3)
            try:
                self.live.top_up()
            except Exception as e:
                log(f"top-up failed: {e}")
            if not self.strip.wow_seen and self.mixer.duck < 0.999:
                log("WoW closed during a music dip: back to full")
                self.mixer.do("set_duck", 100)

    def start(self):
        addon_dir = self.cfg["addon_dir"]
        if not addon_dir:
            log("WoW Forever wasn't found: set addon_dir in " + CONFIG_PATH)
        else:
            try:
                did = install_addon(addon_dir)
                if did:
                    log(f"{did} the addon in {addon_dir}")
                    self.notify(f"The {ADDON} addon was {did}. If WoW is open, type /reload once.")
            except OSError as e:
                log(f"couldn't put the addon in {addon_dir}: {e}")
        if addon_dir and not os.path.isdir(addon_dir):
            log(f"the {ADDON} addon isn't installed at {addon_dir}")
        if not addon_dir or not os.path.isdir(addon_dir):
            # nothing to talk to: say so, and keep Spotify control and sign-in working from the tray
            self.status = "WoW Forever not found"
            self.notify(f"{ADDON} couldn't find WoW Forever or its addon. Install the {ADDON} addon, then restart this app.")
            for th in (self.spotify, self.mixer):
                th.start()
            return
        self.status = "preparing files"
        t0 = time.time()
        created = self.live.ensure_pools(lambda i, n: setattr(self, "status", f"preparing files {100 * i // n}%"))
        if created:
            log(f"created {created} placeholder files in {time.time() - t0:.1f} s")
            if strip.wow_window():
                log("WoW was already running: it needs one /reload to see the new files")
                self.notify("WoW was already running: type /reload once so Cassette can show your music.")
        if not created and strip.wow_window():
            if self.live.restore_session():  # restarted while WoW was running: pick up where we were
                # the looks too: the game only says when they change
                self.browser.set_look(self.live.accent, self.live.ui_font, self.live.look)
        for th in (self.spotify, self.mixer, self.strip):
            th.start()
        threading.Thread(target=self.keep_window_filled, daemon=True, name="top-up").start()
        threading.Thread(target=self.game_fonts, daemon=True, name="game-fonts").start()
        self.status = "running"
        log(f"Cassette companion {VERSION} running")

    def notify(self, text):
        try:
            if self.icon:
                self.icon.notify(text, "Cassette")
        except Exception:
            pass

    # -- tray --
    def describe(self):
        p = self.spotify.player
        if self.status != "running":
            return f"Cassette: {self.status}"
        song = f"{p.title} - {p.artist}" if p.available and p.title else "Spotify isn't playing"
        game = "in game" if time.time() - self.last_game < 30 else "waiting for WoW"
        return f"{song}  ({game})"

    def run_tray(self):
        import pystray
        from PIL import Image, ImageDraw

        try:  # Cassette's logo (tools/make_logo.py), carried with the app
            im = Image.open(os.path.join(getattr(sys, "_MEIPASS", HERE), "logo.png")).convert("RGBA")
        except OSError:
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((2, 2, 62, 62), 14, fill=(30, 215, 96, 255))

        def toggle_autostart(icon, item):
            set_autostart(not autostart_on())

        def open_log(icon, item):
            os.startfile(LOG_PATH)

        def quit_(icon, item):
            log("quit from the tray")
            try:
                self.mixer.restore_now()
            except Exception as e:
                log(f"couldn't end the music dip: {e}")
            icon.stop()

        # the installed app's uninstaller (Inno Setup puts it beside the app)
        uninstaller = os.path.join(os.path.dirname(sys.executable), "unins000.exe")

        def uninstall(icon, item):
            log("uninstall from the tray")
            import subprocess
            subprocess.Popen([uninstaller], close_fds=True)
            quit_(icon, item)  # out of the way, so nothing is in use while it's removed

        def spotify_item(item):
            if self.web.signed_in():
                return f"Spotify: {self.web.user or 'connected'}..."
            return "Connect Spotify (playlists and search)..."

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.describe(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(spotify_item, lambda icon, item: self.open_setup()),
            pystray.MenuItem("Start with Windows", toggle_autostart, checked=lambda item: autostart_on()),
            pystray.MenuItem("Open log", open_log),
            pystray.MenuItem("Uninstall Cassette...", uninstall,
                             visible=getattr(sys, "frozen", False) and os.path.exists(uninstaller)),
            pystray.MenuItem("Quit", quit_),
        )
        self.icon = pystray.Icon("Cassette", im, "Cassette", menu)

        def setup(icon):
            icon.visible = True
            threading.Thread(target=self.start, daemon=True, name="start").start()

            def tooltip():
                while True:
                    try:
                        icon.title = self.describe()[:127]
                    except Exception:
                        pass
                    time.sleep(2)
            threading.Thread(target=tooltip, daemon=True, name="tooltip").start()

        self.icon.run(setup)


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    cfg = load_config()
    if not single_instance():
        log("already running; this copy exits")
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real screen pixels for the strip
    except Exception:
        pass
    log(f"starting Cassette companion {VERSION}")
    package = appdata_redirected()
    if package:
        log(f"WARNING: started from inside {package}: Windows keeps this copy's settings and sign-in "
            "private to that app. Start Cassette with Start-Cassette.bat or at Windows sign-in instead.")
    Companion(cfg).run_tray()
    os._exit(0)  # the worker threads are daemons; leave promptly


if __name__ == "__main__":
    main()
