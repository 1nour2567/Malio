from typing import List, Dict, Any, Optional
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models.music import Song, Playlist, PlaylistSong, UserMusicHistory
from core.scene_aware_engine import SceneAwareEngine
from config.config import settings


class RecommendationEngine:
    """Music recommendation engine"""

    def __init__(self):
        """Initialize the recommendation engine"""
        self.engine = create_engine(settings.database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.scene_engine = SceneAwareEngine()

        # Create database tables
        from models.music import Base
        Base.metadata.create_all(self.engine)

        # Import sample data if database is empty
        self._import_sample_data()

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get user music preferences"""
        session = self.Session()
        try:
            # Get user listening history
            history = session.query(UserMusicHistory).filter_by(user_id=user_id).all()

            # Analyze preferences
            preferences = {
                "frequent_songs": {},
                "frequent_genres": {},
                "time_preferences": {},
                "mood_preferences": {}
            }

            for item in history:
                # Count song frequency
                preferences["frequent_songs"][item.song_id] = preferences["frequent_songs"].get(item.song_id, 0) + 1

                # Get song details
                song = session.query(Song).filter_by(id=item.song_id).first()
                if song:
                    # Count genre frequency
                    for genre in song.genre or []:
                        preferences["frequent_genres"][genre] = preferences["frequent_genres"].get(genre, 0) + 1

                # Analyze time preferences
                if item.context:
                    time_of_day = item.context.get("timeOfDay")
                    if time_of_day:
                        if time_of_day not in preferences["time_preferences"]:
                            preferences["time_preferences"][time_of_day] = {}
                        preferences["time_preferences"][time_of_day][item.song_id] = preferences["time_preferences"][
                                                                                         time_of_day].get(item.song_id,
                                                                                                          0) + 1

                    # Analyze mood preferences
                    mood = item.context.get("mood")
                    if mood:
                        if mood not in preferences["mood_preferences"]:
                            preferences["mood_preferences"][mood] = {}
                        preferences["mood_preferences"][mood][item.song_id] = preferences["mood_preferences"][mood].get(
                            item.song_id, 0) + 1

            return preferences
        finally:
            session.close()

    def calculate_song_score(self, song_id: str, user_id: str, context: Dict[str, Any]) -> float:
        """Calculate score for a song based on user preferences and context"""
        session = self.Session()
        try:
            song = session.query(Song).filter_by(id=song_id).first()
            if not song:
                return 0.0

            score = 0.0

            # Get user preferences
            preferences = self.get_user_preferences(user_id)

            # 1. Historical preference score (40%)
            historical_score = preferences["frequent_songs"].get(song_id, 0) * 0.4
            score += historical_score

            # 2. Genre preference score (20%)
            genre_score = 0.0
            for genre in song.genre or []:
                genre_score += preferences["frequent_genres"].get(genre, 0)
            genre_score = genre_score * 0.2
            score += genre_score

            # 3. Time context score (15%)
            time_of_day = context.get("time", {}).get("time_of_day")
            if time_of_day:
                time_score = preferences["time_preferences"].get(time_of_day, {}).get(song_id, 0) * 0.15
                score += time_score

            # 4. Mood context score (15%)
            user_mood = context.get("user_mood")
            if user_mood:
                mood_score = preferences["mood_preferences"].get(user_mood, {}).get(song_id, 0) * 0.15
                score += mood_score

            # 5. Weather context score (10%)
            weather = context.get("weather", {})
            if weather:
                weather_condition = weather.get("condition")
                # Map weather to appropriate music features
                if weather_condition == "Clear":
                    # Prefer energetic, happy songs
                    if song.features:
                        energy = song.features.get("energy", 0)
                        valence = song.features.get("valence", 0)
                        weather_score = (energy + valence) * 0.05
                        score += weather_score
                elif weather_condition == "Rain":
                    # Prefer calm, acoustic songs
                    if song.features:
                        acousticness = song.features.get("acousticness", 0)
                        energy = song.features.get("energy", 0)
                        weather_score = (acousticness + (1 - energy)) * 0.05
                        score += weather_score

            return score
        finally:
            session.close()

    def get_recommendations(self, user_id: str, context: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
        """Get music recommendations for the user"""
        session = self.Session()
        try:
            # Get all songs
            songs = session.query(Song).all()

            # Calculate scores for each song
            song_scores = []
            for song in songs:
                score = self.calculate_song_score(song.id, user_id, context)
                song_scores.append((song, score))

            # Sort songs by score
            song_scores.sort(key=lambda x: x[1], reverse=True)

            # Get top recommendations
            recommendations = []
            for song, score in song_scores[:limit]:
                recommendations.append({
                    "id": song.id,
                    "title": song.title,
                    "artist": song.artist,
                    "album": song.album,
                    "genre": song.genre,
                    "duration": song.duration,
                    "audio_path": song.audio_path,
                    "preview_url": (song.features or {}).get("preview_url", ""),
                    "score": score
                })

            return recommendations
        finally:
            session.close()

    def get_contextual_recommendations(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recommendations based on current context"""
        # Get current context
        context = self.scene_engine.get_full_context(user_id)

        # Get recommendations
        return self.get_recommendations(user_id, context, limit)

    def _import_sample_data(self):
        """Import sample data if database is empty"""
        session = self.Session()
        try:
            # Check if database is empty
            from models.music import Song
            song_count = session.query(Song).count()

            if song_count == 0:
                print("Database is empty, importing sample data...")

                # Import sample songs
                import json
                import os

                # Get sample data path
                sample_data_path = os.path.join(os.path.dirname(__file__), "..", "data")

                # Import songs
                songs_path = os.path.join(sample_data_path, "songs", "sample_songs.json")
                if os.path.exists(songs_path):
                    with open(songs_path, 'r', encoding='utf-8') as f:
                        songs_data = json.load(f)
                        for song_data in songs_data:
                            song = Song(
                                id=song_data.get("id"),
                                title=song_data.get("title"),
                                artist=song_data.get("artist", []),
                                album=song_data.get("album"),
                                genre=song_data.get("genre", []),
                                release_year=song_data.get("release_year"),
                                duration=song_data.get("duration"),
                                features=song_data.get("features", {})
                            )
                            session.add(song)

                # Import playlists
                from models.music import Playlist, PlaylistSong
                playlists_path = os.path.join(sample_data_path, "playlists", "sample_playlists.json")
                if os.path.exists(playlists_path):
                    with open(playlists_path, 'r', encoding='utf-8') as f:
                        playlists_data = json.load(f)
                        for playlist_data in playlists_data:
                            playlist = Playlist(
                                id=playlist_data.get("id"),
                                name=playlist_data.get("name"),
                                description=playlist_data.get("description"),
                                context=playlist_data.get("context", {})
                            )
                            session.add(playlist)

                            # Add playlist songs
                            for position, song_id in enumerate(playlist_data.get("songs", [])):
                                playlist_song = PlaylistSong(
                                    playlist_id=playlist.id,
                                    song_id=song_id,
                                    position=position
                                )
                                session.add(playlist_song)

                # Import listening history
                from models.music import UserMusicHistory
                from datetime import datetime
                history_path = os.path.join(sample_data_path, "history", "sample_history.json")
                if os.path.exists(history_path):
                    with open(history_path, 'r', encoding='utf-8') as f:
                        history_data = json.load(f)
                        for item in history_data:
                            history = UserMusicHistory(
                                user_id=item.get("user_id", "default"),
                                song_id=item.get("song_id"),
                                timestamp=datetime.fromisoformat(item.get("timestamp")) if item.get(
                                    "timestamp") else datetime.now(),
                                context=item.get("context", {}),
                                skip_rate=item.get("skip_rate", 0.0)
                            )
                            session.add(history)

                session.commit()
                print("Sample data imported successfully!")
        except Exception as e:
            session.rollback()
            print(f"Error importing sample data: {e}")
        finally:
            session.close()


# Example usage
if __name__ == "__main__":
    engine = RecommendationEngine()
    recommendations = engine.get_contextual_recommendations("default", limit=5)
    print("Recommended songs:")
    for i, song in enumerate(recommendations, 1):
        print(f"{i}. {song['title']} by {', '.join(song['artist'])} (Score: {song['score']:.2f})")
