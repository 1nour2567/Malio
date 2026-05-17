/* ================================================================
   WSClient — WebSocket State Snapshot Consumer
   Connects to /stream, dispatches state_snapshot / agent_log messages,
   auto-reconnects on close.
   ================================================================ */

const WS_RECONNECT_DELAY = 3000;
const WS_QUEUE_MAX = 100;
const WS_QUEUE_TTL_MS = 30000;

class WSClient {
  constructor (url) {
    this.url = url;
    this.ws = null;
    this._reconnectTimer = null;
    this._destroyed = false;
    this._pendingQueue = [];  /* messages queued before connection opens */

    /* ── callbacks (set by consumer) ──────────────────────── */
    this.onSnapshot = null;
    this.onLog = null;
    this.onStateUpdate = null;
    this.onRule = null;  /* agent-generated DSL rules */

    this._connect();
  }

  /* ═══════════════════════════════════════════════════════════
     Connect
     ═══════════════════════════════════════════════════════════ */

  _connect () {
    if (this._destroyed) return;

    try {
      // Bypass Vite proxy (bug: connects but drops messages).
      // In dev: direct to backend port 8007. In prod: relative to page origin.
      const isDev = location.port === '5173';
      const wsHost = isDev ? 'localhost:8007' : location.host;
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = protocol + '//' + wsHost + this.url;
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn('[WSClient] Connection error:', err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      /* send an initial get_state to sync */
      this.getState();
      /* drain pending queue — drop expired messages */
      var now = Date.now();
      var valid = [];
      for (var i = 0; i < this._pendingQueue.length; i++) {
        var msg = this._pendingQueue[i];
        if (msg._ts && now - msg._ts < WS_QUEUE_TTL_MS) {
          valid.push(msg);
        }
      }
      for (var j = 0; j < valid.length; j++) {
        var m = valid[j];
        delete m._ts;
        try { this.ws.send(JSON.stringify(m)); } catch (_) {}
      }
      this._pendingQueue = [];
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._handleMessage(data);
      } catch (_) {
        /* ignore malformed frames */
      }
    };

    this.ws.onclose = () => {
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws.close();
    };
  }

  /* ═══════════════════════════════════════════════════════════
     Message dispatch
     ═══════════════════════════════════════════════════════════ */

  _handleMessage (data) {
    switch (data.type) {
      case 'state_snapshot':
        if (typeof this.onSnapshot === 'function') {
          this.onSnapshot(data);
        }
        break;

      case 'agent_log':
        if (typeof this.onLog === 'function') {
          this.onLog(data.message || data.content || '');
        }
        break;

      case 'now_playing':
        /* bridge to existing now_playing handler via onStateUpdate */
        if (typeof this.onStateUpdate === 'function') {
          this.onStateUpdate(data);
        }
        break;

      case 'playlist_update':
        if (typeof this.onStateUpdate === 'function') {
          this.onStateUpdate(data);
        }
        break;

      case 'rule':
        if (typeof this.onRule === 'function') {
          this.onRule(data.rule || data);
        }
        break;

      default:
        /* unknown type — forward to onStateUpdate if set */
        if (typeof this.onStateUpdate === 'function') {
          this.onStateUpdate(data);
        }
        break;
    }
  }

  /* ═══════════════════════════════════════════════════════════
     Reconnect
     ═══════════════════════════════════════════════════════════ */

  _scheduleReconnect () {
    if (this._destroyed) return;
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer);
    this._reconnectTimer = setTimeout(() => this._connect(), WS_RECONNECT_DELAY);
  }

  /* ═══════════════════════════════════════════════════════════
     getState — request a full state snapshot
     ═══════════════════════════════════════════════════════════ */

  getState () {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      var uid = localStorage.getItem('malio_user_id') || 'default';
      this.ws.send(JSON.stringify({ action: 'get_state', user_id: uid }));
    } catch (_) { /* ignore */ }
  }

  sendCoreEvent (type, detail) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      var uid = localStorage.getItem('malio_user_id') || 'default';
      this.ws.send(JSON.stringify({ action: 'core_event', user_id: uid, event: { type: type, detail: detail, ts: Date.now() } }));
    } catch (_) { /* ignore */ }
  }

  sendGuaranteed (msg) {
    /* Send now if connected; queue with TTL otherwise */
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try { this.ws.send(JSON.stringify(msg)); } catch (_) {}
    } else {
      if (this._pendingQueue.length < WS_QUEUE_MAX) {
        msg._ts = Date.now();
        this._pendingQueue.push(msg);
      }
    }
  }

  /* ═══════════════════════════════════════════════════════════
     Destroy — clean up
     ═══════════════════════════════════════════════════════════ */

  destroy () {
    this._destroyed = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
  }
}

/* ── Export singleton ──────────────────────────────────── */
const wsClient = new WSClient('/stream');
