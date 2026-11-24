-- Cassette: Spotify in a compact bar. Settings, start-up and slash commands.
--
-- How it talks to the companion on the PC:
--   game -> PC   Strip.lua draws short text messages as coloured squares in the screen's
--                top-left corner; the companion reads them off the screen.
--   PC -> game   Live.lua reads files the companion fills in, in the addon's live folder.
--                WoW reads each file once, so they come from pools used one by one.

local ADDON, JB = ...
_G.Cassette = JB

JB.version = "0.2.0"
JB.MEDIA = "Interface\\AddOns\\Cassette\\Media\\"
JB.startTime = GetTime()

JB.state = {
  connected = false,      -- a record arrived and nothing has gone unanswered since
  everConnected = false,
  available = false,      -- Spotify is open
  art = 0,                -- art number of the current song (0: nothing playing)
  duration = 0,           -- seconds
  position = 0,           -- seconds, at `anchor`
  anchor = 0,             -- GetTime() of `position`
  playing = false,
  shuffle = false,
  muted = false,
  volume = 100,
  exhausted = false,      -- the file pools for this session are used up: needs a /reload
}

local DEFAULTS = {
  point = { "BOTTOMRIGHT", "UIParent", "BOTTOMRIGHT", -43, 64 },
  scale = 1,
  locked = false,
  shown = true,
  layout = "bar",     -- Widget.lua's LAYOUTS
  accent = "spotify", -- "spotify", "class" or "custom"
  accentColor = { 0.12, 0.84, 0.38 },
  theme = nil,        -- "classic", "modern" or "ellesmere" (UI.lua); chosen at first login
  bgAlpha = 0.88,
  duck = true,        -- dip the music while Spoken reads
  duckLevel = 30,     -- % of your volume during the dip
  duckHold = 2,       -- seconds of quiet before the music comes back up
  setupDone = false,  -- the first-setup window has been finished once
  musicApp = "spotify", -- the app the player follows: a JB.MUSIC_APPS key
  hideIdle = false,   -- at a fresh login, keep the player hidden until music plays
  autoShow = false,   -- (this game session: hidden by hideIdle, so music playing brings it up)
  minimapIcon = true, -- the minimap icon (left-click: the player; right-click: the options)
  minimapAngle = 200, -- where it sits round the minimap, in degrees (when Cassette draws it)
  newsSeen = nil,     -- the last "What's new" window shown (Setup.lua)
}
JB.DEFAULTS = DEFAULTS

--------------------------------------------------------------------------------
-- The music app the player follows (the app on the PC: players.py). Playlists, liked songs
-- and search (the browser) are Spotify's only.
--------------------------------------------------------------------------------

JB.MUSIC_APPS = {   -- key, name, beta (new: may not work fully yet)
  { "spotify", "Spotify" }, { "youtube", "YouTube Music", true }, { "apple", "Apple Music", true },
}
JB.BETA_NOTE = "Beta: this may not work fully yet."

function JB:MusicBeta()
  local key = self:MusicApp()
  for _, a in ipairs(self.MUSIC_APPS) do
    if a[1] == key then return a[3] == true end
  end
  return false
end
JB.FOLLOWS_OTHERS = 2 * 32   -- the first app on the PC that can follow others: 0.2.0 (updates.py's code)

function JB:MusicApp()
  local key = self.db and self.db.musicApp
  for _, a in ipairs(self.MUSIC_APPS) do
    if a[1] == key then return a[1], a[2] end
  end
  return "spotify", "Spotify"
end

function JB:MusicName()
  local _, name = self:MusicApp()
  return name
end

function JB:IsSpotify()
  return self:MusicApp() == "spotify"
end

-- YouTube Music plays in a browser or a browser-based app, and those never take shuffle from
-- other programs.
function JB:CanShuffle()
  return self:MusicApp() ~= "youtube"
end

-- false when the app on the PC is too old to follow anything but Spotify
function JB:AppFollowsMusicApp()
  local s = self.state
  if self:IsSpotify() then return true end
  if s.appOld then return false end
  return not s.appCode or s.appCode >= self.FOLLOWS_OTHERS
end

-- Tell the app on the PC which music app to follow. It remembers, so this is only sent when
-- the choice changes, and once on connecting if it was ever changed (a message is a flash).
function JB:SendMusicApp(quiet)
  local key = self:MusicApp()
  if quiet then self:Send("MUSIC", key) else self:Command("MUSIC", key) end
end

function JB:SetMusicApp(key)
  if key == self:MusicApp() then return end
  self.db.musicApp, self.db.musicAppChanged = key, true
  self:SendMusicApp()
  self:RefreshWidget()
  if key == "spotify" and self.browser and self.browser:IsShown() and not self.view and self.BrowserCommand then
    self:BrowserCommand("BR", "P", 0)
  end
  if self.RefreshBrowser then self:RefreshBrowser() end
  if self.RefreshOptionsStatus then self:RefreshOptionsStatus() end
end

-- Show or hide the player: the minimap icon, the addon menu, /cassette and the options' check.
-- The player's choice holds until the game closes (music no longer brings it up by itself).
function JB:SetShown(shown)
  self.db.shown, self.db.autoShow = shown and true or false, false
  self:RefreshWidget()
  if self.UI and self.UI.RefreshAll then self.UI.RefreshAll() end
end

function JB:ToggleShown()
  self:SetShown(not self.db.shown)
end

function JB:Print(msg)
  print("|cff1ed760Cassette|r " .. msg)
end

--------------------------------------------------------------------------------
-- Looks: accent colour and font, shared by the player, the browser and the windows
--------------------------------------------------------------------------------

function JB:Accent()
  local db = self.db
  if db and db.accent == "class" then
    local _, class = UnitClass("player")
    local c = class and (CUSTOM_CLASS_COLORS or RAID_CLASS_COLORS)[class]
    if c then return c.r, c.g, c.b end
  elseif db and db.accent == "custom" and db.accentColor then
    return db.accentColor[1], db.accentColor[2], db.accentColor[3]
  end
  return 0.12, 0.84, 0.38   -- Spotify green
end

-- The font: EllesmereUI's when it's installed (and it follows changes made there), otherwise
-- the game's own.
local function eui(fn, ...)
  local E = _G.EllesmereUI
  if E and type(E[fn]) == "function" then
    local ok, v = pcall(E[fn], ...)
    if ok then return v end
  end
end

function JB:FontPath()
  local path = eui("GetFontPath")
  if type(path) == "string" and path ~= "" then return path end
  path = GameFontNormal and GameFontNormal:GetFont()
  return path or STANDARD_TEXT_FONT
end

function JB:FontFlags()
  local flag = eui("GetFontOutlineFlag")
  return type(flag) == "string" and flag or ""
end

function JB:FontShadow()
  local shadow = eui("GetFontUseShadow")
  if shadow ~= nil then return shadow and true or false end
  return self.Theme and self:Theme().shadow or false
end

-- A drop shadow only shows when it comes from a font object, so every string is given one of
-- these first (with or without a shadow), then its typeface.
local fontObjects
local function fontObject(shadow)
  if not CreateFont then return nil end
  if not fontObjects then
    fontObjects = { [true] = CreateFont("CassetteShadowFont"), [false] = CreateFont("CassettePlainFont") }
    for on, obj in pairs(fontObjects) do
      obj:SetFont(STANDARD_TEXT_FONT, 12, "")
      obj:SetShadowOffset(on and 1 or 0, on and -1 or 0)
      obj:SetShadowColor(0, 0, 0, on and 0.9 or 0)
    end
  end
  return fontObjects[shadow and true or false]
end

-- Every piece of text registers here, so a font change reaches all of it.
local fonts = {}
function JB:SetFont(fs, size)
  fonts[fs] = size
  local obj = fontObject(self:FontShadow())
  if obj and fs.SetFontObject then pcall(fs.SetFontObject, fs, obj) end
  local ok, res = pcall(fs.SetFont, fs, self:FontPath(), size, self:FontFlags())
  if not ok or res == false then pcall(fs.SetFont, fs, STANDARD_TEXT_FONT, size, "") end
  -- text already showing keeps the width measured for the old font (or no shadow), so its last
  -- letter or two would wrap: set it again to measure it afresh
  if fs.GetObjectType and fs:GetObjectType() == "FontString" then
    local text = fs:GetText()
    if text and text ~= "" then
      fs:SetText("")
      fs:SetText(text)
    end
  end
end

function JB:ApplyFonts()
  for fs, size in pairs(fonts) do self:SetFont(fs, size) end
end

-- The accent, lighter (under the mouse).
function JB:AccentLight()
  local r, g, b = self:Accent()
  return r + (1 - r) * 0.35, g + (1 - g) * 0.35, b + (1 - b) * 0.35
end

-- Seconds into the song now. `raw` doesn't stop at the song's end.
function JB:Position(raw)
  local s = self.state
  local p = s.position
  if s.playing then p = p + (GetTime() - s.anchor) end
  if not raw and s.duration > 0 and p > s.duration then p = s.duration end
  return p
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("ADDON_LOADED")
ev:RegisterEvent("PLAYER_ENTERING_WORLD")
ev:RegisterEvent("PLAYER_LOGOUT")
ev:SetScript("OnEvent", function(_, event, a1, a2)
  if event == "ADDON_LOADED" and a1 == ADDON then
    CassetteDB = CassetteDB or {}
    for k, v in pairs(DEFAULTS) do
      if CassetteDB[k] == nil then CassetteDB[k] = v end
    end
    JB.db = CassetteDB
  elseif event == "PLAYER_ENTERING_WORLD" and not JB.started then
    JB.started = true
    if not JB.db.theme then JB.db.theme = _G.EllesmereUI and "ellesmere" or "classic" end
    -- EllesmereUI's font changed: follow it
    local E = _G.EllesmereUI
    if E and type(E.InvalidateFontCache) == "function" and hooksecurefunc then
      hooksecurefunc(E, "InvalidateFontCache", function()
        C_Timer.After(0.5, function() if JB.widget then JB:ApplyLook() end end)
      end)
    end
    -- a fresh login (a1: isInitialLogin; not a /reload) with "hide when no music": hidden until
    -- music plays (ApplyRecord) or the button brings it up. Never before the setup is done.
    if a1 and JB.db.hideIdle and JB.db.setupDone then
      JB.db.shown, JB.db.autoShow = false, true
    end
    JB:StartLive(a2)  -- a2: isReloadingUi
    JB:CreateWidget()
    if JB.StartDuck then JB:StartDuck() end  -- Duck.lua (a new file may need a full restart)
    if JB.StartSetup then JB:StartSetup() end  -- shows the first-setup window when it's needed
  elseif event == "PLAYER_LOGOUT" then
    JB:SaveCursors()
  end
end)

SLASH_CASSETTE1 = "/cassette"
SLASH_CASSETTE2 = "/tape"
SlashCmdList.CASSETTE = function(input)
  local cmd, arg = (input or ""):lower():match("^%s*(%S*)%s*(.-)%s*$")
  local db = JB.db
  if cmd == "" then
    JB:ToggleShown()
  elseif cmd == "options" or cmd == "config" or cmd == "settings" then
    if JB.ToggleOptions then JB:ToggleOptions() else JB:Print("restart WoW once to finish installing the options.") end
  elseif cmd == "setup" then
    JB.setupPreview = (arg == "new" or arg == "preview") or nil   -- as a new player sees it
    if JB.ShowSetup then
      if JB.setup and JB.setup:IsShown() then JB:RefreshSetup() end
      JB:ShowSetup()
    else JB:Print("restart WoW once to finish installing the setup window.") end
  elseif cmd == "update" then     -- a new version of the app on the PC (Live.lua)
    JB:UpdateApp()
  elseif cmd == "showcase" then   -- screenshots for the download pages (see Options.lua)
    if JB.Showcase then JB:Showcase(arg ~= "" and arg or nil) end
  elseif cmd == "lock" or cmd == "unlock" then
    db.locked = cmd == "lock"
    JB:Print(db.locked and "locked in place." or "unlocked: drag it to move it.")
  elseif cmd == "reset" then
    db.point, db.scale = DEFAULTS.point, 1
    JB:ApplyLook()
    JB:Print("back to its default place and size.")
  elseif cmd == "scale" and tonumber(arg) then
    db.scale = math.max(0.5, math.min(2.5, tonumber(arg)))
    JB:ApplyLook()
  elseif (cmd == "duck" or cmd == "dip") and JB.DUCK_SOURCES and arg:match("^%a+ o[nf]f?$") then
    -- /tape duck chatter on: choose which of Spoken's parts dip the music
    local key, onoff = arg:match("^(%a+) (o[nf]f?)$")
    if JB.DUCK_SOURCES[key] == nil then
      JB:Print("Spoken's parts: quests, gossip, readables, places, bosses, chatter.")
      return
    end
    db.duckSources = db.duckSources or {}
    db.duckSources[key] = onoff == "on"
    JB:UpdateDuck()
    JB:Print(("%s %s the music."):format(key, onoff == "on" and "dips" or "no longer dips"))
  elseif cmd == "duck" or cmd == "dip" then
    if tonumber(arg) then
      JB:SetDuckLevel(tonumber(arg))
      db.duck = true
    elseif arg == "on" or arg == "off" then
      db.duck = arg == "on"
    else
      db.duck = not db.duck
    end
    JB:UpdateDuck()
    JB:Print(db.duck and ("music dips to %d%% while Spoken reads."):format(db.duckLevel)
      or "music no longer dips while Spoken reads.")
  elseif cmd == "debug" then
    -- what the bar's parts are doing, for troubleshooting
    local f, s = JB.widget, JB.state
    if f then
      local font, size = f.volText:GetFont()
      JB:Print(("volume text %q shown %s alpha %.2f font %s %s; bar shown %s"):format(
        tostring(f.volText:GetText()), tostring(f.volText:IsShown()), f.volText:GetAlpha() or -1,
        tostring(font), tostring(size), tostring(f:IsShown())))
      JB:Print(("state: art %d shown %s, volume %s, playing %s, connected %s"):format(
        s.art, tostring(f.shownArt), tostring(s.volume), tostring(s.playing), tostring(s.connected)))
    end
  elseif cmd == "status" then
    local s = JB.state
    JB:Print(("session %d, mail %d/%d, record %d/%d, art %d/%d; %s, %s %s"):format(
      JB.nonce, JB.mailCursor, JB.MAIL, JB.nextRecord, JB.RECORDS, JB.nextArt, JB.ART,
      s.connected and "companion answering" or "companion not answering", JB:MusicName(),
      s.available and (s.playing and "playing" or "paused") or "not open"))
    local st = JB.stats
    if st then
      JB:Print(("file reads: %d, slow (over 1 s): %d, gave up: %d, slowest: %.1f s; slow frames: %d"):format(
        st.reads, st.slow, st.failed, st.slowest, st.hitches or 0))
    end
    if JB.HasSpoken then
      local parts = {}
      for _, key in ipairs({ "quests", "gossip", "readables", "places", "bosses", "chatter" }) do
        if JB:DipsFor(key) then parts[#parts + 1] = key end
      end
      JB:Print(("dip while Spoken reads: %s (%d%%)%s; for %s; Spoken %s"):format(db.duck and "on" or "off",
        db.duckLevel, JB.ducked and ", dipped now" or "", table.concat(parts, ", "),
        JB:HasSpoken() and "found" or "not loaded"))
    end
  else
    JB:Print("/tape options  |  /tape setup  (/tape setup new: as a new player sees it)  |  /tape  show or hide  |  /tape reset  |  /tape status")
    JB:Print("/tape duck  dip on or off  |  /tape duck 30  how low the music goes (% of your volume)")
    JB:Print("/tape duck chatter on  which of Spoken's parts dip it (quests, gossip, readables, places, bosses, chatter)")
  end
end
