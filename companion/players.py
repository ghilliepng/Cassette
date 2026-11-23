"""The music apps Cassette follows, and how to recognise each one.

Windows' media controls name each player by an app ID (a session's source_app_user_model_id),
and the volume mixer by its program's file name. Spotify and Apple Music are one app each
(Apple Music also still plays in iTunes). YouTube Music has no Windows app of its own: it plays
in a browser tab, in a browser's installed web app, or in an unofficial desktop app (Pear
Desktop, YTMDesktop). A browser has one media session for all its tabs, so in a browser Cassette
follows whatever the browser is playing, and its volume is the whole browser's.
"""
import os
import re

NAMES = {"spotify": "Spotify", "youtube": "YouTube Music", "apple": "Apple Music"}
DEFAULT = "spotify"

# Chromium's ID for the YouTube Music web app: its installed app's session is "<browser>._crx_<id>"
YTM_WEB_APP = "cinhimbnkkaeohfgghhklpknlkffjgod"
YTM_APPS = ("youtube-music", "youtube_music", "youtubemusic", "youtube music", "ytmd")

BROWSERS = (  # (the start of the browser's app ID, its program)
    ("chrome", "chrome.exe"), ("msedge", "msedge.exe"), ("brave", "brave.exe"),
    ("opera", "opera.exe"), ("vivaldi", "vivaldi.exe"), ("firefox", "firefox.exe"),
)
FIREFOX_ID = re.compile(r"^[0-9A-Fa-f]{16}$")   # Firefox's app ID: a hash of where it's installed

# Start-menu names to open when you press play and the app isn't running (first found wins)
START_NAMES = {
    "spotify": ("Spotify",),
    "youtube": ("YouTube Music", "YouTube Music Desktop App"),
    "apple": ("Apple Music", "iTunes"),
}
YTM_WEB = "https://music.youtube.com"


def known(app):
    return app if app in NAMES else DEFAULT


def browser_program(app_id):
    """The browser's program, if this media session is a browser's (or a web app installed from
    one, which shares the browser's volume)."""
    a = app_id or ""
    low = a.lower()
    for start, exe in BROWSERS:
        if low.startswith(start):
            return exe
    if FIREFOX_ID.match(a):
        return "firefox.exe"
    return None


def rank(app, app_id):
    """How well a media session fits the chosen app: 0 not at all; higher is a better fit."""
    a = (app_id or "").lower()
    if app == "spotify":
        return 2 if "spotify" in a else 0
    if app == "apple":
        return 2 if ("applemusic" in a or "itunes" in a) else 0
    if app == "youtube":
        if YTM_WEB_APP in a or any(k in a for k in YTM_APPS):
            return 2      # YouTube Music's own window: its web app or a desktop app
        if browser_program(app_id):
            return 1      # a browser: whatever it's playing
    return 0


def owns(app, app_id, program):
    """Whether a volume-mixer entry (by its program's file name) is this player's volume."""
    p = (program or "").lower()
    if app == "spotify":
        return p == "spotify.exe"
    if app == "apple":
        return p in ("applemusic.exe", "itunes.exe")
    if app == "youtube":
        browser = browser_program(app_id)
        if browser:
            return p == browser
        return rank("youtube", app_id) == 2 and any(k in p for k in YTM_APPS)
    return False


def pick(app, sessions, current_id=None):
    """The session to follow, from (app ID, playing) pairs: the best fit, then one that's playing,
    then the one already followed (so two paused browsers don't take turns). None if none fit."""
    best, best_key = None, None
    for app_id, playing in sessions:
        r = rank(app, app_id)
        if not r:
            continue
        key = (r, bool(playing), app_id == current_id)
        if best_key is None or key > best_key:
            best, best_key = app_id, key
    return best


def start_apps():
    """{Start-menu name: what to open} for the apps installed for this user."""
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()
    shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
    items = shell.NameSpace("shell:AppsFolder").Items()
    return {items.Item(i).Name: items.Item(i).Path for i in range(items.Count)}


def open_app(app, log, apps=None):
    """Start the chosen app (pressing play with nothing to control). Returns what was opened."""
    try:
        apps = start_apps() if apps is None else apps
    except Exception as e:
        log(f"couldn't list the Start menu's apps: {e}")
        apps = {}
    for name in START_NAMES.get(app, ()):
        target = apps.get(name)
        if not target:
            continue
        path = target if os.path.isabs(target) else "shell:AppsFolder\\" + target
        try:
            os.startfile(path)
            log(f"opened {name}")
            return name
        except OSError as e:
            log(f"couldn't open {name}: {e}")
    if app == "youtube":   # not installed as an app: the web player, in the default browser
        try:
            os.startfile(YTM_WEB)
            log("opened YouTube Music in the browser")
            return YTM_WEB
        except OSError as e:
            log(f"couldn't open YouTube Music: {e}")
    elif app == "spotify":
        try:
            os.startfile("spotify:")
            return "spotify:"
        except OSError as e:
            log(f"couldn't open Spotify: {e}")
    return None
