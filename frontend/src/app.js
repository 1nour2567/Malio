/* ================================================================
   Malio AI Radio — Fullscreen Player App Logic
   Vanilla HTML5 / CSS / JS — zero framework dependency
   ================================================================ */

/* ── State ──────────────────────────────────────────────────── */
const state = {
  currentSong: {
    id: '', title: '—', artist: ['准备播放'],
    album: '', duration: 0, currentTime: 0,
    audioPath: '', previewUrl: '', albumArt: ''
  },
  isPlaying: false,
  playlist: [],
  playlistIndex: 0,
  messages: [],
  recommendations: [],
  ttsEnabled: true,
  autoPlayEnabled: true,
  ttsVoices: [],
  selectedVoiceId: 'CwhRBWXzGAHq8TQ4Fs17',
  isSpeaking: false,
  lastSnapshotSeq: 0,           /* reject stale snapshots */
  libraryStats: { songs: 0, playlists: 0, listening_history: 0 },
  /* panel state */
  activePanel: null,           /* 'chat' | 'search' | null */
  /* ── identity ──────────────────────────────────────────── */
  userId: localStorage.getItem('malio_user_id') || (function () {
    var id = 'u_' + Math.random().toString(36).slice(2, 10);
    localStorage.setItem('malio_user_id', id);
    return id;
  }())
};

/* ── DOM refs ────────────────────────────────────────────────── */
const dom = {};

function cacheDom () {
  const g = (id) => document.getElementById(id);
  const q = (sel) => document.querySelector(sel);

  /* Player */
  dom.audioPlayer        = g('audio-player');
  dom.ttsPlayer          = g('tts-player');
  dom.albumArtPlaceholder = g('album-art-placeholder');
  dom.albumArtImg        = g('album-art-img');
  dom.songTitle          = g('song-title');
  dom.songArtist         = g('song-artist');
  dom.songAlbum          = g('song-album');
  dom.progressBar        = g('progress-bar');
  dom.progressFill       = g('progress-fill');
  dom.progressThumb      = g('progress-thumb');
  dom.timeElapsed        = g('time-elapsed');
  dom.timeTotal          = g('time-total');
  dom.iconPlay           = g('icon-play');
  dom.iconPause          = g('icon-pause');
  dom.volumeSlider       = g('volume-slider');

  /* Buttons */
  dom.btnMenu            = g('btn-menu');
  dom.btnPlay            = g('btn-play');
  dom.btnPrev            = g('btn-prev');
  dom.btnNext            = g('btn-next');
  dom.btnSend            = g('btn-send');
  dom.btnTtsToggle       = g('btn-tts-toggle');
  dom.btnAutoPlay        = g('btn-autoplay-toggle');
  dom.btnSearchToggle    = g('btn-search-toggle');

  /* Chat */
  dom.chatMessages       = g('chat-messages');
  dom.chatInput          = g('chat-input');
  dom.chatLoading        = g('chat-loading');
  dom.chatPanel          = g('chat-panel');
  dom.chatInputWrap      = q('.chat-input-wrap');

  /* Search */
  dom.searchPanel        = g('search-panel');
  dom.searchInput        = g('search-input');
  dom.searchResults      = g('search-results');
  dom.searchResultCount  = g('search-result-count');
  dom.searchResultsHeader = g('search-results-header');
  dom.btnSearch          = g('btn-search');
  dom.btnImportAll       = g('btn-import-all');

  /* Manager / Memory Corridor */
  dom.libraryPanel       = g('library-panel');
  dom.songList           = g('song-list');
  dom.sceneList          = g('scene-list');
  dom.playlistList       = g('playlist-list');
  dom.allSongsToggle     = g('all-songs-toggle');
  dom.allSongsCount      = g('all-songs-count');
  dom.btnNewPlaylist     = g('btn-new-playlist');
  dom.addSongForm        = g('add-song-form');
  dom.btnShowAddForm     = g('btn-show-add-form');
  dom.btnCancelForm      = g('btn-cancel-form');

  /* TTS */
  dom.voiceSelect        = g('voice-select');
  dom.speakingIndicator  = g('speaking-indicator');

  /* Agent log */
  dom.agentLog           = g('agent-log');

  /* Player panel / card */
  dom.playerPanel        = g('player-panel');

  /* Close buttons */
  dom.btnSearchClose     = g('btn-search-close');
  dom.btnChatToggle      = g('btn-chat-toggle');
  dom.btnChatClose       = g('btn-chat-close');
  dom.btnManagerToggle   = g('btn-settings-toggle');
  dom.btnManagerClose    = g('btn-library-close');

  /* Pin button for agent log */
  dom.btnAgentLogPin     = g('btn-agent-log-pin');
}

/* ── Init ────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  cacheDom();
  setInitTime();
  loadVoices();
  fastLoadInitialSong();
  fetchLibraryStats();
  bindEvents();
  setupWsClient();
  fetchSessionResume();
  initAudioReactivity();
  initParticleRules();
  startParticleMood();
  initIdleTimer();
  injectSongLibrary();
  loadSongList();  // preload for library panel
  loadCorridor();  // load playlists + scene section

  /* ── 30s heartbeat: state consistency check ────────────────── */
  setInterval(function () {
    if (wsClient && state.currentSong && state.currentSong.id) {
      wsClient.sendGuaranteed({
        action: 'heartbeat',
        user_id: state.userId,
        current_song_id: state.currentSong.id,
        is_playing: state.isPlaying,
        playlist_index: state.playlistIndex
      });
    }
  }, 30000);

  if (typeof engine !== 'undefined') {
    engine.onTimeWarp = function (active) {
      if (active) {
        if (dom.audioPlayer) dom.audioPlayer.pause();
        state.isPlaying = false;
      } else {
        if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
        state.isPlaying = true;
      }
      if (wsClient) wsClient.sendCoreEvent('time_warp', { active: active });
    };
  }
});

// Set swipe handler immediately (outside DOMContentLoaded) so it's always ready
if (typeof engine !== 'undefined') {
  var _swipeBusy = false;
  engine.onSwipe = function (dir) {
    if (_swipeBusy) return;
    _swipeBusy = true;
    setTimeout(function () { _swipeBusy = false; }, 800);
    if (dir === 'right') {
      if (typeof nextSong === 'function') nextSong();
    } else {
      if (typeof prevSong === 'function') prevSong();
    }
  };

  /* search mode */
  engine.onSearchStart = function () {
    var existing = document.getElementById('search-ball-input');
    if (existing) { existing.remove(); }
    var topBar = document.getElementById('top-bar');
    if (!topBar) return;
    var input = document.createElement('input');
    input.id = 'search-ball-input';
    input.type = 'text';
    input.placeholder = '搜索音乐...';
    input.autocomplete = 'off';
    input.style.cssText = 'width:140px;height:28px;border:1px solid var(--accent-border);border-radius:14px;padding:0 12px;background:var(--bg-glass);color:#fff;font-size:13px;outline:none;margin-left:8px;';
    input.addEventListener('input', function () {
      if (typeof engine !== 'undefined') engine.updateSearchInput(this.value.length);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { executeSearch(this.value); }
      if (e.key === 'Escape') { cancelSearch(input); }
    });
    topBar.appendChild(input);
    setTimeout(function () { input.focus(); }, 100);
  };
  engine.onSearchEnd = function () {
    var input = document.getElementById('search-ball-input');
    if (input) input.remove();
  };
  engine.onSearchCollapse = function () {
    var input = document.getElementById('search-ball-input');
    var query = input ? input.value.trim() : '';
    if (input) input.remove();
    if (query) executeSearch(query);
  };

  function executeSearch (query) {
    if (typeof engine !== 'undefined' && engine._searchMode) engine.endSearch();
    if (query && typeof searchNetease === 'function') {
      var si = document.getElementById('search-input');
      if (si) { si.value = query; searchNetease(); }
      /* open search panel to show results */
      togglePanel('search');
    }
  }
  function cancelSearch (input) {
    if (typeof engine !== 'undefined') engine.endSearch();
    if (input) input.remove();
  }

  engine.onCaptureComplete = function (capturedSongs) {
    if (!capturedSongs || !capturedSongs.length) return;
    if (wsClient) wsClient.sendCoreEvent('nebula_capture', { count: capturedSongs.length });
    // Show confirm bar before generating playlist
    var names = capturedSongs.map(function(s) { return s.title || '?' ; }).slice(0, 3).join('、');
    if (capturedSongs.length > 3) names += '等' + capturedSongs.length + '首';
    var defaultName = '星云捕获 · ' + (capturedSongs[0] ? (capturedSongs[0].title || '未命名') : '未命名');
    state._pendingCapture = capturedSongs;
    showConfirmBar('✨ 捕获 ' + names + '，要创建歌单吗？', function (playlistName) {
      var songs = state._pendingCapture;
      state._pendingCapture = null;
      var name = playlistName || defaultName;
      fetch('/api/playlists/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ captured_songs: songs, name: name })
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.playlist_name) {
          showToast('歌单「' + data.playlist_name + '」已生成（' + data.total + ' 首）');
          loadCorridor(); // refresh playlist panel
        }
      })
      .catch(function(err) { console.error('Capture error:', err); showToast('歌单生成失败，请重试'); });
    }, function () {
      state._pendingCapture = null; // cancelled
    });
  };

  // Reverse embodiment: core drag release → music zone intent
  // Rule feedback loop: report rule health back to LLM via WebSocket
  engine.onRuleFeedback = function (rules) {
    if (wsClient && rules && rules.length) {
      wsClient.sendCoreEvent('rule_feedback', { rules: rules });
    }
  };

  engine.onCoreRelease = function (pos) {
    var w = window.innerWidth, h = window.innerHeight;
    var rx = pos.rx, ry = pos.ry;
    var zone = '';
    var mood = '';
    // Determine dominant zone: horizontal or vertical
    if (Math.abs(rx) > Math.abs(ry)) {
      zone = rx > 0 ? 'warm' : 'cool';
    } else {
      zone = ry < 0 ? 'energy' : 'calm';
    }
    // Map zone to music mood
    var moodMap = {
      warm:   { label: '温暖', prompt: '推荐一首温暖治愈的歌' },
      cool:   { label: '冷静', prompt: '推荐一首安静放松的纯音乐' },
      energy: { label: '高能', prompt: '推荐一首嗨到爆的电音' },
      calm:   { label: '舒缓', prompt: '推荐一首舒缓的慢歌' }
    };
    var mapping = moodMap[zone];
    if (!mapping) return;
    showToast('✨ 内核释放到' + mapping.label + '区，切换氛围...');
    // Send to backend as chat message for full pipeline processing
    if (wsClient) wsClient.sendCoreEvent('core_release', { zone: zone, rx: rx, ry: ry });
    // Trigger song recommendation matching the zone
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.userId, input: mapping.prompt })
    }).then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.response) addChatMessage('Malio', data.response);
      if (data.recommendations && data.recommendations.length) {
        state.recommendations = data.recommendations;
        state.playlist = data.recommendations;
        state.playlistIndex = 0;
        if (data.auto_play !== false && data.recommendations[0]) {
          setCurrentSong(data.recommendations[0]);
          state.isPlaying = true;
          updatePlayIcon();
          if (dom.audioPlayer) dom.audioPlayer.play().catch(function(){});
        }
      }
    }).catch(function(err) { console.error('Core release error:', err); });
  };
}

function setInitTime () {
  const t = new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit'
  });
  const el = document.getElementById('msg-init-time');
  if (el) el.textContent = t;
}

/* ── Event Bindings ──────────────────────────────────────────── */
function bindEvents () {
  /* Player */
  if (dom.btnPlay)   dom.btnPlay.addEventListener('click', togglePlay);
  if (dom.btnPrev)   dom.btnPrev.addEventListener('click', prevSong);
  if (dom.btnNext)   dom.btnNext.addEventListener('click', nextSong);

  if (dom.volumeSlider) {
    dom.volumeSlider.addEventListener('input', function (e) {
      dom.audioPlayer.volume = e.target.value / 100;
    });
    dom.volumeSlider.addEventListener('change', function (e) {
      if (wsClient) wsClient.sendCoreEvent('volume_change', { to: parseInt(e.target.value) });
    });
    dom.audioPlayer.volume = dom.volumeSlider.value / 100;
  }

  /* Progress bar click-to-seek */
  if (dom.progressBar) {
    dom.progressBar.addEventListener('click', function (e) {
      const rect = dom.progressBar.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      dom.audioPlayer.currentTime = ratio * (dom.audioPlayer.duration || state.currentSong.duration);
    });
  }

  /* Audio events */
  if (dom.audioPlayer) {
    dom.audioPlayer.addEventListener('timeupdate', updateProgress);
    dom.audioPlayer.addEventListener('loadedmetadata', function () {
      state.currentSong.duration = dom.audioPlayer.duration;
      updateProgress();
    });
    dom.audioPlayer.addEventListener('ended', function () {
      state.isPlaying = false;
      updatePlayIcon();
      nextSong('ended');
    });
    dom.audioPlayer.addEventListener('play', function () {
      state.isPlaying = true;
      updatePlayIcon();
    });
    dom.audioPlayer.addEventListener('pause', function () {
      state.isPlaying = false;
      updatePlayIcon();
    });
    dom.audioPlayer.addEventListener('error', function () {
      state.isPlaying = false;
      updatePlayIcon();
      refreshExpiredUrl();
    });
  }

  /* TTS player */
  if (dom.ttsPlayer) {
    dom.ttsPlayer.addEventListener('ended', function () {
      state.isSpeaking = false;
      if (dom.speakingIndicator) dom.speakingIndicator.hidden = true;
    });
  }

  /* Chat */
  if (dom.btnSend)   dom.btnSend.addEventListener('click', sendMessage);
  if (dom.chatInput) {
    dom.chatInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') sendMessage();
    });
  }

  /* Toggle buttons */
  if (dom.btnTtsToggle)    dom.btnTtsToggle.addEventListener('click', toggleTts);
  if (dom.btnAutoPlay)     dom.btnAutoPlay.addEventListener('click', toggleAutoPlay);

  /* Hide player */
  var btnHide = document.getElementById('btn-hide-player');
  if (btnHide) btnHide.addEventListener('click', function () {
    document.body.classList.toggle('player-hidden');
    btnHide.classList.toggle('active', document.body.classList.contains('player-hidden'));
  });
  /* Menu button: open library panel */
  if (dom.btnMenu) dom.btnMenu.addEventListener('click', function () {
    togglePanel('library');
  });

  /* Panel toggles */
  if (dom.btnSearchToggle) dom.btnSearchToggle.addEventListener('click', function () {
    togglePanel('search');
  });
  if (dom.btnSearchClose)  dom.btnSearchClose.addEventListener('click', function () {
    togglePanel('search');
  });

  /* Chat toggle */
  if (dom.btnChatToggle)   dom.btnChatToggle.addEventListener('click', function () {
    togglePanel('chat');
  });
  if (dom.btnChatClose)    dom.btnChatClose.addEventListener('click', function () {
    togglePanel('chat');
  });

  if (dom.btnManagerToggle) dom.btnManagerToggle.addEventListener('click', function () {
    togglePanel('library');
  });
  if (dom.btnManagerClose)  dom.btnManagerClose.addEventListener('click', function () {
    togglePanel('library');
  });

  /* All songs toggle */
  if (dom.allSongsToggle) dom.allSongsToggle.addEventListener('click', function () {
    var list = dom.songList;
    var arrow = dom.allSongsToggle.querySelector('.expand-arrow');
    if (list) {
      list.hidden = !list.hidden;
      if (arrow) {
        arrow.classList.toggle('open', !list.hidden);
      }
    }
  });

  /* New playlist button */
  if (dom.btnNewPlaylist) dom.btnNewPlaylist.addEventListener('click', function () {
    var name = prompt('歌单名称：');
    if (!name || !name.trim()) return;
    fetch('/api/playlists', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), playlist_type: 'manual' })
    })
    .then(function (r) { return r.json(); })
    .then(function () { loadCorridor(); })
    .catch(function (err) { console.error('Create playlist error:', err); });
  });

  /* Search */
  if (dom.btnSearch) {
    dom.btnSearch.addEventListener('click', searchNetease);
  }
  if (dom.searchInput) {
    dom.searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') searchNetease();
    });
  }
  if (dom.btnImportAll) dom.btnImportAll.addEventListener('click', importAllTracks);

  /* Song manager */
  if (dom.btnShowAddForm) {
    dom.btnShowAddForm.addEventListener('click', function () {
      if (dom.addSongForm) dom.addSongForm.hidden = !dom.addSongForm.hidden;
    });
  }
  if (dom.btnCancelForm) {
    dom.btnCancelForm.addEventListener('click', function () {
      if (dom.addSongForm) dom.addSongForm.hidden = true;
    });
  }
  if (dom.addSongForm) {
    dom.addSongForm.addEventListener('submit', addSong);
  }

  /* Agent log pin */
  if (dom.btnAgentLogPin) {
    dom.btnAgentLogPin.addEventListener('click', function () {
      if (dom.agentLog) dom.agentLog.classList.toggle('pinned');
    });
  }
}

/* ═══════════════════════════════════════════════════════════════
   PANEL TOGGLING
   ═══════════════════════════════════════════════════════════════ */

function togglePanel (name) {
  const panels = {
    chat:    dom.chatPanel,
    search:  dom.searchPanel,
    library: dom.libraryPanel
  };

  const panel = panels[name];

  /* If no panel was found, bail silently */
  if (!panel) { console.warn('[togglePanel] panel not found:', name); return; }

  const isCurrentlyOpen = state.activePanel === name;
  console.log('[togglePanel]', name, 'isCurrentlyOpen:', isCurrentlyOpen, 'panel.hidden:', panel.hidden);

  /* Close any open panel first */
  closeAllPanels();

  if (!isCurrentlyOpen) {
    /* Open this panel */
    panel.hidden = false;
    state.activePanel = name;

    /* Focus input for search/chat */
    if (name === 'search' && dom.searchInput) {
      dom.searchInput.focus();
    } else if (name === 'chat' && dom.chatInput) {
      dom.chatInput.focus();
    } else if (name === 'library') {
      loadCorridor();
    }

    /* Update toggle button active state */
    const toggleBtn = name === 'search' ? dom.btnSearchToggle : dom.btnChatToggle;
    if (toggleBtn) toggleBtn.classList.add('active');
  } else {
    state.activePanel = null;
  }

  /* If chat is open, scroll to bottom after layout settles */
  if (name === 'chat' && dom.chatMessages) {
    requestAnimationFrame(function () {
      dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    });
  }
}

function closeAllPanels () {
  if (dom.chatPanel)    dom.chatPanel.hidden = true;
  if (dom.searchPanel)  dom.searchPanel.hidden = true;
  if (dom.libraryPanel) dom.libraryPanel.hidden = true;

  if (dom.btnSearchToggle) dom.btnSearchToggle.classList.remove('active');
  if (dom.btnChatToggle)   dom.btnChatToggle.classList.remove('active');

  state.activePanel = null;
}

/* ═══════════════════════════════════════════════════════════════
   PLAYER
   ═══════════════════════════════════════════════════════════════ */

function togglePlay () {
  if (!state.currentSong.previewUrl && !state.currentSong.audioPath) return;
  if (state.isPlaying) {
    dom.audioPlayer.pause();
    if (wsClient) wsClient.sendCoreEvent('pause', { song_id: state.currentSong.id, title: state.currentSong.title });
  } else {
    dom.audioPlayer.play().catch(function () {});
    if (wsClient) wsClient.sendCoreEvent('play', { song_id: state.currentSong.id, title: state.currentSong.title });
  }
}

function updatePlayIcon () {
  if (dom.iconPlay)  dom.iconPlay.hidden = state.isPlaying;
  if (dom.iconPause) dom.iconPause.hidden = !state.isPlaying;
}

function updateProgress () {
  const current = dom.audioPlayer.currentTime || 0;
  const dur = dom.audioPlayer.duration;
  const duration = (dur && isFinite(dur) && dur > 0)
    ? dur
    : (state.currentSong.duration > 0 ? state.currentSong.duration : 180);
  const pct = Math.min((current / duration) * 100, 100);

  if (dom.progressFill)  dom.progressFill.style.width = pct + '%';
  if (dom.progressThumb) dom.progressThumb.style.left = pct + '%';
  if (dom.timeElapsed)   dom.timeElapsed.textContent = formatTime(current);
  if (dom.timeTotal)     dom.timeTotal.textContent = formatTime(duration);

  state.currentSong.currentTime = current;
}

function formatTime (sec) {
  if (!sec || !isFinite(sec) || sec < 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m + ':' + s.toString().padStart(2, '0');
}

function ewdToShape (energy, warmth, density) {
  if (energy > 0.8 && density > 0.6) return 'swirl';         // intense + complex → psychedelic
  if (energy > 0.75 && warmth > 0.6) return 'pulse_ring';    // warm banger
  if (energy > 0.7) return 'star';                            // high energy
  if (warmth > 0.7 && energy < 0.5) return 'drop';            // tender & low-energy → teardrop
  if (warmth > 0.6) return 'bloom';                           // warm → petal/flower
  if (density > 0.7) return 'hexagon';                        // complex/rich
  if (density < 0.35) return 'circle';                        // minimal/sparse
  return 'diamond';                                            // balanced pop
}

function setCurrentSong (song) {
  /* trigger DSL rules */
  if (particleRules) particleRules.triggerEvent('song_change');

  state.currentSong = {
    id:         song.id || '',
    title:      song.title || '—',
    artist:     song.artist || ['—'],
    album:      song.album || '',
    duration:   song.duration || 180,
    currentTime: 0,
    audioPath:  song.audio_path || '',
    previewUrl: song.preview_url || '',
    albumArt:   song.album_art || ''
  };

  if (dom.songTitle)  dom.songTitle.textContent = state.currentSong.title;
  if (dom.songArtist) {
    dom.songArtist.textContent = Array.isArray(state.currentSong.artist)
      ? state.currentSong.artist.join(', ')
      : state.currentSong.artist;
  }
  if (dom.songAlbum)  dom.songAlbum.textContent = state.currentSong.album;

  /* Album art + extract cover color */
  if (state.currentSong.albumArt) {
    if (dom.albumArtImg) {
      dom.albumArtImg.crossOrigin = 'anonymous';
      dom.albumArtImg.src = state.currentSong.albumArt;
      dom.albumArtImg.hidden = false;
      /* extract dominant color on load */
      dom.albumArtImg.onload = function () {
        var coverColor = typeof extractDominantColor === 'function'
          ? extractDominantColor(dom.albumArtImg) : null;
        if (coverColor && typeof engine !== 'undefined') {
          engine._coverColor = coverColor;
          engine._coverSetAt = performance.now();
          engine.triggerLightBurst(coverColor);
          engine.updateParams({ color: coverColor }, 0.12);
        }
      };
    }
    if (dom.albumArtPlaceholder) dom.albumArtPlaceholder.hidden = true;
  } else {
    if (dom.albumArtImg) dom.albumArtImg.hidden = true;
    if (dom.albumArtPlaceholder) dom.albumArtPlaceholder.hidden = false;
  }

  /* Audio source */
  const src = state.currentSong.previewUrl
    || (state.currentSong.audioPath ? '/audio/' + state.currentSong.audioPath : '');
  if (src && dom.audioPlayer) {
    dom.audioPlayer.src = src;
    dom.audioPlayer.load();
    if (state.isPlaying) dom.audioPlayer.play().catch(function () {});
  }

  /* ── Immediate color from E/W/D on song change ───────── */
  if (typeof engine !== 'undefined') {
    var ew = song.energy != null ? song.energy : 0.5;
    var wm = song.warmth != null ? song.warmth : 0.5;
    var dn = song.density != null ? song.density : 0.5;
    // Feed current E/W/D to capture filter
    if (typeof engine.setCurrentSongEWD === 'function') engine.setCurrentSongEWD(ew, wm, dn);
    // HSL: energy→hue (240→0), warmth→sat (30%→90%), density→light (75%→25%)
    var h = Math.round(240 - ew * 240);  // 240°=blue(cold), 0°=red(hot)
    var s = Math.round(30 + wm * 60);     // 30%=muted, 90%=vivid
    var l = Math.round(75 - dn * 50);      // 75%=bright, 25%=dark
    var ewColor = hslToHex(h, s, l);
    state._ewdColor = ewColor;
    engine._coverSetAt = performance.now();
    engine.updateParams({ amplitude: Math.min(2.5, (engine.params.amplitude || 1) + 0.6) }, 0.06);
    // Auto-morph core shape from E/W/D
    if (typeof engine.setShape === 'function') {
      engine.setShape(ewdToShape(ew, wm, dn));
    }
    clearTimeout(state._colorTimer);
    state._colorTimer = setTimeout(function () {
      // Blend all sources, push to nebula too
      var blended = blendAllColors();
      var light = lightenColor(blended, 0.45);
      if (typeof engine !== 'undefined') {
        engine.updateParams({ color: light }, 0.065);
        if (engine._nebula && engine._nebula.particles) {
          var r = parseInt(blended.slice(1,3),16), g = parseInt(blended.slice(3,5),16), b = parseInt(blended.slice(5,7),16);
          for (var ni = 0; ni < engine._nebula.particles.length; ni++) {
            var p = engine._nebula.particles[ni];
            if (!p._rgb) p._rgb = {r:r, g:g, b:b};
            p._rgb.r = Math.round(p._rgb.r + (r - p._rgb.r) * 0.3);
            p._rgb.g = Math.round(p._rgb.g + (g - p._rgb.g) * 0.3);
            p._rgb.b = Math.round(p._rgb.b + (b - p._rgb.b) * 0.3);
          }
        }
      }
    }, 700);
    clearTimeout(state._ampReset);
    state._ampReset = setTimeout(function () {
      if (typeof engine !== 'undefined') {
        engine.updateParams({ amplitude: 0.4 });
      }
    }, 800);
  }
}

function prevSong () {
  if (state.playlist.length === 0) return;
  state.playlistIndex = (state.playlistIndex - 1 + state.playlist.length) % state.playlist.length;
  var song = state.playlist[state.playlistIndex];
  if (typeof engine !== 'undefined' && engine.triggerLightBurst) {
    engine.triggerLightBurst('#22C55E');
  }
  setCurrentSong(song);
  state.isPlaying = true;
  if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
}

var _lastSkipTime = 0;

function nextSong (skipSource) {
  /* Debounce: ignore calls within 800ms to prevent ABA double-skip */
  var now = performance.now();
  if (now - _lastSkipTime < 800) return;
  _lastSkipTime = now;

  /* advance locally immediately, backend syncs asynchronously */
  if (state.playlist.length > 0) {
    state.playlistIndex = (state.playlistIndex + 1) % state.playlist.length;
    setCurrentSong(state.playlist[state.playlistIndex]);
    state.isPlaying = true;
    if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
  }
  if (wsClient) {
    var source = skipSource || 'user';
    if (window._songBroken) { source = 'broken'; window._songBroken = false; }
    var detail = { direction: 'right', source: source };
    if (source === 'broken') detail.reason = 'broken_url';
    wsClient.sendCoreEvent('song_skip', detail);
  }
  if (typeof engine !== 'undefined' && engine.triggerLightBurst) {
    engine.triggerLightBurst('#22C55E');
  }
}

function _applySongFromWS (song) {
  setCurrentSong(song);
  state.isPlaying = true;
  updatePlayIcon();
  if (dom.audioPlayer) {
    dom.audioPlayer.load();
    dom.audioPlayer.play().catch(function () {});
  }
}

/* Refresh expired NetEase URL */
let _refreshInProgress = false;
async function refreshExpiredUrl () {
  const songId = state.currentSong.id;
  if (!songId || _refreshInProgress) return;

  _refreshInProgress = true;
  var refreshed = false;
  try {
    if (/^\d{4,}$/.test(songId)) {
      const res = await fetch('/api/netease/track/' + songId + '/url');
      const data = await res.json();
      if (data.url) {
        state.currentSong.previewUrl = data.url;
        if (dom.audioPlayer) {
          dom.audioPlayer.src = data.url;
          dom.audioPlayer.load();
          dom.audioPlayer.play().catch(function () {});
        }
        refreshed = true;
      }
    }
  } catch (err) {
    console.error('Failed to refresh URL:', err);
  } finally {
    _refreshInProgress = false;
  }

  // If refresh failed, mark as broken then skip
  if (!refreshed) {
    console.warn('Song unavailable, auto-skipping to next');
    _songBroken = true;
    setTimeout(function () { nextSong(); }, 500);
  }
}

/* ═══════════════════════════════════════════════════════════════
   CHAT
   ═══════════════════════════════════════════════════════════════ */

async function sendMessage () {
  const text = dom.chatInput.value.trim();
  if (!text) return;

  addMessage(text, 'user');
  dom.chatInput.value = '';
  if (dom.chatLoading) dom.chatLoading.hidden = false;
  if (dom.btnSend) dom.btnSend.disabled = true;
  /* unlock audio — browser requires user gesture for play() */
  if (dom.audioPlayer && dom.audioPlayer.paused) {
    dom.audioPlayer.play().then(function () { dom.audioPlayer.pause(); dom.audioPlayer.currentTime = 0; }).catch(function () {});
  }

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: state.userId, input: text })
    });
    const data = await res.json();

    addMessage(data.response, 'malio');

    if (data.recommendations && data.recommendations.length > 0) {
      state.recommendations = data.recommendations;
      state.playlist = data.recommendations;
      state.playlistIndex = 0;
      if (data.auto_play && data.recommendations[0]) {
        _applySongFromWS(data.recommendations[0]);
      }
    }

    if (state.ttsEnabled) playTTS(data.response);
  } catch (err) {
    console.error('Chat error:', err);
    addMessage('抱歉，我遇到了一些问题，请稍后再试。', 'malio');
  } finally {
    if (dom.chatLoading) dom.chatLoading.hidden = true;
    if (dom.btnSend) dom.btnSend.disabled = false;
    if (dom.chatMessages) {
      dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    }
  }
}

function addMessage (text, sender) {
  const msg = {
    id: Date.now(),
    content: text,
    sender: sender,
    time: new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit', minute: '2-digit'
    })
  };
  state.messages.push(msg);

  const div = document.createElement('div');
  div.className = 'msg msg-' + (sender === 'user' ? 'user' : 'malio');

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = sender === 'user' ? 'U' : 'M';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = '<p>' + escapeHtml(text).replace(/\n/g, '<br>') + '</p>';

  const timeSpan = document.createElement('span');
  timeSpan.className = 'msg-time';
  timeSpan.textContent = msg.time;
  bubble.appendChild(timeSpan);

  div.appendChild(avatar);
  div.appendChild(bubble);

  if (dom.chatMessages) {
    dom.chatMessages.appendChild(div);
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
  }
}

function escapeHtml (s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* ═══════════════════════════════════════════════════════════════
   TTS
   ═══════════════════════════════════════════════════════════════ */

async function loadVoices () {
  try {
    const res = await fetch('/api/tts/voices');
    const data = await res.json();
    if (data.voices) {
      state.ttsVoices = data.voices;
      if (dom.voiceSelect) {
        dom.voiceSelect.innerHTML = data.voices
          .map(function (v) {
            return '<option value="' + v.voice_id + '">' + v.name + '</option>';
          })
          .join('');
        if (data.voices.length > 0) state.selectedVoiceId = data.voices[0].voice_id;
        dom.voiceSelect.value = state.selectedVoiceId;
      }
    }
  } catch (err) {
    console.error('Failed to load voices:', err);
  }
  if (dom.voiceSelect) {
    dom.voiceSelect.addEventListener('change', function (e) {
      state.selectedVoiceId = e.target.value;
    });
  }
}

async function playTTS (text) {
  if (!text || !state.ttsEnabled) return;
  try {
    state.isSpeaking = true;
    if (dom.speakingIndicator) dom.speakingIndicator.hidden = false;

    const res = await fetch('/api/tts/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, voice_id: state.selectedVoiceId })
    });
    if (!res.ok) throw new Error('TTS failed');

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    if (dom.ttsPlayer) {
      dom.ttsPlayer.src = url;
      dom.ttsPlayer.play().catch(function () {});
    }
  } catch (err) {
    console.error('TTS error:', err);
    state.isSpeaking = false;
    if (dom.speakingIndicator) dom.speakingIndicator.hidden = true;
  }
}

function toggleTts () {
  state.ttsEnabled = !state.ttsEnabled;

  if (dom.btnTtsToggle) {
    dom.btnTtsToggle.classList.toggle('active', state.ttsEnabled);
  }

  if (!state.ttsEnabled) {
    if (dom.ttsPlayer) dom.ttsPlayer.pause();
    state.isSpeaking = false;
    if (dom.speakingIndicator) dom.speakingIndicator.hidden = true;
  }
}

function toggleAutoPlay () {
  state.autoPlayEnabled = !state.autoPlayEnabled;
  if (dom.btnAutoPlay) {
    dom.btnAutoPlay.classList.toggle('active', state.autoPlayEnabled);
  }
}

function lightenColor (hex, factor) {
  /* Desaturate + lighten a hex color. factor 0-1: 0.5 = 50% toward white. */
  if (!hex || hex.length < 7) return hex || '#27AE60';
  var r = parseInt(hex.slice(1, 3), 16);
  var g = parseInt(hex.slice(3, 5), 16);
  var b = parseInt(hex.slice(5, 7), 16);
  // Desaturate: pull toward gray
  var gray = r * 0.299 + g * 0.587 + b * 0.114;
  r = Math.round(r + (gray - r) * 0.35);
  g = Math.round(g + (gray - g) * 0.35);
  b = Math.round(b + (gray - b) * 0.35);
  // Lighten: pull toward white by factor
  r = Math.min(255, Math.round(r + (255 - r) * factor));
  g = Math.min(255, Math.round(g + (255 - g) * factor));
  b = Math.min(255, Math.round(b + (255 - b) * factor));
  return '#' + r.toString(16).padStart(2, '0') + g.toString(16).padStart(2, '0') + b.toString(16).padStart(2, '0');
}

function blendAllColors () {
  /* Weighted blend: persona+weather 45%, E/W/D 30%, cover 15%, jitter 10% */
  var atm = state._personaColor || '#27AE60';
  var ewd = state._ewdColor || atm;
  var cov = state._coverColor || ewd;
  var weights = [0.45, 0.40, 0.10];
  var hexes = [atm, ewd, cov];
  var tr = 0, tg = 0, tb = 0, tw = 0;
  for (var i = 0; i < 3; i++) {
    var h = hexes[i] || '#27AE60';
    var wt = weights[i];
    tr += parseInt(h.slice(1,3),16) * wt;
    tg += parseInt(h.slice(3,5),16) * wt;
    tb += parseInt(h.slice(5,7),16) * wt;
    tw += wt;
  }
  // Random jitter 10%
  tr += (Math.random() - 0.5) * 26;
  tg += (Math.random() - 0.5) * 26;
  tb += (Math.random() - 0.5) * 26;
  tw += 0.05;
  tr = Math.max(0, Math.min(255, Math.round(tr / tw)));
  tg = Math.max(0, Math.min(255, Math.round(tg / tw)));
  tb = Math.max(0, Math.min(255, Math.round(tb / tw)));
  return '#' + tr.toString(16).padStart(2,'0') + tg.toString(16).padStart(2,'0') + tb.toString(16).padStart(2,'0');
}

function applyBlendedColor (lerpSpd) {
  if (typeof engine === 'undefined') return;
  var blended = blendAllColors();
  var light = lightenColor(blended, 0.45);
  engine.updateParams({ color: light }, lerpSpd != null ? lerpSpd : 0.015);
}

function hslToHex (h, s, l) {
  s /= 100; l /= 100;
  var a = s * Math.min(l, 1 - l);
  var f = function (n) {
    var k = (n + h / 30) % 12;
    var c = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * c).toString(16).padStart(2, '0');
  };
  return '#' + f(0) + f(8) + f(4);
}

function tryAutoPlay () {
  if (!state.autoPlayEnabled) return;
  if (state.isPlaying) return;
  if (state.playlist.length === 0) return;
  setCurrentSong(state.playlist[0]);
  state.playlistIndex = 0;
  state.isPlaying = true;
  if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
}

/* ═══════════════════════════════════════════════════════════════
   RECOMMENDATIONS
   ═══════════════════════════════════════════════════════════════ */

async function fastLoadInitialSong () {
  try {
    var res = await fetch('/api/songs');
    var data = await res.json();
    if (data.songs && data.songs.length) {
      state.playlist = data.songs;
      state.playlistIndex = 0;
      setCurrentSong(data.songs[0]);
      dom.audioPlayer.preload = 'auto';
      // Sync playlist to backend so song_skip knows the queue
      if (wsClient) wsClient.sendGuaranteed({ action: 'sync_playlist', user_id: state.userId, songs: data.songs });
    }
  } catch (e) { console.error('fastLoadInitialSong:', e); }
}

async function fetchSessionResume () {
  try {
    var res = await fetch('/api/session/resume?user_id=' + state.userId);
    var data = await res.json();
    if (data.has_session && data.current_song) {
      addMessage(
        '欢迎回来！上次听到 ' + data.current_song + ' — ' + data.current_artist +
        '，队列里还有 ' + data.queue_size + ' 首歌。',
        'malio'
      );
    }
  } catch (e) { /* silent */ }
}

async function fetchRecommendations () {
  try {
    const res = await fetch('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();

    if (data.response) {
      addMessage(data.response, 'malio');
      if (state.ttsEnabled) playTTS(data.response);
    }
    if (data.recommendations && data.recommendations.length) {
      state.recommendations = data.recommendations;
      state.playlist = data.recommendations;
      state.playlistIndex = 0;
      setCurrentSong(data.recommendations[0]);
    }
  } catch (err) {
    console.error('Recommendations error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════
   LIBRARY STATS
   ═══════════════════════════════════════════════════════════════ */

async function fetchLibraryStats () {
  try {
    const res = await fetch('/api/library/stats');
    const data = await res.json();
    state.libraryStats = data;
  } catch (err) {
    console.error('Library stats error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════
   NETEASE SEARCH
   ═══════════════════════════════════════════════════════════════ */

async function searchNetease () {
  const query = dom.searchInput.value.trim();
  if (!query) return;

  if (dom.btnSearch) {
    dom.btnSearch.disabled = true;
    dom.btnSearch.textContent = '搜索中...';
  }

  try {
    const res = await fetch('/api/netease/search?query=' + encodeURIComponent(query) + '&limit=20');
    const data = await res.json();
    const tracks = data.tracks || [];
    renderSearchResults(tracks);
  } catch (err) {
    console.error('Search error:', err);
    showToast('搜索失败，请检查网络连接', true);
  } finally {
    if (dom.btnSearch) {
      dom.btnSearch.disabled = false;
      dom.btnSearch.textContent = '搜索';
    }
  }
}

function renderSearchResults (tracks) {
  if (dom.searchResultsHeader) dom.searchResultsHeader.hidden = tracks.length === 0;
  if (dom.searchResultCount) {
    dom.searchResultCount.textContent = '找到 ' + tracks.length + ' 首歌曲';
  }
  if (dom.searchResults) dom.searchResults.innerHTML = '';

  if (tracks.length === 0) {
    if (dom.searchResults) {
      dom.searchResults.innerHTML = '<div class="empty-state"><p>未找到结果</p></div>';
    }
    return;
  }

  tracks.forEach(function (track) {
    var item = document.createElement('div');
    item.className = 'search-result-item';
    item.innerHTML = [
      track.album_art
        ? '<img class="search-result-thumb" src="' + track.album_art + '" alt="" loading="lazy">'
        : '<div class="search-result-thumb" style="display:flex;align-items:center;justify-content:center;color:var(--text-muted)">'
          + '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
          + '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg></div>',
      '<div class="search-result-info">',
        '<h4>' + escapeHtml(track.title) + '</h4>',
        '<p>' + escapeHtml((track.artist || []).join(', ')) + ' · ' + escapeHtml(track.album || '') + '</p>',
      '</div>',
      '<div class="search-result-actions">',
        '<button class="action-btn play-btn" data-id="' + track.id + '" title="播放" aria-label="播放 ' + escapeHtml(track.title) + '">',
          '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
        '</button>',
        '<button class="action-btn add-btn" data-track=\'' + JSON.stringify(track).replace(/'/g, '&#39;') + '\' title="添加到本地库" aria-label="添加 ' + escapeHtml(track.title) + '">',
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
        '</button>',
      '</div>'
    ].join('');

    if (dom.searchResults) dom.searchResults.appendChild(item);
  });

  /* Bind search result actions */
  if (dom.searchResults) {
    dom.searchResults.querySelectorAll('.play-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        playNeteaseTrack(btn.dataset.id);
      });
    });
    dom.searchResults.querySelectorAll('.add-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        try {
          var track = JSON.parse(btn.dataset.track);
          addNeteaseToLibrary(track);
        } catch (_) {}
      });
    });
  }
}

async function playNeteaseTrack (trackId) {
  try {
    const res = await fetch('/api/netease/track/' + trackId + '/url');
    const data = await res.json();
    const detailRes = await fetch('/api/netease/track/' + trackId);
    const detail = await detailRes.json();

    var song = {
      id: trackId,
      title: detail.title || '—',
      artist: detail.artist || ['—'],
      album: detail.album || '',
      duration: detail.duration || 180,
      preview_url: data.url || '',
      album_art: detail.album_art || ''
    };
    setCurrentSong(song);
    state.isPlaying = true;
    if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
  } catch (err) {
    console.error('Play track error:', err);
    showToast('无法播放此歌曲', true);
  }
}

async function addNeteaseToLibrary (track) {
  try {
    var playableUrl = track.preview_url || '';
    if (!playableUrl) {
      const res = await fetch('/api/netease/track/' + track.id + '/url');
      const data = await res.json();
      playableUrl = data.url || '';
    }

    const res = await fetch('/api/netease/add-to-library', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...track, preview_url: playableUrl })
    });
    if (res.ok) {
      showToast('已添加到本地库');
      fetchLibraryStats();
    }
  } catch (err) {
    console.error('Add to library error:', err);
    showToast('添加失败', true);
  }
}

async function importAllTracks () {
  if (dom.btnImportAll) {
    dom.btnImportAll.disabled = true;
    dom.btnImportAll.textContent = '导入中...';
  }
  try {
    var query = dom.searchInput ? dom.searchInput.value.trim() : '';
    const res = await fetch('/api/netease/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, limit: 20 })
    });
    const data = await res.json();
    showToast('导入完成！新增 ' + data.imported + ' 首，重复 ' + data.duplicates + ' 首');
    fetchLibraryStats();
  } catch (err) {
    console.error('Import error:', err);
    showToast('导入失败', true);
  } finally {
    if (dom.btnImportAll) {
      dom.btnImportAll.disabled = false;
      dom.btnImportAll.textContent = '全部导入';
    }
  }
}

/* ═══════════════════════════════════════════════════════════════
   SONG MANAGER
   ═══════════════════════════════════════════════════════════════ */

async function injectSongLibrary () {
  try {
    const res = await fetch('/api/songs');
    const data = await res.json();
    if (typeof engine !== 'undefined' && engine.setSongLibrary) {
      engine.setSongLibrary(data.songs || []);
    }
  } catch (err) {
    console.error('Inject song library error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════
   MEMORY CORRIDOR
   ═══════════════════════════════════════════════════════════════ */

var _corridorState = { openCardId: null };

async function loadCorridor () {
  // Fetch scene playlists, user playlists, and song list in parallel
  try {
    var sceneRes = await fetch('/api/playlists/scenes');
    if (sceneRes.ok) {
      var sceneData = await sceneRes.json();
      renderSceneSection(sceneData);
    }
  } catch (e) { console.error('Scene playlists error:', e); }

  try {
    var plRes = await fetch('/api/playlists');
    if (plRes.ok) {
      var plData = await plRes.json();
      renderUserPlaylists(plData.playlists || []);
    }
  } catch (e) { console.error('Playlists error:', e); }

  loadSongList();
}

function renderSceneSection (sceneData) {
  if (!dom.sceneList) return;
  var songs = sceneData.songs || [];
  var name = sceneData.name || '场景歌单';
  var card = document.createElement('div');
  card.className = 'playlist-card scene-card';
  card.setAttribute('data-scene', sceneData.scene || '');
  card.innerHTML =
    '<div class="card-dots">' + buildColorDots(songs) + '</div>' +
    '<div class="card-info">' +
      '<div class="card-name">' + escapeHtml(name) + '</div>' +
      '<div class="card-meta">' + songs.length + ' 首 · 自动生成</div>' +
    '</div>' +
    '<span class="card-arrow">▸</span>';
  card.addEventListener('click', function () {
    var list = card.nextElementSibling;
    if (list && list.classList.contains('playlist-songs')) {
      list.hidden = !list.hidden;
      card.querySelector('.card-arrow').textContent = list.hidden ? '▸' : '▾';
    }
  });
  dom.sceneList.innerHTML = '';
  dom.sceneList.appendChild(card);
  // Build expandable song list
  var songList = buildSongExpandList(songs);
  dom.sceneList.appendChild(songList);
}

function renderUserPlaylists (playlists) {
  if (!dom.playlistList) return;
  dom.playlistList.innerHTML = '';
  if (!playlists || !playlists.length) {
    dom.playlistList.innerHTML = '<div class="playlist-card" style="opacity:0.5;justify-content:center">暂无歌单 — 长按内核捕获星云粒子</div>';
    return;
  }
  for (var i = 0; i < playlists.length; i++) {
    let pl = playlists[i];
    var card = document.createElement('div');
    card.className = 'playlist-card';
    card.style.position = 'relative';
    card.innerHTML =
      '<div class="card-dots">' + buildColorDots(pl.color_dots || []) + '</div>' +
      '<div class="card-info">' +
        '<div class="card-name">' + escapeHtml(pl.name) + '</div>' +
        '<div class="card-meta">' + (pl.song_count || 0) + ' 首</div>' +
      '</div>' +
      '<span class="card-arrow">▸</span>';
    card._plId = pl.id;
    // Long-press (3s) to delete playlist
    var _holdTimer = null, _holdFired = false;
    var startHold = function () { _holdFired = false; _holdTimer = setTimeout(function () { _holdFired = true; deletePlaylist(pl.id, pl.name, card); }, 3000); };
    var cancelHold = function () { clearTimeout(_holdTimer); };
    card.addEventListener('mousedown', startHold);
    card.addEventListener('mouseup', cancelHold);
    // Don't cancel on mouseleave — tiny movements during 3s hold break it
    card.addEventListener('touchstart', startHold);
    card.addEventListener('touchend', cancelHold);
    card.addEventListener('click', function (plId, el) {
      if (_holdFired) { _holdFired = false; return; }  // long-press triggered, skip click
      return function () {
        var list = el.nextElementSibling;
        if (list && list.classList.contains('playlist-songs')) {
          list.hidden = !list.hidden;
          el.querySelector('.card-arrow').textContent = list.hidden ? '▸' : '▾';
        }
        if (!list || list.hidden) return;
        if (!list._loaded) {
          list._loaded = true;
          fetch('/api/playlists/' + plId).then(function (r) { return r.json(); }).then(function (d) {
            var songEl = buildSongExpandList(d.songs || [], plId);
            while (list.firstChild) list.removeChild(list.firstChild);
            while (songEl.firstChild) list.appendChild(songEl.firstChild);
          });
        }
      };
    }(pl.id, card));
    dom.playlistList.appendChild(card);
    // Expandable song list placeholder
    var songList = document.createElement('div');
    songList.className = 'playlist-songs';
    songList.hidden = true;
    songList._loaded = false;
    dom.playlistList.appendChild(songList);
  }
}

function buildColorDots (songs) {
  if (!songs || !songs.length) return '';
  var dots = '';
  for (var i = 0; i < Math.min(songs.length, 5); i++) {
    var s = songs[i];
    if (s.energy == null) continue;
    var h = (180 - (s.warmth || 0.5) * 120) / 360;
    var sat = (5 + (s.density || 0.5) * 20) / 100;
    var light = (25 + (s.energy || 0.5) * 25) / 100;
    var rgb = hslToRgb(h, sat, light);
    dots += '<span class="card-dot" style="background:rgb(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ')"></span>';
  }
  return dots || '<span class="card-dot" style="background:rgba(255,255,255,0.1)"></span>';
}

function hslToRgb (h, s, l) {
  var hue2rgb = function (p, q, t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  };
  if (s === 0) { var v = Math.round(l * 255); return { r: v, g: v, b: v }; }
  var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  var p = 2 * l - q;
  return {
    r: Math.round(hue2rgb(p, q, h + 1/3) * 255),
    g: Math.round(hue2rgb(p, q, h) * 255),
    b: Math.round(hue2rgb(p, q, h - 1/3) * 255)
  };
}

function buildSongExpandList (songs, plId) {
  var div = document.createElement('div');
  if (!songs || !songs.length) {
    div.innerHTML = '<div class="playlist-song-item" style="opacity:0.5">暂无歌曲</div>';
    return div;
  }
  var html = '';
  for (var i = 0; i < songs.length; i++) {
    var s = songs[i];
    var dot = '';
    if (s.energy != null) {
      var h = (180 - (s.warmth || 0.5) * 120) / 360;
      var sat = (5 + (s.density || 0.5) * 20) / 100;
      var light = (25 + (s.energy || 0.5) * 25) / 100;
      var rgb = hslToRgb(h, sat, light);
      dot = '<span class="song-energy-dot" style="background:rgb(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ')"></span>';
    }
    html += '<div class="playlist-song-item" data-song-id="' + s.id + '" data-song=\'' + JSON.stringify(s).replace(/'/g, '&#39;') + '\'>' +
      dot + '<span>' + escapeHtml(s.title) + ' · ' + escapeHtml((s.artist || []).join(', ')) + '</span>' +
      '<button class="song-del-btn" data-del-id="' + s.id + '" title="删除">✕</button>' +
    '</div>';
  }
  div.innerHTML = html;
  div.querySelectorAll('.playlist-song-item').forEach(function (item, idx) {
    item.addEventListener('click', function (e) {
      if (e.target.classList.contains('song-del-btn')) return;
      try {
        var song = JSON.parse(item.dataset.song);
        state.playlist = songs;
        state.playlistIndex = idx;
        setCurrentSong(song);
        state.isPlaying = true;
        if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
      } catch (_) {}
    });
    var delBtn = item.querySelector('.song-del-btn');
    if (delBtn) {
      delBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        var songId = this.dataset.delId;
        if (!plId) return;
        fetch('/api/playlists/' + plId + '/songs/' + songId, { method: 'DELETE' })
          .then(function (r) { return r.json(); })
          .then(function () { item.remove(); showToast('已删除'); })
          .catch(function (err) { console.error('Delete song error:', err); });
      });
    }
  });
  return div;
}

async function loadSongList () {
  try {
    const res = await fetch('/api/songs');
    const data = await res.json();
    var songs = data.songs || [];
    renderSongList(songs);
  } catch (err) {
    console.error('Load songs error:', err);
  }
}

function renderSongList (songs) {
  if (dom.allSongsCount) dom.allSongsCount.textContent = songs.length;
  if (dom.songList) {
    if (songs.length === 0) {
      dom.songList.innerHTML = '<div class="empty-state"><p>还没有歌曲，点击上方按钮添加</p></div>';
      return;
    }

    dom.songList.innerHTML = songs.map(function (song) {
      return '<div class="song-list-item">'
        + '<div class="song-list-info">'
          + '<h4>' + escapeHtml(song.title) + '</h4>'
          + '<p>' + escapeHtml((song.artist || []).join(', ')) + ' · ' + escapeHtml(song.album || '') + '</p>'
        + '</div>'
        + '<div class="song-list-meta">'
          + '<span>' + (song.duration || 0) + '秒</span>'
          + '<button class="delete-btn" data-id="' + song.id + '" title="删除" aria-label="删除 ' + escapeHtml(song.title) + '">'
            + '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            + '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>'
          + '</button>'
        + '</div>'
      + '</div>';
    }).join('');

    dom.songList.querySelectorAll('.delete-btn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        deleteSong(btn.dataset.id);
      });
    });
    dom.songList.querySelectorAll('.song-list-item').forEach(function (item, i) {
      item.addEventListener('click', function () {
        state.playlist = songs;
        state.playlistIndex = i;
        setCurrentSong(songs[i]);
        state.isPlaying = true;
        if (dom.audioPlayer) dom.audioPlayer.play().catch(function () {});
      });
    });
  }
}

async function addSong (e) {
  e.preventDefault();
  var songData = {
    id: 'song_' + Date.now(),
    title: document.getElementById('form-title') ? document.getElementById('form-title').value : '',
    artist: document.getElementById('form-artist')
      ? document.getElementById('form-artist').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
      : [],
    album: document.getElementById('form-album') ? document.getElementById('form-album').value : '',
    genre: (document.getElementById('form-genre') ? document.getElementById('form-genre').value : '').split(',').map(function (s) { return s.trim(); }).filter(Boolean),
    release_year: parseInt(document.getElementById('form-year') ? document.getElementById('form-year').value : '') || new Date().getFullYear(),
    duration: parseInt(document.getElementById('form-duration') ? document.getElementById('form-duration').value : '') || 180,
    features: {}
  };

  try {
    const res = await fetch('/api/songs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(songData)
    });
    if (res.ok) {
      showToast('歌曲添加成功');
      if (dom.addSongForm) {
        dom.addSongForm.hidden = true;
        dom.addSongForm.reset();
      }
      loadSongList();
      fetchLibraryStats();
    }
  } catch (err) {
    console.error('Add song error:', err);
    showToast('添加失败', true);
  }
}

async function deleteSong (id) {
  if (!confirm('确定要删除这首歌吗？')) return;
  try {
    const res = await fetch('/api/songs/' + id, { method: 'DELETE' });
    if (res.ok) {
      showToast('歌曲已删除');
      loadSongList();
      fetchLibraryStats();
    }
  } catch (err) {
    console.error('Delete song error:', err);
  }
}

/* ═══════════════════════════════════════════════════════════════
   TOAST
   ═══════════════════════════════════════════════════════════════ */

function deletePlaylist (plId, plName, cardEl) {
  showConfirmBar('删除歌单「' + plName + '」？', function () {
    fetch('/api/playlists/' + plId, { method: 'DELETE' })
      .then(function (r) { return r.json(); })
      .then(function () {
        cardEl.remove();
        var next = cardEl.nextElementSibling;
        if (next && next.classList.contains('playlist-songs')) next.remove();
        showToast('歌单已删除');
      })
      .catch(function (err) { console.error('Delete playlist error:', err); showToast('删除失败'); });
  });
}

function showToast (msg, isError) {
  var toast = document.createElement('div');
  toast.className = 'toast' + (isError ? ' error' : '');
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(function () { toast.remove(); }, 3000);
}

function showConfirmBar (msg, onConfirm, onCancel, inputOpts) {
  var existing = document.getElementById('confirm-bar');
  if (existing) existing.remove();
  var bar = document.createElement('div');
  bar.id = 'confirm-bar';
  bar.style.cssText = 'position:fixed;bottom:100px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.85);border:1px solid rgba(255,255,255,0.15);border-radius:12px;padding:12px 20px;color:#fff;font-size:14px;z-index:9999;display:flex;align-items:center;gap:14px;backdrop-filter:blur(10px);flex-wrap:wrap;justify-content:center;';
  var html = '<span>' + msg + '</span>';
  if (inputOpts) {
    html += '<input id="confirm-bar-input" type="text" value="' + (inputOpts.value || '') + '" style="padding:6px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.08);color:#fff;font-size:13px;width:180px;outline:none;">';
  }
  html += '<button id="confirm-bar-yes" style="padding:6px 16px;border-radius:8px;border:none;background:#22C55E;color:#fff;cursor:pointer;font-size:13px;">' + (inputOpts ? '创建歌单' : '创建') + '</button>' +
    '<button id="confirm-bar-no" style="padding:6px 16px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:transparent;color:#aaa;cursor:pointer;font-size:13px;">取消</button>';
  bar.innerHTML = html;
  bar.querySelector('#confirm-bar-yes').addEventListener('click', function () {
    var inputVal = inputOpts ? (document.getElementById('confirm-bar-input') || {}).value : null;
    bar.remove();
    if (onConfirm) onConfirm(inputVal);
  });
  bar.querySelector('#confirm-bar-no').addEventListener('click', function () {
    bar.remove();
    if (onCancel) onCancel();
  });
  setTimeout(function () {
    if (document.getElementById('confirm-bar')) {
      bar.remove();
      if (onCancel) onCancel();
    }
  }, 15000);
}

/* ═══════════════════════════════════════════════════════════════
   AGENT LOG
   ═══════════════════════════════════════════════════════════════ */

var _agentLogTimer = null;

function showAgentLog (message) {
  if (!dom.agentLog) return;

  var logText = document.getElementById('agent-log-text');
  if (logText) logText.textContent = message;
  dom.agentLog.hidden = false;

  /* Clear any pending auto-hide */
  if (_agentLogTimer) {
    clearTimeout(_agentLogTimer);
    _agentLogTimer = null;
  }

  /* Auto-hide after 3s unless pinned */
  if (!dom.agentLog.classList.contains('pinned')) {
    _agentLogTimer = setTimeout(function () {
      if (dom.agentLog && !dom.agentLog.classList.contains('pinned')) {
        dom.agentLog.hidden = true;
      }
    }, 3000);
  }
}

/* ═══════════════════════════════════════════════════════════════
   WEB SOCKET CLIENT SETUP
   ═══════════════════════════════════════════════════════════════ */

function setupWsClient () {
  if (typeof wsClient === 'undefined') {
    /* fallback: direct websocket if ws-client.js not loaded */
    setupDirectWebSocket();
    return;
  }

  wsClient.onLog = function (message) {
    showAgentLog(message);
  };

  wsClient.onRule = function (ruleJson) {
    if (particleRules) particleRules.addRule(ruleJson);
  };

  wsClient.onSnapshot = function (data) {
    // Reject stale snapshots (version-based ABA guard)
    if (data.seq !== undefined && data.seq <= state.lastSnapshotSeq) return;
    if (data.seq !== undefined) state.lastSnapshotSeq = data.seq;

    if (data.song && data.song.title) {
      _applySongFromWS(data.song);
    }
    if (data.is_playing !== undefined) {
      state.isPlaying = data.is_playing;
      updatePlayIcon();
    }
    if (data.playlist && data.playlist.length) {
      state.playlist = data.playlist;
    }
    if (data.core_mode && typeof engine !== 'undefined') {
      engine.setCoreMode(data.core_mode);
    }
    if (data.core_action && typeof engine !== 'undefined') {
      _executeCoreAction(data.core_action);
    }
    if (data.atmosphere && typeof engine !== 'undefined') {
      if (data.atmosphere.color) state._personaColor = data.atmosphere.color;
      var atm = Object.assign({}, data.atmosphere);
      delete atm.color; delete atm.amplitude; delete atm.density;
      engine.updateParams(atm, 0.015);
      applyBlendedColor();
    }
    // Store weather for DSL rules
    if (data.weather) {
      window._lastWeather = data.weather;
    }
  };

  wsClient.onStateUpdate = function (data) {
    if (data.type === 'now_playing' && data.song) {
      setCurrentSong(data.song);
      if (data.is_playing) {
        state.isPlaying = true;
        updatePlayIcon();
      }
    } else if (data.type === 'playlist_update') {
      state.playlist = data.playlist || [];
    }
  };
}

function _executeCoreAction (ca) {
  if (!engine) return;
  var action = ca.action;
  var params = ca.params || {};
  switch (action) {
    case 'set_mode':
      engine.setCoreMode(params.mode || 'dot');
      break;
    case 'set_shape':
      if (params.shape && typeof engine.setShape === 'function') engine.setShape(params.shape);
      break;
    case 'light_burst':
      engine.triggerLightBurst(params.color);
      break;
    case 'move_core':
      // Drift smoothly to target, then spring back — not instant jump
      engine._driftStartX = engine.core.x;
      engine._driftStartY = engine.core.y;
      engine._driftTargetX = engine.core.x + (params.x || 0);
      engine._driftTargetY = engine.core.y + (params.y || 0);
      engine._driftStartTime = performance.now();
      engine._driftDuration = 2000 + Math.random() * 1500; // 2-3.5s drift
      engine._settled = false;
      break;
    case 'set_size':
      if (params.radius) engine._targetCoreR = Math.max(10, Math.min(80, params.radius));
      break;
    case 'time_warp':
      if (params.active && !engine._timeWarp) {
        engine._timeWarp = true;
        engine._timeWarpStart = performance.now();
        engine._timeWarpBubble = 0;
        if (typeof engine.onTimeWarp === 'function') engine.onTimeWarp(true);
      } else if (!params.active && engine._timeWarp) {
        engine._timeWarp = false;
        if (typeof engine.onTimeWarp === 'function') engine.onTimeWarp(false);
      }
      break;
    case 'breath':
      engine.setBreath(params.rate, params.depth);
      break;
    case 'set_speed':
      engine.updateParams({ speed: params.speed || 1.0 }, 0.03);
      break;
    case 'set_color':
      engine.updateParams({ color: params.color || '#22C55E' }, 0.03);
      break;
    case 'set_density':
      engine.updateParams({ amplitude: params.amplitude || 0.4 }, 0.05);
      break;
  }
}

/* ═══════════════════════════════════════════════════════════════
   PARTICLE RULES — DSL engine
   ═══════════════════════════════════════════════════════════════ */

var _rulesLoopId = null;

function initParticleRules () {
  if (typeof ParticleRules === 'undefined' || typeof engine === 'undefined') return;
  particleRules = new ParticleRules(engine);

  /* hook into animation loop */
  function rulesLoop () {
    particleRules.evaluate(performance.now());
    _rulesLoopId = requestAnimationFrame(rulesLoop);
  }
  _rulesLoopId = requestAnimationFrame(rulesLoop);
}

/* expose for ws-client to feed agent-generated rules */
window.addAgentRule = function (ruleJson) {
  if (particleRules) particleRules.addRule(ruleJson);
};
window.removeAgentRule = function (id) {
  if (particleRules) particleRules.removeRule(id);
};

/* ═══════════════════════════════════════════════════════════════
   AUDIO REACTIVITY — drive particles with music
   ═══════════════════════════════════════════════════════════════ */

var _audioAnalyzerInitialized = false;
var _audioUpdateRaf = null;

function initAudioReactivity () {
  if (typeof AudioAnalyzer === 'undefined') return;
  /* AudioContext requires user gesture — activate on first play */
  if (dom.audioPlayer) {
    dom.audioPlayer.addEventListener('play', function () {
      if (!_audioAnalyzerInitialized) {
        audioAnalyzer = new AudioAnalyzer(dom.audioPlayer);
        audioAnalyzer.init();
        if (audioAnalyzer.active) {
          _audioAnalyzerInitialized = true;
          _startAudioLoop();
        }
      }
    }, { once: false });
  }
  /* If already playing when page loads */
  if (dom.audioPlayer && !dom.audioPlayer.paused && !_audioAnalyzerInitialized) {
    audioAnalyzer = new AudioAnalyzer(dom.audioPlayer);
    audioAnalyzer.init();
    if (audioAnalyzer.active) {
      _audioAnalyzerInitialized = true;
      _startAudioLoop();
    }
  }
}

function _startAudioLoop () {
  function loop () {
    if (!audioAnalyzer || !audioAnalyzer.active) {
      _audioUpdateRaf = null;
      return;
    }
    var data = audioAnalyzer.analyze();
    if (typeof engine !== 'undefined') engine.setAudioData(data);
    _audioUpdateRaf = requestAnimationFrame(loop);
  }
  _audioUpdateRaf = requestAnimationFrame(loop);
}

/* Fallback WebSocket if ws-client.js is not loaded */
function setupDirectWebSocket () {
  var protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = protocol + '//' + location.host + '/stream';
  var ws;

  function connect () {
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = function (e) {
        try {
          var data = JSON.parse(e.data);
          handleWsMessage(data);
        } catch (_) {}
      };
      ws.onclose = function () { setTimeout(connect, 3000); };
      ws.onerror = function () { ws.close(); };
    } catch (_) {}
  }

  connect();
}

function handleWsMessage (data) {
  if (data.type === 'now_playing' && data.song) {
    setCurrentSong(data.song);
    if (data.is_playing) {
      state.isPlaying = true;
      updatePlayIcon();
    }
  } else if (data.type === 'playlist_update') {
    state.playlist = data.playlist || [];
  } else if (data.type === 'state_snapshot') {
    if (data.song) { setCurrentSong(data.song); }
    if (data.is_playing !== undefined) { state.isPlaying = data.is_playing; updatePlayIcon(); }
    if (data.playlist && data.playlist.length) { state.playlist = data.playlist; }
  } else if (data.type === 'agent_log') {
    showAgentLog(data.message || data.content || '');
  }
}

/* ═══════════════════════════════════════════════════════════════
   PARTICLE ENGINE — PERIODIC MOOD CHANGES
   ═══════════════════════════════════════════════════════════════ */

var _particleMoodInterval = null;

/* ── Idle Timer: time-gradient rest mode ──────────────────── */
var _idleSeconds = 0;
var _idleLevel = 0;
var _idleInterval = null;

function initIdleTimer () {
  var events = ['mousedown', 'mousemove', 'touchstart', 'touchmove',
                'keydown', 'wheel', 'click'];
  var reset = function () { _idleSeconds = 0; };
  events.forEach(function (evt) {
    document.addEventListener(evt, reset, { passive: true });
  });
  _idleInterval = setInterval(_idleTick, 1000);
}

function _idleTick () {
  _idleSeconds++;
  var hour = new Date().getHours();
  var isNight = hour >= 23 || hour < 5;
  var newLevel = 0;

  if (_idleSeconds < 180) newLevel = 0;         // 0-3min
  else if (_idleSeconds < 600) newLevel = 1;     // 3-10min
  else if (_idleSeconds < 1200) newLevel = 2;    // 10-20min
  else if (_idleSeconds < 2400) newLevel = 3;    // 20-40min
  else newLevel = 4;                              // 40min+

  // Night: start at soft (2), skip to deep (3) after 10min idle
  if (isNight) {
    if (_idleSeconds < 600) newLevel = 2;
    else newLevel = Math.max(3, newLevel);
  }

  if (newLevel !== _idleLevel) {
    var transition = newLevel > _idleLevel ? 30 : 8; // 30s down, 8s up
    _idleLevel = newLevel;
    if (typeof engine !== 'undefined' && engine.setTimeLevel) {
      engine.setTimeLevel(newLevel, transition);
    }
  }
}

function startParticleMood () {
  if (typeof engine === 'undefined') return;

  /* Slightly vary amplitude every 4–8 seconds to simulate mood changes */
  _particleMoodInterval = setInterval(function () {
    if (typeof engine === 'undefined') return;
    var base = engine.params.amplitude || 0.4;
    var variation = (Math.random() - 0.5) * 0.15;  /* subtle sway */
    engine.updateParams({
      amplitude: Math.max(0.3, Math.min(3, base + variation))
    });
  }, 4000 + Math.random() * 4000);
}

/* ═══════════════════════════════════════════════════════════════
   KEYBOARD SHORTCUTS
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('keydown', function (e) {
  /* Ignore when typing in input/textarea */
  var tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    /* Allow Escape to close panels even in inputs */
    if (e.key === 'Escape') {
      if (state.activePanel) {
        e.preventDefault();
        closeAllPanels();
      }
      return;
    }
    /* Allow / to refocus chat if currently in search input */
    if (e.key === '/' && tag === 'INPUT') return;
    return;
  }

  switch (e.key) {
    case ' ':
      /* Space — play/pause (but not when button is focused) */
      if (tag !== 'BUTTON') {
        e.preventDefault();
        togglePlay();
      }
      break;

    case 'ArrowLeft':
      e.preventDefault();
      prevSong();
      break;

    case 'ArrowRight':
      e.preventDefault();
      nextSong();
      break;

    case '/':
      /* Forward slash — focus chat input */
      if (dom.chatInput) {
        e.preventDefault();
        /* Ensure chat panel is open */
        if (state.activePanel !== 'chat') {
          togglePanel('chat');
        } else {
          dom.chatInput.focus();
        }
      }
      break;

    case 'h':
      /* H — toggle player visibility */
      document.body.classList.toggle('player-hidden');
      var btnHide = document.getElementById('btn-hide-player');
      if (btnHide) btnHide.classList.toggle('active', document.body.classList.contains('player-hidden'));
      break;

    case 'Escape':
      /* Escape — close any open panel */
      if (state.activePanel) {
        e.preventDefault();
        closeAllPanels();
      }
      break;
  }

  /* Ctrl+K — toggle search */
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    togglePanel('search');
  }
});
