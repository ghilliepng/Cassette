"""Cassette's logo: a cassette tape, drawn at high resolution and scaled down for each use.

    python tools\\make_logo.py preview <out.png>     a sheet of the designs and colours to choose from
    python tools\\make_logo.py build <design> <colour>  writes the chosen logo everywhere it's used

Designs: "tape" (a classic cassette), "play" (a cassette with a play symbol in its window),
"reels" (just the two reels and the tape between them, for very small sizes).
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024  # drawing size; scaled down with Lanczos for clean edges

COLOURS = {
    "green": dict(accent=(30, 215, 96), body=(64, 66, 75), edge=(108, 111, 122), window=(20, 20, 24), reel=(236, 236, 240)),
    "amber": dict(accent=(245, 166, 35), body=(70, 63, 58), edge=(118, 108, 98), window=(22, 19, 17), reel=(244, 238, 228)),
    "coral": dict(accent=(255, 94, 91), body=(66, 62, 70), edge=(114, 108, 120), window=(21, 19, 22), reel=(244, 240, 240)),
}


def _reel(d, cx, cy, r, colour, hub):
    """A tape reel: a ring with six teeth inside, like a real cassette's spools."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)
    d.ellipse((cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62), fill=hub)
    import math
    for k in range(6):
        a = k * math.pi / 3
        x, y = cx + math.cos(a) * r * 0.5, cy + math.sin(a) * r * 0.5
        w = r * 0.16
        d.ellipse((x - w, y - w, x + w, y + w), fill=colour)


def cassette(design, colour, size=512):
    c = COLOURS[colour]
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if design == "reels":
        # two reels on a dark rounded tile, the tape running between them
        d.rounded_rectangle((40, 40, S - 40, S - 40), radius=200, fill=c["body"], outline=c["edge"], width=16)
        r = 170
        y = S * 0.5
        d.rectangle((S * 0.3, y + r - 34, S * 0.7, y + r), fill=c["accent"])
        _reel(d, S * 0.3, y, r, c["accent"], c["body"])
        _reel(d, S * 0.7, y, r, c["accent"], c["body"])
    else:
        # the body: a rounded rectangle, the label band across the top, the window with the reels,
        # and the trapezoid at the bottom where the tape shows
        top, bottom = S * 0.19, S * 0.81
        d.rounded_rectangle((60, top, S - 60, bottom), radius=70, fill=c["body"], outline=c["edge"], width=16)
        d.rounded_rectangle((120, top + 50, S - 120, top + 150), radius=24, fill=c["accent"])
        wy0, wy1 = top + 190, top + 390
        d.rounded_rectangle((200, wy0, S - 200, wy1), radius=100, fill=c["window"])
        cy, r = (wy0 + wy1) / 2, 78
        if design == "play":
            t = 70
            cx = S / 2
            d.polygon([(cx - t * 0.8, cy - t), (cx - t * 0.8, cy + t), (cx + t, cy)], fill=c["accent"])
            _reel(d, 300, cy, r * 0.8, c["reel"], c["window"])
            _reel(d, S - 300, cy, r * 0.8, c["reel"], c["window"])
        else:
            _reel(d, 330, cy, r, c["reel"], c["window"])
            _reel(d, S - 330, cy, r, c["reel"], c["window"])
            d.rectangle((330, cy + r - 8, S - 330, cy + r + 4), fill=c["reel"])
        d.polygon([(260, bottom), (300, bottom - 90), (S - 300, bottom - 90), (S - 260, bottom)], fill=c["window"])
        for x in (360, S - 360):
            d.ellipse((x - 22, bottom - 60, x + 22, bottom - 16), fill=c["body"])
    return im.resize((size, size), Image.Resampling.LANCZOS)


def preview(out):
    designs, colours = ["tape", "play", "reels"], list(COLOURS)
    cell, small = 300, (64, 32, 16)
    sheet = Image.new("RGBA", (len(designs) * cell + 40, len(colours) * (cell + 70) + 60), (245, 245, 247, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for i, design in enumerate(designs):
        d.text((20 + i * cell + cell / 2, 22), design, fill=(40, 40, 46), font=font, anchor="mm")
        for j, colour in enumerate(colours):
            x, y = 20 + i * cell, 50 + j * (cell + 70)
            big = cassette(design, colour, 220)
            # on a dark tile (how it looks in WoW and Windows' dark mode) and the small sizes
            tile = Image.new("RGBA", (cell - 20, cell + 50), (28, 28, 32, 255))
            tile.alpha_composite(big, ((cell - 20 - 220) // 2, 8))
            sx = 20
            for s in small:
                tile.alpha_composite(cassette(design, colour, s), (sx, 240 + (64 - s) // 2))
                sx += s + 18
            ImageDraw.Draw(tile).text((cell - 30, 300), colour, fill=(200, 200, 205), font=font, anchor="rm")
            sheet.alpha_composite(tile, (x, y))
    sheet.save(out)
    return out


def build(design, colour):
    """Write the chosen logo everywhere it's used."""
    sys.path.insert(0, os.path.join(ROOT, "companion"))
    import tga
    made = []

    def save(im, *parts):
        path = os.path.join(ROOT, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if path.endswith(".tga"):
            tga.write(path, tga.from_image(im))
        else:
            im.save(path)
        made.append(path)

    save(cassette(design, colour, 64), "addon", "Cassette", "Media", "icon.tga")  # WoW's addon list
    save(cassette(design, colour, 256), "companion", "logo.png")                   # tray and windows
    save(cassette(design, colour, 256), "docs", "logo.png")                        # the GitHub page
    save(cassette(design, colour, 400), "docs", "logo-400.png")                    # CurseForge and Wago
    return made


def icon_file(path, design="play", colour="green"):
    """The app's .ico, each size drawn from the full-size logo."""
    big = cassette(design, colour, 256)
    big.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


if __name__ == "__main__":
    if sys.argv[1] == "preview":
        print(preview(sys.argv[2]))
    elif sys.argv[1] == "build":
        for p in build(sys.argv[2], sys.argv[3]):
            print(p)
