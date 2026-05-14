/* ================================================================
   WSClient — WebSocket State Snapshot Consumer
   Connects to /stream, dispatches state_snapshot / agent_log messages,
   auto-reconnects on close.
   ================================================================ */

const WS_RECONNECT_DELAY = 3000;

class WSClient {
  constructor (url) {
    this.url = url;
    this.ws = null;
    this._reconnectTimer = null;
    this._destroyed = false;

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
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = protocol + '//' + location.host + this.url;
      this.ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn('[WSClient] Connection error:', err);
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      /* send an initial get_state to sync */
      this.getState();
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
          this.onRule(data);
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
      this.ws.send(JSON.stringify({ action: 'get_state' }));
    } catch (_) { /* ignore */ }
  }

  sendCoreEvent (type, detail) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    try {
      this.ws.send(JSON.stringify({ action: 'core_event', event: { type: type, detail: detail, ts: Date.now() } }));
    } catch (_) { /* ignore */ }
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
