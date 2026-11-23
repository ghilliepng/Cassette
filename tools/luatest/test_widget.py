import sys
from lupa import lua51
lua = lua51.LuaRuntime(unpack_returned_tuples=True)
d = sys.argv[1]
lua.execute(open(sys.argv[2], encoding="utf-8").read())
JB = lua.table()
for name in lua.eval("ADDON_FILES").values():
    fn = lua.eval("loadstring")(open(f"{d}/{name}.lua", encoding="utf-8").read(), "@" + name)
    fn("Cassette", JB)
run = lua.execute
steps = [
  ("load + login", '_mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", true, false); _mock_timers()'),
  ("frames tick", 'for i = 1, 30 do _mock_update(0.05) end; _mock_timers()'),
  ("record arrives", 'Cassette:ApplyRecord({1, 159, 3, time() % 4096, 1 + 8 + 70 * 16, 0})'),
  ("art shows", 'Cassette:ShowArt(1, {"cv1", "ti1", "ar1"}, {{48, 48}, {400, 19}, {60, 17}})'),
  ("widget ticks + marquee", 'for i = 1, 200 do _mock_update(0.05) end'),
  ("buttons", 'local f = Cassette.widget; f.play.scripts.OnClick(); f.next.scripts.OnClick(); f.prev.scripts.OnClick(); f.volUp.scripts.OnClick(); f.volDown.scripts.OnClick(); f.vol.scripts.OnClick(); f.scripts.OnMouseUp(f, "RightButton"); f.scripts.OnDragStart(); f.scripts.OnDragStop(); _mock_timers()'),
  ("tooltips", 'local f = Cassette.widget; f.play.scripts.OnEnter(f.play); f.play.scripts.OnLeave(f.play)'),
  ("unanswered click: a quiet check first, the song stays", 'for i = 1, 180 do _mock_update(0.05) end; assert(Cassette.state.connected, "warned before checking")'),
  ("...and only if that goes unanswered too, the status", 'for i = 1, 180 do _mock_update(0.05) end; assert(Cassette.state.connected == false, "should notice no answer")'),
  ("the player's shuffle button turns shuffle on and off", 'local before = Cassette.state.shuffle; Cassette.widget.shuffle.scripts.OnClick(); assert(Cassette.state.shuffle ~= before); Cassette.widget.shuffle.scripts.OnClick(); assert(Cassette.state.shuffle == before)'),
  ("nothing playing", 'Cassette:ApplyRecord({0, 0, 0, time() % 4096, 8 + 50 * 16, 0}); assert(Cassette.widget.statusShown)'),
  ("spotify closed", 'Cassette:ApplyRecord({0, 0, 0, time() % 4096, 0, 0})'),
  ("slash commands", 'for _, c in ipairs({"", "", "lock", "unlock", "scale 1.3", "reset", "status", "help"}) do SlashCmdList.CASSETTE(c) end'),
  ("logout", '_mock_fire("PLAYER_LOGOUT"); assert(CassetteDB.cursors.mail >= 0)'),
  ("display change", '_mock_fire("UI_SCALE_CHANGED"); _mock_timers()'),
]
ok = True
for label, code in steps:
    try:
        run(code)
        print("OK  ", label)
    except Exception as e:
        ok = False
        print("FAIL", label, "->", str(e).splitlines()[0])
for line in lua.eval("printed").values():
    print("   chat:", line)
sys.exit(0 if ok else 1)
