"""Spotify's Web API: signing in, and the calls the in-game browser needs.

Spotify only lets an app like this serve the person who made it (Development Mode: the owner
needs Premium, and at most 5 hand-added users), so each player makes their own free developer
app and gives Cassette its Client ID. Sign-in is Authorization Code with PKCE: no secret is
needed, the browser asks the player to agree, and Spotify sends the answer to a tiny server on
this PC at REDIRECT_URI. The refresh token is kept encrypted for this Windows user (DPAPI).

What Development Mode still allows (Spotify's February 2026 rules): your playlists, the songs in
playlists you own or collaborate on (others show without their songs), liked songs, search (10
results a page), and playback control.
"""
import base64
import ctypes
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes

PORT = 43117
REDIRECT_URI = f"http://127.0.0.1:{PORT}/callback"
DASHBOARD_URL = "https://developer.spotify.com/dashboard"
SCOPES = " ".join([
    "user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing",
    "playlist-read-private", "playlist-read-collaborative", "user-library-read", "user-library-modify",
])
ACCOUNTS = "https://accounts.spotify.com"
API = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    def __init__(self, status, reason, message=""):
        super().__init__(f"{status} {reason} {message}".strip())
        self.status, self.reason, self.message = status, reason, message

    def advice(self):
        """What to tell the player, in plain words."""
        if self.reason == "port":
            return f"Another program is using port {PORT}, which Cassette needs for signing in. Close it and try again."
        if self.reason == "invalid_client":
            return "Spotify doesn't know that Client ID. Copy it again from your app's page on the dashboard."
        if self.reason == "timeout":
            return ("No answer from Spotify. If it said \"Invalid redirect URI\", the Redirect URI in your app's "
                    f"settings must be exactly {REDIRECT_URI}")
        if self.reason == "access_denied":
            return "You chose not to allow access. Press Connect to try again."
        if self.status == 403:
            return ("Spotify refused. Your developer app needs Spotify Premium on the account that made it, and if "
                    "you signed in with a different account, add that account under Users Management in the app's settings.")
        if self.status == 429:
            return "Spotify asked Cassette to slow down. Wait a minute and try again."
        if self.reason == "unexpected":
            return f"Something went wrong on this PC ({self.message}). Press Connect to try again."
        if self.status == 0:
            return "Couldn't reach Spotify. Check your internet connection."
        return f"Spotify said: {self.message or self.reason} ({self.status})"


# -- keeping the token safe: Windows DPAPI, readable only by this Windows user --
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32, _kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
_crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
_crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
_kernel32.LocalFree.argtypes = [ctypes.c_void_p]


def _dpapi(data, protect):
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    fn = _crypt32.CryptProtectData if protect else _crypt32.CryptUnprotectData
    args = (ctypes.byref(blob_in), "Cassette" if protect else None, None, None, None, 0, ctypes.byref(blob_out))
    if not fn(*args):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        _kernel32.LocalFree(blob_out.pbData)


class WebApi:
    def __init__(self, store_path, log):
        self.store_path, self.log = store_path, log
        self.lock = threading.Lock()
        self.data = {}
        try:
            with open(store_path, "rb") as f:
                self.data = json.loads(_dpapi(f.read(), False))
        except (OSError, ValueError):
            pass

    # -- state --
    @property
    def client_id(self):
        return self.data.get("client_id", "")

    @property
    def user(self):
        return self.data.get("user", "")

    def signed_in(self):
        return bool(self.data.get("refresh_token") and self.client_id)

    def _save(self):
        data = _dpapi(json.dumps(self.data).encode(), True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        for _ in range(20):  # a virus scanner often holds a fresh file for a moment
            try:
                os.replace(tmp, self.store_path)
                return
            except PermissionError:
                time.sleep(0.1)
            except OSError:  # some setups can't rename here at all (redirected folders): write directly
                break
        with open(self.store_path, "wb") as f:  # last resort: write it in place
            f.write(data)
        try:
            os.remove(tmp)
        except OSError:
            pass

    def sign_out(self):
        with self.lock:
            self.data = {"client_id": self.client_id}  # keep the ID: reconnecting is one click
            self._save()
        self.log("signed out of Spotify")

    # -- signing in --
    def sign_in(self, client_id, open_url, cancelled=lambda: False, timeout=300):
        """Opens Spotify's consent page (through open_url) and waits for the answer. Returns the
        Spotify display name; raises SpotifyError with advice() for the player."""
        client_id = client_id.strip()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        result = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            timeout = 5  # a browser's spare connection that never sends anything mustn't block us

            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if not self.path.startswith("/callback") or q.get("state", [""])[0] != state:
                    self.send_response(404)
                    self.end_headers()
                    return
                result.update({k: v[0] for k, v in q.items()})
                ok = "code" in result
                page = (_PAGE_OK if ok else _PAGE_FAIL).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, *args):
                pass

        try:
            server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
        except OSError:
            raise SpotifyError(0, "port")
        server.timeout = 0.5
        try:
            open_url(f"{ACCOUNTS}/authorize?" + urllib.parse.urlencode({
                "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
                "code_challenge_method": "S256", "code_challenge": challenge, "state": state, "scope": SCOPES,
            }))
            end = time.time() + timeout
            while not result and time.time() < end and not cancelled():
                server.handle_request()
        finally:
            server.server_close()
        if cancelled():
            raise SpotifyError(0, "cancelled")
        if not result:
            raise SpotifyError(0, "timeout")
        if "error" in result:
            raise SpotifyError(0, result["error"])
        tok = self._token_request({"grant_type": "authorization_code", "code": result["code"],
                                   "redirect_uri": REDIRECT_URI, "client_id": client_id, "code_verifier": verifier})
        with self.lock:
            self.data = {"client_id": client_id}
            self._store_token(tok)
        me = self.call("GET", "/me")
        self.call("GET", "/me/playlists", {"limit": 1})  # a 403 here means the app can't be used: say so now
        with self.lock:
            self.data["user"] = me.get("display_name") or me.get("id", "")
            self.data["user_id"] = me.get("id", "")
            self._save()
        self.log(f"signed in to Spotify as {self.user}")
        return self.user

    def _token_request(self, form):
        req = urllib.request.Request(f"{ACCOUNTS}/api/token", data=urllib.parse.urlencode(form).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = _json(e)
            raise SpotifyError(e.code, body.get("error", "token"), body.get("error_description", ""))
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            raise SpotifyError(0, "network", str(e))

    def _store_token(self, tok):
        self.data["access_token"] = tok["access_token"]
        self.data["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
        if tok.get("refresh_token"):
            self.data["refresh_token"] = tok["refresh_token"]
        self._save()

    def _access_token(self):
        with self.lock:
            if not self.signed_in():
                raise SpotifyError(401, "not_signed_in")
            if time.time() < self.data.get("expires_at", 0):
                return self.data["access_token"]
            tok = self._token_request({"grant_type": "refresh_token", "refresh_token": self.data["refresh_token"],
                                       "client_id": self.client_id})
            self._store_token(tok)
            return self.data["access_token"]

    # -- calls --
    def call(self, method, path, params=None, body=None, retry=True):
        url = (path if path.startswith("http") else API + path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else (b"" if method in ("PUT", "POST") else None)
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + self._access_token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            try:
                return json.loads(raw) if raw.strip() else {}
            except ValueError:  # some calls (shuffle, play) answer with a bare id or nothing useful
                return {}
        except urllib.error.HTTPError as e:
            body_json = _json(e)
            err = body_json.get("error") or {}
            reason = err.get("reason", "") if isinstance(err, dict) else str(err)
            message = err.get("message", "") if isinstance(err, dict) else ""
            if e.code == 401 and retry:
                with self.lock:
                    self.data["expires_at"] = 0  # force a refresh
                return self.call(method, path, params, body, retry=False)
            if e.code == 429 and retry:
                time.sleep(min(5, int(e.headers.get("Retry-After", "1") or 1)))
                return self.call(method, path, params, body, retry=False)
            raise SpotifyError(e.code, reason or "http", message)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            raise SpotifyError(0, "network", str(e))

    # -- what the browser uses --
    def playlists(self, offset, limit=50):
        return self.call("GET", "/me/playlists", {"offset": offset, "limit": limit})

    def playlist(self, pid):
        return self.call("GET", f"/playlists/{pid}")

    def playlist_items(self, pid, offset, limit=50):
        return self.call("GET", f"/playlists/{pid}/items", {"offset": offset, "limit": limit})

    def liked(self, offset, limit=50):
        return self.call("GET", "/me/tracks", {"offset": offset, "limit": limit})

    def album_tracks(self, aid, offset, limit=50):
        return self.call("GET", f"/albums/{aid}/tracks", {"offset": offset, "limit": limit})

    def search(self, query, kind, offset):
        return self.call("GET", "/search", {"q": query, "type": kind, "offset": offset, "limit": 10})

    def now_playing(self):
        """(track uri, context uri, the uri it was relinked from, "name<TAB>artists") of what's
        playing; Nones when nothing is."""
        r = self.call("GET", "/me/player") or {}
        item = r.get("item") or {}
        artists = ", ".join(a.get("name", "") for a in item.get("artists") or [])
        key = f"{item.get('name', '')}\t{artists}" if item.get("name") else None
        return (item.get("uri"), (r.get("context") or {}).get("uri"), (item.get("linked_from") or {}).get("uri"),
                key)

    def play(self, context_uri=None, uris=None, offset=None, open_spotify=None, shuffle=None):
        """Start something on this PC's Spotify. If no device is active, pick this computer's
        Spotify (opening it if needed) and try again. shuffle: True / False sets Spotify's
        shuffle first; None leaves it as it is."""
        shuffled = shuffle is None or self._set_shuffle(shuffle)  # needs a device that's awake
        body = {}
        if context_uri:
            body["context_uri"] = context_uri
        if uris:
            body["uris"] = uris
        if offset is not None:
            body["offset"] = offset
        try:
            self.call("PUT", "/me/player/play", body=body)
            if shuffle is not None:
                # Spotify can put back the shuffle a playlist had when it starts one: set it again
                # once it has started (and if no device was awake before, this is the first time)
                time.sleep(0.4)
                self._set_shuffle(shuffle)
            return
        except SpotifyError as e:
            if e.status != 404:
                raise
        result = self._play_on_this_pc(body, open_spotify)
        if shuffle is not None:
            time.sleep(0.4)
            self._set_shuffle(shuffle)
        return result

    def _set_shuffle(self, on):
        """True once set; False when no device is awake yet (Spotify answers 404)."""
        try:
            self.call("PUT", "/me/player/shuffle", {"state": "true" if on else "false"})
            return True
        except SpotifyError as e:
            if e.status == 404:
                return False
            raise

    def _play_on_this_pc(self, body, open_spotify):
        device = self._this_pc_device()
        if device is None and open_spotify:
            open_spotify()
            for _ in range(20):
                time.sleep(0.75)
                device = self._this_pc_device()
                if device:
                    break
        if device is None:
            raise SpotifyError(404, "no_device", "Spotify isn't open on this PC")
        return self.call("PUT", "/me/player/play", {"device_id": device}, body)

    def _this_pc_device(self):
        devices = self.call("GET", "/me/player/devices").get("devices", [])
        here = socket.gethostname().lower()
        computers = [d for d in devices if d.get("type") == "Computer"]
        for d in computers:
            if (d.get("name") or "").lower() == here:
                return d["id"]
        return (computers or devices or [{}])[0].get("id")


def _json(e):
    try:
        return json.loads(e.read() or b"{}")
    except (ValueError, OSError):
        return {}


_STYLE = ("<style>body{background:#121214;color:#eee;font:16px Segoe UI,sans-serif;display:flex;height:90vh;"
          "align-items:center;justify-content:center}div{text-align:center}h1{color:#1ed760;font-size:26px}</style>")
_PAGE_OK = (f"<!doctype html><meta charset=utf-8><title>Cassette</title>{_STYLE}<div><h1>Cassette is connected</h1>"
            "<p>You can close this tab and go back to the game.</p></div>")
_PAGE_FAIL = (f"<!doctype html><meta charset=utf-8><title>Cassette</title>{_STYLE}<div><h1>Not connected</h1>"
              "<p>Spotify didn't give permission. Go back to the Cassette window to try again.</p></div>")
