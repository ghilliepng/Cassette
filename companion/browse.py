"""The in-game browser's lists: your playlists (Mine), other people's you've saved (Saved), a
playlist's songs, liked songs, search results.

The addon asks for a list and a page; this fetches what that page needs from Spotify, draws it
as one picture (render.page) and publishes it as a "view" (live.publish_view). Each view
remembers which list and page it showed, so a click on row 3 of view 17 means the same thing
however long the message took to arrive.

Spotify's rules for apps like this (Development Mode, 2026): the songs of playlists you don't
own or collaborate on can't be listed (403), search gives 10 results a request, and there's no
song radio or recommendations. So a song is always played inside something that carries on - its
album, or your liked songs - after which Spotify's own autoplay continues with related music.
"""
import queue
import random
import re
import threading
import time
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import render
from web import SpotifyError

ROWS = 8
# must match Browser.lua
KIND_PLAYLISTS, KIND_PLAYLIST, KIND_LIKED, KIND_SEARCH, KIND_SETUP, KIND_MESSAGE, KIND_SAVED = 1, 2, 3, 4, 5, 6, 7
AHEAD = 16  # added to a tab's kind: its first page, sent ahead for an instant switch later


def clock(ms):
    s = int((ms or 0) / 1000)
    return f"{s // 60}:{s % 60:02d}"


def smallest_image(images, at_least=48):
    """The smallest picture that's still at least `at_least` px (or the only one there is)."""
    images = [i for i in (images or []) if i.get("url")]
    if not images:
        return None
    sized = sorted((i for i in images if i.get("width")), key=lambda i: i["width"])
    for i in sized:
        if i["width"] >= at_least:
            return i["url"]
    return (sized[-1] if sized else images[0])["url"]


def song_row(track):
    if not track:
        return {"title": "Unavailable", "subtitle": "", "right": ""}
    artists = ", ".join(a.get("name", "") for a in track.get("artists") or [])
    return {"title": track.get("name", ""), "subtitle": artists, "right": clock(track.get("duration_ms")),
            "image_url": smallest_image((track.get("album") or {}).get("images")), "uri": track.get("uri"),
            "key": f"{track.get('name', '')}\t{artists}"}


def _now(value):
    """What's playing as a 4-tuple (track, context, relinked-from, name+artists)."""
    value = tuple(value or ())
    return (value + (None, None, None, None))[:4]


def is_playing(row, now):
    """Is this row the song (or playlist, or album) playing now?"""
    uri, key, now = row.get("uri"), row.get("key"), _now(now)
    return bool((uri and uri in now[:3]) or (key and key == now[3]))


def song_count(playlist):
    return (playlist.get("items") or playlist.get("tracks") or {}).get("total")


def play_playlist(web, playlist, shuffle, open_spotify):
    """Play a playlist from the top in order, or shuffled from a random song."""
    offset = None
    total = song_count(playlist)
    if shuffle and total:
        offset = {"position": random.randrange(total)}
    web.play(context_uri=playlist["uri"], offset=offset, open_spotify=open_spotify, shuffle=bool(shuffle))


class Blocks:
    """Items fetched from Spotify in blocks, on demand, and kept."""

    def __init__(self, fetch, size):
        self.fetch, self.size = fetch, size  # fetch(offset, limit) -> (items, total)
        self.items, self.total = {}, None

    def get(self, start, n):
        if self.total is None:
            self._load(0)
        end = min(start + n, self.total)
        for i in range(start, end):
            if i not in self.items:
                self._load(i - i % self.size)
        return [self.items.get(i) for i in range(start, end)]

    def _load(self, offset):
        items, total = self.fetch(offset, self.size)
        self.total = total
        for k, item in enumerate(items):
            self.items[offset + k] = item


class Playlists:
    """Mine (made by you or shared with you to edit) or Saved (other people's you follow)."""

    def __init__(self, web, playlists, saved):
        self.web, self.items, self.saved = web, playlists, saved
        self.kind = KIND_SAVED if saved else KIND_PLAYLISTS

    def count(self):
        return len(self.items)

    def rows(self, start, n):
        out = []
        for p in self.items[start:start + n]:
            songs = song_count(p)
            sub = f"{songs} songs" if songs is not None else ""
            if self.saved:
                owner = (p.get("owner") or {}).get("display_name") or "Spotify"
                sub = f"by {owner}" + (f"  -  {sub}" if sub else "")
            out.append({"title": p.get("name", ""), "subtitle": sub, "image_url": smallest_image(p.get("images")),
                        "uri": p.get("uri")})
        return out

    def play(self, i, open_spotify, shuffle=False):
        if 0 <= i < len(self.items):
            play_playlist(self.web, self.items[i], shuffle, open_spotify)

    def open(self, i):
        if self.saved or not 0 <= i < len(self.items):
            return None  # Spotify won't list their songs: the addon plays these instead
        return PlaylistSongs(self.web, self.items[i])


class PlaylistSongs:
    """Row 0 plays the whole playlist (in order, or shuffled); then its songs."""
    kind = KIND_PLAYLIST

    def __init__(self, web, playlist):
        self.web, self.p = web, playlist
        self.listable = True
        self.blocks = Blocks(self._fetch, 50)

    def _fetch(self, offset, limit):
        try:
            r = self.web.playlist_items(self.p["id"], offset, limit)
        except SpotifyError as e:
            if e.status in (403, 404):
                self.listable = False
                return [], 0
            raise
        return [(x.get("item") or x.get("track")) for x in r.get("items", [])], r.get("total", 0)

    def count(self):
        self.blocks.get(0, 1)
        return 1 + (self.blocks.total if self.listable else 1)

    def rows(self, start, n):
        out = []
        total = song_count(self.p)
        if start == 0:
            out.append({"title": f"Play {self.p.get('name', '')}", "style": "action",
                        "subtitle": f"{total} songs" if total is not None else ""})
            n -= 1
        songs = self.blocks.get(max(0, start - 1), n)
        if not self.listable:
            if start == 0:
                out.append({"style": "note", "title": "Cassette can't show songs in playlists not made by you. "
                                                      "Play it with the row above."})
            return out
        out += [song_row(t) for t in songs]
        return out

    def play(self, i, open_spotify, shuffle=False):
        if i == 0 or not self.listable:
            play_playlist(self.web, self.p, shuffle, open_spotify)
        else:  # from this song on; shuffle stays as it is
            self.web.play(context_uri=self.p["uri"], offset={"position": i - 1}, open_spotify=open_spotify)

    def open(self, i):
        return None


class Liked:
    kind = KIND_LIKED

    def __init__(self, web):
        self.web = web
        self.blocks = Blocks(self._fetch, 50)

    def _fetch(self, offset, limit):
        r = self.web.liked(offset, limit)
        return [(x.get("track") or x.get("item")) for x in r.get("items", [])], r.get("total", 0)

    def count(self):
        self.blocks.get(0, 1)
        return self.blocks.total or 0

    def rows(self, start, n):
        return [song_row(t) for t in self.blocks.get(start, n)]

    def play(self, i, open_spotify, shuffle=False):
        t = (self.blocks.get(i, 1) or [None])[0]
        if not t or not t.get("uri"):
            return
        user = self.web.data.get("user_id")
        try:  # inside your Liked Songs, from this one: carries on through all of them
            self.web.play(context_uri=f"spotify:user:{user}:collection", offset={"uri": t["uri"]},
                          open_spotify=open_spotify)
        except SpotifyError as e:
            if e.status not in (400, 403):
                raise
            uris = [x["uri"] for x in self.blocks.get(i, 100) if x and x.get("uri")]
            self.web.play(uris=uris, open_spotify=open_spotify)

    def open(self, i):
        return None


def _norm(text):
    return re.sub(r"[^0-9a-z]+", " ", (text or "").lower()).strip()


def album_row(album):
    artists = ", ".join(a.get("name", "") for a in album.get("artists") or [])
    year = (album.get("release_date") or "")[:4]
    sub = "  -  ".join(x for x in ("Album", artists, year) if x)
    return {"title": album.get("name", ""), "subtitle": sub, "image_url": smallest_image(album.get("images")),
            "uri": album.get("uri")}


class SearchSongs:
    """Search results: albums whose name matches the search first, then songs, then the other
    albums. A click on a song plays it; on an album, opens it."""
    kind = KIND_SEARCH

    def __init__(self, web, query):
        self.web, self.query = web, query
        self.blocks = Blocks(self._fetch, 10)  # Spotify allows 10 results a request
        self._albums = None

    def _fetch(self, offset, limit):
        r = (self.web.search(self.query, "track", offset) or {}).get("tracks") or {}
        return [t for t in r.get("items", [])], min(r.get("total", 0), 100)

    def albums(self):
        """(matching albums, the rest), fetched once."""
        if self._albums is None:
            try:
                r = (self.web.search(self.query, "album", 0) or {}).get("albums") or {}
                found = [a for a in r.get("items", []) if a]
            except SpotifyError:
                found = []
            q = _norm(self.query)
            top = [a for a in found if q and (q in _norm(a.get("name")) or _norm(a.get("name")) in q)][:3]
            self._albums = (top, [a for a in found if a not in top])
        return self._albums

    def count(self):
        top, rest = self.albums()
        self.blocks.get(0, 1)
        return len(top) + (self.blocks.total or 0) + len(rest)

    def item(self, i):
        """("album", album) or ("song", track) at row i, or (None, None)."""
        top, rest = self.albums()
        if i < len(top):
            return "album", top[i]
        i -= len(top)
        self.blocks.get(0, 1)
        songs = self.blocks.total or 0
        if i < songs:
            return "song", (self.blocks.get(i, 1) or [None])[0]
        i -= songs
        return ("album", rest[i]) if 0 <= i < len(rest) else (None, None)

    def rows(self, start, n):
        out = []
        for i in range(start, min(start + n, self.count())):
            what, x = self.item(i)
            out.append(album_row(x) if what == "album" else song_row(x))
        if not out and start == 0:
            out = [{"style": "note", "title": f'Nothing found for "{self.query}".'}]
        return out

    def open(self, i):
        what, x = self.item(i)
        return AlbumSongs(self.web, x) if what == "album" and x else None

    def play(self, i, open_spotify, shuffle=False):
        what, t = self.item(i)
        if what != "song" or not t or not t.get("uri"):
            return
        album = (t.get("album") or {}).get("uri")
        if album:  # inside its album, from this song: then Spotify's autoplay carries on
            try:
                self.web.play(context_uri=album, offset={"uri": t["uri"]}, open_spotify=open_spotify)
                return
            except SpotifyError as e:
                if e.status not in (400, 403):
                    raise
        self.web.play(uris=[t["uri"]], open_spotify=open_spotify)


class AlbumSongs:
    """An album (from search): row 0 plays all of it (in order, or shuffled); then its songs."""
    kind = KIND_PLAYLIST

    def __init__(self, web, album):
        self.web, self.a = web, album
        self.blocks = Blocks(self._fetch, 50)

    def _fetch(self, offset, limit):
        r = self.web.album_tracks(self.a["id"], offset, limit) or {}
        return list(r.get("items", [])), r.get("total", 0)

    def count(self):
        self.blocks.get(0, 1)
        return 1 + (self.blocks.total or 0)

    def rows(self, start, n):
        out = []
        cover = smallest_image(self.a.get("images"))
        if start == 0:
            total = self.a.get("total_tracks")
            out.append({"title": f"Play {self.a.get('name', '')}", "style": "action",
                        "subtitle": f"{total} songs" if total else "", "uri": self.a.get("uri")})
            n -= 1
        for t in self.blocks.get(max(0, start - 1), n):
            row = song_row(t)
            row["image_url"] = row.get("image_url") or cover  # an album's songs come without pictures
            out.append(row)
        return out

    def play(self, i, open_spotify, shuffle=False):
        if i == 0:
            total = self.a.get("total_tracks") or 0
            offset = {"position": random.randrange(total)} if shuffle and total else None
            self.web.play(context_uri=self.a["uri"], offset=offset, open_spotify=open_spotify, shuffle=bool(shuffle))
        else:  # from this song on; shuffle stays as it is
            self.web.play(context_uri=self.a["uri"], offset={"position": i - 1}, open_spotify=open_spotify)

    def open(self, i):
        return None


class Browser:
    """Runs the addon's browser commands one at a time on its own thread (they wait on Spotify)."""

    FRESH = 120  # seconds a fetched list is reused before it's fetched again

    def __init__(self, web, live, open_spotify, ui_font, log):
        self.web, self.live, self.open_spotify, self.ui_font, self.log = web, live, open_spotify, ui_font, log
        self.jobs = queue.Queue()
        self.views = OrderedDict()  # view number -> (list, page)
        self.stack = []             # lists you've opened, for Back
        self.thumbs = OrderedDict()  # picture URL -> bytes
        self.thumbs_lock = threading.Lock()
        self.playlists_cache = (0.0, None)
        self.lists = {}             # "P" / "S" / "L" -> (fetched at, list): switching tabs is instant
        self.sent_ahead = {}        # "P" / "S" / "L" -> the list whose first page was sent ahead
        self.ahead = True           # send the other tabs' first pages ahead (tests turn it off)
        self.prefetched = 0.0
        self.now = _now(None)       # what's playing (see _now): its rows show in the accent colour
        self.accent = render.GREEN_RGB
        self.look = "ellesmere"     # the addon's theme
        self.last_browse = 0.0
        self.ready = OrderedDict()  # pages drawn ahead (the next and previous): turning to one is instant
        self.ready_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(6)
        threading.Thread(target=self._run, daemon=True, name="browser").start()

    def set_look(self, accent, font, look="ellesmere"):
        """The accent colour, font and theme chosen in the game (the LOOK message)."""
        self.accent, self.ui_font, self.look = tuple(accent), font, look
        with self.ready_lock:
            self.ready.clear()

    def song_changed(self):
        """Spotify moved to another song: if you've been browsing lately, redraw the page with the
        new song (and playlist) in the accent colour."""
        if self.web.signed_in() and time.time() - self.last_browse < 600:
            self.do("playing")

    def _playing(self, tries=0):
        """Redraw the pages of the list you're in that show the song (or playlist) that was
        playing or is now: lists scroll, so several pages can be on show. Spotify's web side can
        lag a moment behind the song change, so ask again a few times if it hasn't caught up."""
        now = _now(self.web.now_playing())
        if now == self.now:
            if tries < 4:
                timer = threading.Timer(0.8, self.do, ("playing", tries + 1))
                timer.daemon = True
                timer.start()
            return
        old, self.now = self.now, now
        if not self.stack:
            return
        lst = self.stack[-1]
        pages = sorted({p for (l, p) in self.views.values() if l is lst})
        for page in pages[-8:]:
            if any(is_playing(r, old) or is_playing(r, now) for r in lst.rows(page * ROWS, ROWS)):
                self._show(lst, page, ahead=False)

    def _list(self, which):
        fetched, lst = self.lists.get(which, (0.0, None))
        if lst is None or time.time() - fetched > self.FRESH:
            lst = Liked(self.web) if which == "L" else self._playlists(saved=which == "S")
            self.lists[which] = (time.time(), lst)
        return lst

    def _prefetch(self):
        """Fetch the other tabs' first pages (and their pictures) in the background, so the first
        switch to each is quick too."""
        if time.time() - self.prefetched < self.FRESH:
            return
        self.prefetched = time.time()

        def warm():
            try:
                for which in ("P", "S", "L"):
                    self._fetch_thumbs(self._list(which).rows(0, ROWS))
            except Exception as e:
                self.log(f"browser prefetch: {e}")
            self.do("send_ahead")
        threading.Thread(target=warm, daemon=True, name="prefetch").start()

    def do(self, job, *args):
        self.jobs.put((job, args))

    def _run(self):
        while True:
            job, args = self.jobs.get()
            try:
                getattr(self, "_" + job)(*args)
            except SpotifyError as e:
                self.log(f"browser {job}: {e}")
                if e.status == 401 or e.reason == "not_signed_in":
                    self._show_setup()
                else:
                    self._message(e.advice())
            except Exception as e:
                import traceback
                self.log(f"browser {job} crashed: " + traceback.format_exc().replace("\n", " | "))
                self._message(f"Something went wrong ({type(e).__name__}).")

    def _all_playlists(self):
        fetched, items = self.playlists_cache
        if items is None or time.time() - fetched > self.FRESH:
            items, offset = [], 0
            while offset < 500:
                r = self.web.playlists(offset, 50)
                page = [p for p in r.get("items", []) if p]
                items += page
                offset += 50
                if offset >= r.get("total", 0) or not page:
                    break
            self.playlists_cache = (time.time(), items)
        return items

    def _playlists(self, saved):
        me = self.web.data.get("user_id")
        mine = lambda p: bool((p.get("owner") or {}).get("id") == me or p.get("collaborative"))  # noqa: E731
        items = [p for p in self._all_playlists() if mine(p) != saved]
        return Playlists(self.web, items, saved)

    # -- commands from the addon --
    def _browse(self, which):
        if not self.web.signed_in():
            return self._show_setup()
        lst = self._list(which if which in ("S", "L") else "P")
        self.stack = [lst]
        if time.time() - self.last_browse > 60:  # coming back to the browser: what's playing now?
            try:
                self.now = _now(self.web.now_playing())
            except SpotifyError:
                pass
        self._show(lst, 0)
        self._prefetch()

    def _send_ahead(self):
        """Send each tab's first page that hasn't been (the lists are fetched by _prefetch), so
        switching to it is instant."""
        if not self.ahead:
            return
        current = self.stack[0] if self.stack else None
        for which in ("P", "S", "L"):
            fetched, lst = self.lists.get(which, (0.0, None))
            if lst is None or lst is current or self.sent_ahead.get(which) is lst:
                continue
            im, page, pages, nrows = self._render(lst, 0)
            view = self.live.publish_view(im, lst.kind + AHEAD, 0, pages, nrows)
            if view:
                self.views[view] = (lst, 0)
                self.sent_ahead[which] = lst

    def _page(self, view, page, kind=None):
        lst = self._list_of(view, kind)
        if lst:
            self._show(lst, page)

    def _open(self, view, row, kind=None):
        lst = self._list_of(view, kind)
        if lst is None:
            return
        sub = lst.open(row)
        if sub:
            self.stack.append(sub)
            self._show(sub, 0)

    def _play(self, view, row, shuffle=False, kind=None):
        lst = self._list_of(view, kind)
        if lst and lst.kind == KIND_SEARCH:
            sub = lst.open(row)  # an album among the results: show its songs
            if sub:
                self.stack.append(sub)
                self._show(sub, 0)
                return
        if lst:
            asked = time.time()
            lst.play(row, self.open_spotify, shuffle)
            # the song changing answers this; if it doesn't (the same song again), say we heard
            timer = threading.Timer(2.0, self.live.ack, (asked,))
            timer.daemon = True
            timer.start()

    def _back(self, view):
        if len(self.stack) > 1:
            self.stack.pop()
        if self.stack:
            lst = self.stack[-1]
            last = next((p for v, (l, p) in reversed(self.views.items()) if l is lst), 0)
            self._show(lst, last)

    def _search(self, query):
        if not self.web.signed_in():
            return self._show_setup()
        lst = SearchSongs(self.web, query)
        self.stack = [lst]
        self._show(lst, 0)

    # -- publishing a page --
    TABS = {KIND_PLAYLISTS: "P", KIND_SAVED: "S", KIND_LIKED: "L"}

    def _list_of(self, view, kind=None):
        """The list a view showed. A view this companion doesn't know (it restarted while the
        addon kept the list) is fine for the tabs: the addon says which kind it was, and the tab's
        list is opened again."""
        entry = self.views.get(view)
        if entry is not None:
            return entry[0]
        if kind in self.TABS and self.web.signed_in():
            self.log(f"browser: view {view} is from before a restart: using the {self.TABS[kind]} tab's list")
            lst = self._list(self.TABS[kind])
            self.stack = [lst]
            return lst
        self.log(f"browser: view {view} is unknown (the companion restarted?)")
        self._message("That list is out of date: pick it again (Playlists, Saved or Liked).")
        return None

    def _render(self, lst, page):
        """Fetch and draw one page: (picture, page, pages, rows)."""
        total = lst.count()
        pages = max(1, (total + ROWS - 1) // ROWS)
        page = max(0, min(page, pages - 1))
        rows = lst.rows(page * ROWS, ROWS)
        for r in rows:
            r["playing"] = is_playing(r, self.now)
        self._fetch_thumbs(rows)
        im = render.page(rows, self.live.ppu(), self.ui_font,
                            play_buttons=lst.kind in (KIND_PLAYLISTS, KIND_SAVED), accent=self.accent,
                            look=self.look)
        return im, page, pages, len(rows)

    def _key(self, lst, page):
        return id(lst), page, self.now, self.live.ppu(), self.accent, self.ui_font, self.look

    def _show(self, lst, page, ahead=True):
        with self.ready_lock:
            got = self.ready.pop(self._key(lst, page), None)
        im, page, pages, nrows = got or self._render(lst, page)
        view = self.live.publish_view(im, lst.kind, page, pages, nrows)
        self.last_browse = time.time()
        if view:
            self.views[view] = (lst, page)
            while len(self.views) > 600:
                self.views.popitem(last=False)
        if ahead:
            self._draw_ahead(lst, page, pages)

    def _draw_ahead(self, lst, page, pages):
        """Draw the next and previous pages in the background, so turning to them is instant."""
        def work():
            for p in (page + 1, page - 1):
                key = self._key(lst, p)
                if not 0 <= p < pages:
                    continue
                with self.ready_lock:
                    if key in self.ready:
                        continue
                try:
                    drawn = self._render(lst, p)
                except Exception as e:
                    self.log(f"browser: drawing page {p + 1} ahead failed: {e}")
                    continue
                with self.ready_lock:
                    self.ready[key] = drawn
                    while len(self.ready) > 12:
                        self.ready.popitem(last=False)
        threading.Thread(target=work, daemon=True, name="draw-ahead").start()

    def _show_setup(self):
        self.live.publish_view(None, KIND_SETUP, 0, 1, 0)

    def _message(self, text):
        self.live.publish_view(render.message_page(text, self.live.ppu(), self.ui_font, self.look),
                               KIND_MESSAGE, 0, 1, 1)

    def _fetch_thumbs(self, rows):
        def get(url):
            with self.thumbs_lock:
                if url in self.thumbs:
                    return self.thumbs[url]
            try:
                with urllib.request.urlopen(url, timeout=8) as r:
                    data = r.read()
            except Exception:
                data = b""
            with self.thumbs_lock:
                self.thumbs[url] = data
                while len(self.thumbs) > 400:
                    self.thumbs.popitem(last=False)
            return data
        urls = [r.get("image_url") for r in rows]
        for r, data in zip(rows, self.pool.map(lambda u: get(u) if u else b"", urls)):
            r["image"] = data
