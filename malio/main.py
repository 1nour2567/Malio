from fastapi import FastAPI, HTTPException, Depends, Query, Response, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional
import json
import asyncio
import datetime as dt
from dotenv import load_dotenv
from core.scene_aware_engine import SceneAwareEngine
from core.recommendation_engine import RecommendationEngine
from core.device_control import DeviceControl
from core.state_manager import (get_playback, set_playlist, next_in_queue,
                                 get_core_events, get_chat_history, state_store,
                                 query_local_songs, enrich_songs,
                                 add_fast_skip, count_recent_fast_skips, clear_fast_skips)
from integrations.kimi_integration import KimiIntegration
from integrations.spotify_integration import SpotifyIntegration
from integrations.netease_integration import NeteaseIntegration
from integrations.elevenlabs_integration import ElevenLabsIntegration
from data.data_importer import MusicDataImporter
from config.config import settings
from memory.short_term import l2_memory
from memory.history import l4_history
from memory.user_profile import l3_profile
from agent.perception import Perception
from agent.router import Router
from agent.reasoner import Reasoner
from agent.providers import create_providers_from_config
from agent.tools import ToolRegistry
from agent.feedback import Feedback
from agent.persona import persona_engine
from agent.pipeline import Pipeline, MusicResponse
from agent.music_agent import MusicAgent
from agent.visual_agent import VisualAgent

# Load .env file
load_dotenv()

import contextlib

# ═══════════════════════════════════════════════════════════════
# App setup
# ═══════════════════════════════════════════════════════════════

@contextlib.asynccontextmanager
async def lifespan(app):
    asyncio.create_task(_atmosphere_loop())
    asyncio.create_task(_distill_loop())
    asyncio.create_task(_persist_loop())
    yield

app = FastAPI(
    title="Malio Music Agent API",
    description="AI music agent that provides personalized music recommendations",
    version="0.3.0",
    lifespan=lifespan
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    print(f"[error] {type(exc).__name__}: {exc}")
    print(traceback.format_exc())
    return Response(
        content=json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False),
        status_code=500, media_type="application/json"
    )

# CORS middleware
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=cors_origins,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Static files for audio
import os
audio_dir = os.path.join(os.path.dirname(__file__), "data", "audio")
if not os.path.exists(audio_dir):
    os.makedirs(audio_dir)
songs_dir = os.path.join(audio_dir, "songs")
if not os.path.exists(songs_dir):
    os.makedirs(songs_dir)
app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

# ═══════════════════════════════════════════════════════════════
# Initialize engines
# ═══════════════════════════════════════════════════════════════

scene_engine = SceneAwareEngine()
recommendation_engine = RecommendationEngine()
kimi_integration = KimiIntegration()
device_control = DeviceControl()
spotify_integration = SpotifyIntegration()
netease_integration = NeteaseIntegration()
elevenlabs_integration = ElevenLabsIntegration()

# ═══════════════════════════════════════════════════════════════
# Initialize agent components
# ═══════════════════════════════════════════════════════════════

provider_registry = create_providers_from_config(settings)
perception = Perception()
router = Router()
reasoner = Reasoner(provider_registry)
tool_registry = ToolRegistry()
feedback_mgr = Feedback()
feedback_mgr._perception = perception

# ── MusicAgent (single-responsibility music worker) ──
music_agent = MusicAgent(recommendation_engine, netease_integration, tool_registry,
                         provider_registry=provider_registry, reasoner=reasoner,
                         feedback_mgr=feedback_mgr)
visual_agent = VisualAgent(persona_engine, feedback_mgr=feedback_mgr,
                           scene_engine=scene_engine)

# ── Pipeline (thin in main.py, heavy in agent/pipeline.py) ──
pipeline = Pipeline(perception, router, reasoner, provider_registry, tool_registry,
                    feedback_mgr, recommendation_engine, device_control,
                    l2_memory, l3_profile, persona_engine,
                    scene_engine=scene_engine, music_agent=music_agent,
                    visual_agent=visual_agent)

# ═══════════════════════════════════════════════════════════════
# Background loops
# ═══════════════════════════════════════════════════════════════

async def _atmosphere_loop():
    while True:
        await asyncio.sleep(30)
        try:
            _atmosphere_loop._ticks = getattr(_atmosphere_loop, '_ticks', 0) + 1
            now = dt.datetime.now()
            if _atmosphere_loop._ticks % 60 == 0:  # every 30 min
                persona_engine.drift_natural(now.hour)
                persona_engine.save()
            tod = "morning" if 5 <= now.hour < 12 else \
                  "afternoon" if 12 <= now.hour < 18 else \
                  "evening" if 18 <= now.hour < 22 else "night"
            atm = persona_engine.derive_atmosphere(tod, now.hour)

            # ── Weather blend: fetch every 5 min, slow polling ──
            if _atmosphere_loop._ticks % 10 == 0:  # every 5 min
                try:
                    _atmosphere_loop._cached_weather = \
                        scene_engine.get_weather_context(24.9175, 118.6465) or {}
                except Exception:
                    _atmosphere_loop._cached_weather = getattr(_atmosphere_loop, '_cached_weather', {})
            weather = getattr(_atmosphere_loop, '_cached_weather', {})
            atm = persona_engine.blend_weather(atm, weather)
            await feedback_mgr.push_snapshot(atmosphere=atm)

            # ── Autonomous behavior: Agent acts on its own ──
            auto = persona_engine.maybe_autonomous_action()
            if auto:
                await feedback_mgr.push_snapshot(core_action=auto)
        except Exception as e:
            print(f"[atmosphere-loop] {e}")

_LAST_DISTILL = None
async def _distill_loop():
    global _LAST_DISTILL
    while True:
        await asyncio.sleep(3600)
        now = dt.datetime.now()
        if _LAST_DISTILL and (now - _LAST_DISTILL).total_seconds() < 86400:
            continue
        if l4_history.count_today() < 5:
            continue
        try:
            l2_memory.expire()
            summaries = list(l2_memory._summaries)
            events = list(l2_memory._events)
            l4_events = l4_history.read_recent(1)
            l3_profile.distill_from_l2(summaries, events, l4_events)
            _LAST_DISTILL = now
            print(f"[distill] L2→L3 ok — {len(summaries)} summaries")
        except Exception as e:
            print(f"[distill] failed: {e}")

async def _persist_loop():
    while True:
        await asyncio.sleep(300)
        try:
            from core.state_manager import _sessions
            for uid in list(_sessions.keys()):
                state_store.save_if_dirty(uid)
        except Exception as e:
            print(f"[persist] {e}")

# ═══════════════════════════════════════════════════════════════
# Tool registry
# ═══════════════════════════════════════════════════════════════

tool_registry.register("get_local_songs", "获取本地曲库中的歌曲（默认80首，可指定limit）", {"limit": "int"},
    lambda limit=80, **kw: {"songs": query_local_songs(limit, recommendation_engine)})
tool_registry.register("search_music", "搜索歌曲，支持歌名、歌手、风格", {"query": "string", "limit": "int"},
    lambda query, limit=5, **kw: netease_integration.search_tracks(query, limit))
tool_registry.register("get_weather", "获取当前天气和温度", {"city": "string"},
    lambda city="", **kw: scene_engine.get_weather_context(24.9175, 118.6465) or {})
tool_registry.register("check_history", "查询最近播放记录", {"limit": "int"},
    lambda limit=10, **kw: _get_history(limit))
tool_registry.register("get_lyrics", "获取歌曲歌词", {"song_id": "string", "title": "string"},
    lambda song_id="", title="", **kw: {"lyrics": f"获取歌词功能需对接歌词API，歌曲ID: {song_id}", "title": title})
tool_registry.register("get_current_song", "获取当前正在播放的歌曲", {},
    lambda **kw: playback_state.get("current", {}) or {"note": "暂无播放"})
tool_registry.register("get_playlist", "获取当前播放列表", {"limit": "int"},
    lambda limit=20, **kw: {"playlist": _get_current_playlist(limit)})
tool_registry.register("get_recommendations", "获取情境化音乐推荐", {"user_id": "string", "limit": "int"},
    lambda user_id="default", limit=5, **kw: recommendation_engine.get_contextual_recommendations(user_id, limit) or [])
tool_registry.register("get_l2_summary", "查询用户近期行为", {},
    lambda **kw: {"summary": l2_memory.recent_activity(30), "today": l2_memory.today_summary()})
tool_registry.register("get_l3_profile", "查询用户长期音乐偏好画像", {},
    lambda **kw: {"preferences": l3_profile.preferences.get("artists", {}), "behavior": l3_profile.behavior})

def _get_history(limit=10):
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        songs = session.query(Song).order_by(Song.id.desc()).limit(limit).all()
        return [{"id": s.id, "title": s.title, "artist": s.artist} for s in songs]
    finally:
        session.close()

def _get_current_playlist(limit=20):
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        songs = session.query(Song).limit(limit).all()
        return [{"id": s.id, "title": s.title, "artist": s.artist} for s in songs]
    finally:
        session.close()

# ═══════════════════════════════════════════════════════════════
# Restore last session
# ═══════════════════════════════════════════════════════════════

state_store.restore("default")

# ═══════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════

class UserInput(BaseModel):
    user_id: str = "default"
    input: str
    context: Dict[str, Any] = None

class RecommendationRequest(BaseModel):
    user_id: str = "default"
    limit: int = 10
    context: Dict[str, Any] = None

class PlaylistRequest(BaseModel):
    user_id: str = "default"
    songs: List[Dict[str, Any]]
    context: Dict[str, Any] = None

class EnergyUpdateRequest(BaseModel):
    energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warmth: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    density: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    @model_validator(mode="after")
    def at_least_one_field(self) -> "EnergyUpdateRequest":
        if self.energy is None and self.warmth is None and self.density is None:
            raise ValueError("At least one of energy, warmth, density must be provided")
        return self

class PlaylistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    playlist_type: str = "manual"
    seed_songs: Optional[List[Dict[str, Any]]] = None
    context: Optional[Dict[str, Any]] = None

class PlaylistUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None

class PlaylistSongRequest(BaseModel):
    song_id: str

class PlaylistGenerateRequest(BaseModel):
    captured_songs: List[Dict[str, Any]]
    hour: Optional[int] = None

class SpotifySearchRequest(BaseModel):
    query: str
    limit: int = 10

class SpotifyRecommendationRequest(BaseModel):
    seed_tracks: Optional[List[str]] = None
    seed_artists: Optional[List[str]] = None
    seed_genres: Optional[List[str]] = None
    limit: int = 20
    min_acousticness: Optional[float] = None
    max_acousticness: Optional[float] = None
    min_danceability: Optional[float] = None
    max_danceability: Optional[float] = None
    min_energy: Optional[float] = None
    max_energy: Optional[float] = None
    min_instrumentalness: Optional[float] = None
    max_instrumentalness: Optional[float] = None
    min_liveness: Optional[float] = None
    max_liveness: Optional[float] = None
    min_loudness: Optional[float] = None
    max_loudness: Optional[float] = None
    min_speechiness: Optional[float] = None
    max_speechiness: Optional[float] = None
    min_tempo: Optional[float] = None
    max_tempo: Optional[float] = None
    min_valence: Optional[float] = None
    max_valence: Optional[float] = None
    min_popularity: Optional[int] = None
    max_popularity: Optional[int] = None

class SpotifyAddRequest(BaseModel):
    track_id: str

class NeteaseAddRequest(BaseModel):
    id: str
    title: str = ""
    artist: List[str] = []
    album: str = ""
    album_art: str = ""
    duration: int = 180
    preview_url: str = ""
    external_url: str = ""
    genre: List[str] = []
    audio_path: str = ""

class NeteaseImportRequest(BaseModel):
    query: str
    limit: int = 20

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    model_id: Optional[str] = None

# ═══════════════════════════════════════════════════════════════
# Routes — Chat (primary agent entry point)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/chat", response_model=MusicResponse)
async def chat_with_malio(request: UserInput):
    """Chat with Malio — delegates to 5-stage agent pipeline."""
    return await pipeline.run(request)

# ═══════════════════════════════════════════════════════════════
# Routes — Recommendations
# ═══════════════════════════════════════════════════════════════

@app.post("/api/recommend", response_model=MusicResponse)
async def get_recommendations(request: RecommendationRequest):
    try:
        if request.context:
            recommendations = recommendation_engine.get_recommendations(
                request.user_id, request.context, request.limit)
        else:
            recommendations = recommendation_engine.get_contextual_recommendations(
                request.user_id, request.limit)
        context = request.context or scene_engine.get_full_context(request.user_id)
        response = kimi_integration.generate_music_recommendation(
            "Recommend me some music", context, recommendations)
        return MusicResponse(response=response, recommendations=recommendations)
    except Exception as e:
        print(f"Error in /api/recommend: {e}")
        return MusicResponse(response="抱歉，我遇到了一些问题。", recommendations=[])

@app.post("/api/generate-playlist-name")
async def generate_playlist_name(request: PlaylistRequest):
    try:
        context = request.context or scene_engine.get_full_context(request.user_id)
        playlist_name = kimi_integration.generate_playlist_name(request.songs, context)
        return {"playlist_name": playlist_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/context")
async def get_current_context(user_id: str = "default"):
    try:
        return scene_engine.get_full_context(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/import-data")
async def import_music_data():
    try:
        importer = MusicDataImporter()
        importer.import_data(settings.music_data_path)
        return {"message": "Data import completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# Routes — Device control
# ═══════════════════════════════════════════════════════════════

@app.get("/api/devices")
async def get_devices():
    try:
        return {"devices": device_control.discover_devices()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/connect")
async def connect_device(device_id: str):
    try:
        if device_control.connect_device(device_id):
            return {"message": "Device connected successfully"}
        raise HTTPException(status_code=404, detail="Device not found")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/disconnect")
async def disconnect_device():
    try:
        if device_control.disconnect_device():
            return {"message": "Device disconnected successfully"}
        return {"message": "No device connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/play")
async def play_music(song_uri: str):
    try:
        if device_control.play(song_uri): return {"message": "Music playing"}
        raise HTTPException(status_code=400, detail="Failed to play music")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/pause")
async def pause_music():
    try:
        if device_control.pause(): return {"message": "Music paused"}
        raise HTTPException(status_code=400, detail="Failed to pause music")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/stop")
async def stop_music():
    try:
        if device_control.stop(): return {"message": "Music stopped"}
        raise HTTPException(status_code=400, detail="Failed to stop music")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/volume")
async def set_volume(volume: int):
    try:
        if device_control.set_volume(volume): return {"message": f"Volume set to {volume}"}
        raise HTTPException(status_code=400, detail="Failed to set volume")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/devices/status")
async def get_device_status():
    try:
        status = device_control.get_device_status()
        return status if status else {"message": "No device connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# Routes — Song management
# ═══════════════════════════════════════════════════════════════

@app.get("/api/songs")
async def get_all_songs():
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        songs = session.query(Song).all()
        return {"songs": [{
            "id": s.id, "title": s.title, "artist": s.artist,
            "album": s.album, "genre": s.genre, "release_year": s.release_year,
            "duration": s.duration or 180, "audio_path": s.audio_path or "",
            "preview_url": (s.features or {}).get("preview_url", ""),
            "album_art": (s.features or {}).get("album_art", ""),
            "external_url": (s.features or {}).get("external_url", ""),
            "energy": s.energy, "warmth": s.warmth, "density": s.density,
            "energy_updated_at": s.energy_updated_at.isoformat() if s.energy_updated_at else None
        } for s in songs], "total": len(songs)}
    except Exception as e:
        print(f"Error getting songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.post("/api/songs")
async def add_song(song_data: dict):
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        from datetime import datetime, timezone
        existing = session.query(Song).filter_by(id=song_data.get("id")).first()
        if existing:
            raise HTTPException(status_code=400, detail="Song already exists")
        song = Song(
            id=song_data.get("id"), title=song_data.get("title"),
            artist=song_data.get("artist", []), album=song_data.get("album", "Unknown Album"),
            genre=song_data.get("genre", []), release_year=song_data.get("release_year"),
            duration=song_data.get("duration", 180), features=song_data.get("features", {}),
            audio_path=song_data.get("audio_path", ""),
            energy=song_data.get("energy"), warmth=song_data.get("warmth"), density=song_data.get("density"))
        if any(v is not None for v in (song.energy, song.warmth, song.density)):
            song.energy_updated_at = datetime.now(timezone.utc)
        session.add(song)
        session.commit()
        return {"message": "Song added successfully", "song_id": song.id}
    except HTTPException: raise
    except Exception as e:
        session.rollback()
        print(f"Error adding song: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.delete("/api/songs/{song_id}")
async def delete_song(song_id: str):
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        song = session.query(Song).filter_by(id=song_id).first()
        if not song: raise HTTPException(status_code=404, detail="Song not found")
        session.delete(song)
        session.commit()
        return {"message": "Song deleted successfully"}
    except HTTPException: raise
    except Exception as e:
        session.rollback()
        print(f"Error deleting song: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.put("/api/songs/{song_id}/energy")
async def update_song_energy(song_id: str, body: EnergyUpdateRequest):
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        from datetime import datetime, timezone
        song = session.query(Song).filter_by(id=song_id).first()
        if not song: raise HTTPException(status_code=404, detail="Song not found")
        if body.energy is not None: song.energy = body.energy
        if body.warmth is not None: song.warmth = body.warmth
        if body.density is not None: song.density = body.density
        song.energy_updated_at = datetime.now(timezone.utc)
        session.commit(); session.refresh(song)
        return {"message": "Energy values updated", "song": {
            "id": song.id, "title": song.title,
            "energy": song.energy, "warmth": song.warmth, "density": song.density,
            "energy_updated_at": song.energy_updated_at.isoformat() if song.energy_updated_at else None}}
    except HTTPException: raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

# ═══════════════════════════════════════════════════════════════
# Routes — Spotify
# ═══════════════════════════════════════════════════════════════

@app.get("/api/spotify/search")
async def search_spotify_tracks(query: str = Query(...), limit: int = Query(10, ge=1, le=50)):
    try:
        tracks = spotify_integration.search_tracks(query, limit)
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spotify/recommendations")
async def get_spotify_recommendations(request: SpotifyRecommendationRequest):
    try:
        tracks = spotify_integration.get_recommendations(
            seed_tracks=request.seed_tracks, seed_artists=request.seed_artists,
            seed_genres=request.seed_genres, limit=request.limit,
            min_acousticness=request.min_acousticness, max_acousticness=request.max_acousticness,
            min_danceability=request.min_danceability, max_danceability=request.max_danceability,
            min_energy=request.min_energy, max_energy=request.max_energy,
            min_instrumentalness=request.min_instrumentalness, max_instrumentalness=request.max_instrumentalness,
            min_liveness=request.min_liveness, max_liveness=request.max_liveness,
            min_loudness=request.min_loudness, max_loudness=request.max_loudness,
            min_speechiness=request.min_speechiness, max_speechiness=request.max_speechiness,
            min_tempo=request.min_tempo, max_tempo=request.max_tempo,
            min_valence=request.min_valence, max_valence=request.max_valence,
            min_popularity=request.min_popularity, max_popularity=request.max_popularity)
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spotify/track/{track_id}")
async def get_spotify_track_details(track_id: str):
    try:
        track = spotify_integration.get_track_details(track_id)
        if not track: raise HTTPException(status_code=404, detail="Track not found")
        return track
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spotify/artists")
async def search_spotify_artists(query: str = Query(...), limit: int = Query(10, ge=1, le=50)):
    try:
        artists = spotify_integration.search_artists(query, limit)
        return {"artists": artists, "total": len(artists)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spotify/add-to-library")
async def add_spotify_to_library(request: SpotifyAddRequest):
    try:
        result = spotify_integration.add_to_library(request.track_id)
        if result: return {"message": "Track added to library successfully", "track": result}
        raise HTTPException(status_code=400, detail="Failed to add track")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/spotify/import")
async def import_spotify_track(request: SpotifyAddRequest):
    try:
        track = spotify_integration.import_track(request.track_id)
        if track: return {"message": "Track imported successfully", "track": track}
        raise HTTPException(status_code=400, detail="Failed to import track")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# Routes — NetEase
# ═══════════════════════════════════════════════════════════════

@app.get("/api/netease/search")
async def search_netease_tracks(query: str = Query(...), limit: int = Query(10, ge=1, le=50)):
    try:
        tracks = netease_integration.search_tracks(query, limit)
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e: return {"error": str(e)}

@app.get("/api/netease/track/{track_id}")
async def get_netease_track(track_id: str):
    try:
        track = netease_integration.get_track_details(track_id)
        if not track: raise HTTPException(status_code=404, detail="Track not found")
        return track
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/netease/track/{track_id}/url")
async def get_netease_track_url(track_id: str):
    try:
        url = netease_integration.get_track_url(track_id)
        if url: return {"url": url}
        raise HTTPException(status_code=404, detail="Track URL not found")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/netease/track/{track_id}/details", response_class=Response)
async def get_netease_track_details(track_id: str):
    try:
        details = netease_integration.get_full_track_details(track_id)
        return Response(content=json.dumps({"details": details}, ensure_ascii=False), media_type="application/json")
    except Exception as e: return {"error": str(e)}

@app.get("/api/netease/top")
async def get_netease_top_songs(limit: int = 20):
    try:
        songs = netease_integration.get_top_songs(limit)
        return {"songs": songs, "total": len(songs)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/netease/new")
async def get_netease_new_songs(limit: int = 20):
    try:
        songs = netease_integration.get_new_songs(limit)
        return {"songs": songs, "total": len(songs)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/netease/add-to-library")
async def add_netease_to_library(request: NeteaseAddRequest):
    try:
        result = netease_integration.add_to_library(request.model_dump())
        if result: return {"message": "Track added to library successfully", "track": result}
        raise HTTPException(status_code=400, detail="Failed to add track")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/netease/import")
async def import_netease_track(request: NeteaseImportRequest):
    try:
        result = netease_integration.search_and_import_tracks(request.query, request.limit)
        tracks = result.get("tracks", [])
        session = recommendation_engine.Session()
        try:
            import_result = netease_integration.import_tracks_to_database(tracks, session)
            return {"message": "Tracks imported successfully", "tracks_found": len(tracks),
                    "imported": import_result.get("imported", 0),
                    "duplicates": import_result.get("duplicates", 0),
                    "failed": import_result.get("failed", 0)}
        finally:
            session.close()
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# Routes — Library stats
# ═══════════════════════════════════════════════════════════════

@app.get("/api/library/stats")
async def get_library_stats():
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        from sqlalchemy import func
        total_songs = session.query(Song).count()
        def _stats(attr):
            vals = [r[0] for r in session.query(attr).filter(attr.isnot(None)).all() if r[0] is not None]
            if not vals: return {"average": None, "min": None, "max": None, "distribution": {}}
            buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
            for v in vals:
                if v < 0.2: buckets["0.0-0.2"] += 1
                elif v < 0.4: buckets["0.2-0.4"] += 1
                elif v < 0.6: buckets["0.4-0.6"] += 1
                elif v < 0.8: buckets["0.6-0.8"] += 1
                else: buckets["0.8-1.0"] += 1
            return {"average": round(sum(vals)/len(vals), 4), "min": round(min(vals), 4),
                    "max": round(max(vals), 4), "distribution": buckets}
        analyzed = session.query(Song).filter(Song.energy.isnot(None)).count()
        return {"total_songs": total_songs, "analyzed_count": analyzed,
                "pending_analysis_count": total_songs - analyzed,
                "energy_stats": _stats(Song.energy), "warmth_stats": _stats(Song.warmth),
                "density_stats": _stats(Song.density)}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

# ═══════════════════════════════════════════════════════════════
# Routes — TTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/tts/speak", response_class=Response)
async def text_to_speech(request: TTSRequest):
    try:
        audio_data = elevenlabs_integration.text_to_speech(
            text=request.text, voice_id=request.voice_id, model_id=request.model_id)
        if audio_data: return Response(content=audio_data, media_type="audio/mpeg")
        raise HTTPException(status_code=500, detail="Failed to generate speech")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tts/voices")
async def get_tts_voices():
    try:
        voices = elevenlabs_integration.list_voices()
        if voices: return voices
        raise HTTPException(status_code=500, detail="Failed to get voices")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tts/voice/{voice_id}")
async def get_tts_voice_info(voice_id: str):
    try:
        voice_info = elevenlabs_integration.get_voice_info(voice_id)
        if voice_info: return voice_info
        raise HTTPException(status_code=404, detail="Voice not found")
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════
# Routes — Playlist / Memory Corridor
# ═══════════════════════════════════════════════════════════════

def _playlist_to_dict(pl) -> dict:
    return {"id": pl.id, "name": pl.name, "description": pl.description,
            "created_at": pl.created_at.isoformat() if pl.created_at else None,
            "updated_at": pl.updated_at.isoformat() if pl.updated_at else None,
            "context": pl.context or {}, "song_count": len(pl.playlist_songs) if pl.playlist_songs else 0}

def _ewd_distance(a, b) -> float:
    import math
    de = (a.get("energy") or 0.5) - (b.get("energy") or 0.5)
    dw = (a.get("warmth") or 0.5) - (b.get("warmth") or 0.5)
    dd = (a.get("density") or 0.5) - (b.get("density") or 0.5)
    return math.sqrt(de*de + dw*dw + dd*dd) / math.sqrt(3)

SCENE_NAMES = {(5,8):"清晨微光",(8,12):"正午底色",(12,18):"午后暖流",(18,21):"黄昏余音",(21,24):"深夜暗流",(0,5):"凌晨寂静"}

def _get_scene_for_hour(hour: int) -> tuple:
    for (h_start, h_end), name in SCENE_NAMES.items():
        if h_start <= hour < h_end:
            from core.audio_analyzer import get_time_offset
            return name, get_time_offset(hour)
    return "正午底色", {"energy_offset":0,"warmth_offset":0,"density_offset":0}

@app.post("/api/playlists")
async def create_playlist(body: PlaylistCreateRequest):
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        import uuid
        from datetime import datetime, timezone
        pl_id = str(uuid.uuid4())[:8]
        ctx = body.context or {}
        ctx["type"] = body.playlist_type
        if body.seed_songs:
            ctx["seed_song_ids"] = [s["id"] for s in body.seed_songs]
            energies = [s.get("energy",0.5) for s in body.seed_songs if s.get("energy") is not None]
            if energies:
                ctx["energy_center"] = round(sum(energies)/len(energies), 4)
                ctx["warmth_center"] = round(sum([s.get("warmth",0.5) for s in body.seed_songs if s.get("warmth") is not None])/max(1,len([s for s in body.seed_songs if s.get("warmth") is not None])), 4)
                ctx["density_center"] = round(sum([s.get("density",0.5) for s in body.seed_songs if s.get("density") is not None])/max(1,len([s for s in body.seed_songs if s.get("density") is not None])), 4)
        playlist = Playlist(id=pl_id, name=body.name, description=body.description,
                            created_at=datetime.now(timezone.utc), context=ctx)
        session.add(playlist)
        if body.seed_songs:
            for i, s in enumerate(body.seed_songs):
                session.add(PlaylistSong(playlist_id=pl_id, song_id=s["id"], position=i))
        session.commit()
        return {"message":"Playlist created","playlist":_playlist_to_dict(playlist)}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.get("/api/playlists")
async def get_all_playlists():
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        playlists = session.query(Playlist).order_by(Playlist.updated_at.desc()).all()
        result = []
        for pl in playlists:
            d = _playlist_to_dict(pl)
            pss = session.query(PlaylistSong).filter_by(playlist_id=pl.id).order_by(PlaylistSong.position).limit(5).all()
            dots = []
            for ps in pss:
                song = session.query(Song).filter_by(id=ps.song_id).first()
                if song and song.energy is not None:
                    dots.append({"song_id":song.id,"title":song.title,"energy":song.energy,"warmth":song.warmth,"density":song.density})
            d["color_dots"] = dots
            result.append(d)
        return {"playlists": result}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.get("/api/playlists/scenes")
async def get_scene_playlists():
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        from datetime import datetime, timezone
        import uuid, math
        hour = datetime.now().hour
        scene_name, offsets = _get_scene_for_hour(hour)
        e_off, w_off, d_off = offsets.get("energy_offset",0), offsets.get("warmth_offset",0), offsets.get("density_offset",0)

        # ── Weather adjustment ──
        try:
            weather = scene_engine.get_weather_context(24.9175, 118.6465) or {}
            cond = (weather.get("condition") or "").lower()
            if "rain" in cond or "drizzle" in cond:
                e_off -= 0.1; w_off += 0.05  # rain: lower energy, cozy warmth
            elif "clear" in cond or "sun" in cond:
                e_off += 0.08  # sunny: more energetic
            wind = weather.get("wind_speed", 0) or 0
            if wind > 8:
                e_off -= 0.05; w_off += 0.05  # windy: seek stability
        except Exception:
            pass

        # ── L3 preference boosting ──
        liked_artists = set()
        disliked_artists = set()
        try:
            for name, entry in l3_profile.preferences.get("artists", {}).items():
                if entry.get("strength", 0) > 0.5: liked_artists.add(name.lower())
            for name in l3_profile.preferences.get("disliked_artists", {}):
                disliked_artists.add(name.lower())
        except Exception:
            pass

        all_songs = session.query(Song).filter(Song.energy.isnot(None), Song.warmth.isnot(None), Song.density.isnot(None)).all()
        matched = []
        for s in all_songs:
            # Filter disliked
            if any(a.lower() in disliked_artists for a in (s.artist or [])): continue
            eff_e = max(0,min(1,(s.energy or 0.5)+e_off))
            eff_w = max(0,min(1,(s.warmth or 0.5)+w_off))
            eff_d = max(0,min(1,(s.density or 0.5)+d_off))
            if 5<=hour<8: score = (1-abs(eff_e-0.45))+(1-abs(eff_w-0.6))+(1-abs(eff_d-0.4))
            elif 8<=hour<12: score = (1-abs(eff_e-0.5))+(1-abs(eff_w-0.5))+(1-abs(eff_d-0.5))
            elif 12<=hour<18: score = (1-abs(eff_e-0.55))+(1-abs(eff_w-0.6))+(1-abs(eff_d-0.5))
            elif 18<=hour<21: score = (1-abs(eff_e-0.4))+(1-abs(eff_w-0.55))+(1-abs(eff_d-0.45))
            elif 21<=hour<24: score = (1-abs(eff_e-0.35))+(1-abs(eff_w-0.45))+(1-abs(eff_d-0.45))
            else: score = (1-abs(eff_e-0.25))+(1-abs(eff_w-0.4))+(1-abs(eff_d-0.35))
            # L3 boost: preferred artists get +0.3
            if any(a.lower() in liked_artists for a in (s.artist or [])): score += 0.3
            if score>1.8: matched.append((score,s))
        matched.sort(key=lambda x:-x[0]); top = matched[:10]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = session.query(Playlist).filter_by(id="scene_auto").first()
        if not existing:
            playlist = Playlist(id="scene_auto", name=scene_name, description=f"Malio 自动生成 · {scene_name}",
                                created_at=datetime.now(timezone.utc), context={"type":"scene","scene":scene_name,"updated_date":today,"offsets":offsets})
            session.add(playlist)
            for i,(score,s) in enumerate(top): session.add(PlaylistSong(playlist_id="scene_auto",song_id=s.id,position=i))
            session.commit()
        else:
            if existing.context.get("updated_date") != today:
                existing.name = scene_name; existing.context["updated_date"] = today; existing.context["offsets"] = offsets
                session.query(PlaylistSong).filter_by(playlist_id="scene_auto").delete()
                for i,(score,s) in enumerate(top): session.add(PlaylistSong(playlist_id="scene_auto",song_id=s.id,position=i))
                existing.updated_at = datetime.now(timezone.utc); session.commit()
            playlist = existing
        pss = session.query(PlaylistSong).filter_by(playlist_id=playlist.id).order_by(PlaylistSong.position).all()
        songs_out = []
        for ps in pss:
            s = session.query(Song).filter_by(id=ps.song_id).first()
            if s: songs_out.append({"id":s.id,"title":s.title,"artist":s.artist,"energy":s.energy,"warmth":s.warmth,"density":s.density})
        return {"playlist_id":playlist.id,"name":playlist.name,"scene":scene_name,"hour":hour,"offsets":offsets,"songs":songs_out,"total":len(songs_out)}
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.get("/api/playlists/{playlist_id}")
async def get_playlist(playlist_id: str):
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl: raise HTTPException(status_code=404, detail="Playlist not found")
        pss = session.query(PlaylistSong).filter_by(playlist_id=playlist_id).order_by(PlaylistSong.position).all()
        songs = []
        for ps in pss:
            song = session.query(Song).filter_by(id=ps.song_id).first()
            if song: songs.append({"id":song.id,"title":song.title,"artist":song.artist,"album":song.album,"duration":song.duration,"energy":song.energy,"warmth":song.warmth,"density":song.density,"audio_path":song.audio_path,"position":ps.position})
        result = _playlist_to_dict(pl); result["songs"] = songs
        return result
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.put("/api/playlists/{playlist_id}")
async def update_playlist(playlist_id: str, body: PlaylistUpdateRequest):
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist
        from datetime import datetime, timezone
        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl: raise HTTPException(status_code=404, detail="Playlist not found")
        if body.name is not None: pl.name = body.name
        if body.description is not None: pl.description = body.description
        ctx = dict(pl.context or {})
        if body.tags is not None: ctx["tags"] = body.tags
        if body.context is not None: ctx.update(body.context)
        pl.context = ctx; pl.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"message":"Playlist updated","playlist":_playlist_to_dict(pl)}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong
        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl: raise HTTPException(status_code=404, detail="Playlist not found")
        session.query(PlaylistSong).filter_by(playlist_id=playlist_id).delete()
        session.delete(pl); session.commit()
        return {"message":"Playlist deleted"}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.post("/api/playlists/generate")
async def generate_playlist_from_capture(body: PlaylistGenerateRequest):
    session = recommendation_engine.Session()
    try:
        from models.music import Song, Playlist, PlaylistSong
        import uuid, math
        from datetime import datetime, timezone
        captured = body.captured_songs
        if not captured: raise HTTPException(status_code=400, detail="No captured songs provided")
        energies = [s.get("energy",0.5) for s in captured if s.get("energy") is not None] or [0.5]
        warmths = [s.get("warmth",0.5) for s in captured if s.get("warmth") is not None] or [0.5]
        densities = [s.get("density",0.5) for s in captured if s.get("density") is not None] or [0.5]
        centroid = {"energy":round(sum(energies)/len(energies),4),"warmth":round(sum(warmths)/len(warmths),4),"density":round(sum(densities)/len(densities),4)}
        all_songs = session.query(Song).filter(Song.energy.isnot(None),Song.warmth.isnot(None),Song.density.isnot(None)).all()
        scored = []
        for song in all_songs:
            dist = _ewd_distance({"energy":song.energy,"warmth":song.warmth,"density":song.density}, centroid)
            if dist<0.25: scored.append((dist,song))
        scored.sort(key=lambda x:x[0]); top_matches = scored[:20]
        seed_titles = [s.get("title","") for s in captured if s.get("title")]
        e_desc = "高能" if centroid["energy"]>0.65 else ("低能" if centroid["energy"]<0.35 else "中能")
        w_desc = "暖调" if centroid["warmth"]>0.6 else ("冷调" if centroid["warmth"]<0.4 else "中性")
        d_desc = "浓密" if centroid["density"]>0.7 else ("极简" if centroid["density"]<0.3 else "适密")
        try:
            song_context = [{"title":s.get("title",""),"artist":""} for s in captured[:3]]
            playlist_name = kimi_integration.generate_playlist_name(song_context, {"energy_desc":f"{e_desc}{w_desc}{d_desc}","seed":seed_titles})
        except Exception:
            playlist_name = f"{e_desc}{w_desc}{d_desc} · {seed_titles[0] if seed_titles else '未命名'}"
        pl_id = str(uuid.uuid4())[:8]
        ctx = {"type":"capture","energy_center":centroid["energy"],"warmth_center":centroid["warmth"],"density_center":centroid["density"],
               "seed_song_ids":[s.get("id") for s in captured],"captured_at":datetime.now(timezone.utc).isoformat()}
        if top_matches:
            ctx["energy_range"] = [round(min(s.energy for _,s in top_matches),4), round(max(s.energy for _,s in top_matches),4)]
            ctx["warmth_range"] = [round(min(s.warmth for _,s in top_matches),4), round(max(s.warmth for _,s in top_matches),4)]
            ctx["density_range"] = [round(min(s.density for _,s in top_matches),4), round(max(s.density for _,s in top_matches),4)]
        playlist = Playlist(id=pl_id, name=playlist_name, description=f"星云捕获 · {e_desc}{w_desc}{d_desc}",
                            created_at=datetime.now(timezone.utc), context=ctx)
        session.add(playlist)
        for i,(dist,song) in enumerate(top_matches): session.add(PlaylistSong(playlist_id=pl_id,song_id=song.id,position=i))
        session.commit()
        songs_out = [{"id":s.id,"title":s.title,"artist":s.artist,"energy":s.energy,"warmth":s.warmth,"density":s.density} for _,s in top_matches]
        return {"playlist_name":playlist_name,"playlist_id":pl_id,"centroid":centroid,"songs":songs_out,"total":len(songs_out)}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.post("/api/playlists/{playlist_id}/songs")
async def add_song_to_playlist(playlist_id: str, body: PlaylistSongRequest):
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        from datetime import datetime, timezone
        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl: raise HTTPException(status_code=404, detail="Playlist not found")
        song = session.query(Song).filter_by(id=body.song_id).first()
        if not song: raise HTTPException(status_code=404, detail="Song not found")
        existing = session.query(PlaylistSong).filter_by(playlist_id=playlist_id,song_id=body.song_id).first()
        if existing: return {"message":"Song already in playlist"}
        max_pos = session.query(PlaylistSong).filter_by(playlist_id=playlist_id).count()
        session.add(PlaylistSong(playlist_id=playlist_id,song_id=body.song_id,position=max_pos))
        pl.updated_at = datetime.now(timezone.utc); session.commit()
        return {"message":"Song added to playlist"}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

@app.delete("/api/playlists/{playlist_id}/songs/{song_id}")
async def remove_song_from_playlist(playlist_id: str, song_id: str):
    session = recommendation_engine.Session()
    try:
        from models.music import PlaylistSong
        ps = session.query(PlaylistSong).filter_by(playlist_id=playlist_id,song_id=song_id).first()
        if not ps: raise HTTPException(status_code=404, detail="Song not in playlist")
        session.delete(ps); session.commit()
        return {"message":"Song removed from playlist"}
    except HTTPException: raise
    except Exception as e: session.rollback(); raise HTTPException(status_code=500, detail=str(e))
    finally: session.close()

# ═══════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Malio Music Agent API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ═══════════════════════════════════════════════════════════════
# WebSocket — Real-time playback state
# ═══════════════════════════════════════════════════════════════
# Session resume
# ═══════════════════════════════════════════════════════════════

@app.get("/api/session/resume")
async def resume_session(user_id: str = "default"):
    """Return a summary of the last session for welcome-back display."""
    ps = get_playback(user_id)
    ch = get_chat_history(user_id)
    cur = ps.get("current", {})
    return {
        "has_session": bool(cur or ch),
        "current_song": cur.get("title"),
        "current_artist": ", ".join(cur.get("artist", [])),
        "chat_count": len(ch),
        "last_exchange": ch[-2]["content"][:100] if len(ch) >= 2 else "",
        "queue_size": len(ps.get("playlist", [])),
    }

# ═══════════════════════════════════════════════════════════════

@app.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    feedback_mgr.register(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                action = data.get("action", "")
                uid = data.get("user_id", "default")
                ps = get_playback(uid)
                ce = get_core_events(uid)
                ch = get_chat_history(uid)

                if action == "get_state":
                    await feedback_mgr.push_snapshot(
                        song=ps["current"] if ps["current"] else None,
                        is_playing=ps["is_playing"],
                        playlist=ps["playlist"])

                elif action == "sync_playlist":
                    songs = data.get("songs", [])
                    if songs:
                        set_playlist(enrich_songs(songs, recommendation_engine), user_id=uid)
                        await feedback_mgr.push_snapshot(
                            song=ps["current"], playlist=songs,
                            is_playing=ps["is_playing"])

                elif action == "heartbeat":
                    frontend_id = data.get("current_song_id", "")
                    backend_id = ps["current"].get("id", "")
                    if frontend_id and backend_id and frontend_id != backend_id:
                        # Only re-sync if same mismatch persists 2 beats (60s)
                        _hb_key = f"mismatch_{uid}"
                        _hb_last = getattr(websocket_stream, '_hb_tracker', {})
                        prev = _hb_last.get(_hb_key, "")
                        cur = f"{frontend_id}_{backend_id}"
                        if prev == cur:
                            print(f"[ws] mismatch confirmed {uid}, re-syncing")
                            # Only sync playlist + is_playing — don't force song change
                            await feedback_mgr.push_snapshot(
                                playlist=ps["playlist"],
                                is_playing=ps["is_playing"])
                            _hb_last.pop(_hb_key, None)
                        else:
                            _hb_last[_hb_key] = cur
                            print(f"[ws] mismatch pending {uid} frontend={frontend_id} backend={backend_id}")
                        websocket_stream._hb_tracker = _hb_last

                elif action == "core_event":
                    evt = data.get("event", {})
                    evt["received_at"] = dt.datetime.now().isoformat()
                    ce.append(evt)
                    state_store.mark_dirty(uid)
                    evt_type = evt.get("type", "")

                    if evt_type in ("play", "pause", "volume_change"):
                        l2_memory.record(evt_type, evt.get("detail", {}))
                    else:
                        l2_memory.record(f"core_{evt_type}", evt.get("detail", {}))
                    l4_history.record(f"core_{evt.get('type','')}", evt.get("detail", {}))

                    ws_label = {"song_skip":"切歌","time_warp":"暂停粒子","search":"搜索","spin":"调音量",
                                "core_drag":"拖拽内核","nebula_capture":"捕获歌曲"}.get(evt_type, evt_type)

                    if evt_type == "song_skip":
                        skipped = ps["current"]
                        detail = evt.get("detail", {})
                        is_broken = detail.get("reason") == "broken_url"
                        is_ended = detail.get("source") == "ended"  # natural song end, not user skip

                        if skipped and skipped.get("title") and not is_ended:
                            weaken_amt = 0.05 if is_broken else 0.03
                            slabel = "URL失效" if is_broken else "切歌"
                            for artist in (skipped.get("artist") or []):
                                l3_profile.weaken("artists", artist, f"{slabel}:{skipped.get('title','')}")
                                if is_broken:
                                    l3_profile.add_explicit_rule(f"避免推荐: {artist}")
                            for genre in (skipped.get("genre") or []):
                                l3_profile.weaken("genres", genre, f"{slabel}:{skipped.get('title','')}")
                            if not is_broken:
                                add_fast_skip(uid)
                            if count_recent_fast_skips(30, uid) >= 2:
                                await feedback_mgr.push_agent_log("用户连续快速切歌，当前推荐方向可能需要调整")
                                clear_fast_skips(uid)
                        elif is_ended:
                            # Natural song end — just advance, no preference change
                            pass

                        if not ps["playlist"]:
                            db_songs = query_local_songs(50, recommendation_engine)
                            if db_songs:
                                set_playlist(db_songs, user_id=uid)
                        next_song = next_in_queue(uid)
                        if next_song:
                            await feedback_mgr.push_snapshot(
                                song=next_song, playlist=ps["playlist"], is_playing=True)
                        else:
                            await feedback_mgr.push_snapshot(playlist=ps["playlist"])

                    persona_engine.drift_from_interaction(evt_type, evt.get("detail", {}))
                    await feedback_mgr.push_agent_log(f"感知到用户交互: {ws_label}")

            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        feedback_mgr.unregister(websocket)

# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
