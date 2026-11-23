"""The music app (Spotify, YouTube Music or Apple Music: see players.py) through Windows' own
media controls, and its volume through the Windows mixer.

Windows' media session (the one behind the volume pop-up) gives the song, artist, album, cover,
length, position and play state, and takes play/pause/next/previous/shuffle. It works with any
account and needs no sign-in. Volume is the app's slider in the Windows mixer, so game sound is
never touched.
"""
import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, field, replace

from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
from winrt.windows.storage.streams import Buffer, InputStreamOptions

import players

PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


@dataclass
class Player:
    available: bool = False      # the music app has a media session (it's open and has played)
    key: str = ""                # identifies the song: title | artist | album
    title: str = ""
    artist: str = ""
    album: str = ""
    cover: bytes = field(default=b"", repr=False)
    duration: float = 0.0        # seconds
    position: float = 0.0        # seconds, at `sample`
    sample: float = 0.0          # time.time() of `position`
    playing: bool = False
    shuffle: bool = False
    volume: int = 100            # the app's slider in the Windows mixer, 0-100
    muted: bool = False

    def position_now(self):
        if self.playing:
            return min(self.duration or 1e9, self.position + time.time() - self.sample)
        return self.position


def _seconds(td):
    return td.total_seconds() if td is not None else 0.0


class Spotify(threading.Thread):
    """Watches the music app about 3 times a second; calls on_change(player, reason) when
    something the widget shows has changed. (Named for the first app it followed.)"""

    def __init__(self, on_change, log, app=players.DEFAULT):
        super().__init__(daemon=True, name="spotify")
        self.on_change, self.log = on_change, log
        self.app = players.known(app)   # which app to follow: a players.NAMES key
        self.app_id = None              # the media session followed (its app ID), for the mixer
        self.player = Player()
        self.loop = asyncio.new_event_loop()
        self.session = None
        self.lock = threading.Lock()
        self.opened_at = 0.0

    def set_app(self, app):
        """Follow another app from the next look (about a third of a second). The one left behind
        is paused if it was playing, so the two don't play at once; the new one isn't started
        (that's the player's play button)."""
        app = players.known(app)
        if app != self.app:
            old, playing = self.session, self.player.playing
            self.app = app
            self.log(f"following {players.NAMES[app]}")
            if old is not None and playing:
                asyncio.run_coroutine_threadsafe(self._pause(old), self.loop)

    async def _pause(self, session):
        try:
            await session.try_pause_async()
            self.log("paused the app left behind")
        except Exception as e:
            self.log(f"couldn't pause the app left behind: {e}")

    # -- reading --
    def run(self):
        self.loop.run_until_complete(self._main())

    async def _main(self):
        manager = None
        while True:
            try:
                if manager is None:
                    manager = await Manager.request_async()
                await self._poll(manager)
            except Exception as e:  # Spotify closing mid-call and the like: try again next time
                self.log(f"media session read failed: {e}")
                manager = None
                await asyncio.sleep(2)
            await asyncio.sleep(0.3)

    async def _poll(self, manager):
        found = {}
        for s in manager.get_sessions():
            app_id = s.source_app_user_model_id or ""
            if players.rank(self.app, app_id):
                found[app_id] = (s, s.get_playback_info().playback_status == PLAYING)
        app_id = players.pick(self.app, [(a, v[1]) for a, v in found.items()], self.app_id)
        session = found[app_id][0] if app_id else None
        if app_id != self.app_id:
            self.log(f"music from {app_id}" if app_id else f"no {players.NAMES[self.app]} to follow")
        self.session, self.app_id = session, app_id
        old = self.player
        if session is None:
            if old.available:
                self._set(replace(Player(), volume=old.volume, muted=old.muted), "closed")
            return
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        info = session.get_playback_info()
        now = time.time()
        playing = info.playback_status == PLAYING
        duration = max(0.0, _seconds(timeline.end_time) - _seconds(timeline.start_time))
        # Windows gives the position as of its last update; carry it forward to now
        position = _seconds(timeline.position)
        if playing and timeline.last_updated_time is not None:
            position += max(0.0, now - timeline.last_updated_time.timestamp())
        position = min(position, duration) if duration else position
        title, artist, album = props.title or "", props.artist or "", props.album_title or ""
        key = f"{title}|{artist}|{album}"
        new = replace(old, available=True, key=key, title=title, artist=artist, album=album,
                      duration=duration, position=position, sample=now, playing=playing,
                      shuffle=bool(info.is_shuffle_active))
        reason = None
        if key != old.key:
            new.cover = b""
            reason = "song"
        elif not old.available:
            reason = "opened"
        elif playing != old.playing:
            reason = "play" if playing else "pause"
        elif new.shuffle != old.shuffle:
            reason = "shuffle"
        elif abs(duration - old.duration) > 1:
            reason = "length"
        elif abs(position - old.position_now()) > 2.5:
            reason = "seek"
        # The cover: fetched when the song changes, then checked once more 1.5 s later (right at a
        # change Windows can still hand out the previous song's picture), and retried a few times
        # if it wasn't there yet.
        if key != old.key:
            self.cover_checks = [now, now + 1.5, now + 3, now + 6]
        checks = getattr(self, "cover_checks", [])
        if checks and now >= checks[0] and props.thumbnail is not None and title:
            checks.pop(0)
            cover = await self._cover(props)  # new.cover is the old one, or empty for a new song
            if cover and cover != new.cover:
                new.cover = cover
                reason = reason or "cover"
        self._set(new, reason)

    async def _cover(self, props):
        if props.thumbnail is None:
            return b""
        stream = await props.thumbnail.open_read_async()
        size = int(stream.size)
        if not size:
            return b""
        buf = Buffer(size)
        got = await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
        return bytes(got)

    def _set(self, player, reason):
        with self.lock:
            self.player = player
        if reason:
            self.on_change(player, reason)

    def set_volume(self, volume, muted):
        with self.lock:
            changed = (volume, muted) != (self.player.volume, self.player.muted)
            self.player = replace(self.player, volume=volume, muted=muted)
            player = self.player
        if changed:
            self.on_change(player, "volume")

    # -- controls --
    def command(self, name):
        asyncio.run_coroutine_threadsafe(self._command(name), self.loop)

    async def _command(self, name):
        s = self.session
        if s is None:
            if name in ("toggle", "play") and time.time() - self.opened_at > 10:
                self.opened_at = time.time()   # (one window, however often play is pressed)
                players.open_app(self.app, self.log)
            return
        if name == "toggle":
            await s.try_toggle_play_pause_async()
        elif name == "next":
            await s.try_skip_next_async()
        elif name == "prev":
            await s.try_skip_previous_async()
        elif name == "shuffle":
            if s.get_playback_info().controls.is_shuffle_enabled:
                await s.try_change_shuffle_active_async(not self.player.shuffle)
            else:
                self.log(f"{players.NAMES[self.app]} doesn't take shuffle from other apps")

    def open_spotify(self):
        """Spotify itself (the in-game browser plays on Spotify, whichever app is followed)."""
        exe = os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe")
        try:
            os.startfile(exe if os.path.exists(exe) else "spotify:")
            self.log("opened Spotify")
        except OSError as e:
            self.log(f"couldn't open Spotify: {e}")


class Mixer(threading.Thread):
    """The music app's volume in the Windows mixer (in a browser, the whole browser's).

    `volume` (0-100) is the player's own setting, the one the widget shows. `duck` (0-1) scales
    it down without changing that number, to dip the music while Spoken reads. A dip fades in
    and out, and only lasts as long as the game keeps asking for it (DUCK_LEASE seconds per
    request), so the music can't stay quiet if WoW closes or the message to end it is missed.
    While dipped, the player's volume is kept in a file, so even a crash can't leave it low.
    """

    STEP = 5
    DUCK_LEASE = 40

    def __init__(self, spotify, log, duck_file):
        super().__init__(daemon=True, name="mixer")
        self.spotify, self.log, self.duck_file = spotify, log, duck_file
        self.jobs = []
        self.wake = threading.Event()
        self.volume, self.muted, self.duck = None, False, 1.0
        self.duck_until = 0.0

    def do(self, job, *args):
        self.jobs.append((job, args))
        self.wake.set()

    def run(self):
        import comtypes
        comtypes.CoInitialize()
        self._recover()
        while True:
            self.wake.wait(1.0)
            self.wake.clear()
            while self.jobs:
                job, args = self.jobs.pop(0)
                try:
                    getattr(self, "_" + job)(*args)
                except Exception as e:
                    self.log(f"mixer {job} failed: {e}")
            try:
                if self.duck < 0.999 and time.time() > self.duck_until:
                    self.log("music dip ran out (the game stopped asking): back to full")
                    self._set_duck(100)
                self._read()
            except Exception as e:
                self.log(f"mixer read failed: {e}")

    def _sessions(self):
        from pycaw.pycaw import AudioUtilities
        app, app_id = self.spotify.app, self.spotify.app_id
        return [s for s in AudioUtilities.GetAllSessions()
                if s.Process and players.owns(app, app_id, s.Process.name())]

    def _read(self):
        sessions = self._sessions()
        if not sessions:
            return
        v = sessions[0].SimpleAudioVolume
        level = v.GetMasterVolume()
        muted = bool(v.GetMute())
        if self.duck >= 0.999:  # while dipped the mixer level isn't the player's volume
            self.volume = round(level * 100)
        self.muted = muted
        self.spotify.set_volume(self.volume if self.volume is not None else 100, muted)

    def _apply(self, sessions=None):
        level = max(0.0, min(1.0, (self.volume if self.volume is not None else 100) / 100 * self.duck))
        for s in sessions if sessions is not None else self._sessions():
            s.SimpleAudioVolume.SetMasterVolume(level, None)

    def _step(self, direction):
        if self.volume is None:
            self._read()
        self.volume = max(0, min(100, (self.volume or 0) + direction * self.STEP))
        if self.muted and direction > 0:
            self._mute(False)
        self._apply()

    def _set(self, volume):
        self.volume = max(0, min(100, int(volume)))
        self._apply()

    def _mute(self, on=None):
        on = (not self.muted) if on is None else on
        for s in self._sessions():
            s.SimpleAudioVolume.SetMute(1 if on else 0, None)
        self.muted = on

    # -- the dip --
    def _set_duck(self, percent):
        """Dip to `percent` of the player's volume (100: no dip), fading over a moment.
        Asking again for the same dip just extends it."""
        target = max(0.0, min(1.0, int(percent) / 100))
        self.duck_until = time.time() + self.DUCK_LEASE if target < 0.999 else 0.0
        if abs(target - self.duck) < 0.001:
            return
        if self.duck >= 0.999:  # starting a dip: note the player's volume first
            if self.volume is None:
                self._read()
            self._remember(self.volume)
        start, sessions = self.duck, self._sessions()
        steps = 12 if target < start else 28   # about 0.4 s down, 1 s back up
        for i in range(1, steps + 1):
            self.duck = start + (target - start) * i / steps
            self._apply(sessions)
            time.sleep(0.035)
        self.duck = target
        if target >= 0.999:
            self._remember(None)

    def _remember(self, volume):
        try:
            if volume is None:
                if os.path.exists(self.duck_file):
                    os.remove(self.duck_file)
            else:
                with open(self.duck_file, "w", encoding="utf-8") as f:
                    json.dump({"volume": volume}, f)
        except OSError:
            pass

    def _recover(self):
        """If the companion stopped in the middle of a dip, put the player's volume back."""
        try:
            with open(self.duck_file, encoding="utf-8") as f:
                volume = int(json.load(f)["volume"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        self.volume = volume
        try:
            self._apply()
            self.log(f"put the music's volume back to {volume} after an interrupted dip")
        except Exception as e:
            self.log(f"couldn't put the volume back: {e}")
        self._remember(None)

    def restore_now(self):
        """From another thread, when quitting: end any dip at once."""
        import comtypes
        comtypes.CoInitialize()
        if self.duck < 0.999:
            self.duck = 1.0
            self._apply()
            self._remember(None)
