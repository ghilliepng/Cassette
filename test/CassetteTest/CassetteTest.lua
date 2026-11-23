-- Cassette test 4: the number channel and the round trip.
--
-- Test 3 showed that a texture with no size set takes its size from the file, so the PC can send
-- numbers as a picture's width and height. This test checks the details, using files that were
-- 1 x 1 placeholders when the game loaded and are only given their real size afterwards:
--
--   round trip: on opening, the window sends READY through the strip. imagetest.py reads it and
--     gives rt0..rt39 a size of 5 x 3. The window reads one rt file every 0.1 s and notes the
--     first one that has changed: how long a click -> PC -> game answer takes.
--   sizes, read 3 s after opening: an odd size (37 x 5) read at once / next frame / on a hidden
--     texture / on an invisible one, long thin files, an 8-bit grey file and a bigger one.
--
-- Open it once after each /reload: files are only fresh the first time.

local BASE = "Interface\\AddOns\\CassetteTest\\img\\"

local frame = CreateFrame("Frame", "CassetteTestFrame", UIParent)
frame:SetSize(520, 250)
frame:SetPoint("CENTER")
frame:SetFrameStrata("DIALOG")
frame:SetClampedToScreen(true)
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:Hide()

local bg = frame:CreateTexture(nil, "BACKGROUND")
bg:SetAllPoints()
bg:SetColorTexture(0.05, 0.05, 0.07, 0.92)

local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOPLEFT", 14, -12)
title:SetText("Cassette test 4: numbers from the PC")

local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", 0, 0)

local results = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
results:SetPoint("TOPLEFT", 14, -44)
results:SetWidth(490)
results:SetJustifyH("LEFT")
results:SetSpacing(4)

local host = CreateFrame("Frame", nil, frame)
host:SetPoint("BOTTOMRIGHT", -14, 14)
host:SetSize(1, 1)

local function newTex()
  local t = host:CreateTexture(nil, "ARTWORK")
  t:SetPoint("BOTTOMRIGHT")  -- one anchor and no size: WoW sizes it from the file
  return t
end

local function dims(t)
  local ok, w, h = pcall(t.GetSize, t)
  if not ok then return "ERROR " .. tostring(w) end
  return ("%.0f x %.0f"):format(w or -1, h or -1)
end

--------------------------------------------------------------------------------
-- The strip: game to PC. Squares of 3 x 3 screen pixels, each colour channel fully on or off
-- (3 bits a square). Squares 1-2 are markers (cyan, yellow), then the bytes: sequence number,
-- length, checksum, text.
--------------------------------------------------------------------------------

local SQ = 3
local strip, squares, unit, seq = nil, {}, 1, 0

local function place()
  if not strip then return end
  local _, h = GetPhysicalScreenSize()
  unit = 768 / ((h and h > 0) and h or 768)   -- one screen pixel, in this frame's units
  for i, t in ipairs(squares) do
    t:ClearAllPoints()
    t:SetPoint("TOPLEFT", strip, "TOPLEFT", (i - 1) * SQ * unit, 0)
    t:SetSize(SQ * unit, SQ * unit)
  end
end

local function sendStrip(text)
  if not strip then
    strip = CreateFrame("Frame", "CassetteTestStrip", nil) -- no parent: ignores UI scale, stays when the UI is hidden
    strip:SetFrameStrata("TOOLTIP")
    strip:SetFrameLevel(10000)
    strip:SetScale(1)
    strip:SetPoint("TOPLEFT", nil, "TOPLEFT", 0, 0)
  end
  seq = (seq + 1) % 256
  -- checksum over sequence, length and text, each weighted by its position, mod 255: any one
  -- wrong bit always changes it (a plain mod 256 sum misses a flipped top bit)
  local sum = (seq * 1 + #text * 2) % 255
  for i = 1, #text do sum = (sum + text:byte(i) * (i + 2)) % 255 end
  local bytes = { seq, #text, sum }
  for i = 1, #text do bytes[#bytes + 1] = text:byte(i) end
  local bits = {}
  for _, b in ipairs(bytes) do
    for j = 7, 0, -1 do bits[#bits + 1] = math.floor(b / 2 ^ j) % 2 end
  end
  local count = 2 + math.ceil(#bits / 3)
  for i = #squares + 1, count do
    squares[i] = strip:CreateTexture(nil, "OVERLAY", nil, 7)
  end
  place()
  squares[1]:SetColorTexture(0, 1, 1, 1)
  squares[2]:SetColorTexture(1, 1, 0, 1)
  squares[1]:Show()
  squares[2]:Show()
  for i = 3, count do
    local k = (i - 3) * 3
    squares[i]:SetColorTexture(bits[k + 1] or 0, bits[k + 2] or 0, bits[k + 3] or 0, 1)
    squares[i]:Show()
  end
  for i = count + 1, #squares do squares[i]:Hide() end
  strip:SetSize(count * SQ * unit, SQ * unit)
  strip:Show()
end

--------------------------------------------------------------------------------

local roundTrip = "round trip: waiting..."
local sizeLines = {}

local function show()
  local all = { roundTrip }
  for _, l in ipairs(sizeLines) do all[#all + 1] = l end
  results:SetText(table.concat(all, "\n"))
end

local function runSizeProbes()
  local t0 = newTex()
  t0:SetTexture(BASE .. "sz0")
  sizeLines[1] = "37 x 5, read at once:  " .. dims(t0)
  local t1 = newTex()
  t1:SetTexture(BASE .. "sz1")
  local t2 = newTex()
  t2:Hide()
  t2:SetTexture(BASE .. "sz2")
  local t3 = newTex()
  t3:SetAlpha(0)
  t3:SetTexture(BASE .. "sz3")
  local t4 = newTex()
  t4:SetTexture(BASE .. "sz4")
  local t5 = newTex()
  t5:SetTexture(BASE .. "sz5")
  local t6 = newTex()
  t6:SetTexture(BASE .. "sz6")
  local t7 = newTex()
  t7:SetTexture(BASE .. "sz7")
  C_Timer.After(0, function()
    sizeLines[2] = "37 x 5, read next frame:  " .. dims(t1)
    show()
  end)
  C_Timer.After(0.5, function()
    sizeLines[3] = "37 x 5, hidden texture:  " .. dims(t2)
    sizeLines[4] = "37 x 5, invisible texture (alpha 0):  " .. dims(t3)
    sizeLines[5] = "1000 x 1:  " .. dims(t4)
    sizeLines[6] = "4096 x 1:  " .. dims(t5)
    sizeLines[7] = "37 x 5, 8-bit grey file:  " .. dims(t6)
    sizeLines[8] = "300 x 200:  " .. dims(t7)
    for _, t in ipairs({ t0, t1, t2, t3, t4, t5, t6, t7 }) do t:Hide() end
    show()
  end)
end

local ticker

frame:SetScript("OnShow", function()
  roundTrip, sizeLines = "round trip: waiting...", {}
  show()
  sendStrip("READY " .. time())
  -- read rt0, rt1, ... every 0.1 s until one has its new size (5 x 3)
  local k, prev = 0, nil
  if ticker then ticker:Cancel() end
  ticker = C_Timer.NewTicker(0.1, function()
    if prev then
      local w, h = prev:GetSize()
      prev:Hide()
      if math.floor(w + 0.5) == 5 and math.floor(h + 0.5) == 3 then
        roundTrip = ("round trip: answer was there by rt%d, about %.1f s after sending READY"):format(k - 1, k * 0.1)
        show()
        ticker:Cancel()
        return
      end
    end
    if k >= 40 then
      roundTrip = "round trip: no answer within 4 s (last rt size " .. (prev and dims(prev) or "?") .. ")"
      show()
      ticker:Cancel()
      return
    end
    prev = newTex()
    prev:SetTexture(BASE .. "rt" .. k)
    k = k + 1
  end)
  C_Timer.After(3, runSizeProbes)
end)

frame:SetScript("OnHide", function()
  if ticker then ticker:Cancel() end
  if strip then strip:Hide() end
end)

SLASH_CASSETTETEST1 = "/jbtest"
SlashCmdList.CASSETTETEST = function()
  frame:SetShown(not frame:IsShown())
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("PLAYER_LOGIN")
pcall(ev.RegisterEvent, ev, "DISPLAY_SIZE_CHANGED")
pcall(ev.RegisterEvent, ev, "UI_SCALE_CHANGED")
ev:SetScript("OnEvent", function(_, event)
  if event == "PLAYER_LOGIN" then
    print("|cff66ccffCassette test 4|r loaded. Type |cffffff00/jbtest|r to open it.")
  else
    place()
  end
end)
