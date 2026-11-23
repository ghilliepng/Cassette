-- The first-setup window: shown once, the first time Cassette loads (and any time with /tape setup).
-- It checks things off as they happen: the companion answering, the Spotify account connected.
-- Step 2 is the music app: Spotify, YouTube Music or Apple Music (Spotify's account for Spotify).

local _, JB = ...

local UI = JB.UI
local W, H = 420, 380   -- H: until LayoutSetup fits it to what's showing

-- Where players get the companion. Set this before publishing.
JB.COMPANION_URL = "https://github.com/ghilliepng/Cassette/releases/latest"

-- A step: tick, heading and text. Placed by RefreshSetup, right under the step before it.
local function line(parent, title)
  local head = UI.Text(parent, 13)
  head:SetText(title)
  local mark = parent:CreateTexture(nil, "ARTWORK")
  mark:SetSize(16, 16)
  mark:SetPoint("TOPRIGHT", head, "TOPLEFT", -8, 1)
  local body = UI.Text(parent, 11.5, "dim")
  body:SetPoint("TOPLEFT", head, "BOTTOMLEFT", 0, -4)
  body:SetWidth(W - 56)
  body:SetSpacing(3)
  return mark, body, head
end

-- Text height, wrapped (falls back to one line if the game can't say yet); a frame's own height
local function height(fs, lines)
  if not fs.GetStringHeight then return fs:GetHeight() end
  local h = fs:GetStringHeight()
  return (h and h > 0) and h or 14 * (lines or 1)
end

local function tick(mark, ok)
  if ok then
    mark:SetTexture(JB.MEDIA .. "check")
    mark:SetVertexColor(JB:Accent())
  else
    mark:SetTexture(JB.MEDIA .. "dot")
    mark:SetVertexColor(0.5, 0.5, 0.55)
  end
end

function JB:CreateSetup()
  local f = UI.Window("CassetteSetup", W, H, "Welcome to Cassette")
  self.setup = f
  local intro = UI.Text(f, 11.5, "dim")
  intro:SetPoint("TOPLEFT", 16, -36)
  intro:SetWidth(W - 32)
  intro:SetText("Your music in a compact player: the song, its cover and the controls, live in the game.")
  f.intro = intro

  -- 1. the companion
  f.companionMark, f.companionText, f.companionHead = line(f, "1. Set up the Cassette companion on your PC")
  local url = CreateFrame("EditBox", nil, f)
  f.url = url
  url:SetSize(W - 56, 20)
  url:SetPoint("TOPLEFT", f.companionText, "BOTTOMLEFT", 0, -6)
  url:SetAutoFocus(false)
  JB:SetFont(url, 11)
  url:SetTextColor(0.95, 0.95, 0.95)
  url:SetTextInsets(6, 6, 0, 0)
  local urlBg = url:CreateTexture(nil, "BACKGROUND")
  urlBg:SetAllPoints()
  urlBg:SetColorTexture(1, 1, 1, 0.06)
  url:SetText(JB.COMPANION_URL)
  url:SetScript("OnEditFocusGained", function() url:HighlightText() end)
  url:SetScript("OnTextChanged", function(_, user) if user then url:SetText(JB.COMPANION_URL) end end)
  url:SetScript("OnEscapePressed", function() url:ClearFocus() end)

  -- 2. the music app, and Spotify's account (the step's text under the choice)
  f.spotifyMark, f.spotifyText, f.spotifyHead = line(f, "2. Choose your music app")
  f.music = CreateFrame("Frame", nil, f)
  f.music:SetPoint("TOPLEFT", f.spotifyHead, "BOTTOMLEFT", 0, -4)
  f.musicChoice = JB:MusicChoice(f.music, W - 56)
  f.musicChoice:SetPoint("TOPLEFT", f.music, "TOPLEFT", 0, 0)
  f.spotifyText:ClearAllPoints()
  f.spotifyText:SetPoint("TOPLEFT", f.musicChoice, "BOTTOMLEFT", 0, -8)
  f.spotifyButton = UI.Button(f.music, "Set up on PC", 110, function()
    JB:Command("SETUP")
    JB:Print("the Connect Spotify window is open on your PC (Alt+Tab if it's behind the game).")
  end, true)
  f.spotifyButton:SetPoint("TOPLEFT", f.spotifyText, "BOTTOMLEFT", 0, -8)

  -- 3. Spoken
  f.spokenMark, f.spokenText, f.spokenHead = line(f, "3. Reduce volume during NPC dialogue (Spoken)")
  f.spokenCheck = UI.Check(f, "Reduce volume while Spoken reads NPC dialogue",
    function() return JB.db.duck end, function(v) JB.db.duck = v; JB:UpdateDuck() end)
  f.spokenCheck:SetPoint("TOPLEFT", f.spokenText, "BOTTOMLEFT", 0, -6)

  -- 4. looks
  f.lookMark, f.lookText, f.lookHead = line(f, "4. Choose your look")
  f.looks = CreateFrame("Frame", nil, f)
  f.looks:SetPoint("TOPLEFT", f.lookText, "BOTTOMLEFT", 0, -8)
  local theme = JB:ThemeChoice(f.looks, W - 56)
  theme:SetPoint("TOPLEFT", f.looks, "TOPLEFT", 0, 0)
  local style = JB:StyleChoice(f.looks, W - 56)
  style:SetPoint("TOPLEFT", theme, "BOTTOMLEFT", 0, -10)
  f.looks:SetSize(W - 56, theme:GetHeight() + 10 + style:GetHeight())

  local done = UI.Button(f, "Done", 90, function()
    JB.db.setupDone = true
    f:Hide()
  end, true)
  done:SetPoint("BOTTOMRIGHT", -16, 16)
  local options = UI.Button(f, "Options", 90, function()
    JB.db.setupDone = true
    f:Hide()
    JB:ToggleOptions()
  end)
  options:SetPoint("RIGHT", done, "LEFT", -8, 0)

  f:SetScript("OnShow", function() JB:RefreshSetup() end)
  f:SetScript("OnHide", function() JB.setupPreview = nil end)
end

function JB:RefreshSetup()
  local f = self.setup
  if not f or not f:IsShown() then return end
  local s = self.state
  local connected, account = s.connected, s.account
  if self.setupPreview then connected, account = false, false end   -- /tape setup new
  tick(f.companionMark, connected)
  if connected then
    f.companionText:SetText("Companion is installed: Cassette can show and control your music.")
    f.url:Hide()
  else
    f.companionText:SetText("A small program that talks to your music app for the game. Get it here, start it, then "
      .. "type /reload (if it's running already, give it a moment):")
    f.url:Show()
  end
  local spotify = self:IsSpotify()
  tick(f.spotifyMark, (not spotify and connected) or account)
  if spotify then
    f.spotifyText:SetText(account and "Connected: browse your playlists, liked songs and search with the = button."
      or "The controls work with any account. To browse your playlists, liked songs and search here, "
      .. "connect it (Spotify allows this with Premium):")
  elseif self:MusicApp() == "youtube" then
    f.spotifyText:SetText("Play it in your browser, in YouTube Music's installed app or in a YouTube Music "
      .. "desktop app. In a browser, the volume is the whole browser's. Playlists and search are Spotify's only, for now.")
  else
    f.spotifyText:SetText("Play it in the Apple Music app (or iTunes). Playlists and search are Spotify's only, for now.")
  end
  f.spotifyButton:SetShown(spotify and (connected or self.setupPreview) and not account and true or false)
  local spoken = self.HasSpoken and self:HasSpoken()
  tick(f.spokenMark, spoken and self.db.duck)
  f.spokenText:SetText(spoken and "Spoken is installed: the music turns down while it reads NPC dialogue, and back up after."
    or "Needs the Spoken addon, which reads NPC dialogue aloud. With it, the music turns down while it reads.")
  f.spokenCheck:SetShown(spoken and true or false)
  tick(f.lookMark, true)
  f.lookText:SetText("Change these any time: right-click the player for its options.")
  self:LayoutSetup()
end

-- Stack the steps with no gaps: each one starts under the last thing showing in the one before,
-- and the window is as tall as what's in it.
function JB:LayoutSetup()
  local f = self.setup
  local y = -36 - height(f.intro, 2) - 16
  local steps = {
    { f.companionHead, f.companionText, f.url, 6 },
    { f.spotifyHead, f.music, false, 0 },   -- (a box: the choice, its text and the button)
    { f.spokenHead, f.spokenText, f.spokenCheck, 6 },
    { f.lookHead, f.lookText, f.looks, 8 },
  }
  local box = f.musicChoice:GetHeight() + 8 + height(f.spotifyText, 2)
  if f.spotifyButton:IsShown() then box = box + 8 + f.spotifyButton:GetHeight() end
  f.music:SetSize(W - 56, box)
  for _, st in ipairs(steps) do
    local head, body, extra, gap = st[1], st[2], st[3], st[4]
    head:ClearAllPoints()
    head:SetPoint("TOPLEFT", f, "TOPLEFT", 40, y)
    y = y - height(head) - 4 - height(body, 2)
    if extra and extra:IsShown() then y = y - gap - extra:GetHeight() end
    y = y - 18
  end
  f:SetHeight(-y + 36)
end

function JB:ShowSetup()
  if not self.setup then self:CreateSetup() end
  self.setup:Show()
end

-- At login: the first time ever, show it once the companion has had a moment to answer.
function JB:StartSetup()
  if self.db.setupDone then return end
  C_Timer.After(4, function()
    if not self.db.setupDone then self:ShowSetup() end
  end)
end
