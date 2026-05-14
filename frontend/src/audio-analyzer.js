/* ================================================================
   AudioAnalyzer — Web Audio API bridge
   Extracts bass/mid/treble energy + beat detection → drives particles
   ================================================================ */

class AudioAnalyzer {
  constructor (audioEl) {
    this.audio = audioEl;
    this.ctx = null;
    this.analyser = null;
    this.data = new Uint8Array(0);
    this.active = false;

    /* beat detection */
    this._bassHistory = [];
    this._bassThreshold = 80;
    this._beatCooldown = 0;
    this._beatDecay = 0.9;
  }

  init () {
    if (this.ctx) return;
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = this.ctx.createMediaElementSource(this.audio);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.7;
      source.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
      this.data = new Uint8Array(this.analyser.frequencyBinCount);
      this.active = true;
    } catch (e) {
      console.warn('[AudioAnalyzer] init failed:', e.message);
    }
  }

  /* call every frame — returns { bass, mid, treble, beat } */
  analyze () {
    if (!this.active || !this.analyser) {
      return { bass: 0, mid: 0, treble: 0, beat: 0 };
    }
    this.analyser.getByteFrequencyData(this.data);

    /* freq bands (fftSize=256 → 128 bins, sampleRate÷2÷128 ≈ 86Hz/bin) */
    const bassEnd = 4;         /* ~0-340Hz */
    const midEnd  = 16;        /* ~340-1400Hz */
    const trebleEnd = 48;      /* ~1400-4100Hz */

    let bass = 0, mid = 0, treble = 0;
    for (let i = 0; i < bassEnd; i++) bass += this.data[i];
    for (let i = bassEnd; i < midEnd; i++) mid += this.data[i];
    for (let i = midEnd; i < trebleEnd; i++) treble += this.data[i];
    bass /= bassEnd * 255;
    mid  /= (midEnd - bassEnd) * 255;
    treble /= (trebleEnd - midEnd) * 255;

    /* beat detection on bass energy */
    this._bassHistory.push(bass);
    if (this._bassHistory.length > 43) this._bassHistory.shift(); /* ~0.7s at 60fps */
    const avg = this._bassHistory.reduce((a, b) => a + b, 0) / this._bassHistory.length;
    this._bassThreshold = this._bassThreshold * this._beatDecay + avg * (1 - this._beatDecay);
    this._beatCooldown = Math.max(0, this._beatCooldown - 1);

    let beat = 0;
    if (bass > this._bassThreshold * 1.5 && this._beatCooldown === 0) {
      beat = 1;
      this._beatCooldown = 8;  /* ~130ms min gap between beats */
    }

    return { bass, mid, treble, beat };
  }

  destroy () {
    if (this.ctx) { this.ctx.close(); this.ctx = null; }
    this.active = false;
  }
}

/* singleton — created by app.js */
let audioAnalyzer = null;
