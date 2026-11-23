"""New versions of the app: finding them, and installing one with a click.

At start-up and then twice a day, the app asks GitHub for Cassette's newest release. That's an
anonymous request, like opening the releases page: nothing about the player is sent. If it's
newer, the tray says so and the game shows it in Cassette's options, with an Update button.

Updating downloads that release's installer, checks it against the size and SHA-256 GitHub lists
for it (it isn't run otherwise), and runs it silently. The installer replaces the app and starts
the new one; this one gets out of its way first.
"""
import hashlib
import json
import os
import re
import subprocess
import urllib.request

REPO = "ghilliepng/Cassette"
PAGE = f"https://github.com/{REPO}/releases/latest"
# (CASSETTE_UPDATE_FEED: another address for the release information, for testing an update)
FEED = os.environ.get("CASSETTE_UPDATE_FEED") or f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALLER = re.compile(r"^Cassette-Setup-(\d+)\.(\d+)\.(\d+)\.exe$")
AGENT = "Cassette-app"


def parse(text):
    """'0.1.2' or 'v0.1.2' -> (0, 1, 2), or None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def code(version):
    """A version as one number the game can read (0-4095): major x 1024 + minor x 32 + patch.
    0 means none. Must match the addon (Live.lua)."""
    if not version:
        return 0
    major, minor, patch = version
    return min(major, 3) * 1024 + min(minor, 31) * 32 + min(patch, 31)


def text(version):
    return ".".join(str(n) for n in version)


class Release:
    def __init__(self, version, name, url, size, sha256):
        self.version, self.name, self.url, self.size, self.sha256 = version, name, url, size, sha256


def latest(timeout=15):
    """The newest published release that has an installer, or None. Raises OSError/ValueError
    if GitHub can't be reached or answers oddly."""
    req = urllib.request.Request(FEED, headers={"User-Agent": AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if data.get("draft") or data.get("prerelease"):
        return None
    for a in data.get("assets") or []:
        m = INSTALLER.match(a.get("name") or "")
        if m and a.get("browser_download_url"):
            digest = a.get("digest") or ""
            sha = digest[len("sha256:"):].lower() if digest.startswith("sha256:") else None
            return Release(tuple(int(n) for n in m.groups()), a["name"], a["browser_download_url"],
                           a.get("size"), sha)
    return None


def download(release, folder, timeout=60):
    """Fetch the installer into folder and check it. Returns its path; raises ValueError if it
    isn't exactly the file GitHub lists (and deletes it)."""
    if not release.sha256:
        raise ValueError("GitHub lists no checksum for this installer")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, release.name)
    part = path + ".part"
    h, n = hashlib.sha256(), 0
    req = urllib.request.Request(release.url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                n += len(chunk)
        if release.size and n != release.size:
            raise ValueError(f"the download is {n} bytes, not {release.size}")
        if h.hexdigest() != release.sha256:
            raise ValueError("the download doesn't match GitHub's checksum")
        os.replace(part, path)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return path


def run_installer(path):
    """Start the installer on its own, silently (no questions; it keeps the earlier choices, like
    starting with Windows). /RELAUNCH=1 has it start the new app when it's done (setup.iss)."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"],
                     creationflags=flags, close_fds=True)


def clear_downloads(folder):
    """Installers left from earlier updates."""
    try:
        for name in os.listdir(folder):
            if INSTALLER.match(name) or name.endswith(".part"):
                os.remove(os.path.join(folder, name))
    except OSError:
        pass
