import requests
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from config.config import settings


class SpotifyIntegration:
    """Integration with Spotify API"""

    def __init__(self):
        """Initialize Spotify integration"""
        self.client_id = settings.spotify_client_id
        self.client_secret = settings.spotify_client_secret

        self.access_token = None
        self.token_expires_at = None

        print(f"Spotify Client ID: {'Set' if self.client_id else 'Not set'}")
        print(f"Spotify Client Secret: {'Set' if self.client_secret else 'Not set'}")

        self._refresh_access_token()

    def _refresh_access_token(self) -> bool:
        """Refresh Spotify access token"""
        if not self.client_id or self.client_id == "placeholder_spotify_client_id" or \
                not self.client_secret or self.client_secret == "placeholder_spotify_client_secret":
            print("Spotify credentials not set, skipping token refresh")
            return False

        try:
            # Encode client credentials
            credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}"
            }

            data = {
                "grant_type": "client_credentials"
            }

            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()
            self.access_token = result["access_token"]
            self.token_expires_at = datetime.now() + timedelta(seconds=result["expires_in"])

            print(f"Spotify access token acquired successfully, expires at {self.token_expires_at}")
            return True

        except Exception as e:
            print(f"Error refreshing Spotify access token: {e}")
            return False

    def _ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token"""
        if not self.access_token or datetime.now() >= self.token_expires_at - timedelta(minutes=5):
            return self._refresh_access_token()
        return True

    def search_tracks(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for tracks on Spotify"""
        if not self._ensure_valid_token():
            return self._get_sample_tracks()

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            params = {
                "q": query,
                "type": "track",
                "limit": limit
            }

            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()

            # Convert to our format
            tracks = []
            for item in result.get("tracks", {}).get("items", []):
                track = self._convert_spotify_track(item)
                tracks.append(track)

            return tracks

        except Exception as e:
            print(f"Error searching tracks: {e}")
            return self._get_sample_tracks()

    def get_track_details(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get track details from Spotify"""
        if not self._ensure_valid_token():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            response = requests.get(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers=headers,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()
            return self._convert_spotify_track(result)

        except Exception as e:
            print(f"Error getting track details: {e}")
            return None

    def get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get audio features from Spotify"""
        if not self._ensure_valid_token():
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            response = requests.get(
                f"https://api.spotify.com/v1/audio-features/{track_id}",
                headers=headers,
                timeout=10
            )

            response.raise_for_status()

            return response.json()

        except Exception as e:
            print(f"Error getting audio features: {e}")
            return None

    def get_audio_features_batch(self, track_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get audio features for multiple tracks (max 100)"""
        if not self._ensure_valid_token():
            return {}

        if not track_ids:
            return {}

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            params = {
                "ids": ",".join(track_ids[:100])
            }

            response = requests.get(
                "https://api.spotify.com/v1/audio-features",
                headers=headers,
                params=params,
                timeout=10
            )

            response.raise_for_status()
            result = response.json()

            features_map = {}
            for item in result.get("audio_features", []):
                if item:
                    track_id = item.get("id")
                    features_map[track_id] = item

            return features_map

        except Exception as e:
            print(f"Error getting batch audio features: {e}")
            return {}

    def get_track_with_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get track details with audio features combined"""
        track = self.get_track_details(track_id)
        if not track:
            return None

        features = self.get_audio_features(track_id)
        if features:
            track["features"] = {
                "acousticness": features.get("acousticness", 0),
                "danceability": features.get("danceability", 0),
                "energy": features.get("energy", 0),
                "instrumentalness": features.get("instrumentalness", 0),
                "key": features.get("key", 0),
                "liveness": features.get("liveness", 0),
                "loudness": features.get("loudness", 0),
                "mode": features.get("mode", 0),
                "speechiness": features.get("speechiness", 0),
                "tempo": features.get("tempo", 0),
                "time_signature": features.get("time_signature", 0),
                "valence": features.get("valence", 0)
            }
        return track

    def get_recommendations(
            self,
            seed_tracks: Optional[List[str]] = None,
            seed_artists: Optional[List[str]] = None,
            seed_genres: Optional[List[str]] = None,
            limit: int = 20,
            **kwargs
    ) -> List[Dict[str, Any]]:
        """Get music recommendations from Spotify"""
        if not self._ensure_valid_token():
            return self._get_sample_tracks()

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            params = {
                "limit": limit
            }

            if seed_tracks:
                params["seed_tracks"] = ",".join(seed_tracks)
            if seed_artists:
                params["seed_artists"] = ",".join(seed_artists)
            if seed_genres:
                params["seed_genres"] = ",".join(seed_genres)

            # Add audio feature parameters
            audio_features = [
                "min_acousticness", "max_acousticness", "target_acousticness",
                "min_danceability", "max_danceability", "target_danceability",
                "min_energy", "max_energy", "target_energy",
                "min_instrumentalness", "max_instrumentalness", "target_instrumentalness",
                "min_liveness", "max_liveness", "target_liveness",
                "min_loudness", "max_loudness", "target_loudness",
                "min_speechiness", "max_speechiness", "target_speechiness",
                "min_tempo", "max_tempo", "target_tempo",
                "min_valence", "max_valence", "target_valence",
                "min_popularity", "max_popularity", "target_popularity"
            ]

            for feature in audio_features:
                if feature in kwargs and kwargs[feature] is not None:
                    params[feature] = kwargs[feature]

            response = requests.get(
                "https://api.spotify.com/v1/recommendations",
                headers=headers,
                params=params,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()

            # Convert to our format
            tracks = []
            for item in result.get("tracks", []):
                track = self._convert_spotify_track(item)
                tracks.append(track)

            return tracks

        except Exception as e:
            print(f"Error getting recommendations: {e}")
            return self._get_sample_tracks()

    def _convert_spotify_track(self, spotify_track: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Spotify track to our format"""
        return {
            "id": spotify_track.get("id", ""),
            "title": spotify_track.get("name", ""),
            "artist": [artist.get("name", "") for artist in spotify_track.get("artists", [])],
            "album": spotify_track.get("album", {}).get("name", ""),
            "album_art": spotify_track.get("album", {}).get("images", [{}])[0].get("url", "") if spotify_track.get(
                "album", {}).get("images") else "",
            "duration": spotify_track.get("duration_ms", 0) // 1000,
            "preview_url": spotify_track.get("preview_url", ""),
            "external_url": spotify_track.get("external_urls", {}).get("spotify", ""),
            "spotify_uri": spotify_track.get("uri", ""),
            "popularity": spotify_track.get("popularity", 0),
            "genre": [],  # Spotify doesn't provide genres at track level
            "audio_path": ""  # We'll use preview_url for playback
        }

    def _get_sample_tracks(self) -> List[Dict[str, Any]]:
        """Get sample tracks when Spotify is not available"""
        return [
            {
                "id": "sample_001",
                "title": "晴天",
                "artist": ["周杰伦"],
                "album": "叶惠美",
                "album_art": "",
                "duration": 269,
                "preview_url": "",
                "external_url": "",
                "spotify_uri": "",
                "popularity": 95,
                "genre": ["华语流行"],
                "audio_path": "songs/sunny_day.mp3"
            },
            {
                "id": "sample_002",
                "title": "平凡之路",
                "artist": ["朴树"],
                "album": "猎户星座",
                "album_art": "",
                "duration": 302,
                "preview_url": "",
                "external_url": "",
                "spotify_uri": "",
                "popularity": 90,
                "genre": ["华语摇滚"],
                "audio_path": "songs/ordinary_road.mp3"
            },
            {
                "id": "sample_003",
                "title": "孤勇者",
                "artist": ["陈奕迅"],
                "album": "孤勇者",
                "album_art": "",
                "duration": 262,
                "preview_url": "",
                "external_url": "",
                "spotify_uri": "",
                "popularity": 98,
                "genre": ["华语流行"],
                "audio_path": "songs/lone_warrior.mp3"
            }
        ]

    def get_new_releases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get new releases from Spotify"""
        if not self._ensure_valid_token():
            return self._get_sample_tracks()

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            params = {
                "limit": limit
            }

            response = requests.get(
                "https://api.spotify.com/v1/browse/new-releases",
                headers=headers,
                params=params,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()

            # Get tracks from the new release albums
            tracks = []
            albums = result.get("albums", {}).get("items", [])
            
            # Get up to limit tracks from the new releases
            tracks_collected = 0
            for album in albums:
                if tracks_collected >= limit:
                    break
                
                # Get tracks for this album
                album_tracks_url = album.get("href") + "/tracks"
                tracks_response = requests.get(
                    album_tracks_url,
                    headers=headers,
                    params={"limit": limit - tracks_collected},
                    timeout=10
                )
                
                if tracks_response.status_code == 200:
                    album_tracks_data = tracks_response.json()
                    for item in album_tracks_data.get("items", []):
                        if tracks_collected >= limit:
                            break
                        track = self._convert_spotify_track(item)
                        # Add album genre info from the album
                        if album.get("genres"):
                            track["genre"] = album["genres"]
                        tracks.append(track)
                        tracks_collected += 1

            return tracks if tracks else self._get_sample_tracks()

        except Exception as e:
            print(f"Error getting new releases: {e}")
            return self._get_sample_tracks()

    def search_artists(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for artists on Spotify"""
        if not self._ensure_valid_token():
            return []

        try:
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            params = {
                "q": query,
                "type": "artist",
                "limit": limit
            }

            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params,
                timeout=10
            )

            response.raise_for_status()

            result = response.json()

            artists = []
            for item in result.get("artists", {}).get("items", []):
                artist = {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "genres": item.get("genres", []),
                    "images": item.get("images", []),
                    "popularity": item.get("popularity", 0),
                    "external_url": item.get("external_urls", {}).get("spotify", "")
                }
                artists.append(artist)

            return artists

        except Exception as e:
            print(f"Error searching artists: {e}")
            return []

    def add_to_library(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Add a Spotify track to the local database"""
        track = self.get_track_with_features(track_id)
        if not track:
            return None
        return self.import_track_to_db_single(track)

    def import_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Import a Spotify track by ID into the local database"""
        return self.add_to_library(track_id)

    def import_track_to_db_single(self, track_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Import a single track dict into the local database"""
        from models.music import Song
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from config.config import settings

        engine = create_engine(settings.database_url)
        from models.music import Base
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            track_id = track_data.get("id")
            existing = session.query(Song).filter_by(id=track_id).first()
            if existing:
                session.close()
                return self._convert_spotify_track({"id": track_id, "name": ""})

            song = Song(
                id=track_id,
                title=track_data.get("title", "Unknown"),
                artist=track_data.get("artist", []),
                album=track_data.get("album", "Unknown Album"),
                genre=track_data.get("genre", []),
                duration=track_data.get("duration", 180),
                features=track_data.get("features", {}),
                audio_path=track_data.get("audio_path", "")
            )
            session.add(song)
            session.commit()
            return track_data
        except Exception as e:
            session.rollback()
            print(f"Error importing track to DB: {e}")
            return None
        finally:
            session.close()

    def search_and_import_tracks(self, query: str, limit: int = 20, include_features: bool = True) -> Dict[str, Any]:
        """Search tracks on Spotify and return with optional audio features"""
        tracks = self.search_tracks(query, limit)
        if not tracks:
            return {"tracks": [], "imported": 0, "failed": 0}

        track_ids = [t["id"] for t in tracks if t.get("id")]
        
        features_map = {}
        if include_features and track_ids:
            features_map = self.get_audio_features_batch(track_ids)

        for track in tracks:
            track_id = track.get("id")
            if track_id in features_map:
                features = features_map[track_id]
                track["features"] = {
                    "acousticness": features.get("acousticness", 0),
                    "danceability": features.get("danceability", 0),
                    "energy": features.get("energy", 0),
                    "instrumentalness": features.get("instrumentalness", 0),
                    "key": features.get("key", 0),
                    "liveness": features.get("liveness", 0),
                    "loudness": features.get("loudness", 0),
                    "mode": features.get("mode", 0),
                    "speechiness": features.get("speechiness", 0),
                    "tempo": features.get("tempo", 0),
                    "time_signature": features.get("time_signature", 0),
                    "valence": features.get("valence", 0)
                }

        return {"tracks": tracks, "features_count": len(features_map)}

    def import_tracks_to_database(self, tracks: List[Dict[str, Any]], session) -> Dict[str, Any]:
        """Import tracks to local database"""
        from models.music import Song
        
        imported = 0
        failed = 0
        duplicates = 0
        
        for track_data in tracks:
            try:
                track_id = track_data.get("id")
                if not track_id:
                    failed += 1
                    continue

                existing = session.query(Song).filter_by(id=track_id).first()
                if existing:
                    duplicates += 1
                    continue

                song = Song(
                    id=track_id,
                    title=track_data.get("title", "Unknown"),
                    artist=track_data.get("artist", []),
                    album=track_data.get("album", "Unknown Album"),
                    genre=track_data.get("genre", []),
                    release_year=None,
                    duration=track_data.get("duration", 180),
                    features=track_data.get("features", {}),
                    audio_path=track_data.get("audio_path", "")
                )
                session.add(song)
                imported += 1

            except Exception as e:
                print(f"Error importing track {track_data.get('id')}: {e}")
                failed += 1

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error committing transaction: {e}")

        return {
            "imported": imported,
            "duplicates": duplicates,
            "failed": failed,
            "total": len(tracks)
        }


# Example usage
if __name__ == "__main__":
    spotify = SpotifyIntegration()

    # Test search
    print("Searching for tracks...")
    tracks = spotify.search_tracks("周杰伦", limit=5)
    for i, track in enumerate(tracks, 1):
        print(f"{i}. {track['title']} by {', '.join(track['artist'])}")

    # Test recommendations
    print("\nGetting recommendations...")
    recommendations = spotify.get_recommendations(
        seed_genres=["pop", "rock"],
        limit=5
    )
    for i, track in enumerate(recommendations, 1):
        print(f"{i}. {track['title']} by {', '.join(track['artist'])}")
