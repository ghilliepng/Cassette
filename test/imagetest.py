"""Cassette test helper, for the CassetteTest addon (test 4).

At start: empties the addon's img folder and makes 1 x 1 placeholders (sz0-sz7, rt0-rt39),
which have to exist before the /reload. Then reads the strip of coloured squares the addon
shows in the top-left corner; when it says READY, gives every placeholder its real size.
(draw_all / redraw_forever are from tests 1-3.)

  python imagetest.py --init           create the pictures once (they must exist before WoW starts)
  python imagetest.py                  keep redrawing and reading until Ctrl+C
  python imagetest.py --shot out.png   save a screenshot of the WoW window
  python imagetest.py --preview out.png  save one test picture as a PNG, to check the drawing
"""
import colorsys
import ctypes
import os
import struct
import sys
import threading
import time
import zlib
from ctypes import wintypes

ADDON = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\CassetteTest"
IMG = os.path.join(ADDON, "img")
W, H = 256, 64            # picture size (powers of two)
PERIOD, SLOTS = 2, 30     # test 1 only
POOL = 300                # must match CassetteTest.lua
PROBE_FONT = r"C:\Windows\Fonts\marlett.ttf"  # any small, valid TrueType file
SQ, MAXLEN = 3, 120       # strip square size in screen pixels, longest text
MAXSQ = 2 + (24 + 8 * MAXLEN + 2) // 3


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------------------------

FONT = {  # 5 x 7 digits
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
}


def render(text, hue, W=W, H=H, scale=5):
    """White text on a coloured background, as top-down BGRA bytes."""
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.65, 0.55))
    px = bytearray(bytes((b, g, r, 255)) * (W * H))
    cw = 6 * scale
    x0 = (W - len(text) * cw + scale) // 2
    y0 = (H - 7 * scale) // 2
    white = b"\xff" * (scale * 4)
    for ci, ch in enumerate(text):
        for gy, row in enumerate(FONT.get(ch, ())):
            for gx, bit in enumerate(row):
                if bit == "1":
                    for dy in range(scale):
                        start = ((y0 + gy * scale + dy) * W + x0 + ci * cw + gx * scale) * 4
                        px[start:start + scale * 4] = white
    return px


def write_tga(path, px, W=W, H=H):
    """Uncompressed 32-bit TGA, bottom-left origin (the same layout as the TGAs other addons ship)."""
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, W, H, 32, 8)
    data = header + b"".join(px[(H - 1 - y) * W * 4:(H - y) * W * 4] for y in range(H))
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    for _ in range(5):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.02)
    try:  # WoW is holding it: overwrite in place instead
        with open(path, "r+b") as f:
            f.write(data)
        os.remove(tmp)
        return True
    except OSError as e:
        log(f"couldn't write {os.path.basename(path)}: {e}")
        return False


def write_sized(path, w, h, grey=False):
    """A plain grey picture of exactly w x h pixels: 32-bit, or 8-bit greyscale (TGA type 3)."""
    if grey:
        data = struct.pack("<BBBHHBHHHHBB", 0, 0, 3, 0, 0, 0, 0, 0, w, h, 8, 0) + b"\x80" * (w * h)
    else:
        data = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8) + b"\x80\x80\x80\xff" * (w * h)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# test 4: file -> (width, height, grey) once READY arrives
SIZES = {"sz0": (37, 5, False), "sz1": (37, 5, False), "sz2": (37, 5, False), "sz3": (37, 5, False),
         "sz4": (1000, 1, False), "sz5": (4096, 1, False), "sz6": (37, 5, True), "sz7": (300, 200, False)}
SIZES.update({f"rt{k}": (5, 3, False) for k in range(40)})


def prepare_test4():
    """1 x 1 placeholders for every test 4 file; these must exist before the /reload."""
    os.makedirs(IMG, exist_ok=True)
    for name in os.listdir(IMG):
        remove(os.path.join(IMG, name))
    for name in SIZES:
        write_sized(os.path.join(IMG, name + ".tga"), 1, 1)


def answer_ready(text):
    if not text.startswith("READY"):
        return
    start = time.perf_counter()
    for name, (w, h, grey) in SIZES.items():
        write_sized(os.path.join(IMG, name + ".tga"), w, h, grey)
    log(f"READY answered: {len(SIZES)} files given their real sizes in {(time.perf_counter() - start) * 1000:.0f} ms")


def stamp(t):
    return time.strftime("%H:%M:%S", time.localtime(t))


def draw_all():
    """Everything test 3 needs to exist before the /reload: a.tga, the pool, and q.tga / q.ttf."""
    os.makedirs(IMG, exist_ok=True)
    now = int(time.time())
    write_tga(os.path.join(IMG, "a.tga"), render(stamp(now), (now % 12) / 12))
    blank = render("00:00:00", 0.0)
    for k in range(POOL):
        write_tga(os.path.join(IMG, f"pool{k}.tga"), blank)
    write_tga(os.path.join(IMG, "q.tga"), render(stamp(now), 0.33, 128, 32, 2), 128, 32)
    with open(PROBE_FONT, "rb") as src, open(os.path.join(IMG, "q.ttf"), "wb") as dst:
        dst.write(src.read())
    # earlier tests' files are no longer used
    for name in os.listdir(IMG):
        if name[0] in "bcdfpn" and not name.startswith("pool"):
            remove(os.path.join(IMG, name))


def remove(*paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def redraw_forever(stop):
    last, filled = None, {}
    while not stop.is_set():
        sec = int(time.time())
        if sec != last:
            last = sec
            write_tga(os.path.join(IMG, "a.tga"), render(stamp(sec), (sec % 12) / 12))
            # row P: fill the pool file for this second (if not yet) and the next, ahead of time
            for t in (sec, sec + 1):
                k = t % POOL
                if filled.get(k) != t:
                    write_tga(os.path.join(IMG, f"pool{k}.tga"), render(stamp(t), (t % 12) / 12))
                    filled[k] = t
        time.sleep(0.05)


# ---------------------------------------------------------------------------------------------
# Reading the screen
# ---------------------------------------------------------------------------------------------

u, g = ctypes.windll.user32, ctypes.windll.gdi32
u.FindWindowW.restype = wintypes.HWND
u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u.IsWindow.argtypes = [wintypes.HWND]
u.GetDC.restype = wintypes.HDC
u.GetDC.argtypes = [wintypes.HWND]
u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
g.CreateCompatibleDC.restype = wintypes.HDC
g.CreateCompatibleDC.argtypes = [wintypes.HDC]
g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g.SelectObject.restype = wintypes.HGDIOBJ
g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
g.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
g.DeleteDC.argtypes = [wintypes.HDC]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                        ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]


def wow_window():
    # WoW's own window class, not a browser tab's title. Older clients use GxWindowClass;
    # WoW Forever 1.60 uses "waApplication Window".
    for cls in ("waApplication Window", "GxWindowClass"):
        hwnd = u.FindWindowW(cls, None)
        if hwnd:
            return hwnd
    return None


def grab(hwnd, w, h):
    """The top-left w x h pixels of the window's client area, as top-down BGRA bytes."""
    pt = wintypes.POINT(0, 0)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    sdc = u.GetDC(None)
    mdc = g.CreateCompatibleDC(sdc)
    bmp = g.CreateCompatibleBitmap(sdc, w, h)
    old = g.SelectObject(mdc, bmp)
    g.BitBlt(mdc, 0, 0, w, h, sdc, pt.x, pt.y, 0x00CC0020)  # SRCCOPY
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    g.SelectObject(mdc, old)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(None, sdc)
    return bytes(buf)


def checksum(seq, data):
    """Sequence, length and text, each weighted by position, mod 255 (as in CassetteTest.lua)."""
    return sum(v * (k + 1) for k, v in enumerate([seq, len(data), *data])) % 255


def level(v):
    return 1 if v > 191 else 0 if v < 64 else None


def decode(buf, w):
    """((seq, text), None) for a readable strip, (None, reason) for a broken one, (None, None) for none."""
    def square(i):
        o = (1 * w + i * SQ + 1) * 4  # the square's middle pixel
        return level(buf[o + 2]), level(buf[o + 1]), level(buf[o])

    if square(0) != (0, 1, 1) or square(1) != (1, 1, 0):
        return None, None
    bits = []

    def need(n):
        while len(bits) < n:
            i = 2 + len(bits) // 3
            if i >= MAXSQ:
                return False
            s = square(i)
            if None in s:
                return False
            bits.extend(s)
        return True

    def byte(k):
        return int("".join(map(str, bits[k * 8:k * 8 + 8])), 2)

    if not need(24):
        return None, "unclear colours"
    seq, length, check = byte(0), byte(1), byte(2)
    if length > MAXLEN:
        return None, "too long"
    if not need(24 + 8 * length):
        return None, "unclear colours"
    data = bytes(byte(3 + i) for i in range(length))
    if checksum(seq, data) != check:
        return None, "bad checksum"
    return (seq, data.decode("utf-8", "replace")), None


def read_forever(stop, on_text=None):
    w, h = MAXSQ * SQ, SQ
    hwnd, looked = None, 0.0
    last, last_ping = None, None
    good = missed = rejected = 0
    reasons = {}
    report = time.time() + 30
    while not stop.is_set():
        time.sleep(0.05)
        if not hwnd or time.time() - looked > 5:
            looked = time.time()
            found = wow_window()
            if found and found != hwnd:
                log("found the WoW window")
            hwnd = found
        if not hwnd or not u.IsWindow(hwnd):
            hwnd = None
            continue
        got, why = decode(grab(hwnd, w, h), w)
        if got and got != last:
            last = got
            good += 1
            seq, text = got
            n = text[5:]
            if text.startswith("PING ") and n.isdigit():
                n = int(n)
                if last_ping is not None and n > last_ping + 1:
                    missed += n - last_ping - 1
                last_ping = n
            if good <= 3 or not text.startswith("PING "):
                log(f"strip read: {text!r} (seq {seq})")
            if on_text:
                on_text(text)
        elif why:
            rejected += 1
            reasons[why] = reasons.get(why, 0) + 1
        if time.time() > report:
            report = time.time() + 30
            if good or rejected:
                log(f"strip so far: {good} read, {missed} missed, {rejected} unreadable frames {reasons or ''}")


# ---------------------------------------------------------------------------------------------
# PNG output (screenshots and previews)
# ---------------------------------------------------------------------------------------------

def save_png(path, w, h, bgra):
    raw = bytearray()
    for y in range(h):
        row = bgra[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        raw += b"\x00" + rgb

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def shot(path):
    hwnd = wow_window()
    if not hwnd:
        log("WoW isn't running.")
        return
    r = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(r))
    save_png(path, r.right, r.bottom, grab(hwnd, r.right, r.bottom))
    log(f"saved {path} ({r.right} x {r.bottom})")


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, not scaled ones
    except Exception:
        pass
    args = sys.argv[1:]
    if args[:1] == ["--shot"]:
        return shot(args[1] if len(args) > 1 else "wow.png")
    if args[:1] == ["--preview"]:
        return save_png(args[1] if len(args) > 1 else "preview.png", W, H, bytes(render(stamp(time.time()), 0.6)))
    # test 4 (tests 1-3 used draw_all / redraw_forever)
    prepare_test4()
    if args[:1] == ["--init"]:
        log(f"test 4 placeholders created in {IMG}")
        return
    stop = threading.Event()
    log("test 4: placeholders ready; watching the strip for READY (Ctrl+C stops)")
    try:
        read_forever(stop, answer_ready)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
