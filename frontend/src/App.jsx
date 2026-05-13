import React, { useState, useEffect, useRef } from 'react';
import { Play, Pause, SkipBack, SkipForward, Send, Settings, Search, Music, Plus, Volume2, VolumeX } from 'lucide-react';
import SongManager from './SongManager';

function App() {
  // State for player
  const [currentSong, setCurrentSong] = useState({
    id: "",
    title: "颜色",
    artist: ["许美静"],
    album: "都是夜归人",
    duration: 258,
    currentTime: 0,
    audio_path: "",
    preview_url: "",
    album_art: ""
  });
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentPlaylist, setCurrentPlaylist] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  // State for NetEase Cloud Music integration
  const [showNeteaseSearch, setShowNeteaseSearch] = useState(false);
  const [neteaseSearchQuery, setNeteaseSearchQuery] = useState('');
  const [neteaseSearchResults, setNeteaseSearchResults] = useState([]);
  const [isSearchingNetease, setIsSearchingNetease] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [libraryStats, setLibraryStats] = useState({ songs: 0, playlists: 0, listening_history: 0 });

  // Audio element ref
  const audioRef = useRef(null);

  // State for chat
  const [messages, setMessages] = useState([
    {
      id: 1,
      content: "你好！我是 Claudio，你的音乐智能助手。今天想听听什么音乐？",
      sender: "claudio",
      time: new Date().toLocaleTimeString()
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showManager, setShowManager] = useState(false);

  // State for TTS
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceList, setVoiceList] = useState([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState('CwhRBWXzGAHq8TQ4Fs17');
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const audioPlayerRef = useRef(null);

  const messagesEndRef = useRef(null);

  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Get initial recommendations
  useEffect(() => {
    fetchRecommendations();
    fetchLibraryStats();
    fetchVoiceList();
  }, []);

  // Fetch TTS voice list
  const fetchVoiceList = async () => {
    try {
      const response = await fetch('/api/tts/voices');
      const data = await response.json();
      if (data.voices && data.voices.length > 0) {
        setVoiceList(data.voices);
      }
    } catch (error) {
      console.error('Error fetching voice list:', error);
    }
  };

  // Play TTS audio
  const playTTS = async (text) => {
    if (!ttsEnabled || !text.trim()) return;

    try {
      setIsSpeaking(true);
      const response = await fetch('/api/tts/speak', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: text,
          voice_id: selectedVoiceId
        })
      });

      if (!response.ok) {
        throw new Error('Failed to generate speech');
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);

      if (audioPlayerRef.current) {
        audioPlayerRef.current.src = audioUrl;
        audioPlayerRef.current.play().catch(error => {
          console.error('Error playing TTS:', error);
        });
      }
    } catch (error) {
      console.error('Error generating speech:', error);
    } finally {
      setIsSpeaking(false);
    }
  };

  // Update progress bar from audio element
  useEffect(() => {
    const updateProgress = () => {
      if (audioRef.current) {
        setCurrentSong(prev => ({
          ...prev,
          currentTime: audioRef.current.currentTime,
          duration: audioRef.current.duration || prev.duration
        }));
      }
    };

    const audioElement = audioRef.current;
    if (audioElement) {
      audioElement.addEventListener('timeupdate', updateProgress);
      audioElement.addEventListener('ended', () => {
        setIsPlaying(false);
        handleNextSong();
      });
    }

    return () => {
      if (audioElement) {
        audioElement.removeEventListener('timeupdate', updateProgress);
        audioElement.removeEventListener('ended', () => {
          setIsPlaying(false);
          handleNextSong();
        });
      }
    };
  }, []);

  // Handle play/pause state
  useEffect(() => {
    if (audioRef.current) {
      if (isPlaying) {
        audioRef.current.play().catch(error => {
          console.error('Error playing audio:', error);
          setIsPlaying(false);
        });
      } else {
        audioRef.current.pause();
      }
    }
  }, [isPlaying, currentSong.audio_path, currentSong.preview_url]);

  // NetEase Cloud Music search function
  const searchNetease = async () => {
    if (!neteaseSearchQuery.trim()) return;

    setIsSearchingNetease(true);
    try {
      const response = await fetch(`/api/netease/search?query=${encodeURIComponent(neteaseSearchQuery)}&limit=20`);
      const data = await response.json();
      setNeteaseSearchResults(data.tracks || []);
    } catch (error) {
      console.error('Error searching NetEase:', error);
    } finally {
      setIsSearchingNetease(false);
    }
  };

  // Play NetEase track
  const playNeteaseTrack = (track) => {
    // Get playable URL first
    const getPlayableUrl = async () => {
      if (track.preview_url) {
        return track.preview_url;
      }
      try {
        const response = await fetch(`/api/netease/track/${track.id}/url`);
        const data = await response.json();
        return data.url || '';
      } catch (error) {
        console.error('Error getting track URL:', error);
        return '';
      }
    };

    getPlayableUrl().then(url => {
      setCurrentSong({
        id: track.id,
        title: track.title,
        artist: track.artist,
        album: track.album,
        duration: track.duration || 180,
        currentTime: 0,
        audio_path: "",
        preview_url: url,
        album_art: track.album_art || ""
      });
      setIsPlaying(true);
    });
  };

  // Add NetEase track to library
  const addNeteaseTrackToLibrary = async (track) => {
    try {
      // Get playable URL first
      let playableUrl = track.preview_url;
      if (!playableUrl) {
        const response = await fetch(`/api/netease/track/${track.id}/url`);
        const data = await response.json();
        playableUrl = data.url || '';
      }

      const trackWithUrl = { ...track, preview_url: playableUrl };

      const response = await fetch('/api/netease/add-to-library', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(trackWithUrl)
      });

      if (response.ok) {
        alert('歌曲已添加到本地库！');
        fetchLibraryStats();
      } else {
        alert('添加歌曲失败');
      }
    } catch (error) {
      console.error('Error adding track to library:', error);
      alert('添加歌曲失败');
    }
  };

  // Import tracks from NetEase search results
  const importAllTracks = async () => {
    if (neteaseSearchResults.length === 0) return;

    setIsImporting(true);
    try {
      const response = await fetch('/api/netease/import', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          query: neteaseSearchQuery,
          limit: neteaseSearchResults.length
        })
      });

      const data = await response.json();
      alert(`导入完成！\n找到: ${data.tracks_found}\n成功导入: ${data.imported}\n已存在: ${data.duplicates}\n失败: ${data.failed}`);
      fetchLibraryStats();
    } catch (error) {
      console.error('Error importing tracks:', error);
      alert('导入失败');
    } finally {
      setIsImporting(false);
    }
  };

  // Fetch library statistics
  const fetchLibraryStats = async () => {
    try {
      const response = await fetch('/api/library/stats');
      const data = await response.json();
      setLibraryStats(data);
    } catch (error) {
      console.error('Error fetching library stats:', error);
    }
  };

  // Fetch recommendations from API
  const fetchRecommendations = async () => {
    try {
      const response = await fetch('/api/recommend', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      });
      const data = await response.json();

      // Add Claude's response to messages
      const claudioResponse = {
        id: messages.length + 1,
        content: data.response,
        sender: "claudio",
        time: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, claudioResponse]);

      // Play TTS for Claude's response
      setTimeout(() => playTTS(data.response), 500);

      setRecommendations(data.recommendations);
      setCurrentPlaylist(data.recommendations);
    } catch (error) {
      console.error('Error fetching recommendations:', error);
    }
  };

  // Handle chat input
  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;

    // Add user message to chat
    const userMessage = {
      id: messages.length + 1,
      content: inputMessage,
      sender: "user",
      time: new Date().toLocaleTimeString()
    };
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      // Send message to API
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          input: inputMessage
        })
      });

      const data = await response.json();

      // Add Claude's response
      const claudeMessage = {
        id: messages.length + 2,
        content: data.response,
        sender: "claudio",
        time: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, claudeMessage]);

      // Play TTS for Claude's response
      setTimeout(() => playTTS(data.response), 500);

      // Update recommendations if any
      if (data.recommendations && data.recommendations.length > 0) {
        setRecommendations(data.recommendations);
        setCurrentPlaylist(data.recommendations);
        setCurrentIndex(0);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      // Add error message
      setMessages(prev => [...prev, {
        id: messages.length + 2,
        content: "抱歉，我遇到了一些问题，请稍后再试。",
        sender: "claudio",
        time: new Date().toLocaleTimeString()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle recommendation selection
  const handleSelectRecommendation = (song) => {
    const index = currentPlaylist.findIndex(s => s.id === song.id);
    if (index !== -1) {
      setCurrentIndex(index);
    }
    setCurrentSong({
      id: song.id,
      title: song.title,
      artist: song.artist,
      album: song.album,
      duration: song.duration || 180,
      currentTime: 0,
      audio_path: song.audio_path || "",
      preview_url: song.preview_url || "",
      album_art: song.album_art || ""
    });
    setIsPlaying(true);
  };

  // Handle previous song
  const handlePreviousSong = () => {
    if (currentPlaylist.length === 0) return;
    const newIndex = (currentIndex - 1 + currentPlaylist.length) % currentPlaylist.length;
    setCurrentIndex(newIndex);
    const song = currentPlaylist[newIndex];
    setCurrentSong({
      id: song.id,
      title: song.title,
      artist: song.artist,
      album: song.album,
      duration: song.duration || 180,
      currentTime: 0,
      audio_path: song.audio_path || "",
      preview_url: song.preview_url || "",
      album_art: song.album_art || ""
    });
    setIsPlaying(true);
  };

  // Handle next song
  const handleNextSong = () => {
    if (currentPlaylist.length === 0) return;
    const newIndex = (currentIndex + 1) % currentPlaylist.length;
    setCurrentIndex(newIndex);
    const song = currentPlaylist[newIndex];
    setCurrentSong({
      id: song.id,
      title: song.title,
      artist: song.artist,
      album: song.album,
      duration: song.duration || 180,
      currentTime: 0,
      audio_path: song.audio_path || "",
      preview_url: song.preview_url || "",
      album_art: song.album_art || ""
    });
    setIsPlaying(true);
  };

  // Format time (seconds to MM:SS)
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Calculate progress percentage
  const progressPercentage = (currentSong.currentTime / currentSong.duration) * 100;

  return (
    <div className="app">
      {/* Audio element for music playback */}
      <audio
        ref={audioRef}
        src={currentSong.preview_url || (currentSong.audio_path ? `/audio/${currentSong.audio_path}` : '')}
        preload="metadata"
      />

      {/* Audio element for TTS playback */}
      <audio
        ref={audioPlayerRef}
        onEnded={() => setIsSpeaking(false)}
        onError={() => setIsSpeaking(false)}
      />

      <header className="header">
        <div className="header-left">
          <h1>Claudio</h1>
          <p>智能音乐代理</p>
        </div>
        <div className="header-buttons">
          <button
            className={`manager-btn ${ttsEnabled ? 'active' : ''}`}
            onClick={() => setTtsEnabled(!ttsEnabled)}
            title={ttsEnabled ? '关闭语音' : '开启语音'}
          >
            {ttsEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
          </button>
          <button
            className="manager-btn"
            onClick={() => setShowNeteaseSearch(!showNeteaseSearch)}
            title="搜索网易云音乐"
          >
            <Search size={20} />
          </button>
          <button
            className="manager-btn"
            onClick={() => setShowManager(!showManager)}
            title="歌曲管理"
          >
            <Settings size={20} />
          </button>
        </div>
        <div className="tts-controls">
          <select
            className="voice-select"
            value={selectedVoiceId}
            onChange={(e) => setSelectedVoiceId(e.target.value)}
            disabled={voiceList.length === 0}
          >
            {voiceList.map(voice => (
              <option key={voice.voice_id} value={voice.voice_id}>
                {voice.name}
              </option>
            ))}
          </select>
          {isSpeaking && <span className="speaking-indicator">🔊 说话中...</span>}
        </div>
      </header>

      <main className="main-content">
        {showNeteaseSearch ? (
          <div className="netease-search">
            <div className="search-header">
              <h2>搜索网易云音乐</h2>
              <button
                className="close-btn"
                onClick={() => setShowNeteaseSearch(false)}
              >
                ✕
              </button>
            </div>

            <div className="search-input-container">
              <input
                type="text"
                placeholder="搜索歌曲、歌手..."
                value={neteaseSearchQuery}
                onChange={(e) => setNeteaseSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && searchNetease()}
                className="search-input"
              />
              <button
                className="search-btn"
                onClick={searchNetease}
                disabled={isSearchingNetease}
              >
                {isSearchingNetease ? '搜索中...' : '搜索'}
              </button>
            </div>

            <div className="search-results">
              <div className="search-results-header">
                <span>找到 {neteaseSearchResults.length} 首歌曲</span>
                {neteaseSearchResults.length > 0 && (
                  <button
                    className="import-all-btn"
                    onClick={importAllTracks}
                    disabled={isImporting}
                  >
                    {isImporting ? '导入中...' : '全部导入到本地库'}
                  </button>
                )}
              </div>
              {neteaseSearchResults.map((track) => (
                <div key={track.id} className="search-result-item">
                  {track.album_art && (
                    <img
                      src={track.album_art}
                      alt={track.album}
                      className="album-art-small"
                    />
                  )}
                  <div className="track-info">
                    <h4>{track.title}</h4>
                    <p>{track.artist.join(', ')}</p>
                    <p className="album-name">{track.album}</p>
                  </div>
                  <div className="track-actions">
                    <button
                      className="play-btn"
                      onClick={() => playNeteaseTrack(track)}
                      title="播放"
                    >
                      <Play size={16} />
                    </button>
                    <button
                      className="add-btn"
                      onClick={() => addNeteaseTrackToLibrary(track)}
                      title="添加到本地库"
                    >
                      <Plus size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="library-stats">
              <h4>本地库统计</h4>
              <p>歌曲: {libraryStats.songs} | 歌单: {libraryStats.playlists} | 历史: {libraryStats.listening_history}</p>
            </div>
          </div>
        ) : showManager ? (
          <SongManager
            onClose={() => setShowManager(false)}
            onRefresh={() => fetchRecommendations()}
          />
        ) : (
          <>
        {/* Player Section */}
        <section className="player-section">
          <h2>音乐播放器</h2>

          <div className="current-song">
            {currentSong.album_art ? (
              <img
                src={currentSong.album_art}
                alt={currentSong.album}
                className="album-art-image"
              />
            ) : (
              <div className="album-art">🎵</div>
            )}
            <h3>{currentSong.title}</h3>
            <p>{currentSong.artist.join(', ')}</p>
          </div>

          <div className="player-controls">
            <button className="control-btn" onClick={handlePreviousSong}>
              <SkipBack size={24} />
            </button>
            <button
              className="control-btn play"
              onClick={() => setIsPlaying(!isPlaying)}
            >
              {isPlaying ? <Pause size={32} /> : <Play size={32} />}
            </button>
            <button className="control-btn" onClick={handleNextSong}>
              <SkipForward size={24} />
            </button>
          </div>

          <div className="progress-bar">
            <div
              className="progress"
              style={{ width: `${progressPercentage}%` }}
            ></div>
          </div>

          <div className="time-info">
            <span>{formatTime(currentSong.currentTime)}</span>
            <span>{formatTime(currentSong.duration)}</span>
          </div>
        </section>

        {/* Chat Section */}
        <section className="chat-section">
          <h2>与 Claudio 聊天</h2>

          <div className="chat-messages">
            {messages.map(message => (
              <div
                key={message.id}
                className={`message ${message.sender === 'user' ? 'user-message' : 'claudio-message'}`}
              >
                <div className="message-content">{message.content}</div>
                <div className="message-time">{message.time}</div>
              </div>
            ))}
            {isLoading && (
              <div className="message claudio-message">
                <div className="message-content">Claudio 正在思考...</div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input">
            <input
              type="text"
              placeholder="输入消息..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            />
            <button onClick={handleSendMessage} disabled={isLoading}>
              <Send size={20} />
            </button>
          </div>

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <div className="recommendations">
              <h3>推荐歌曲</h3>
              <ul className="recommendation-list">
                {recommendations.map((song, index) => (
                  <li
                    key={song.id}
                    className="recommendation-item"
                    onClick={() => handleSelectRecommendation(song)}
                  >
                    <h4>{song.title}</h4>
                    <p>{song.artist.join(', ')}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
        </>
      )}
      </main>
    </div>
  );
}

export default App;
