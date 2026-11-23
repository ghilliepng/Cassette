"""The music dip that follows Spoken, against a fake Spoken (tools/luatest/wowmock.lua).
The dip travels as tiny strip messages: "D 30" when a line starts, "D 100" after, and a
renewal every 25 s during long readings.
Usage: python test_duck.py <addon dir> <wowmock.lua>"""
import sys

from lupa import lua51

lua = lua51.LuaRuntime(unpack_returned_tuples=True)
d = sys.argv[1]
lua.execute(open(sys.argv[2], encoding="utf-8").read())
lua.execute('''
SpokenFake = { clip = nil, paused = false, muted = false, cbs = {} }
Spoken = {
  GetNowPlaying = function(self) return SpokenFake.clip end,
  IsPaused = function(self) return SpokenFake.paused end,
  IsMuted = function(self) return SpokenFake.muted end,
  RegisterCallback = function(self, ev, fn) SpokenFake.cbs[#SpokenFake.cbs + 1] = fn end,
}
function fire() for _, fn in ipairs(SpokenFake.cbs) do fn() end end
QUEST = { source = { key = "quests" } }
CHATTER = { source = { key = "chatter" } }
SILENT = { source = { key = "gossip" }, silent = true }
function say(clip) SpokenFake.clip = clip; fire() end
function wait(s) _mock_update(s) end
function dipped() return Cassette.ducked end
function lastD() return sent[#sent] end
function count(v) local n = 0 for _, x in ipairs(sent) do if x == v then n = n + 1 end end return n end
''')
JB = lua.table()
for name in lua.eval("ADDON_FILES").values():
    lua.eval("loadstring")(open(f"{d}/{name}.lua", encoding="utf-8").read(), "@" + name)("Cassette", JB)
lua.execute('''
_mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", true, false)
wait(1)
sent = {}
local send = Cassette.Send
Cassette.Send = function(self, cmd, arg) if cmd == "D" then sent[#sent + 1] = arg end return send(self, cmd, arg) end
''')
steps = [
    ("hooked Spoken's callbacks", 'assert(#SpokenFake.cbs == 4, #SpokenFake.cbs)'),
    ("quest line starts: dips to 30", 'say(QUEST); assert(dipped() and lastD() == "30")'),
    ("reads for 60 s (window closed, ran off): stays down, renewed every 25 s",
     'wait(60); assert(dipped()); assert(count("30") == 3, count("30"))'),
    ("line ends: still down 1 s later", 'say(nil); wait(1); assert(dipped(), "too early")'),
    ("and back up within 3 s", 'wait(2); assert(not dipped() and lastD() == "100")'),
    ("no more dip messages afterwards", 'local n = #sent; wait(60); assert(#sent == n, #sent - n)'),
    ("back up even with no callback from Spoken", 'say(QUEST); wait(5); SpokenFake.clip = nil; wait(3.1); assert(not dipped())'),
    ("gap of 1 s between lines keeps it down",
     'say(QUEST); wait(5); say(nil); wait(1); say(QUEST); wait(10); assert(dipped()); say(nil); wait(3)'),
    ("pausing Spoken brings it back",
     'say(QUEST); wait(2); SpokenFake.paused = true; fire(); wait(3); assert(not dipped()); SpokenFake.paused = false; say(nil); wait(3)'),
    ("ambient chatter never dips", 'local n = #sent; say(CHATTER); wait(120); assert(not dipped() and #sent == n); say(nil)'),
    ("silent line never dips", 'say(SILENT); wait(5); assert(not dipped()); say(nil)'),
    ("quest line then chatter: back up", 'say(QUEST); wait(5); say(CHATTER); wait(3); assert(not dipped()); say(nil); wait(1)'),
    ("/tape duck 20 while reading", 'say(QUEST); SlashCmdList.CASSETTE("duck 20"); assert(dipped() and lastD() == "20", lastD()); say(nil); wait(3)'),
    ("/tape duck off ends it at once",
     'say(QUEST); SlashCmdList.CASSETTE("duck off"); assert(not dipped()); SlashCmdList.CASSETTE("duck on"); say(nil); wait(3)'),
    ("/tape duck chatter on",
     'SlashCmdList.CASSETTE("duck chatter on"); say(CHATTER); assert(dipped()); SlashCmdList.CASSETTE("duck chatter off"); wait(3); assert(not dipped()); say(nil)'),
    ("10 minutes without a break: back to full",
     'say(QUEST); wait(601); assert(not dipped(), "should give up"); wait(30); assert(not dipped(), "no re-dip while still reading")'),
    ("after real quiet, dips again", 'say(nil); wait(3); say(QUEST); assert(dipped()); say(nil); wait(3); assert(not dipped())'),
    ("status", 'SlashCmdList.CASSETTE("status")'),
]
ok = True
for label, code in steps:
    try:
        lua.execute(code)
        print("OK  ", label)
    except Exception as e:
        ok = False
        print("FAIL", label, "->", str(e).splitlines()[0])
print("   chat:", list(lua.eval("printed").values())[-1])
sys.exit(0 if ok else 1)
