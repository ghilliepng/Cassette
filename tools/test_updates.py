"""Checks the app's updater (updates.py) against a fake GitHub on this PC: finding a newer
release, and refusing a download that isn't exactly the file GitHub lists.
Run with the companion's Python:  companion\\.venv\\Scripts\\python.exe tools\\test_updates.py
"""
import hashlib
import http.server
import json
import os
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "companion"))

import updates  # noqa: E402

PAYLOAD = b"pretend installer " * 1000
served = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = served.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
updates.FEED = base + "/latest"


def feed(tag="v0.2.3", name="Cassette-Setup-0.2.3.exe", digest=None, size=None, **extra):
    asset = {"name": name, "browser_download_url": base + "/" + name, "size": size or len(PAYLOAD),
             "digest": digest if digest is not None else "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()}
    release = dict(tag_name=tag, draft=False, prerelease=False,
                   assets=[{"name": "notes.md", "browser_download_url": base + "/x"}, asset])
    release.update(extra)
    served["/latest"] = json.dumps(release).encode()
    served["/" + name] = PAYLOAD


ok = True


def check(label, cond):
    global ok
    print(("OK   " if cond else "FAIL ") + label)
    ok = ok and bool(cond)


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


check("versions read with or without a v", updates.parse("v0.1.2") == (0, 1, 2) and updates.parse("0.1.2") == (0, 1, 2))
check("nonsense isn't a version", updates.parse("latest") is None)
check("the game's number for 0.1.1 is 33 (Live.lua reads it back as 0.1.1)", updates.code((0, 1, 1)) == 33)
check("no version is 0", updates.code(None) == 0)
check("numbers stay within what the game can read", updates.code((9, 99, 99)) <= 4095)

feed()
rel = updates.latest()
check("finds the installer in the newest release", rel and rel.version == (0, 2, 3) and rel.name == "Cassette-Setup-0.2.3.exe")
check("...with GitHub's checksum", rel.sha256 == hashlib.sha256(PAYLOAD).hexdigest())

folder = tempfile.mkdtemp()
path = updates.download(rel, folder)
check("downloads it, checked", os.path.exists(path) and open(path, "rb").read() == PAYLOAD)

feed(digest="sha256:" + "0" * 64)
bad = tempfile.mkdtemp()
check("refuses a download that doesn't match the checksum", raises(lambda: updates.download(updates.latest(), bad)))
check("...and leaves nothing behind", not os.listdir(bad))
feed(size=len(PAYLOAD) + 1)
check("refuses a download of the wrong size", raises(lambda: updates.download(updates.latest(), tempfile.mkdtemp())))
feed(digest="")
check("refuses to install when GitHub lists no checksum", raises(lambda: updates.download(updates.latest(), tempfile.mkdtemp())))

feed(prerelease=True)
check("ignores pre-releases", updates.latest() is None)
feed(name="Something-else.exe")
check("ignores releases without an installer", updates.latest() is None)

updates.clear_downloads(folder)
check("old installers are cleared away", not os.listdir(folder))

server.shutdown()
print("ALL PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
