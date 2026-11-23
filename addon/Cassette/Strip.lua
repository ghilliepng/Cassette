-- Game -> PC: short messages drawn as a one-pixel-high line in the screen's top-left corner, for
-- a moment, which the companion reads off the screen about 20 times a second.
--
-- Each pixel's colour channels are fully on or off (3 bits a pixel). Pixels 1-2 are markers
-- (cyan, yellow), then the bytes: sequence number, length, checksum, data. The checksum is
-- sequence, length and data bytes, each weighted by position, mod 255: any one wrong bit
-- changes it. (In-game tests showed single pixels land exactly where they're put.)
--
-- Data: seven 16-bit numbers (high byte first) - the time (time() mod 65536), the session
-- number, and where the addon is in the file pools: next mail, record, art and view, then the
-- widget's screen pixels per UI unit x100 - followed by the command as text ("N", "PL 12 3",
-- "FD linkin park"). A click is about 45 pixels long; it shows for 0.15 s.
--
-- The companion drops messages older than a few seconds (drawn while WoW was covered). The time
-- and mail number also anchor the addon's reading pace (Live.lua), so the companion knows where
-- it is reading without being told again.

local _, JB = ...

local MAXLEN = 120  -- bytes of data
local strip, pixels, unit, seq = nil, {}, 1, 0
local queue, showing, gen = {}, false, 0

local function place()
  if not strip then return end
  local _, h = GetPhysicalScreenSize()
  unit = 768 / ((h and h > 0) and h or 768)   -- one screen pixel, in the strip's units
  for i, t in ipairs(pixels) do
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", strip, "TOPLEFT", (i - 1) * unit, 0)
    t:SetSize(unit, unit)
  end
end
JB.PlaceStrip = place

local function draw(data)
  if not strip then
    strip = CreateFrame("Frame", "CassetteStrip", nil) -- no parent: ignores UI scale, stays when the UI is hidden
    strip:SetFrameStrata("TOOLTIP")
    strip:SetFrameLevel(10000)
    strip:SetScale(1)
    strip:SetPoint("TOPLEFT", nil, "TOPLEFT", 0, 0)
  end
  seq = (seq + 1) % 256
  local sum = (seq * 1 + #data * 2) % 255
  for i, b in ipairs(data) do sum = (sum + b * (i + 2)) % 255 end
  local bytes = { seq, #data, sum }
  for _, b in ipairs(data) do bytes[#bytes + 1] = b end
  local bits = {}
  for _, b in ipairs(bytes) do
    for j = 7, 0, -1 do bits[#bits + 1] = math.floor(b / 2 ^ j) % 2 end
  end
  local count = 2 + math.ceil(#bits / 3)
  for i = #pixels + 1, count do
    pixels[i] = strip:CreateTexture(nil, "OVERLAY", nil, 7)
  end
  place()
  pixels[1]:SetColorTexture(0, 1, 1, 1)
  pixels[2]:SetColorTexture(1, 1, 0, 1)
  pixels[1]:Show()
  pixels[2]:Show()
  for i = 3, count do
    local k = (i - 3) * 3
    pixels[i]:SetColorTexture(bits[k + 1] or 0, bits[k + 2] or 0, bits[k + 3] or 0, 1)
    pixels[i]:Show()
  end
  for i = count + 1, #pixels do pixels[i]:Hide() end
  strip:SetSize(count * unit, unit)
  strip:Show()
end

-- Shows queued messages one after another, each long enough to be read (the companion looks
-- every 0.05 s), then hides the line.
local function pump()
  gen = gen + 1
  local mine = gen
  if #queue == 0 then
    showing = false
    C_Timer.After(0.05, function()
      if gen == mine and strip then strip:Hide() end
    end)
    return
  end
  showing = true
  draw(table.remove(queue, 1))
  C_Timer.After(0.15, pump)
end

function JB:PPU100()
  local _, h = GetPhysicalScreenSize()
  local scale = (self.widget and self.widget:GetEffectiveScale()) or UIParent:GetEffectiveScale()
  return math.floor(scale * ((h and h > 0) and h or 768) / 768 * 100 + 0.5)
end

local function u16(list, v)
  v = math.floor(v) % 65536
  list[#list + 1] = math.floor(v / 256)
  list[#list + 1] = v % 256
end

function JB:Send(cmd, arg)
  local now = time()
  local data = {}
  for _, v in ipairs({ now, self.nonce, self.mailCursor, self.nextRecord, self.nextArt, self.nextView, self:PPU100() }) do
    u16(data, v)
  end
  local text = cmd .. (arg and (" " .. arg) or "")
  for i = 1, math.min(#text, MAXLEN - #data) do data[#data + 1] = text:byte(i) end
  if #queue >= 20 then table.remove(queue, 1) end
  queue[#queue + 1] = data
  self.lastSent = GetTime()
  self.anchorMail, self.anchorTime = self.mailCursor, now   -- the reading pace counts from here
  if not showing then pump() end
end

local ev = CreateFrame("Frame")
pcall(ev.RegisterEvent, ev, "DISPLAY_SIZE_CHANGED")
pcall(ev.RegisterEvent, ev, "UI_SCALE_CHANGED")
ev:SetScript("OnEvent", function() place() end)
