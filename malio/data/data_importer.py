import os
import json
import csv
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models.music import Base, Song, Playlist, PlaylistSong, UserMusicHistory
from config.config import settings


class MusicDataImporter:
    """Music data importer for importing 14 years of music data"""
    
    def __init__(self):
        """Initialize the importer"""
        self.engine = create_engine(settings.database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def import_data(self, data_path):
        """Import music data from the given path"""
        session = self.Session()
        
        try:
            # Import songs
            songs_path = os.path.join(data_path, "songs")
            if os.path.exists(songs_path):
                self._import_songs(session, songs_path)
            
            # Import playlists
            playlists_path = os.path.join(data_path, "playlists")
            if os.path.exists(playlists_path):
                self._import_playlists(session, playlists_path)
            
            # Import listening history
            history_path = os.path.join(data_path, "history")
            if os.path.exists(history_path):
                self._import_listening_history(session, history_path)
            
            session.commit()
            print("Data import completed successfully!")
            
        except Exception as e:
            session.rollback()
            print(f"Error during data import: {e}")
            raise
        finally:
            session.close()
    
    def _import_songs(self, session, songs_path):
        """Import songs from the songs directory"""
        for filename in os.listdir(songs_path):
            if filename.endswith(".json"):
                file_path = os.path.join(songs_path, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    songs_data = json.load(f)
                    for song_data in songs_data:
                        song = self._create_song(song_data)
                        # Check if song already exists
                        existing_song = session.query(Song).filter_by(id=song.id).first()
                        if not existing_song:
                            session.add(song)
    
    def _import_playlists(self, session, playlists_path):
        """Import playlists from the playlists directory"""
        for filename in os.listdir(playlists_path):
            if filename.endswith(".json"):
                file_path = os.path.join(playlists_path, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    playlists_data = json.load(f)
                    for playlist_data in playlists_data:
                        playlist = self._create_playlist(playlist_data)
                        # Check if playlist already exists
                        existing_playlist = session.query(Playlist).filter_by(id=playlist.id).first()
                        if not existing_playlist:
                            session.add(playlist)
                            
                            # Add playlist songs
                            for position, song_id in enumerate(playlist_data.get("songs", [])):
                                playlist_song = PlaylistSong(
                                    playlist_id=playlist.id,
                                    song_id=song_id,
                                    position=position
                                )
                                session.add(playlist_song)
    
    def _import_listening_history(self, session, history_path):
        """Import listening history from the history directory"""
        for filename in os.listdir(history_path):
            if filename.endswith(".json"):
                file_path = os.path.join(history_path, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                    for item in history_data:
                        history = self._create_listening_history(item)
                        session.add(history)
    
    def _create_song(self, song_data):
        """Create a Song object from song data"""
        return Song(
            id=song_data.get("id"),
            title=song_data.get("title"),
            artist=song_data.get("artist", []),
            album=song_data.get("album"),
            genre=song_data.get("genre", []),
            release_year=song_data.get("release_year"),
            duration=song_data.get("duration"),
            features=song_data.get("features", {})
        )
    
    def _create_playlist(self, playlist_data):
        """Create a Playlist object from playlist data"""
        created_at = playlist_data.get("created_at")
        if created_at:
            created_at = datetime.fromisoformat(created_at)
        
        return Playlist(
            id=playlist_data.get("id"),
            name=playlist_data.get("name"),
            description=playlist_data.get("description"),
            created_at=created_at,
            context=playlist_data.get("context", {})
        )
    
    def _create_listening_history(self, history_data):
        """Create a UserMusicHistory object from history data"""
        timestamp = history_data.get("timestamp")
        if timestamp:
            timestamp = datetime.fromisoformat(timestamp)
        
        return UserMusicHistory(
            user_id=history_data.get("user_id", "default"),
            song_id=history_data.get("song_id"),
            timestamp=timestamp,
            context=history_data.get("context", {}),
            skip_rate=history_data.get("skip_rate", 0.0)
        )


# Example usage
if __name__ == "__main__":
    importer = MusicDataImporter()
    importer.import_data(settings.music_data_path)
