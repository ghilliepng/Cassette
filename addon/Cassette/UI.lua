-- Cassette's looks, and the small building blocks of its windows (options, first setup).
--
-- Three themes change the whole look: the player, the browser and the windows.
--   classic    WoW's classic art: stone dialog borders, tooltip-style panels, gold text and the
--              red buttons. Sits with the vanilla look.
--   modern     the game's own modern frames, buttons and close button (retail's art; on WoW
--              Forever, Forever's own), drawn by the game itself where it has them.
--   ellesmere  flat and dark, to sit with EllesmereUI.
-- The font isn't part of a theme: it's EllesmereUI's when that's installed, otherwise the
-- game's own (Core.lua).
--
-- Each theme draws its own pieces on a frame, made the first time that theme shows there and kept
-- after, so switching theme in the options is instant: one set shows, the others hide.

local _, JB = ...

local UI = {}
JB.UI = UI
local M = JB.MEDIA
local GOLD = { 1, 0.82, 0 }
local BRONZE = { 0.6, 0.48, 0.28 }

local THEMES = {
  classic = {
    name = "Classic",
    text = { 1, 1, 1 }, dim = { 0.82, 0.82, 0.82 }, faint = { 0.55, 0.55, 0.55 },
    heading = GOLD, title = GOLD, icon = GOLD, iconHover = { 1, 1, 1 }, tab = GOLD,
    shadow = true,
    outset = { bar = 4, panel = 4, window = 7 },   -- how far the border reaches past the frame
    progress = { h = 4, texture = "Interface\\TargetingFrame\\UI-StatusBar", bg = { 0, 0, 0, 0.6 } },
  },
  modern = {
    name = "Modern",
    text = { 0.96, 0.94, 0.9 }, dim = { 0.7, 0.68, 0.64 }, faint = { 0.5, 0.48, 0.45 },
    heading = GOLD, title = GOLD, icon = { 0.92, 0.89, 0.82 }, iconHover = GOLD, tab = { 0.82, 0.79, 0.72 },
    shadow = true,
    outset = { bar = 2, panel = 2, window = 2 },
    progress = { h = 3, bg = { 0.02, 0.02, 0.02, 0.85 } },
  },
  ellesmere = {
    name = "EllesmereUI",
    text = { 0.9, 0.9, 0.92 }, dim = { 0.62, 0.62, 0.68 }, faint = { 0.45, 0.45, 0.5 },
    heading = "accent", title = "accent", icon = { 0.85, 0.85, 0.88 }, iconHover = { 1, 1, 1 },
    tab = { 0.62, 0.62, 0.68 },
    shadow = false,
    outset = { bar = 0, panel = 0, window = 0 },
    progress = { h = 2, bg = { 0.2, 0.2, 0.23, 1 } },
  },
}
UI.THEMES = THEMES
UI.THEME_ORDER = { "classic", "modern", "ellesmere" }

function JB:ThemeKey()
  local key = self.db and self.db.theme
  return THEMES[key] and key or "ellesmere"
end

function JB:Theme()
  return THEMES[self:ThemeKey()]
end

-- A colour by its job: text, dim, faint, heading, title, icon, iconHover, tab.
function JB:Colour(role)
  local T = self:Theme()
  local c = T[role] or T.text
  if c == "accent" then return self:Accent() end
  return c[1], c[2], c[3]
end

-- One screen pixel, in a frame's units (for hairlines that stay one pixel at any scale).
function UI.Pixel(frame)
  local _, h = GetPhysicalScreenSize()
  local s = frame and frame.GetEffectiveScale and frame:GetEffectiveScale()
  if not h or h <= 0 or not s or s <= 0 then return 1 end
  return 768 / h / s
end

local function hasAtlas(name)
  return C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo(name) ~= nil
end

-- refreshers: run after any setting changes, so every control shows the current value and look
UI.refreshers = {}
local texts = setmetatable({}, { __mode = "k" })   -- text -> its colour's job
local icons = setmetatable({}, { __mode = "k" })   -- icon buttons

function UI.Role(fs, role)
  texts[fs] = role
  fs:SetTextColor(JB:Colour(role))
end

function UI.Recolour()
  for fs, role in pairs(texts) do fs:SetTextColor(JB:Colour(role)) end
  for b in pairs(icons) do b:Paint() end
end

function UI.RefreshAll()
  UI.Recolour()
  for _, fn in ipairs(UI.refreshers) do pcall(fn) end
end

--------------------------------------------------------------------------------
-- Theme pieces
--------------------------------------------------------------------------------

-- The current theme's set of regions in `slot` on `owner`, built by build(set, add) the first
-- time; the other themes' sets are hidden.
local function pieces(owner, slot, build)
  owner.themed = owner.themed or {}
  local key = JB:ThemeKey()
  local sets = owner.themed[slot]
  if not sets then
    sets = {}
    owner.themed[slot] = sets
  end
  for k, set in pairs(sets) do
    if k ~= key then
      for _, r in ipairs(set) do r:Hide() end
    end
  end
  local set = sets[key]
  if not set then
    set = {}
    build(set, function(r) set[#set + 1] = r return r end)
    sets[key] = set
  end
  for _, r in ipairs(set) do r:Show() end
  return set
end
UI.Pieces = pieces

-- A top-to-bottom gradient (colours { r, g, b, a }), or the average where the client can't.
local function gradient(t, top, bottom)
  t:SetColorTexture(1, 1, 1, 1)
  local ok = CreateColor and pcall(t.SetGradient, t, "VERTICAL",
    CreateColor(bottom[1], bottom[2], bottom[3], bottom[4]), CreateColor(top[1], top[2], top[3], top[4]))
  if not ok then
    t:SetColorTexture((top[1] + bottom[1]) / 2, (top[2] + bottom[2]) / 2, (top[3] + bottom[3]) / 2,
      (top[4] + bottom[4]) / 2)
  end
end

-- Four lines round a frame or region: their outer edge `out` past its edges, `thick` wide.
local function lines(owner, add, layer, sub)
  local l = {}
  for i = 1, 4 do l[i] = add(owner:CreateTexture(nil, layer, nil, sub)) end
  return l
end

local function outline(l, rel, out, thick, r, g, b, a)
  local top, bottom, left, right = l[1], l[2], l[3], l[4]
  for _, t in ipairs(l) do
    t:ClearAllPoints()
    t:SetColorTexture(r, g, b, a)
  end
  top:SetPoint("TOPLEFT", rel, "TOPLEFT", -out, out)
  top:SetPoint("TOPRIGHT", rel, "TOPRIGHT", out, out)
  top:SetHeight(thick)
  bottom:SetPoint("BOTTOMLEFT", rel, "BOTTOMLEFT", -out, -out)
  bottom:SetPoint("BOTTOMRIGHT", rel, "BOTTOMRIGHT", out, -out)
  bottom:SetHeight(thick)
  left:SetPoint("TOPLEFT", rel, "TOPLEFT", -out, out - thick)
  left:SetPoint("BOTTOMLEFT", rel, "BOTTOMLEFT", -out, -out + thick)
  left:SetWidth(thick)
  right:SetPoint("TOPRIGHT", rel, "TOPRIGHT", out, out - thick)
  right:SetPoint("BOTTOMRIGHT", rel, "BOTTOMRIGHT", out, -out + thick)
  right:SetWidth(thick)
end
UI.Outline = outline
UI.Lines = lines

-- Classic borders, cut from the game's own border art the way its backdrops are: the file holds
-- eight squares side by side (left, right, top, bottom edges, then the four corners), the top and
-- bottom edges lying on their side. Edges repeat along their length.
local BORDERS = {
  tooltip = { edge = "Interface\\Tooltips\\UI-Tooltip-Border", size = 16, inset = 4,
              bg = "Interface\\Tooltips\\UI-Tooltip-Background", tint = { 0.05, 0.05, 0.08 }, line = { 0.8, 0.8, 0.8 } },
  dialog  = { edge = "Interface\\DialogFrame\\UI-DialogBox-Border", size = 32, inset = 11,
              bg = "Interface\\DialogFrame\\UI-DialogBox-Background", tile = true, tint = { 1, 1, 1 }, line = { 1, 1, 1 } },
  slider  = { edge = "Interface\\Buttons\\UI-SliderBar-Border", size = 8, inset = 3,
              bg = "Interface\\Buttons\\UI-SliderBar-Background", tile = true, tint = { 1, 1, 1 }, line = { 1, 1, 1 } },
  input   = { edge = "Interface\\Tooltips\\UI-Tooltip-Border", size = 10, inset = 3,
              bg = "Interface\\Tooltips\\UI-Tooltip-Background", tint = { 0, 0, 0 }, line = { 0.6, 0.6, 0.6 } },
}
local CS, CE = 0.0625, 0.9375
local function seg(k) return k * 0.125 + 0.0078125, (k + 1) * 0.125 - 0.0078125 end

local function classicBorder(owner, add, spec)
  local b = { spec = spec, owner = owner, parts = {} }
  b.bg = add(owner:CreateTexture(nil, "BACKGROUND", nil, -8))
  if spec.tile then
    b.bg:SetTexture(spec.bg, "REPEAT", "REPEAT")
    b.bg:SetHorizTile(true)
    b.bg:SetVertTile(true)
  else
    b.bg:SetTexture(spec.bg)
  end
  for i = 1, 8 do
    local t = add(owner:CreateTexture(nil, "BORDER", nil, -8))
    t:SetTexture(spec.edge, "REPEAT", "REPEAT")
    b.parts[i] = t
  end
  return b
end

-- Seat a classic border `o` past its frame's edges, its tiling fitted to the frame's size.
local function seatBorder(b, o, alpha)
  local owner, spec, e = b.owner, b.spec, b.spec.size
  local tl, tr, bl, br, top, bottom, left, right = unpack(b.parts)
  for _, t in ipairs(b.parts) do
    t:ClearAllPoints()
    t:SetVertexColor(spec.line[1], spec.line[2], spec.line[3], 1)
  end
  tl:SetPoint("TOPLEFT", owner, "TOPLEFT", -o, o)
  tr:SetPoint("TOPRIGHT", owner, "TOPRIGHT", o, o)
  bl:SetPoint("BOTTOMLEFT", owner, "BOTTOMLEFT", -o, -o)
  br:SetPoint("BOTTOMRIGHT", owner, "BOTTOMRIGHT", o, -o)
  for _, c in ipairs({ tl, tr, bl, br }) do c:SetSize(e, e) end
  top:SetPoint("TOPLEFT", tl, "TOPRIGHT")
  top:SetPoint("BOTTOMRIGHT", tr, "BOTTOMLEFT")
  bottom:SetPoint("TOPLEFT", bl, "TOPRIGHT")
  bottom:SetPoint("BOTTOMRIGHT", br, "BOTTOMLEFT")
  left:SetPoint("TOPLEFT", tl, "BOTTOMLEFT")
  left:SetPoint("BOTTOMRIGHT", bl, "TOPRIGHT")
  right:SetPoint("TOPLEFT", tr, "BOTTOMLEFT")
  right:SetPoint("BOTTOMRIGHT", br, "TOPRIGHT")
  local w, h = owner:GetWidth() + 2 * o, owner:GetHeight() + 2 * o
  local nx, ny = math.max(0.01, (w - 2 * e) / e), math.max(0.01, (h - 2 * e) / e)
  for k, c in ipairs({ tl, tr, bl, br }) do
    local u0, u1 = seg(k + 3)
    c:SetTexCoord(u0, CS, u0, CE, u1, CS, u1, CE)
  end
  local u0, u1 = seg(0)
  left:SetTexCoord(u0, CS, u0, ny, u1, CS, u1, ny)
  u0, u1 = seg(1)
  right:SetTexCoord(u0, CS, u0, ny, u1, CS, u1, ny)
  u0, u1 = seg(2)
  top:SetTexCoord(u0, nx, u1, nx, u0, CS, u1, CS)
  u0, u1 = seg(3)
  bottom:SetTexCoord(u0, nx, u1, nx, u0, CS, u1, CS)
  local i = spec.inset
  b.bg:ClearAllPoints()
  b.bg:SetPoint("TOPLEFT", owner, "TOPLEFT", -o + i, o - i)
  b.bg:SetPoint("BOTTOMRIGHT", owner, "BOTTOMRIGHT", o - i, -o + i)
  b.bg:SetVertexColor(spec.tint[1], spec.tint[2], spec.tint[3], alpha)
end

--------------------------------------------------------------------------------
-- The game's own frame art (for Modern)
--------------------------------------------------------------------------------

-- NineSlice layouts, in order of preference; the first the client has is used.
local NATIVE_LAYOUTS = {
  window = { "ButtonFrameTemplateNoPortrait", "PortraitFrameTemplate", "Dialog" },
  panel = { "TooltipDefaultLayout", "TooltipDefaultDarkLayout", "Dialog" },
  bar = { "TooltipDefaultLayout", "TooltipDefaultDarkLayout", "Dialog" },
}
local NINE = { "TopLeftCorner", "TopRightCorner", "BottomLeftCorner", "BottomRightCorner",
               "TopEdge", "BottomEdge", "LeftEdge", "RightEdge", "Center" }

local function nativeLayout(kind)
  if not (NineSliceUtil and NineSliceUtil.GetLayout and NineSliceUtil.ApplyLayout) then return nil end
  for _, name in ipairs(NATIVE_LAYOUTS[kind] or {}) do
    local ok, layout = pcall(NineSliceUtil.GetLayout, name)
    if ok and layout then return layout end
  end
end

-- The layout's pieces on `owner` itself, under everything the owner draws. nil if it can't.
local function nativeFrame(owner, add, kind)
  local layout = nativeLayout(kind)
  if not layout or not pcall(NineSliceUtil.ApplyLayout, owner, layout) then return nil end
  local got = {}
  for _, name in ipairs(NINE) do
    local piece = rawget(owner, name)
    if type(piece) == "table" and piece.SetDrawLayer then
      if name == "Center" then
        piece:SetDrawLayer("BACKGROUND", -7)
        piece:SetAlpha(0)   -- our own background (its opacity is a setting) stands in for it
      else
        piece:SetDrawLayer("BORDER", -8)
      end
      got[#got + 1] = add(piece)
    end
  end
  return #got > 0 and got or nil
end
UI.HasAtlas = hasAtlas

--------------------------------------------------------------------------------
-- Skins: a frame's background and border in the current theme
--------------------------------------------------------------------------------

local SKINS = {}

SKINS.ellesmere = {
  build = function(set, add, owner)
    set.bg = add(owner:CreateTexture(nil, "BACKGROUND", nil, -8))
    set.edge = lines(owner, add, "BORDER", -8)
  end,
  seat = function(set, owner, kind, alpha)
    set.bg:ClearAllPoints()
    set.bg:SetAllPoints(owner)
    set.bg:SetColorTexture(0.05, 0.05, 0.06, alpha)
    outline(set.edge, owner, 0, UI.Pixel(owner), 0, 0, 0, 1)
  end,
}

SKINS.classic = {
  build = function(set, add, owner, kind)
    set.border = classicBorder(owner, add, kind == "window" and BORDERS.dialog or BORDERS.tooltip)
    if kind == "window" then
      set.header = add(owner:CreateTexture(nil, "ARTWORK", nil, -7))
      set.header:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
    end
  end,
  seat = function(set, owner, kind, alpha)
    local o = THEMES.classic.outset[kind] or 0
    seatBorder(set.border, o, alpha)
    if set.header then
      set.header:ClearAllPoints()
      set.header:SetPoint("TOP", owner, "TOP", 0, o + 12)
      local w = owner.title and owner.title:GetStringWidth() or 100
      set.header:SetSize(math.max(220, w + 150), 64)
    end
  end,
}

SKINS.modern = {
  build = function(set, add, owner, kind)
    set.bg = add(owner:CreateTexture(nil, "BACKGROUND", nil, -8))
    set.native = nativeFrame(owner, add, kind)
    if set.native then
      if kind == "window" then   -- the band under the title, as the game's windows have
        set.band = add(owner:CreateTexture(nil, "BACKGROUND", nil, -6))
      end
      return
    end
    set.outer = lines(owner, add, "BORDER", -8)
    set.rim = lines(owner, add, "BORDER", -7)
    if kind == "window" then
      set.band = add(owner:CreateTexture(nil, "BACKGROUND", nil, -7))
      set.divider = add(owner:CreateTexture(nil, "BORDER", nil, -6))
    end
    set.studs = {}
    for i = 1, 4 do set.studs[i] = add(owner:CreateTexture(nil, "BORDER", nil, -5)) end
  end,
  seat = function(set, owner, kind, alpha)
    local px, o = UI.Pixel(owner), THEMES.modern.outset[kind] or 0
    set.bg:ClearAllPoints()
    if set.native then
      set.bg:SetPoint("TOPLEFT", owner, "TOPLEFT", 2, -2)
      set.bg:SetPoint("BOTTOMRIGHT", owner, "BOTTOMRIGHT", -2, 2)
      gradient(set.bg, { 0.09, 0.09, 0.1, alpha }, { 0.03, 0.03, 0.035, alpha })
      if set.band then
        set.band:ClearAllPoints()
        set.band:SetPoint("TOPLEFT", owner, "TOPLEFT", 2, -2)
        set.band:SetPoint("TOPRIGHT", owner, "TOPRIGHT", -2, -2)
        set.band:SetHeight(22)
        gradient(set.band, { 0.2, 0.17, 0.12, 0.7 }, { 0.12, 0.1, 0.07, 0.4 })
      end
      return
    end
    set.bg:SetAllPoints(owner)
    gradient(set.bg, { 0.11, 0.105, 0.1, alpha }, { 0.035, 0.035, 0.04, alpha })
    outline(set.outer, owner, o + px, px, 0, 0, 0, 0.9)
    outline(set.rim, owner, o, px, BRONZE[1], BRONZE[2], BRONZE[3], 0.95)
    if set.band then
      set.band:ClearAllPoints()
      set.band:SetPoint("TOPLEFT", owner, "TOPLEFT", 0, 0)
      set.band:SetPoint("TOPRIGHT", owner, "TOPRIGHT", 0, 0)
      set.band:SetHeight(30)
      gradient(set.band, { 0.32, 0.25, 0.13, 0.5 }, { 0.32, 0.25, 0.13, 0 })
      set.divider:ClearAllPoints()
      set.divider:SetPoint("TOPLEFT", owner, "TOPLEFT", 8, -30)
      set.divider:SetPoint("TOPRIGHT", owner, "TOPRIGHT", -8, -30)
      set.divider:SetHeight(px)
      set.divider:SetColorTexture(BRONZE[1], BRONZE[2], BRONZE[3], 0.6)
    end
    -- small gold studs on the rim's corners
    for i, point in ipairs({ "TOPLEFT", "TOPRIGHT", "BOTTOMLEFT", "BOTTOMRIGHT" }) do
      local s = set.studs[i]
      local x = (i == 1 or i == 3) and -o or o
      local y = (i <= 2) and o or -o
      s:ClearAllPoints()
      s:SetPoint("CENTER", owner, point, x, y)
      s:SetSize(3, 3)
      s:SetColorTexture(0.95, 0.78, 0.38, 1)
    end
  end,
}

-- Paint `owner` (kind "bar", "panel" or "window") in the current theme. alpha: background opacity.
function UI.Skin(owner, kind, alpha)
  local key = JB:ThemeKey()
  local def = SKINS[key]
  local set = pieces(owner, "skin", function(s, add) def.build(s, add, owner, kind) end)
  owner.skinKind, owner.skinAlpha = kind, alpha or 1
  def.seat(set, owner, kind, owner.skinAlpha)
  if not owner.skinHooked then
    owner.skinHooked = true
    owner:HookScript("OnSizeChanged", function()
      local k = JB:ThemeKey()
      local s = owner.themed and owner.themed.skin and owner.themed.skin[k]
      if s then SKINS[k].seat(s, owner, owner.skinKind, owner.skinAlpha) end
    end)
  end
  return set
end

-- How far a frame's border reaches past it, in this theme.
function UI.Outset(kind)
  return JB:Theme().outset[kind] or 0
end

-- A box behind a text field: dark, with a rim in the theme's colours.
function UI.FieldSkin(owner)
  local key = JB:ThemeKey()
  local set = pieces(owner, "field", function(s, add)
    if key == "classic" then
      s.border = classicBorder(owner, add, BORDERS.input)
    else
      s.bg = add(owner:CreateTexture(nil, "BACKGROUND"))
      s.rim = lines(owner, add, "BORDER", 0)
    end
  end)
  if key == "classic" then
    seatBorder(set.border, 2, 0.6)
  elseif key == "modern" then
    set.bg:SetAllPoints(owner)
    set.bg:SetColorTexture(0, 0, 0, 0.45)
    outline(set.rim, owner, 0, UI.Pixel(owner), BRONZE[1], BRONZE[2], BRONZE[3], 0.7)
  else
    set.bg:SetAllPoints(owner)
    set.bg:SetColorTexture(1, 1, 1, 0.06)
    outline(set.rim, owner, 0, UI.Pixel(owner), 0, 0, 0, 0)
  end
end

--------------------------------------------------------------------------------
-- Controls
--------------------------------------------------------------------------------

function UI.Text(parent, size, role)
  local fs = parent:CreateFontString(nil, "OVERLAY")
  JB:SetFont(fs, size or 12)
  fs:SetJustifyH("LEFT")
  UI.Role(fs, role or "text")
  return fs
end

function UI.Heading(parent, text)
  local fs = UI.Text(parent, 13, "heading")
  fs:SetText(text)
  return fs
end

-- A button with one of the white icons in Media, tinted in the theme's icon colours.
-- colour(hover), if given, can return a colour of its own (the shuffle toggle: the accent while
-- it's on, a lighter accent under the mouse); nil keeps the usual colours.
function UI.Icon(parent, icon, size, onClick, colour)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(size, size)
  b:RegisterForClicks("LeftButtonUp")
  local t = b:CreateTexture(nil, "ARTWORK")
  t:SetAllPoints()
  t:SetTexture(M .. icon)
  b.icon = t
  local hover = false
  function b:Paint()
    local r, g, bl
    if colour then r, g, bl = colour(hover) end
    if r then
      t:SetVertexColor(r, g, bl)
    elseif hover then
      t:SetVertexColor(JB:Colour("iconHover"))
    else
      t:SetVertexColor(JB:Colour("icon"))
    end
  end
  b:SetScript("OnEnter", function() hover = true b:Paint() end)
  b:SetScript("OnLeave", function() hover = false b:Paint() end)
  b:SetScript("OnMouseDown", function() t:SetPoint("TOPLEFT", 1, -1) t:SetPoint("BOTTOMRIGHT", 1, -1) end)
  b:SetScript("OnMouseUp", function() t:SetAllPoints() end)
  b:SetScript("OnClick", onClick)
  icons[b] = true
  b:Paint()
  return b
end

-- A window: the theme's frame, its title, and a close button. Escape closes it.
function UI.Window(name, w, h, title)
  local f = CreateFrame("Frame", name, UIParent)
  f:SetSize(w, h)
  f:SetPoint("CENTER")
  f:SetFrameStrata("DIALOG")
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:Hide()
  tinsert(UISpecialFrames, name)
  f.title = f:CreateFontString(nil, "OVERLAY")
  JB:SetFont(f.title, 15)
  f.title:SetText(title)
  UI.Role(f.title, "title")

  local close = CreateFrame("Button", nil, f)
  f.close = close
  local down = false
  local function paintClose()
    local key = JB:ThemeKey()
    local modern = key == "modern" and hasAtlas("RedButton-Exit")
    local set = pieces(close, "skin", function(s, add)
      s.icon = add(close:CreateTexture(nil, "ARTWORK"))
      s.icon:SetAllPoints()
      if key == "ellesmere" then
        s.icon:SetTexture(M .. "close")
      elseif not modern then
        s.hl = add(close:CreateTexture(nil, "HIGHLIGHT"))
        s.hl:SetAllPoints()
        s.hl:SetTexture("Interface\\Buttons\\UI-Panel-MinimizeButton-Highlight")
        s.hl:SetBlendMode("ADD")
      else
        s.hl = add(close:CreateTexture(nil, "HIGHLIGHT"))
        s.hl:SetAllPoints()
        if hasAtlas("RedButton-Highlight") then s.hl:SetAtlas("RedButton-Highlight") end
        s.hl:SetBlendMode("ADD")
      end
    end)
    close:ClearAllPoints()
    if key == "ellesmere" then
      close:SetSize(14, 14)
      close:SetPoint("TOPRIGHT", -10, -10)
      set.icon:SetVertexColor(JB:Colour(close.hover and "iconHover" or "dim"))
    elseif modern then
      close:SetSize(22, 22)
      close:SetPoint("TOPRIGHT", 0, 0)
      set.icon:SetAtlas(down and hasAtlas("RedButton-exit-pressed") and "RedButton-exit-pressed" or "RedButton-Exit")
    else
      local o = UI.Outset("window")
      close:SetSize(32, 32)
      close:SetPoint("TOPRIGHT", f, "TOPRIGHT", key == "classic" and o - 5 or 3, key == "classic" and o - 5 or 3)
      set.icon:SetTexture(down and "Interface\\Buttons\\UI-Panel-MinimizeButton-Down"
        or "Interface\\Buttons\\UI-Panel-MinimizeButton-Up")
    end
  end
  close:SetScript("OnClick", function() f:Hide() end)
  close:SetScript("OnEnter", function() close.hover = true paintClose() end)
  close:SetScript("OnLeave", function() close.hover, down = false, false paintClose() end)
  close:SetScript("OnMouseDown", function() down = true paintClose() end)
  close:SetScript("OnMouseUp", function() down = false paintClose() end)

  local function paint()
    UI.Skin(f, "window", 0.97)
    f.title:ClearAllPoints()
    if JB:ThemeKey() == "classic" then
      f.title:SetPoint("TOP", f, "TOP", 0, UI.Outset("window") - 2)   -- on the gold banner
    elseif JB:ThemeKey() == "modern" then
      f.title:SetPoint("TOP", f, "TOP", 0, -5)                          -- in the title bar
    else
      f.title:SetPoint("TOPLEFT", 14, -10)
    end
    paintClose()
  end
  table.insert(UI.refreshers, paint)
  paint()
  return f
end

-- A button: the theme's (classic red, modern red or dark, or flat). primary: the main action.
function UI.Button(parent, text, w, onClick, primary)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(w or 120, 22)
  b.text = b:CreateFontString(nil, "OVERLAY")
  JB:SetFont(b.text, 11.5)
  b.text:SetJustifyH("CENTER")
  b.text:SetText(text)
  local hover, down = false, false
  local function paint()
    local key = JB:ThemeKey()
    local set = pieces(b, "skin", function(s, add)
      if key == "classic" then
        s.l = add(b:CreateTexture(nil, "BACKGROUND"))
        s.r = add(b:CreateTexture(nil, "BACKGROUND"))
        s.m = add(b:CreateTexture(nil, "BACKGROUND"))
        s.l:SetPoint("TOPLEFT")
        s.l:SetPoint("BOTTOMLEFT")
        s.l:SetWidth(12)
        s.r:SetPoint("TOPRIGHT")
        s.r:SetPoint("BOTTOMRIGHT")
        s.r:SetWidth(12)
        s.m:SetPoint("TOPLEFT", s.l, "TOPRIGHT")
        s.m:SetPoint("BOTTOMRIGHT", s.r, "BOTTOMLEFT")
        s.hl = add(b:CreateTexture(nil, "HIGHLIGHT"))
        s.hl:SetAllPoints()
        s.hl:SetTexture("Interface\\Buttons\\UI-Panel-Button-Highlight")
        s.hl:SetTexCoord(0, 0.625, 0, 0.6875)
        s.hl:SetBlendMode("ADD")
      elseif key == "modern" and not b.noNative then
        local ok, native = pcall(CreateFrame, "Button", nil, b, "UIPanelButtonTemplate")
        if ok and native then
          s.native = add(native)
          native:SetAllPoints()
          native:SetText(text)
          native:SetScript("OnClick", function(...) onClick(b, ...) end)
          return
        end
        b.noNative = true
      end
      if not s.native and not s.l then
        s.fill = add(b:CreateTexture(nil, "BACKGROUND"))
        s.fill:SetAllPoints()
        s.rim = lines(b, add, "BORDER", 0)
        if key == "modern" then
          s.shine = add(b:CreateTexture(nil, "HIGHLIGHT"))
          s.shine:SetAllPoints()
          s.shine:SetColorTexture(1, 1, 1, 0.08)
        end
      end
    end)
    b.text:SetShown(not set.native)
    if set.native then
      set.native:SetText(b.text:GetText() or "")
      return
    elseif key == "classic" then
      local file = down and "Interface\\Buttons\\UI-Panel-Button-Down" or "Interface\\Buttons\\UI-Panel-Button-Up"
      set.l:SetTexture(file)
      set.l:SetTexCoord(0, 0.09375, 0, 0.6875)
      set.m:SetTexture(file)
      set.m:SetTexCoord(0.09375, 0.53125, 0, 0.6875)
      set.r:SetTexture(file)
      set.r:SetTexCoord(0.53125, 0.625, 0, 0.6875)
      if hover then b.text:SetTextColor(1, 1, 1) else b.text:SetTextColor(GOLD[1], GOLD[2], GOLD[3]) end
    elseif key == "modern" then
      local top, bottom
      if primary then
        top, bottom = { 0.62, 0.1, 0.07, 1 }, { 0.33, 0.04, 0.03, 1 }
      else
        top, bottom = { 0.21, 0.2, 0.19, 1 }, { 0.08, 0.08, 0.08, 1 }
      end
      if down then top, bottom = bottom, top end
      gradient(set.fill, top, bottom)
      outline(set.rim, b, 0, UI.Pixel(b), BRONZE[1], BRONZE[2], BRONZE[3], hover and 1 or 0.8)
      if hover then
        b.text:SetTextColor(1, 1, 1)
      elseif primary then
        b.text:SetTextColor(GOLD[1], GOLD[2], GOLD[3])
      else
        b.text:SetTextColor(0.95, 0.92, 0.85)
      end
    else
      local r, g, bl = JB:Accent()
      if primary then
        set.fill:SetColorTexture(r, g, bl, hover and 0.34 or 0.24)
        outline(set.rim, b, 0, UI.Pixel(b), r, g, bl, 0.9)
        b.text:SetTextColor(1, 1, 1)
      else
        set.fill:SetColorTexture(1, 1, 1, hover and 0.12 or 0.08)
        outline(set.rim, b, 0, UI.Pixel(b), 0, 0, 0, 0)
        b.text:SetTextColor(0.92, 0.92, 0.94)
      end
    end
    b.text:ClearAllPoints()
    b.text:SetPoint("CENTER", down and 1 or 0, down and -1 or 0)
  end
  b:SetScript("OnEnter", function() hover = true paint() end)
  b:SetScript("OnLeave", function() hover, down = false, false paint() end)
  b:SetScript("OnMouseDown", function() down = true paint() end)
  b:SetScript("OnMouseUp", function() down = false paint() end)
  b:SetScript("OnClick", onClick)
  b.Paint = paint
  table.insert(UI.refreshers, paint)
  paint()
  return b
end

-- A checkbox with a label. get() -> boolean; set(boolean).
function UI.Check(parent, label, get, set)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(220, 18)
  b.label = UI.Text(b, 11.5)
  b.label:SetText(label)
  local hover = false
  local function paint()
    local key = JB:ThemeKey()
    local s = pieces(b, "skin", function(s, add)
      if key == "classic" then
        s.box = add(b:CreateTexture(nil, "ARTWORK"))
        s.box:SetSize(24, 24)
        s.box:SetPoint("LEFT", -4, 0)
        s.box:SetTexture("Interface\\Buttons\\UI-CheckBox-Up")
        s.tick = add(b:CreateTexture(nil, "OVERLAY"))
        s.tick:SetAllPoints(s.box)
        s.tick:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
        s.hl = add(b:CreateTexture(nil, "HIGHLIGHT"))
        s.hl:SetAllPoints(s.box)
        s.hl:SetTexture("Interface\\Buttons\\UI-CheckBox-Highlight")
        s.hl:SetBlendMode("ADD")
        s.labelX = 20
      elseif key == "modern" and hasAtlas("checkbox-minimal") and hasAtlas("checkmark-minimal") then
        s.box = add(b:CreateTexture(nil, "ARTWORK"))
        s.box:SetSize(18, 18)
        s.box:SetPoint("LEFT", -1, 0)
        s.box:SetAtlas("checkbox-minimal")
        s.tick = add(b:CreateTexture(nil, "OVERLAY"))
        s.tick:SetAllPoints(s.box)
        s.tick:SetAtlas("checkmark-minimal")
        s.labelX = 22
      elseif key == "modern" then
        s.box = add(b:CreateTexture(nil, "ARTWORK"))
        s.box:SetSize(14, 14)
        s.box:SetPoint("LEFT", 0, 0)
        s.box:SetColorTexture(0.04, 0.04, 0.05, 0.95)
        s.rim = lines(b, add, "ARTWORK", 1)
        s.tick = add(b:CreateTexture(nil, "OVERLAY"))
        s.tick:SetSize(20, 20)
        s.tick:SetPoint("CENTER", s.box, "CENTER", 1, 1)
        s.tick:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
        s.labelX = 21
      else
        s.box = add(b:CreateTexture(nil, "BORDER"))
        s.box:SetSize(13, 13)
        s.box:SetPoint("LEFT")
        s.box:SetColorTexture(1, 1, 1, 0.12)
        s.tick = add(b:CreateTexture(nil, "ARTWORK"))
        s.tick:SetSize(7, 7)
        s.tick:SetPoint("CENTER", s.box, "CENTER")
        s.labelX = 20
      end
    end)
    if key == "ellesmere" then s.tick:SetColorTexture(JB:Accent()) end
    if s.rim then
      outline(s.rim, s.box, 0, UI.Pixel(b), BRONZE[1], BRONZE[2], BRONZE[3], hover and 1 or 0.85)
    end
    s.tick:SetShown(get() and true or false)
    b.label:ClearAllPoints()
    b.label:SetPoint("LEFT", b, "LEFT", s.labelX, 0)
    if hover then b.label:SetTextColor(1, 1, 1) else b.label:SetTextColor(JB:Colour("text")) end
  end
  table.insert(UI.refreshers, paint)
  b:SetScript("OnClick", function()
    set(not get())
    UI.RefreshAll()
  end)
  b:SetScript("OnEnter", function() hover = true paint() end)
  b:SetScript("OnLeave", function() hover = false paint() end)
  paint()
  return b
end

-- A slider with a label and its value. fmt(value) -> text.
function UI.Slider(parent, label, min, max, step, fmt, get, set)
  local f = CreateFrame("Frame", nil, parent)
  f:SetSize(220, 38)
  f.label = UI.Text(f, 11.5)
  f.label:SetPoint("TOPLEFT")
  f.label:SetText(label)
  f.value = UI.Text(f, 11.5, "dim")
  f.value:SetPoint("TOPRIGHT")
  f.value:SetJustifyH("RIGHT")
  local s = CreateFrame("Slider", nil, f)
  f.slider = s
  s:SetOrientation("HORIZONTAL")
  s:SetSize(220, 12)
  s:SetMinMaxValues(min, max)
  s:SetValueStep(step)
  pcall(s.SetObeyStepOnDrag, s, true)
  local thumb = s:CreateTexture(nil, "OVERLAY")
  s:SetThumbTexture(thumb)
  local quiet = false
  local function paint()
    local key = JB:ThemeKey()
    local p = pieces(s, "skin", function(p, add)
      if key == "classic" then
        p.border = classicBorder(s, add, BORDERS.slider)
      elseif key == "modern" and hasAtlas("Minimal_SliderBar_Left") and hasAtlas("Minimal_SliderBar_Button") then
        p.left = add(s:CreateTexture(nil, "BACKGROUND"))
        p.right = add(s:CreateTexture(nil, "BACKGROUND"))
        p.middle = add(s:CreateTexture(nil, "BACKGROUND"))
        p.left:SetAtlas("Minimal_SliderBar_Left", true)
        p.right:SetAtlas("Minimal_SliderBar_Right", true)
        p.middle:SetAtlas("Minimal_SliderBar_Middle", true)
        p.left:SetPoint("LEFT")
        p.right:SetPoint("RIGHT")
        p.middle:SetPoint("TOPLEFT", p.left, "TOPRIGHT")
        p.middle:SetPoint("BOTTOMRIGHT", p.right, "BOTTOMLEFT")
        p.minimal = true
      else
        p.track = add(s:CreateTexture(nil, "BACKGROUND"))
        if key == "modern" then p.rim = lines(s, add, "BORDER", 0) end
      end
    end)
    s:ClearAllPoints()
    s:SetPoint("TOPLEFT", f.label, "BOTTOMLEFT", 0, key == "classic" and -4 or -7)
    thumb:SetVertexColor(1, 1, 1, 1)
    if key == "classic" then
      s:SetHeight(17)
      seatBorder(p.border, 0, 1)
      thumb:SetTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
      thumb:SetSize(32, 32)
    elseif p.minimal then
      s:SetHeight(16)
      thumb:SetTexCoord(0, 1, 0, 1)
      thumb:SetAtlas("Minimal_SliderBar_Button", true)
    elseif key == "modern" then
      s:SetHeight(12)
      p.track:ClearAllPoints()
      p.track:SetPoint("LEFT")
      p.track:SetPoint("RIGHT")
      p.track:SetHeight(5)
      p.track:SetColorTexture(0.03, 0.03, 0.035, 0.95)
      outline(p.rim, p.track, 0, UI.Pixel(s), BRONZE[1], BRONZE[2], BRONZE[3], 0.8)
      thumb:SetColorTexture(GOLD[1], GOLD[2], GOLD[3], 1)
      thumb:SetSize(7, 14)
    else
      s:SetHeight(12)
      p.track:ClearAllPoints()
      p.track:SetPoint("LEFT")
      p.track:SetPoint("RIGHT")
      p.track:SetHeight(3)
      p.track:SetColorTexture(1, 1, 1, 0.12)
      thumb:SetColorTexture(JB:Accent())
      thumb:SetSize(8, 12)
    end
    quiet = true
    s:SetValue(get())
    quiet = false
    f.value:SetText(fmt(get()))
  end
  table.insert(UI.refreshers, paint)
  s:SetScript("OnValueChanged", function(_, value)
    if quiet then return end
    value = math.floor(value / step + 0.5) * step
    set(value)
    f.value:SetText(fmt(get()))
  end)
  s:EnableMouseWheel(true)
  s:SetScript("OnMouseWheel", function(_, delta)
    s:SetValue(math.max(min, math.min(max, s:GetValue() + delta * step)))
  end)
  paint()
  return f
end

-- One choice among several, as a row (wrapping) of buttons. choices: { {value, text}, ... }
function UI.Choice(parent, label, choices, width, get, set)
  local f = CreateFrame("Frame", nil, parent)
  f.label = UI.Text(f, 11.5)
  f.label:SetPoint("TOPLEFT")
  f.label:SetText(label)
  local x, y, buttons = 0, -18, {}
  for _, c in ipairs(choices) do
    local b = CreateFrame("Button", nil, f)
    b.text = b:CreateFontString(nil, "OVERLAY")
    JB:SetFont(b.text, 11.5)
    b.text:SetPoint("CENTER")
    b.text:SetText(c[2])
    local w = (b.text:GetStringWidth() or 40) + 16
    if x > 0 and x + w > width then x, y = 0, y - 24 end
    b:SetSize(w, 20)
    b:SetPoint("TOPLEFT", f, "TOPLEFT", x, y)
    b.bg = b:CreateTexture(nil, "BACKGROUND")
    b.bg:SetAllPoints()
    b.rim = lines(b, function(r) return r end, "BORDER", 0)
    b.value = c[1]
    b:SetScript("OnClick", function()
      set(c[1])
      UI.RefreshAll()
    end)
    buttons[#buttons + 1] = b
    x = x + w + 4
  end
  f:SetSize(width, -y + 20)
  local function paint()
    local key = JB:ThemeKey()
    local px = UI.Pixel(f)
    for _, b in ipairs(buttons) do
      local on = b.value == get()
      if key == "classic" then
        b.bg:SetColorTexture(on and 1 or 0, on and 0.82 or 0, 0, on and 0.22 or 0.45)
        outline(b.rim, b, 0, px, on and 1 or 0.45, on and 0.82 or 0.45, on and 0 or 0.45, on and 0.7 or 0.8)
        if on then b.text:SetTextColor(GOLD[1], GOLD[2], GOLD[3]) else b.text:SetTextColor(0.85, 0.85, 0.85) end
      elseif key == "modern" then
        b.bg:SetColorTexture(BRONZE[1], BRONZE[2], BRONZE[3], on and 0.35 or 0.06)
        outline(b.rim, b, 0, px, BRONZE[1], BRONZE[2], BRONZE[3], on and 1 or 0.45)
        if on then b.text:SetTextColor(GOLD[1], GOLD[2], GOLD[3]) else b.text:SetTextColor(JB:Colour("dim")) end
      else
        b.bg:SetColorTexture(1, 1, 1, on and 0.14 or 0.05)
        outline(b.rim, b, 0, px, 0, 0, 0, 0)
        if on then b.text:SetTextColor(JB:Accent()) else b.text:SetTextColor(JB:Colour("dim")) end
      end
    end
  end
  table.insert(UI.refreshers, paint)
  paint()
  return f
end

-- A colour swatch that opens WoW's colour picker. get() -> r, g, b; set(r, g, b).
function UI.Swatch(parent, get, set)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(18, 18)
  b.edge = b:CreateTexture(nil, "BORDER")
  b.edge:SetAllPoints()
  b.edge:SetColorTexture(1, 1, 1, 0.3)
  b.fill = b:CreateTexture(nil, "ARTWORK")
  b.fill:SetPoint("TOPLEFT", 1, -1)
  b.fill:SetPoint("BOTTOMRIGHT", -1, 1)
  local function show() b.fill:SetColorTexture(get()) end
  table.insert(UI.refreshers, show)
  b:SetScript("OnClick", function()
    local r, g, bl = get()
    local function apply(nr, ng, nb)
      set(nr, ng, nb)
      UI.RefreshAll()
    end
    local picker = ColorPickerFrame
    if not picker then return end
    if picker.SetupColorPickerAndShow then
      picker:SetupColorPickerAndShow({
        r = r, g = g, b = bl, hasOpacity = false,
        swatchFunc = function() apply(picker:GetColorRGB()) end,
        cancelFunc = function(prev)
          if type(prev) == "table" and prev.r then apply(prev.r, prev.g, prev.b) else apply(r, g, bl) end
        end,
      })
    else  -- older clients
      picker.hasOpacity, picker.previousValues = false, { r, g, bl }
      picker.func = function() apply(picker:GetColorRGB()) end
      picker.cancelFunc = function() apply(r, g, bl) end
      picker:SetColorRGB(r, g, bl)
      picker:Hide()
      picker:Show()
    end
  end)
  show()
  return b
end
