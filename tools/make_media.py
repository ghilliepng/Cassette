"""Draws the addon's icons into addon/Cassette/Media (run with the companion's Python).

White glyphs on transparent backgrounds, drawn 4x larger and scaled down for smooth edges.
sentinel.tga is 65 x 1: a size no number file can have (they are at most 64 wide), which the
addon's readers show between reads so they can tell a fresh size from a leftover one.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "companion"))

from PIL import Image, ImageDraw  # noqa: E402

import tga  # noqa: E402

OUT = os.path.join(ROOT, "addon", "Cassette", "Media")
S = 64 * 4
WHITE = (255, 255, 255, 255)


def canvas():
    im = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    return im, ImageDraw.Draw(im)


def save(name, im):
    im = im.resize((64, 64), Image.Resampling.LANCZOS)
    tga.write(os.path.join(OUT, name + ".tga"), tga.from_image(im))


def play():
    im, d = canvas()
    d.polygon([(S * 0.30, S * 0.20), (S * 0.30, S * 0.80), (S * 0.80, S * 0.50)], fill=WHITE)
    return im


def pause():
    im, d = canvas()
    d.rounded_rectangle((S * 0.26, S * 0.20, S * 0.42, S * 0.80), S * 0.03, fill=WHITE)
    d.rounded_rectangle((S * 0.58, S * 0.20, S * 0.74, S * 0.80), S * 0.03, fill=WHITE)
    return im


def skip(forward):
    im, d = canvas()
    d.polygon([(S * 0.24, S * 0.22), (S * 0.24, S * 0.78), (S * 0.64, S * 0.50)], fill=WHITE)
    d.rounded_rectangle((S * 0.66, S * 0.22, S * 0.78, S * 0.78), S * 0.02, fill=WHITE)
    return im if forward else im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def minus():
    im, d = canvas()
    d.rounded_rectangle((S * 0.22, S * 0.44, S * 0.78, S * 0.56), S * 0.03, fill=WHITE)
    return im


def plus():
    im = minus()
    ImageDraw.Draw(im).rounded_rectangle((S * 0.44, S * 0.22, S * 0.56, S * 0.78), S * 0.03, fill=WHITE)
    return im


def listing():
    im, d = canvas()
    for y in (0.27, 0.47, 0.67):
        d.rounded_rectangle((S * 0.20, S * y, S * 0.80, S * (y + 0.09)), S * 0.03, fill=WHITE)
    return im


def close():
    im, d = canvas()
    w = S * 0.09
    d.line((S * 0.25, S * 0.25, S * 0.75, S * 0.75), fill=WHITE, width=round(w))
    d.line((S * 0.75, S * 0.25, S * 0.25, S * 0.75), fill=WHITE, width=round(w))
    return im


def chevron(right):
    im, d = canvas()
    pts = [(S * 0.38, S * 0.22), (S * 0.66, S * 0.50), (S * 0.38, S * 0.78)]
    d.line(pts, fill=WHITE, width=round(S * 0.10), joint="curve")
    return im if right else im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def shuffle():
    """Two crossing arrows."""
    im, d = canvas()
    w = round(S * 0.075)
    d.line([(S * 0.14, S * 0.30), (S * 0.34, S * 0.30), (S * 0.62, S * 0.70), (S * 0.80, S * 0.70)], fill=WHITE, width=w, joint="curve")
    d.line([(S * 0.14, S * 0.70), (S * 0.34, S * 0.70), (S * 0.62, S * 0.30), (S * 0.80, S * 0.30)], fill=WHITE, width=w, joint="curve")
    for y in (0.30, 0.70):
        d.polygon([(S * 0.90, S * y), (S * 0.74, S * (y - 0.11)), (S * 0.74, S * (y + 0.11))], fill=WHITE)
    return im


def check():
    im, d = canvas()
    d.line([(S * 0.18, S * 0.52), (S * 0.40, S * 0.74), (S * 0.82, S * 0.28)], fill=WHITE, width=round(S * 0.11), joint="curve")
    return im


def dot():
    im, d = canvas()
    d.ellipse((S * 0.38, S * 0.38, S * 0.62, S * 0.62), fill=WHITE)
    return im


def icon():
    im, d = canvas()
    d.rounded_rectangle((S * 0.03, S * 0.03, S * 0.97, S * 0.97), S * 0.22, fill=(30, 215, 96, 255))
    dark = (20, 20, 24, 255)
    d.ellipse((S * 0.22, S * 0.60, S * 0.47, S * 0.81), fill=dark)
    d.rectangle((S * 0.41, S * 0.22, S * 0.47, S * 0.72), fill=dark)
    d.polygon([(S * 0.41, S * 0.22), (S * 0.75, S * 0.14), (S * 0.75, S * 0.28), (S * 0.47, S * 0.36)], fill=dark)
    return im


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, im in [("play", play()), ("pause", pause()), ("next", skip(True)), ("prev", skip(False)),
                     ("minus", minus()), ("plus", plus()), ("icon", icon()), ("list", listing()),
                     ("close", close()), ("left", chevron(False)), ("right", chevron(True)),
                     ("shuffle", shuffle()), ("check", check()), ("dot", dot())]:
        save(name, im)
    tga.write(os.path.join(OUT, "sentinel.tga"), tga.blank(65, 1))
    print("media written to", OUT)


if __name__ == "__main__":
    main()
