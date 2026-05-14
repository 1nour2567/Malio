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
    this.core = { x: 0, y: 0, r: 40, active: true };
    this._breathPhase = 0;  // breathing ring oscillation
    this.params = { speed: 1.0, color: '#22C55E' };
    this._targetParams = { ...this.params };
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
    /* audio reactivity */
    this._audio = { bass: 0, mid: 0, treble: 0, beat: 0 };
    /* core mode from Agent */
    this._coreMode = 'dot';  /* dot / vortex / helix / error */
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
      const pos = this._eventPos(e);
      const dx = pos.x - this.core.x;
      const dy = pos.y - this.core.y;
      if (Math.sqrt(dx * dx + dy * dy) < this.core.r + 10) {
        // Double-tap detection
        const now = performance.now();
        if (now - this._lastTap < 400) {
          clearTimeout(_pressTimer);
          if (this._summonActive) this.endSummon();
          this._dragging = false;
          this.canvas.style.cursor = '';
          this._timeWarp = !this._timeWarp;
          this._lastTap = 0;
          if (this._timeWarp) {
            this._timeWarpStart = now;
            this._timeWarpBubble = 0;
            this._lastWarpInteract = now;
          } else {
            // Reset all particle velocities on exit
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
          if (Math.abs(dx2) + Math.abs(dy2) < 10) {
            this.startSummon();
          }
        }, 600);
        this._dragging = true;
        this._settled = false;
        this._grabTime = performance.now();
        this.canvas.style.cursor = 'grabbing';
        e.preventDefault();
      } else {
        // Potential swipe — start tracking, prevent scroll
        _swiping = true;
        _swipeStartX = pos.x;
        _swipeStartY = pos.y;
        e.preventDefault();
      }
    };
    let _dragPrevX = 0, _dragPrevY = 0;
    const move = (e) => {
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

        // Nebula capture: find closest frozen particle to core
        if (this._summonActive || (this._nebula && this._nebula.active)) {
          let closest = null, closestDist = 25;
          for (const lyr of [this._colsFar, this._colsMid, this._colsNear]) {
            for (const col of lyr) {
              for (const c of col.stream) {
                if (!c._frozen || !c._tag || c._swallowed) continue;
                const dx = c.x - this.core.x;
                const dy = c.y - this.core.y;
                const dist = Math.sqrt(dx*dx + dy*dy);
                if (dist < closestDist) { closestDist = dist; closest = c; }
              }
            }
          }
          this._captureTarget = closest;
          if (closest) {
            // Scale: 20px→1.0x, 10px→1.5x, 5px→swallow
            if (closestDist < 5) {
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
              closest._captureScale = Math.max(1.0, 1.5 - (closestDist - 10) * 0.05);
            }
          }
        }
      }
    };
    const end = (e) => {
      clearTimeout(_pressTimer);
      if (this._summonActive) this.endSummon();
      if (this._dragging) {
        this._returning = true;
        this._retVX = 0;
        this._retVY = 0;
      }
      this._dragging = false;
      // Swipe detection: check horizontal movement
      if (_swiping) {
        const pos = this._eventPos(e);
        const swipeDx = pos.x - _swipeStartX;
        const swipeDy = pos.y - _swipeStartY;
        if (Math.abs(swipeDx) > 30 && Math.abs(swipeDx) > Math.abs(swipeDy) * 0.5) {
          if (typeof this.onSwipe === 'function') {
            this.onSwipe(swipeDx > 0 ? 'right' : 'left');
          }
        }
      }
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

  setCoreMode (mode) {
    if (this._coreMode !== mode) {
      this._coreMode = mode;
      if (mode === 'error') this._coreModeStart = performance.now();
      if (mode === 'vortex') this._coreModeStart = performance.now();
    }
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
    if (Math.random() < 0.03) {
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
    this._coreExpand = now; // trigger core expansion
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
            if (info && this._infoCols.has(col)) { /* column occupied — stay random */ }
            else if (info) {
              if (c._tag) this._infoCols.delete(col); // free previous column if was info
              c.char = info.chars; c._tag = info.tag;
              c._ewd = { energy: info.energy, warmth: info.warmth, density: info.density };
              c._rgb = ewdToRgb(info.energy, info.warmth, info.density);
              c._infoSpeedMul = 1.15 + Math.random() * 0.15;
              this._infoCols.add(col);
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
              if (info2 && this._infoCols.has(col)) { /* column occupied */ }
              else if (info2) {
                c.char = info2.chars; c._tag = info2.tag;
                c._ewd = { energy: info2.energy, warmth: info2.warmth, density: info2.density };
                c._rgb = ewdToRgb(info2.energy, info2.warmth, info2.density);
                c._infoSpeedMul = 1.15 + Math.random() * 0.15;
                this._infoCols.add(col);
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
          if (dist < this.core.r && dist > 2) {
            const t = dist / this.core.r;
            const strength = t * (1 - t) * 24;
            drawX -= (dx / dist) * strength;
            drawY -= (dy / dist) * strength;
            lensScale = 1 + (1 - t) * 0.5; // 1.5x at center, 1x at edge
          }
        }

        // Particle memory: veteran particles slightly larger
        const memScale = 1 + Math.min(0.3, (c.mem || 0) * 0.01);
        lensScale *= memScale;

        // Capture target scaling: particle grows as core approaches
        if (c._captureScale && c._captureScale > 1) {
          lensScale = Math.max(lensScale, c._captureScale);
        }

        // Luminance gradient
        const memoryBoost = 1 + Math.min(0.5, (c.mem || 0) * 0.05); /* veteran particles glow */
        const infoBoost = c._tag ? 1.15 : 1.0;
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
          r = Math.round(0x22 * bright);
          g = Math.round(0xC5 * bright);
          b = Math.round(0x5E * bright);
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
        this._nebula = new NebulaEngine(this.canvas, this.ctx);
        this._nebula.enter(frozen);
      }
    }

    // Nebula physics: drive gravitational clustering once per frame
    if (this._nebula && this._nebula.active) {
      this._nebula._updatePhysics(dt);
    }

    // Core lens — nearly invisible, perceived only through refraction
    if (this.core.active) {
      const cx = this.core.x, cy = this.core.y, cr = this.core.r;
      const mode = this._coreMode;

      /* ── vortex mode: spinning ring particles ────────── */
      if (mode === 'vortex' && !this._timeWarp) {
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

      /* ── error mode: red flicker + fade ──────────────── */
      if (mode === 'error') {
        const sinceError = performance.now() - (this._coreModeStart || 0);
        const flicker = Math.abs(Math.sin(sinceError / 80)) * (sinceError < 1200 ? 1 : Math.max(0, 1 - (sinceError - 1200) / 2000));
        ctx.fillStyle = `rgba(255, 0, 0, ${flicker * 0.4})`;
        ctx.beginPath();
        ctx.arc(cx, cy, cr + 12, 0, Math.PI * 2);
        ctx.fill();
      }

      // Ring: dashed during summon, breathing otherwise
      this._breathPhase += this._summonActive ? 0.08 : 0.016;
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
      const breathBase = this._timeWarp ? 0.3 : (0.3 + 0.7 * Math.sin(this._breathPhase));
      let breath = breathBase;
      const tc = this._targetParams.color || '#22C55E';
      const hex = tc.replace('#', '');
      const rr = parseInt(hex.substring(0, 2), 16);
      const gg = parseInt(hex.substring(2, 4), 16);
      const bb = parseInt(hex.substring(4, 6), 16);

      // Grab flash: brightness spike on initial grab, then decay
      const now = performance.now();
      const grabAge = now - this._grabTime;
      let grabFlash = 1;
      if (grabAge < 80) grabFlash = 1.4;       // spike
      else if (grabAge < 250) grabFlash = 1 + 0.4 * (1 - (grabAge - 80) / 170);  // decay

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

      if (stretched && dMag > 1) {
        // Draw deformed ring: ellipse stretched perpendicular to drag direction
        const stretch = Math.min(0.3, dMag / 200);  // max 30% deformation
        const sx = 1 + stretch * 0.5;  // wider perpendicular to drag
        const sy = 1 - stretch * 0.3;  // narrower along drag
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
        ringGrad.addColorStop(0.7, 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (0.36 * breath * grabFlash).toFixed(2) + ')');
        ringGrad.addColorStop(1, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
        ctx.fillStyle = ringGrad;
        ctx.globalAlpha = 1;
        ctx.fill();
        ctx.restore();
      } else {
        // Normal round ring
        ctx.beginPath();
        ctx.arc(cx, cy, ringOuter, 0, Math.PI * 2);
        ctx.arc(cx, cy, ringInner, 0, Math.PI * 2, true);
        const ringGrad = ctx.createRadialGradient(cx, cy, ringInner, cx, cy, ringOuter);
        ringGrad.addColorStop(0, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
        ringGrad.addColorStop(0.3, 'rgba(' + rr + ',' + gg + ',' + bb + ',0.08)');
        ringGrad.addColorStop(0.7, 'rgba(' + rr + ',' + gg + ',' + bb + ',' + (0.36 * breath * grabFlash).toFixed(2) + ')');
        ringGrad.addColorStop(1, 'rgba(' + rr + ',' + gg + ',' + bb + ',0)');
        ctx.fillStyle = ringGrad;
        ctx.globalAlpha = 1;
        ctx.fill();
      }

      // Lens gradient fill
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cr);
      grad.addColorStop(0, 'rgba(34,197,94,0.04)');
      grad.addColorStop(0.15, 'rgba(34,197,94,0.01)');
      grad.addColorStop(1, 'rgba(34,197,94,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, cr, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
    requestAnimationFrame(this._boundAnimate);
  }
}

window.engine = new MatrixRain('particle-canvas');
