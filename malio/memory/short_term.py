"""L2 Short-Term Memory — 24-hour behavior snapshots with hourly summaries."""

import time
import threading
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, Any, List, Optional


class L2Memory:
    """Tracks user behavior for the last 24 hours. Generates hourly summaries."""

    def __init__(self, max_events: int = 2000):
        self._events: deque = deque(maxlen=max_events)
        self._summaries: List[Dict[str, Any]] = []  # hourly summaries
        self._lock = threading.Lock()
        self._last_summary_hour = -1

    # ── Event recording ──────────────────────────────────────

    def record(self, event_type: str, detail: Optional[Dict[str, Any]] = None):
        with self._lock:
            self._events.append({
                "type": event_type,
                "detail": detail or {},
                "ts": time.time(),
            })
        self._maybe_summarize()

    # ── Hourly summary ───────────────────────────────────────

    def _maybe_summarize(self):
        now = datetime.now()
        if now.hour == self._last_summary_hour:
            return
        self._last_summary_hour = now.hour
        cutoff = (now - timedelta(hours=1)).timestamp()

        with self._lock:
            recent = [e for e in self._events if e["ts"] >= cutoff]
            if not recent:
                return

            plays = [e for e in recent if e["type"] == "play"]
            skips = [e for e in recent if e["type"] == "skip"]
            pauses = [e for e in recent if e["type"] == "pause"]
            vol_changes = [e for e in recent if e["type"] == "volume_change"]
            core_events = [e for e in recent if e["type"].startswith("core_")]

            # average play duration for skipped songs
            skip_durations = []
            for s in skips:
                d = s.get("detail", {}).get("played_sec", 0)
                if d > 0:
                    skip_durations.append(d)

            summary = {
                "hour": now.strftime("%Y-%m-%d %H:00"),
                "plays": len(plays),
                "skips": len(skips),
                "pauses": len(pauses),
                "vol_changes": len(vol_changes),
                "core_interactions": len(core_events),
                "avg_skip_time": round(sum(skip_durations) / len(skip_durations), 1) if skip_durations else None,
                "ts": now.timestamp(),
            }
            self._summaries.append(summary)
            # keep last 24 summaries only
            if len(self._summaries) > 24:
                self._summaries = self._summaries[-24:]

    # ── Expiry ───────────────────────────────────────────────

    def expire(self):
        cutoff = (datetime.now() - timedelta(hours=24)).timestamp()
        with self._lock:
            self._events = deque(
                [e for e in self._events if e["ts"] >= cutoff],
                maxlen=self._events.maxlen
            )

    # ── Queries for Reasoner ──────────────────────────────────

    def recent_activity(self, minutes: int = 30) -> str:
        """Human-readable summary of recent activity for Agent context."""
        cutoff = time.time() - minutes * 60
        with self._lock:
            recent = [e for e in self._events if e["ts"] >= cutoff]

        if not recent:
            return "最近 30 分钟无活动"

        plays = sum(1 for e in recent if e["type"] == "play")
        skips = sum(1 for e in recent if e["type"] == "skip")
        cores = sum(1 for e in recent if e["type"].startswith("core_"))

        parts = []
        if plays: parts.append(f"播放了 {plays} 首歌")
        if skips: parts.append(f"切歌 {skips} 次")
        if cores: parts.append(f"与内核互动 {cores} 次")

        # compute skip mood
        all_skips = [e for e in recent if e["type"] == "skip"]
        fast_skips = sum(1 for s in all_skips if s.get("detail", {}).get("played_sec", 999) < 60)
        if fast_skips > 3:
            parts.append(f"快速切歌 {fast_skips} 次（可能心情烦躁）")

        return "；".join(parts) if parts else "最近 30 分钟无活动"

    def today_summary(self) -> str:
        """Summary of today's behavior for Agent context."""
        self.expire()
        with self._lock:
            all_events = list(self._events)

        if not all_events:
            return "今日暂无播放记录"

        plays = sum(1 for e in all_events if e["type"] == "play")
        skips = sum(1 for e in all_events if e["type"] == "skip")
        unique_songs = len(set(
            e.get("detail", {}).get("song_id", "")
            for e in all_events if e["type"] == "play" and e.get("detail", {}).get("song_id")
        ))
        total_pause = sum(
            e.get("detail", {}).get("pause_count", 0)
            for e in all_events if e["type"] == "pause"
        )

        return f"今日播放 {plays} 首歌（{unique_songs} 首不同），切歌 {skips} 次，暂停 {total_pause} 次"

    def summary_for_prompt(self) -> str:
        """Concise text block for injection into Reasoner prompt."""
        lines = [
            "## 用户近期行为（L2 记忆）",
            f"- {self.recent_activity(30)}",
            f"- {self.today_summary()}",
        ]
        # add last 2 hourly summaries
        if self._summaries:
            lines.append("- 最近时段摘要：")
            for s in self._summaries[-2:]:
                mood_note = ""
                if s.get("avg_skip_time") and s["avg_skip_time"] < 90:
                    mood_note = " （可能不耐心）"
                lines.append(
                    f"  {s['hour']}: 播放 {s['plays']} 首, "
                    f"切歌 {s['skips']} 次, "
                    f"平均切歌时间 {s.get('avg_skip_time', '?')} 秒{mood_note}"
                )
        return "\n".join(lines)


# L3 stub — will be expanded later
class L3Profile:
    """Placeholder for L3 long-term profile."""
    pass


# singleton
l2_memory = L2Memory()
