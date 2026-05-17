"""L3 Long-Term Profile — distilled conclusions from L2 summaries.
Four sub-libraries: preferences, behavior, mood, rules.
Context-tagged, version-controlled. Updated daily from L2 data.
No vector DB — structured JSON with metadata filtering.
"""

import json
import os
import time
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


class L3Profile:
    """Dynamic user digital twin — stores distilled conclusions, not raw data."""

    _embedder = None  # lazy-loaded SentenceTransformer

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base, "data")
        self._path = os.path.join(data_dir, "user_profile.json")
        self._load()

    @classmethod
    def _get_embedder(cls):
        if not hasattr(cls, '_embed_model'):
            import os
            os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
            from text2vec import SentenceModel
            cls._embed_model = SentenceModel('shibing624/text2vec-base-chinese')
        return cls._embed_model

    @classmethod
    def _embed_similarity(cls, query: str, candidate: str) -> float:
        """Cosine similarity via text2vec Chinese embedding model."""
        try:
            import numpy as np
            model = cls._get_embedder()
            vecs = model.encode([query, candidate])
            dot = np.dot(vecs[0], vecs[1])
            na = np.linalg.norm(vecs[0])
            nb = np.linalg.norm(vecs[1])
            return float(dot / (na * nb + 1e-9))
        except Exception:
            return 0.0

    @staticmethod
    def _semantic_sim(query: str, candidate: str, context: Dict[str, Any] = None) -> float:
        """Semantic similarity: text2vec embedding + context metadata bonus."""
        emb_sim = L3Profile._embed_similarity(query, candidate)

        context_bonus = 0.0
        if context:
            time_slots = context.get("time_slots", {})
            ts_text = " ".join(time_slots.keys()) if time_slots else ""
            if ts_text:
                ts_bonus = L3Profile._embed_similarity(query, ts_text) * 0.3
                context_bonus = max(context_bonus, ts_bonus)

        return min(1.0, emb_sim + context_bonus)

    def _build_query(self, situation: Dict[str, Any]) -> str:
        """Build a query string from the current situation for semantic search."""
        parts = []
        tod = situation.get("time_of_day", "")
        hour = situation.get("hour", 0)
        if tod:
            parts.append(tod)
        if hour:
            if 5 <= hour < 8: parts.append("清晨")
            elif 8 <= hour < 12: parts.append("上午")
            elif 12 <= hour < 18: parts.append("下午")
            elif 18 <= hour < 22: parts.append("傍晚")
            else: parts.append("深夜")
        mood = situation.get("mood_tag", "")
        if mood:
            parts.append(mood)
        return " ".join(parts)

    # ── Persistence ────────────────────────────────────────

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        self.preferences = data.get("preferences", {
            "artists": {},        # {name: {strength, evidence[], last_reinforced, decay, source}}
            "genres": {},
            "eras": {},
            "disliked_artists": {},
            "disliked_genres": {},
            "time_slots": {},
            "_pending": [],       # confirmation queue: updates awaiting user approval
        })

        self.behavior = data.get("behavior", {
            "avg_skip_time_sec": 180,    # average seconds before skipping
            "avg_volume": 70,            # typical volume level
            "preferred_play_mode": "shuffle",
            "peak_hours": [],            # [{"hour": 21, "count": 15}, ...]
            "session_duration_avg": 30,  # minutes
        })

        self.mood = data.get("mood", {
            "baseline": "neutral",       # most common mood
            "patterns": {},              # {"烦躁": {genres:..., skip_fast: true}}
            "mood_swing_hours": [],      # hours where mood changes frequently
        })

        self.rules = data.get("rules", {
            "explicit": [],              # user-stated rules: "不要抖音热歌"
            "inferred": [],              # system-inferred: "工作时间不喜欢有歌词的"
            "active_dsl_ids": [],        # IDs of active DSL rules
        })

        self._meta = data.get("_meta", {
            "last_distilled": None,
            "total_updates": 0,
            "profile_version": 1,
            "recent_digest": {},         # L4浓缩摘要，推理时快速读取
        })

    def _save(self):
        self._meta["total_updates"] += 1
        self._meta["profile_version"] += 1
        data = {
            "preferences": self.preferences,
            "behavior": self.behavior,
            "mood": self.mood,
            "rules": self.rules,
            "_meta": self._meta,
        }
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Distillation from L2 ───────────────────────────────

    def distill_from_l2(self, l2_summaries: List[Dict], l2_events: List[Dict], l4_events: List[Dict] = None):
        """Daily distillation: convert L2+L4 raw data into L3 conclusions + digest."""
        if not l2_summaries and not l2_events:
            return

        now = datetime.now()
        self._meta["last_distilled"] = now.isoformat()

        # ── L4 digest: quick summary for Reasoner ──────────
        if l4_events:
            song_plays = {}
            fast_skips = []
            for evt in l4_events:
                sid = evt.get("detail", {}).get("song_id", "")
                title = evt.get("detail", {}).get("title", "")
                if evt.get("type") in ("play", "core_song_skip") and sid:
                    song_plays[sid] = song_plays.get(sid, 0) + 1
                if evt.get("type") == "core_song_skip":
                    sec = evt.get("detail", {}).get("played_sec", 0)
                    if sec and sec < 90:
                        fast_skips.append(title or sid)

            top_songs = sorted(song_plays.items(), key=lambda x: x[1], reverse=True)[:5]
            self._meta["recent_digest"] = {
                "top_songs": [{"id": s[0], "plays": s[1]} for s in top_songs],
                "fast_skips": fast_skips[-5:],
                "total_events": len(l4_events),
                "generated_at": now.isoformat(),
            }

        # ── Behavior patterns ──────────────────────────────
        skip_times = []
        volumes = []
        hour_counts: Dict[int, int] = {}
        for evt in l2_events:
            if evt.get("type") == "skip":
                sec = evt.get("detail", {}).get("played_sec", 0)
                if sec > 0:
                    skip_times.append(sec)
            if evt.get("type") == "volume_change":
                vol = evt.get("detail", {}).get("to", 0)
                if vol > 0:
                    volumes.append(vol)
            ts = evt.get("ts", 0)
            if ts:
                h = datetime.fromtimestamp(ts).hour
                hour_counts[h] = hour_counts.get(h, 0) + 1

        if skip_times:
            self.behavior["avg_skip_time_sec"] = round(sum(skip_times) / len(skip_times), 1)
        if volumes:
            self.behavior["avg_volume"] = round(sum(volumes) / len(volumes))
        if hour_counts:
            self.behavior["peak_hours"] = sorted(
                [{"hour": h, "count": c} for h, c in hour_counts.items()],
                key=lambda x: x["count"], reverse=True
            )[:5]

        # ── Mood inference from fast-skips ──────────────────
        fast_skips = [s for s in skip_times if s < 60]
        if len(fast_skips) > 3:
            self.mood["patterns"]["restless"] = {
                "fast_skip_count": len(fast_skips),
                "avg_skip_sec": round(sum(fast_skips) / len(fast_skips), 1) if fast_skips else 0,
                "detected_at": now.isoformat(),
            }

        # ── Summary-based preference adjustment ────────────
        for s in l2_summaries:
            if s.get("avg_skip_time") and s["avg_skip_time"] < 90:
                hour = s.get("hour", "")
                if hour not in self.preferences["time_slots"]:
                    self.preferences["time_slots"][hour] = {}
                self.preferences["time_slots"][hour]["fast_skip"] = True

        self.decay_all()
        self.expire_pending()
        self._save()

    # ── Retrieval (trigger-based, not polling) ──────────────

    def _semantic_top_prefs(self, query: str, top_k: int = 3) -> List[Dict]:
        """Return top-k preference entries matching query via character n-gram similarity."""
        artists = self.preferences.get("artists", {})
        genres = self.preferences.get("genres", {})
        if not artists and not genres:
            return []

        items = []
        for name, entry in artists.items():
            items.append({"type": "artist", "name": name, "strength": entry.get("strength", 0.5)})
        for name, entry in genres.items():
            items.append({"type": "genre", "name": name, "strength": entry.get("strength", 0.5)})

        if not items:
            return []

        scored = []
        for item in items:
            # Get the full preference entry for context metadata
            full_entry = (artists if item["type"] == "artist" else genres).get(item["name"], {})
            sim = self._semantic_sim(query, item["name"], full_entry)
            if sim > 0.05:
                scored.append((sim, item))

        scored.sort(key=lambda x: -x[0])
        return [{"type": s[1]["type"], "name": s[1]["name"],
                 "strength": s[1]["strength"], "similarity": round(s[0], 3)}
                for s in scored[:top_k]]

    def relevant_context(self, situation: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger-based retrieval: only returns context when situation matches."""
        tod = situation.get("time_of_day", "")
        hour = situation.get("hour", 0)
        mood_tag = situation.get("mood_tag", "")

        ctx: Dict[str, Any] = {}

        # Semantic search: match preferences to current situation
        query = self._build_query(situation)
        semantic = self._semantic_top_prefs(query, top_k=3)
        if semantic:
            ctx["semantic_matches"] = semantic

        # time-slot preferences
        if tod and tod in self.preferences.get("time_slots", {}):
            ctx["time_preference"] = self.preferences["time_slots"][tod]

        # peak hour behavior
        if self.behavior.get("peak_hours"):
            for ph in self.behavior["peak_hours"]:
                if ph["hour"] == hour:
                    ctx["peak_hour"] = True
                    break

        # mood-linked patterns
        if mood_tag and mood_tag in self.mood.get("patterns", {}):
            ctx["mood_pattern"] = self.mood["patterns"][mood_tag]

        # active rules
        if self.rules.get("explicit"):
            ctx["explicit_rules"] = self.rules["explicit"]

        return ctx

    def summary_for_prompt(self, situation: Dict[str, Any] = None) -> str:
        """Generate a concise text block for Reasoner prompt."""
        ctx = self.relevant_context(situation or {})
        lines = ["## 用户长期画像（L3 记忆）"]

        p = self.preferences
        if p.get("artists"):
            top = sorted(p["artists"].items(), key=lambda x: x[1].get("strength", 0), reverse=True)[:5]
            lines.append("- 偏好歌手: " + ", ".join(f"{a}({w.get('strength',0):.1f})" for a, w in top))
        if p.get("genres"):
            top = sorted(p["genres"].items(), key=lambda x: x[1].get("strength", 0), reverse=True)[:3]
            lines.append("- 偏好风格: " + ", ".join(f"{g}({w.get('strength',0):.1f})" for g, w in top))
        if p.get("disliked_artists"):
            lines.append("- 不喜欢的歌手: " + ", ".join(p["disliked_artists"].keys()))

        # Semantic matches: preferences closest to current situation
        semantic = ctx.get("semantic_matches", [])
        if semantic:
            lines.append("- 情境关联偏好: " + ", ".join(
                f"{m['name']}({m['type']},{m['similarity']:.2f})" for m in semantic))

        b = self.behavior
        lines.append(f"- 平均切歌时间: {b.get('avg_skip_time_sec', '?')} 秒")
        if b.get("peak_hours"):
            ph = b["peak_hours"][:3]
            lines.append("- 活跃时段: " + ", ".join(f"{h['hour']}点({h['count']}次)" for h in ph))

        if ctx.get("mood_pattern"):
            lines.append(f"- 当前情绪模式: {ctx['mood_pattern']}")

        if self.rules.get("explicit"):
            lines.append("- 用户明确规则: " + "; ".join(self.rules["explicit"]))

        pending = self.pending_for_prompt()
        if pending:
            lines.append("")
            lines.append(pending)

        digest = self._meta.get("recent_digest", {})
        if digest.get("top_songs"):
            lines.append("- 近期常播: " + ", ".join(f"#{s['id'][-6:]}({s['plays']}次)" for s in digest["top_songs"][:3]))
        if digest.get("fast_skips"):
            lines.append("- 近期快速切掉: " + ", ".join(digest["fast_skips"][:3]))

        return "\n".join(lines)

    # ── MARS-style preference operations ──────────────────

    def _pref_entry(self, collection: str, key: str) -> Dict[str, Any]:
        """Get or create a preference entry with defaults."""
        store = self.preferences.get(collection, {})
        if key not in store:
            store[key] = {"strength": 0.5, "evidence": [], "last_reinforced": None, "decay": 0.01, "source": "observed"}
            self.preferences[collection] = store
        return store[key]

    def reinforce(self, collection: str, key: str, evidence: str, amount: float = 0.05):
        """Strengthen a preference with evidence."""
        entry = self._pref_entry(collection, key)
        entry["strength"] = min(1.0, entry["strength"] + amount)
        entry["evidence"].append(f"{datetime.now().strftime('%m-%d %H:%M')} {evidence}")
        if len(entry["evidence"]) > 10:
            entry["evidence"] = entry["evidence"][-10:]
        entry["last_reinforced"] = datetime.now().isoformat()

    def weaken(self, collection: str, key: str, evidence: str, amount: float = 0.03):
        """Weaken a preference with counter-evidence."""
        entry = self._pref_entry(collection, key)
        entry["strength"] = max(0.1, entry["strength"] - amount)
        entry["evidence"].append(f"{datetime.now().strftime('%m-%d %H:%M')} ✗ {evidence}")
        if len(entry["evidence"]) > 10:
            entry["evidence"] = entry["evidence"][-10:]

    def decay_all(self):
        """Apply time-based decay to all preferences."""
        now = datetime.now()
        for collection in ["artists", "genres", "eras"]:
            for key, entry in self.preferences.get(collection, {}).items():
                if entry.get("last_reinforced"):
                    days_since = (now - datetime.fromisoformat(entry["last_reinforced"])).days
                    decay_amount = days_since * entry.get("decay", 0.01)
                    entry["strength"] = max(0.1, entry["strength"] - decay_amount)

    # ── User confirmation queue ───────────────────────────

    def queue_confirmation(self, proposal: Dict[str, Any]):
        """Add a proposed update to the confirmation queue."""
        proposal["queued_at"] = datetime.now().isoformat()
        proposal["status"] = "pending"
        self.preferences.setdefault("_pending", []).append(proposal)
        self._save()

    def confirm(self, proposal_id: str) -> bool:
        """User accepts a pending proposal."""
        for p in self.preferences.get("_pending", []):
            if p.get("id") == proposal_id:
                p["status"] = "confirmed"
                if p.get("action") == "reinforce":
                    self.reinforce(p["collection"], p["key"], "用户确认")
                elif p.get("action") == "weaken":
                    self.weaken(p["collection"], p["key"], "用户确认")
                self._save()
                return True
        return False

    def reject(self, proposal_id: str):
        """User rejects a pending proposal."""
        for p in self.preferences.get("_pending", []):
            if p.get("id") == proposal_id:
                p["status"] = "rejected"
                self._save()
                return

    def expire_pending(self, max_age_days: int = 7):
        """Auto-expire old pending proposals."""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        self.preferences["_pending"] = [
            p for p in self.preferences.get("_pending", [])
            if datetime.fromisoformat(p.get("queued_at", "")) > cutoff
        ]

    def pending_for_prompt(self) -> str:
        """Generate a prompt snippet for Agent to ask user about pending updates."""
        pending = [p for p in self.preferences.get("_pending", []) if p.get("status") == "pending"]
        if not pending:
            return ""
        lines = ["## 待确认的记忆更新"]
        for p in pending[:2]:
            desc = p.get("description", p.get("key", "?"))
            lines.append(f"- [{p.get('id','?')}] {desc}")
        return "\n".join(lines)

    # ── Manual updates (user-confirmed) ────────────────────

    def set_artist_preference(self, name: str, weight: float):
        now = datetime.now().isoformat()
        existing = self.preferences["artists"].get(name, {})
        self.preferences["artists"][name] = {
            "weight": round(max(0, min(1, weight)), 2),
            "updated": now,
            "version": existing.get("version", 0) + 1,
            "previous_weight": existing.get("weight"),
        }
        self._save()

    def add_explicit_rule(self, rule: str):
        if rule not in self.rules["explicit"]:
            self.rules["explicit"].append(rule)
            self._save()

    def add_inferred_rule(self, rule: str):
        """System-inferred rule, lower confidence than explicit."""
        if rule not in self.rules["inferred"]:
            self.rules["inferred"].append(rule)
            self._save()


# singleton
l3_profile = L3Profile()
