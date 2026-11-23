"""Checks the in-game browser's lists (browse) against a fake Spotify: no network, no WoW.
Run with the companion's Python:  companion\\.venv\\Scripts\\python.exe tools\\test_browse.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "companion"))

import browse  # noqa: E402
from web import SpotifyError  # noqa: E402

FONT = r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns\EllesmereUI\media\fonts\Expressway.TTF"


def track(i):
    return {"name": f"Song {i}", "uri": f"spotify:track:{i}", "duration_ms": 180000 + i * 1000,
            "artists": [{"name": "Band"}], "album": {"uri": f"spotify:album:{i // 10}", "images": []}}


class FakeWeb:
    def __init__(self, signed_in=True):
        self.data = {"user_id": "me"}
        self._signed = signed_in
        self.played = []
        self.refuse = set()  # context kinds to refuse with 400 ("collection", "album")
        self.mine = {"id": "p1", "name": "Mine", "uri": "spotify:playlist:p1", "owner": {"id": "me"},
                     "items": {"total": 20}, "images": []}
        self.theirs = {"id": "p2", "name": "Daily Mix", "uri": "spotify:playlist:p2",
                       "owner": {"id": "spotify", "display_name": "Spotify"}, "items": {"total": 50}, "images": []}

    def signed_in(self):
        return self._signed

    playing = (None, None)
    fetches = 0

    def now_playing(self):
        return self.playing

    def playlists(self, offset, limit):
        allp = [self.mine, self.theirs] + [dict(self.mine, id=f"x{i}", name=f"List {i}", uri=f"spotify:playlist:x{i}")
                                           for i in range(10)]
        return {"items": allp[offset:offset + limit], "total": len(allp)}

    def playlist_items(self, pid, offset, limit):
        if pid == "p2":
            raise SpotifyError(403, "forbidden")
        return {"items": [{"item": track(i)} for i in range(offset, min(20, offset + limit))], "total": 20}

    def liked(self, offset, limit):
        self.fetches += 1
        return {"items": [{"track": track(i)} for i in range(offset, min(155, offset + limit))], "total": 155}

    ALBUMS = [{"id": "a1", "name": "Count Your Blessings", "uri": "spotify:album:cyb", "total_tracks": 12,
               "artists": [{"name": "Bring Me The Horizon"}], "release_date": "2006-10-30", "images": []},
              {"id": "a2", "name": "Something Else", "uri": "spotify:album:else", "total_tracks": 9,
               "artists": [{"name": "Band"}], "release_date": "2010", "images": []}]

    def search(self, query, kind, offset):
        if kind == "album":
            return {"albums": {"items": self.ALBUMS if query == "count your blessings" else []}}
        if query == "nothing":
            return {"tracks": {"items": [], "total": 0}}
        return {"tracks": {"items": [track(i) for i in range(offset, min(16, offset + 10))], "total": 16}}

    def album_tracks(self, aid, offset, limit):
        return {"items": [dict(track(i), album=None) for i in range(offset, min(12, offset + limit))], "total": 12}

    def play(self, context_uri=None, uris=None, offset=None, open_spotify=None, shuffle=None):
        if context_uri and any(k in context_uri for k in self.refuse):
            raise SpotifyError(400, "bad_request")
        self.played.append(dict(context=context_uri, uris=len(uris) if uris else None, offset=offset, shuffle=shuffle))


class FakeLive:
    def __init__(self):
        self.views, self.acks = [], 0

    def ppu(self):
        return 1.2

    def publish_view(self, image, kind, page, pages, rows):
        self.views.append(dict(kind=kind, page=page, pages=pages, rows=rows, size=image.size if image else None))
        return len(self.views)

    def ack(self, since):
        self.acks += 1


failed = False


def check(label, ok):
    global failed
    print(("PASS " if ok else "FAIL ") + label)
    failed |= not ok


def run(b, job, *args):
    b.do(job, *args)
    deadline = time.time() + 10
    while not b.jobs.empty() and time.time() < deadline:
        time.sleep(0.02)
    time.sleep(0.1)


def main():
    web, live = FakeWeb(), FakeLive()
    b = browse.Browser(web, live, lambda: None, FONT, print)
    b.ahead = False  # (sending the other tabs' first pages ahead has its own check below)

    run(b, "browse", "P")
    v = live.views[-1]
    check(f"Mine: your 11 playlists in 2 pages ({v})", v["kind"] == 1 and v["pages"] == 2 and v["rows"] == 8)
    run(b, "browse", "S")
    v = live.views[-1]
    check(f"Saved: the 1 someone else's ({v})", v["kind"] == 7 and v["pages"] == 1 and v["rows"] == 1)
    saved_view = len(live.views)
    n = len(live.views)
    run(b, "open", saved_view, 0)
    check("a saved playlist doesn't open (no songs to show)", len(live.views) == n)
    run(b, "play", saved_view, 0, True)
    p = web.played[-1]
    check(f"shuffling a saved one: its context, a random start, shuffle on ({p})",
          p["context"] == "spotify:playlist:p2" and p["shuffle"] is True and 0 <= p["offset"]["position"] < 50)

    run(b, "browse", "P")
    mine_view = len(live.views)
    run(b, "play", mine_view, 0, False)
    check("playing one of yours in order: from the top, shuffle off",
          web.played[-1] == dict(context="spotify:playlist:p1", uris=None, offset=None, shuffle=False))
    run(b, "page", mine_view, 1)
    check("page 2 has the last 3", live.views[-1]["rows"] == 3 and live.views[-1]["page"] == 1)

    run(b, "browse", "P")
    run(b, "open", len(live.views), 0)
    v = live.views[-1]
    check("opening your playlist: Play row + 20 songs = 3 pages", v["kind"] == 2 and v["pages"] == 3 and v["rows"] == 8)
    songs_view = len(live.views)
    run(b, "play", songs_view, 0, True)
    check("the Play row's shuffle: shuffled from a random song", web.played[-1]["shuffle"] is True and web.played[-1]["offset"])
    run(b, "play", songs_view, 3)
    check("a song row plays from that song, shuffle left alone",
          web.played[-1] == dict(context="spotify:playlist:p1", uris=None, offset={"position": 2}, shuffle=None))
    run(b, "back", songs_view)
    check("Back returns to Mine", live.views[-1]["kind"] == 1)

    run(b, "browse", "L")
    v = live.views[-1]
    check("liked: 155 songs in 20 pages", v["kind"] == 3 and v["pages"] == 20 and v["rows"] == 8)
    liked_view = len(live.views)
    run(b, "play", liked_view, 40)
    check("a liked song plays inside your Liked Songs, from that song",
          web.played[-1] == dict(context="spotify:user:me:collection", uris=None, offset={"uri": "spotify:track:40"}, shuffle=None))
    web.refuse.add("collection")
    run(b, "play", liked_view, 40)
    check("...or, if Spotify refuses that, as a list from that song on", web.played[-1]["uris"] == 100)

    # turning pages: the next one was drawn ahead, so it needs nothing from Spotify
    run(b, "browse", "L")
    time.sleep(1.0)  # the background draws page 2 (and fetches its covers)
    before = web.fetches
    with b.ready_lock:
        ahead = len(b.ready)
    run(b, "page", len(live.views), 1)
    check(f"page 2 was drawn ahead ({ahead} ready) and shown without fetching", ahead >= 1 and web.fetches == before)

    # the playing song shows in the accent colour; a song change while browsing redraws the page
    shown = {}
    real_page = browse.render.page

    def spy(rows, *a, **k):
        marked = [r["title"] for r in rows if r.get("playing")]
        shown["playing"] = marked
        shown.setdefault("all", []).append(marked)
        return real_page(rows, *a, **k)
    browse.render.page = spy
    web.playing = ("spotify:track:3", "spotify:user:me:collection")
    before = len(live.views)
    b.song_changed()
    time.sleep(0.5)
    check(f"song change while browsing: page redrawn with the playing song marked ({shown.get('playing')})",
          len(live.views) == before + 1 and shown.get("playing") == ["Song 3"] or
          (len(live.views) == before + 1 and shown.get("playing") == []))
    # Spotify plays a song under another id than the list has (relinked): matched by name and artists
    run(b, "browse", "L")
    time.sleep(0.3)
    web.playing = ("spotify:track:relinked", "spotify:user:me:collection", None, "Song 5	Band")
    shown.clear()
    b.song_changed()
    time.sleep(0.5)
    check(f"a relinked song is still marked, by its name and artists ({shown.get('playing')})",
          shown.get("playing") == ["Song 5"])
    # Spotify's web side still reports the old song for a moment: asked again until it catches up
    web.playing = ("spotify:track:relinked", "spotify:user:me:collection", None, "Song 5	Band")
    shown.clear()
    b.song_changed()
    time.sleep(0.3)
    web.playing = ("spotify:track:6", "spotify:user:me:collection")
    time.sleep(1.5)
    check(f"...and a lagging answer is asked again ({shown.get('playing')})", shown.get("playing") == ["Song 6"])
    run(b, "browse", "P")
    web.playing = ("spotify:track:0", "spotify:playlist:p1")
    b.now = web.now_playing()
    shown["all"] = []
    run(b, "page", len(live.views), 0)
    check(f"the playlist that's playing is marked too ({shown['all']})", ["Mine"] in shown["all"])
    browse.render.page = real_page
    b.set_look((200, 100, 50), FONT)
    check("a new accent colour drops pages drawn ahead in the old one", len(b.ready) == 0 and b.accent == (200, 100, 50))

    run(b, "search", "linkin park")
    v = live.views[-1]
    check("search: 16 results in 2 pages", v["kind"] == 4 and v["pages"] == 2 and v["rows"] == 8)
    search_view = len(live.views)
    run(b, "play", search_view, 12)
    check("a search result plays inside its album, from that song (then Spotify's autoplay)",
          web.played[-1] == dict(context="spotify:album:1", uris=None, offset={"uri": "spotify:track:12"}, shuffle=None))
    web.refuse.add("album")
    run(b, "play", search_view, 12)
    check("...or just the song, if Spotify refuses that", web.played[-1]["uris"] == 1)
    run(b, "search", "nothing")
    check("nothing found: a message row", live.views[-1]["rows"] == 1 and live.views[-1]["pages"] == 1)

    web.refuse.discard("album")  # (the step before made Spotify refuse albums)
    run(b, "search", "count your blessings")
    v = live.views[-1]
    check("album search: the matching album first, then 16 songs, then the other album (18 rows, 3 pages)",
          v["kind"] == 4 and v["pages"] == 3)
    results = len(live.views)
    run(b, "play", results, 0)
    check("clicking the album opens it: Play row + its 12 songs", live.views[-1]["kind"] == 2 and live.views[-1]["pages"] == 2)
    album_view = len(live.views)
    run(b, "play", album_view, 0, True)
    check("the album's Play row, shuffled: the album, shuffle on",
          web.played[-1]["context"] == "spotify:album:cyb" and web.played[-1]["shuffle"] is True)
    run(b, "play", album_view, 3)
    check("an album song plays inside the album, from that song",
          web.played[-1] == dict(context="spotify:album:cyb", uris=None, offset={"position": 2}, shuffle=None))
    run(b, "back", album_view)
    check("Back returns to the search results", live.views[-1]["kind"] == 4)
    run(b, "play", results, 17)
    check("the other album, at the end, opens too", live.views[-1]["kind"] == 2)

    import render
    plain = render.text_strip("Song", 16, 13.5, (255, 255, 255), 1.2, FONT)
    shaded = render.text_strip("Song", 16, 13.5, (255, 209, 0), 1.2, FONT, shadow=True)
    check("classic and modern text has a drop shadow", shaded.size[0] > plain.size[0]
          and shaded.getpixel((shaded.size[0] - 1, shaded.size[1] - 1))[3] >= 0)
    b.set_look((31, 214, 97), FONT, "classic")
    run(b, "browse", "P")
    check("pages draw in the classic theme", live.views[-1]["size"] is not None)

    # the other tabs' first pages are sent ahead (marked kind + 16), once per list
    b.ahead = True
    b.prefetched = 0
    before = len(live.views)
    run(b, "browse", "P")
    time.sleep(1.5)
    ahead = sorted(v["kind"] for v in live.views[before:] if v["kind"] > 16)
    check(f"the other tabs' first pages are sent ahead ({ahead})", ahead == [browse.KIND_LIKED + 16, browse.KIND_SAVED + 16])
    before = len(live.views)
    run(b, "browse", "S")
    time.sleep(0.5)
    check("...and not again for the same lists", not [v for v in live.views[before:] if v["kind"] > 16])
    b.ahead = False

    # a view from before a restart (the addon kept the tab): the tab's list is opened again
    b2 = browse.Browser(web, live, lambda: None, FONT, print)
    b2.ahead = False
    web.refuse.discard("collection")  # (a step before made Spotify refuse Liked plays)
    n = len(web.played)
    run(b2, "play", 4242, 3, False, browse.KIND_LIKED)
    check("a click in a kept Liked list after a restart still plays that song",
          len(web.played) == n + 1 and web.played[-1]["offset"] == {"uri": "spotify:track:3"})

    run(b, "open", 999, 0)
    check("a click on an unknown view (companion restarted) gets a message", live.views[-1]["kind"] == 6)

    b2 = browse.Browser(FakeWeb(signed_in=False), live, lambda: None, FONT, print)
    run(b2, "browse", "S")
    check("not signed in: the 'connect Spotify' page", live.views[-1]["kind"] == 5 and live.views[-1]["size"] is None)

    print("ALL PASSED" if not failed else "SOME CHECKS FAILED")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
