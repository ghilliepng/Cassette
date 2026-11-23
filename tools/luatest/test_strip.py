"""End to end: the addon's real strip code (Strip.lua, in the WoW stand-in) draws messages; the
companion's real decoder (strip.decode) reads them back from those pixels.
Usage: python test_strip.py <addon dir> <wowmock.lua>"""
import os
import struct
import sys

from lupa import lua51

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "companion"))
import strip as strip_mod  # noqa: E402

lua = lua51.LuaRuntime(unpack_returned_tuples=True)
d = sys.argv[1]
lua.execute(open(sys.argv[2], encoding="utf-8").read())
JB = lua.table()
for name in lua.eval("ADDON_FILES").values():
    lua.eval("loadstring")(open(f"{d}/{name}.lua", encoding="utf-8").read(), "@" + name)("Cassette", JB)
lua.execute('_mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", true, false); _mock_update(2)')


def screen():
    """The strip's pixels as the screen grab would see them (top row, BGRA)."""
    strip = lua.eval("CassetteStrip")
    w = strip_mod.MAXSQ
    buf = bytearray(w * 4)
    if not strip or not strip.shown:
        return bytes(buf), w
    for i, t in enumerate(strip.children.values()):
        if t.shown is False or t.color is None:
            continue
        r, g, b = (round(t.color[k] * 255) for k in (1, 2, 3))
        buf[i * 4:i * 4 + 4] = bytes((b, g, r, 255))
    return bytes(buf), w


failed = False


def check(label, ok):
    global failed
    print(("OK   " if ok else "FAIL ") + label)
    failed |= not ok


for cmd, arg in [("N", None), ("PL", "12 3"), ("FD", "linkin park"), ("FD", "千本桜 ミク"), ("D", "30"), ("H", None)]:
    lua.execute(f'Cassette:Send({cmd!r}, {repr(arg) if arg else "nil"})')
    buf, w = screen()
    got = strip_mod.decode(buf, w)
    if not got:
        check(f"{cmd} {arg or ''}: read back", False)
        continue
    data = got[1]
    t, nonce, mail, rec, art, view, ppu = struct.unpack(">7H", data[:14])
    text = data[14:].decode("utf-8")
    want = cmd + (" " + arg if arg else "")
    width = sum(1 for t in lua.eval("CassetteStrip").children.values() if t.shown is not False)
    check(f"{ascii(want)}: read back exactly ({width} pixels wide), session {nonce}, mail {mail}, ppu {ppu}",
          text == want and nonce == lua.eval("Cassette.nonce") and view >= 1)
    lua.execute("_mock_update(0.3)")  # let it go before the next

lua.execute("_mock_update(1)")
check("the line is gone once there's nothing to say", not lua.eval("CassetteStrip").shown)
sys.exit(1 if failed else 0)
