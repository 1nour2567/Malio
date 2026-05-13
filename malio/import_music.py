"""
Import music files from a directory into the Malio library.
Scans for mp3/flac/wav/m4a/ogg, parses "Artist - Title" from filenames,
copies to malio/data/audio/songs/, inserts into DB with E/W/D analysis.

Usage: python import_music.py /mnt/e/音乐
"""

import sys
import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add malio to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.music import Song
from core.audio_analyzer import analyze_audio_file

DB_PATH = Path(__file__).resolve().parent / "malio.db"
AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio" / "songs"
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".ogg"}


def parse_filename(filename: str) -> tuple[str, list[str]]:
    """Parse 'Artist - Title.ext' into (title, [artist])."""
    stem = Path(filename).stem
    if " - " in stem:
        parts = stem.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()
        return title, [artist]
    return stem, ["Unknown"]


def import_directory(source_dir: str):
    source = Path(source_dir)
    if not source.exists():
        print(f"Directory not found: {source_dir}")
        return

    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    session = Session()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all audio files
    audio_files = []
    for f in source.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            audio_files.append(f)

    print(f"Found {len(audio_files)} playable audio files in {source_dir}")

    imported = 0
    skipped = 0

    for fpath in sorted(audio_files):
        fname = fpath.name
        # Skip Kugou encrypted files
        if ".kgm" in fname.lower() or fname.lower().endswith(".kgm") or fname.lower().endswith(".kgma"):
            skipped += 1
            continue
        title, artist = parse_filename(fname)

        # Check if already imported (by filename match in audio_path)
        existing = session.query(Song).filter(Song.audio_path.like(f"%{fname}")).first()
        if existing:
            print(f"  SKIP (exists): {fname}")
            skipped += 1
            continue

        # Copy file
        dest = AUDIO_DIR / fname
        if not dest.exists():
            shutil.copy2(str(fpath), str(dest))

        # Analyze E/W/D
        try:
            ewd = analyze_audio_file(str(dest))
        except Exception:
            ewd = {"energy": 0.5, "warmth": 0.5, "density": 0.5}

        # Create song
        song_id = f"import_{str(uuid.uuid4())[:8]}"
        song = Song(
            id=song_id,
            title=title,
            artist=artist,
            album="",
            genre=[],
            duration=None,
            features={},
            audio_path=f"songs/{fname}",
            energy=ewd.get("energy"),
            warmth=ewd.get("warmth"),
            density=ewd.get("density"),
            energy_updated_at=datetime.now(timezone.utc),
        )
        session.add(song)
        imported += 1
        print(f"  OK: {fname}  → {title}  E={ewd.get('energy',0):.2f} W={ewd.get('warmth',0):.2f} D={ewd.get('density',0):.2f}")

    session.commit()
    total = session.query(Song).count()
    session.close()

    print(f"\nDone: {imported} imported, {skipped} skipped, {total} total in library")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_music.py <directory>")
        sys.exit(1)
    import_directory(sys.argv[1])
