import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Music, Settings } from 'lucide-react';

function SongManager({ onClose, onRefresh }) {
  const [songs, setSongs] = useState([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSong, setNewSong] = useState({
    id: '', title: '', artist: '', album: '', genre: '', releaseYear: '', duration: '' });
  const [loading, setLoading] = useState(false);

  // Load songs from API
  useEffect(() => {
    loadSongs();
  }, []);

  const loadSongs = async () => {
    fetch('/api/songs')
      .then(res => res.json())
      .then(data => {
        setSongs(data.songs || []);
      })
      .catch(err => {
        console.error('Error loading songs:', err);
      });
  };

  const handleAddSong = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const songData = {
        id: newSong.id || `song_${Date.now()}`,
        title: newSong.title,
        artist: newSong.artist.split(',').map(a => a.trim()),
        album: newSong.album,
        genre: newSong.genre.split(',').map(g => g.trim()),
        release_year: parseInt(newSong.releaseYear) || new Date().getFullYear(),
        duration: parseInt(newSong.duration) || 180,
        features: {}
      };

      const response = await fetch('/api/songs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(songData),
      });

      if (response.ok) {
        alert('歌曲添加成功！');
        setShowAddForm(false);
        setNewSong({ id: '', title: '', artist: '', album: '', genre: '', releaseYear: '', duration: '' });
        loadSongs();
        if (onRefresh) onRefresh();
      } else {
        alert('添加失败！');
      }
    } catch (error) {
      console.error('Error adding song:', error);
      alert('添加失败！');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSong = async (songId) => {
    if (!confirm('确定要删除这首歌吗？')) return;

    try {
      const response = await fetch(`/api/songs/${songId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        alert('歌曲删除成功！');
        loadSongs();
        if (onRefresh) onRefresh();
      }
    } catch (error) {
      console.error('Error deleting song:', error);
    }
  };

  return (
    <div className="song-manager">
      <div className="manager-header">
        <h2><Music size={24} /> 歌曲管理</h2>
        <div className="manager-actions">
          <button onClick={() => setShowAddForm(!showAddForm)} className="add-btn">
            <Plus size={16} /> 添加歌曲
          </button>
          <button onClick={onClose} className="close-btn">
            关闭
          </button>
        </div>
      </div>

      {showAddForm && (
        <div className="add-song-form">
          <h3>添加新歌曲</h3>
          <form onSubmit={handleAddSong}>
            <div className="form-row">
              <div className="form-group">
              <label>歌曲名称 *</label>
              <input
                type="text"
                value={newSong.title}
                onChange={(e) => setNewSong({...newSong, title: e.target.value})}
                required
              />
            </div>
            <div className="form-group">
              <label>歌手 *</label>
              <input
                type="text"
                value={newSong.artist}
                onChange={(e) => setNewSong({...newSong, artist: e.target.value})}
                placeholder="多个歌手用逗号分隔"
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>专辑</label>
              <input
                type="text"
                value={newSong.album}
                onChange={(e) => setNewSong({...newSong, album: e.target.value})}
              />
            </div>
            <div className="form-group">
              <label>风格</label>
              <input
                type="text"
                value={newSong.genre}
                onChange={(e) => setNewSong({...newSong, genre: e.target.value})}
                placeholder="多个风格用逗号分隔"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>发行年份</label>
              <input
                type="number"
                value={newSong.releaseYear}
                onChange={(e) => setNewSong({...newSong, releaseYear: e.target.value})}
              />
            </div>
            <div className="form-group">
              <label>时长 (秒)</label>
              <input
                type="number"
                value={newSong.duration}
                onChange={(e) => setNewSong({...newSong, duration: e.target.value})}
              />
            </div>
          </div>

          <div className="form-actions">
            <button type="submit" disabled={loading} className="submit-btn">
              {loading ? '添加中...' : '添加歌曲'}
            </button>
            <button type="button" onClick={() => setShowAddForm(false)} className="cancel-btn">
              取消
            </button>
          </div>
          </form>
        </div>
      )}

      <div className="songs-list">
        <h3>现有歌曲 ({songs.length})</h3>
        {songs.length === 0 ? (
          <div className="empty-state">
            <p>还没有歌曲，点击"添加歌曲"来添加第一首！</p>
          </div>
        ) : (
          <ul>
            {songs.map((song) => (
              <li key={song.id} className="song-item">
                <div className="song-info">
                  <Music size={20} />
                  <div>
                    <h4>{song.title}</h4>
                    <p>{song.artist.join(', ')} - {song.album}</p>
                  </div>
                </div>
                <div className="song-actions">
                  <span className="duration">{song.duration}秒</span>
                  <button
                    onClick={() => handleDeleteSong(song.id)}
                    className="delete-btn"
                    title="删除"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default SongManager;
