from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Song(Base):
    """Song model"""
    __tablename__ = "songs"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    artist = Column(JSON, nullable=False)  # List of artists
    album = Column(String)
    genre = Column(JSON)  # List of genres
    release_year = Column(Integer)
    duration = Column(Integer)  # Duration in seconds
    features = Column(JSON)  # Audio features
    audio_path = Column(String)  # Path to audio file

    # E/W/D energy field classification (0.0 - 1.0)
    energy = Column(Float, nullable=True, default=None)
    warmth = Column(Float, nullable=True, default=None)
    density = Column(Float, nullable=True, default=None)
    energy_updated_at = Column(DateTime, nullable=True, default=None)

    # Relationships
    playlist_songs = relationship("PlaylistSong", back_populates="song")
    listening_history = relationship("UserMusicHistory", back_populates="song")


class Playlist(Base):
    """Playlist model"""
    __tablename__ = "playlists"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    context = Column(JSON)  # Creation context

    # Relationships
    playlist_songs = relationship("PlaylistSong", back_populates="playlist")


class PlaylistSong(Base):
    """Association table for playlist-song many-to-many relationship"""
    __tablename__ = "playlist_songs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(String, ForeignKey("playlists.id"), nullable=False)
    song_id = Column(String, ForeignKey("songs.id"), nullable=False)
    position = Column(Integer, nullable=False)

    # Relationships
    playlist = relationship("Playlist", back_populates="playlist_songs")
    song = relationship("Song", back_populates="playlist_songs")


class UserMusicHistory(Base):
    """User music history model"""
    __tablename__ = "user_music_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)  # Using string for flexibility
    song_id = Column(String, ForeignKey("songs.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    context = Column(JSON)  # Listening context
    skip_rate = Column(Float, default=0.0)  # 0.0 = completed, 1.0 = skipped immediately

    # Relationships
    song = relationship("Song", back_populates="listening_history")
