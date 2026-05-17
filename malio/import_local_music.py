"""One-shot: scan a music directory and import all missing songs into the DB."""
import os, sys, uuid, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MUSIC_DIR = "/mnt/e/音乐"
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "audio", "songs")

os.makedirs(AUDIO_DIR, exist_ok=True)

from models.music import Song
from core.recommendation_engine import RecommendationEngine

engine = RecommendationEngine()
session = engine.Session()
db_titles = {s.title for s in session.query(Song).all()}
imported = 0

for fname in sorted(os.listdir(MUSIC_DIR)):
    if not fname.lower().endswith(('.mp3', '.flac', '.m4a', '.wav', '.ogg')):
        continue

    name = os.path.splitext(fname)[0]
    ext = os.path.splitext(fname)[1]

    # Parse "Artist - Title.ext"
    parts = name.split(' - ', 1)
    artist = [parts[0].strip()] if len(parts) > 1 else ["Unknown"]
    title = parts[1].strip() if len(parts) > 1 else name.strip()

    # Skip instrumental markers
    title = re.sub(r'[_（(]?(SQ|HQ|Inst|Instrumental|Live|Demo|Explicit)[_）)]?', '', title).strip()

    if title in db_titles or name in db_titles:
        continue

    # Copy file to audio dir
    src_path = os.path.join(MUSIC_DIR, fname)
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', fname)
    dst_path = os.path.join(AUDIO_DIR, safe_name)
    if not os.path.exists(dst_path):
        try:
            with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
                dst.write(src.read())
        except Exception as e:
            print(f"  SKIP {fname}: {e}")
            continue

    song_id = f"local_{uuid.uuid4().hex[:4]}"
    song = Song(
        id=song_id, title=title, artist=artist,
        album="Local Import", duration=180,
        audio_path=safe_name,
    )
    session.add(song)
    db_titles.add(title)
    imported += 1
    print(f"  + [{song_id}] {title} — {artist}")

session.commit()
session.close()
print(f"\nDone. Imported {imported} new songs. DB now has {len(db_titles)} songs.")
