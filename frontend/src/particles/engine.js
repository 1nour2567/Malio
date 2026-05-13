/* ================================================================
   engine.js — Malio Particle Body
   512-particle pool, 100-column grid, trails,绕流, FPS failsafe
   ================================================================ */

const POOL_SIZE = 512;
const COLUMN_COUNT = 100;
const COLUMN_GAP_MIN = 18;
const COLUMN_GAP_MAX = 32;
const FPS_WINDOW = 60;
const FPS_THRESHOLD = 30;
const CARD_PADDING = 60;
const DISSIPATE_DECEL = 0.98;
const DISSIPATE_FADE = 0.92;
const RECYCLE_MARGIN = 30;

const DEFAULT_PARAMS = {
  speed: 0.8, density: 0.6, color: '#22C55E', opacity: 0.7, amplitude: 0.4
};

const CHARS = (() => {
  const sets = [
    'アイウエオカキクケコサシスセソタチツテトナニヌネノ',
    'ハヒフヘホマミムメモヤユヨラリルレロワヲン',
    'あいうえおかきくけこさしすせそたちつてとなにぬねの',
    'はひふへほまみむめもやゆよらりるれろわをん',
    '日月火水木金土空風雨山川海花鳥魚声音楽心身体',
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
  ];
  return sets.join('');
})();

class ParticleEngine {
  constructor (canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      this.canvas = document.createElement('canvas');
      this.canvas.id = canvasId;
      Object.assign(this.canvas.style, {
        position: 'fixed', top: '0', left: '0',
        width: '100%', height: '100%',
        zIndex: '0'
      });
      document.body.prepend(this.canvas);
    }
    this.ctx = this.canvas.getContext('2d');

    this.params = { ...DEFAULT_PARAMS };
    this._targetParams = { ...DEFAULT_PARAMS };
    this._lerpFactor = 0.05;

    this._columns = [];
    this.particles = [];
    this._cardRect = null;
    this._trailTimer = 0;
    this._lastFrameTime = performance.now();

    this.frameTimestamps = [];
    this.failsafeActive = false;

    this._resize();
    this._buildColumns();
    this._initParticles();
    window.addEventListener('resize', () => { this._resize(); this._buildColumns(); });

    this._boundAnimate = this._animate.bind(this);
    this._boundAnimate();
  }

  /* ── Public ─────────────────────────────────────────────── */

  updateParams (params, lerpSpeed) {
    Object.assign(this._targetParams, params);
    if (lerpSpeed !== undefined) this._lerpFactor = lerpSpeed;
  }

  /* ── Sizing ─────────────────────────────────────────────── */

  _resize () {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  /* ── Columns ────────────────────────────────────────────── */

  _buildColumns () {
    this._columns = [];
    const w = this.canvas.width || window.innerWidth || 1920;
    let x = COLUMN_GAP_MIN;
    while (x < w - COLUMN_GAP_MIN) {
      this._columns.push(x);
      x += COLUMN_GAP_MIN + Math.random() * (COLUMN_GAP_MAX - COLUMN_GAP_MIN);
    }
  }

  _randomColumnX () {
    if (this._columns.length === 0) return Math.random() * (this.canvas.width || 1920);
    return this._columns[Math.floor(Math.random() * this._columns.length)];
  }

  /* ── Particle Pool ──────────────────────────────────────── */

  _initParticles () {
    const count = Math.round(POOL_SIZE * this.params.density);
    for (let i = 0; i < count; i++) {
      const p = this._createParticle();
      p.y = Math.random() * this.canvas.height; /* spread initial batch across screen */
      this.particles.push(p);
    }
  }

  _createParticle () {
    return {
      x: this._randomColumnX(),
      y: Math.random() * this.canvas.height * -0.3,
      char: CHARS[Math.floor(Math.random() * CHARS.length)],
      speed: (0.7 + Math.random() * 0.6) * this.params.speed,
      opacity: (0.3 + Math.random() * 0.7) * this.params.opacity,
      size: 11 + Math.random() * 7,
      phase: Math.random() * Math.PI * 2,
      vx: 0, vy: 0,
      dissipated: false,
      _trail: false
    };
  }

  _recycleParticle (p) {
    Object.assign(p, this._createParticle());
    p.y = 0;
  }

  _spawnTrail (colX) {
    const count = 4 + Math.floor(Math.random() * 6);
    const gap = 16 + Math.random() * 10;
    const sorted = [...this.particles].sort((a, b) => a.opacity - b.opacity);
    for (let i = 0; i < Math.min(count, sorted.length); i++) {
      const p = sorted[i];
      if (p.opacity > 0.3) continue;
      Object.assign(p, this._createParticle());
      p.x = colX;
      p.y = -i * gap;
      p._trail = true;
    }
  }

  /* ── Card Detection ─────────────────────────────────────── */

  _getCardRect () {
    const el = document.getElementById('player-card') || document.getElementById('player-panel');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      left: r.left - CARD_PADDING, right: r.right + CARD_PADDING,
      top: r.top - CARD_PADDING, bottom: r.bottom + CARD_PADDING,
      cx: (r.left + r.right) / 2, cy: (r.top + r.bottom) / 2,
      innerLeft: r.left, innerRight: r.right,
      innerTop: r.top, innerBottom: r.bottom
    };
  }

  /* ── Main Loop ──────────────────────────────────────────── */

  _animate () {
    const now = performance.now();
    const dt = now - this._lastFrameTime;
    this._lastFrameTime = now;

    /* FPS tracking */
    this.frameTimestamps.push(now);
    if (this.frameTimestamps.length > FPS_WINDOW) this.frameTimestamps.shift();
    if (this.frameTimestamps.length >= 30) {
      const elapsed = this.frameTimestamps[this.frameTimestamps.length - 1]
                    - this.frameTimestamps[0];
      const fps = ((this.frameTimestamps.length - 1) / (elapsed / 1000)) || 0;
      this.failsafeActive = fps < FPS_THRESHOLD;
    }

    this._cardRect = this.failsafeActive ? null : this._getCardRect();

    /* Trail spawner */
    this._trailTimer += dt;
    if (this._trailTimer > 1500 + Math.random() * 2500) {
      this._trailTimer = 0;
      this._spawnTrail(this._randomColumnX());
    }

    /* Lerp params */
    for (const k of ['speed', 'density', 'opacity', 'amplitude', 'color']) {
      if (this._targetParams[k] !== this.params[k]) {
        if (k === 'color') {
          this.params[k] = this._targetParams[k]; /* instant */
        } else {
          this.params[k] += (this._targetParams[k] - this.params[k]) * this._lerpFactor;
        }
      }
    }

    /* Update & draw */
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    const rect = this._cardRect;
    for (const p of this.particles) {
      const nearCard = rect && p.y >= rect.top - 100 && p.y <= rect.bottom + 100;
      if (!this.failsafeActive && nearCard) {
        this._updatePhysics(p, dt, rect);
      } else {
        this._updateSimple(p, dt);
      }
      this._draw(p);
    }

    requestAnimationFrame(this._boundAnimate);
  }

  /* ── Update: Simple ─────────────────────────────────────── */

  _updateSimple (p, dt) {
    const dtNorm = dt / 16;
    p.y += p.speed * dtNorm;
    if (p.y > this.canvas.height) this._recycleParticle(p);
  }

  /* ── Update: Physics (near card) ────────────────────────── */

  _updatePhysics (p, dt, rect) {
    const dtNorm = dt / 16;
    const gravity = p.speed * dtNorm;
    const inExpY = p.y >= rect.top && p.y <= rect.bottom;

    if (inExpY && p.x >= rect.left && p.x <= rect.right) {
      const inCardX = p.x >= rect.innerLeft && p.x <= rect.innerRight;
      const inCardY = p.y >= rect.innerTop && p.y <= rect.innerBottom;

      if (inCardX && inCardY) {
        const dx = p.x - rect.cx, dy = p.y - rect.cy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = 6 / (dist + 1);
        p.vx += (dx / dist) * force;
        p.vy += (dy / dist) * force;
        p.vx += (-dy / dist) * force * 0.4;
        p.vy += (dx / dist) * force * 0.4;
      } else if (p.y >= rect.innerTop && p.y <= rect.innerBottom) {
        if (p.x < rect.innerLeft) p.vx -= 0.3;
        else if (p.x > rect.innerRight) p.vx += 0.3;
        p.vy += gravity;
      } else if (p.y > rect.innerBottom) {
        p.vy *= DISSIPATE_DECEL;
        p.opacity *= DISSIPATE_FADE;
        p.dissipated = true;
      } else {
        const distL = p.x - rect.innerLeft, distR = rect.innerRight - p.x;
        if (p.x > rect.innerLeft && p.x < rect.innerRight) {
          p.vx += (distL < distR ? -1 : 1) * 1.2;
        }
        p.vy += gravity;
      }
    } else if (p.y > rect.innerBottom) {
      if (p.dissipated) {
        p.vy *= DISSIPATE_DECEL;
        p.opacity *= DISSIPATE_FADE;
      } else {
        p.vy += gravity;
      }
    } else {
      p.vy += gravity;
      p.vx *= 0.92;
      if (p.dissipated && p.y < rect.top - 50) {
        p.dissipated = false;
        p.opacity = Math.min(p.opacity + 0.04, this.params.opacity);
      }
    }

    p.x += p.vx * dtNorm;
    p.y += p.vy * dtNorm;
    p.vx *= 0.94;
    p.vy *= 0.97;

    if (p.opacity <= 0.01 || p.y > this.canvas.height + RECYCLE_MARGIN) {
      this._recycleParticle(p);
    }
  }

  /* ── Draw ───────────────────────────────────────────────── */

  _draw (p) {
    const alpha = Math.max(0, Math.min(1, p.opacity));
    if (alpha < 0.01) return;
    this.ctx.font = p.size + 'px "JetBrains Mono", monospace';
    this.ctx.fillStyle = this.params.color;
    this.ctx.globalAlpha = alpha;
    this.ctx.fillText(p.char, Math.round(p.x), Math.round(p.y));
    this.ctx.globalAlpha = 1;
  }
}

window.ParticleEngine = ParticleEngine;
window.engine = new ParticleEngine('particle-canvas');
