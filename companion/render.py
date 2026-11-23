"""Drawing the pictures the widget shows: cover art and the title and artist text strips.

Sizes are in screen pixels. The addon reports how many screen pixels one of its UI units covers
(ppu), so the pictures are drawn at exactly the size they appear and the text stays sharp.
Widget layout (UI units, must match Widget.lua): cover 40 x 40, title line 16 high,
artist line 14 high.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

COVER_UNITS, TITLE_UNITS, ARTIST_UNITS = 40, 16, 14
TITLE_FONT_UNITS, ARTIST_FONT_UNITS = 13.5, 11.5
TITLE_RGB, ARTIST_RGB = (255, 255, 255), (165, 165, 172)
MAX_WIDTH = 4096

# The addon's themes (UI.lua): text colours, and whether text has a drop shadow as WoW's does.
THEMES = {
    "ellesmere": dict(title=(255, 255, 255), artist=(165, 165, 172), row=(240, 240, 244), sub=(165, 165, 172),
                      note=(140, 140, 150), shadow=False),
    "classic": dict(title=(255, 255, 255), artist=(215, 215, 215), row=(255, 255, 255), sub=(205, 205, 205),
                    note=(160, 160, 160), shadow=True),
    "modern": dict(title=(255, 255, 255), artist=(190, 184, 172), row=(250, 246, 238), sub=(182, 176, 164),
                   note=(150, 146, 138), shadow=True),
}


def theme(key):
    return THEMES.get(key) or THEMES["ellesmere"]

_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
# Latin text in the user's UI font; scripts it lacks fall back to Windows fonts
_FALLBACKS = [
    (lambda c: 0x3040 <= c <= 0x30FF or 0x4E00 <= c <= 0x9FFF or 0xFF00 <= c <= 0xFFEF, ["YuGothM.ttc", "msyh.ttc"]),
    (lambda c: 0xAC00 <= c <= 0xD7AF or 0x1100 <= c <= 0x11FF, ["malgun.ttf"]),
    (lambda c: c > 0x024F, ["segoeui.ttf", "arial.ttf"]),
]
_cache = {}


def _font(path, px):
    key = (path, px)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(path, px)
    return _cache[key]


def pick_font(text, ui_font, px):
    """The UI font, unless the text uses a script it can't show."""
    for needs, names in _FALLBACKS:
        if any(needs(ord(ch)) for ch in text):
            for name in names:
                path = os.path.join(_WIN_FONTS, name)
                if os.path.exists(path):
                    return _font(path, px)
    if ui_font and os.path.exists(ui_font):
        return _font(ui_font, px)
    return _font(os.path.join(_WIN_FONTS, "segoeui.ttf"), px)


def _shadowed(im, ppu):
    """A drop shadow under what's drawn (one unit down and right, as WoW's text has)."""
    d = max(1, round(ppu))
    alpha = im.getchannel("A").point(lambda a: int(a * 0.85))
    black = Image.new("RGBA", im.size, (0, 0, 0, 255))
    black.putalpha(alpha)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.alpha_composite(black, (d, d))
    out.alpha_composite(im)
    return out


def text_strip(text, line_units, font_units, rgb, ppu, ui_font, shadow=False):
    """One line of text on a transparent background: as wide as the text, as high as the line."""
    h = max(4, round(line_units * ppu))
    font = pick_font(text, ui_font, max(6, round(font_units * ppu)))
    text = text or " "
    width = min(MAX_WIDTH, max(1, int(font.getlength(text)) + 3 + (round(ppu) if shadow else 0)))
    mask = Image.new("L", (width, h), 0)
    ImageDraw.Draw(mask).text((1, h / 2), text, font=font, fill=255, anchor="lm")
    im = Image.new("RGBA", (width, h), tuple(rgb) + (0,))
    im.putalpha(mask)  # colour everywhere, coverage in the alpha: clean edges when WoW blends it
    return _shadowed(im, ppu) if shadow else im


def cover(image_bytes, ppu, units=COVER_UNITS):
    px = max(8, round(units * ppu))
    if image_bytes:
        try:
            im = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            side = min(im.size)  # centre-crop to a square
            left, top = (im.width - side) // 2, (im.height - side) // 2
            return im.crop((left, top, left + side, top + side)).resize((px, px), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return no_cover(px)


def no_cover(px):
    """Dark square with a simple note, for songs without art."""
    s = px * 4
    im = Image.new("RGBA", (s, s), (38, 38, 44, 255))
    d = ImageDraw.Draw(im)
    c = (120, 120, 130, 255)
    d.ellipse((s * 0.28, s * 0.58, s * 0.48, s * 0.74), fill=c)
    d.rectangle((s * 0.44, s * 0.26, s * 0.48, s * 0.66), fill=c)
    d.polygon([(s * 0.44, s * 0.26), (s * 0.70, s * 0.20), (s * 0.70, s * 0.30), (s * 0.48, s * 0.36)], fill=c)
    return im.resize((px, px), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------------------------
# The browser: a page of up to 8 rows, drawn as one picture. Layout in UI units; must match
# Browser.lua (PAGE_W, ROW_H). The addon lays clickable rows (and, for playlists, a play button
# in the last PLAY_W units) over it.
# ---------------------------------------------------------------------------------------------

PAGE_W, ROW_H, THUMB = 352, 34, 28
PLAY_W = 32  # room on playlist rows for the addon's play button
ROW_TITLE_FONT, ROW_SUB_FONT = 12.5, 10.5
GREEN_RGB, NOTE_RGB = (30, 215, 96), (140, 140, 150)


def _fit(text, font, width):
    """Text shortened with an ellipsis to fit width pixels."""
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + "...") > width:
        text = text[:-1]
    return text.rstrip() + "..."


def _thumb_image(image_bytes, px):
    if image_bytes:
        try:
            im = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            return im.crop((left, top, left + side, top + side)).resize((px, px), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return no_cover(px)


def page(rows, ppu, ui_font, play_buttons=False, accent=GREEN_RGB, look="ellesmere"):
    """rows: dicts with title, subtitle, right (text at the right edge), image (bytes or None),
    style ("normal", "action": a Play row, "note": a grey explanation), playing (the song or
    playlist playing now: its title in the accent colour, as Spotify does). look: the theme."""
    T = theme(look)
    s = ppu
    w, row_h = round(PAGE_W * s), round(ROW_H * s)
    im = Image.new("RGBA", (w, max(1, row_h * len(rows))), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    thumb = round(THUMB * s)
    for i, r in enumerate(rows):
        top = i * row_h
        style = r.get("style", "normal")
        # each row in the UI font, unless its own text needs another script
        tf = pick_font(r.get("title", ""), ui_font, max(6, round(ROW_TITLE_FONT * s)))
        sf = pick_font(r.get("subtitle", "") + r.get("right", ""), ui_font, max(6, round(ROW_SUB_FONT * s)))
        if style == "note":
            sf = pick_font(r.get("title", ""), ui_font, max(6, round(ROW_SUB_FONT * s)))
        text_x = round(40 * s)
        right_edge = w - round((PLAY_W + 6 if play_buttons else 8) * s)
        if style == "note":
            words, line, lines = r.get("title", "").split(), "", []
            for word in words:
                if sf.getlength((line + " " + word).strip()) > w - round(16 * s):
                    lines.append(line)
                    line = word
                else:
                    line = (line + " " + word).strip()
            lines.append(line)
            for j, text in enumerate(lines[:2]):
                d.text((round(8 * s), top + row_h * (0.33 + 0.36 * j)), text, font=sf, fill=T["note"] + (255,), anchor="lm")
            continue
        if style == "action":
            cx, cy, rad = round(4 * s) + thumb / 2, top + row_h / 2, thumb / 2
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=tuple(accent) + (255,))
            t = rad * 0.42
            d.polygon([(cx - t * 0.7, cy - t), (cx - t * 0.7, cy + t), (cx + t, cy)], fill=(12, 12, 14, 255))
        else:
            im.alpha_composite(_thumb_image(r.get("image"), thumb), (round(4 * s), top + (row_h - thumb) // 2))
        right = r.get("right", "")
        right_w = sf.getlength(right) + round(8 * s) if right else 0
        if right:
            d.text((right_edge, top + row_h / 2), right, font=sf, fill=T["note"] + (255,), anchor="rm")
        avail = right_edge - text_x - right_w
        title_rgb = tuple(accent) if (style == "action" or r.get("playing")) else T["row"]
        d.text((text_x, top + row_h * 0.36), _fit(r.get("title", ""), tf, avail), font=tf, fill=title_rgb + (255,), anchor="lm")
        if r.get("subtitle"):
            d.text((text_x, top + row_h * 0.72), _fit(r["subtitle"], sf, avail), font=sf, fill=T["sub"] + (255,), anchor="lm")
    return _shadowed(im, ppu) if T["shadow"] else im


def message_page(text, ppu, ui_font, look="ellesmere"):
    """A page with just a message (errors and the like), as grey wrapped text."""
    return page([{"title": text, "style": "note"}], ppu, ui_font, look=look)
