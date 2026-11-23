-- The bar: cover, song and artist (pictures drawn by the companion), controls, progress.
--
-- Its parts are made once; a layout (JB.LAYOUTS) places, sizes and shows them, so switching
-- layout in the options is instant. The companion draws the cover at the layout's size (it's
-- told with the LOOK message) and the text strips 16 and 14 units high (render.py), so all
-- layouts use those text heights.
--
--  bar             [ART] Title             |< || >|  - 70 +  =
--                  [   ] Artist                         1:42 / 3:05
--                        ===========---------------------------
--
--  stacked         [ART] Title             stacked (controls above) has the
--  (controls       [   ] Artist      1:42  controls row on top instead
--   below)         =========-------------
--                  =     |<  ||  >|  - 70 +
--
--  slim            [a] Title ...    |< || >|  =     (one thin line)
--
--  card            [   big cover   ]
--                  Title / Artist / progress / controls

local _, JB = ...

local M = JB.MEDIA
local TITLE_H, ARTIST_H = 16, 14   -- render.TITLE_UNITS / ARTIST_UNITS

local function tip(owner, text)
  owner:HookScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    GameTooltip:SetText(text, 1, 1, 1)
    GameTooltip:Show()
  end)
  owner:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

-- an icon in the theme's colours (UI.lua), with a tooltip
local function iconButton(parent, icon, size, onClick, text, colour)
  local b = JB.UI.Icon(parent, icon, size, onClick, colour)
  if text then tip(b, text) end
  return b
end

-- A clipped line holding one text picture, which scrolls back and forth when it's too long.
local function textLine(parent)
  local clip = CreateFrame("Frame", nil, parent)
  clip:SetClipsChildren(true)
  clip.tex = clip:CreateTexture(nil, "ARTWORK")
  clip.tex:SetPoint("LEFT", clip, "LEFT", 0, 0)
  clip.width, clip.offset, clip.phase, clip.timer = 0, 0, "hold", 0
  return clip
end

local function scrollLine(line, elapsed)
  local over = line.width - line:GetWidth()
  if over <= 0.5 then
    if line.offset ~= 0 then
      line.offset = 0
      line.tex:SetPoint("LEFT", line, "LEFT", 0, 0)
    end
    return
  end
  line.timer = line.timer + elapsed
  if line.phase == "hold" then
    if line.timer > 2.5 then line.phase, line.timer = "move", 0 end
  elseif line.phase == "move" then
    line.offset = math.min(over, line.offset + elapsed * 20)
    if line.offset >= over then line.phase, line.timer = "end", 0 end
  elseif line.timer > 2 then
    line.phase, line.timer, line.offset = "hold", 0, 0
  end
  line.tex:SetPoint("LEFT", line, "LEFT", -line.offset, 0)
end

local function clock(sec)
  sec = math.max(0, math.floor(sec))
  return ("%d:%02d"):format(math.floor(sec / 60), sec % 60)
end

local function put(el, point, rel, relPoint, x, y)
  el:ClearAllPoints()
  el:SetPoint(point, rel, relPoint, x, y)
end

-- the progress bar: a line across, `y` units up from the bottom (or down from the top if top)
local function bar(f, left, right, y, top)
  f.barBg:ClearAllPoints()
  local p = top and "TOP" or "BOTTOM"
  f.barBg:SetPoint(p .. "LEFT", f, p .. "LEFT", left, y)
  f.barBg:SetPoint(p .. "RIGHT", f, p .. "RIGHT", -right, y)
end

--------------------------------------------------------------------------------
-- Layouts
--------------------------------------------------------------------------------

local LAYOUTS = {
  bar = {
    name = "Bar", w = 360, h = 48, cover = 40,
    place = function(f)
      put(f.cover, "TOPLEFT", f, "TOPLEFT", 4, -4)
      put(f.title, "TOPLEFT", f, "TOPLEFT", 50, -5)
      f.title:SetSize(128, TITLE_H)
      put(f.artist, "TOPLEFT", f, "TOPLEFT", 50, -22)
      f.artist:SetSize(214, ARTIST_H)
      put(f.controls, "LEFT", f, "TOPLEFT", 186, -13)
      put(f.volume, "LEFT", f.controls, "RIGHT", 14, 0)
      put(f.list, "LEFT", f.volume, "RIGHT", 7, 0)
      put(f.time, "RIGHT", f, "TOPRIGHT", -7, -29)
      bar(f, 50, 7, 6)
      return { artist = true, volume = true, time = true, status = 214 }
    end,
  },
  stackedBelow = {
    name = "Stacked, controls below", w = 236, h = 98, cover = 48,
    place = function(f)
      put(f.cover, "TOPLEFT", f, "TOPLEFT", 6, -6)
      put(f.title, "TOPLEFT", f, "TOPLEFT", 62, -9)
      f.title:SetSize(166, TITLE_H)
      put(f.artist, "TOPLEFT", f, "TOPLEFT", 62, -27)
      f.artist:SetSize(124, ARTIST_H)
      put(f.time, "RIGHT", f, "TOPRIGHT", -7, -34)
      bar(f, 6, 6, -62, true)
      put(f.controls, "CENTER", f, "TOP", 0, -80)
      put(f.volume, "RIGHT", f, "TOPRIGHT", -6, -80)
      put(f.list, "LEFT", f, "TOPLEFT", 8, -80)
      return { artist = true, volume = true, time = true, status = 166 }
    end,
  },
  stackedAbove = {
    name = "Stacked, controls above", w = 236, h = 92, cover = 48,
    place = function(f)
      put(f.controls, "CENTER", f, "TOP", 0, -16)
      put(f.volume, "RIGHT", f, "TOPRIGHT", -6, -16)
      put(f.list, "LEFT", f, "TOPLEFT", 8, -16)
      put(f.cover, "TOPLEFT", f, "TOPLEFT", 6, -32)
      put(f.title, "TOPLEFT", f, "TOPLEFT", 62, -35)
      f.title:SetSize(166, TITLE_H)
      put(f.artist, "TOPLEFT", f, "TOPLEFT", 62, -53)
      f.artist:SetSize(124, ARTIST_H)
      put(f.time, "RIGHT", f, "TOPRIGHT", -7, -60)
      bar(f, 6, 6, 4)
      return { artist = true, volume = true, time = true, status = 166 }
    end,
  },
  slim = {
    name = "Slim", w = 300, h = 26, cover = 22,
    place = function(f)
      put(f.cover, "TOPLEFT", f, "TOPLEFT", 2, -2)
      put(f.list, "RIGHT", f, "RIGHT", -5, 1)
      put(f.controls, "RIGHT", f.list, "LEFT", -10, 0)
      put(f.title, "LEFT", f, "LEFT", 30, 1)
      f.title:SetSize(150, TITLE_H)
      bar(f, 26, 2, 1)
      return { artist = false, volume = false, time = false, status = 170 }
    end,
  },
  card = {
    name = "Card", w = 200, h = 270, cover = 188,
    place = function(f)
      put(f.cover, "TOPLEFT", f, "TOPLEFT", 6, -6)
      put(f.title, "TOPLEFT", f, "TOPLEFT", 8, -200)
      f.title:SetSize(184, TITLE_H)
      put(f.artist, "TOPLEFT", f, "TOPLEFT", 8, -218)
      f.artist:SetSize(140, ARTIST_H)
      put(f.time, "RIGHT", f, "TOPRIGHT", -7, -225)
      bar(f, 6, 6, -238, true)
      put(f.controls, "CENTER", f, "TOP", 0, -255)
      put(f.volume, "RIGHT", f, "TOPRIGHT", -6, -255)
      put(f.list, "LEFT", f, "TOPLEFT", 8, -255)
      return { artist = true, volume = true, time = true, status = 184 }
    end,
  },
}
JB.LAYOUTS = LAYOUTS
JB.LAYOUT_ORDER = { "bar", "stackedBelow", "stackedAbove", "slim", "card" }

local function layout()
  return LAYOUTS[JB.db.layout] or LAYOUTS.bar
end

--------------------------------------------------------------------------------
-- Building, placing, looks
--------------------------------------------------------------------------------

function JB:PlaceWidget()
  local f = self.widget
  if not f then return end
  local p = self.db.point
  f:SetScale(self.db.scale)
  f:ClearAllPoints()
  f:SetPoint(p[1], UIParent, p[3], p[4], p[5])
  if self.PlaceBrowser then self:PlaceBrowser() end
end

-- Layout, size, theme, colours, font: after any change in the options.
function JB:ApplyLook()
  local f = self.widget
  if not f then return end
  local L, T = layout(), self:Theme()
  f:SetSize(L.w, L.h)
  f.cover:SetSize(L.cover, L.cover)
  local shows = L.place(f)
  f.layoutShows = shows
  f.volume:SetShown(shows.volume)
  f.time:SetShown(shows.time)
  f.status:SetWidth(shows.status)
  f.sub:SetWidth(shows.status)
  JB.UI.Skin(f, "bar", self.db.bgAlpha or 0.88)
  local P = T.progress
  f.barBg:SetColorTexture(P.bg[1], P.bg[2], P.bg[3], P.bg[4])
  f.barBg:SetHeight(P.h)
  if P.texture then
    f.bar:SetTexture(P.texture)
    f.bar:SetVertexColor(self:Accent())
  else
    f.bar:SetColorTexture(self:Accent())
    f.bar:SetVertexColor(1, 1, 1, 1)
  end
  self:ApplyFonts()
  JB.UI.RefreshAll()   -- colours (a font change can reset them) and the open windows' looks
  self:PlaceWidget()
  self:SendLook()
  if self.ApplyBrowserLook then self:ApplyBrowserLook() end
  self:RefreshWidget()
end

-- Tell the companion the cover size, accent colour, theme and font, so its pictures match. Only
-- when something changed: each message is a flash in the corner.
function JB:SendLook()
  local r, g, b = self:Accent()
  local arg = ("%d %d %d %d %s %s"):format(layout().cover, r * 255 + 0.5, g * 255 + 0.5, b * 255 + 0.5,
    self:ThemeKey(), self:FontPath())
  if arg ~= self.lookSent then
    self.lookSent = arg
    self:Send("LOOK", arg)
  end
end

function JB:CreateWidget()
  local f = CreateFrame("Frame", "CassetteWidget", UIParent)
  self.widget = f
  f:SetFrameStrata("MEDIUM")
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  -- (its background and border are the theme's: JB.UI.Skin in ApplyLook)

  f.cover = f:CreateTexture(nil, "ARTWORK")
  f.cover:SetColorTexture(0.15, 0.15, 0.17, 1)
  f.title = textLine(f)
  f.artist = textLine(f)

  -- status lines, shown instead of the song when there's something to say
  f.status = f:CreateFontString(nil, "OVERLAY")
  self:SetFont(f.status, 12)
  f.status:SetPoint("LEFT", f.title, "LEFT", 1, 0)
  f.status:SetJustifyH("LEFT")
  JB.UI.Role(f.status, "text")
  f.sub = f:CreateFontString(nil, "OVERLAY")
  self:SetFont(f.sub, 10.5)
  f.sub:SetPoint("LEFT", f.artist, "LEFT", 1, 0)
  f.sub:SetJustifyH("LEFT")
  JB.UI.Role(f.sub, "dim")

  -- shuffle / previous / play / next, together
  f.controls = CreateFrame("Frame", nil, f)
  f.controls:SetSize(86, 20)
  f.shuffle = iconButton(f.controls, "shuffle", 13, function()
    local s = self.state
    s.shuffle = not s.shuffle   -- show it straight away; the companion confirms
    self:RefreshWidget()
    if self.RefreshBrowser then self:RefreshBrowser() end
    self:Command("S")
  end, "Shuffle", function(hover)
    if not self.state.shuffle then return nil end
    if hover then return self:AccentLight() end
    return self:Accent()
  end)
  f.shuffle:SetPoint("LEFT")
  f.prev = iconButton(f.controls, "prev", 16, function() self:Command("B") end, "Previous")
  f.prev:SetPoint("LEFT", f.shuffle, "RIGHT", 8, 0)
  f.play = iconButton(f.controls, "play", 20, function()
    local s = self.state
    s.position, s.anchor = self:Position(), GetTime()
    s.playing = not s.playing   -- show it straight away; the companion confirms
    self:RefreshWidget()
    self:Command("P")
  end, "Play / pause")
  f.play:SetPoint("LEFT", f.prev, "RIGHT", 6, 0)
  f.next = iconButton(f.controls, "next", 16, function() self:Command("N") end, "Next")
  f.next:SetPoint("LEFT", f.play, "RIGHT", 6, 0)

  -- volume: - 70 +, together
  local function nudge(dir)
    local s = self.state
    s.volume = math.max(0, math.min(100, s.volume + dir * 5))
    if dir > 0 then s.muted = false end
    self:RefreshWidget()
    self:Command(dir > 0 and "VU" or "VD")
  end
  f.volume = CreateFrame("Frame", nil, f)
  f.volume:SetSize(50, 16)
  f.volDown = iconButton(f.volume, "minus", 12, function() nudge(-1) end, "Quieter")
  f.volDown:SetPoint("LEFT")
  f.volText = f.volume:CreateFontString(nil, "OVERLAY")
  self:SetFont(f.volText, 11)
  f.volText:SetPoint("CENTER", f.volDown, "RIGHT", 13, 0)
  f.vol = CreateFrame("Button", nil, f.volume)
  f.vol:SetSize(24, 16)
  f.vol:SetPoint("LEFT", f.volDown, "RIGHT", 1, 0)
  f.vol:RegisterForClicks("LeftButtonUp")
  f.vol.text = f.volText
  f.vol:SetScript("OnClick", function()
    self.state.muted = not self.state.muted
    self:RefreshWidget()
    self:Command("M")
  end)
  tip(f.vol, "Spotify's volume (click to mute)\nPurple: dipped while Spoken reads")
  f.volUp = iconButton(f.volume, "plus", 12, function() nudge(1) end, "Louder")
  f.volUp:SetPoint("LEFT", f.vol, "RIGHT", 1, 0)

  f.list = iconButton(f, "list", 15, function()
    if self.ToggleBrowser then
      self:ToggleBrowser()
    else  -- Browser.lua is new: some clients only load new files after a full restart
      self:Print("restart WoW once to finish installing the browser.")
    end
  end, "Your music: playlists, liked songs, search")

  f.time = f:CreateFontString(nil, "OVERLAY")
  self:SetFont(f.time, 10.5)
  f.time:SetJustifyH("RIGHT")
  JB.UI.Role(f.time, "dim")

  f.barBg = f:CreateTexture(nil, "ARTWORK")
  f.bar = f:CreateTexture(nil, "OVERLAY")
  f.bar:SetPoint("TOPLEFT", f.barBg, "TOPLEFT")
  f.bar:SetPoint("BOTTOMLEFT", f.barBg, "BOTTOMLEFT")
  f.bar:SetWidth(0.01)

  -- moving (unless locked), options on right-click
  f:SetScript("OnDragStart", function() if not self.db.locked then f:StartMoving() end end)
  f:SetScript("OnDragStop", function()
    f:StopMovingOrSizing()
    local p, _, rp, x, y = f:GetPoint()
    self.db.point = { p, "UIParent", rp, x, y }
    if self.PlaceBrowser then self:PlaceBrowser() end
  end)
  f:SetScript("OnMouseUp", function(_, button)
    if button == "RightButton" then
      if self.ToggleOptions then self:ToggleOptions() end
    end
  end)
  tip(f, "Cassette\nDrag to move, right-click for options")

  local acc = 0
  f:SetScript("OnUpdate", function(_, elapsed)
    scrollLine(f.title, elapsed)
    scrollLine(f.artist, elapsed)
    acc = acc + elapsed
    if acc < 0.1 then return end
    acc = 0
    self:UpdateProgress()
    if f.statusShown then self:RefreshWidget() end  -- "Connecting..." turns into advice after a while
  end)

  local ev = CreateFrame("Frame")
  pcall(ev.RegisterEvent, ev, "DISPLAY_SIZE_CHANGED")
  pcall(ev.RegisterEvent, ev, "UI_SCALE_CHANGED")
  ev:SetScript("OnEvent", function()
    JB.UI.Skin(f, "bar", self.db.bgAlpha or 0.88)   -- hairlines stay one pixel
    self:Send("H")  -- new pixels per unit: the companion redraws the text to stay sharp
  end)

  self:ApplyLook()
end

function JB:ShowArt(a, paths, sizes)
  local f = self.widget
  if not f or a ~= self.state.art then return end
  local ppu = self:PPU100() / 100
  f.cover:SetTexture(paths[1])
  f.cover:SetTexCoord(0, 1, 0, 1)
  for i, line in ipairs({ f.title, f.artist }) do
    local w, h = sizes[i + 1][1] / ppu, sizes[i + 1][2] / ppu
    line.tex:SetTexture(paths[i + 1])
    line.tex:SetSize(w, h)
    line.width, line.offset, line.phase, line.timer = w, 0, "hold", 0
    line.tex:SetPoint("LEFT", line, "LEFT", 0, 0)
  end
  f.shownArt = a
  self:RefreshWidget()
end

local function statusText(s)
  if s.exhausted then
    return "Type /reload to keep it live", "Cassette has used its files for this session"
  end
  if not s.connected then
    if s.everConnected then return "Companion isn't answering", "Is the Cassette companion still running?" end
    if GetTime() - JB.startTime < 15 then return "Connecting to Cassette...", "" end
    return "Start the Cassette companion", "then /reload if WoW was already open"
  end
  if not s.available then return "Spotify isn't open", "Press play to open it" end
  if s.art == 0 then return "Nothing playing", "" end
  if not JB.widget.shownArt then return "Loading...", "" end
  return nil
end

function JB:UpdateProgress()
  local f, s = self.widget, self.state
  if not f then return end
  if s.duration > 0 and not f.statusShown then
    local pos = self:Position()
    f.time:SetText(clock(pos) .. " / " .. clock(s.duration))
    f.bar:SetWidth(math.max(0.01, f.barBg:GetWidth() * math.min(1, pos / s.duration)))
  else
    f.time:SetText("")
    f.bar:SetWidth(0.01)
  end
end

function JB:RefreshWidget()
  local f, s = self.widget, self.state
  if not f then return end
  f:SetShown(self.db.shown)
  local shows = f.layoutShows or {}
  local line1, line2 = statusText(s)
  f.statusShown = line1 ~= nil
  f.status:SetText(line1 or "")
  f.sub:SetText(shows.artist and line2 or "")
  f.title:SetShown(not line1)
  f.artist:SetShown(not line1 and shows.artist == true)
  if line1 and not f.shownArt then f.cover:SetColorTexture(0.15, 0.15, 0.17, 1) end
  f.cover:SetDesaturated(line1 ~= nil)
  f.play.icon:SetTexture(M .. (s.playing and "pause" or "play"))
  f.shuffle:Paint()
  if s.muted then
    f.volText:SetText("mute")
    f.volText:SetTextColor(0.9, 0.45, 0.45)
  else
    f.volText:SetText(tostring(s.volume))
    if self.ducked then
      f.volText:SetTextColor(0.71, 0.55, 1)   -- Spoken's purple: dipped while it reads
    else
      f.volText:SetTextColor(self:Colour("icon"))
    end
  end
  if self.RefreshSetup then self:RefreshSetup() end
  if self.RefreshOptionsStatus then self:RefreshOptionsStatus() end
  self:UpdateProgress()
end
