-- Dipping the music while Spoken reads.
--
-- Spoken tells other addons when its audio changes (Spoken:RegisterCallback("AUDIO_CHANGED")),
-- and Spoken:GetNowPlaying() returns the line being read (nil when it's quiet or holding a line
-- back). Each line says which part of Spoken it's from (clip.source.key) and whether it has a
-- voice at all (clip.silent). So the music dips when a voiced line from a chosen part starts,
-- stays down for as long as Spoken keeps reading - whether or not the quest window is still
-- open - and comes back up a moment after, or straight away if you pause or mute Spoken.
--
-- The companion fades Spotify down to db.duckLevel % of its volume and back. Each request only
-- holds for 40 s there (so a missed "back up" can't leave the music low), so while a long
-- reading goes on the addon repeats it every 25 s. Each is a tiny one-pixel flash (Strip.lua).

local _, JB = ...

local RENEW = 25
local LONGEST = 600   -- a dip that has lasted 10 minutes without a break ends anyway
local ducked, since, gaveUp, lastSent = false, 0, false, 0
local quietSince = nil   -- when Spoken last went quiet (nil while it's reading)
JB.ducked = false

local function spoken()
  local S = _G.Spoken
  if type(S) == "table" and type(S.GetNowPlaying) == "function" then return S end
end

-- Spoken's parts ("sources"), and whether their lines dip the music. Ambient NPC chatter in
-- cities and camps goes on almost without a break, so it doesn't; the rest is narration meant
-- for you. A part Cassette doesn't know yet dips.
JB.DUCK_SOURCES = {
  quests = true,      -- quest text
  gossip = true,      -- what NPCs say when you talk to them
  readables = true,   -- books, letters, plaques
  places = true,      -- zone lore when you arrive somewhere
  bosses = true,      -- boss stories
  chatter = false,    -- ambient lines NPCs say around you
}

function JB:DipsFor(key)
  local chosen = self.db.duckSources and self.db.duckSources[key]
  if chosen == nil then chosen = self.DUCK_SOURCES[key] end
  return chosen ~= false
end

-- Is Spoken reading something out loud right now that should dip the music?
local function speaking()
  local S = spoken()
  if not S then return false end
  local ok, clip = pcall(S.GetNowPlaying, S)
  if not ok or type(clip) ~= "table" then return false end
  if clip.silent then return false end   -- words on screen only, or muted: nothing to hear
  local source = type(clip.source) == "table" and clip.source.key
  if source and not JB:DipsFor(source) then return false end
  local okP, paused = pcall(S.IsPaused, S)
  if okP and paused then return false end
  local okM, muted = pcall(S.IsMuted, S)
  if okM and muted then return false end
  return true
end

local function setDucked(on)
  if on == ducked then return end
  ducked, JB.ducked = on, on
  if on then since = GetTime() end
  lastSent = GetTime()
  JB:Send("D", tostring(on and JB.db.duckLevel or 100))
  JB:RefreshWidget()
end

-- Called on every change Spoken reports, and twice a second regardless. Works from timestamps,
-- not timers: it's called far more often than the wait it measures.
function JB:UpdateDuck()
  if not self.db or not self.db.duck then
    gaveUp, quietSince = false, nil
    setDucked(false)
    return
  end
  local now = GetTime()
  if speaking() then
    quietSince = nil
    if gaveUp then return end
    if ducked and now - since > LONGEST then
      gaveUp = true        -- don't dip again until Spoken has really been quiet
      setDucked(false)
      self:Print("the music had been dipped for 10 minutes without a break, so it's back to full.")
      return
    end
    setDucked(true)
    return
  end
  -- Quiet. Back up only once it has stayed quiet for a moment: Spoken pauses briefly between
  -- lines, and the music shouldn't bob up and down.
  quietSince = quietSince or now
  if now - quietSince >= self.db.duckHold then
    gaveUp = false
    setDucked(false)
  end
end

local function hook()
  local S = spoken()
  if not S or type(S.RegisterCallback) ~= "function" or JB.duckHooked then return end
  JB.duckHooked = true
  local function changed() JB:UpdateDuck() end
  for _, event in ipairs({ "AUDIO_CHANGED", "CLIP_STARTED", "CLIP_STOPPED", "QUEUE_EMPTY" }) do
    pcall(S.RegisterCallback, S, event, changed)
  end
end

function JB:StartDuck()
  hook()
  C_Timer.NewTicker(0.5, function()
    hook()              -- in case Spoken loaded late
    self:UpdateDuck()   -- in case a callback was missed
    if ducked and GetTime() - lastSent > RENEW then
      lastSent = GetTime()
      self:Send("D", tostring(self.db.duckLevel))   -- still reading: keep the dip going
    end
  end)
end

function JB:SetDuckLevel(percent)
  self.db.duckLevel = math.max(0, math.min(90, math.floor(percent + 0.5)))
  if ducked then
    lastSent = GetTime()
    self:Send("D", tostring(self.db.duckLevel))
  end
end

function JB:HasSpoken()
  return spoken() ~= nil
end
