"""Following YouTube Music and Apple Music as well as Spotify (companion/players.py, spotify.py).

Run with the companion's Python:  companion\\.venv\\Scripts\\python.exe tools\\test_players.py
Uses stand-in media sessions: nothing on this PC is read or changed, and nothing is opened.
"""
import asyncio
import datetime
import os
import sys
import threading
import time
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "companion"))
import players  # noqa: E402
import spotify  # noqa: E402

failures = []


def check(what, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + what + ("" if ok else f": got {got!r}, want {want!r}"))
    if not ok:
        failures.append(what)


# app IDs as Windows' media controls give them
SPOTIFY = "Spotify.exe"
SPOTIFY_STORE = "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"
CHROME, EDGE, FIREFOX = "Chrome", "MSEdge", "308046B0AF4A39CB"
YTM_PWA = "Chrome._crx_cinhimbnkkaeohfgghhklpknlkffjgod"
YTM_PWA_EDGE = "MSEdge._crx_cinhimbnkkaeohfgghhklpknlkffjgod"
PEAR = "com.github.th-ch.youtube-music"
APPLE = "AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"
ITUNES = "Apple.iTunes"
OTHER = "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic"   # Media Player

# -- which sessions fit which app --
check("Spotify fits Spotify", players.rank("spotify", SPOTIFY) > 0, True)
check("Spotify (Store) fits Spotify", players.rank("spotify", SPOTIFY_STORE) > 0, True)
check("a browser doesn't fit Spotify", players.rank("spotify", CHROME), 0)
check("a browser fits YouTube Music", players.rank("youtube", CHROME), 1)
check("Edge fits YouTube Music", players.rank("youtube", EDGE), 1)
check("Firefox fits YouTube Music", players.rank("youtube", FIREFOX), 1)
check("the web app fits YouTube Music better", players.rank("youtube", YTM_PWA), 2)
check("Edge's web app too", players.rank("youtube", YTM_PWA_EDGE), 2)
check("Pear Desktop fits YouTube Music", players.rank("youtube", PEAR), 2)
check("Spotify doesn't fit YouTube Music", players.rank("youtube", SPOTIFY), 0)
check("Apple Music fits Apple Music", players.rank("apple", APPLE) > 0, True)
check("iTunes fits Apple Music", players.rank("apple", ITUNES) > 0, True)
check("Media Player fits nothing", [players.rank(a, OTHER) for a in players.NAMES], [0, 0, 0])
check("an unknown choice means Spotify", players.known("tidal"), "spotify")

# -- whose volume --
check("Spotify's volume", players.owns("spotify", SPOTIFY, "Spotify.exe"), True)
check("not Discord's", players.owns("spotify", SPOTIFY, "Discord.exe"), False)
check("in Chrome: Chrome's", players.owns("youtube", CHROME, "chrome.exe"), True)
check("in Chrome: not Edge's", players.owns("youtube", CHROME, "msedge.exe"), False)
check("web app in Chrome: Chrome's", players.owns("youtube", YTM_PWA, "chrome.exe"), True)
check("in Firefox: Firefox's", players.owns("youtube", FIREFOX, "firefox.exe"), True)
check("Pear Desktop: its own", players.owns("youtube", PEAR, "YouTube Music.exe"), True)
check("YTMDesktop: its own", players.owns("youtube", "app.ytmd", "YouTube Music Desktop App.exe"), True)
check("Pear Desktop: not Chrome's", players.owns("youtube", PEAR, "chrome.exe"), False)
check("nothing followed: nobody's", players.owns("youtube", None, "chrome.exe"), False)
check("Apple Music's", players.owns("apple", APPLE, "AppleMusic.exe"), True)

# -- which session to follow --
check("YouTube Music's own window over a browser",
      players.pick("youtube", [(CHROME, True), (YTM_PWA, False)]), YTM_PWA)
check("of two browsers, the one playing",
      players.pick("youtube", [(CHROME, False), (EDGE, True)]), EDGE)
check("of two paused browsers, the one already followed",
      players.pick("youtube", [(CHROME, False), (EDGE, False)], EDGE), EDGE)
check("Spotify chosen: ignores the playing browser",
      players.pick("spotify", [(CHROME, True), (SPOTIFY, False)]), SPOTIFY)
check("nothing fits", players.pick("apple", [(CHROME, True), (SPOTIFY, True)]), None)

# -- opening the app when play is pressed with nothing to control --
opened = []
real_startfile = os.startfile
os.startfile = lambda path: opened.append(path)
logs = []
try:
    apps = {"YouTube Music": YTM_PWA, "Spotify": r"C:\Users\x\AppData\Roaming\Spotify\Spotify.exe"}
    players.open_app("youtube", logs.append, apps)
    check("opens YouTube Music's installed app", opened[-1], "shell:AppsFolder\\" + YTM_PWA)
    players.open_app("youtube", logs.append, {})
    check("no app: the web player", opened[-1], players.YTM_WEB)
    players.open_app("spotify", logs.append, apps)
    check("opens Spotify from the Start menu", opened[-1], apps["Spotify"])
    players.open_app("apple", logs.append, {"iTunes": ITUNES})
    check("Apple Music: falls back to iTunes", opened[-1], "shell:AppsFolder\\" + ITUNES)
    n = len(opened)
    check("Apple Music not installed: opens nothing", players.open_app("apple", logs.append, {}), None)
    check("(nothing opened)", len(opened), n)
finally:
    os.startfile = real_startfile


# -- the watcher, with stand-in media sessions --
class Session:
    def __init__(self, app_id, title, playing, shuffle_ok=True):
        self.source_app_user_model_id = app_id
        self.title, self.playing, self.shuffle_ok = title, playing, shuffle_ok
        self.calls = []

    async def try_get_media_properties_async(self):
        return NS(title=self.title, artist="Artist", album_title="Album", thumbnail=None)

    def get_timeline_properties(self):
        td = datetime.timedelta
        return NS(start_time=td(0), end_time=td(seconds=200), position=td(seconds=10),
                  last_updated_time=None)

    def get_playback_info(self):
        return NS(playback_status=spotify.PLAYING if self.playing else 5, is_shuffle_active=False,
                  controls=NS(is_shuffle_enabled=self.shuffle_ok))

    async def try_toggle_play_pause_async(self):
        self.calls.append("toggle")

    async def try_change_shuffle_active_async(self, on):
        self.calls.append("shuffle")

    async def try_pause_async(self):
        self.calls.append("pause")


class Manager:
    def __init__(self, sessions):
        self.sessions = sessions

    def get_sessions(self):
        return self.sessions


changes = []
watch = spotify.Spotify(lambda p, reason: changes.append((reason, p.title)), logs.append)
threading.Thread(target=watch.loop.run_forever, daemon=True).start()   # (for its pause)
spot = Session(SPOTIFY, "Spotify song", True)
chrome = Session(CHROME, "Browser video", True, shuffle_ok=False)
m = Manager([spot, chrome])


async def poll():
    await watch._poll(m)

asyncio.run(poll())
check("follows Spotify by default", (watch.player.title, watch.app_id), ("Spotify song", SPOTIFY))
watch.set_app("youtube")
time.sleep(0.2)
check("switching away from a playing Spotify pauses it", spot.calls, ["pause"])
asyncio.run(poll())
check("switched to YouTube Music: follows the browser", (watch.player.title, watch.app_id),
      ("Browser video", CHROME))
check("...and doesn't press anything there", chrome.calls, [])
check("...and says the song changed", changes[-1], ("song", "Browser video"))
pwa = Session(YTM_PWA, "Web app song", False, shuffle_ok=False)
m.sessions.append(pwa)
asyncio.run(poll())
check("the web app opens: follows it instead", watch.player.title, "Web app song")
asyncio.run(watch._command("shuffle"))
check("no shuffle sent where the player can't take it", pwa.calls, [])
asyncio.run(watch._command("toggle"))
check("play/pause goes to the followed session", pwa.calls, ["toggle"])
m.sessions.remove(pwa)
m.sessions.remove(chrome)
asyncio.run(poll())
check("no YouTube Music left: says it's closed", (changes[-1][0], watch.player.available), ("closed", False))
watch.set_app("spotify")
asyncio.run(poll())
check("back to Spotify", (watch.player.title, watch.player.available), ("Spotify song", True))
watch.set_app("apple")
asyncio.run(poll())
opened = []
os.startfile = lambda path: opened.append(path)
real_open = players.open_app
players.open_app = lambda app, log, apps=None: opened.append(app)
try:
    asyncio.run(watch._command("toggle"))
    asyncio.run(watch._command("toggle"))
    check("play with no Apple Music: opens it, once", opened, ["apple"])
finally:
    os.startfile = real_startfile
    players.open_app = real_open

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED")
sys.exit(1 if failures else 0)
