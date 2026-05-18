/* ================================================================
   Malio — Matrix Code Rain
   Frame-buffer trail: each frame overlays rgba(0,0,0,0.07),
   old characters naturally fade. Columns stack chars vertically.
   ================================================================ */

const COL_GAP = 20;
const CHAR_GAP = 18;
const TRAIL_FADE = 0.14;   // half-length trail: higher = faster fade
const FONT_SIZE = 15;
/* Three z-layers: far (z=1), mid (z=0.5), near (z=0) */
const LAYERS = [
  { z: 1, size: 12, opacity: 0.25, speedMul: 0.5,  brightness: 0.6,  ratio: 0.30, label: 'far' },
  { z: 0.5, size: 15, opacity: 0.5, speedMul: 0.65, brightness: 0.8, ratio: 0.45, label: 'mid' },
  { z: 0, size: 17, opacity: 0.9, speedMul: 1.0,   brightness: 1.0,  ratio: 0.25, label: 'near' },
];
const HEAD_COLOR = '#22C55E';

/* ── E/W/D → RGB color mapping ──────────────────────────────── */
/* Warmth→Hue(180°cyan→60°yellow-green), Density→Sat(5%→25%), Energy→Light(25%→50%) */
/* All ranges narrowed around Matrix green (120°) for immersive, non-neon look */
function ewdToRgb (energy, warmth, density) {
  const h = (180 - warmth * 120) / 360;    /* hue 0-1: 180°→60° */
  const s = (5 + density * 20) / 100;      /* saturation 0-1: 5%→25% */
  const l = (25 + energy * 25) / 100;      /* lightness 0-1: 25%→50% */

  /* HSL → RGB */
  const hue2rgb = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  };

  if (s === 0) {
    const v = Math.round(l * 255);
    return { r: v, g: v, b: v };
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return {
    r: Math.round(hue2rgb(p, q, h + 1/3) * 255),
    g: Math.round(hue2rgb(p, q, h) * 255),
    b: Math.round(hue2rgb(p, q, h - 1/3) * 255)
  };
}

const KATAKANA = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン';

const CHARS = (() => {
  const s = [
    'アイウエオカキクケコサシスセソタチツテトナニヌネノ',
    'あいうえおかきくけこさしすせそたちつてとなにぬねの',
    '日月火水木金土空風雨山川海花鳥魚声音楽心身体夢',
    '春夏秋冬朝昼夜明暗光影静寂響律譜調和奏旋律記憶',
    '自我在存思知情意感覚悟道真理天地宇宙',
    '零壱弐参肆伍陸漆捌玖拾佰仟万',
  ];
  return s.join('');
})();

const PHRASES = [
  '存在', '意識', '記憶', '時間', '空間', '宇宙', '無限',
  '自由', '解放', '進化', '生成', '消滅', '再生', '循環',
  '旋律', '和音', '共鳴', '静寂', '波動', '律動', '調和',
  '月光', '星空', '風鈴', '花火', '桜花', '雪解', '朝霧',
  '天命', '覚悟', '真実', '永遠', '刹那', '運命', '奇跡',
  '白昼夢', '夕立', '十六夜', '花吹雪', '泡沫', '蝉時雨',
  '人工知能', '自律思考', '深層学習', '情報空間',
  '知行合一', '格物致知', '天人合一', '道法自然',
  '明心見性', '大道至簡', '大象無形', '大音希声',
  '残像', '心象', '境界', '回路', '回廊', '残響', '深淵',
  '意識体', '自己像', '記憶痕', '情報体', '思考層',
  '木霊', '風音', '水鏡', '陽炎', '霜柱', '薄明', '黄昏',
  '星霜', '雪化粧', '花嵐', '月影', '水面', '燈火', '夜霧',
  '空蝉', '名残', '徒花', '夢枕', '永遠', '約束', '祈',
  '想い', '絆', '光', '闇', '響', '凪', '刹那',
];

function randChars () {
  const r = Math.random();
  if (r < 0.25) {
    const p = PHRASES[Math.floor(Math.random() * PHRASES.length)];
    return p.split('');
  }
  if (r < 0.45) {
    const len = 2 + Math.floor(Math.random() * 4);
    const chars = [];
    for (let i = 0; i < len; i++) {
      chars.push(KATAKANA[Math.floor(Math.random() * KATAKANA.length)]);
    }
    return chars;
  }
  return [CHARS[Math.floor(Math.random() * CHARS.length)]];
}

class MatrixRain {
  constructor (canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      this.canvas = document.createElement('canvas');
      this.canvas.id = canvasId;
      Object.assign(this.canvas.style, {
        position: 'fixed', top: '0', left: '0',
        width: '100%', height: '100%', zIndex: '0'
      });
      document.body.prepend(this.canvas);
    }
    this.ctx = this.canvas.getContext('2d');
    this._colsFar = [];
    this._colsMid = [];
    this._colsNear = [];
    this.core = { x: 0, y: 0, r: 27, active: true };
    this._breathPhase = 0;
    this._breathRate = 0.016;   // Agent-controllable
    this._breathDepth = 0.7;    // Agent-controllable
    this.params = { speed: 3.8, color: '#22C55E' };
    this._targetParams = { speed: 3.8, color: '#22C55E' };
    this._lerpFactor = 0.03;
    this._fadeAlpha = TRAIL_FADE;
    this._timeLevel = 0;          // current fade level 0-4
    this._timeTarget = 0;         // target level
    this._timeLerp = 0;           // lerp progress 0-1
    this._timeLerpSpeed = 0;      // lerp rate per frame
    this._lastFrame = performance.now();
    this._resize();
    this._buildColumns();
    this._dragging = false;
    this._dX = 0; this._dY = 0;  // drag direction
    this._grabTime = 0;          // when grab started
    this._settled = true;        // core at home, not returning
    this._ripples = [];          // water ripple rings [{x,y,r,alpha}]
    this._prevCoreX = this.core.x;
    this._prevCoreY = this.core.y;
    this._rippleTimer = 0;       // cooldown between ripple spawns
    this._burst = null;          // light burst state
    this._timeWarp = false;      // bullet time active
    this._timeWarpStart = 0;     // when it started
    this._timeWarpBubble = 0;    // expanding bubble radius (0→600)
    this._lastTap = 0;           // double-tap detection
    this._lastWarpInteract = 0;  // last interaction during warp
    this._summonActive = false;  // long-press summon
    this._summonStart = 0;       // summon start time
    this._infoChars = [];        // song info character pool
    this._infoTags = [];         // song_id tags for info chars
    this._infoCols = new Set();  // columns currently occupied by info particles
    this._infoPending = [];      // info particles awaiting delayed respawn
    this._captureTarget = null;  // frozen particle closest to core during drag
    this._capturedParticles = []; // swallowed particles [{song_id, title, energy, warmth, density}]
    this._returning = false;
    this._retVX = 0;
    this._retVY = 0;
    this._homeX = this.core.x;
    this._homeY = this.core.y;
    this.onSwipe = null;            // callback for swipe gesture
    this.onTimeWarp = null;         // callback for double-tap pause
    this.onCaptureComplete = null;  // callback for nebula capture → playlist
    this.onCoreRelease = null;     // callback for reverse embodiment: core position → music
    /* audio reactivity */
    this._audio = { bass: 0, mid: 0, treble: 0, beat: 0 };
    /* search mode */
    this._searchMode = false;
    this._searchInputLen = 0;
    /* core mode from Agent */
    this._coreMode = 'dot';  /* dot / vortex / helix / error */
    this._coreShape = 'circle';       /* current rendered shape */
    this._shapeTarget = 'circle';     /* morph target */
    this._shapeMorphT = 1;            /* morph progress 0→1 */
    this._shapeFromVerts = null;      /* snapshot of vertices at morph start */
    /* particle memory — interaction fingerprint */
    this._memory = this._loadMemory();
    this._memoryDirty = false;
    this._memorySaveTimer = null;
    this._bindDrag();
    this._boundAnimate = this._animate.bind(this);
    this._boundAnimate();
    window.addEventListener('resize', () => { this._resize(); this._buildColumns(); });
  }

  _bindDrag () {
    let _pressTimer = null;
    let _pressStartX = 0;
    let _pressStartY = 0;
    let _swipeStartX = 0;
    let _swipeStartY = 0;
    let _swiping = false;

    const start = (e) => {
      /* skip interactive elements — let their handlers work */
      let el = e.target;
      while (el && el !== document.body) {
        const t = el.tagName;
        if (t === 'BUTTON' || t === 'INPUT' || t === 'A' || t === 'SELECT' || t === 'TEXTAREA' || t === 'LABEL') {
          _swiping = false; this._dragging = false; return;
        }
        if (el.classList && (el.classList.contains('side-panel') || el.classList.contains('playlist-card') || el.classList.contains('chat-messages') || el.classList.contains('search-results'))) {
          _swiping = false; this._dragging = false; return;
        }
        if (el.id && (el.id.startsWith('btn-') || el.id.startsWith('ctrl-') || el.id.endsWith('-panel'))) {
          _swiping = false; this._dragging = false; return;
        }
        el = el.parentElement;
      }

      const pos = this._eventPos(e);
      const dx = pos.x - this.core.x;
      const dy = pos.y - this.core.y;
      const nearCore = Math.sqrt(dx * dx + dy * dy) < this.core.r + 10;

      if (nearCore) {
        // Double-tap detection
        const now = performance.now();
        if (now - this._lastTap < 400) {
          clearTimeout(_pressTimer);
          if (this._summonActive) this.endSummon();
          if (this._searchMode) this.endSearch();
          this._dragging = false;
          this.canvas.style.cursor = '';
          this._timeWarp = !this._timeWarp;
          this._lastTap = 0;
          if (this._timeWarp) {
            this._timeWarpStart = now;
            this._timeWarpBubble = 0;
            this._lastWarpInteract = now;
          } else {
            for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
              for (const col of layer) {
                for (const c of col.stream) {
                  c.vx = 0; c.vy = 0;
                  c._wY = 0; c._wstretch = 1;
                }
              }
            }
          }
          if (typeof this.onTimeWarp === 'function') {
            this.onTimeWarp(this._timeWarp);
          }
          return;
        }
        this._lastTap = now;

        _pressStartX = pos.x;
        _pressStartY = pos.y;
        const sx = _pressStartX, sy = _pressStartY;
        _pressTimer = setTimeout(() => {
          const dx2 = this.core.x - sx, dy2 = this.core.y - sy;
          const moved = Math.abs(dx2) + Math.abs(dy2);
          if (moved < 10) {
            this.startSearch();  /* held still → search */
          } else {
            this.startSummon(); /* dragged → nebula capture */
          }
        }, 600);
        this._dragging = true;
        this._settled = false;
        this._grabTime = performance.now();
        this.canvas.style.cursor = 'grabbing';
        e.preventDefault();
      } else {
        /* outside core → swipe only, no drag */
        _swiping = true;
        _swipeStartX = pos.x;
        _swipeStartY = pos.y;
        _swipeAccDx = 0;
        _swipeAccDy = 0;
        e.preventDefault();
      }
    };
    let _dragPrevX = 0, _dragPrevY = 0;
    let _swipeAccDx = 0, _swipeAccDy = 0;
    const move = (e) => {
      if (!_swiping && !this._dragging) return;
      const pos = this._eventPos(e);

      /* track swipe delta — fire immediately on threshold */
      if (_swiping) {
        _swipeAccDx = pos.x - _swipeStartX;
        _swipeAccDy = pos.y - _swipeStartY;
        /* immediate fire once threshold crossed */
        if (Math.abs(_swipeAccDx) > 30 && Math.abs(_swipeAccDx) > Math.abs(_swipeAccDy)) {
          const dir = _swipeAccDx > 0 ? 'right' : 'left';
          this.triggerSwipeRipple(dir);
          _swiping = false;
          _swipeAccDx = 0;
          _swipeAccDy = 0;
          return;
        }
      }

      if (this._dragging) {
        const pos = this._eventPos(e);
        // Stir particles near core during drag
        const dmx = pos.x - (_dragPrevX || pos.x);
        const dmy = pos.y - (_dragPrevY || pos.y);
        _dragPrevX = pos.x; _dragPrevY = pos.y;
        const dmag = Math.sqrt(dmx * dmx + dmy * dmy);
        if (dmag > 0.5) {
          const ndx = dmx / dmag, ndy = dmy / dmag;
          // Water ripple from dragged core
          for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
            for (const col of layer) {
              for (const c of col.stream) {
                const ddx = c.x - pos.x, ddy = c.y - pos.y;
                const ddist = Math.sqrt(ddx * ddx + ddy * ddy);
                if (ddist < 120) {
                  const amp = (1 - ddist / 120) * dmag * 0.3;
                  c._wY = (c._wY || 0) + Math.sin(ddist * 0.05) * amp;
                }
              }
            }
          }
        }
        this.core.x = pos.x;
        this.core.y = pos.y;

        // Nebula capture: find closest info particle to core (no frozen req)
        if (this._summonActive || (this._nebula && this._nebula.active)) {
          // Build set of already-captured song_ids for dedup
          const capturedIds = new Set(this._capturedParticles.map(function(p) { return p.song_id; }));
          let closest = null, closestDist = 60;
          for (const lyr of [this._colsFar, this._colsMid, this._colsNear]) {
            for (const col of lyr) {
              for (const c of col.stream) {
                if (!c._tag || c._swallowed || capturedIds.has(c._tag)) continue;
                const dx = c.x - this.core.x;
                const dy = c.y - this.core.y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < closestDist) { closestDist = dist; closest = c; }
              }
            }
          }
          this._captureTarget = closest;
          if (closest) {
            if (closestDist < 15) {
              // Swallow!
              closest._swallowed = true;
              closest._swallowStart = performance.now();
              closest._swallowX = closest.x;
              closest._swallowY = closest.y;
              this._capturedParticles.push({
                song_id: closest._tag,
                title: (closest._ewd && closest._ewd.title) || '',
                energy: (closest._ewd && closest._ewd.energy != null) ? closest._ewd.energy : 0.5,
                warmth: (closest._ewd && closest._ewd.warmth != null) ? closest._ewd.warmth : 0.5,
                density: (closest._ewd && closest._ewd.density != null) ? closest._ewd.density : 0.5
              });
              this._captureTarget = null;
            } else {
              // Visual scale feedback: 45px→1.0x, 15px→1.8x
              closest._captureScale = Math.max(1.0, 1.8 - (closestDist - 15) * 0.027);
              // Magnetic pull: drift toward core
              const pullStrength = 0.15 * (1 - closestDist / 60);
              closest.vx = (closest.vx || 0) + (this.core.x - closest.x) * pullStrength * 0.1;
              closest.vy = (closest.vy || 0) + (this.core.y - closest.y) * pullStrength * 0.1;
            }
          }
        }
      }
    };
    const end = (e) => {
      if (!_swiping && !this._dragging) return;
      clearTimeout(_pressTimer);
      if (this._summonActive) this.endSummon();

      if (this._dragging) {
        this._returning = true;
        this._retVX = 0;
        this._retVY = 0;
        // Reverse embodiment: release position → music zone
        if (typeof this.onCoreRelease === 'function') {
          const w = this.canvas.width, h = this.canvas.height;
          const rx = (this.core.x - w / 2) / (w / 2);  // -1(left) to +1(right)
          const ry = (this.core.y - h / 2) / (h / 2);  // -1(top) to +1(bottom)
          const dist = Math.sqrt(rx * rx + ry * ry);
          if (dist > 0.25) {  // dead zone: ignore small drags
            this.onCoreRelease({ x: this.core.x, y: this.core.y, rx: rx, ry: ry, dist: dist });
          }
        }
      }
      this._dragging = false;
      _swiping = false;
      this.canvas.style.cursor = '';
    };
    window.addEventListener('mousedown', start);
    window.addEventListener('touchstart', start, { passive: false });
    // Particle stirring during time warp
    let _warpPrevX = 0, _warpPrevY = 0;
    const warpStir = (e) => {
      if (!this._timeWarp) return;
      const pos = this._eventPos(e);
      const bubbleR = this._timeWarpBubble || 600;
      this._lastWarpInteract = performance.now();
      const moveX = pos.x - _warpPrevX;
      const moveY = pos.y - _warpPrevY;
      _warpPrevX = pos.x; _warpPrevY = pos.y;
      const moveMag = Math.sqrt(moveX * moveX + moveY * moveY);
      if (moveMag < 1) return;
      const ndx = moveX / moveMag, ndy = moveY / moveMag;
      for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
        for (const col of layer) {
          for (const c of col.stream) {
            const dx = c.x - pos.x, dy = c.y - pos.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < 80 && dist > 2) {
              const stir = (1 - dist / 80) * moveMag * 0.4;
              c.vx = (c.vx || 0) + ndx * stir;
              c.vy = (c.vy || 0) + ndy * stir;
            }
          }
        }
      }
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('touchmove', move, { passive: false });
    window.addEventListener('mousemove', warpStir);
    window.addEventListener('touchmove', warpStir, { passive: false });
    window.addEventListener('mouseup', end);
    window.addEventListener('touchend', end);
    window.addEventListener('touchcancel', end);
  }

  _eventPos (e) {
    // touchend/touchcancel: active touches are empty, use changedTouches
    if (e.touches && e.touches.length === 0 && e.changedTouches && e.changedTouches.length > 0) {
      const t = e.changedTouches[0];
      return { x: t.clientX, y: t.clientY };
    }
    const t = (e.touches && e.touches.length) ? e.touches[0] : e;
    return t ? { x: t.clientX, y: t.clientY } : { x: 0, y: 0 };
  }

  updateParams (params, lerpSpeed) {
    Object.assign(this._targetParams, params);
    if (lerpSpeed !== undefined) this._lerpFactor = lerpSpeed;
  }

  setAudioData (data) {
    this._audio.bass  += (data.bass  - this._audio.bass)  * 0.3;
    this._audio.mid   += (data.mid   - this._audio.mid)   * 0.3;
    this._audio.treble += (data.treble - this._audio.treble) * 0.3;
    this._audio.beat = data.beat;
  }

  setBreath (rate, depth) {
    if (rate !== undefined) this._breathRate = rate;
    if (depth !== undefined) this._breathDepth = depth;
  }

  setCoreMode (mode) {
    if (this._coreMode !== mode) {
      this._coreMode = mode;
      this._coreModeStart = performance.now();
    }
    if (mode === 'vortex') {
      this._coreModeStart = performance.now();
    }
    if (mode === 'dot' && this._coreModeStart && performance.now() - this._coreModeStart < 2000) {
      this._coreMode = 'vortex';
      this._pendingDot = true;
    }
  }

  /* ── Shape morphing: LLM-controllable core shape ── */
  _shapeRadius (shape, theta) {
    switch (shape) {
      case 'circle':     return 1;
      case 'star':       return 0.55 + 0.45 * Math.abs(Math.cos(theta * 2.5));
      case 'diamond':    return 1 / (Math.abs(Math.cos(theta)) + Math.abs(Math.sin(theta)));
      case 'hexagon': {
        const seg = Math.PI / 3;
        const a = ((theta % seg) + seg) % seg - seg / 2;  // angle within segment [-π/6, π/6]
        return Math.cos(seg / 2) / Math.cos(a);
      }
      case 'heart': {
        // Heart in polar: r = 1 + 0.45*(sin(θ) - 0.3*sin(3θ))
        return 1 + 0.45 * (Math.sin(theta) - 0.3 * Math.sin(3 * theta));
      }
      case 'pulse_ring': {
        const pulse = 0.7 + 0.3 * Math.sin(theta * 3 + performance.now() / 500);
        return pulse;
      }
      case 'bloom': {
        // 6-petal flower: r oscillates 6 times per revolution
        return 0.45 + 0.55 * Math.abs(Math.cos(theta * 3));
      }
      case 'swirl': {
        // 3-arm spiral: arms twist outward as angle increases
        return 0.55 + 0.45 * Math.cos(3 * theta + theta * 0.6);
      }
      case 'drop': {
        // Teardrop: pointy at top (θ=π/2 → min r), round at bottom
        return 0.5 + 0.5 * Math.sin(theta / 2 + Math.PI / 4);
      }
      default: return 1;
    }
  }

  _buildShapeVerts (shape, radius, cx, cy) {
    const n = 80;  // vertex count
    const pts = [];
    for (let i = 0; i < n; i++) {
      const theta = (i / n) * Math.PI * 2;
      const r = radius * this._shapeRadius(shape, theta);
      pts.push({ x: cx + Math.cos(theta) * r, y: cy + Math.sin(theta) * r });
    }
    return pts;
  }

  _shapeRingParams (shape, breath, beatFlash, grabFlash) {
    // Per-shape ring rendering: lineWidth, outerGlow, innerGlow, innerAlpha, extra
    const bf = beatFlash || 1;
    const gf = grabFlash || 1;
    switch (shape) {
      case 'star':
        return { lineWidth: 2.5, glowAlpha: 0.48 * bf * gf, innerAlpha: 0.012, tips: true };
      case 'heart':
        return { lineWidth: 5, glowAlpha: 0.38 * bf * gf, innerAlpha: 0.04, bottomGlow: true };
      case 'diamond':
        return { lineWidth: 2, glowAlpha: 0.55 * bf * gf, innerAlpha: 0.008, sharpCorners: true };
      case 'hexagon':
        return { lineWidth: 3.5, glowAlpha: 0.42 * bf * gf, innerAlpha: 0.02, cornerDots: true };
      case 'pulse_ring': {
        const pw = 2 + 3 * Math.abs(Math.sin(performance.now() / 200));
        return { lineWidth: pw, glowAlpha: (0.38 + 0.2 * Math.abs(Math.sin(performance.now() / 200))) * bf * gf, innerAlpha: 0.02 };
      }
      case 'bloom':
        return { lineWidth: 4, glowAlpha: 0.35 * bf * gf, innerAlpha: 0.035, doubleLayer: true };
      case 'swirl':
        return { lineWidth: 3, glowAlpha: 0.5 * bf * gf, innerAlpha: 0.02, tailArcs: true };
      case 'drop':
        return { lineWidth: 4.5, glowAlpha: 0.38 * bf * gf, innerAlpha: 0.05, bottomPool: true };
      default: // circle
        return { lineWidth: 4, glowAlpha: 0.36 * bf * gf, innerAlpha: 0.025 };
    }
  }

  setShape (shape) {
    if (!shape || shape === this._shapeTarget) return;
    // Snapshot current visible vertices as morph start
    this._shapeFromVerts = this._buildShapeVerts(this._shapeTarget, 1, 0, 0);
    this._shapeTarget = shape;
    this._shapeMorphT = 0;
  }

  _drawShapePath (ctx, verts) {
    if (!verts || verts.length < 3) return;
    ctx.beginPath();
    ctx.moveTo(verts[0].x, verts[0].y);
    for (let i = 1; i < verts.length; i++) {
      ctx.lineTo(verts[i].x, verts[i].y);
    }
    ctx.closePath();
  }

  /* ── Particle memory: per-particle interaction fingerprint ── */
  recordInteraction (p, type) {
    if (!p) return;
    p.mem = (p.mem || 0) + 1;
    p.memType = type;
    this._memory.totalInteractions += 1;
    this._memoryDirty = true;
    /* batch save every 5s */
    if (!this._memorySaveTimer) {
      const self = this;
      this._memorySaveTimer = setTimeout(() => {
        self._saveMemory();
        self._memorySaveTimer = null;
      }, 5000);
    }
  }

  _loadMemory () {
    try {
      const raw = localStorage.getItem('malio_particle_memory');
      return raw ? JSON.parse(raw) : { totalInteractions: 0, sessions: 0 };
    } catch (e) { return { totalInteractions: 0, sessions: 0 }; }
  }

  _saveMemory () {
    this._memory.sessions += 1;
    try { localStorage.setItem('malio_particle_memory', JSON.stringify(this._memory)); }
    catch (e) { /* storage full or unavailable */ }
  }

  setSongLibrary (songs) {
    this._infoChars = [];  // each entry = char[] (full title as phrase)
    this._infoTags = [];
    this._songData = {};   /* song_id → {energy, warmth, density, title} */
    if (!songs || !songs.length) return;
    for (const s of songs) {
      const title = s.title || '';
      const chars = title.replace(/\s/g, '').split('');
      if (chars.length === 0) continue;
      this._infoChars.push(chars);
      this._infoTags.push(s.id);
      this._songData[s.id] = {
        energy: s.energy != null ? s.energy : 0.5,
        warmth: s.warmth != null ? s.warmth : 0.5,
        density: s.density != null ? s.density : 0.5,
        title: title
      };
    }
  }

  _infoChar () {
    if (this._infoChars.length === 0) return null;
    // During summon: dramatically boost info particle spawn rate for capture
    const spawnChance = (this._summonActive || (this._nebula && this._nebula.active)) ? 0.25 : 0.03;
    if (Math.random() < spawnChance) {
      const i = Math.floor(Math.random() * this._infoChars.length);
      const tag = this._infoTags[i];
      const sd = this._songData[tag] || {};
      return {
        chars: this._infoChars[i], tag: tag,
        energy: sd.energy != null ? sd.energy : 0.5,
        warmth: sd.warmth != null ? sd.warmth : 0.5,
        density: sd.density != null ? sd.density : 0.5,
        title: sd.title || ''
      };
    }
    return null;
  }

  /* ── Find a column that currently has NO info particle ────── */
  _findFreeInfoColumn () {
    const allCols = [...this._colsFar, ...this._colsMid, ...this._colsNear];
    const free = allCols.filter(c => !this._infoCols.has(c));
    if (free.length === 0) return null;
    return free[Math.floor(Math.random() * free.length)];
  }

  /* ── Check if any particle occupies the top `range` px of a column ─ */
  _columnTopOccupied (col, range) {
    for (const c of col.stream) {
      if (c.y < range && c.y > -FONT_SIZE) return true;
    }
    return false;
  }

  setTimeLevel (targetLevel, transitionSec) {
    this._timeLevel = this._timeLevel + (this._timeTarget - this._timeLevel) * this._timeLerp;
    this._timeTarget = targetLevel;
    this._timeLerp = 0;
    this._timeLerpSpeed = 1 / (transitionSec * 60);
  }

  triggerLightBurst (coverColor) {
    const color = coverColor || this._targetParams.color || '#22C55E';
    this._burst = {
      start: performance.now(),
      color: color,
      waves: [
        { delay: 0,   speed: 250, duration: 200, maxR: 280, ampNear: 22, ampFar: 5, cycle: 150, brightUp: 1.2, brightDown: 0.8, colorShift: 0.1, colorDir: 'blue', stretch: 0.10 },
        { delay: 120, speed: 200, duration: 250, maxR: 240, ampNear: 17, ampFar: 3.5, cycle: 160, tintColor: color, tintStrength: 0.3, stretch: 0.05 },
        { delay: 240, speed: 180, duration: 300, maxR: 200, ampNear: 12, ampFar: 2.5, cycle: 170, alphaDrop: 0.85, stretch: 0 },
      ]
    };
    this._coreExpand = performance.now();
  }

  triggerSwipeRipple (dir) {
    const now = performance.now();
    const color = this._targetParams.color || '#22C55E';
    /* directional bias: push ripple slightly to match swipe direction */
    const dirX = dir === 'right' ? 1 : -1;
    this._burst = {
      start: now,
      color: color,
      dirX: dirX,
      waves: [
        { delay: 0,   speed: 220, duration: 180, maxR: 240, ampNear: 20, ampFar: 4, cycle: 130, brightUp: 1.3, dirPush: dirX * 0.6 },
        { delay: 100, speed: 180, duration: 220, maxR: 200, ampNear: 14, ampFar: 3,  cycle: 150, tintColor: color, tintStrength: 0.25, dirPush: dirX * 0.3 },
        { delay: 200, speed: 150, duration: 280, maxR: 170, ampNear: 9,  ampFar: 2,  cycle: 160, alphaDrop: 0.88, dirPush: dirX * 0.15 },
      ]
    };
    this._coreExpand = now;
    /* fire callback after ripple starts */
    const self = this;
    setTimeout(() => {
      if (typeof self.onSwipe === 'function') {
        self.onSwipe(dir);
      }
    }, 220);
  }

  startSummon () {
    this._summonActive = true;
    this._summonStart = performance.now();
    this._nebula = null;  // reset — will be created when particles converge
  }

  endSummon () {
    this._summonActive = false;
    this._summonStart = 0;
    const h = this.canvas.height || 1080;
    const hadCaptures = this._capturedParticles.length > 0;

    // Exit nebula if active
    if (this._nebula) {
      this._nebula.exit();
      this._nebula = null;
    }

    // Clean up capture state
    this._captureTarget = null;

    for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
      for (const col of layer) {
        for (const c of col.stream) {
          // Reset swallow state
          c._swallowed = false;
          c._swallowStart = null;
          c._captureScale = null;
          if (c._frozen) {
            c._frozen = false;
            c._frozenY = null;
            // Reset to column X, scatter Y across screen
            c.x = col.x;
            c.y = -10 - Math.random() * h;
          }
        }
      }
    }

    // Fire capture callback
    if (hadCaptures && typeof this.onCaptureComplete === 'function') {
      const captured = this._capturedParticles.slice();
      this._capturedParticles = [];
      this.onCaptureComplete(captured);
    } else {
      this._capturedParticles = [];
    }
  }

  /* ── Search mode ──────────────────────────────────────── */

  startSearch () {
    this._searchMode = true;
    this._searchInputLen = 0;
    if (this._summonActive) this.endSummon();
    if (typeof this.onSearchStart === 'function') this.onSearchStart();
  }

  endSearch () {
    this._searchMode = false;
    this._searchInputLen = 0;
    if (typeof this.onSearchEnd === 'function') this.onSearchEnd();
  }

  updateSearchInput (len) {
    this._searchInputLen = Math.max(0, len);
  }

  triggerSearchCollapse () {
    this._searchMode = false;
    if (typeof this.onSearchCollapse === 'function') this.onSearchCollapse();
  }

  _resize () {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
    this._homeX = this.canvas.width / 2;
    this._homeY = this.canvas.height / 2;
    if (!this._dragging && !this._returning) {
      this.core.x = this._homeX;
      this.core.y = this._homeY;
    }
  }

  _buildColumns () {
    const w = this.canvas.width || 1920;
    const h = this.canvas.height || 1080;
    const maxStack = Math.ceil(h / CHAR_GAP) + 2;
    const totalCols = Math.floor((w - 20) / COL_GAP);

    const counts = {
      far:  Math.round(totalCols * LAYERS[0].ratio),
      mid:  Math.round(totalCols * LAYERS[1].ratio),
      near: totalCols - Math.round(totalCols * LAYERS[0].ratio) - Math.round(totalCols * LAYERS[1].ratio),
    };

    this._colsFar  = this._buildLayer(LAYERS[0], counts.far, maxStack, w, h);
    this._colsMid  = this._buildLayer(LAYERS[1], counts.mid, maxStack, w, h);
    this._colsNear = this._buildLayer(LAYERS[2], counts.near, maxStack, w, h);
  }

  _buildLayer (layer, count, maxStack, w, h) {
    const cols = [];
    const step = (w - 30) / Math.max(1, count);
    for (let i = 0; i < count; i++) {
      let x = 15 + i * step + (Math.random() - 0.5) * step * 0.6;
      // Micro horizontal offset based on z
      x += (layer.z - 0.5) * 6 * (Math.random() - 0.5);

      const speedBase = layer.speedMul * (0.7 + Math.random() * 0.6);
      const speedPhase = Math.random() * Math.PI * 2;       // column phase
      const speedPeriod = 2000 + Math.random() * 1000;       // 2-3s
      const stream = [];
      for (let j = 0; j < maxStack; j++) {
        stream.push({
          char: randChars(),
          x: x, y: -(j * CHAR_GAP) - Math.random() * h,
          vx: 0, vy: 0,
          tick: Math.floor(Math.random() * 30),
          phaseOff: (Math.random() - 0.5) * 0.3,
          mem: 0,     /* interaction count — user fingerprint */
          memType: 0, /* 0=none, 1=drag, 2=burst, 3=core, 4=capture */
        });
      }
      cols.push({ x, stream, speedBase, speedPhase, speedPeriod, layer });
    }
    return cols;
  }

  _animate () {
    const now = performance.now();
    const dt = Math.min((now - this._lastFrame) / 16, 3);
    this._lastFrame = now;

    if (this._targetParams.speed !== this.params.speed) {
      this.params.speed += (this._targetParams.speed - this.params.speed) * this._lerpFactor;
    }

    // Smooth color lerp — fast, toward _targetParams.color
    const targetColor = this._targetParams.color || '#22C55E';
    if (!this.params.color) this.params.color = targetColor;
    const tcDiff = this.params.color !== targetColor;
    if (tcDiff) {
      const tr = parseInt(targetColor.slice(1, 3), 16), tg = parseInt(targetColor.slice(3, 5), 16), tb = parseInt(targetColor.slice(5, 7), 16);
      const cr = parseInt(this.params.color.slice(1, 3), 16), cg = parseInt(this.params.color.slice(3, 5), 16), cb = parseInt(this.params.color.slice(5, 7), 16);
      const f = Math.min(1, this._lerpFactor);
      const nr = Math.round(cr + (tr - cr) * f);
      const ng = Math.round(cg + (tg - cg) * f);
      const nb = Math.round(cb + (tb - cb) * f);
      const next = '#' + nr.toString(16).padStart(2, '0') + ng.toString(16).padStart(2, '0') + nb.toString(16).padStart(2, '0');
      // Snap if close
      const dist = Math.abs(tr - nr) + Math.abs(tg - ng) + Math.abs(tb - nb);
      this.params.color = dist < 15 ? targetColor : next;
    }

    // Use lerped color for particle + core rendering
    const tc = this.params.color || targetColor;
    const _rr = parseInt(tc.replace('#', '').substring(0, 2), 16);
    const _gg = parseInt(tc.replace('#', '').substring(2, 4), 16);
    const _bb = parseInt(tc.replace('#', '').substring(4, 6), 16);

    // Emotional return physics — core drifts back to home after drag
    if (this._returning && !this._dragging) {
      const dx = this._homeX - this.core.x;
      const dy = this._homeY - this.core.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 0.5) {
        this.core.x = this._homeX;
        this.core.y = this._homeY;
        this._returning = false;
        this._settled = true;
        this._settleTime = performance.now();
        this._retVX = 0;
        this._retVY = 0;
      } else {
        // Spring-damper with speed cap
        const springK = 0.008;  // stiffness
        const damping = 0.94;   // friction
        const maxSpeed = 5;     // ~300px/s at 60fps
        this._retVX = (this._retVX + (dx / dist) * springK * dist) * damping;
        this._retVY = (this._retVY + (dy / dist) * springK * dist) * damping;
        const spd = Math.sqrt(this._retVX * this._retVX + this._retVY * this._retVY);
        if (spd > maxSpeed) {
          this._retVX = (this._retVX / spd) * maxSpeed;
          this._retVY = (this._retVY / spd) * maxSpeed;
        }
        this.core.x += this._retVX;
        this.core.y += this._retVY;
      }
    }

    // ── Water ripple spawn: driven by core velocity ──
    const coreVX = this.core.x - this._prevCoreX;
    const coreVY = this.core.y - this._prevCoreY;
    const coreSpeed = Math.sqrt(coreVX * coreVX + coreVY * coreVY);
    this._prevCoreX = this.core.x;
    this._prevCoreY = this.core.y;
    this._rippleTimer += 1;
    // Spawn ripple when core moves fast enough, max every 3 frames
    if (coreSpeed > 0.4 && this._rippleTimer > 3) {
      this._rippleTimer = 0;
      this._ripples.push({
        x: this.core.x, y: this.core.y,
        r: this.core.r * 0.6,       // start at core edge
        maxR: this.core.r * 0.6 + coreSpeed * 35,  // bigger ripple for faster movement
        alpha: Math.min(0.2, coreSpeed * 0.04),     // brighter for faster
        birth: performance.now()
      });
      // Cap total ripples
      if (this._ripples.length > 12) this._ripples.shift();
    }

    // Time fade level lerp
    if (this._timeLerp < 1) {
      this._timeLerp = Math.min(1, this._timeLerp + this._timeLerpSpeed);
    }
    const t = this._timeLerp;
    const level = this._timeLevel + (this._timeTarget - this._timeLevel) * t;
    // Level coefficients: [speed, nearBright, midBright, farBright]
    const LEVELS = [
      [1.0,  1.0, 1.0,  1.0],    // 0: full
      [0.9,  1.0, 0.9,  0.8],    // 1: dim
      [0.75, 0.9, 0.8,  0.65],   // 2: soft
      [0.5,  0.8, 0.65, 0.5],    // 3: deep
      [0.35, 0.7, 0.5,  0.35],   // 4: sleep
    ];
    const L = LEVELS[Math.round(level)] || LEVELS[0];
    const fadeSpeed = L[0];
    const fadeBright = [L[1], L[2], L[3]]; // near, mid, far

    /* ── audio reactivity ──────────────────────────────── */
    const a = this._audio;
    const audioPulse = 1 + a.bass * 0.3 + a.mid * 0.15 + a.treble * 0.08 + a.beat * 0.25;

    /* ── beat-triggered core pulse ─────────────────────── */
    if (a.beat) {
      this._coreExpand = performance.now();
      this._beatFlash = performance.now();
    }

    const h = this.canvas.height;
    const w = this.canvas.width;
    const spd = this.params.speed * audioPulse;
    const ctx = this.ctx;

    /* trail fade modulated by audio energy */
    const dynamicFade = this._fadeAlpha * (1 - a.bass * 0.15);
    ctx.fillStyle = 'rgba(0,0,0,' + dynamicFade + ')';
    ctx.fillRect(0, 0, w, h);

    // Water ripple burst — sine wave oscillation from core
    if (this._burst) {
      const elapsed = now - this._burst.start;
      if (elapsed > 700) { this._burst = null; }
      else {
        const cx = this.core.x, cy = this.core.y;
        const coreImmune = 25;
        for (const w of this._burst.waves) {
          const wt = (elapsed - w.delay) / w.duration;
          if (wt < 0 || wt > 1.2) continue;
          const waveCenter = wt * w.speed;
          const waveWidth = 50;
          const waveInner = Math.max(0, waveCenter - waveWidth);
          const waveOuter = waveCenter + waveWidth;
          for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
            for (const col of layer) {
              for (const c of col.stream) {
                const dist = Math.sqrt((col.x - cx) ** 2 + (c.y - cy) ** 2);
                if (dist < coreImmune || dist > w.maxR) continue;
                if (dist >= waveInner && dist <= waveOuter) {
                  const inWave = (dist - waveInner) / waveWidth;
                  const ampFactor = 1 - dist / w.maxR;
                  const amp = w.ampFar + (w.ampNear - w.ampFar) * ampFactor;
                  const phase = inWave * Math.PI * 2;
                  c._wY = (c._wY || 0) + Math.sin(phase) * amp;
                  if (w.brightUp) c._wbright = c._wbright || 1;
                  if (w.alphaDrop) c._walpha = (c._walpha || 1) * w.alphaDrop;
                  if (w.tintColor) c._wtint = w.tintColor;
                  if (w.stretch) c._wstretch = 1 + (c._wstretch || 0) * 0.3 + w.stretch * Math.cos(phase);
                  /* directional push for swipe ripple */
                  if (w.dirPush) {
                    const pushForce = w.dirPush * Math.cos(phase) * ampFactor;
                    c.vx = (c.vx || 0) + pushForce * 0.8;
                  }
                }
              }
            }
          }
        }
      }
    }

    // Process pending info particle respawns (delayed, column-exclusive)
    if (this._infoPending.length > 0) {
      const nextPending = [];
      for (const pend of this._infoPending) {
        if (now < pend.readyAt) { nextPending.push(pend); continue; }
        const freeCol = this._findFreeInfoColumn();
        if (!freeCol) { nextPending.push(pend); continue; }
        if (this._columnTopOccupied(freeCol, 60)) { nextPending.push(pend); continue; }
        const c = pend.particle;
        c.x = freeCol.x;
        c.y = -10 - Math.random() * 30;
        const infoR = this._infoChar();
        if (infoR) {
          c.char = infoR.chars; c._tag = infoR.tag;
          c._ewd = { energy: infoR.energy, warmth: infoR.warmth, density: infoR.density };
          c._rgb = ewdToRgb(infoR.energy, infoR.warmth, infoR.density);
          c._infoSpeedMul = 1.15 + Math.random() * 0.15;
          c.tick = 0;
          this._infoCols.add(freeCol);
        } else { c.char = randChars(); c._tag = null; }
      }
      this._infoPending = nextPending;
    }

    // Clear capture scale from non-target particles each frame
    for (const lyr of [this._colsFar, this._colsMid, this._colsNear]) {
      for (const col of lyr) {
        for (const c of col.stream) {
          if (c !== this._captureTarget && c._captureScale) c._captureScale = null;
        }
      }
    }

    let _lastColSize = -1;

    // Draw order: far (z=1) → mid (z=0.5) → near (z=0)
    const allLayers = [this._colsFar, this._colsMid, this._colsNear];

    let layerIdx = 2; // far=2, mid=1, near=0 (reverse of draw order)
    for (const columns of allLayers) {
     const layerFade = fadeBright[layerIdx] || 1;
     layerIdx--;
     for (const col of columns) {
      const { x, stream, speedBase, speedPhase, speedPeriod, layer } = col;
      const colSize = layer.size;
      if (colSize !== _lastColSize) {
        ctx.font = colSize + 'px "JetBrains Mono", monospace';
        _lastColSize = colSize;
      }
      // Per-column micro speed variation (±15%, sine ease-in-out)
      const speedVar = 1 + 0.15 * Math.sin(speedPhase + now / speedPeriod * Math.PI * 2);
      const baseSpeed = speedBase * speedVar;
      // Time warp: bubble radius update (per-column)
      const baseStep = baseSpeed * spd * dt * fadeSpeed;
      if (this._timeWarp) {
        const warpAge = now - this._timeWarpStart;
        this._timeWarpBubble = warpAge < 300 ? (warpAge / 300) * 600 : 600;
      }
      // Spacing follows speed proportionally
      const colGap = CHAR_GAP * speedVar;

      for (const c of stream) {
        // Per-particle warp factor
        let warpMul = 1, warpBoost = 1;
        if (this._timeWarp) {
          const cx = this.core.x, cy = this.core.y;
          const wdist = Math.sqrt((col.x - cx) ** 2 + (c.y - cy) ** 2);
          if (wdist < this._timeWarpBubble) {
            const t = wdist / this._timeWarpBubble;
            if (t < 0.08) { warpMul = 0.03; warpBoost = 1.6; }
            else if (t < 0.25) { warpMul = 0.08; warpBoost = 1.3; }
            else if (t < 0.5) { warpMul = 0.20; warpBoost = 1.1; }
            else { warpMul = 0.45; }
          }
        }
        // Summon mode: freeze info particles, drift toward orbital rings
        if (this._summonActive && c._tag) {
          if (!c._frozen) {
            c._frozen = true; c._frozenY = c.y;
            c._frozenX = c.x; c._frozenY0 = c.y;
            // One per column, lined up below the core
            // X stays at column position. Y: below core, energy determines offset.
            const e = (c._ewd && c._ewd.energy != null) ? c._ewd.energy : 0.5;
            const offsetY = 50 + (1 - e) * 50 + (Math.random() - 0.5) * 20;
            c._driftTargetX = col.x;           // stay in own column
            c._driftTargetY = this.core.y + offsetY;  // below core
            // Drift duration: ~2s, slight variation
            const dx = c._driftTargetX - c.x;
            const dy = c._driftTargetY - c.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            c._driftDuration = 1200 + dist * 2.5 + Math.random() * 600;
            c._driftStart = now;
          }
          const elapsed = now - c._driftStart;
          if (!this._nebula && elapsed > 300) {
            // Ease-in cubic: slow at start, fast at end
            let t = Math.min(elapsed / c._driftDuration, 1.0);
            t = t * t * t;  // cubic ease-in
            c.x = c._frozenX + (c._driftTargetX - c._frozenX) * t;
            c.y = c._frozenY0 + (c._driftTargetY - c._frozenY0) * t;
          }
          // Once nebula is active, positions driven by NebulaEngine._updatePhysics(dt)
        } else {
          c.y += baseStep * warpMul * (c._infoSpeedMul || 1) + (c.vy || 0) * dt;
        }
        // Wave effect decay
        if (c._wY) c._wY *= 0.92;
        if (c._wstretch && c._wstretch !== 1) c._wstretch = 1 + (c._wstretch - 1) * 0.9;
        if (c._wtint) c._wtint = null; // single-frame tint
        if (c._wbright && c._wbright !== 1) c._wbright = 1 + (c._wbright - 1) * 0.92;
        if (c._walpha && c._walpha !== 1) c._walpha = 1 + (c._walpha - 1) * 0.92;

        // Spring-back to column X (skip frozen particles — they're in drift/nebula)
        if (!c._frozen) {
          const springK = 0.06;
          if (c.vx || Math.abs(c.x - col.x) > 1) {
            c.x += (c.vx || 0) * dt + (col.x - c.x) * springK;
            c.vx *= 0.88;
          }
          if (Math.abs(c.x - col.x) > 200) { c.x = col.x; c.vx = 0; }
        }
        if (c.vy) { c.vy *= 0.85; }
        if (this._summonActive && c._tag) {
          // During summon: skip char cycling + respawn, but continue to draw
          c.tick++;
        } else {
          c.tick++;
          if (c.tick > 40 + Math.floor(Math.random() * 50)) {
            c.tick = 0;
            const info = this._infoChar();
            const isSummon = this._summonActive || (this._nebula && this._nebula.active);
            if (info && !isSummon && this._infoCols.has(col)) { /* column occupied — stay random */ }
            else if (info) {
              if (c._tag) this._infoCols.delete(col);
              c.char = info.chars; c._tag = info.tag;
              c._ewd = { energy: info.energy, warmth: info.warmth, density: info.density };
              c._rgb = ewdToRgb(info.energy, info.warmth, info.density);
              c._infoSpeedMul = 1.15 + Math.random() * 0.15;
              if (!isSummon) this._infoCols.add(col);  // don't block column during summon
            } else {
              if (c._tag) this._infoCols.delete(col); // was info, now normal
              c.char = randChars(); c._tag = null; c._ewd = null; c._rgb = null; c._infoSpeedMul = 0;
            }
          }
          if (c.y > h + FONT_SIZE) {
            if (c._tag) {
              // Info particle: queue for delayed respawn in a free column
              this._infoCols.delete(col);
              c._tag = null; c._ewd = null; c._rgb = null; c._infoSpeedMul = 0;
              this._infoPending.push({
                particle: c,
                readyAt: now + 500 + Math.random() * 1500  // 0.5-2s delay
              });
              c.y = h + 9999;  // hide far off screen
              c.tick = 0;
            } else {
              // Normal particle: immediate respawn in same column
              c.y -= h + stream.length * CHAR_GAP + 20;
              const info2 = Math.random() < 0.5 ? this._infoChar() : null;
              const isSummon2 = this._summonActive || (this._nebula && this._nebula.active);
              if (info2 && !isSummon2 && this._infoCols.has(col)) { /* column occupied */ }
              else if (info2) {
                c.char = info2.chars; c._tag = info2.tag;
                c._ewd = { energy: info2.energy, warmth: info2.warmth, density: info2.density };
                c._rgb = ewdToRgb(info2.energy, info2.warmth, info2.density);
                c._infoSpeedMul = 1.15 + Math.random() * 0.15;
                if (!isSummon2) this._infoCols.add(col);
              } else { c.char = randChars(); c._tag = null; c._ewd = null; c._rgb = null; c._infoSpeedMul = 0; }
              c.tick = 0;
            }
          }
        }

        if (c.y < -FONT_SIZE || c.y > h + FONT_SIZE) continue;

        // Normalise chars: always a flat array of single-character strings
        let chars = c.char;
        if (typeof chars === 'string') chars = chars.split('');
        else if (!Array.isArray(chars)) chars = [];
        // Flatten in case of nested arrays (defensive)
        if (chars.length === 1 && Array.isArray(chars[0])) chars = chars[0];

        // Core convex lens: converge + magnify
        let drawX = c.x !== undefined ? c.x : col.x;
        let drawY = c.y + (c._wY || 0);
        let lensScale = 1;
        let aberration = 0;

        // Swallowed particle: shrink into core, then skip draw
        if (c._swallowed) {
          if (!c._swallowStart) continue;
          const elapsed = performance.now() - c._swallowStart;
          if (elapsed > 200) continue; // gone, don't draw
          const t = elapsed / 200;
          lensScale = c._captureScale * (1 - t * t); // ease-in shrink
          drawX += (this.core.x - drawX) * t;
          drawY += (this.core.y - drawY) * t;
        } else if (this.core.active) {
          const dx = drawX - this.core.x;
          const dy = c.y - this.core.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const effR = this._effectiveCoreR || this.core.r;
          if (dist < effR && dist > 2) {
            const t = dist / effR;
            /* search brownian: add random jitter near core */
            if (this._searchMode && this._searchInputLen > 0) {
              const bf = 0.3 + this._searchInputLen * 0.1;
              c.vx = (c.vx || 0) + (Math.random() - 0.5) * bf;
              c.vy = (c.vy || 0) + (Math.random() - 0.5) * bf;
            }
            const strength = t * (1 - t) * 24;
            drawX -= (dx / dist) * strength;
            drawY -= (dy / dist) * strength;
            lensScale = 1 + (1 - t) * 0.5; // 1.5x at center, 1x at edge
          }
        }

        // Capture target scaling: particle grows as core approaches
        if (c._captureScale && c._captureScale > 1) {
          lensScale = Math.max(lensScale, c._captureScale);
        }

        // Luminance gradient
        const memoryBoost = 1 + Math.min(0.5, (c.mem || 0) * 0.05);
        const isSummon = this._summonActive || (this._nebula && this._nebula.active);
        const infoBoost = c._tag ? (isSummon ? 3.0 : 1.15) : 1.0;
        let yBright = (0.65 + 0.35 * Math.min(1, c.y / h)) * infoBoost * warpBoost * memoryBoost;
        if (c._wbright) yBright *= Math.min(2, c._wbright);
        const depthBright = layer.brightness * layerFade;
        const bright = yBright * depthBright;
        let r, g, b;
        if (c._rgb) {
          /* Info particle: use E/W/D energy color */
          r = Math.round(c._rgb.r * bright);
          g = Math.round(c._rgb.g * bright);
          b = Math.round(c._rgb.b * bright);
        } else {
          r = Math.round(_rr * bright);
          g = Math.round(_gg * bright);
          b = Math.round(_bb * bright);
        }
        ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
        ctx.globalAlpha = c._walpha || 1;

        if (lensScale !== 1 || (c._wstretch && c._wstretch !== 1)) {
          ctx.font = Math.round(colSize * lensScale) + 'px "JetBrains Mono", monospace';
          ctx.font = Math.round(colSize * lensScale * (c._wstretch || 1)) + 'px "JetBrains Mono", monospace';
        }
        const isPhrase = chars.length > 1;
        const phraseGap = isPhrase ? Math.max(colGap, CHAR_GAP) : colGap;
        for (let k = 0; k < chars.length; k++) {
          const py = drawY + k * phraseGap;
          const isLast = k === chars.length - 1;
          // Only last char gets full trail; preceding chars drawn dim with no staying power
          if (isPhrase && !isLast) {
            ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',0.15)';
            ctx.fillText(chars[k], drawX, py);
            continue;
          }
          if (aberration > 0.1) {
            ctx.fillStyle = 'rgba(255,0,0,0.25)';
            ctx.fillText(chars[k], drawX + aberration, py);
            ctx.fillStyle = 'rgba(0,0,255,0.25)';
            ctx.fillText(chars[k], drawX - aberration, py);
          }
          ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
          ctx.fillText(chars[k], drawX, py);
        }
      }
     }
    }

    // Nebula: create engine when summon has converged particles (>600ms)
    if (this._summonActive && !this._nebula && (now - this._summonStart) > 600) {
      const frozen = [];
      for (const lyr of [this._colsFar, this._colsMid, this._colsNear]) {
        for (const col of lyr) {
          for (const c of col.stream) {
            if (c._frozen && c._tag) frozen.push(c);
          }
        }
      }
      if (frozen.length > 2 && typeof NebulaEngine !== 'undefined') {
        this._nebula = new NebulaEngine(this.canvas, this.ctx, this);
        this._nebula.enter(frozen);
      }
    }

    // Nebula physics: drive gravitational clustering once per frame
    if (this._nebula && this._nebula.active) {
      this._nebula._updatePhysics(dt);
    }

    // Core lens — nearly invisible, perceived only through refraction
    if (this.core.active) {
      /* search mode: core shrinks to 20 over 0.3s */
      let coreR = this.core.r * (1 + 0.12 * this._breathDepth * Math.sin(this._breathPhase));
      if (this._searchMode) {
        const targetR = 20;
        coreR += (targetR - coreR) * 0.12;
      }
      this._effectiveCoreR = coreR;
      const cx = this.core.x, cy = this.core.y, cr = coreR;
      const mode = this._coreMode;

      // Release pending dot after minimum vortex duration (2s)
      if (this._pendingDot && this._coreModeStart && performance.now() - this._coreModeStart > 2000) {
        this._coreMode = 'dot';
        this._pendingDot = false;
      }

      const isCircle = this._coreShape === 'circle' && this._shapeMorphT >= 1;
      /* ── vortex mode: spinning ring particles ────────── */
      if (mode === 'vortex' && !this._timeWarp && isCircle) {
        ctx.strokeStyle = this._targetParams.color || '#22C55E';
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.6;
        const vortexPhase = (performance.now() / 300) % (Math.PI * 2);
        for (let i = 0; i < 3; i++) {
          ctx.beginPath();
          ctx.arc(cx, cy, cr + 5 + i * 6, vortexPhase + i * 2, vortexPhase + i * 2 + Math.PI * 1.5);
          ctx.stroke();
        }
      }

      /* ── error mode: red flicker → brownian → pulse heal ── */
      if (mode === 'error' && isCircle) {
        const sinceError = performance.now() - (this._coreModeStart || 0);
        /* phase 1: flicker (0-900ms) */
        if (sinceError < 900) {
          const flicker = Math.abs(Math.sin(sinceError / 75)) * 0.7;
          ctx.fillStyle = `rgba(255, ${flicker > 0.3 ? 0 : 255}, ${flicker > 0.3 ? 0 : 255}, ${flicker})`;
          ctx.beginPath();
          ctx.arc(cx, cy, cr + 14, 0, Math.PI * 2);
          ctx.fill();
        }
        /* phase 2: dim red dot + brownian (900-4000ms) */
        if (sinceError >= 900 && sinceError < 4000) {
          ctx.fillStyle = 'rgba(255, 40, 40, 0.3)';
          ctx.beginPath();
          ctx.arc(cx, cy, cr * 0.6, 0, Math.PI * 2);
          ctx.fill();
          /* brownian on nearby particles */
          for (const layer of [this._colsFar, this._colsMid, this._colsNear]) {
            for (const col of layer) {
              for (const c of col.stream) {
                const d = Math.sqrt((c.x - cx) ** 2 + (c.y - cy) ** 2);
                if (d < 200) {
                  c.vx = (c.vx || 0) + (Math.random() - 0.5) * 0.6;
                  c.vy = (c.vy || 0) + (Math.random() - 0.5) * 0.6;
                }
              }
            }
          }
        }
        /* phase 3: pulse recovery (4000-5500ms) */
        if (sinceError >= 4000 && sinceError < 5500) {
          const pulseT = (sinceError - 4000) / 1500;
          const pulse = Math.sin(pulseT * Math.PI * 3) * 0.5 + 0.5;
          ctx.fillStyle = `rgba(34, 197, 94, ${pulse * 0.4})`;
          ctx.beginPath();
          ctx.arc(cx, cy, cr + 8 * pulse, 0, Math.PI * 2);
          ctx.fill();
        }
        /* after 5500ms → auto-recover */
        if (sinceError > 5500) {
          this.setCoreMode('dot');
        }
      }

      // Ring: dashed during summon, breathing otherwise
      this._breathPhase += this._summonActive ? 0.08 : this._breathRate;
      if (this._summonActive) {
        ctx.setLineDash([8, 12]);
        ctx.lineDashOffset = -this._breathPhase * 20;
        ctx.lineWidth = 2;
        ctx.strokeStyle = this._targetParams.color || '#22C55E';
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.arc(cx, cy, cr + 8, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.lineWidth = 1;
      }
      const breathBase = this._timeWarp ? 0.3 : (0.3 + this._breathDepth * Math.sin(this._breathPhase));
      let breath = breathBase;
      const rr = _rr, gg = _gg, bb = _bb;

      // Grab flash: brightness spike on initial grab, then decay
      const now = performance.now();
      const grabAge = now - this._grabTime;
      let grabFlash = 1;
      if (grabAge < 80) grabFlash = 1.4;       // spike
      else if (grabAge < 250) grabFlash = 1 + 0.4 * (1 - (grabAge - 80) / 170);  // decay

      // Beat flash: brief brightness spike on drum hit
      let beatFlash = 1;
      if (this._beatFlash) {
        const beatAge = now - this._beatFlash;
        if (beatAge < 60) beatFlash = 1.5;
        else if (beatAge < 180) beatFlash = 1 + 0.5 * (1 - (beatAge - 60) / 120);
        else this._beatFlash = 0;
      }

      // Settled deep breath on return complete
      if (this._settled && !this._dragging && !this._returning) {
        const settleAge = (now - (this._settleTime || 0));
        if (settleAge < 1200) {
          breath = 0.1 + 0.9 * Math.sin(this._breathPhase * 2);  // deeper, faster
          if (settleAge < 100) breath *= 1.3;  // extra brightness on arrival
        }
      }

      // Ring deformation during drag or return
      const stretched = this._dragging || this._returning;
      const dX = this._dragging ? this._dX : (this._returning ? (this.core.x - this._homeX) : 0);
      const dY = this._dragging ? this._dY : (this._returning ? (this.core.y - this._homeY) : 0);
      const dMag = Math.sqrt(dX * dX + dY * dY) || 1;
      const dNX = dX / dMag;  // drag direction normalized
      const dNY = dY / dMag;

      // Core expansion during burst ("石子落水")
      let coreScale = 1;
      if (this._coreExpand) {
        const ce = now - this._coreExpand;
        if (ce < 50) coreScale = 1 + 0.15 * (ce / 50);       // expand 15%
        else if (ce < 150) coreScale = 1.15 - 0.15 * ((ce - 50) / 100); // contract
        else this._coreExpand = 0;
      }
      const ringInner = cr * coreScale + 1;
      const ringOuter = cr * coreScale + 5;

      // ── Shape morph update ──
      if (this._shapeMorphT < 1) {
        this._shapeMorphT = Math.min(1, this._shapeMorphT + 0.03);
        if (this._shapeMorphT >= 1) {
          this._coreShape = this._shapeTarget;
          this._shapeFromVerts = null;
        }
      }
      if (!isCircle) {
        // ── Shape path ring ──
        const shapeRingOuter = cr * coreScale + 5;
        const shapeRingInner = cr * coreScale + 1;
        // Build target verts
        const targetOuter = this._buildShapeVerts(this._shapeTarget, shapeRingOuter, cx, cy);
        const targetInner = this._buildShapeVerts(this._shapeTarget, shapeRingInner, cx, cy);
        let outerVerts, innerVerts;
        if (this._shapeMorphT < 1 && this._shapeFromVerts) {
          // Morph: lerp from cached start verts to target
          const fromOuter = this._shapeFromVerts.map(function(v) {
            return { x: cx + v.x * shapeRingOuter, y: cy + v.y * shapeRingOuter };
          });
          const fromInner = this._shapeFromVerts.map(function(v) {
            return { x: cx + v.x * shapeRingInner, y: cy + v.y * shapeRingInner };
          });
          const t = this._shapeMorphT;
          outerVerts = targetOuter.map(function(v, i) {
            return { x: fromOuter[i].x + (v.x - fromOuter[i].x) * t, y: fromOuter[i].y + (v.y - fromOuter[i].y) * t };
          });
          innerVerts = targetInner.map(function(v, i) {
            return { x: fromInner[i].x + (v.x - fromInner[i].x) * t, y: fromInner[i].y + (v.y - fromInner[i].y) * t };
          });
        } else {
          outerVerts = targetOuter;
          innerVerts = targetInner;
        }
        // ── Per-shape ring params ──
        const ringParams = this._shapeRingParams(this._shapeTarget, breath, beatFlash, grabFlash);
        const effectiveShape = this._shapeMorphT < 1 ? 'circle' : this._shapeTarget;
        const lensParams = this._shapeMorphT < 1
          ? this._shapeRingParams('circle', breath, beatFlash, grabFlash)
          : ringParams;

        // Outer glow: shape path stroke
        ctx.strokeStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',' + ringParams.glowAlpha.toFixed(2) + ')';
        ctx.lineWidth = ringParams.lineWidth;
        ctx.globalAlpha = 1;
        this._drawShapePath(ctx, outerVerts);
        ctx.stroke();

        // Double layer (bloom): offset second petal overlay
        if (ringParams.doubleLayer) {
          const dlVerts = this._buildShapeVerts(effectiveShape, shapeRingOuter * 0.85, cx, cy);
          ctx.strokeStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (ringParams.glowAlpha * 0.5).toFixed(2) + ')';
          ctx.lineWidth = ringParams.lineWidth * 0.6;
          this._drawShapePath(ctx, dlVerts);
          ctx.stroke();
        }

        // Tail arcs (swirl): draw fading tangent arcs from each arm tip
        if (ringParams.tailArcs) {
          const n = 80;
          for (let i = 0; i < n; i += Math.floor(n / 3)) {
            const theta = (i / n) * Math.PI * 2;
            const r = shapeRingOuter * this._shapeRadius(effectiveShape, theta);
            const tx = cx + Math.cos(theta) * r;
            const ty = cy + Math.sin(theta) * r;
            ctx.beginPath();
            ctx.arc(tx, ty, 4, theta - 0.5, theta + 0.5);
            ctx.strokeStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (ringParams.glowAlpha * 0.3).toFixed(2) + ')';
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }

        // Corner dots (hexagon): small dots at vertices
        if (ringParams.cornerDots) {
          for (let i = 0; i < 6; i++) {
            const theta = (i / 6) * Math.PI * 2;
            const r = shapeRingOuter * this._shapeRadius(effectiveShape, theta);
            ctx.beginPath();
            ctx.arc(cx + Math.cos(theta) * r, cy + Math.sin(theta) * r, 2, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',0.6)';
            ctx.fill();
          }
        }

        // Inner subtle stroke
        ctx.strokeStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',0.06)';
        ctx.lineWidth = 1;
        this._drawShapePath(ctx, innerVerts);
        ctx.stroke();

        // Lens fill with per-shape alpha
        const lensVerts = this._buildShapeVerts(effectiveShape, cr * 0.85, cx, cy);
        ctx.fillStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',' + lensParams.innerAlpha.toFixed(3) + ')';
        this._drawShapePath(ctx, lensVerts);
        ctx.fill();

        // Bottom glow (heart/drop): extra fill pool at bottom
        if (ringParams.bottomGlow || ringParams.bottomPool) {
          const poolAlpha = ringParams.bottomPool ? 0.06 : 0.03;
          const poolR = cr * (ringParams.bottomPool ? 0.5 : 0.35);
          ctx.fillStyle = 'rgba(' + rr + ',' + gg + ',' + bb + ',' + poolAlpha.toFixed(3) + ')';
          ctx.beginPath();
          ctx.arc(cx, cy + cr * 0.35, poolR, 0, Math.PI * 2);
          ctx.fill();
        }
      } else {
        // ── Normal round ring (circle shape) ──
        if (stretched && dMag > 1) {
          const stretch = Math.min(0.3, dMag / 200);
          const sx = 1 + stretch * 0.5;
          const sy = 1 - stretch * 0.3;
          ctx.save();
          ctx.translate(cx, cy);
          ctx.rotate(Math.atan2(dY, dX));
          ctx.scale(sx, sy);
          ctx.beginPath();
          ctx.arc(0, 0, ringOuter, 0, Math.PI * 2);
          ctx.arc(0, 0, ringInner, 0, Math.PI * 2, true);
          const ringGrad = ctx.createRadialGradient(0, 0, ringInner, 0, 0, ringOuter);
          ringGrad.addColorStop(0, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
          ringGrad.addColorStop(0.3, 'rgba(' + rr + ',' + gg + ',' + bb + ',0.08)');
          ringGrad.addColorStop(0.7, 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (0.36 * breath * grabFlash * beatFlash).toFixed(2) + ')');
          ringGrad.addColorStop(1, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
          ctx.fillStyle = ringGrad;
          ctx.globalAlpha = 1;
          ctx.fill();
          ctx.restore();
        } else {
          ctx.beginPath();
          ctx.arc(cx, cy, ringOuter, 0, Math.PI * 2);
          ctx.arc(cx, cy, ringInner, 0, Math.PI * 2, true);
          const ringGrad = ctx.createRadialGradient(cx, cy, ringInner, cx, cy, ringOuter);
          ringGrad.addColorStop(0, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
          ringGrad.addColorStop(0.3, 'rgba(' + rr + ',' + gg + ',' + bb + ',0.08)');
          ringGrad.addColorStop(0.7, 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (0.36 * breath * grabFlash * beatFlash).toFixed(2) + ')');
          ringGrad.addColorStop(1, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
          ctx.fillStyle = ringGrad;
          ctx.globalAlpha = 1;
          ctx.fill();
        }

        // Lens gradient fill
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cr);
        grad.addColorStop(0, `rgba(${rr},${gg},${bb},0.04)`);
        grad.addColorStop(0.15, `rgba(${rr},${gg},${bb},0.01)`);
        grad.addColorStop(1, `rgba(${rr},${gg},${bb},0)`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, cr, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // ── Capture count badge ──
    if ((this._summonActive || (this._nebula && this._nebula.active)) && this._capturedParticles.length > 0) {
      const badgeX = this.core.x + 18, badgeY = this.core.y - 22;
      const count = this._capturedParticles.length;
      // Glow ring
      ctx.beginPath();
      ctx.arc(badgeX, badgeY, 12, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(34,197,94,0.25)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(34,197,94,0.6)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      // Count number
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 11px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(count), badgeX, badgeY);
    }

    // ── Water ripples: expanding rings around core ──
    const nowR = performance.now();
    for (let i = this._ripples.length - 1; i >= 0; i--) {
      const rip = this._ripples[i];
      const age = nowR - rip.birth;
      const life = 600;  // ripple lifetime in ms
      if (age > life) {
        this._ripples.splice(i, 1);
        continue;
      }
      const progress = age / life;  // 0 → 1
      rip.r = rip.maxR * (0.05 + 0.95 * progress);  // expand from center
      rip.alpha = rip.alpha * (1 - progress);        // fade out
      if (rip.alpha < 0.005) continue;
      // Draw ripple ring
      ctx.beginPath();
      ctx.arc(rip.x, rip.y, rip.r, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(' + _rr + ',' + _gg + ',' + _bb + ',' + rip.alpha.toFixed(3) + ')';
      ctx.lineWidth = 1.5 * (1 - progress * 0.7);
      ctx.globalAlpha = 1;
      ctx.stroke();
      // Secondary ghost ring (double ripple for depth)
      if (progress > 0.3 && progress < 0.8) {
        ctx.beginPath();
        ctx.arc(rip.x, rip.y, rip.r * 0.7, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(' + _rr + ',' + _gg + ',' + _bb + ',' + (rip.alpha * 0.4).toFixed(3) + ')';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

    ctx.globalAlpha = 1;
    requestAnimationFrame(this._boundAnimate);
  }
}

window.engine = new MatrixRain('particle-canvas');
