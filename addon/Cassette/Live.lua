-- PC -> game: reading what the companion sends.
--
-- WoW only sees files that existed when the game (or the last /reload) started, and reads each
-- file once, keeping its copy until the next /reload. So the companion keeps pools of
-- placeholder files in live\ and fills each in just before it's read, once:
--
--   m<k>          mail, read in turn (every 4 s; faster after a click and near a song's end).
--                 Holds the number of the newest record.
--   r<n>_<f>      record n, fields 0-6: art, length (s), position (s), when (time() mod 4096),
--                 flags (1 playing, 2 shuffle, 4 muted, 8 Spotify open, volume x 16, 2048 Spotify
--                 account connected), view, checksum.
--   cv/ti/ar<a>   art a: cover picture, title strip, artist strip.
--   v<n>_<f>      view n, a page of the browser, fields 0-4: kind, page, pages, rows, checksum;
--                 pg<n> is its picture.
--
-- Numbers travel as picture sizes: a texture with one anchor and no size takes its file's
-- size, and value v is the v-th size in SIZES below. Reading takes about 0.1 s, and only works
-- on textures that are shown (alpha 0 is fine). Readers show sentinel.tga (65 x 1, a size no
-- number has) between reads, so a fresh size can't be mistaken for a leftover one.
--
-- The addon tells the companion its session number and how far it has got in each pool with
-- every message (Strip.lua); the companion only writes beyond that, and the checksum includes
-- the session number, so leftovers from earlier sessions are ignored.
--
-- No "still here" messages: between messages the mail is read at a pace the companion can work
-- out from the clock - at least one every IDLE seconds, counted from the time and mail number in
-- the last message (skipping ahead if WoW was held up) - so it always knows where to write.

local _, JB = ...

local LIVE = "Interface\\AddOns\\Cassette\\live\\"
local SENTINEL = JB.MEDIA .. "sentinel"
local MAIL, RECORDS, ART, VIEWS = 15000, 1500, 600, 1000   -- must match the companion (live.py)
local IDLE = 4                                            -- must match the companion
JB.MAIL, JB.RECORDS, JB.ART, JB.VIEWS = MAIL, RECORDS, ART, VIEWS

JB.nonce = (time() % 4095) + 1
JB.mailCursor, JB.nextRecord, JB.nextArt, JB.nextView = 0, 1, 1, 1
local applied = 0          -- newest record applied
local readingRecord = nil  -- record being read now
local rejected = {}        -- records that turned out to be another session's: never retried
local appliedView, wantView = 0, 0   -- browser pages: shown up to, announced up to
local viewJobs = {}                   -- view -> { tries, tried, loading, data or skip }

-- A short diagnostic log, saved with the settings (CassetteDB.debug) at /reload or logout, and
-- read statistics for /tape status.
JB.debugLog = {}
JB.stats = { reads = 0, slow = 0, failed = 0, slowest = 0 }
function JB:Log(fmt, ...)
  local log = self.debugLog
  log[#log + 1] = ("%.1f "):format(GetTime() - self.startTime) .. fmt:format(...)
  if #log > 300 then table.remove(log, 1) end
end

-- Runs fn; an error is written to the diagnostic log instead of stopping the reading loop (an
-- error there every frame would silently stop all reading).
local function safely(what, fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok then
    JB.stats.errors = (JB.stats.errors or 0) + 1
    JB:Log("ERROR in %s: %s", what, tostring(err))
  end
  return ok
end
JB.Safely = safely

--------------------------------------------------------------------------------
-- Readers
--------------------------------------------------------------------------------

-- no parent: keeps working when the interface is hidden (Alt+Z)
local host = CreateFrame("Frame", "CassetteReaders", nil)
host:SetFrameStrata("BACKGROUND")
host:SetPoint("BOTTOMLEFT", nil, "BOTTOMLEFT", 0, 0)
host:SetSize(1, 1)

local free = {}

local function takeReader(alpha)
  local t = table.remove(free)
  if not t then
    t = host:CreateTexture(nil, "BACKGROUND")
    t:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", 0, 0)  -- one anchor, no size: sized by its file
    t:SetTexture(SENTINEL)
  end
  -- Number files and the sentinel are fully transparent, so they're read at full alpha (shown
  -- textures load reliably). Pictures are read at alpha 0, which still loads them.
  t:SetAlpha(alpha)
  return t
end

local function sizeOf(t)
  local w, h = t:GetSize()
  return math.floor((w or 0) + 0.5), math.floor((h or 0) + 0.5)
end

-- The sizes numbers use, in order: value v is the v-th. WoW misreads a 6 x 1 picture (every
-- browser page carrying the value 5 failed its checksum), so no size with width 6, height 6, or
-- six pixels in all (the same file length) is used. Must match tga.py.
local SIZES, VALUES = {}, {}
do
  for h = 1, 67 do
    for w = 1, 64 do
      if w ~= 6 and h ~= 6 and w * h ~= 6 and #SIZES < 4096 then
        SIZES[#SIZES + 1] = { w, h }
        VALUES[w * 100 + h] = #SIZES - 1
      end
    end
  end
end
function JB.NumberSize(v) return SIZES[v + 1] end   -- (for tests)

local function decode(size)
  return VALUES[size[1] * 100 + size[2]] or -1
end

local jobs = {}

-- Reads the pixel sizes of the files at `paths`, then calls done({ {w, h}, ... }), or done(nil)
-- if they don't all load within `timeout` seconds. `pictures`: true, or { [index] = true }, for
-- visible images, which are read unseen.
local function read(paths, done, timeout, pictures)
  local job = { paths = paths, done = done, readers = {}, stage = 1, t0 = GetTime(), timeout = timeout or 4 }
  for i = 1, #paths do
    local picture = pictures == true or (type(pictures) == "table" and pictures[i])
    job.readers[i] = takeReader(picture and 0 or 1)
  end
  jobs[#jobs + 1] = job
end

local function step(job)
  if job.stage == 1 then   -- wait until every reader shows the sentinel, then load the files
    for _, t in ipairs(job.readers) do
      local w, h = sizeOf(t)
      if w ~= 65 or h ~= 1 then return false end
    end
    for i, t in ipairs(job.readers) do t:SetTexture(job.paths[i]) end
    job.stage = 2
    return false
  end
  local sizes = {}
  for i, t in ipairs(job.readers) do
    local w, h = sizeOf(t)
    if w < 1 or h < 1 or (w == 65 and h == 1) then return false end
    sizes[i] = { w, h }
  end
  job.sizes = sizes
  return true
end

--------------------------------------------------------------------------------
-- Records and art
--------------------------------------------------------------------------------

function JB:ApplyRecord(v)
  local s = self.state
  local flags = v[5]
  s.playing = flags % 2 == 1
  s.shuffle = math.floor(flags / 2) % 2 == 1
  s.muted = math.floor(flags / 4) % 2 == 1
  s.available = math.floor(flags / 8) % 2 == 1
  s.volume = math.floor(flags / 16) % 128
  s.account = math.floor(flags / 2048) % 2 == 1   -- Spotify account connected (browser works)
  s.duration = v[2]
  local age = (time() - v[4]) % 4096   -- seconds since the companion took the position
  if age > 600 then age = 0 end
  s.position = v[3] + (s.playing and age or 0)
  if s.duration > 0 and s.position > s.duration then s.position = s.duration end
  s.anchor = GetTime()
  s.connected, s.everConnected, s.waitingSince, s.probeSince = true, true, nil, nil
  if v[1] ~= s.art then
    s.art = v[1]
    if s.art > 0 then
      self.nextArt = math.max(self.nextArt, s.art + 1)
      self:LoadArt(s.art)
    end
  end
  if v[6] > wantView then   -- new browser pages: read them all (scrolling can bring several)
    if wantView == 0 and appliedView == 0 then
      appliedView = v[6] - 1        -- first news since loading: just the newest
    elseif v[6] - appliedView > 12 then
      appliedView = v[6] - 12       -- far behind: the last few
    end
    wantView = v[6]
    self.nextView = math.max(self.nextView, wantView + 1)
    for n = appliedView + 1, wantView do
      if not viewJobs[n] then self:ReadView(n) end
    end
  end
  safely("refreshing the bar", self.RefreshWidget, self)
  if self.RefreshBrowser then safely("refreshing the browser", self.RefreshBrowser, self) end
end

-- A record that doesn't load in time isn't lost: the next mail still names it (or a newer one),
-- and it's read again. That's safe because the companion never changes a record once written.
function JB:ReadRecord(r)
  readingRecord = r
  local paths = {}
  for f = 0, 6 do paths[#paths + 1] = LIVE .. "r" .. r .. "_" .. f end
  read(paths, function(sizes)
    if readingRecord == r then readingRecord = nil end
    if not sizes then
      self:Log("record %d didn't load in time; will try again", r)
      return
    end
    if r <= applied then return end
    local v = {}
    for i = 1, 7 do v[i] = decode(sizes[i]) end
    if (v[1] + v[2] + v[3] + v[4] + v[5] + v[6] + self.nonce) % 4096 ~= v[7] then
      rejected[r] = true   -- left over from another session
      self:Log("record %d is from another session", r)
      return
    end
    applied = r
    self:Log("record %d applied (art %d, %s)", r, v[1], v[5] % 2 == 1 and "playing" or "paused")
    self:ApplyRecord(v)
  end, 4)
end

local loadingArt, artTried = nil, 0

function JB:LoadArt(a)
  loadingArt, artTried = a, GetTime()
  local paths = { LIVE .. "cv" .. a, LIVE .. "ti" .. a, LIVE .. "ar" .. a }
  read(paths, function(sizes)
    if loadingArt == a then loadingArt = nil end
    if sizes then
      self:ShowArt(a, paths, sizes)
    else
      self:Log("art %d didn't load in time; will try again", a)
    end
  end, 6, true)
end

-- A browser page: its numbers and its picture, read together (pages feel quicker that way).
-- Pages are shown in the order they were published, whatever order they load in; one that
-- never loads is skipped after three tries (retried from the driver).
function JB:ReadView(n)
  local job = viewJobs[n] or { tries = 0 }
  viewJobs[n] = job
  job.loading, job.tried, job.tries = true, GetTime(), job.tries + 1
  local pic = LIVE .. "pg" .. n
  local paths = {}
  for f = 0, 4 do paths[#paths + 1] = LIVE .. "v" .. n .. "_" .. f end
  paths[6] = pic
  read(paths, function(sizes)
    job.loading = false
    if n <= appliedView then
      viewJobs[n] = nil
      return
    end
    if not sizes then
      if job.tries >= 2 then
        job.skip = true
        self:Log("view %d never loaded; skipped", n)
      else
        self:Log("view %d didn't load in time; will try again", n)
      end
    else
      local v = {}
      for i = 1, 5 do v[i] = decode(sizes[i]) end
      local ps = sizes[6]
      if (v[1] + v[2] + v[3] + v[4] + self.nonce) % 4096 ~= v[5] then
        job.skip = true
        self:Log("view %d is from another session", n)
      elseif v[1] ~= 5 and v[4] > 0 and (ps[1] < 64 or ps[2] < v[4] * 8) then
        -- not the page drawn for it (read too early?): WoW keeps what it read, so asking again
        -- for this file can't help; the browser asks for the page again instead
        job.skip = true
        self:Log("view %d's picture is %dx%d, not a page of %d rows; skipped", n, ps[1], ps[2], v[4])
      else
        job.data = { v[1], v[2], v[3], v[4], pic, sizes[6] }
      end
    end
    self:ApplyViews()
  end, 6, { [6] = true })
end

function JB:ApplyViews()
  while appliedView < wantView do
    local n = appliedView + 1
    local job = viewJobs[n]
    if not job or not (job.data or job.skip) then return end
    appliedView = n
    viewJobs[n] = nil
    local d = job.data
    if d and not job.shown then
      self:Log("view %d shown (kind %d, page %d/%d)", n, d[1], d[2] + 1, d[3])
      if d[1] == 5 then   -- "connect Spotify": no picture
        self:ShowView(n, d[1], d[2], d[3], d[4])
      else
        self:ShowView(n, d[1], d[2], d[3], d[4], d[5], d[6])
      end
    end
  end
  -- more pages of the list on show needn't wait behind one that's slow to load
  local L = self.list
  if L and not self.expectNew then
    for n, job in pairs(viewJobs) do
      local d = job.data
      if d and not job.shown and d[1] == L.kind and d[3] == L.pages then
        job.shown = true
        self:Log("view %d shown early (page %d/%d)", n, d[2] + 1, d[3])
        self:ShowView(n, d[1], d[2], d[3], d[4], d[5], d[6])
      end
    end
  end
end

--------------------------------------------------------------------------------
-- Polling the mail
--------------------------------------------------------------------------------

local polling, nextPoll, fastUntil, rushUntil = false, 0, 0, 0

-- Read the mail often for a while: after a click, the answer comes within a second or so.
-- interval 0.1 ("rush") for browser pages, which should feel instant; 0.25 otherwise.
function JB:PollFast(seconds, interval)
  local now = GetTime()
  if interval and interval < 0.25 then
    rushUntil = math.max(rushUntil, now + (seconds or 2))
  end
  fastUntil = math.max(fastUntil, now + (seconds or 3))
  nextPoll = math.min(nextPoll, now + (interval or 0.15))
end

local function poll(now)
  local s = JB.state
  if JB.mailCursor >= MAIL or JB.nextRecord >= RECORDS or JB.nextArt >= ART or JB.nextView >= VIEWS then
    if not s.exhausted then
      s.exhausted = true
      JB:RefreshWidget()
    end
    return
  end
  local interval = IDLE
  local pos = JB:Position(true)
  if now < rushUntil then
    interval = 0.1
  elseif now < fastUntil then
    interval = 0.25
  elseif s.playing and s.duration > 0 and pos > s.duration - 1.5 and pos < s.duration + 8 then
    interval = 0.5   -- the song is about to end: catch the next one quickly
  end
  nextPoll = now + interval
  -- Keep the pace the companion counts on: never behind one mail per IDLE seconds since the
  -- last message (a loading screen or a slow read would otherwise leave us behind).
  if JB.anchorMail then
    local pace = JB.anchorMail + math.floor((time() - JB.anchorTime) / IDLE)
    if pace > JB.mailCursor then
      JB:Log("mail %d -> %d to keep pace", JB.mailCursor, pace)
      JB.mailCursor = pace
    end
  end
  polling = true
  local k = JB.mailCursor
  JB.mailCursor = k + 1
  read({ LIVE .. "m" .. k }, function(sizes)
    polling = false
    if not sizes then
      JB:Log("mail %d didn't load in time", k)
      return
    end
    local r = decode(sizes[1])
    if r >= RECORDS then return end
    if r >= JB.nextRecord then JB.nextRecord = r + 1 end
    -- newer than what's shown: read it (again, if an earlier try didn't load in time)
    if r > applied and not rejected[r] and readingRecord ~= r then
      JB:Log("mail %d names record %d", k, r)
      JB:ReadRecord(r)
    end
  end, 4)
end

local function checkConnection(now)
  local s = JB.state
  if not s.connected then return end
  if s.probeSince then
    -- we asked quietly and still heard nothing: now say so
    if now - s.probeSince > 8 then
      JB:Log("no answer from the companion, even to a check")
      s.connected, s.waitingSince, s.probeSince = false, nil, nil
      JB:RefreshWidget()
      JB:Send("H")   -- say where we are (more every 30 s while it lasts)
    end
  elseif (s.waitingSince and now - s.waitingSince > 8)
      or (s.playing and s.duration > 0 and JB:Position(true) > s.duration + 15) then
    -- a click went unanswered, or a song should have ended long ago with no news. Usually an
    -- answer just went missing: ask quietly first and keep showing the song meanwhile.
    JB:Log("no answer yet (waiting %.1f s): checking", s.waitingSince and now - s.waitingSince or -1)
    s.probeSince, s.waitingSince = now, nil
    JB:Send("H")
    JB:PollFast(4)
  end
end

local driver = CreateFrame("Frame", nil, host)
local lastFrame = GetTime()
driver:SetScript("OnUpdate", function()
  local now = GetTime()
  -- slow frames, and what was being read at the time (is a stutter Cassette's doing?)
  local frame = now - lastFrame
  lastFrame = now
  if frame > 0.08 and JB.started then
    JB.stats.hitches = (JB.stats.hitches or 0) + 1
    local reading = {}
    for _, job in ipairs(jobs) do reading[#reading + 1] = tostring(job.paths[#job.paths]):match("[^\\]*$") end
    if #reading > 0 then   -- (only when Cassette was loading something: other stutters aren't ours)
      JB:Log("slow frame: %d ms (reading: %s)", frame * 1000, table.concat(reading, ", "))
    end
  end
  for i = #jobs, 1, -1 do
    local job = jobs[i]
    local stepped, ok = pcall(step, job)
    if not stepped then
      JB:Log("ERROR reading %s: %s", tostring(job.paths[1]), tostring(ok))
      ok, job.t0 = false, -1e9   -- give up on this read
    end
    if ok or now - job.t0 > job.timeout then
      table.remove(jobs, i)
      local took = now - job.t0
      local st = JB.stats
      st.reads = st.reads + 1
      if not ok then
        st.failed = st.failed + 1
        local missing = {}
        for k, t in ipairs(job.readers) do
          local w, h = sizeOf(t)
          if w < 1 or h < 1 or (w == 65 and h == 1) then missing[#missing + 1] = job.paths[k]:match("[^\\]+$") end
        end
        JB:Log("read gave up after %.1f s (%s, waiting for %s: %s)", took, job.paths[1]:match("[^\\]+$"),
          job.stage == 1 and "readers to clear" or "files to load", table.concat(missing, " "))
      elseif took > 1 then
        st.slow = st.slow + 1
        JB:Log("slow read: %.1f s (%s)", took, job.paths[1]:match("[^\\]+$"))
      end
      if ok and took > st.slowest then st.slowest = took end
      -- before the readers move on, so their files stay loaded
      safely("handling " .. tostring(job.paths[1]):match("[^\\]*$"), job.done, ok and job.sizes or nil)
      for _, t in ipairs(job.readers) do
        t:SetTexture(SENTINEL)
        free[#free + 1] = t
      end
    end
  end
  if JB.started and not polling and now >= nextPoll then
    if not safely("poll", poll, now) then polling = false end
  end
  -- art that didn't load in time: try again (WoW has usually finished loading it by then)
  local s = JB.state
  if s.art > 0 and JB.widget and JB.widget.shownArt ~= s.art and not loadingArt and now - artTried > 2 then
    safely("art", JB.LoadArt, JB, s.art)
  end
  -- browser pages that didn't load in time: again
  for n = appliedView + 1, math.min(wantView, appliedView + 12) do
    local job = viewJobs[n]
    if not job or (not job.loading and not job.data and not job.skip and now - job.tried > 1.5) then
      safely("view", JB.ReadView, JB, n)
    end
  end
  safely("connection check", checkConnection, now)
end)

--------------------------------------------------------------------------------
-- Commands and start-up
--------------------------------------------------------------------------------

-- A button press: send it, then look for the answer quickly.
function JB:Command(cmd, arg)
  self:Send(cmd, arg)
  self:PollFast(5)
  self:Log("command %s%s (mail %d, applied %d)", cmd, arg and (" " .. arg) or "", self.mailCursor, applied)
  if not self.state.waitingSince then self.state.waitingSince = GetTime() end
end

function JB:StartLive(isReload)
  -- A /reload clears WoW's copies of the files, so the pools start over. After logging in, it
  -- isn't certain they were cleared, so carry on from where the last session got to.
  local c = self.db.cursors
  if c and not isReload and c.view and c.mail < MAIL * 0.8 and c.record < RECORDS * 0.8
      and c.art < ART * 0.8 and c.view < VIEWS * 0.8 then
    self.mailCursor, self.nextRecord, self.nextArt, self.nextView = c.mail, c.record, c.art, c.view
  end
  self:PollFast(10)
  -- "I'm here, and this is where I've got to" - only until the companion answers, or after
  -- losing touch with it. Never while all is well: each message flashes the strip.
  C_Timer.After(0.5, function() self:Send("H") end)
  C_Timer.NewTicker(3, function()
    local s = self.state
    if s.connected then return end
    local every = (not s.everConnected and GetTime() - self.startTime < 60) and 3 or 30
    if GetTime() - (self.lastSent or 0) >= every then self:Send("H") end
  end)
end

function JB:SaveCursors()
  self.db.cursors = { mail = self.mailCursor, record = self.nextRecord, art = self.nextArt, view = self.nextView }
  self.db.debug = self.debugLog   -- for troubleshooting: last 300 events of the session
  self.db.debugStats = self.stats
end
