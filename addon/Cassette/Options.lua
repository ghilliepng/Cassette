-- The options window: right-click the player, /tape options, or WoW's addon menu.
--
--   Look     theme (Classic, Modern, EllesmereUI), accent colour; the font follows
--            EllesmereUI's, or the game's
--   Player   style, size, background, lock, show
--   Spoken   dip the music while Spoken reads: on/off, how low, how soon back, for which parts
--   Spotify  companion and account status, set up on PC, first-time setup

local _, JB = ...

local UI = JB.UI
local W, H, COL = 560, 540, 240

local function apply()
  JB:ApplyLook()
  UI.RefreshAll()
end

-- A column that stacks controls downwards.
local function column(parent, x)
  local c = { y = -44 }
  function c.add(widget, height, gap)
    widget:SetPoint("TOPLEFT", parent, "TOPLEFT", x, c.y)
    c.y = c.y - (height or widget:GetHeight()) - (gap or 8)
    return widget
  end
  return c
end

local PARTS = {
  { "quests", "Quest text" },
  { "gossip", "NPCs talking to you" },
  { "readables", "Books and letters" },
  { "places", "Zone lore" },
  { "bosses", "Boss stories" },
  { "chatter", "NPC chatter around you" },
}

-- The theme and player style choices (the first-time setup shows them too).
function JB:ThemeChoice(parent, width)
  local themes = {}
  for _, key in ipairs(UI.THEME_ORDER) do themes[#themes + 1] = { key, UI.THEMES[key].name } end
  return UI.Choice(parent, "Theme", themes, width,
    function() return JB:ThemeKey() end,
    function(v) JB.db.theme = v; apply() end)
end

function JB:StyleChoice(parent, width)
  local layouts = {}
  for _, key in ipairs(self.LAYOUT_ORDER) do layouts[#layouts + 1] = { key, self.LAYOUTS[key].name } end
  return UI.Choice(parent, "Player style", layouts, width,
    function() return JB.db.layout end,
    function(v) JB.db.layout = v; apply() end)
end

function JB:CreateOptions()
  local f = UI.Window("CassetteOptions", W, H, "Cassette")
  self.options = f
  local db = self.db
  f:SetScript("OnShow", UI.RefreshAll)

  -- left: looks and the player
  local L = column(f, 16)
  L.add(UI.Heading(f, "Look"), 16, 6)
  L.add(self:ThemeChoice(f, COL), nil, 10)
  local accent = L.add(UI.Choice(f, "Accent colour (progress bar, highlights)", {
    { "spotify", "Spotify green" }, { "class", "Class colour" }, { "custom", "Custom colour" },
  }, COL - 30, function() return db.accent end, function(v) db.accent = v; apply() end), nil, 8)
  local swatch = UI.Swatch(f,
    function() return unpack(db.accentColor) end,
    function(r, g, b) db.accentColor, db.accent = { r, g, b }, "custom"; apply() end)
  swatch:SetPoint("BOTTOMRIGHT", accent, "BOTTOMRIGHT", 30, 1)
  local fontNote = L.add(UI.Text(f, 11, "dim"), 14, 16)
  fontNote:SetWidth(COL)
  table.insert(UI.refreshers, function()
    fontNote:SetText(_G.EllesmereUI and "Font: EllesmereUI's (change it there)" or "Font: your game's")
  end)

  L.add(UI.Heading(f, "Player"), 16, 6)
  L.add(self:StyleChoice(f, COL), nil, 10)
  L.add(UI.Slider(f, "Size", 0.6, 2, 0.05, function(v) return ("%d%%"):format(v * 100 + 0.5) end,
    function() return db.scale end,
    function(v) db.scale = v; JB:ApplyLook() end))
  L.add(UI.Slider(f, "Background", 0, 1, 0.05, function(v) return ("%d%%"):format(v * 100 + 0.5) end,
    function() return db.bgAlpha end,
    function(v) db.bgAlpha = v; JB:ApplyLook() end))
  L.add(UI.Check(f, "Lock in place", function() return db.locked end, function(v) db.locked = v end), 18, 4)
  L.add(UI.Check(f, "Show the player", function() return db.shown end,
    function(v) db.shown = v; JB:RefreshWidget() end), 18, 6)
  L.add(UI.Button(f, "Reset position", 110, function()
    db.point, db.scale = JB.DEFAULTS.point, 1
    apply()
  end), 22, 16)

  -- right: Spoken and Spotify
  local R = column(f, 16 + COL + 48)
  R.add(UI.Heading(f, "NPC dialogue (Spoken)"), 16, 6)
  local spokenNote = R.add(UI.Text(f, 11, "dim"), 14, 4)
  table.insert(UI.refreshers, function()
    spokenNote:SetText(JB.HasSpoken and JB:HasSpoken() and "Spoken is installed." or "Spoken isn't installed: these wait for it.")
  end)
  R.add(UI.Check(f, "Reduce volume during NPC dialogue", function() return db.duck end,
    function(v) db.duck = v; JB:UpdateDuck() end), 18, 8)
  R.add(UI.Slider(f, "How low", 0, 90, 5, function(v) return ("%d%% of your volume"):format(v) end,
    function() return db.duckLevel end,
    function(v) JB:SetDuckLevel(v) end))
  R.add(UI.Slider(f, "Back up after quiet for", 1, 5, 0.5, function(v) return ("%.1f s"):format(v) end,
    function() return db.duckHold end,
    function(v) db.duckHold = v end), nil, 6)
  R.add(UI.Text(f, 11.5), 14, 4):SetText("Reduce it for:")
  for _, p in ipairs(PARTS) do
    R.add(UI.Check(f, p[2], function() return JB:DipsFor(p[1]) end, function(v)
      db.duckSources = db.duckSources or {}
      db.duckSources[p[1]] = v
      JB:UpdateDuck()
    end), 18, 2)
  end

  R.y = R.y - 12
  R.add(UI.Heading(f, "Spotify"), 16, 6)
  -- the status can run to three lines: the buttons sit under it, wherever it ends
  local status = R.add(UI.Text(f, 11.5), 14, 6)
  status:SetWidth(COL)
  status:SetSpacing(3)
  f.spotifyStatus = status
  table.insert(UI.refreshers, function() JB:RefreshOptionsStatus() end)
  local setup = UI.Button(f, "Set up on PC", 110, function()
    JB:Command("SETUP")
    JB:Print("the Connect Spotify window is open on your PC (Alt+Tab if it's behind the game).")
  end, true)
  setup:SetPoint("TOPLEFT", status, "BOTTOMLEFT", 0, -10)
  local first = UI.Button(f, "First-time setup", 110, function()
    f:Hide()
    if JB.ShowSetup then JB:ShowSetup() end
  end)
  first:SetPoint("LEFT", setup, "RIGHT", 8, 0)
end

-- The app's and the account's state, kept current while the window is open (Widget.lua calls
-- this whenever news arrives).
function JB:RefreshOptionsStatus()
  local f = self.options
  if not f or not f.spotifyStatus or not f:IsShown() then return end
  local s = self.state
  local function hex(r, g, b) return ("|cff%02x%02x%02x"):format(r * 255, g * 255, b * 255) end
  local good, bad, dim = hex(self:Accent()), "|cffff6b6b", hex(self:Colour("dim"))
  local text = ("Cassette app: %s|r\nSpotify account: %s|r"):format(
    s.connected and good .. "running" or bad .. "not running",
    s.account and good .. "connected" or bad .. "not connected")
  if not s.account then text = text .. "\n" .. dim .. "Connect it for playlists, liked songs and search.|r" end
  f.spotifyStatus:SetText(text)
end

function JB:ToggleOptions()
  if not self.options then self:CreateOptions() end
  self.options:SetShown(not self.options:IsShown())
end

-- WoW's addon menu (the compartment by the minimap), where the client has one
function Cassette_OnAddonCompartmentClick()
  JB:ToggleOptions()
end

-- A page in WoW's own Settings, with a button to the options window, where the client has it
local ev = CreateFrame("Frame")
ev:RegisterEvent("PLAYER_LOGIN")
ev:SetScript("OnEvent", function()
  if not (Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory) then return end
  local panel = CreateFrame("Frame")
  local text = UI.Text(panel, 13)
  text:SetPoint("TOPLEFT", 16, -16)
  text:SetText("Cassette: Spotify in a compact player.")
  local open = UI.Button(panel, "Open Cassette options", 160, function()
    if SettingsPanel then HideUIPanel(SettingsPanel) end
    JB:ToggleOptions()
  end, true)
  open:SetPoint("TOPLEFT", text, "BOTTOMLEFT", 0, -12)
  pcall(function()
    local category = Settings.RegisterCanvasLayoutCategory(panel, "Cassette")
    Settings.RegisterAddOnCategory(category)
  end)
end)
