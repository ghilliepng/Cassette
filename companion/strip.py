"""Reading the addon's messages off the screen.

The addon draws a one-pixel-high line in the top-left corner of the WoW window for a moment.
Each colour channel of a pixel is fully on or off (3 bits a pixel). Pixels 0-1 are markers
(cyan, yellow), then come the bytes: sequence number, length, checksum, data. The checksum is
sequence, length and data bytes each weighted by position, mod 255, so any single wrong bit is
caught. (In-game tests showed single pixels land exactly where the addon puts them.)
"""
import ctypes
import threading
import time
from ctypes import wintypes

SQ, MAXLEN = 1, 120            # pixel size of each 3-bit "square"; longest data in bytes
MAXSQ = 2 + (24 + 8 * MAXLEN + 2) // 3
WINDOW_CLASSES = ("waApplication Window", "GxWindowClass")  # WoW Forever 1.60, older clients

_u, _g = ctypes.windll.user32, ctypes.windll.gdi32
_u.FindWindowW.restype = wintypes.HWND
_u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.IsWindow.argtypes = [wintypes.HWND]
_u.IsIconic.argtypes = [wintypes.HWND]
_u.GetDC.restype = wintypes.HDC
_u.GetDC.argtypes = [wintypes.HWND]
_u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_g.CreateCompatibleDC.restype = wintypes.HDC
_g.CreateCompatibleDC.argtypes = [wintypes.HDC]
_g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_g.SelectObject.restype = wintypes.HGDIOBJ
_g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_g.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                      wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_g.DeleteDC.argtypes = [wintypes.HDC]


class _BMI(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                         ctypes.POINTER(_BMI), wintypes.UINT]


def wow_window():
    for cls in WINDOW_CLASSES:
        hwnd = _u.FindWindowW(cls, None)
        if hwnd:
            return hwnd
    return None


def grab(hwnd, w, h, x=0, y=0):
    """w x h pixels of the window's client area from (x, y) (top-left by default), as top-down
    BGRA bytes."""
    pt = wintypes.POINT(x, y)
    _u.ClientToScreen(hwnd, ctypes.byref(pt))
    sdc = _u.GetDC(None)
    mdc = _g.CreateCompatibleDC(sdc)
    bmp = _g.CreateCompatibleBitmap(sdc, w, h)
    old = _g.SelectObject(mdc, bmp)
    _g.BitBlt(mdc, 0, 0, w, h, sdc, pt.x, pt.y, 0x00CC0020)  # SRCCOPY
    bmi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    _g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    _g.SelectObject(mdc, old)
    _g.DeleteObject(bmp)
    _g.DeleteDC(mdc)
    _u.ReleaseDC(None, sdc)
    return bytes(buf)


def checksum(seq, data):
    return sum(v * (k + 1) for k, v in enumerate([seq, len(data), *data])) % 255


def _level(v):
    return 1 if v > 191 else 0 if v < 64 else None


def decode(buf, w):
    """(seq, data bytes) for a readable message, else None."""
    def square(i):
        o = i * 4  # pixel i of the top row
        return _level(buf[o + 2]), _level(buf[o + 1]), _level(buf[o])

    if square(0) != (0, 1, 1) or square(1) != (1, 1, 0):
        return None
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
        return None
    seq, length, check = byte(0), byte(1), byte(2)
    if length > MAXLEN or not need(24 + 8 * length):
        return None
    data = bytes(byte(3 + i) for i in range(length))
    if checksum(seq, data) != check:
        return None
    return seq, data


class StripReader(threading.Thread):
    """Calls on_message(data) for every new message the addon shows. Looks about 20 times a
    second."""

    def __init__(self, on_message, log):
        super().__init__(daemon=True, name="strip")
        self.on_message, self.log = on_message, log
        self.stop = threading.Event()
        self.wow_seen = False

    def run(self):
        w, h = MAXSQ * SQ, SQ
        hwnd, looked, last = None, 0.0, None
        while not self.stop.is_set():
            time.sleep(0.05)
            if not hwnd or time.time() - looked > 5:
                looked = time.time()
                found = wow_window()
                if bool(found) != self.wow_seen:
                    self.log("WoW window found" if found else "WoW window gone")
                self.wow_seen, hwnd = bool(found), found
            if not hwnd or not _u.IsWindow(hwnd) or _u.IsIconic(hwnd):
                continue
            try:
                got = decode(grab(hwnd, w, h), w)
            except Exception as e:  # a failed screen read must never stop the reader
                self.log(f"screen read failed: {e}")
                time.sleep(1)
                continue
            if got and got != last:
                last = got
                try:
                    self.on_message(got[1])
                except Exception as e:
                    self.log(f"message failed: {got[1]!r}: {e}")
