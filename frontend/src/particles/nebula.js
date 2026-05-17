/* ================================================================
   nebula.js — NebulaEngine
   E/W/D energy-field gravitational clustering for summoned info particles.

   Phase B-B skeleton: class structure + entry/exit stubs.
   Full inter-particle physics deferred to Phase B-B implementation.

   Integration:
     MatrixRain.startSummon() → NebulaEngine.enter(infoParticles)
     NebulaEngine.update(dt)  → gravitational clustering loop
     MatrixRain.endSummon()   → NebulaEngine.exit() → returns positions
   ================================================================ */

const NEBULA_ATTRACTION = 0.002;    // inter-particle gravity constant
const NEBULA_DAMPING = 0.92;        // velocity damping
const NEBULA_MIN_DIST = 8;           // minimum distance (avoid singularity)
const NEBULA_CLUSTER_THRESHOLD = 0.15;  // E/W/D distance below which particles attract
const NEBULA_REPULSION = 0.001;     // repulsion for dissimilar particles
const NEBULA_CORE_PULL = 0.0005;    // gentle pull toward center
const NEBULA_CLUMP_REPEL = 0.008;   // anti-clump: push apart when < 18px
const NEBULA_CLUMP_DIST = 18;       // minimum spacing between particles
const NEBULA_RING_PULL = 0.0003;    // weak pull toward orbital ring target

class NebulaEngine {

  constructor (canvas, ctx, engine) {
    this.canvas = canvas;
    this.ctx = ctx;
    this.engine = engine || null;
    this.active = false;
    this.particles = [];        // {x, y, char, energy, warmth, density, vx, vy, title}
    this._lastFrame = null;
    this._boundLoop = this._loop.bind(this);
  }

  /* ── ENTER: receive frozen particle references, begin clustering ──

     Particles are mutated in-place — no copies. MatrixRain continues
     to draw them in its own render loop. NebulaEngine only updates
     positions via _updatePhysics(dt).                                */

  enter (frozenParticles) {
    this.active = true;
    /* Direct references to MatrixRain particle objects — mutate in place */
    this.particles = frozenParticles.filter(c => c && c._frozen);
    /* Add nebula physics state to each particle */
    for (const c of this.particles) {
      c._nvx = c._nvx || 0;
      c._nvy = c._nvy || 0;
      c._nselected = false;
    }
    this._lastFrame = performance.now();
    /* No rAF loop — MatrixRain drives _updatePhysics(dt) from its own loop */
  }

  /* ── EXIT: clean up nebula state, return particles ────────── */

  exit () {
    this.active = false;
    const result = [];
    for (const c of this.particles) {
      result.push({ x: c.x, y: c.y, _nvx: c._nvx || 0, _nvy: c._nvy || 0 });
      // Clean up nebula-specific state
      delete c._nvx;
      delete c._nvy;
      delete c._nselected;
    }
    this.particles = [];
    return result;
  }

  /* ── Main loop ────────────────────────────────────────────── */

  _loop () {
    if (!this.active) return;

    const now = performance.now();
    const dt = Math.min((now - (this._lastFrame || now)) / 16, 3);
    this._lastFrame = now;

    this._updatePhysics(dt);
    this._draw();

    requestAnimationFrame(this._boundLoop);
  }

  /* ── Gravitational clustering physics ───────────────────────

     Operates directly on MatrixRain particle struct fields:
     x, y, _nvx, _nvy, _ewd{energy,warmth,density}, _rgb, _frozen */

  _updatePhysics (dt) {
    const pArr = this.particles;
    const n = pArr.length;
    if (n < 2) return;

    const cx = this.canvas.width / 2;
    const cy = this.canvas.height / 2;

    for (let i = 0; i < n; i++) {
      const a = pArr[i];
      if (a._nselected) continue;

      const ae = (a._ewd && a._ewd.energy != null) ? a._ewd.energy : 0.5;
      const aw = (a._ewd && a._ewd.warmth != null) ? a._ewd.warmth : 0.5;
      const ad = (a._ewd && a._ewd.density != null) ? a._ewd.density : 0.5;

      for (let j = i + 1; j < n; j++) {
        const b = pArr[j];
        if (b._nselected) continue;

        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || NEBULA_MIN_DIST;

        // Anti-clump: short-range repulsion for ALL nearby particles
        if (dist < NEBULA_CLUMP_DIST) {
          const clumpForce = NEBULA_CLUMP_REPEL * (1 - dist / NEBULA_CLUMP_DIST);
          const cfx = (dx / dist) * clumpForce;
          const cfy = (dy / dist) * clumpForce;
          a._nvx = (a._nvx || 0) - cfx * dt;
          a._nvy = (a._nvy || 0) - cfy * dt;
          b._nvx = (b._nvx || 0) + cfx * dt;
          b._nvy = (b._nvy || 0) + cfy * dt;
        }

        const be = (b._ewd && b._ewd.energy != null) ? b._ewd.energy : 0.5;
        const bw = (b._ewd && b._ewd.warmth != null) ? b._ewd.warmth : 0.5;
        const bd = (b._ewd && b._ewd.density != null) ? b._ewd.density : 0.5;

        // E/W/D spectral distance (normalized 3D distance)
        const de = ae - be;
        const dw = aw - bw;
        const dd = ad - bd;
        const ewdDist = Math.sqrt(de*de + dw*dw + dd*dd) / Math.sqrt(3);

        if (ewdDist < NEBULA_CLUSTER_THRESHOLD && dist < 300) {
          // Similar energy → attract
          const force = NEBULA_ATTRACTION * (1 - ewdDist / NEBULA_CLUSTER_THRESHOLD);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a._nvx = (a._nvx || 0) + fx * dt;
          a._nvy = (a._nvy || 0) + fy * dt;
          b._nvx = (b._nvx || 0) - fx * dt;
          b._nvy = (b._nvy || 0) - fy * dt;
        } else if (dist < 120 && ewdDist >= NEBULA_CLUSTER_THRESHOLD) {
          // Dissimilar energy → gentle repulsion
          const force = NEBULA_REPULSION * (ewdDist - NEBULA_CLUSTER_THRESHOLD);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a._nvx = (a._nvx || 0) - fx * dt;
          a._nvy = (a._nvy || 0) - fy * dt;
          b._nvx = (b._nvx || 0) + fx * dt;
          b._nvy = (b._nvy || 0) + fy * dt;
        }
      }

      // Gentle core pull
      const dcx = cx - a.x;
      const dcy = cy - a.y;
      const dcore = Math.sqrt(dcx*dcx + dcy*dcy) || 1;
      a._nvx = (a._nvx || 0) + (dcx / dcore) * NEBULA_CORE_PULL * dt;
      a._nvy = (a._nvy || 0) + (dcy / dcore) * NEBULA_CORE_PULL * dt;

      // Weak ring pull: maintain orbital distance from core
      if (a._driftTargetX != null) {
        const rtx = a._driftTargetX - a.x;
        const rty = a._driftTargetY - a.y;
        a._nvx = (a._nvx || 0) + rtx * NEBULA_RING_PULL * dt;
        a._nvy = (a._nvy || 0) + rty * NEBULA_RING_PULL * dt;
      }

      // Integrate
      a.x += (a._nvx || 0) * dt;
      a.y += (a._nvy || 0) * dt;
      a._nvx = (a._nvx || 0) * NEBULA_DAMPING;
      a._nvy = (a._nvy || 0) * NEBULA_DAMPING;

      // Bounds clamp
      if (a.x < 10) { a.x = 10; a._nvx *= -0.3; }
      if (a.x > this.canvas.width - 10) { a.x = this.canvas.width - 10; a._nvx *= -0.3; }
      if (a.y < 10) { a.y = 10; a._nvy *= -0.3; }
      if (a.y > this.canvas.height - 10) { a.y = this.canvas.height - 10; a._nvy *= -0.3; }
    }
  }

  /* ── Draw ─────────────────────────────────────────────────── */

  _draw () {
    const ctx = this.ctx;
    const h = this.canvas.height;

    for (const p of this.particles) {
      const bright = 0.65 + 0.35 * Math.min(1, p.y / h);
      if (p._rgb) {
        const r = Math.round(p._rgb.r * bright);
        const g = Math.round(p._rgb.g * bright);
        const b = Math.round(p._rgb.b * bright);
        ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
      } else {
        // Follow engine's current color instead of hardcoded green
        var ec = (this.engine && this.engine._targetParams && this.engine._targetParams.color)
                 || (this.engine && this.engine.params && this.engine.params.color)
                 || '#22C55E';
        ctx.fillStyle = ec;
      }
      ctx.font = '15px "JetBrains Mono", monospace';
      ctx.globalAlpha = 0.9;
      ctx.fillText(p.char, Math.round(p.x), Math.round(p.y));
      ctx.globalAlpha = 1;
    }
  }

  /* ── Gesture: select particle near touch point ────────────── */

  selectAt (px, py, radius) {
    const r = radius || 30;
    let closest = null;
    let closestDist = r;
    for (const p of this.particles) {
      const dx = px - p.x;
      const dy = py - p.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < closestDist) {
        closestDist = dist;
        closest = p;
      }
    }
    if (closest) {
      closest._selected = true;
      closest._selectedAt = performance.now();
    }
    return closest;
  }

  releaseSelection () {
    for (const p of this.particles) {
      if (p._selected) {
        p._selected = false;
        p._selectedAt = null;
      }
    }
  }
}

window.NebulaEngine = NebulaEngine;
