"""The addon's reading of the companion's files: slow loads, keeping pace without check-ins, and
the browser. Usage: python test_live.py <addon dir> <wowmock.lua>"""
import os
import sys

from lupa import lua51

lua = lua51.LuaRuntime(unpack_returned_tuples=True)
d = sys.argv[1]
lua.execute(open(sys.argv[2], encoding="utf-8").read())
JB = lua.table()
for name in lua.eval("ADDON_FILES").values():
    lua.eval("loadstring")(open(f"{d}/{name}.lua", encoding="utf-8").read(), "@" + name)("Cassette", JB)
lua.execute('''
function num(v) local s = Cassette.NumberSize(v) return { s[1], s[2] } end
-- a record as the companion writes it (checksum includes the session number)
function record(r, art, dur, pos, flags, view, nonce)
  local when = time() % 4096
  local f = { art, dur, pos, when, flags, view or 0 }
  local sum = 0
  for i, v in ipairs(f) do FILES["r" .. r .. "_" .. (i - 1)] = num(v); sum = sum + v end
  FILES["r" .. r .. "_6"] = num((sum + (nonce or Cassette.nonce)) % 4096)
end
function view(n, kind, page, pages, rows)
  local f = { kind, page, pages, rows }
  for i, v in ipairs(f) do FILES["v" .. n .. "_" .. (i - 1)] = num(v) end
  FILES["v" .. n .. "_4"] = num((kind + page + pages + rows + Cassette.nonce) % 4096)
  FILES["pg" .. n] = { 422, math.max(1, 41 * rows) }  -- the pool's blank is 1 x 1
end
function mail(from, to, r) for k = from, to do FILES["m" .. k] = num(r) end end
function wait(s) _mock_update(s) end
function logHas(text) local n = 0 for _, l in ipairs(Cassette.debugLog) do if l:find(text, 1, true) then n = n + 1 end end return n end
PLAYING = 1 + 8 + 70 * 16
ACCOUNT = 2048
mail(0, 5000, 0)
_mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", true, false)
sent = {}
local send = Cassette.Send
Cassette.Send = function(self, cmd, arg) sent[#sent + 1] = cmd .. (arg and (" " .. arg) or "") return send(self, cmd, arg) end
function count(prefix) local n = 0 for _, s in ipairs(sent) do if s:sub(1, #prefix) == prefix then n = n + 1 end end return n end
function last() return sent[#sent] end
''')
# the addon and the companion use the same picture sizes for numbers
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "companion"))
import tga  # noqa: E402
size_of = lua.eval("function(v) local s = Cassette.NumberSize(v) return s[1], s[2] end")
assert all(tuple(size_of(v)) == tga.number_size(v) for v in range(4096)), "number sizes differ"
print("OK   the addon and the companion agree on all 4096 number sizes")

steps = [
    ("nothing from the companion yet: it keeps asking", 'wait(10); assert(not Cassette.state.connected); assert(count("H") >= 2, count("H"))'),
    ("first song arrives", 'record(1, 1, 200, 10, PLAYING); mail(Cassette.mailCursor, 5000, 1); wait(5); '
                           'assert(Cassette.state.connected and Cassette.state.art == 1 and Cassette.state.playing)'),
    ("art shows", 'assert(Cassette.widget.shownArt == 1)'),
    ("ten quiet minutes with songs changing: no check-ins at all",
     'local before = count("H"); for i = 2, 4 do wait(150); record(i, i, 200, 0, PLAYING); mail(Cassette.mailCursor, 5000, i) end; '
     'wait(150); assert(count("H") == before, "sent " .. (count("H") - before) .. " check-ins"); assert(Cassette.state.art == 4)'),
    ("and it keeps the pace the companion counts on",
     'local pace = Cassette.anchorMail + math.floor((time() - Cassette.anchorTime) / 4); '
     'assert(Cassette.mailCursor >= pace, Cassette.mailCursor .. " < " .. pace)'),
    ("skip, and the answer takes 10 s to load: retried, not lost",
     'Cassette:Command("N"); wait(0.5); SLOW["r5_"] = 10; record(5, 5, 180, 0, PLAYING); '
     'mail(Cassette.mailCursor, 5000, 5); wait(16); '
     'assert(Cassette.state.art == 5, "record 5 never applied: art " .. Cassette.state.art); '
     'assert(Cassette.state.connected, "still says not answering")'),
    ("it logged the slow load and the retry", 'assert(logHas("record 5 didn\'t load in time") >= 1); assert(logHas("record 5 applied") == 1)'),
    ("a leftover from another session is ignored, and only checked once",
     'record(9, 9, 100, 0, PLAYING, 0, Cassette.nonce + 1); mail(Cassette.mailCursor, 5000, 9); wait(30); '
     'assert(Cassette.state.art == 5); assert(logHas("record 9 is from another session") == 1)'),
    ("a missed answer: a quiet check-in, still showing the song",
     'local before = count("H"); Cassette:Command("N"); wait(10); assert(Cassette.state.connected); '
     'assert(count("H") == before + 1, count("H") - before)'),
    ("no answer to that either: now it says so", 'wait(9); assert(not Cassette.state.connected)'),
    ("back in touch", 'record(10, 6, 150, 0, PLAYING); mail(Cassette.mailCursor, 5000, 10); wait(6); assert(Cassette.state.connected)'),
    # -- the browser --
    ("the = button opens the browser and asks for playlists",
     'Cassette.widget.list.scripts.OnClick(); assert(Cassette.browser.shown); assert(last() == "BR P", last())'),
    ("not connected to Spotify: the setup page and button",
     'view(1, 5, 0, 1, 0); record(11, 6, 150, 0, PLAYING, 1); mail(Cassette.mailCursor, 5000, 11); wait(4); '
     'assert(Cassette.view and Cassette.view.kind == 5, "no setup view"); assert(Cassette.browser.setup.shown)'),
    ("Set up on PC asks the companion to open its window",
     'Cassette.browser.setup.scripts.OnClick(); assert(last() == "SETUP", last())'),
    ("playlists arrive: 8 rows with play buttons, and pages 2 and 3 are asked for as they near",
     'view(2, 1, 0, 3, 8); record(12, 6, 150, 0, PLAYING + ACCOUNT, 2); mail(Cassette.mailCursor, 5000, 12); wait(4); '
     'assert(Cassette.list and Cassette.list.kind == 1 and Cassette.list.pages == 3); '
     'local sl = Cassette.browser.slots[0]; assert(sl.rows[8].shown and sl.rows[3].play.shown); '
     'assert(Cassette.state.account); assert(count("PG 2 1") == 1, "page 2 not asked for")'),
    ("clicking one of your playlists opens it", 'Cassette.browser.slots[0].rows[3].scripts.OnClick(); assert(last() == "OP 2 2 1", last())'),
    ("its play button plays it (shuffle off: in order)", 'Cassette.state.shuffle = false; Cassette.browser.slots[0].rows[2].play.scripts.OnClick(); assert(last() == "PL 2 1 1", last())'),
    ("the shuffle toggle: on, and play now plays shuffled",
     'Cassette.browser.shuffle.scripts.OnClick(); assert(last() == "S" and Cassette.state.shuffle); '
     'Cassette.browser.slots[0].rows[2].play.scripts.OnClick(); assert(last() == "PS 2 1 1", last()); '
     'Cassette.browser.shuffle.scripts.OnClick(); assert(not Cassette.state.shuffle)'),
    ("page 2 arrives below page 1, its rows click as rows 8 on",
     'Cassette.expectNew = false; view(3, 1, 1, 3, 8); record(13, 6, 150, 0, PLAYING + ACCOUNT, 3); mail(Cassette.mailCursor, 5000, 13); wait(4); '
     'assert(Cassette.list.pics[1] and Cassette.list.pics[0], "page 2 didn\'t join the list"); '
     'Cassette.browser.slots[1].rows[1].scripts.OnClick(); assert(last() == "OP 3 8 1", last())'),
    ("scrolling down glides, and asks for page 3 as it nears",
     'Cassette.browser.scripts.OnMouseWheel(Cassette.browser, -1); Cassette.browser.scripts.OnMouseWheel(Cassette.browser, -1); wait(1); '
     'assert(Cassette.list.y > 100, Cassette.list.y); assert(count("PG 3 2") + count("PG 2 2") >= 1, "page 3 not asked for")'),
    ("a page asked for is asked once, not every frame", 'local n = count("PG"); wait(1); assert(count("PG") == n, count("PG") - n)'),
    ("a playlist's songs: rows play, Back shows, no play buttons (the Play row plays)",
     'Cassette.browser.slots[0].rows[3].scripts.OnClick(); '
     'view(4, 2, 0, 1, 5); record(14, 6, 150, 0, PLAYING + ACCOUNT, 4); mail(Cassette.mailCursor, 5000, 14); wait(4); '
     'assert(Cassette.list.kind == 2 and Cassette.browser.back.shown); assert(not Cassette.browser.slots[0].rows[6].shown); '
     'assert(not Cassette.browser.slots[0].rows[1].play.shown and not Cassette.browser.slots[0].rows[2].play.shown); '
     'Cassette.browser.slots[0].rows[2].scripts.OnClick(); assert(last() == "PL 4 1 2", last()); '
     'Cassette.browser.slots[0].rows[1].scripts.OnClick(); assert(last() == "PL 4 0 2", last())'),
    ("Back", 'Cassette.browser.back.scripts.OnClick(); assert(last() == "BK 4", last())'),
    ("a song row darkens while pressed, like the buttons",
     'local r = Cassette.browser.slots[0].rows[3]; r.scripts.OnMouseDown(r); assert(r.press.shown, "no press effect"); '
     'r.scripts.OnMouseUp(r); assert(not r.press.shown)'),
    ("the Saved tab", 'Cassette.browser.tabSaved.scripts.OnClick(); assert(last() == "BR S", last())'),
    ("saved playlists: a click plays (no song list), the note shows",
     'view(5, 7, 0, 1, 4); record(15, 6, 150, 0, PLAYING + ACCOUNT, 5); mail(Cassette.mailCursor, 5000, 15); wait(4); '
     'assert(Cassette.list.kind == 7 and Cassette.browser.note.shown and Cassette.browser.tabSaved.active); '
     'assert(Cassette.browser.slots[0].rows[4].play.shown); Cassette.browser.slots[0].rows[2].scripts.OnClick(); assert(last() == "PL 5 1 7", last())'),
    ("two pages published at once are both read, in order",
     'Cassette.expectNew = false; view(6, 7, 0, 1, 4); view(7, 7, 0, 1, 3); record(16, 6, 150, 0, PLAYING + ACCOUNT, 7); mail(Cassette.mailCursor, 5000, 16); wait(4); '
     'assert(Cassette.view.n == 7, "view " .. tostring(Cassette.view.n)); assert(logHas("view 6 shown") == 1, "view 6 skipped")'),
    ("search sends the text (cut safely)",
     'local box = Cassette.browser.search; box.GetText = function() return "  linkin park  " end; box.scripts.OnEnterPressed(box); '
     'assert(last() == "FD linkin park", last()); assert(Cassette.CutText("ab\\226\\130\\172", 4) == "ab")'),
    ("the search box's clear button empties it",
     'local box = Cassette.browser.search; box.text = "abc"; box.GetText = nil; box.clear.scripts.OnClick(); assert(box.text == "")'),
    ("a slow page picture is retried",
     'SLOW["pg8"] = 9; view(8, 4, 0, 1, 3); record(17, 6, 150, 0, PLAYING + ACCOUNT, 8); mail(Cassette.mailCursor, 5000, 17); '
     'wait(20); assert(Cassette.view.n == 8, "view " .. tostring(Cassette.view.n))'),
    ("a page carrying the number 5 loads (WoW misreads six-pixel pictures; they're never used)",
     'Cassette.expectNew = false; view(10, 7, 5, 7, 8); record(19, 6, 150, 0, PLAYING + ACCOUNT, 10); mail(Cassette.mailCursor, 5000, 19); wait(4); '
     'assert(logHas("view 10 is from another session") == 0, "page 6 thrown away"); assert(Cassette.view.n == 10, Cassette.view.n)'),
    ("a tab's first page sent ahead is kept, not shown",
     'local showing = Cassette.list; view(11, 3 + 16, 0, 20, 8); record(20, 6, 150, 0, PLAYING + ACCOUNT, 11); mail(Cassette.mailCursor, 5000, 20); wait(4); '
     'assert(Cassette.list == showing, "it replaced the list on show"); assert(Cassette.tabLists[3] and Cassette.tabLists[3].pics[0], "not kept")'),
    ("switching to that tab is instant (and the companion is told)",
     'Cassette.browser.tabLiked.scripts.OnClick(); assert(Cassette.list.kind == 3 and not Cassette.browserWaiting, "waited"); assert(last() == "BR L", last())'),
    ("a tab seen before comes back at once, where you'd scrolled to",
     'Cassette.list.target = 300; wait(1); Cassette.browser.tabSaved.scripts.OnClick(); assert(Cassette.list.kind == 7); '
     'Cassette.browser.tabLiked.scripts.OnClick(); assert(Cassette.list.kind == 3 and Cassette.list.y > 250, Cassette.list.y)'),
    ("rows stay in line with the pictures after the interface scale changes",
     'local old = Cassette.PPU100; Cassette.PPU100 = function() return 150 end; Cassette:LayoutList(); '
     'local L = Cassette.list; local pic = L.pics[0]; local sl = Cassette.browser.slots[0]; '
     'local expect = pic.size[2] / 1.5 / pic.rows; '
     'assert(math.abs(sl.rows[2].h - expect) < 0.01, sl.rows[2].h .. " vs " .. expect); '
     'assert(math.abs(sl.tex.h - pic.size[2] / 1.5) < 0.01, "picture height"); '
     'Cassette.PPU100 = old; Cassette:LayoutList()'),
    ("Escape closes it", 'local found = false; for _, n in ipairs(UISpecialFrames) do found = found or n == "CassetteBrowser" end; assert(found)'),
    ("status shows read statistics", 'SlashCmdList.CASSETTE("status")'),
    ("the log is saved at logout", '_mock_fire("PLAYER_LOGOUT"); assert(#CassetteDB.debug > 3 and CassetteDB.cursors.view >= 5)'),
]
ok = True
for label, code in steps:
    try:
        lua.execute(code)
        print("OK  ", label)
    except Exception as e:
        ok = False
        print("FAIL", label, "->", str(e).splitlines()[0])
for line in list(lua.eval("printed").values())[-2:]:
    print("   chat:", line)
sys.exit(0 if ok else 1)
