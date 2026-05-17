"""Lightweight metrics — CSV log for later pandas analysis."""
import csv
import os
import threading
from datetime import datetime
from typing import Dict, Any


class MetricsCollector:
    """Per-interaction metrics. Logged to CSV, consumable by pandas."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base, "data")
        self._path = os.path.join(data_dir, "metrics.csv")
        self._lock = threading.Lock()
        self._ensure_header()

    def _ensure_header(self):
        if not os.path.exists(self._path):
            with open(self._path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "ts", "intent", "react_rounds",
                    "song_count", "had_songs", "auto_play",
                    "input_len", "input_has_recommend", "input_has_skip",
                    "response_len",
                ])

    def record(self, entry: Dict[str, Any]):
        with self._lock:
            with open(self._path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    entry.get("ts", ""),
                    entry.get("intent", ""),
                    entry.get("react_rounds", 0),
                    entry.get("song_count", 0),
                    1 if entry.get("had_songs") else 0,
                    1 if entry.get("auto_play") else 0,
                    entry.get("input_len", 0),
                    1 if entry.get("input_has_recommend") else 0,
                    1 if entry.get("input_has_skip") else 0,
                    entry.get("response_len", 0),
                ])


# singleton
metrics = MetricsCollector()
