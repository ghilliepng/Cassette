-- The browser: your playlists, liked songs and search, opened with the = button on the player.
--
-- Each page of 8 rows is a picture the companion draws (a "view", see Live.lua). A list's pages
-- stack up in a scrolling area and are asked for as you scroll near them; clickable rows sit
-- over each picture. Rows are 34 units high (render.ROW_H, browse.ROWS). The companion
-- remembers what each view showed, so a click names the view and row, and means the same thing
-- however long it took to arrive.
--
--  +--------------------------------------------------------------+
--  | Playlists  Saved  Liked    [ Search songs, albums, artists x] x |
--  | [cover] Name                                             >  | |
--  | [cover] Name                                             >  | |
--  | ...                                              (scrolls)    |
--  | < Back                                           ~ Shuffle    |
--  +--------------------------------------------------------------+
--
-- Playlists: ones you made or collaborate on (click to open, > to play). Saved: other people's
-- you follow; Spotify won't list their songs to apps like this, so a click plays them. Play
-- follows the Shuffle toggle (Spotify's own shuffle).

local _, JB = ...

local W, PAGE_W, ROW_H, ROWS = 360, 352, 34, 8
local HEADER, FOOTER = 30, 26
local LIST_H = ROWS * ROW_H
local H = HEADER + LIST_H + FOOTER
-- must match browse.py
local KIND = { PLAYLISTS = 1, PLAYLIST = 2, LIKED = 3, SEARCH = 4, SETUP = 5, MESSAGE = 6, SAVED = 7 }
local LISTS = { [1] = true, [2] = true, [3] = true, [4] = true, [6] = true, [7] = true }

-- Cut text to n bytes without splitting a character (the strip carries up to ~80 bytes of it).
local function cut(s, n)
  if #s <= n then return s end
  s = s:sub(1, n)
  local i = #s
  while i > 0 and s:byte(i) >= 0x80 and s:byte(i) < 0xC0 do i = i - 1 end
  if i > 0 and s:byte(i) >= 0xC0 then
    local lead = s:byte(i)
    local need = lead >= 0xF0 and 4 or lead >= 0xE0 and 3 or 2
    if #s - i + 1 < need then s = s:sub(1, i - 1) end
  end
  return s
end
JB.CutText = cut

-- A tab or a text button: the theme's tab colour, the accent (and a line under it) when active.
local function textButton(parent, text, size, onClick)
  local b = CreateFrame("Button", nil, parent)
  b.text = b:CreateFontString(nil, "OVERLAY")
  JB:SetFont(b.text, size or 12)
  b.text:SetPoint("CENTER")
  b.text:SetText(text)
  b.line = b:CreateTexture(nil, "ARTWORK")
  b.line:SetHeight(2)
  b.line:SetPoint("BOTTOMLEFT", b.text, "BOTTOMLEFT", 0, -3)
  b.line:SetPoint("BOTTOMRIGHT", b.text, "BOTTOMRIGHT", 0, -3)
  b:SetSize(b.text:GetStringWidth() + 12, 20)
  b:RegisterForClicks("LeftButtonUp")
  b:SetScript("OnClick", onClick)
  local hover = false
  function b:Paint()
    b:SetWidth(b.text:GetStringWidth() + 12)   -- the font may have changed
    if b.active then
      b.text:SetTextColor(JB:Accent())
    elseif hover then
      b.text:SetTextColor(JB:Colour("iconHover"))
    else
      b.text:SetTextColor(JB:Colour("tab"))
    end
    b.line:SetColorTexture(JB:Accent())
    b.line:SetShown(b.active and b.underline and true or false)
  end
  function b:SetActive(on)
    b.active = on and true or false
    b:Paint()
  end
  b:SetScript("OnEnter", function() hover = true b:Paint() end)
  b:SetScript("OnLeave", function() hover = false b:Paint() end)
  return b
end

-- Sending: a request that brings a new list (a tab, a search, opening a playlist, Back). Its
-- first page comes back as a new view; `page`: which page it starts on (nil: any, for Back).
function JB:BrowserCommand(cmd, arg, page)
  self:Command(cmd, arg)
  self:PollFast(2, 0.1)
  self.browserWaiting = GetTime()
  self.expectNew, self.expectPage = true, page
  self:RefreshBrowser()
end

function JB:CreateBrowser()
  local UI = self.UI
  local b = CreateFrame("Frame", "CassetteBrowser", UIParent)
  self.browser = b
  b:SetSize(W, H)
  b:SetFrameStrata("MEDIUM")
  b:SetClampedToScreen(true)
  b:EnableMouse(true)
  b:EnableMouseWheel(true)
  b:Hide()
  tinsert(UISpecialFrames, "CassetteBrowser")   -- Escape closes it

  -- header: tabs, search, close
  b.tabMine = textButton(b, "Playlists", 12.5, function() self:OpenTab(KIND.PLAYLISTS, "P") end)
  b.tabMine:SetPoint("TOPLEFT", 6, -5)
  b.tabSaved = textButton(b, "Saved", 12.5, function() self:OpenTab(KIND.SAVED, "S") end)
  b.tabSaved:SetPoint("LEFT", b.tabMine, "RIGHT", 0, 0)
  b.tabLiked = textButton(b, "Liked", 12.5, function() self:OpenTab(KIND.LIKED, "L") end)
  b.tabLiked:SetPoint("LEFT", b.tabSaved, "RIGHT", 0, 0)
  b.tabs = { b.tabMine, b.tabSaved, b.tabLiked }

  b.close = UI.Icon(b, "close", 14, function() b:Hide() end)
  b.close:SetPoint("TOPRIGHT", -8, -8)

  local box = CreateFrame("EditBox", nil, b)
  b.search = box
  box:SetSize(156, 18)
  box:SetPoint("RIGHT", b.close, "LEFT", -10, 0)
  box:SetAutoFocus(false)
  box:SetMaxBytes(200)
  JB:SetFont(box, 11.5)
  box:SetTextInsets(6, 20, 0, 0)   -- room for the clear button
  UI.Role(box, "text")
  box.hint = box:CreateFontString(nil, "OVERLAY")
  JB:SetFont(box.hint, 10.5)
  box.hint:SetPoint("LEFT", 6, 0)
  box.hint:SetPoint("RIGHT", -20, 0)   -- inside the box, clear of the clear button
  box.hint:SetWordWrap(false)          -- (cut short rather than spill out, in wider fonts)
  box.hint:SetJustifyH("LEFT")         -- where your typing starts
  box.hint:SetText("Songs, albums, artists")
  UI.Role(box.hint, "faint")
  box.clear = UI.Icon(box, "close", 10, function()
    box:SetText("")
    box:SetFocus()
  end)
  box.clear:SetPoint("RIGHT", -5, 0)
  local function hint()
    local empty = (box:GetText() or "") == ""
    box.hint:SetShown(empty and not box:HasFocus())
    box.clear:SetShown(not empty)
  end
  box:SetScript("OnEditFocusGained", hint)
  box:SetScript("OnEditFocusLost", hint)
  box:SetScript("OnTextChanged", hint)
  box:SetScript("OnEscapePressed", function() box:ClearFocus() end)
  box:SetScript("OnEnterPressed", function()
    local q = (box:GetText() or ""):gsub("^%s+", ""):gsub("%s+$", "")
    box:ClearFocus()
    if q ~= "" then self:BrowserCommand("FD", cut(q, 75), 0) end
  end)

  -- body: a scrolling area holding the list's pages
  local scroll = CreateFrame("ScrollFrame", nil, b)
  scroll:SetPoint("TOPLEFT", 4, -HEADER)
  scroll:SetSize(PAGE_W, LIST_H)
  local content = CreateFrame("Frame", nil, scroll)
  content:SetSize(PAGE_W, LIST_H)
  scroll:SetScrollChild(content)
  b.scroll, b.content, b.slots = scroll, content, {}
  b:SetScript("OnMouseWheel", function(_, delta)
    local L = self.list
    if L then L.target = L.target - delta * (L.rowH or ROW_H) * 3 end
  end)

  -- scrollbar: a thin track and a thumb you can drag
  b.track = b:CreateTexture(nil, "ARTWORK")
  b.track:SetPoint("TOPRIGHT", b, "TOPRIGHT", -3, -HEADER)
  b.track:SetSize(3, LIST_H)
  b.thumb = CreateFrame("Button", nil, b)
  b.thumb:SetWidth(7)
  b.thumb.tex = b.thumb:CreateTexture(nil, "OVERLAY")
  b.thumb.tex:SetPoint("TOPRIGHT")
  b.thumb.tex:SetPoint("BOTTOMRIGHT")
  b.thumb.tex:SetWidth(3)
  b.thumb:SetScript("OnMouseDown", function()
    local L = self.list
    if not L or not GetCursorPosition then return end
    local _, y = GetCursorPosition()
    b.drag = { y = y, from = L.target }
  end)
  b.thumb:SetScript("OnMouseUp", function() b.drag = nil end)
  b:SetScript("OnUpdate", function(_, elapsed) self:UpdateScroll(elapsed) end)

  -- messages shown instead of the list (loading, connect Spotify)
  b.msg = UI.Text(b, 12, "text")
  b.msg:SetPoint("TOP", b, "TOP", 0, -HEADER - 70)
  b.msg:SetWidth(W - 60)
  b.msg:SetJustifyH("CENTER")
  b.msg:SetSpacing(4)
  b.setup = UI.Button(b, "Set up on PC", 150, function()
    self:Command("SETUP")
    self:Print("the Connect Spotify window is open on your PC (Alt+Tab if it's behind the game).")
  end, true)
  b.setup:SetPoint("TOP", b.msg, "BOTTOM", 0, -14)

  -- footer: back, the note on Saved, shuffle
  b.back = textButton(b, "< Back", 12, function()
    local L = self.list
    if not L then return end
    if L.parent then   -- the list it came from is still here: show it now, the companion follows
      self:ShowList(L.parent)
      self:Command("BK", tostring(L.ref))
      self:PollFast(2, 0.1)
    else
      self:BrowserCommand("BK", tostring(L.ref))
    end
  end)
  b.back:SetPoint("BOTTOMLEFT", 6, 3)
  b.note = UI.Text(b, 10.5, "faint")   -- on Saved: why there's no song list
  b.note:SetPoint("BOTTOMLEFT", 10, 9)
  b.note:SetWidth(W - 98)
  b.note:SetWordWrap(false)
  b.note:SetText("Cassette can't show songs in playlists not made by you.")
  b.shuffle = UI.Icon(b, "shuffle", 15, function()
    local s = self.state
    s.shuffle = not s.shuffle   -- show it straight away; the companion confirms
    self:Command("S")
    self:RefreshBrowser()
  end, function(hover)
    if self.state.shuffle then
      if hover then return self:AccentLight() end
      return self:Accent()
    end
    if not hover then return self:Colour("dim") end
  end)
  b.shuffle:SetPoint("BOTTOMRIGHT", -72, 5)
  b.shuffleText = UI.Text(b, 11, "dim")
  b.shuffleText:SetPoint("LEFT", b.shuffle, "RIGHT", 5, 0)
  b.shuffle:HookScript("OnEnter", function()
    GameTooltip:SetOwner(b.shuffle, "ANCHOR_TOP")
    GameTooltip:SetText("Shuffle (Spotify's own)\nPlay buttons play shuffled while it's on", 1, 1, 1)
    GameTooltip:Show()
  end)
  b.shuffle:HookScript("OnLeave", function() GameTooltip:Hide() end)

  self:ApplyBrowserLook()
end

-- The theme, colours and background (from the options, and the player's background setting).
function JB:ApplyBrowserLook()
  local b = self.browser
  if not b then return end
  self.UI.Skin(b, "panel", self.db.bgAlpha or 0.88)
  self.UI.FieldSkin(b.search)
  b.track:SetColorTexture(1, 1, 1, 0.08)
  b.thumb.tex:SetColorTexture(self:Colour("dim"))
  for _, tab in ipairs(b.tabs) do tab.underline = true end
  self:PlaceBrowser()
  self:LayoutList()   -- the player's size sets the scale: line the rows up with the pages again
  self:RefreshBrowser()
end

-- Above the player, or below it when the player sits high on the screen.
function JB:PlaceBrowser()
  local b, f = self.browser, self.widget
  if not b or not f then return end
  b:SetScale(f:GetScale())
  b:ClearAllPoints()
  local gap = 4 + self.UI.Outset("bar") + self.UI.Outset("panel")
  local top = f:GetTop() or 0
  if top * f:GetEffectiveScale() > UIParent:GetHeight() * UIParent:GetEffectiveScale() * 0.6 then
    b:SetPoint("TOPLEFT", f, "BOTTOMLEFT", 0, -gap)
  else
    b:SetPoint("BOTTOMLEFT", f, "TOPLEFT", 0, gap)
  end
end

-- Show a list that's already here (a tab seen before, or the list Back returns to), at once.
function JB:ShowList(L)
  self.list, self.expectNew, self.browserWaiting = L, false, nil
  self:LayoutList()
  self:RefreshBrowser()
end

-- A tab: its list at once if it's been seen (or sent ahead), and a fresh first page from the
-- companion, which also makes it the list the companion's working on.
function JB:OpenTab(kind, code)
  local kept = self.tabLists and self.tabLists[kind]
  if kept then
    self:ShowList(kept)
    self:Command("BR", code)
    self:PollFast(2, 0.1)
  else
    self:BrowserCommand("BR", code, 0)
  end
end

function JB:ToggleBrowser()
  if not self.browser then self:CreateBrowser() end
  local b = self.browser
  if b:IsShown() then
    b:Hide()
    return
  end
  self:PlaceBrowser()
  b:Show()
  if not self.view and not self.browserWaiting and self:IsSpotify() then
    self:BrowserCommand("BR", "P", 0)
  end
  self:RefreshBrowser()
end

-- Rows with a play button: playlists. (A playlist's own "Play" row plays when clicked.)
local function hasPlay(kind)
  return kind == KIND.PLAYLISTS or kind == KIND.SAVED
end

-- A click on row i of page k (button: "play" for its play button).
function JB:BrowserClick(k, i, button)
  local L = self.list
  local pic = L and L.pics[k]
  if not pic or i > pic.rows or L.kind == KIND.MESSAGE then return end
  local row = k * ROWS + (i - 1)
  local arg = pic.n .. " " .. row .. " " .. L.kind   -- (the kind: see browse.Browser._list_of)
  if L.kind == KIND.PLAYLISTS and not button then
    self:BrowserCommand("OP", arg, 0)   -- open one of your playlists
    return
  end
  if button == "play" or L.kind == KIND.SAVED or (L.kind == KIND.PLAYLIST and row == 0) then
    self:Command(self.state.shuffle and "PS" or "PL", arg)   -- the whole playlist: shuffled or in order
  else
    self:Command("PL", arg)   -- this song (an album in search results opens)
  end
  self:PollFast(2, 0.1)   -- the song starts within a second or so: show it quickly
end

-- A page's picture and its rows (made the first time a list reaches that page).
local function slot(self, k)
  local b = self.browser
  local sl = b.slots[k]
  if sl then return sl end
  sl = { rows = {} }
  sl.tex = b.content:CreateTexture(nil, "ARTWORK")
  sl.loading = self.UI.Text(b.content, 11, "faint")
  sl.loading:SetText("Loading...")
  sl.loading:Hide()
  for i = 1, ROWS do
    local r = CreateFrame("Button", nil, b.content)
    r:SetSize(PAGE_W, ROW_H)
    r:RegisterForClicks("LeftButtonUp")
    r.hover = r:CreateTexture(nil, "HIGHLIGHT")
    r.hover:SetAllPoints()
    r.hover:SetColorTexture(1, 1, 1, 0.06)
    r.press = r:CreateTexture(nil, "OVERLAY")   -- while the mouse button is down, like the buttons
    r.press:SetAllPoints()
    r.press:SetColorTexture(1, 1, 1, 0.10)
    r.press:Hide()
    r:SetScript("OnMouseDown", function() r.press:Show() end)
    r:SetScript("OnMouseUp", function() r.press:Hide() end)
    r:HookScript("OnLeave", function() r.press:Hide() end)
    r:SetScript("OnClick", function() self:BrowserClick(k, i) end)
    r.play = self.UI.Icon(r, "play", 14, function() self:BrowserClick(k, i, "play") end)
    r.play:SetPoint("RIGHT", -10, 0)
    r:Hide()
    sl.rows[i] = r
  end
  b.slots[k] = sl
  return sl
end

local TABS = { [KIND.PLAYLISTS] = true, [KIND.SAVED] = true, [KIND.LIKED] = true }

-- A page into a list (a new list when L is nil, or when it no longer fits).
local function addPage(L, n, kind, page, pages, rows, path, size, rowH)
  if not L or L.kind ~= kind or L.pages ~= pages then
    L = { kind = kind, pages = pages, pics = {}, asked = {}, rowH = rowH, pageH = rowH * ROWS }
    L.y = page * L.pageH
    L.target = L.y
  end
  -- a page can arrive twice (asked again, or redrawn for the song now playing): the newest wins
  if L.pics[page] and L.pics[page].n > n then return L end
  if n > (L.ref or 0) then L.ref = n end
  if rows == ROWS then L.rowH, L.pageH, L.rowPx = rowH, rowH * ROWS, size[2] / rows end
  L.pics[page] = { n = n, path = path, size = size, rows = rows, rowH = rowH,
                   rowPx = rows > 0 and size[2] / rows or nil }   -- (pixels: see LayoutList)
  L.asked[page] = nil
  if page == pages - 1 then L.lastRows = rows end
  L.total = (pages - 1) * L.pageH + (L.lastRows or ROWS) * L.rowH
  return L
end

-- A new view arrived (Live.lua, in order): a list's page, a message, or "connect Spotify".
function JB:ShowView(n, kind, page, pages, rows, path, size)
  self.tabLists = self.tabLists or {}
  if kind > 16 and path and size then
    -- a tab's first page, sent ahead: kept for when you switch to it
    local base = kind - 16
    local ppu = self:PPU100() / 100
    local rowH = rows > 0 and size[2] / ppu / rows or ROW_H
    local kept = addPage(self.tabLists[base], n, base, page, pages, rows, path, size, rowH)
    self.tabLists[base] = kept
    if self.list == kept then self:LayoutList() end
    return
  end
  self.view = { n = n, kind = kind, page = page, pages = pages, rows = rows, path = path, size = size }
  if not LISTS[kind] or not path or not size then
    self.list, self.expectNew, self.browserWaiting = nil, false, nil
    self:LayoutList()
    self:RefreshBrowser()
    return
  end
  local L = self.list
  if self.expectNew and self.expectPage and page ~= self.expectPage then
    -- a page of the list before (asked for before the new one): the new list comes next
    if not L or L.kind ~= kind then return end
  end
  local ppu = self:PPU100() / 100
  local rowH = rows > 0 and size[2] / ppu / rows or ROW_H
  local new = self.expectNew or not L or L.kind ~= kind or L.pages ~= pages or kind == KIND.MESSAGE
  if new then
    local from = L
    -- a tab seen before starts from what's kept (where you'd scrolled to, its other pages)
    local kept = TABS[kind] and self.tabLists[kind]
    L = addPage(kept, n, kind, page, pages, rows, path, size, rowH)
    if L ~= kept then L.y, L.target = page * L.pageH, page * L.pageH end
    if kind == KIND.PLAYLIST and from and from.kind ~= KIND.PLAYLIST then L.parent = from end
    self.list, self.expectNew, self.browserWaiting = L, false, nil
  else
    L = addPage(L, n, kind, page, pages, rows, path, size, rowH)
    if L ~= self.list then self.list = L end
  end
  if TABS[kind] then self.tabLists[kind] = L end
  self:LayoutList()
  self:RefreshBrowser()
end

-- Place each page that's here, and its rows.
function JB:LayoutList()
  local b, L = self.browser, self.list
  if not b then return end
  for _, sl in pairs(b.slots) do
    sl.tex:Hide()
    sl.loading:Hide()
    for _, r in ipairs(sl.rows) do r:Hide() end
  end
  if not L then return end
  -- heights from the pictures' own pixels at today's scale: if the interface scale has changed
  -- since a page came (another UI addon turned on or off), its rows still line up with it
  local ppu = self:PPU100() / 100
  if L.rowPx then L.rowH, L.pageH = L.rowPx / ppu, L.rowPx / ppu * ROWS end
  L.total = (L.pages - 1) * L.pageH + (L.lastRows or ROWS) * L.rowH
  for _, pic in pairs(L.pics) do
    if pic.rowPx then pic.rowH = pic.rowPx / ppu end
  end
  b.content:SetHeight(math.max(1, L.total))
  for k, pic in pairs(L.pics) do
    local sl = slot(self, k)
    local top = k * L.pageH
    sl.tex:SetTexture(pic.path)
    sl.tex:SetSize(pic.size[1] / ppu, pic.size[2] / ppu)
    sl.tex:ClearAllPoints()
    sl.tex:SetPoint("TOPLEFT", b.content, "TOPLEFT", 0, -top)
    sl.tex:Show()
    for i, r in ipairs(sl.rows) do
      local on = i <= pic.rows and L.kind ~= KIND.MESSAGE
      r:SetShown(on)
      if on then
        r:SetHeight(pic.rowH)
        r:ClearAllPoints()
        r:SetPoint("TOPLEFT", b.content, "TOPLEFT", 0, -top - (i - 1) * pic.rowH)
        r.play:SetShown(hasPlay(L.kind))
      end
    end
  end
end

-- Every frame while open: glide towards where the wheel (or the scrollbar) sent the list, ask
-- for pages coming into view (and one either side), and keep the scrollbar in step.
function JB:UpdateScroll(elapsed)
  local b, L = self.browser, self.list
  if not L then
    b.track:Hide()
    b.thumb:Hide()
    return
  end
  local maxY = math.max(0, L.total - LIST_H)
  local thumbH = math.max(18, LIST_H * LIST_H / math.max(L.total, 1))
  if b.drag and GetCursorPosition then
    local _, y = GetCursorPosition()
    local moved = (b.drag.y - y) / b:GetEffectiveScale()
    L.target = b.drag.from + moved * maxY / math.max(1, LIST_H - thumbH)
  end
  L.target = math.max(0, math.min(maxY, L.target))
  local d = L.target - L.y
  if math.abs(d) < 0.2 or b.drag then L.y = L.target else L.y = L.y + d * math.min(1, elapsed * 14) end
  b.scroll:SetVerticalScroll(L.y)

  local first = math.floor(L.y / L.pageH)
  local last = math.floor((L.y + LIST_H - 1) / L.pageH)
  local now, waiting = GetTime(), 0
  for _, t in pairs(L.asked) do
    if now - t < 4 then waiting = waiting + 1 end
  end
  for _, p in ipairs({ first, last, last + 1, first - 1 }) do
    if p >= 0 and p < L.pages and not L.pics[p] and L.kind ~= KIND.MESSAGE then
      if (not L.asked[p] or now - L.asked[p] > 4) and waiting < 2 then
        L.asked[p] = now
        waiting = waiting + 1
        self:Command("PG", L.ref .. " " .. p .. " " .. L.kind)
        self:PollFast(2, 0.1)
      end
      if p >= first and p <= last then   -- "Loading..." where a page will be
        local sl = slot(self, p)
        sl.loading:ClearAllPoints()
        sl.loading:SetPoint("TOP", b.content, "TOPLEFT", PAGE_W / 2, -p * L.pageH - 16)
        sl.loading:Show()
      end
    end
  end

  local bar = maxY > 0
  b.track:SetShown(bar)
  b.thumb:SetShown(bar)
  if bar then
    b.thumb:SetHeight(thumbH)
    b.thumb:ClearAllPoints()
    b.thumb:SetPoint("TOPRIGHT", b, "TOPRIGHT", -3, -HEADER - (LIST_H - thumbH) * L.y / maxY)
  end
end

function JB:RefreshBrowser()
  local b, v, s, L = self.browser, self.view, self.state, self.list
  if not b then return end
  local waiting = self.browserWaiting and GetTime() - self.browserWaiting < 15
  local kind = v and v.kind
  local message
  if not s.connected and not s.everConnected then
    message = "The Cassette companion isn't running.\nStart it on your PC, then /reload if WoW was already open."
  elseif not self:IsSpotify() then
    message = ("Playlists, liked songs and search work with Spotify only, for now.\n"
      .. "The player works with %s."):format(self:MusicName())
    kind = nil
  elseif kind == KIND.SETUP then
    message = "Connect your Spotify account to browse your playlists,\nliked songs and search here. "
      .. "Spotify allows this with Premium."
  elseif not L then
    message = waiting and "Loading..." or ""
  end
  -- (every SetShown gets a real true/false: some clients reject anything else)
  b.msg:SetText(message or "")
  b.msg:SetShown(message ~= nil)
  b.setup:SetShown(kind == KIND.SETUP and s.connected == true)
  b.scroll:SetShown((L and not message) and true or false)
  b.content:SetAlpha(waiting and 0.45 or 1)   -- dimmed while the next list is on its way
  local lk = L and L.kind
  b.tabMine:SetActive(lk == KIND.PLAYLISTS or lk == KIND.PLAYLIST)
  b.tabSaved:SetActive(lk == KIND.SAVED)
  b.tabLiked:SetActive(lk == KIND.LIKED)
  b.back:SetShown(lk == KIND.PLAYLIST)
  b.back:Paint()
  b.note:SetShown(lk == KIND.SAVED and not message)
  b.shuffle:Paint()
  b.shuffleText:SetText(s.shuffle and "Shuffle on" or "Shuffle off")
  if s.shuffle then b.shuffleText:SetTextColor(self:Accent()) else b.shuffleText:SetTextColor(self:Colour("dim")) end
end
