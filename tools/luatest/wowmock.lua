-- WoW API stand-in with real time: timers fire when their time comes, tickers repeat, and
-- _mock_update(seconds) moves time forward in 0.05 s steps, running due timers and OnUpdate.
local frames, timers = {}, {}
local clock = 1000
-- Files: FILES["m3"] = { w, h } gives a file's pixel size (default 5 x 1); SLOW["r1_"] = 10 makes
-- the first load of matching paths take 10 s. Like WoW, a file keeps loading after it's asked
-- for once, and is instant afterwards.
FILES, SLOW = {}, {}
local loadedAt = {}
local function natural(self)
  local p = self.path
  if not p then return 0, 0 end
  if clock < loadedAt[p] then return 0, 0 end
  if p:find("sentinel") then return 65, 1 end
  local f = FILES[p:match("[^\\]+$")]
  -- like WoW: a picture of six pixels (seen in game: 6 x 1) comes back the wrong size
  if f and f[1] * f[2] == 6 then return f[1] + 1, f[2] end
  if f then return f[1], f[2] end
  return 5, 1
end
local function mock(kind)
  local m = { scripts = {}, kind = kind, shown = true, w = 0, h = 0 }
  return setmetatable(m, { __index = function(t, k)
    if type(k) ~= "string" or not k:match("^%u") then return nil end  -- only WoW-style Methods exist
    local f
    if k == "SetScript" then f = function(self, n, fn) self.scripts[n] = fn end
    elseif k == "HookScript" then f = function(self, n, fn) local old = self.scripts[n]; self.scripts[n] = function(...) if old then old(...) end fn(...) end end
    elseif k == "GetScript" then f = function(self, n) return self.scripts[n] end
    elseif k == "CreateTexture" or k == "CreateFontString" then f = function(self)
        local c = mock(k)
        rawset(self, "children", rawget(self, "children") or {})
        table.insert(self.children, c)
        return c
      end
    elseif k == "SetColorTexture" then f = function(self, r, g, b, a) self.color = { r, g, b, a } end
    elseif k == "SetSize" then f = function(self, w, h) self.w, self.h, self.sized = w, h, true end
    elseif k == "SetWidth" then f = function(self, w) self.w, self.sized = w, true end
    elseif k == "SetHeight" then f = function(self, h) self.h, self.sized = h, true end
    elseif k == "GetSize" then f = function(self) if self.sized then return self.w, self.h end return natural(self) end
    elseif k == "GetWidth" then f = function(self) return self.w > 0 and self.w or 120 end
    elseif k == "GetHeight" then f = function(self) return self.h > 0 and self.h or 768 end
    elseif k == "GetStringWidth" then f = function() return 40 end
    elseif k == "GetTop" then f = function() return 100 end
    elseif k == "GetBottom" then f = function(self) return 100 - (self.h > 0 and self.h or 50) end
    elseif k == "GetLeft" then f = function() return 10 end
    elseif k == "GetRight" then f = function(self) return 10 + (self.w > 0 and self.w or 120) end
    elseif k == "HasFocus" then f = function() return false end
    elseif k == "SetText" then f = function(self, s) self.text = s end
    elseif k == "GetText" then f = function(self) return self.text end
    elseif k == "SetParent" then f = function(self, p) self.parent = p end
    elseif k == "GetParent" then f = function(self) return self.parent end
    elseif k == "GetEffectiveScale" then f = function() return 0.64 end
    elseif k == "GetPoint" then f = function() return "BOTTOMRIGHT", nil, "BOTTOMRIGHT", -40, 60 end
    elseif k == "SetAlpha" then f = function(self, a) self.alpha = a end
    elseif k == "GetAlpha" then f = function(self) return self.alpha or 1 end
    elseif k == "SetShown" then f = function(self, v) self.shown = v and true or false end
    elseif k == "Show" then f = function(self) self.shown = true end
    elseif k == "Hide" then f = function(self) self.shown = false end
    elseif k == "IsShown" then f = function(self) return self.shown end
    elseif k == "SetTexture" then f = function(self, p)
        self.path = p
        if p and not loadedAt[p] then
          local delay = 0
          for part, s in pairs(SLOW) do if p:find(part, 1, true) then delay = s end end
          loadedAt[p] = clock + delay
        end
      end
    elseif k == "SetFont" then f = function() return true end
    else f = function() end end
    rawset(t, k, f)
    return f
  end })
end
function CreateFrame(kind, name, parent)
  local f = mock(kind)
  f.parent = parent
  frames[#frames + 1] = f
  if name then _G[name] = f end
  return f
end
function CreateFont(name) local f = mock("Font"); if name then _G[name] = f end; return f end
UIParent, GameTooltip, WorldFrame = mock("UIParent"), mock("GameTooltip"), mock("WorldFrame")
C_Timer = {
  After = function(t, fn) timers[#timers + 1] = { at = clock + t, fn = fn } end,
  NewTicker = function(t, fn)
    local tk = { at = clock + t, fn = fn, every = t }
    timers[#timers + 1] = tk
    return { Cancel = function() tk.cancelled = true end }
  end,
}
local function runDue()
  local i = 1
  while i <= #timers do
    local t = timers[i]
    if t.cancelled then
      table.remove(timers, i)
    elseif t.at <= clock + 1e-9 then
      if t.every then t.at = t.at + t.every; i = i + 1; t.fn()
      else table.remove(timers, i); t.fn() end
    else
      i = i + 1
    end
  end
end
function GetTime() return clock end
function time() return os.time() end
date = os.date
function GetPhysicalScreenSize() return 2560, 1440 end
STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"
tinsert, UISpecialFrames, ChatFontNormal = table.insert, {}, {}
function UnitClass() return "Rogue", "ROGUE" end
RAID_CLASS_COLORS = { ROGUE = { r = 1, g = 0.96, b = 0.41 } }
ADDON_FILES = { "Core", "Strip", "Live", "Duck", "Widget", "Browser", "UI", "Options", "Setup" }
SlashCmdList = {}
printed = {}
function print(...) printed[#printed + 1] = table.concat({ ... }, " ") end
function _mock_fire(event, ...) for _, f in ipairs(frames) do if f.scripts.OnEvent then f.scripts.OnEvent(f, event, ...) end end end
function _mock_update(seconds)
  local left = seconds
  while left > 1e-9 do
    local step = math.min(0.05, left)
    clock, left = clock + step, left - step
    runDue()
    for _, f in ipairs(frames) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, step) end end
  end
end
function _mock_timers() _mock_update(3) end
function _mock_frames() return frames end
