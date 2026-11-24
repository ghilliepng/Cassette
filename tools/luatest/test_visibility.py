"""When the player shows: "Hide at login if no music is playing", the minimap icon and addon
menu button, and the one-time "What's new" window. Each case starts its own WoW stand-in, as
a fresh login or a /reload with the saved settings given.
Usage: python test_visibility.py <addon dir> <wowmock.lua>"""
import sys

from lupa import lua51

ADDON_DIR, MOCK = sys.argv[1], sys.argv[2]


def boot(saved, reload=False, before=""):
    """A new game: CassetteDB as saved (Lua table text), then logging in (or /reloading)."""
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(open(MOCK, encoding="utf-8").read())
    lua.execute("Minimap = CreateFrame('Frame', 'Minimap'); CassetteDB = " + saved + "; " + before)
    JB = lua.table()
    for name in lua.eval("ADDON_FILES").values():
        lua.eval("loadstring")(open(f"{ADDON_DIR}/{name}.lua", encoding="utf-8").read(), "@" + name)("Cassette", JB)
    initial, reloading = ("false", "true") if reload else ("true", "false")
    lua.execute(f'''
      _mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", {initial}, {reloading})
      _mock_fire("PLAYER_LOGIN")
      function record(playing)   -- a record from the app: Spotify open, playing or paused
        Cassette:ApplyRecord({{ 0, 200, 10, time() % 4096, (playing and 1 or 0) + 8 + 50 * 16, 0 }})
      end
      function shown() return Cassette.widget.shown end
    ''')
    return lua


SET_UP = '{ setupDone = true, newsSeen = "0.2.0", hideIdle = true, shown = true }'
ok = True


def case(label, saved, code, reload=False, before=""):
    global ok
    try:
        boot(saved, reload, before).execute(code)
        print("OK  ", label)
    except Exception as e:
        ok = False
        print("FAIL", label, "->", str(e).splitlines()[0])


case("the setting is off by default: the player shows as it always did",
     '{ setupDone = true, newsSeen = "0.2.0", shown = true }', 'record(false); assert(shown())')
case("fresh login, setting on, nothing playing: hidden",
     SET_UP, 'assert(not shown()); record(false); assert(not shown())')
case("fresh login, music already playing: shown",
     SET_UP, 'record(true); assert(shown())')
case("hidden, then music starts later: shown, and stays when it stops",
     SET_UP, 'record(false); assert(not shown()); record(true); assert(shown()); record(false); assert(shown())')
case("hidden with the button: music starting doesn't bring it back",
     SET_UP, 'record(true); assert(shown()); Cassette:ToggleShown(); assert(not shown()); record(true); assert(not shown())')
case("brought up with the button while nothing plays: stays up",
     SET_UP, 'record(false); Cassette:ToggleShown(); assert(shown()); record(false); assert(shown())')
case("a /reload keeps it shown",
     '{ setupDone = true, newsSeen = "0.2.0", hideIdle = true, shown = true, autoShow = false }',
     'record(false); assert(shown())', reload=True)
case("a /reload keeps it hidden, and music still brings it up",
     '{ setupDone = true, newsSeen = "0.2.0", hideIdle = true, shown = false, autoShow = true }',
     'record(false); assert(not shown()); record(true); assert(shown())', reload=True)
case("the next fresh login after showing it: hidden again until music",
     '{ setupDone = true, newsSeen = "0.2.0", hideIdle = true, shown = true, autoShow = false }',
     'assert(not shown()); record(true); assert(shown())')
case("setup not done yet: shown, whatever the setting",
     '{ setupDone = false, hideIdle = true, shown = true }', 'record(false); assert(shown())')
case("turning the setting off: music no longer brings it up by itself",
     SET_UP, 'Cassette.options = nil; Cassette:CreateOptions(); CassetteDB.hideIdle = false; '
             'CassetteDB.autoShow = false; record(true); assert(not shown())')

# the button
case("Cassette's own minimap icon, when no LibDBIcon is loaded",
     SET_UP, 'assert(CassetteMinimapButton and CassetteMinimapButton.shown)')
case("its left-click shows and hides the player",
     SET_UP, 'local b = CassetteMinimapButton; b.scripts.OnClick(b, "LeftButton"); assert(shown()); '
             'b.scripts.OnClick(b, "LeftButton"); assert(not shown())')
case("its right-click opens the options",
     SET_UP, 'local b = CassetteMinimapButton; b.scripts.OnClick(b, "RightButton"); assert(CassetteOptions.shown); '
             'assert(not shown())')
case("the Minimap icon option hides it",
     SET_UP, 'CassetteDB.minimapIcon = false; Cassette:RefreshMinimapIcon(); assert(not CassetteMinimapButton.shown)')
case("the addon menu entry: left-click shows the player, right-click the options",
     SET_UP, 'Cassette_OnAddonCompartmentClick("Cassette", "LeftButton"); assert(shown()); '
             'Cassette_OnAddonCompartmentClick("Cassette", "RightButton"); assert(CassetteOptions.shown)')
case("/cassette shows it too",
     SET_UP, 'SlashCmdList.CASSETTE(""); assert(shown())')
case("with LibDBIcon loaded by another addon: registered through it, not drawn by Cassette",
     SET_UP, 'assert(registered == "Cassette" and not CassetteMinimapButton); '
             'launcher.OnClick(nil, "LeftButton"); assert(shown()); '
             'CassetteDB.minimapIcon = false; Cassette:RefreshMinimapIcon(); assert(hidden == "Cassette")',
     before='''
       local LDB = { NewDataObject = function(self, name, o) launcher = o; return o end }
       local DBI = { Register = function(self, name) registered = name end,
                     Show = function() end, Hide = function(self, name) hidden = name end }
       LibStub = function(name) return ({ ["LibDataBroker-1.1"] = LDB, ["LibDBIcon-1.0"] = DBI })[name] end
     ''')

# what's new
case("set up before 0.2.0: 'What's new' shows once, a few seconds after login",
     '{ setupDone = true, shown = true }',
     '_mock_update(6); assert(CassetteNews and CassetteNews.shown); assert(CassetteDB.newsSeen == "0.2.0")')
case("...and not again after that",
     '{ setupDone = true, shown = true, newsSeen = "0.2.0" }', '_mock_update(6); assert(not CassetteNews)')
case("a new player gets the first-time setup, not 'What's new'",
     '{}', '_mock_update(6); assert(not CassetteNews); assert(CassetteSetup.shown); assert(CassetteDB.newsSeen == "0.2.0")')
case("it has the new setting's toggle, which turns it on",
     '{ setupDone = true, shown = true }',
     '_mock_update(6); local c; for _, f in ipairs(_mock_frames()) do '
     'if f.label and f.label.text == "Hide at login if no music is playing" then c = f end end; '
     'assert(c, "no toggle"); assert(not CassetteDB.hideIdle); c.scripts.OnClick(c); assert(CassetteDB.hideIdle)')
case("no newer app: no Update app button",
     '{ setupDone = true, shown = true }', '_mock_update(6); assert(not Cassette.news.update.shown)')
case("a newer app out: the Update app button shows, and updates the app",
     '{ setupDone = true, shown = true }',
     '_mock_update(6); local s = Cassette.state; s.connected, s.appNewest = true, "0.2.0"; Cassette:RefreshOptionsStatus(); '
     'assert(Cassette.news.update.shown); assert(Cassette.news.appLine.text:find("0.2.0")); '
     'Cassette.news.update.scripts.OnClick(Cassette.news.update); assert(s.appUpdating == "0.2.0"); '
     'assert(not Cassette.news.update.shown); assert(Cassette.news.appLine.text:find("Updating"))')
case("its Options button opens the options",
     '{ setupDone = true, shown = true }',
     '_mock_update(6); local kids = CassetteNews.children or {}; Cassette.news:Hide(); Cassette:ToggleOptions(); '
     'assert(CassetteOptions.shown)')
case("the first-time setup and the options offer the setting",
     '{}', '_mock_update(6); Cassette:ToggleOptions(); local found = 0; '
           'for _, f in ipairs(_mock_frames()) do if f.label and f.label.text == "Hide at login if no music is playing" '
           'then found = found + 1 end end; assert(found == 2, found)')

sys.exit(0 if ok else 1)
