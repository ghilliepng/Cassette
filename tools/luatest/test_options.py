"""Layouts, the options window and the first-setup window, in the WoW stand-in.
Usage: python test_options.py <addon dir> <wowmock.lua>"""
import sys

from lupa import lua51

lua = lua51.LuaRuntime(unpack_returned_tuples=True)
d = sys.argv[1]
lua.execute(open(sys.argv[2], encoding="utf-8").read())
JB = lua.table()
for name in lua.eval("ADDON_FILES").values():
    lua.eval("loadstring")(open(f"{d}/{name}.lua", encoding="utf-8").read(), "@" + name)("Cassette", JB)
lua.execute('''
-- the game's own frame art (Modern uses it where the client has it)
NineSliceUtil = {
  GetLayout = function(name) if name ~= "Dialog" then return { name = name } end end,
  ApplyLayout = function(c, layout)
    for _, p in ipairs({ "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
                         "TopEdge", "BottomEdge", "LeftEdge", "RightEdge", "Center" }) do
      rawset(c, p, rawget(c, p) or c:CreateTexture())
    end
  end,
}
C_Texture = { GetAtlasInfo = function(name) return { file = 1 } end }
-- listen before logging in, so the look sent at start-up is caught too
sent = {}
local send = Cassette.Send
Cassette.Send = function(self, cmd, arg) sent[#sent + 1] = cmd .. (arg and (" " .. arg) or "") return send(self, cmd, arg) end
function last(prefix) for i = #sent, 1, -1 do if sent[i]:sub(1, #prefix) == prefix then return sent[i] end end end
_mock_fire("ADDON_LOADED", "Cassette"); _mock_fire("PLAYER_ENTERING_WORLD", true, false); _mock_fire("PLAYER_LOGIN")
''')
steps = [
    ("the first-time setup shows by itself a few seconds after the first login",
     '_mock_update(5); assert(CassetteSetup and CassetteSetup.shown)'),
    ("it says the companion isn't running yet, with the download link", 'assert(CassetteSetup.url.shown); tallBefore = CassetteSetup.h'),
    ("...and ticks it off once the companion answers",
     'Cassette.state.connected = true; Cassette:RefreshWidget(); assert(not CassetteSetup.url.shown)'),
    ("the Spotify button shows until the account is connected",
     'assert(CassetteSetup.spotifyButton.shown); Cassette.state.account = true; Cassette:RefreshSetup(); assert(not CassetteSetup.spotifyButton.shown)'),
    ("no gaps: steps close up and the window shrinks once the link and button aren't needed",
     'assert(CassetteSetup.h <= tallBefore - 26, CassetteSetup.h .. " vs " .. tallBefore)'),
    ("Done closes it for good", 'Cassette.setup.scripts.OnHide = nil; for _, c in pairs(Cassette.setup.children or {}) do end; '
                                'CassetteDB.setupDone = true; Cassette.setup:Hide(); assert(CassetteDB.setupDone)'),
    ("the bar told the companion its look at start-up (cover 40, Spotify green, a font)",
     'assert(last("LOOK"):match("^LOOK 40 31 214 97 "), tostring(last("LOOK")))'),
    ("every layout places the bar without errors, with its own size",
     'for _, key in ipairs(Cassette.LAYOUT_ORDER) do CassetteDB.layout = key; Cassette:ApplyLook(); '
     'local L = Cassette.LAYOUTS[key]; assert(Cassette.widget.w == L.w and Cassette.widget.h == L.h, key) end'),
    ("the card layout asks the companion for a 188-unit cover", 'assert(last("LOOK"):match("^LOOK 188 "), last("LOOK"))'),
    ("slim hides the volume and time", 'CassetteDB.layout = "slim"; Cassette:ApplyLook(); assert(not Cassette.widget.volume.shown and not Cassette.widget.time.shown)'),
    ("no LOOK message when nothing changed", 'local n = #sent; Cassette:ApplyLook(); assert(#sent == n, #sent - n)'),
    ("class colour: the accent becomes the class colour and the companion is told",
     'CassetteDB.accent = "class"; Cassette:ApplyLook(); local r, g, b = Cassette:Accent(); assert(r == 1 and b == 0.41); '
     'assert(last("LOOK"):match(" 255 245 105 "), last("LOOK"))'),
    ("right-click opens the options", 'Cassette.widget.scripts.OnMouseUp(Cassette.widget, "RightButton"); assert(CassetteOptions and CassetteOptions.shown)'),
    ("the options window builds all its controls", 'assert(#Cassette.UI.refreshers > 20, #Cassette.UI.refreshers); Cassette.UI.RefreshAll()'),
    ("Escape closes it", 'local found = false; for _, n in ipairs(UISpecialFrames) do if n == "CassetteOptions" then found = true end end; assert(found)'),
    ("/tape options toggles it", 'SlashCmdList.CASSETTE("options"); assert(not CassetteOptions.shown); SlashCmdList.CASSETTE("options"); assert(CassetteOptions.shown)'),
    ("/tape setup brings back the first-time setup", 'Cassette.setup:Hide(); SlashCmdList.CASSETTE("setup"); assert(Cassette.setup.shown)'),
    ("the addon-menu entry exists", 'assert(type(Cassette_OnAddonCompartmentClick) == "function")'),
    ("font: the game's own without EllesmereUI", 'assert(Cassette:FontPath() == STANDARD_TEXT_FONT, Cassette:FontPath())'),
    ("font: EllesmereUI's when it's there",
     'EllesmereUI = { GetFontPath = function() return "Interface\\AddOns\\EllesmereUI\\media\\fonts\\Expressway.TTF" end, '
     'GetFontOutlineFlag = function() return "" end, GetFontUseShadow = function() return false end }; '
     'assert(Cassette:FontPath():find("Expressway")); Cassette.lookSent = nil; Cassette:ApplyLook(); assert(last("LOOK"):find("Expressway"), last("LOOK")); '
     'EllesmereUI = nil'),
    ("each theme paints the player, browser and windows without errors, and tells the companion",
     'Cassette:ToggleBrowser(); for _, key in ipairs(Cassette.UI.THEME_ORDER) do CassetteDB.theme = key; Cassette:ApplyLook(); Cassette.UI.RefreshAll(); '
     'assert(last("LOOK"):find(" " .. key .. " "), last("LOOK")) end'),
    ("Modern wears the game's own frame where it has one",
     'CassetteDB.theme = "modern"; Cassette:ApplyLook(); local set = Cassette.widget.themed.skin.modern; '
     'assert(set.native and #set.native == 9, "no native frame"); assert(rawget(Cassette.widget, "Center").shown)'),
    ("the first-time setup offers the theme and player style", 'Cassette:ShowSetup(); assert(Cassette.setup.looks and Cassette.setup.looks.h > 40, Cassette.setup.looks.h)'),
    ("a newer app on GitHub: said once in chat, and in the options with an Update app button",
     'FILES["app_0"] = Cassette.NumberSize(33); FILES["app_1"] = Cassette.NumberSize(34); '
     'Cassette.state.connected = true; Cassette:ReadAppInfo(1); _mock_update(1); '
     'assert(Cassette.state.appVersion == "0.1.1" and Cassette.state.appNewest == "0.1.2", tostring(Cassette.state.appNewest)); '
     'assert(printed[#printed]:find("0.1.2 is out"), printed[#printed]); '
     'Cassette.options:Show(); Cassette:RefreshOptionsStatus(); '
     'assert(Cassette.options.spotifyStatus.text:find("new version of the app is out: 0.1.2")); assert(Cassette.options.updateButton.shown)'),
    ("Update app asks the app to update itself, and the button goes",
     'Cassette:UpdateApp(); assert(last("UPDATE"), "no UPDATE sent"); assert(not Cassette.options.updateButton.shown); '
     'assert(Cassette.options.spotifyStatus.text:find("Updating the app to 0.1.2"))'),
    ("up to date: no news, no button",
     'local n = #printed; Cassette.toldAppNews, Cassette.state.appUpdating = nil, nil; FILES["app_1"] = Cassette.NumberSize(0); '
     'Cassette:ReadAppInfo(1); _mock_update(1); assert(Cassette.state.appNewest == nil and #printed == n, printed[#printed]); '
     'assert(not Cassette.options.updateButton.shown)'),
    ("an app from before updates (no version files): told to get the new one by hand",
     'FILES["app_0"], FILES["app_1"] = { 0, 0 }, { 0, 0 }; Cassette.state.appVersion = nil; Cassette:ReadAppInfo(1); _mock_update(30); '
     'assert(Cassette.state.appOld); assert(printed[#printed]:find("out of date") and printed[#printed]:find("releases/latest"), printed[#printed]); '
     'assert(Cassette.options.spotifyStatus.text:find("out of date")); Cassette.options:Hide()'),
    ("showcase: Cassette moves off the interface, which then hides (no Alt+Z needed)",
     'CassetteDB.accent = "class"; Cassette.state.connected = true; Cassette:Showcase(); assert(Cassette.widget:GetParent() == CassetteShowcase); '
     'assert(UIParent.shown); _mock_update(3.5); assert(Cassette.widget:GetParent() == CassetteShowcase); assert(not UIParent.shown); '
     'assert(CassetteDB.accent == "spotify")'),
    ("...the browser and the windows too, once they open",
     '_mock_update(44); assert(Cassette.browser:GetParent() == CassetteShowcase and Cassette.options:GetParent() == CassetteShowcase); '
     'assert(not Cassette.widget.shown, "the player shows behind the options"); assert(CassetteDB.shown, "Show the player looks unticked")'),
    ("...a picture for every step, then all back on the interface, which shows again",
     '_mock_update(10); assert(not Cassette.showcasing); assert(Cassette.widget.shown and CassetteDB.accent == "class", CassetteDB.accent); local n = 0; for _, m in ipairs(sent) do if m:match("^SHOT ") then n = n + 1 end end; '
     'assert(n >= 9, n); for _, fr in ipairs({ Cassette.widget, Cassette.browser, Cassette.options, Cassette.setup }) do '
     'assert(fr:GetParent() == UIParent) end; assert(not CassetteShowcase.shown); assert(UIParent.shown)'),
    ("...and the watchdog later changes nothing", '_mock_update(30); assert(UIParent.shown and Cassette.widget:GetParent() == UIParent)'),
    ("reset puts the bar back", 'CassetteDB.scale = 1.7; SlashCmdList.CASSETTE("reset"); assert(CassetteDB.scale == 1)'),
]
ok = True
for label, code in steps:
    try:
        lua.execute(code)
        print("OK  ", label)
    except Exception as e:
        ok = False
        print("FAIL", label, "->", str(e).splitlines()[0])
sys.exit(0 if ok else 1)
