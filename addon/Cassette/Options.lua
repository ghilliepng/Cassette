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
  -- a new version of the app is out: install it from here
  local update = UI.Button(f, "Update app", 110, function() JB:UpdateApp() end, true)
  update:SetPoint("TOPLEFT", setup, "BOTTOMLEFT", 0, -6)
  f.updateButton = update
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
  if s.appUpdating then
    text = text .. "\n" .. good .. ("Updating the app to %s...|r"):format(s.appUpdating)
  elseif s.appNewest then
    text = text .. "\n" .. good .. ("A new version of the app is out: %s|r"):format(s.appNewest)
  elseif s.appOld then
    text = text .. "\n" .. bad .. "The app is out of date: get the new one from GitHub.|r"
  end
  f.spotifyStatus:SetText(text)
  if f.updateButton then f.updateButton:SetShown(s.appNewest and s.connected and true or false) end
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

--------------------------------------------------------------------------------
-- Showcase (/cassette showcase [search]): for the download pages' screenshots. Steps through
-- each theme and layout, the browser, the options and the setup window; at each, asks the app
-- (SHOT) to save a picture of just that part of the screen. Puts everything back afterwards.
--------------------------------------------------------------------------------

-- The screen rectangle (pixels from the top-left) around some frames, with a margin.
local function shotRect(frames)
  local _, ph = GetPhysicalScreenSize()
  local k = ph / 768
  local l, b, r, t
  for _, fr in ipairs(frames) do
    if fr and fr:IsShown() and fr:GetLeft() then
      local s = fr:GetEffectiveScale()
      local fl, fb, fr2, ft = fr:GetLeft() * s, fr:GetBottom() * s, fr:GetRight() * s, fr:GetTop() * s
      l, b = math.min(l or fl, fl), math.min(b or fb, fb)
      r, t = math.max(r or fr2, fr2), math.max(t or ft, ft)
    end
  end
  if not l then return nil end
  local pad = 24
  local x, y = math.max(0, math.floor(l * k) - pad), math.max(0, math.floor(ph - t * k) - pad)
  return x, y, math.floor((r - l) * k) + 2 * pad, math.floor((t - b) * k) + 2 * pad
end

-- Alt+Z hides the interface (UIParent) and everything on it. While the showcase runs, Cassette's
-- frames sit on a holder of their own instead, at the same scale, so they stay on screen and the
-- pictures show only Cassette and the world behind it. Afterwards they go back on UIParent, and
-- hide with the rest of the interface again.
local lifted = {}
local function liftFrames(frames)
  local holder = _G.CassetteShowcase or CreateFrame("Frame", "CassetteShowcase", nil)
  holder:SetScale(UIParent:GetEffectiveScale())
  holder:SetAllPoints(UIParent)
  holder:Show()
  for _, fr in ipairs(frames) do
    if fr and not lifted[fr] then
      local strata, level = fr:GetFrameStrata(), fr:GetFrameLevel()
      lifted[fr] = { fr:GetParent(), strata, level }
      fr:SetParent(holder)
      if strata then fr:SetFrameStrata(strata) end
      if level then fr:SetFrameLevel(level) end
    end
  end
end
local function dropFrames()
  for fr, was in pairs(lifted) do
    fr:SetParent(was[1] or UIParent)
    if was[2] then fr:SetFrameStrata(was[2]) end
    if was[3] then fr:SetFrameLevel(was[3]) end
    lifted[fr] = nil
  end
  if _G.CassetteShowcase then _G.CassetteShowcase:Hide() end
end

function JB:Showcase(search)
  if self.showcasing then return end
  if not self.state.connected then
    self:Print("start the Cassette app first: it saves the pictures.")
    return
  end
  self.showcasing = true
  local db = self.db
  local saved = { theme = db.theme, layout = db.layout, point = db.point, scale = db.scale, shown = db.shown }
  local mine = self:ThemeKey()
  local function look(theme, layout)
    db.theme, db.layout, db.shown, db.scale = theme, layout, true, 1.15
    db.point = { "CENTER", "UIParent", "CENTER", 0, -120 }
    self:ApplyLook()
  end
  local function hideWindows()
    if self.browser then self.browser:Hide() end
    if self.options then self.options:Hide() end
    if self.setup then self.setup:Hide() end
  end
  local steps = {}
  for _, theme in ipairs(UI.THEME_ORDER) do
    steps[#steps + 1] = { "theme-" .. theme, function() hideWindows() look(theme, "bar") end, function() return { self.widget } end }
  end
  for _, layout in ipairs({ "stackedBelow", "stackedAbove", "slim", "card" }) do
    steps[#steps + 1] = { "layout-" .. layout, function() look(mine, layout) end, function() return { self.widget } end }
  end
  steps[#steps + 1] = { "browser-liked", function()
    look(mine, "bar")
    if not (self.browser and self.browser:IsShown()) then self:ToggleBrowser() end
    self:OpenTab(3, "L")
  end, function() return { self.widget, self.browser } end }
  if search then
    steps[#steps + 1] = { "browser-search", function() self:BrowserCommand("FD", search, 0) end,
      function() return { self.widget, self.browser } end }
  end
  steps[#steps + 1] = { "options", function()
    hideWindows()
    if not (self.options and self.options:IsShown()) then self:ToggleOptions() end
  end, function() return { self.options } end }
  steps[#steps + 1] = { "setup", function() hideWindows() self:ShowSetup() end, function() return { self.setup } end }

  local function lift() liftFrames({ self.widget, self.browser, self.options, self.setup }) end
  lift()
  self:Print(("showcase: %d pictures, about %d seconds. Press Alt+Z now to hide the rest of your interface: "
    .. "Cassette stays on screen until it's done, then hides with the rest, and Alt+Z brings it all back. "
    .. "Keep WoW in front and the mouse away from Cassette."):format(#steps, #steps * 4 + 3))
  local i = 0
  local function nextStep()
    i = i + 1
    local step = steps[i]
    if not step then
      hideWindows()
      db.theme, db.layout, db.point, db.scale, db.shown = saved.theme, saved.layout, saved.point, saved.scale, saved.shown
      self:ApplyLook()
      dropFrames()
      self.showcasing = nil
      self:Print("showcase done: the pictures are in the app's folder (%LOCALAPPDATA%\Cassette\showcase).")
      return
    end
    local ok, err = pcall(step[2])
    if not ok then self:Print("showcase: " .. tostring(err)) end
    lift()   -- the browser and the windows are made the first time they open
    C_Timer.After(3, function()   -- the cover and song pictures redraw for the new look first
      local x, y, w, h = shotRect(step[3]())
      if x then self:Send("SHOT", ("%s %d %d %d %d"):format(step[1], x, y, w, h)) end
      C_Timer.After(1, nextStep)
    end)
  end
  C_Timer.After(3, nextStep)   -- time to press Alt+Z
end
