"""Writing TGA files the way WoW Forever reads them, and numbers as picture sizes.

What in-game tests showed (see test/imagetest.py):
- 32-bit uncompressed TGA with a bottom-left origin loads; 8-bit greyscale does not.
- Any size up to at least 4096 wide works, powers of two or not.
- A texture with one anchor and no size takes the file's pixel size, so a picture's width and
  height carry a number to the addon.
"""
import os
import struct
import time

_HEADER = "<BBBHHBHHHHBB"
MAX_VALUE = 4095  # a number file holds 0..4095 as a picture of up to 64 x 67


def _number_sizes():
    """The picture sizes numbers use, in order: value v is the v-th. WoW misreads a 6 x 1
    picture (in game, every page carrying the value 5 failed its checksum), so no size with
    width 6, height 6, or six pixels in all (the same file length) is used. Must match
    Live.lua's SIZES."""
    out = []
    for h in range(1, 68):
        for w in range(1, 65):
            if w != 6 and h != 6 and w * h != 6:
                out.append((w, h))
    return out[:MAX_VALUE + 1]


NUMBER_SIZES = _number_sizes()
NUMBER_VALUES = {size: v for v, size in enumerate(NUMBER_SIZES)}


def tga(w, h, bgra_bottom_up):
    """A complete TGA file from bottom-up BGRA rows."""
    return struct.pack(_HEADER, 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8) + bgra_bottom_up


def blank(w, h):
    """An invisible picture of exactly w x h pixels."""
    return tga(w, h, b"\x00\x00\x00\x00" * (w * h))


def number_size(v):
    """The picture size that carries v (see _number_sizes)."""
    return NUMBER_SIZES[max(0, min(MAX_VALUE, int(v)))]


def number_value(w, h):
    """The number a picture size carries, or -1 for a size no number uses."""
    return NUMBER_VALUES.get((w, h), -1)


def number(v):
    return blank(*number_size(v))


def from_image(im):
    """A TGA file from a Pillow image."""
    from PIL import Image
    im = im.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return tga(im.width, im.height, im.tobytes("raw", "BGRA"))


def write(path, data):
    """Replace path with data in one step, so WoW never reads half a file."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # WoW (or a virus scanner) has it open for a moment
            time.sleep(0.01)
        except OSError:  # this folder can't take renames (redirected folders): write directly
            break
    with open(path, "wb") as f:  # last resort: overwrite in place
        f.write(data)
    try:
        os.remove(tmp)
    except OSError:
        pass
