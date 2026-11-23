"""
casc.py - read one file out of the player's local World of Warcraft game data.

WoW keeps its files in "CASC" storage: a handful of big archive files
(Data\\data\\data.###) plus index files that say where each piece lives. This
module follows Blizzard's chain of lookups, using only the Python standard
library, to pull a single file (for example the UI font Fonts\\FRIZQT__.TTF)
out of the player's own install at runtime. Nothing is redistributed.

It is strictly READ-ONLY on the WoW install: files there are only ever opened
with open(path, "rb"), which on Windows does not lock them, and nothing is ever
written under the WoW folder (the writers below refuse such a destination).

The chain, in order:
  1. .build.info (at the WoW root)  -> which build each product (flavor) runs.
  2. build config (Data\\config\\..) -> the keys of the "encoding" and "root" files.
  3. local indices (Data\\data\\*.idx) -> where a file lives:
     archive number, offset and size, keyed by the first 9 bytes of its
     "encoding key" (EKey: the hash of the stored, compressed bytes).
  4. data.### archives -> the stored bytes, in Blizzard's BLTE container,
     which we unpack ('N' = plain, 'Z' = zlib; 'E' = encrypted is refused).
  5. encoding file -> turns a "content key" (CKey: MD5 of the real file) into
     the encoding key(s) we can look up in step 3.
  6. root file -> turns a file path (via its Jenkins96 name hash) or a
     FileDataID into a content key.

Public API:
  extract(path_in_game, flavor="_forever_", wow_root=None) -> bytes
  font_file(dest_dir, name="FRIZQT__.TTF", flavor="_forever_") -> str | None
  CascStorage(flavor, wow_root)  - keeps the root/encoding loaded for several reads

Command line:
  python casc.py <in-game path> <out file> [flavor]
"""

from __future__ import annotations

import bisect
import hashlib
import logging
import os
import re
import struct
import sys
import zlib
from array import array
from itertools import accumulate

log = logging.getLogger(__name__)

__all__ = [
    "CascError", "CascNotFound", "CascEncrypted",
    "CascStorage", "extract", "font_file", "name_hash", "find_wow_root",
    "installed_products", "KNOWN_FILE_IDS",
]


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class CascError(Exception):
    """Something about the local WoW data could not be read or understood."""


class CascNotFound(CascError, FileNotFoundError):
    """The install, product or requested file is not there."""


class CascEncrypted(CascError):
    """The file is stored encrypted (needs a key we do not have)."""


# --------------------------------------------------------------------------
# Small constants
# --------------------------------------------------------------------------

# FileDataIDs for the few fonts the companion cares about. Only used when the
# root file has no name hash for the path (the name hash is tried first).
# Taken from the name-hash entries of the WoW Forever 1.60.1.71037 root; the
# numbering is the same one the community listfile (github.com/wowdev/wow-listfile)
# uses, and FileDataIDs never change between builds or products.
KNOWN_FILE_IDS = {
    "FONTS\\FRIZQT__.TTF": 615960,
    "FONTS\\ARIALN.TTF": 615958,
    "FONTS\\FRIZQT___CYR.TTF": 615971,
}

# Fallback product codes for flavor folders, used only if the folder's own
# .flavor.info file is missing. (.flavor.info is the real source of truth.)
_FOLDER_PRODUCTS = {
    "_retail_": "wow",
    "_ptr_": "wowt",
    "_beta_": "wow_beta",
    "_classic_": "wow_classic",
    "_classic_ptr_": "wow_classic_ptr",
    "_classic_era_": "wow_classic_era",
    "_classic_era_ptr_": "wow_classic_era_ptr",
    "_forever_": "wowf",
}

# Root-file locale bits (which language a file entry is for).
_LOCALE_BITS = {
    "enUS": 0x2, "koKR": 0x4, "frFR": 0x10, "deDE": 0x20, "zhCN": 0x40,
    "esES": 0x80, "zhTW": 0x100, "enGB": 0x200, "enCN": 0x400, "enTW": 0x800,
    "esMX": 0x1000, "ruRU": 0x2000, "ptBR": 0x4000, "itIT": 0x8000,
    "ptPT": 0x10000,
}

# Root-file content flags we look at.
_CF_LOAD_ON_WINDOWS = 0x8
_CF_LOAD_ON_MAC = 0x10
_CF_LOW_VIOLENCE = 0x80
_CF_DO_NOT_LOAD = 0x100
_CF_ENCRYPTED = 0x8000000
_CF_NO_NAME_HASH = 0x10000000

# Each stored file in data.### starts with this 30-byte header before BLTE.
_ARCHIVE_HEADER_SIZE = 30


# --------------------------------------------------------------------------
# Jenkins96 (Bob Jenkins' lookup3 "hashlittle2") - the root file's name hash
# --------------------------------------------------------------------------

_M32 = 0xFFFFFFFF


def _rot(x: int, k: int) -> int:
    return ((x << k) | (x >> (32 - k))) & _M32


def _hashlittle2(key: bytes, pc: int = 0, pb: int = 0) -> tuple[int, int]:
    """lookup3.c hashlittle2: returns (c, b), the two 32-bit hash words."""
    length = len(key)
    a = b = c = (0xDEADBEEF + length + pc) & _M32
    c = (c + pb) & _M32
    if length == 0:
        return c, b

    # Pad with zeros to whole 12-byte blocks. Zero padding is exactly what the
    # reference code's byte-by-byte tail switch does.
    padded = key + b"\0" * (-length % 12)
    blocks = len(padded) // 12
    for i in range(blocks):
        k0, k1, k2 = struct.unpack_from("<III", padded, i * 12)
        a = (a + k0) & _M32
        b = (b + k1) & _M32
        c = (c + k2) & _M32
        if i == blocks - 1:
            break  # the last block goes through "final", not "mix"
        a = (a - c) & _M32; a ^= _rot(c, 4);  c = (c + b) & _M32
        b = (b - a) & _M32; b ^= _rot(a, 6);  a = (a + c) & _M32
        c = (c - b) & _M32; c ^= _rot(b, 8);  b = (b + a) & _M32
        a = (a - c) & _M32; a ^= _rot(c, 16); c = (c + b) & _M32
        b = (b - a) & _M32; b ^= _rot(a, 19); a = (a + c) & _M32
        c = (c - b) & _M32; c ^= _rot(b, 4);  b = (b + a) & _M32

    c ^= b; c = (c - _rot(b, 14)) & _M32
    a ^= c; a = (a - _rot(c, 11)) & _M32
    b ^= a; b = (b - _rot(a, 25)) & _M32
    c ^= b; c = (c - _rot(b, 16)) & _M32
    a ^= c; a = (a - _rot(c, 4)) & _M32
    b ^= a; b = (b - _rot(a, 14)) & _M32
    c ^= b; c = (c - _rot(b, 24)) & _M32
    return c, b


def normalize_path(path: str) -> str:
    """WoW's canonical form of a path: backslashes, upper case, no leading slash."""
    return path.strip().replace("/", "\\").lstrip("\\").upper()


def name_hash(path: str) -> int:
    """The 64-bit name hash the root file stores for an in-game path."""
    # bytes.upper() changes only a-z, like the game does.
    key = path.strip().replace("/", "\\").lstrip("\\").encode("utf-8").upper()
    c, b = _hashlittle2(key)
    return (c << 32) | b


# --------------------------------------------------------------------------
# Finding the install and reading Blizzard's little "|"-separated tables
# --------------------------------------------------------------------------

def _read_bar_table(path: str) -> list[dict[str, str]]:
    """Read a .build.info / .flavor.info style table into a list of dicts.

    The first line is the header, e.g. "Branch!STRING:0|Active!DEC:1|...";
    the part before "!" is the column name. Each further line is one row.
    """
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if not lines:
        return []
    names = [col.split("!", 1)[0].strip() for col in lines[0].split("|")]
    rows = []
    for ln in lines[1:]:
        values = ln.split("|")
        rows.append({n: (values[i] if i < len(values) else "") for i, n in enumerate(names)})
    return rows


def _is_wow_root(path: str | None) -> bool:
    return bool(path) and os.path.isfile(os.path.join(path, ".build.info")) \
        and os.path.isdir(os.path.join(path, "Data"))


def _registry_install_paths() -> list[str]:
    """Install folders the Battle.net installer recorded in the registry (read only)."""
    paths: list[str] = []
    try:
        import winreg
    except ImportError:
        return paths
    keys = [
        r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft",
        r"SOFTWARE\Blizzard Entertainment\World of Warcraft",
    ]
    for sub in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as k:
                value, _ = winreg.QueryValueEx(k, "InstallPath")
                if value:
                    paths.append(str(value))
        except OSError:
            pass
    return paths


def find_wow_root(flavor: str | None = None, wow_root: str | None = None) -> str:
    """Find the World of Warcraft folder (the one holding .build.info and Data).

    wow_root may be the WoW folder itself or a flavor folder inside it
    (for example ...\\World of Warcraft\\_forever_). Otherwise we look at an
    absolute flavor path, the registry, the usual install folders, and the
    folders above this script.
    """
    candidates: list[str] = []
    if wow_root:
        candidates += [wow_root, os.path.dirname(os.path.normpath(wow_root))]
        for c in candidates:
            if _is_wow_root(c):
                return os.path.normpath(c)
        raise CascNotFound(f"no World of Warcraft install (.build.info + Data) at {wow_root!r}")

    if flavor and os.path.isabs(flavor):
        candidates.append(os.path.dirname(os.path.normpath(flavor)))
    for p in _registry_install_paths():
        p = os.path.normpath(p)
        candidates += [p, os.path.dirname(p)]  # InstallPath often points at _retail_
    for env in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, "World of Warcraft"))
    candidates += [r"C:\Program Files (x86)\World of Warcraft",
                   r"C:\Program Files\World of Warcraft",
                   r"C:\World of Warcraft", r"D:\World of Warcraft",
                   r"D:\Games\World of Warcraft"]
    here = os.path.dirname(os.path.abspath(__file__))
    while True:  # e.g. if this file sits inside the WoW folder (an AddOns folder)
        candidates.append(here)
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent

    for c in candidates:
        if _is_wow_root(c):
            return os.path.normpath(c)
    raise CascNotFound("could not find a World of Warcraft install; pass wow_root=...")


def _flavor_product(wow_root: str, flavor: str) -> str:
    """Product code (e.g. 'wowf') for a flavor folder (e.g. '_forever_')."""
    folder = os.path.basename(os.path.normpath(flavor))
    info = os.path.join(wow_root, folder, ".flavor.info")
    if os.path.isfile(info):
        rows = _read_bar_table(info)
        if rows:
            product = rows[0].get("Product Flavor", "").strip()
            if product:
                return product
    if folder in _FOLDER_PRODUCTS:
        return _FOLDER_PRODUCTS[folder]
    return folder  # maybe the caller passed a product code ("wow", "wowf", ...)


def installed_products(wow_root: str | None = None) -> list[dict[str, str]]:
    """Rows of .build.info (one per installed product), active ones first."""
    root = find_wow_root(None, wow_root)
    rows = _read_bar_table(os.path.join(root, ".build.info"))
    return sorted(rows, key=lambda r: r.get("Active", "0") != "1")


def _pick_build(wow_root: str, flavor: str | None) -> dict[str, str]:
    rows = _read_bar_table(os.path.join(wow_root, ".build.info"))
    if not rows:
        raise CascError("empty .build.info")
    if not flavor:
        for r in rows:
            if r.get("Active", "1") == "1":
                return r
        return rows[0]
    product = _flavor_product(wow_root, flavor)
    for r in rows:
        if r.get("Product", "") == product:
            return r
    have = ", ".join(r.get("Product", "?") for r in rows)
    raise CascNotFound(f"product {product!r} (flavor {flavor!r}) is not installed; .build.info has: {have}")


def _read_config(data_dir: str, key_hex: str) -> dict[str, list[str]]:
    """Read a build config file ('name = value value' lines)."""
    key_hex = key_hex.lower()
    path = os.path.join(data_dir, "config", key_hex[0:2], key_hex[2:4], key_hex)
    if not os.path.isfile(path):
        raise CascNotFound(f"build config {key_hex} not found at {path}")
    out: dict[str, list[str]] = {}
    with open(path, "rb") as f:
        for line in f.read().decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            out[name.strip()] = value.split()
    return out


# --------------------------------------------------------------------------
# Local indices: encoding key -> (archive, offset, size)
# --------------------------------------------------------------------------

class _LocalIndex:
    """The 16 Data\\data\\*.idx "bucket" files. Only the bucket a key falls in is read."""

    def __init__(self, data_dir: str):
        self.dir = os.path.join(data_dir, "data")
        if not os.path.isdir(self.dir):
            raise CascNotFound(f"no CASC data folder at {self.dir}")
        # Each bucket can have several versions (bucket byte + version, in hex);
        # the newest one is current.
        self.files: dict[int, str] = {}
        best: dict[int, int] = {}
        for fn in os.listdir(self.dir):
            m = re.fullmatch(r"([0-9a-fA-F]{2})([0-9a-fA-F]{8})\.idx", fn)
            if not m:
                continue
            bucket, version = int(m.group(1), 16), int(m.group(2), 16)
            if version >= best.get(bucket, -1):
                best[bucket] = version
                self.files[bucket] = os.path.join(self.dir, fn)
        self._loaded: dict[int, tuple] = {}

    @staticmethod
    def bucket_of(ekey: bytes) -> int:
        x = 0
        for byte in ekey[:9]:
            x ^= byte
        return (x & 0x0F) ^ (x >> 4)

    def _load(self, bucket: int) -> tuple:
        if bucket in self._loaded:
            return self._loaded[bucket]
        path = self.files.get(bucket)
        if path is None:
            raise CascNotFound(f"no index file for bucket {bucket:02x}")
        with open(path, "rb") as f:
            raw = f.read()
        # Header: [size][hash] then the header block (version 7 layout).
        hdr_size, _hdr_hash = struct.unpack_from("<II", raw, 0)
        (version, _bucket, _extra, size_len, offset_len, key_len,
         offset_bits) = struct.unpack_from("<HBBBBBB", raw, 8)
        if version != 7:
            raise CascError(f"{os.path.basename(path)}: unsupported index version {version}")
        pos = (8 + hdr_size + 0x0F) & ~0x0F  # entries start on a 16-byte boundary
        entries_size, _entries_hash = struct.unpack_from("<II", raw, pos)
        pos += 8
        entry_len = key_len + offset_len + size_len
        entries = raw[pos:pos + entries_size]
        layout = (entries, entry_len, key_len, offset_len, size_len, offset_bits)
        self._loaded[bucket] = layout
        return layout

    def find(self, ekey: bytes) -> tuple[int, int, int] | None:
        """(archive number, offset, stored size) for an encoding key, or None."""
        entries, entry_len, key_len, offset_len, size_len, offset_bits = \
            self._load(self.bucket_of(ekey))
        needle = ekey[:key_len]
        start = 0
        while True:  # bytes.find runs in C; we just check the hit is entry-aligned
            hit = entries.find(needle, start)
            if hit < 0:
                return None
            if hit % entry_len == 0:
                break
            start = hit + 1
        p = hit + key_len
        packed = int.from_bytes(entries[p:p + offset_len], "big")
        archive = packed >> offset_bits
        offset = packed & ((1 << offset_bits) - 1)
        size = int.from_bytes(entries[p + offset_len:p + offset_len + size_len], "little")
        return archive, offset, size


# --------------------------------------------------------------------------
# BLTE: Blizzard's chunked container for stored files
# --------------------------------------------------------------------------

class _Blte:
    """One stored file, opened lazily: only the chunks ("frames") you ask for
    are read and unpacked. That keeps the 100+ MB encoding file cheap."""

    def __init__(self, path: str, offset: int, size: int, ekey: bytes | None = None):
        self.path = path
        self.f = open(path, "rb")  # read only, not locked on Windows
        self.f.seek(offset)
        head = self.f.read(_ARCHIVE_HEADER_SIZE + 12)
        if len(head) < _ARCHIVE_HEADER_SIZE + 8:
            raise CascError(f"truncated data in {os.path.basename(path)}")
        # 30-byte archive header: the encoding key stored backwards, then size.
        if ekey is not None and head[15::-1][:9] != ekey[:9]:
            raise CascError("archive entry does not match its index (stale index?)")
        base = offset + _ARCHIVE_HEADER_SIZE
        blte_len = size - _ARCHIVE_HEADER_SIZE
        if head[_ARCHIVE_HEADER_SIZE:_ARCHIVE_HEADER_SIZE + 4] != b"BLTE":
            raise CascError("stored data is not BLTE")
        (header_size,) = struct.unpack_from(">I", head, _ARCHIVE_HEADER_SIZE + 4)

        # frames: (file offset, encoded size, decoded size or -1, md5 or None)
        self.frames: list[tuple[int, int, int, bytes | None]] = []
        if header_size == 0:
            # A single frame covering everything after the 8-byte BLTE header.
            self.frames.append((base + 8, blte_len - 8, -1, None))
        else:
            flags_count = struct.unpack_from(">I", head, _ARCHIVE_HEADER_SIZE + 8)[0]
            count = flags_count & 0xFFFFFF
            self.f.seek(base + 12)
            table = self.f.read(24 * count)
            pos = base + header_size
            for i in range(count):
                enc, dec = struct.unpack_from(">II", table, i * 24)
                md5 = table[i * 24 + 8:i * 24 + 24]
                self.frames.append((pos, enc, dec, md5))
                pos += enc
        # Where each frame starts in the unpacked output (known only if sizes are).
        self.starts = [0]
        for fr in self.frames:
            self.starts.append(self.starts[-1] + max(fr[2], 0))
        self._cache: dict[int, bytes] = {}

    def close(self) -> None:
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _frame(self, i: int) -> bytes:
        if i in self._cache:
            return self._cache[i]
        pos, enc, dec, md5 = self.frames[i]
        self.f.seek(pos)
        raw = self.f.read(enc)
        if len(raw) != enc:
            raise CascError("truncated BLTE frame")
        if md5 is not None and hashlib.md5(raw).digest() != md5:
            raise CascError("BLTE frame checksum mismatch (file damaged or being patched)")
        out = self._unpack(raw)
        if dec >= 0 and len(out) != dec:
            raise CascError("BLTE frame unpacked to the wrong size")
        self._cache = {i: out}  # keep only the latest frame; frames can be large
        return out

    @staticmethod
    def _unpack(raw: bytes) -> bytes:
        mode = raw[:1]
        if mode == b"N":
            return raw[1:]
        if mode == b"Z":
            return zlib.decompress(raw[1:])
        if mode == b"E":
            raise CascEncrypted("file is encrypted")
        if mode == b"F":
            raise CascError("nested BLTE frames are not supported")
        raise CascError(f"unknown BLTE frame mode {mode!r}")

    def read_all(self) -> bytes:
        return b"".join(self._frame(i) for i in range(len(self.frames)))

    def read(self, start: int, length: int) -> bytes:
        """Unpacked bytes [start, start+length). Plain ('N') frames are read
        straight from disk without loading the whole frame."""
        if any(fr[2] < 0 for fr in self.frames):
            return self.read_all()[start:start + length]
        out = bytearray()
        end = start + length
        i = max(0, bisect.bisect_right(self.starts, start) - 1)
        while start < end and i < len(self.frames):
            fstart, fend = self.starts[i], self.starts[i + 1]
            lo, hi = start - fstart, min(end, fend) - fstart
            pos = self.frames[i][0]
            # Peek at the mode byte; plain frames can be sliced from disk.
            self.f.seek(pos)
            if i not in self._cache and self.f.read(1) == b"N":
                self.f.seek(pos + 1 + lo)
                out += self.f.read(hi - lo)
            else:
                out += self._frame(i)[lo:hi]
            start = fstart + hi
            i += 1
        return bytes(out)


# --------------------------------------------------------------------------
# Encoding file: content key -> encoding key(s)
# --------------------------------------------------------------------------

class _Encoding:
    def __init__(self, blte: _Blte):
        self.blte = blte
        head = blte.read(0, 22)
        (magic, _version, ckey_len, ekey_len, ckey_page_kb, _ekey_page_kb,
         ckey_pages, _ekey_pages, _unk, espec_size) = struct.unpack(">2sBBBHHIIBI", head)
        if magic != b"EN":
            raise CascError("encoding file has a bad header")
        self.ckey_len, self.ekey_len = ckey_len, ekey_len
        self.page_size = ckey_page_kb * 1024
        index_pos = 22 + espec_size
        index = blte.read(index_pos, ckey_pages * (ckey_len + 16))
        step = ckey_len + 16
        # First content key on each page, for a binary search.
        self.first_keys = [index[i * step:i * step + ckey_len] for i in range(ckey_pages)]
        self.pages_pos = index_pos + len(index)

    def ekeys_for(self, ckey: bytes) -> list[bytes]:
        page = bisect.bisect_right(self.first_keys, ckey) - 1
        if page < 0:
            return []
        data = self.blte.read(self.pages_pos + page * self.page_size, self.page_size)
        p, kl, el = 0, self.ckey_len, self.ekey_len
        while p + 6 + kl <= len(data):
            count = data[p]
            if count == 0:
                break  # rest of the page is padding
            key = data[p + 6:p + 6 + kl]
            if key == ckey:
                first = p + 6 + kl
                return [data[first + j * el:first + (j + 1) * el] for j in range(count)]
            p += 6 + kl + count * el
        return []


# --------------------------------------------------------------------------
# Root file: path name hash or FileDataID -> content key
# --------------------------------------------------------------------------

class _Root:
    """WoW's root file. Supports the old headerless format, the 8.2+ 'TSFM'
    (MFST) format and the 10.1.7+ versioned TSFM header (block versions 1 and 2)."""

    def __init__(self, data: bytes):
        self.data = data
        self.blocks = self._parse()

    def _parse(self) -> list[tuple]:
        d = self.data
        if d[:4] == b"TSFM":
            a, b = struct.unpack_from("<II", d, 4)
            if a == 0x18 and b in (1, 2):      # 10.1.7+: header size, version
                version = b
                total, named = struct.unpack_from("<II", d, 12)
                start = a
            else:                              # 8.2 - 10.1.5
                version, total, named, start = 1, a, b, 12
            # Try the expected block layout first, then the other one.
            layouts = [version, 3 - version]
            for lay in layouts:
                blocks = self._walk(start, lay, mfst=True, maybe_unnamed=(total != named))
                if blocks is not None:
                    return blocks
            raise CascError("root file format not recognised")
        blocks = self._walk(0, 1, mfst=False, maybe_unnamed=False)
        if blocks is None:
            raise CascError("root file format not recognised")
        return blocks

    def _walk(self, pos: int, layout: int, mfst: bool, maybe_unnamed: bool):
        """Split the root into blocks. Returns None if the layout does not fit.

        Each block: (count, content_flags, locale_flags, deltas_pos, ckeys_pos,
        names_pos or -1, interleaved). Returns None if sizes don't add up.
        """
        d, n_total = self.data, len(self.data)
        blocks = []
        while pos < n_total:
            if layout == 2:
                if pos + 17 > n_total:
                    return None
                count, locale, f1, f2 = struct.unpack_from("<IIII", d, pos)
                content = f1 | f2 | (d[pos + 16] << 17)
                pos += 17
            else:
                if pos + 12 > n_total:
                    return None
                count, content, locale = struct.unpack_from("<III", d, pos)
                pos += 12
            deltas = pos
            pos += 4 * count
            if mfst:
                ckeys = pos
                pos += 16 * count
                if maybe_unnamed and content & _CF_NO_NAME_HASH:
                    names = -1
                else:
                    names = pos
                    pos += 8 * count
                interleaved = False
            else:  # pre-8.2: (ckey, name hash) pairs
                ckeys, names, interleaved = pos, pos + 16, True
                pos += 24 * count
            if pos > n_total:
                return None
            blocks.append((count, content, locale, deltas, ckeys, names, interleaved))
        return blocks if pos == n_total else None

    def _deltas(self, blk) -> array:
        count, _c, _l, deltas_pos = blk[:4]
        arr = array("i")
        arr.frombytes(self.data[deltas_pos:deltas_pos + 4 * count])
        if sys.byteorder != "little":
            arr.byteswap()
        return arr

    def _ckey(self, blk, i: int) -> bytes:
        stride = 24 if blk[6] else 16
        p = blk[4] + stride * i
        return self.data[p:p + 16]

    def _fdid_at(self, blk, i: int) -> int:
        # FileDataIDs are stored as gaps: id = previous id + 1 + delta.
        deltas = self._deltas(blk)[:i + 1]
        return sum(deltas) + i

    def by_name(self, h: int) -> list[tuple[int, bytes, int, int]]:
        """Entries (fdid, ckey, locale, content) whose name hash is h."""
        needle = struct.pack("<Q", h)
        found = []
        for blk in self.blocks:
            count, content, locale, _dp, _cp, names, inter = blk
            if names < 0:
                continue
            stride = 24 if inter else 8
            end = names + stride * count
            start = names
            while True:
                hit = self.data.find(needle, start, end)
                if hit < 0:
                    break
                if (hit - names) % stride == 0:
                    i = (hit - names) // stride
                    found.append((self._fdid_at(blk, i), self._ckey(blk, i), locale, content))
                    break
                start = hit + 1
        return found

    def by_fdid(self, fdid: int) -> list[tuple[int, bytes, int, int]]:
        """Entries (fdid, ckey, locale, content) for a FileDataID."""
        found = []
        target = fdid + 1  # running sums of (delta + 1) are id + 1
        for blk in self.blocks:
            sums = list(accumulate(d + 1 for d in self._deltas(blk)))
            i = bisect.bisect_left(sums, target)
            if i < len(sums) and sums[i] == target:
                found.append((fdid, self._ckey(blk, i), blk[2], blk[1]))
        return found


# --------------------------------------------------------------------------
# The storage itself
# --------------------------------------------------------------------------

class CascStorage:
    """One product's view of the local CASC storage. Loading the root file takes
    a moment, so keep one of these around if you need several files; let it go
    afterwards to free the memory (the root file is tens of MB)."""

    def __init__(self, flavor: str | None = "_forever_", wow_root: str | None = None):
        self.wow_root = find_wow_root(flavor, wow_root)
        self.data_dir = os.path.join(self.wow_root, "Data")
        self.build = _pick_build(self.wow_root, flavor)
        self.product = self.build.get("Product", "?")
        self.version = self.build.get("Version", "?")
        build_key = self.build.get("Build Key", "").strip()
        if not build_key:
            raise CascError(f"no build key for {self.product} in .build.info")
        self.config = _read_config(self.data_dir, build_key)
        m = re.search(r"\b([a-z]{2}[A-Z]{2}) text\?", self.build.get("Tags", ""))
        self.locale = m.group(1) if m else "enUS"
        self.index = _LocalIndex(self.data_dir)
        self._encoding: _Encoding | None = None
        self._root: _Root | None = None
        self.root_format = ""
        self.last_fdid: int | None = None  # FileDataID of the last file read

    # -- low level ---------------------------------------------------------

    def _open_ekey(self, ekey: bytes) -> _Blte | None:
        loc = self.index.find(ekey)
        if loc is None:
            return None
        archive, offset, size = loc
        path = os.path.join(self.index.dir, f"data.{archive:03d}")
        return _Blte(path, offset, size, ekey)

    def read_ekey(self, ekey: bytes) -> bytes | None:
        """Unpacked bytes of a stored file by encoding key, or None if not local."""
        blte = self._open_ekey(ekey)
        if blte is None:
            return None
        with blte:
            return blte.read_all()

    @property
    def encoding(self) -> _Encoding:
        if self._encoding is None:
            keys = self.config.get("encoding", [])
            if len(keys) < 2:
                raise CascError("build config has no encoding key")
            blte = self._open_ekey(bytes.fromhex(keys[1]))
            if blte is None:
                raise CascNotFound("encoding file is not in the local storage")
            try:
                self._encoding = _Encoding(blte)
            except Exception:
                blte.close()
                raise
        return self._encoding

    def read_ckey(self, ckey: bytes) -> bytes | None:
        """Unpacked, checksum-verified file by content key, or None if not local."""
        for ekey in self.encoding.ekeys_for(ckey):
            data = self.read_ekey(ekey)
            if data is None:
                continue
            if hashlib.md5(data).digest() != ckey:
                raise CascError("file content does not match its checksum")
            return data
        return None

    @property
    def root(self) -> _Root:
        if self._root is None:
            keys = self.config.get("root", [])
            if not keys:
                raise CascError("build config has no root key")
            data = self.read_ckey(bytes.fromhex(keys[0]))
            if data is None:
                raise CascNotFound("root file is not in the local storage")
            self._root = _Root(data)
            if data[:4] == b"TSFM":
                hs, ver = struct.unpack_from("<II", data, 4)
                self.root_format = f"TSFM v{ver}" if hs == 0x18 else "TSFM (8.2)"
            else:
                self.root_format = "legacy (pre-8.2)"
        return self._root

    def close(self) -> None:
        if self._encoding is not None:
            self._encoding.blte.close()
        self._encoding = None
        self._root = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- lookups -----------------------------------------------------------

    def _rank(self, entry: tuple[int, bytes, int, int]) -> tuple:
        """Sort key: entries for our locale, Windows and normal content first."""
        _fdid, _ckey, locale, content = entry
        want = _LOCALE_BITS.get(self.locale, 0x2)
        return (
            not (locale & want),
            bool(content & _CF_LOW_VIOLENCE),
            bool(content & _CF_DO_NOT_LOAD),
            bool(content & _CF_LOAD_ON_MAC) and not content & _CF_LOAD_ON_WINDOWS,
            bool(content & _CF_ENCRYPTED),
        )

    def lookup(self, path_or_fdid: str | int) -> list[tuple[int, bytes, int, int]]:
        """Root entries (fdid, ckey, locale, content) for a path or FileDataID,
        best match first. Paths are tried by name hash, then KNOWN_FILE_IDS."""
        if isinstance(path_or_fdid, int):
            entries = self.root.by_fdid(path_or_fdid)
        else:
            entries = self.root.by_name(name_hash(path_or_fdid))
            if not entries:
                fdid = KNOWN_FILE_IDS.get(normalize_path(path_or_fdid))
                if fdid is not None:
                    entries = self.root.by_fdid(fdid)
        return sorted(entries, key=self._rank)

    def read_file(self, path_or_fdid: str | int) -> bytes:
        """The file's bytes. Raises CascNotFound / CascEncrypted / CascError."""
        entries = self.lookup(path_or_fdid)
        if not entries:
            raise CascNotFound(f"{path_or_fdid!r} is not in the {self.product} root file")
        last_error: Exception | None = None
        for entry in entries:
            try:
                data = self.read_ckey(entry[1])
            except CascEncrypted as e:
                last_error = e
                continue
            if data is not None:
                self.last_fdid = entry[0]
                return data
        if last_error:
            raise last_error
        raise CascNotFound(f"{path_or_fdid!r} is listed but not downloaded in the local {self.product} storage")


# --------------------------------------------------------------------------
# Convenience functions
# --------------------------------------------------------------------------

def extract(path_in_game: str | int, flavor: str | None = "_forever_",
            wow_root: str | None = None) -> bytes:
    """Return the bytes of one game file, e.g. extract("Fonts\\\\FRIZQT__.TTF").

    path_in_game: in-game path (either slash) or an int FileDataID.
    flavor: flavor folder ("_forever_", "_retail_", ...) or product code;
            None = the first active product in .build.info.
    wow_root: the World of Warcraft folder (or a flavor folder in it);
              None = find it.
    Raises CascNotFound if the install, product or file is not there.
    """
    with CascStorage(flavor, wow_root) as casc:
        return casc.read_file(path_in_game)


def _inside(path: str, folder: str) -> bool:
    try:
        path, folder = os.path.realpath(path), os.path.realpath(folder)
        return os.path.commonpath([os.path.normcase(path), os.path.normcase(folder)]) \
            == os.path.normcase(folder)
    except ValueError:  # different drives
        return False


def _write_file(dest: str, data: bytes, wow_root: str | None) -> None:
    """Write via a temp file + rename; never inside the WoW install."""
    if wow_root and _inside(dest, wow_root):
        raise CascError("refusing to write inside the World of Warcraft folder")
    folder = os.path.dirname(os.path.abspath(dest))
    os.makedirs(folder, exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)


def _looks_like_font(data: bytes) -> bool:
    return data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


def font_file(dest_dir: str, name: str = "FRIZQT__.TTF",
              flavor: str | None = "_forever_") -> str | None:
    """Copy Fonts\\<name> from the local WoW data into dest_dir once and return
    its path. Returns None on any failure (never raises), so callers can fall
    back to another font. If the flavor isn't installed, other installed
    products are tried (the UI fonts are the same files)."""
    try:
        name = os.path.basename(name)
        dest = os.path.join(dest_dir, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            return dest
        root = find_wow_root(flavor)
        # The requested flavor first, then every other installed product.
        tries: list[str | None] = [flavor]
        tried = {_flavor_product(root, flavor) if flavor else None}
        for row in installed_products(root):
            product = row.get("Product")
            if product and product not in tried:
                tries.append(product)
                tried.add(product)
        for f in tries:
            try:
                data = extract("Fonts\\" + name, f, root)
            except CascError as e:
                log.info("%s from %s: %s", name, f, e)
                continue
            if not _looks_like_font(data):
                log.warning("%s from %s does not look like a font", name, f)
                continue
            _write_file(dest, data, root)
            return dest
        return None
    except Exception as e:  # the companion must keep working without the font
        log.warning("could not get font %s: %s", name, e)
        return None


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print("usage: python casc.py <in-game path or FileDataID> <out file> [flavor]",
              file=sys.stderr)
        return 2
    import time
    target: str | int = argv[0]
    if isinstance(target, str) and target.isdigit():
        target = int(target)
    out = argv[1]
    flavor = argv[2] if len(argv) == 3 else "_forever_"
    t0 = time.perf_counter()
    try:
        with CascStorage(flavor) as casc:
            data = casc.read_file(target)
            _write_file(out, data, casc.wow_root)
            print(f"{casc.product} {casc.version} ({casc.root_format} root, {casc.locale}): "
                  f"FileDataID {casc.last_fdid}, {len(data)} bytes -> {out} "
                  f"in {time.perf_counter() - t0:.2f}s")
    except CascError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
