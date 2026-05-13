"""
One-shot migration: add E/W/D columns to songs table and populate values
for existing tracks using audio analysis.

Usage:  python -m malio.migrate_ewd
        (run from the AI_music-master directory)

Idempotent — safe to run multiple times.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Ensure malio package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from core.audio_analyzer import analyze_audio_file, batch_analyze_library
from models.music import Song

DB_PATH = Path(__file__).resolve().parent / "malio.db"
AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio" / "songs"

# ── Pre-computed fallback estimates for the 10 known songs ──────
# Used ONLY when real audio analysis cannot produce values.
FALLBACKS = {
    "Kid Cudi - Maui Wowie.mp3":                         (0.52, 0.55, 0.48),
    "Kid Cudi - Maui Wowie (Explicit).mp3":              (0.52, 0.55, 0.48),
    "MC Sniper、Rachael Yamagata - 夜间飞行.flac":       (0.45, 0.60, 0.50),
    "MC Sniper、Rachael Yamagata - 야간비행 (夜间飞行)(feat. 레이첼 야마가타).flac": (0.45, 0.60, 0.50),
    "Ray Saetta - Somehow.mp3":                          (0.55, 0.50, 0.52),
    "Terror Squad、Remy Ma、Fat Joe、Dre、Armageddon - Take Me Home (Explicit).mp3": (0.62, 0.48, 0.55),
    "周杰伦 - 你听得到.mp3":                             (0.42, 0.58, 0.47),
    "周杰伦 - 反方向的钟.mp3":                           (0.50, 0.52, 0.50),
    "周杰伦 - 爱在西元前.mp3":                           (0.48, 0.54, 0.49),
    "周杰伦 - 给我一首歌的时间.mp3":                     (0.44, 0.56, 0.46),
    "周杰伦 - 龙卷风.mp3":                               (0.58, 0.50, 0.53),
    "椎名林檎 - 17.mp3":                                 (0.60, 0.45, 0.62),
}


def migrate():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Add columns (idempotent)
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("songs")}

    new_cols = [
        ("energy", "FLOAT"),
        ("warmth", "FLOAT"),
        ("density", "FLOAT"),
        ("energy_updated_at", "DATETIME"),
    ]

    with engine.connect() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE songs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
                print(f"[migrate_ewd] Added column: {col_name}")
            else:
                print(f"[migrate_ewd] Column already exists: {col_name}")

    # 2. Run audio analysis on songs without E/W/D
    updated = batch_analyze_library(session)
    print(f"[migrate_ewd] Audio analysis updated {updated} songs.")

    # 3. Fallback: fill any remaining NULLs with pre-computed estimates
    fallback_count = _apply_fallbacks(session)
    print(f"[migrate_ewd] Fallback estimates applied to {fallback_count} songs.")

    # 4. Report
    total = session.query(Song).count()
    with_energy = session.query(Song).filter(Song.energy.isnot(None)).count()
    with_warmth = session.query(Song).filter(Song.warmth.isnot(None)).count()
    with_density = session.query(Song).filter(Song.density.isnot(None)).count()

    print(f"\n[migrate_ewd] Done. {total} total songs.")
    print(f"  energy: {with_energy}/{total}   warmth: {with_warmth}/{total}   density: {with_density}/{total}")

    session.close()


def _apply_fallbacks(session) -> int:
    """Apply pre-computed E/W/D fallbacks for songs still missing values."""
    count = 0
    songs = session.query(Song).filter(
        (Song.energy.is_(None)) |
        (Song.warmth.is_(None)) |
        (Song.density.is_(None))
    ).all()

    for song in songs:
        # Try matching by audio_path filename
        fname = Path(song.audio_path).name if song.audio_path else None
        values = None
        if fname and fname in FALLBACKS:
            values = FALLBACKS[fname]
        if values is None:
            # Try partial match
            for key, val in FALLBACKS.items():
                if fname and Path(key).name == fname:
                    values = val
                    break
        if values is None:
            # Try match by title
            for key, val in FALLBACKS.items():
                if song.title and song.title in key:
                    values = val
                    break

        if values is None:
            # Last resort: neutral midpoint
            values = (0.50, 0.50, 0.50)

        if song.energy is None:
            song.energy = values[0]
        if song.warmth is None:
            song.warmth = values[1]
        if song.density is None:
            song.density = values[2]

        if song.energy_updated_at is None:
            song.energy_updated_at = datetime.now(timezone.utc)

        count += 1

    session.commit()
    return count


if __name__ == "__main__":
    migrate()
