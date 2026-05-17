"""L4 Permanent Memory — append-only, immutable fact log.
Per-date files in malio/data/history/. Hash-verified entries.
Agent can only read last 30 days. Older needs explicit auth.
"""

import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List


class L4History:
    """Append-only log. Every playback, interaction, and system event is recorded."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base, "data", "history")
        self._dir = data_dir
        os.makedirs(self._dir, exist_ok=True)

    # ── Append ────────────────────────────────────────────

    def record(self, event_type: str, detail: Dict[str, Any] = None):
        """Append one event to today's log file."""
        entry = {
            "type": event_type,
            "detail": detail or {},
            "ts": datetime.now().isoformat(),
            "hash": "",
        }
        entry["hash"] = self._hash(entry)
        self._append(entry)

    def _append(self, entry: Dict[str, Any]):
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._dir, f"{date_str}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Read (last 30 days by default) ────────────────────

    def read_recent(self, days: int = 30) -> List[Dict[str, Any]]:
        """Read events from the last N days."""
        events = []
        for d in range(days):
            date = datetime.now() - timedelta(days=d)
            path = os.path.join(self._dir, date.strftime("%Y-%m-%d") + ".jsonl")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                events.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        return events

    def count_today(self) -> int:
        """Count today's events."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._dir, f"{date_str}.jsonl")
        if not os.path.exists(path):
            return 0
        return sum(1 for _ in open(path, "r", encoding="utf-8"))

    # ── Hash ──────────────────────────────────────────────

    @staticmethod
    def _hash(entry: Dict[str, Any]) -> str:
        raw = json.dumps({"type": entry["type"], "detail": entry["detail"], "ts": entry["ts"]},
                         ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Verification ──────────────────────────────────────

    def verify_today(self) -> bool:
        """Check that all entries in today's log have valid hashes."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._dir, f"{date_str}.jsonl")
        if not os.path.exists(path):
            return True
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False
                expected = entry.get("hash", "")
                entry["hash"] = ""
                actual = self._hash(entry)
                if expected != actual:
                    return False
        return True


# singleton
l4_history = L4History()
