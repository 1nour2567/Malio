"""State Manager — per-user state with JSON persistence."""
import collections
import json
import os as _os
import threading
from datetime import datetime
from typing import Dict, Any, List


# ═══════════════════════════════════════════════════════════════
# Per-user state storage
# ═══════════════════════════════════════════════════════════════

_sessions: Dict[str, Dict] = {}
_lock = threading.Lock()


def _get_or_create(user_id: str) -> dict:
    with _lock:
        if user_id not in _sessions:
            _sessions[user_id] = {
                "playback_state": {"playlist": [], "index": 0, "current": {}, "is_playing": False},
                "core_events": collections.deque(maxlen=50),
                "chat_history": collections.deque(maxlen=10),
                "agent_rules": [],
                "_fast_skips": collections.deque(),
            }
        return _sessions[user_id]


def _session(user_id: str = "default") -> dict:
    return _get_or_create(user_id)


# ═══════════════════════════════════════════════════════════════
# Convenience accessors — pass user_id through the call chain
# ═══════════════════════════════════════════════════════════════

def get_playback(user_id: str = "default") -> dict:
    return _session(user_id)["playback_state"]


def get_core_events(user_id: str = "default"):
    return _session(user_id)["core_events"]


def get_chat_history(user_id: str = "default"):
    return _session(user_id)["chat_history"]


def get_agent_rules(user_id: str = "default") -> list:
    return _session(user_id)["agent_rules"]


def _fast_skips_of(user_id: str = "default"):
    return _session(user_id)["_fast_skips"]


# ═══════════════════════════════════════════════════════════════
# Queue helpers (per-user)
# ═══════════════════════════════════════════════════════════════

def set_playlist(songs: list, start_index: int = 0, user_id: str = "default"):
    ps = get_playback(user_id)
    ps["playlist"] = songs
    ps["index"] = max(0, min(start_index, len(songs) - 1)) if songs else 0
    ps["current"] = songs[ps["index"]] if songs else {}
    state_store.mark_dirty(user_id)


def next_in_queue(user_id: str = "default") -> dict:
    ps = get_playback(user_id)
    pl = ps["playlist"]
    if not pl:
        return {}
    ps["index"] = (ps["index"] + 1) % len(pl)
    ps["current"] = pl[ps["index"]]
    state_store.mark_dirty(user_id)
    return ps["current"]


def add_fast_skip(user_id: str = "default"):
    _fast_skips_of(user_id).append(datetime.now().timestamp())


def count_recent_fast_skips(seconds: int = 30, user_id: str = "default") -> int:
    fs = _fast_skips_of(user_id)
    cutoff = datetime.now().timestamp() - seconds
    while fs and fs[0] < cutoff:
        fs.popleft()
    return len(fs)


def clear_fast_skips(user_id: str = "default"):
    _fast_skips_of(user_id).clear()


# ═══════════════════════════════════════════════════════════════
# DB queries (shared — stateless)
# ═══════════════════════════════════════════════════════════════

def query_local_songs(limit=20, recommendation_engine=None) -> list:
    if recommendation_engine is None:
        return []
    try:
        from models.music import Song
        from sqlalchemy import func
        session = recommendation_engine.Session()
        songs = session.query(Song).order_by(func.random()).limit(limit).all()
        result = [{"id": s.id, "title": s.title, "artist": s.artist,
                   "audio_path": s.audio_path or "",
                   "preview_url": (s.features or {}).get("preview_url", ""),
                   "album_art": (s.features or {}).get("album_art", ""),
                   "album": s.album, "duration": s.duration or 180,
                   "energy": s.energy, "warmth": s.warmth, "density": s.density,
                   "lang": _guess_lang(s.title, s.artist)}
                  for s in songs]
        session.close()
        return result
    except Exception:
        return []


def _guess_lang(title: str, artist: list) -> str:
    """Guess song language from title/artist heuristics."""
    t = (title or '') + ' ' + ' '.join(artist or [])
    has_cn = any('一' <= c <= '鿿' for c in t)
    has_kr = any('가' <= c <= '힯' for c in t)
    has_jp = any('぀' <= c <= 'ヿ' for c in t)
    if has_kr: return 'kr'
    if has_jp: return 'jp'
    if has_cn: return 'cn'
    # Check for instrumental markers
    low = t.lower()
    if any(kw in low for kw in ['lofi', 'instrumental', 'piano', 'orchestra', 'ost', 'bgm', '纯音乐']):
        return 'inst'
    return 'en'


def enrich_songs(songs: list, recommendation_engine=None) -> list:
    if not songs or recommendation_engine is None:
        return songs
    try:
        from models.music import Song
        session = recommendation_engine.Session()
        db_songs = {s.title.lower(): s for s in session.query(Song).all()}
        session.close()
        for song in songs:
            if song.get("audio_path") or song.get("preview_url"):
                continue
            db_match = db_songs.get((song.get("title") or "").lower())
            if db_match:
                song["audio_path"] = db_match.audio_path or ""
                song["preview_url"] = (db_match.features or {}).get("preview_url", "")
                song["id"] = song.get("id") or db_match.id
                song["duration"] = song.get("duration") or db_match.duration or 180
    except Exception:
        pass
    return songs


# ═══════════════════════════════════════════════════════════════
# State persistence (per-user)
# ═══════════════════════════════════════════════════════════════

class StateStore:
    """JSON-file persistence for playback state, events, and chat history."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            data_dir = _os.path.join(base, "data")
        self._dir = _os.path.join(data_dir, "sessions")
        _os.makedirs(self._dir, exist_ok=True)
        self._lock = threading.Lock()
        self._dirty: Dict[str, bool] = {}

    def save(self, session_id: str):
        s = _session(session_id)
        ps = s["playback_state"]
        with self._lock:
            snapshot = {
                "session_id": session_id,
                "saved_at": datetime.now().isoformat(),
                "playback_state": {
                    "playlist": list(ps["playlist"]),
                    "index": ps["index"],
                    "current": dict(ps["current"]),
                    "is_playing": ps["is_playing"],
                },
                "core_events": list(s["core_events"]),
                "chat_history": list(s["chat_history"]),
                "agent_rules": list(s["agent_rules"]),
            }
            tmp = _os.path.join(self._dir, f"{session_id}.json.tmp")
            dst = _os.path.join(self._dir, f"{session_id}.json")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            _os.replace(tmp, dst)
            self._dirty[session_id] = False

    def load(self, session_id: str) -> dict:
        path = _os.path.join(self._dir, f"{session_id}.json")
        if not _os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def restore(self, session_id: str) -> bool:
        data = self.load(session_id)
        if not data:
            return False
        s = _session(session_id)
        ps_data = data.get("playback_state", {})
        if ps_data:
            s["playback_state"] = {
                "playlist": ps_data.get("playlist", []),
                "index": ps_data.get("index", 0),
                "current": ps_data.get("current", {}),
                "is_playing": ps_data.get("is_playing", False),
            }
        for evt in data.get("core_events", []):
            s["core_events"].append(evt)
        for msg in data.get("chat_history", []):
            s["chat_history"].append(msg)
        for rule in data.get("agent_rules", []):
            s["agent_rules"].append(rule)
        cur = s["playback_state"]["current"]
        if cur:
            print(f"[state] restored {session_id} — {cur.get('title','?')}, "
                  f"queue={len(s['playback_state']['playlist'])}, chat={len(s['chat_history'])}")
        return True

    def mark_dirty(self, session_id: str):
        self._dirty[session_id] = True

    def save_if_dirty(self, session_id: str):
        if self._dirty.get(session_id):
            self.save(session_id)


state_store = StateStore()
