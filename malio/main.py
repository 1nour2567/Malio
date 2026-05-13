from fastapi import FastAPI, HTTPException, Depends, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional
import json
import asyncio
from dotenv import load_dotenv
from core.scene_aware_engine import SceneAwareEngine
from core.recommendation_engine import RecommendationEngine
from core.device_control import DeviceControl
from integrations.kimi_integration import KimiIntegration
from integrations.spotify_integration import SpotifyIntegration
from integrations.netease_integration import NeteaseIntegration
from integrations.elevenlabs_integration import ElevenLabsIntegration
from data.data_importer import MusicDataImporter
from config.config import settings
from agent.perception import Perception
from agent.router import Router
from agent.reasoner import Reasoner
from agent.providers import create_providers_from_config
from agent.tools import ToolRegistry
from agent.feedback import Feedback

# Load .env file
load_dotenv()

app = FastAPI(
    title="Malio Music Agent API",
    description="AI music agent that provides personalized music recommendations",
    version="0.2.0"
)

# CORS middleware
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for audio
import os

audio_dir = os.path.join(os.path.dirname(__file__), "data", "audio")
if not os.path.exists(audio_dir):
    os.makedirs(audio_dir)

songs_dir = os.path.join(audio_dir, "songs")
if not os.path.exists(songs_dir):
    os.makedirs(songs_dir)

app.mount("/audio", StaticFiles(directory=audio_dir), name="audio")

# Initialize engines
scene_engine = SceneAwareEngine()
recommendation_engine = RecommendationEngine()
kimi_integration = KimiIntegration()
device_control = DeviceControl()
spotify_integration = SpotifyIntegration()
netease_integration = NeteaseIntegration()
elevenlabs_integration = ElevenLabsIntegration()

# Initialize agent components
provider_registry = create_providers_from_config(settings)
perception = Perception()
router = Router()
reasoner = Reasoner(provider_registry)
tool_registry = ToolRegistry()
feedback_mgr = Feedback()

# Register tools
tool_registry.register("search_music", "搜索歌曲", {"query": "string", "limit": "int"},
    lambda query, limit=5, **kw: netease_integration.search_tracks(query, limit))
tool_registry.register("get_weather", "获取天气", {"city": "string"},
    lambda city="", **kw: scene_engine.get_weather_context(24.9175, 118.6465) or {})


# Data models
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


class MusicResponse(BaseModel):
    response: str
    recommendations: List[Dict[str, Any]] = []


class EnergyUpdateRequest(BaseModel):
    """Manual E/W/D fine-tuning request (Layer 2). At least one field required."""
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
    playlist_type: str = "manual"  # "capture" | "manual" | "scene" | "tag"
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
    captured_songs: List[Dict[str, Any]]  # [{id, title, energy, warmth, density}]
    hour: Optional[int] = None


# API endpoints
@app.post("/api/recommend", response_model=MusicResponse)
async def get_recommendations(request: RecommendationRequest):
    """Get music recommendations"""
    try:
        # Get recommendations (this will also initialize database and import sample data if needed)
        if request.context:
            recommendations = recommendation_engine.get_recommendations(
                request.user_id, request.context, request.limit
            )
        else:
            recommendations = recommendation_engine.get_contextual_recommendations(
                request.user_id, request.limit
            )

        # Get current context if not provided
        context = request.context or scene_engine.get_full_context(request.user_id)

        # Generate natural language response
        response = kimi_integration.generate_music_recommendation(
            "Recommend me some music",
            context,
            recommendations
        )

        return MusicResponse(
            response=response,
            recommendations=recommendations
        )
    except Exception as e:
        print(f"Error in /api/recommend: {e}")
        # Return a friendly error message instead of a 500 error
        return MusicResponse(
            response="抱歉，我遇到了一些问题。请检查服务器日志以了解详细信息。",
            recommendations=[]
        )


@app.post("/api/chat", response_model=MusicResponse)
async def chat_with_malio(request: UserInput):
    """Chat with Malio about music — 5-stage agent pipeline"""
    try:
        # Stage 1: Perception — build context from user input + environment
        print("[chat] Stage 1: Perception...")
        perception_ctx = perception.build(request.input, request.user_id)
        if request.context:
            perception_ctx["context"] = request.context

        # Stage 2: Router — direct command or reasoning path
        print("[chat] Stage 2: Router...")
        route_result = router.route(request.input)
        agent_log = ""

        if route_result["routed_to"] == "direct":
            # Direct command execution
            cmd = route_result["command"]
            print(f"[chat] Direct command: {cmd}")
            agent_log = f"Executing command: {cmd}"

            if cmd == "volume":
                value = route_result["params"].get("value", "50")
                volume = int(value) if value.isdigit() else 50
                device_control.set_volume(volume)
                response = f"音量已设置为 {volume}"
            elif cmd == "play":
                device_control.play("")
                response = "正在播放音乐"
            elif cmd == "pause":
                device_control.pause()
                response = "音乐已暂停"
            elif cmd == "stop":
                device_control.stop()
                response = "音乐已停止"
            elif cmd == "next":
                device_control.next_track() if hasattr(device_control, "next_track") else None
                response = "已切换到下一首"
            elif cmd == "previous":
                device_control.previous_track() if hasattr(device_control, "previous_track") else None
                response = "已切换到上一首"
            else:
                response = f"未知命令: {cmd}"

            # Push feedback snapshot
            await feedback_mgr.push_snapshot(agent_log=agent_log, song=None, playlist=None)
            return MusicResponse(response=response, recommendations=[])

        # Stage 3: Reasoner — LLM reasoning
        print("[chat] Stage 3: Reasoner...")
        reasoner_result = reasoner.reason(request.input, perception_ctx)
        agent_log = reasoner_result.get("reasoning", "")
        response_text = reasoner_result.get("response", "好的，让我为您推荐一些音乐。")

        # Stage 4: Tools — execute any actions from the reasoner
        print("[chat] Stage 4: Tools...")
        recommendations = []
        actions = reasoner_result.get("actions", [])
        for action in actions:
            if isinstance(action, dict):
                tool_name = action.get("tool", "")
                tool_params = action.get("params", {})
                tool_result = tool_registry.execute(tool_name, tool_params)
                if "error" not in tool_result:
                    recommendations = tool_result.get("tracks", []) or tool_result.get("songs", []) or []
                    agent_log += f"\nExecuted tool: {tool_name}"

        # Fallback: get recommendations if no tools produced them
        if not recommendations:
            show_context = perception_ctx.get("context") or scene_engine.get_full_context(request.user_id)
            if reasoner_result.get("intent") in ("music_recommendation", "mood_change", "unknown"):
                recommendations = recommendation_engine.get_contextual_recommendations(
                    request.user_id, 5
                )

        # Stage 5: Feedback — push state snapshot
        print("[chat] Stage 5: Feedback...")
        await feedback_mgr.push_snapshot(
            agent_log=agent_log,
            song=recommendations[0] if recommendations else None,
            playlist=recommendations,
            tool_error=reasoner_result.get("error"),
        )

        return MusicResponse(response=response_text, recommendations=recommendations)

    except Exception as e:
        import traceback
        print(f"[chat] ERROR: {e}")
        print(f"[chat] Full traceback:\n{traceback.format_exc()}")
        return MusicResponse(
            response=f"抱歉，我遇到了一些问题。请检查服务器日志以了解详细信息。\n错误类型：{type(e).__name__}",
            recommendations=[]
        )


def _generate_smart_chat_response(user_message: str, context: Dict, recommendations: List) -> str:
    """Generate smart chat responses without API key"""
    time_of_day = context.get('time', {}).get('time_of_day', 'day')

    # Common user intents
    greetings = ['你好', '您好', '嗨', 'hi', 'hello', '早上好', '下午好', '晚上好']
    music_requests = ['音乐', '歌', '听', '推荐', '播放', '唱']
    mood_requests = ['开心', '难过', '快乐', '悲伤', '忧郁', '兴奋', '安静']
    thanks = ['谢谢', '感谢', '谢了']
    goodbye = ['再见', '拜拜', '走了', '离开']

    user_lower = user_message.lower()

    # Check for common intents
    if any(greet in user_lower for greet in greetings):
        time_greeting = {
            'morning': '早上好',
            'afternoon': '下午好',
            'evening': '晚上好',
            'night': '晚上好'
        }.get(time_of_day, '你好')
        return f"{time_greeting}！我是 Malio，您的音乐智能助手！我为您准备了一些推荐歌曲，您可以点击上一首/下一首按钮来切换。您想听什么类型的音乐呢？"

    elif any(request in user_lower for request in music_requests):
        return f"好的！我为您准备了{len(recommendations)}首推荐歌曲！您可以点击推荐列表中的任意歌曲开始播放，或者用控制按钮切换。有什么特别想听的风格或歌手吗？"

    elif any(mood in user_lower for mood in mood_requests):
        if any(word in user_lower for word in ['难过', '悲伤', '忧郁', '不开心']):
            return "我理解您的心情。听一些温暖治愈的音乐会有帮助！我为您准备了一些舒缓的音乐，希望能让您感觉好一点。"
        elif any(word in user_lower for word in ['开心', '快乐', '兴奋']):
            return "太棒了！在这么好的心情下，听一些欢快的音乐会更棒！我为您准备了一些有活力的歌曲！"
        return "我明白您的心情！让我们用合适的音乐来配合您的心情吧。"

    elif any(thank in user_lower for thank in thanks):
        return "不客气！能为您服务是我的荣幸！如果有其他想听的音乐，随时告诉我！"

    elif any(bye in user_lower for bye in goodbye):
        return "再见！希望您享受今天的音乐。下次想听音乐时，随时找我！"

    else:
        return f"我收到您的消息了！我已经为您准备了{len(recommendations)}首推荐歌曲，您可以点击上一首/下一首按钮来切换，或者点击推荐列表中的任意歌曲开始播放！有什么特别想听的音乐吗？"


@app.post("/api/generate-playlist-name")
async def generate_playlist_name(request: PlaylistRequest):
    """Generate a playlist name"""
    try:
        # Get current context if not provided
        context = request.context or scene_engine.get_full_context(request.user_id)

        # Generate playlist name
        playlist_name = kimi_integration.generate_playlist_name(
            request.songs,
            context
        )

        return {"playlist_name": playlist_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/context")
async def get_current_context(user_id: str = "default"):
    """Get current scene context"""
    try:
        context = scene_engine.get_full_context(user_id)
        return context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/import-data")
async def import_music_data():
    """Import music data"""
    try:
        importer = MusicDataImporter()
        importer.import_data(settings.music_data_path)
        return {"message": "Data import completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Device control endpoints
@app.get("/api/devices")
async def get_devices():
    """Get list of available devices"""
    try:
        devices = device_control.discover_devices()
        return {"devices": devices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/connect")
async def connect_device(device_id: str):
    """Connect to a device"""
    try:
        success = device_control.connect_device(device_id)
        if success:
            return {"message": "Device connected successfully"}
        else:
            raise HTTPException(status_code=404, detail="Device not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/disconnect")
async def disconnect_device():
    """Disconnect from current device"""
    try:
        success = device_control.disconnect_device()
        if success:
            return {"message": "Device disconnected successfully"}
        else:
            return {"message": "No device connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/play")
async def play_music(song_uri: str):
    """Play music on connected device"""
    try:
        success = device_control.play(song_uri)
        if success:
            return {"message": "Music playing"}
        else:
            raise HTTPException(status_code=400, detail="Failed to play music")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/pause")
async def pause_music():
    """Pause music on connected device"""
    try:
        success = device_control.pause()
        if success:
            return {"message": "Music paused"}
        else:
            raise HTTPException(status_code=400, detail="Failed to pause music")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/stop")
async def stop_music():
    """Stop music on connected device"""
    try:
        success = device_control.stop()
        if success:
            return {"message": "Music stopped"}
        else:
            raise HTTPException(status_code=400, detail="Failed to stop music")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/devices/volume")
async def set_volume(volume: int):
    """Set volume on connected device"""
    try:
        success = device_control.set_volume(volume)
        if success:
            return {"message": f"Volume set to {volume}"}
        else:
            raise HTTPException(status_code=400, detail="Failed to set volume")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices/status")
async def get_device_status():
    """Get device status"""
    try:
        status = device_control.get_device_status()
        if status:
            return status
        else:
            return {"message": "No device connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Health check
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Malio Music Agent API is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Song Management APIs
@app.get("/api/songs")
async def get_all_songs():
    """Get all songs in the database"""
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        songs = session.query(Song).all()

        return {
            "songs": [
                {
                    "id": song.id,
                    "title": song.title,
                    "artist": song.artist,
                    "album": song.album,
                    "genre": song.genre,
                    "release_year": song.release_year,
                    "duration": song.duration or 180,
                    "audio_path": song.audio_path or "",
                    "preview_url": (song.features or {}).get("preview_url", ""),
                    "album_art": (song.features or {}).get("album_art", ""),
                    "external_url": (song.features or {}).get("external_url", ""),
                    "energy": song.energy,
                    "warmth": song.warmth,
                    "density": song.density,
                    "energy_updated_at": song.energy_updated_at.isoformat() if song.energy_updated_at else None
                }
                for song in songs
            ],
            "total": len(songs)
        }
    except Exception as e:
        print(f"Error getting songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/songs")
async def add_song(song_data: dict):
    """Add a new song"""
    session = recommendation_engine.Session()
    try:
        from models.music import Song

        # Check if song already exists
        existing_song = session.query(Song).filter_by(id=song_data.get("id")).first()
        if existing_song:
            raise HTTPException(status_code=400, detail="Song already exists")

        song = Song(
            id=song_data.get("id"),
            title=song_data.get("title"),
            artist=song_data.get("artist", []),
            album=song_data.get("album", "Unknown Album"),
            genre=song_data.get("genre", []),
            release_year=song_data.get("release_year"),
            duration=song_data.get("duration", 180),
            features=song_data.get("features", {}),
            audio_path=song_data.get("audio_path", ""),
            energy=song_data.get("energy"),
            warmth=song_data.get("warmth"),
            density=song_data.get("density"),
        )
        if any(v is not None for v in (song.energy, song.warmth, song.density)):
            from datetime import datetime, timezone
            song.energy_updated_at = datetime.now(timezone.utc)

        session.add(song)
        session.commit()

        return {"message": "Song added successfully", "song_id": song.id}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error adding song: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/api/songs/{song_id}")
async def delete_song(song_id: str):
    """Delete a song"""
    session = recommendation_engine.Session()
    try:
        from models.music import Song

        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            raise HTTPException(status_code=404, detail="Song not found")

        session.delete(song)
        session.commit()

        return {"message": "Song deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error deleting song: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.put("/api/songs/{song_id}/energy")
async def update_song_energy(song_id: str, body: EnergyUpdateRequest):
    """Manual E/W/D fine-tuning (Layer 2). Partial update — only provided fields modified."""
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        from datetime import datetime, timezone

        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            raise HTTPException(status_code=404, detail="Song not found")

        if body.energy is not None:
            song.energy = body.energy
        if body.warmth is not None:
            song.warmth = body.warmth
        if body.density is not None:
            song.density = body.density

        song.energy_updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(song)

        return {
            "message": "Energy values updated",
            "song": {
                "id": song.id,
                "title": song.title,
                "energy": song.energy,
                "warmth": song.warmth,
                "density": song.density,
                "energy_updated_at": song.energy_updated_at.isoformat() if song.energy_updated_at else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error updating song energy: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# Spotify API endpoints
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
    target_acousticness: Optional[float] = None
    min_danceability: Optional[float] = None
    max_danceability: Optional[float] = None
    target_danceability: Optional[float] = None
    min_energy: Optional[float] = None
    max_energy: Optional[float] = None
    target_energy: Optional[float] = None
    min_instrumentalness: Optional[float] = None
    max_instrumentalness: Optional[float] = None
    target_instrumentalness: Optional[float] = None
    min_liveness: Optional[float] = None
    max_liveness: Optional[float] = None
    target_liveness: Optional[float] = None
    min_loudness: Optional[float] = None
    max_loudness: Optional[float] = None
    target_loudness: Optional[float] = None
    min_speechiness: Optional[float] = None
    max_speechiness: Optional[float] = None
    target_speechiness: Optional[float] = None
    min_tempo: Optional[float] = None
    max_tempo: Optional[float] = None
    target_tempo: Optional[float] = None
    min_valence: Optional[float] = None
    max_valence: Optional[float] = None
    target_valence: Optional[float] = None
    min_popularity: Optional[int] = None
    max_popularity: Optional[int] = None
    target_popularity: Optional[int] = None


@app.get("/api/spotify/search")
async def search_spotify_tracks(
        query: str = Query(..., description="Search query"),
        limit: int = Query(10, description="Number of results to return", ge=1, le=50)
):
    """Search for tracks on Spotify"""
    try:
        tracks = spotify_integration.search_tracks(query, limit)
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e:
        print(f"Error searching Spotify tracks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spotify/recommendations")
async def get_spotify_recommendations(request: SpotifyRecommendationRequest):
    """Get music recommendations from Spotify"""
    try:
        tracks = spotify_integration.get_recommendations(
            seed_tracks=request.seed_tracks,
            seed_artists=request.seed_artists,
            seed_genres=request.seed_genres,
            limit=request.limit,
            min_acousticness=request.min_acousticness,
            max_acousticness=request.max_acousticness,
            target_acousticness=request.target_acousticness,
            min_danceability=request.min_danceability,
            max_danceability=request.max_danceability,
            target_danceability=request.target_danceability,
            min_energy=request.min_energy,
            max_energy=request.max_energy,
            target_energy=request.target_energy,
            min_instrumentalness=request.min_instrumentalness,
            max_instrumentalness=request.max_instrumentalness,
            target_instrumentalness=request.target_instrumentalness,
            min_liveness=request.min_liveness,
            max_liveness=request.max_liveness,
            target_liveness=request.target_liveness,
            min_loudness=request.min_loudness,
            max_loudness=request.max_loudness,
            target_loudness=request.target_loudness,
            min_speechiness=request.min_speechiness,
            max_speechiness=request.max_speechiness,
            target_speechiness=request.target_speechiness,
            min_tempo=request.min_tempo,
            max_tempo=request.max_tempo,
            target_tempo=request.target_tempo,
            min_valence=request.min_valence,
            max_valence=request.max_valence,
            target_valence=request.target_valence,
            min_popularity=request.min_popularity,
            max_popularity=request.max_popularity,
            target_popularity=request.target_popularity
        )
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e:
        print(f"Error getting Spotify recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spotify/track/{track_id}")
async def get_spotify_track_details(track_id: str):
    """Get track details from Spotify"""
    try:
        track = spotify_integration.get_track_details(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        return track
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting Spotify track details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/spotify/artists")
async def search_spotify_artists(
        query: str = Query(..., description="Artist search query"),
        limit: int = Query(10, description="Number of results to return", ge=1, le=50)
):
    """Search for artists on Spotify"""
    try:
        artists = spotify_integration.search_artists(query, limit)
        return {"artists": artists, "total": len(artists)}
    except Exception as e:
        print(f"Error searching Spotify artists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SpotifyAddRequest(BaseModel):
    track_id: str

@app.post("/api/spotify/add-to-library")
async def add_spotify_to_library(request: SpotifyAddRequest):
    """Add Spotify track to local library"""
    try:
        result = spotify_integration.add_to_library(request.track_id)
        if result:
            return {"message": "Track added to library successfully", "track": result}
        else:
            raise HTTPException(status_code=400, detail="Failed to add track")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding Spotify track to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/spotify/import")
async def import_spotify_track(request: SpotifyAddRequest):
    """Import Spotify track details to database"""
    try:
        track = spotify_integration.import_track(request.track_id)
        if track:
            return {"message": "Track imported successfully", "track": track}
        else:
            raise HTTPException(status_code=400, detail="Failed to import track")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error importing Spotify track: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# NetEase Cloud Music API endpoints
@app.get("/api/netease/search")
async def search_netease_tracks(
        query: str = Query(..., description="Search query"),
        limit: int = Query(10, description="Number of results to return", ge=1, le=50)
):
    """Search for tracks on NetEase Cloud Music"""
    try:
        tracks = netease_integration.search_tracks(query, limit)
        return {"tracks": tracks, "total": len(tracks)}
    except Exception as e:
        print(f"Error searching NetEase tracks: {e}")
        return {"error": str(e)}


@app.get("/api/netease/track/{track_id}")
async def get_netease_track(track_id: str):
    """Get track details from NetEase"""
    try:
        track = netease_integration.get_track_details(track_id)
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        return track
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting NetEase track: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/netease/track/{track_id}/url")
async def get_netease_track_url(track_id: str):
    """Get playable URL for a NetEase track"""
    try:
        url = netease_integration.get_track_url(track_id)
        if url:
            return {"url": url}
        else:
            raise HTTPException(status_code=404, detail="Track URL not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting NetEase track URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/netease/track/{track_id}/details", response_class=Response)
async def get_netease_track_details(track_id: str):
    """Get complete track details from NetEase"""
    try:
        details = netease_integration.get_full_track_details(track_id)
        result = {"details": details}
        return Response(content=json.dumps(result, ensure_ascii=False), media_type="application/json")
    except Exception as e:
        print(f"Error getting NetEase track details: {e}")
        return {"error": str(e)}


@app.get("/api/netease/top")
async def get_netease_top_songs(limit: int = 20):
    """Get top songs from NetEase"""
    try:
        songs = netease_integration.get_top_songs(limit)
        return {"songs": songs, "total": len(songs)}
    except Exception as e:
        print(f"Error getting NetEase top songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/netease/new")
async def get_netease_new_songs(limit: int = 20):
    """Get new songs from NetEase"""
    try:
        songs = netease_integration.get_new_songs(limit)
        return {"songs": songs, "total": len(songs)}
    except Exception as e:
        print(f"Error getting NetEase new songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/api/netease/add-to-library")
async def add_netease_to_library(request: NeteaseAddRequest):
    """Add NetEase track to local library"""
    try:
        track_data = request.model_dump()
        result = netease_integration.add_to_library(track_data)
        if result:
            return {"message": "Track added to library successfully", "track": result}
        else:
            raise HTTPException(status_code=400, detail="Failed to add track")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding NetEase track to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/netease/import")
async def import_netease_track(request: NeteaseImportRequest):
    """Import NetEase tracks to database"""
    try:
        result = netease_integration.search_and_import_tracks(request.query, request.limit)
        tracks = result.get("tracks", [])
        session = recommendation_engine.Session()
        try:
            import_result = netease_integration.import_tracks_to_database(tracks, session)
            return {
                "message": "Tracks imported successfully",
                "tracks_found": len(tracks),
                "imported": import_result.get("imported", 0),
                "duplicates": import_result.get("duplicates", 0),
                "failed": import_result.get("failed", 0)
            }
        finally:
            session.close()
    except Exception as e:
        print(f"Error importing NetEase track: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Library stats endpoint
@app.get("/api/library/stats")
async def get_library_stats():
    """Get library statistics including E/W/D energy distribution"""
    session = recommendation_engine.Session()
    try:
        from models.music import Song
        from sqlalchemy import func

        total_songs = session.query(Song).count()

        def _stats(attr):
            vals = [r[0] for r in session.query(attr).filter(attr.isnot(None)).all() if r[0] is not None]
            if not vals:
                return {"average": None, "min": None, "max": None, "distribution": {}}
            buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
            for v in vals:
                if v < 0.2: buckets["0.0-0.2"] += 1
                elif v < 0.4: buckets["0.2-0.4"] += 1
                elif v < 0.6: buckets["0.4-0.6"] += 1
                elif v < 0.8: buckets["0.6-0.8"] += 1
                else: buckets["0.8-1.0"] += 1
            return {
                "average": round(sum(vals) / len(vals), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "distribution": buckets
            }

        analyzed = session.query(Song).filter(Song.energy.isnot(None)).count()

        return {
            "total_songs": total_songs,
            "analyzed_count": analyzed,
            "pending_analysis_count": total_songs - analyzed,
            "energy_stats": _stats(Song.energy),
            "warmth_stats": _stats(Song.warmth),
            "density_stats": _stats(Song.density)
        }
    except Exception as e:
        print(f"Error getting library stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# ElevenLabs TTS API endpoints
class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    model_id: Optional[str] = None


@app.post("/api/tts/speak", response_class=Response)
async def text_to_speech(request: TTSRequest):
    """Convert text to speech using ElevenLabs API"""
    try:
        audio_data = elevenlabs_integration.text_to_speech(
            text=request.text,
            voice_id=request.voice_id,
            model_id=request.model_id
        )
        
        if audio_data:
            return Response(content=audio_data, media_type="audio/mpeg")
        else:
            raise HTTPException(status_code=500, detail="Failed to generate speech")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in TTS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tts/voices")
async def get_tts_voices():
    """Get list of available ElevenLabs voices"""
    try:
        voices = elevenlabs_integration.list_voices()
        if voices:
            return voices
        else:
            raise HTTPException(status_code=500, detail="Failed to get voices")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting TTS voices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tts/voice/{voice_id}")
async def get_tts_voice_info(voice_id: str):
    """Get detailed information about a specific voice"""
    try:
        voice_info = elevenlabs_integration.get_voice_info(voice_id)
        if voice_info:
            return voice_info
        else:
            raise HTTPException(status_code=404, detail="Voice not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting voice info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# Playlist API — Memory Corridor
# ═══════════════════════════════════════════════════════════════

def _playlist_to_dict(pl) -> dict:
    return {
        "id": pl.id,
        "name": pl.name,
        "description": pl.description,
        "created_at": pl.created_at.isoformat() if pl.created_at else None,
        "updated_at": pl.updated_at.isoformat() if pl.updated_at else None,
        "context": pl.context or {},
        "song_count": len(pl.playlist_songs) if pl.playlist_songs else 0
    }


def _ewd_distance(a, b) -> float:
    """Normalized E/W/D distance between two songs (0-1)."""
    import math
    de = (a.get("energy") or 0.5) - (b.get("energy") or 0.5)
    dw = (a.get("warmth") or 0.5) - (b.get("warmth") or 0.5)
    dd = (a.get("density") or 0.5) - (b.get("density") or 0.5)
    return math.sqrt(de*de + dw*dw + dd*dd) / math.sqrt(3)


SCENE_NAMES = {
    (5, 8):   "清晨微光",
    (8, 12):  "正午底色",
    (12, 18): "午后暖流",
    (18, 21): "黄昏余音",
    (21, 24): "深夜暗流",
    (0, 5):   "凌晨寂静",
}


def _get_scene_for_hour(hour: int) -> tuple:
    for (h_start, h_end), name in SCENE_NAMES.items():
        if h_start <= hour < h_end:
            from core.audio_analyzer import get_time_offset
            return name, get_time_offset(hour)
    return "正午底色", {"energy_offset": 0, "warmth_offset": 0, "density_offset": 0}


@app.post("/api/playlists")
async def create_playlist(body: PlaylistCreateRequest):
    """Create a new playlist."""
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
            energies = [s.get("energy", 0.5) for s in body.seed_songs if s.get("energy") is not None]
            warmths = [s.get("warmth", 0.5) for s in body.seed_songs if s.get("warmth") is not None]
            densities = [s.get("density", 0.5) for s in body.seed_songs if s.get("density") is not None]
            if energies:
                ctx["energy_center"] = round(sum(energies) / len(energies), 4)
                ctx["warmth_center"] = round(sum(warmths) / len(warmths), 4)
                ctx["density_center"] = round(sum(densities) / len(densities), 4)

        playlist = Playlist(
            id=pl_id, name=body.name, description=body.description,
            created_at=datetime.now(timezone.utc), context=ctx
        )
        session.add(playlist)

        if body.seed_songs:
            for i, s in enumerate(body.seed_songs):
                ps = PlaylistSong(playlist_id=pl_id, song_id=s["id"], position=i)
                session.add(ps)

        session.commit()
        return {"message": "Playlist created", "playlist": _playlist_to_dict(playlist)}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error creating playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/api/playlists")
async def get_all_playlists():
    """Get all playlists with song counts and E/W/D color previews."""
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
                    dots.append({"song_id": song.id, "title": song.title,
                                 "energy": song.energy, "warmth": song.warmth, "density": song.density})
            d["color_dots"] = dots
            result.append(d)
        return {"playlists": result}
    except Exception as e:
        print(f"Error getting playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/api/playlists/scenes")
async def get_scene_playlists():
    """Get or auto-generate scene playlists matching the current hour."""
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song
        from datetime import datetime, timezone
        import uuid, math

        hour = datetime.now().hour
        scene_name, offsets = _get_scene_for_hour(hour)

        e_off = offsets.get("energy_offset", 0)
        w_off = offsets.get("warmth_offset", 0)
        d_off = offsets.get("density_offset", 0)

        all_songs = session.query(Song).filter(
            Song.energy.isnot(None), Song.warmth.isnot(None), Song.density.isnot(None)).all()

        matched = []
        for s in all_songs:
            eff_e = max(0, min(1, (s.energy or 0.5) + e_off))
            eff_w = max(0, min(1, (s.warmth or 0.5) + w_off))
            eff_d = max(0, min(1, (s.density or 0.5) + d_off))
            if 5 <= hour < 8:
                score = (1 - abs(eff_e - 0.45)) + (1 - abs(eff_w - 0.6)) + (1 - abs(eff_d - 0.4))
            elif 8 <= hour < 12:
                score = (1 - abs(eff_e - 0.5)) + (1 - abs(eff_w - 0.5)) + (1 - abs(eff_d - 0.5))
            elif 12 <= hour < 18:
                score = (1 - abs(eff_e - 0.55)) + (1 - abs(eff_w - 0.6)) + (1 - abs(eff_d - 0.5))
            elif 18 <= hour < 21:
                score = (1 - abs(eff_e - 0.4)) + (1 - abs(eff_w - 0.55)) + (1 - abs(eff_d - 0.45))
            elif 21 <= hour < 24:
                score = (1 - abs(eff_e - 0.35)) + (1 - abs(eff_w - 0.45)) + (1 - abs(eff_d - 0.45))
            else:
                score = (1 - abs(eff_e - 0.25)) + (1 - abs(eff_w - 0.4)) + (1 - abs(eff_d - 0.35))
            if score > 1.8:
                matched.append((score, s))
        matched.sort(key=lambda x: -x[0])
        top = matched[:10]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        existing = session.query(Playlist).filter_by(id="scene_auto").first()

        if not existing:
            playlist = Playlist(id="scene_auto", name=scene_name,
                                description=f"Malio 自动生成 · {scene_name}",
                                created_at=datetime.now(timezone.utc),
                                context={"type": "scene", "scene": scene_name, "updated_date": today, "offsets": offsets})
            session.add(playlist)
            for i, (score, s) in enumerate(top):
                session.add(PlaylistSong(playlist_id="scene_auto", song_id=s.id, position=i))
            session.commit()
        else:
            if existing.context.get("updated_date") != today:
                existing.name = scene_name
                existing.context["updated_date"] = today
                existing.context["offsets"] = offsets
                session.query(PlaylistSong).filter_by(playlist_id="scene_auto").delete()
                for i, (score, s) in enumerate(top):
                    session.add(PlaylistSong(playlist_id="scene_auto", song_id=s.id, position=i))
                existing.updated_at = datetime.now(timezone.utc)
                session.commit()
            playlist = existing

        pss = session.query(PlaylistSong).filter_by(playlist_id=playlist.id).order_by(PlaylistSong.position).all()
        songs_out = []
        for ps in pss:
            s = session.query(Song).filter_by(id=ps.song_id).first()
            if s:
                songs_out.append({"id": s.id, "title": s.title, "artist": s.artist,
                                  "energy": s.energy, "warmth": s.warmth, "density": s.density})
        return {"playlist_id": playlist.id, "name": playlist.name, "scene": scene_name,
                "hour": hour, "offsets": offsets, "songs": songs_out, "total": len(songs_out)}
    except Exception as e:
        session.rollback()
        print(f"Error getting scene playlists: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/api/playlists/{playlist_id}")
async def get_playlist(playlist_id: str):
    """Get playlist detail with full song list."""
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song

        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")

        pss = session.query(PlaylistSong).filter_by(playlist_id=playlist_id).order_by(PlaylistSong.position).all()
        songs = []
        for ps in pss:
            song = session.query(Song).filter_by(id=ps.song_id).first()
            if song:
                songs.append({"id": song.id, "title": song.title, "artist": song.artist,
                              "album": song.album, "duration": song.duration,
                              "energy": song.energy, "warmth": song.warmth, "density": song.density,
                              "audio_path": song.audio_path, "position": ps.position})
        result = _playlist_to_dict(pl)
        result["songs"] = songs
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.put("/api/playlists/{playlist_id}")
async def update_playlist(playlist_id: str, body: PlaylistUpdateRequest):
    """Update playlist metadata."""
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist

        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if body.name is not None:
            pl.name = body.name
        if body.description is not None:
            pl.description = body.description

        ctx = dict(pl.context or {})
        if body.tags is not None:
            ctx["tags"] = body.tags
        if body.context is not None:
            ctx.update(body.context)
        pl.context = ctx

        from datetime import datetime, timezone
        pl.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"message": "Playlist updated", "playlist": _playlist_to_dict(pl)}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error updating playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: str):
    """Delete a playlist and its song associations."""
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong

        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")

        session.query(PlaylistSong).filter_by(playlist_id=playlist_id).delete()
        session.delete(pl)
        session.commit()
        return {"message": "Playlist deleted"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error deleting playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/playlists/generate")
async def generate_playlist_from_capture(body: PlaylistGenerateRequest):
    """Generate a playlist from nebula-captured particles."""
    session = recommendation_engine.Session()
    try:
        from models.music import Song, Playlist, PlaylistSong
        import uuid, math
        from datetime import datetime, timezone

        captured = body.captured_songs
        if not captured:
            raise HTTPException(status_code=400, detail="No captured songs provided")

        energies = [s.get("energy", 0.5) for s in captured if s.get("energy") is not None] or [0.5]
        warmths = [s.get("warmth", 0.5) for s in captured if s.get("warmth") is not None] or [0.5]
        densities = [s.get("density", 0.5) for s in captured if s.get("density") is not None] or [0.5]
        centroid = {"energy": round(sum(energies)/len(energies), 4),
                    "warmth": round(sum(warmths)/len(warmths), 4),
                    "density": round(sum(densities)/len(densities), 4)}

        all_songs = session.query(Song).filter(
            Song.energy.isnot(None), Song.warmth.isnot(None), Song.density.isnot(None)).all()

        scored = []
        for song in all_songs:
            dist = _ewd_distance(
                {"energy": song.energy, "warmth": song.warmth, "density": song.density}, centroid)
            if dist < 0.25:
                scored.append((dist, song))
        scored.sort(key=lambda x: x[0])
        top_matches = scored[:20]

        seed_titles = [s.get("title", "") for s in captured if s.get("title")]
        e_desc = "高能" if centroid["energy"] > 0.65 else ("低能" if centroid["energy"] < 0.35 else "中能")
        w_desc = "暖调" if centroid["warmth"] > 0.6 else ("冷调" if centroid["warmth"] < 0.4 else "中性")
        d_desc = "浓密" if centroid["density"] > 0.7 else ("极简" if centroid["density"] < 0.3 else "适密")

        try:
            song_context = [{"title": s.get("title", ""), "artist": ""} for s in captured[:3]]
            playlist_name = kimi_integration.generate_playlist_name(
                song_context, {"energy_desc": f"{e_desc}{w_desc}{d_desc}", "seed": seed_titles})
        except Exception:
            playlist_name = f"{e_desc}{w_desc}{d_desc} · {seed_titles[0] if seed_titles else '未命名'}"

        pl_id = str(uuid.uuid4())[:8]
        ctx = {
            "type": "capture", "energy_center": centroid["energy"],
            "warmth_center": centroid["warmth"], "density_center": centroid["density"],
            "seed_song_ids": [s.get("id") for s in captured],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        if top_matches:
            ctx["energy_range"] = [round(min(s.energy for _, s in top_matches), 4),
                                   round(max(s.energy for _, s in top_matches), 4)]
            ctx["warmth_range"] = [round(min(s.warmth for _, s in top_matches), 4),
                                   round(max(s.warmth for _, s in top_matches), 4)]
            ctx["density_range"] = [round(min(s.density for _, s in top_matches), 4),
                                    round(max(s.density for _, s in top_matches), 4)]

        playlist = Playlist(id=pl_id, name=playlist_name,
                            description=f"星云捕获 · {e_desc}{w_desc}{d_desc}",
                            created_at=datetime.now(timezone.utc), context=ctx)
        session.add(playlist)
        for i, (dist, song) in enumerate(top_matches):
            session.add(PlaylistSong(playlist_id=pl_id, song_id=song.id, position=i))
        session.commit()

        songs_out = [{"id": s.id, "title": s.title, "artist": s.artist,
                      "energy": s.energy, "warmth": s.warmth, "density": s.density}
                     for _, s in top_matches]
        return {"playlist_name": playlist_name, "playlist_id": pl_id, "centroid": centroid,
                "songs": songs_out, "total": len(songs_out)}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error generating playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/playlists/{playlist_id}/songs")
async def add_song_to_playlist(playlist_id: str, body: PlaylistSongRequest):
    """Add a song to a playlist."""
    session = recommendation_engine.Session()
    try:
        from models.music import Playlist, PlaylistSong, Song

        pl = session.query(Playlist).filter_by(id=playlist_id).first()
        if not pl:
            raise HTTPException(status_code=404, detail="Playlist not found")
        song = session.query(Song).filter_by(id=body.song_id).first()
        if not song:
            raise HTTPException(status_code=404, detail="Song not found")

        existing = session.query(PlaylistSong).filter_by(playlist_id=playlist_id, song_id=body.song_id).first()
        if existing:
            return {"message": "Song already in playlist"}

        max_pos = session.query(PlaylistSong).filter_by(playlist_id=playlist_id).count()
        ps = PlaylistSong(playlist_id=playlist_id, song_id=body.song_id, position=max_pos)
        session.add(ps)

        from datetime import datetime, timezone
        pl.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"message": "Song added to playlist"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error adding song to playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/api/playlists/{playlist_id}/songs/{song_id}")
async def remove_song_from_playlist(playlist_id: str, song_id: str):
    """Remove a song from a playlist."""
    session = recommendation_engine.Session()
    try:
        from models.music import PlaylistSong
        ps = session.query(PlaylistSong).filter_by(playlist_id=playlist_id, song_id=song_id).first()
        if not ps:
            raise HTTPException(status_code=404, detail="Song not in playlist")
        session.delete(ps)
        session.commit()
        return {"message": "Song removed from playlist"}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        print(f"Error removing song from playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
# ── WebSocket: Real-time playback state ─────────────────────────
@app.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """Real-time playback state and song queue updates via Feedback"""
    await websocket.accept()
    feedback_mgr.register(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                if data.get("action") == "get_state":
                    await feedback_mgr.push_snapshot(
                        song=None,
                        is_playing=False,
                        playlist=[],
                    )
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        feedback_mgr.unregister(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
