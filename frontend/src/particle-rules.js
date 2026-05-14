/* ================================================================
   ParticleRules — DSL engine for agent-programmed particle behavior

   Syntax:
     WHEN <condition> THEN <action>
     WHEN <condition> THEN <action> RAMP TO <target> IN <duration>
     WHEN <condition> THEN <action> END WHEN <end_condition>

   Conditions:
     time > HH:MM | time < HH:MM | idle > N
     event = "song_change" | event = "beat"
     audio.bass > N | audio.mid > N | audio.treble > N
     day IN [Mon, Tue, ...]
     particle_count > N | particle_count < N

   Actions:
     speed = N | speed *= N | speed += N
     brightness = N | brightness *= N
     amplitude = N | amplitude *= N
     density = N | density_max = N
     color = "#hex"

   Sources:
     1. System rules (5 built-in, always active)
     2. Agent-generated (via WebSocket or app.js API)
     3. User-spoken (via /api/chat → reasoner outputs rules)

   Lifecycle:
     Rules are evaluated every frame. Agent can add/remove/update rules.
     Each rule tracks hit count and last fire time for self-evaluation.
   ================================================================ */

const SYSTEM_RULES = [
  {
    id: 'sys_night',
    source: 'system',
    when: { type: 'or', clauses: [
      { op: 'time_gt', val: '23:00' },
      { op: 'time_lt', val: '05:00' },
    ]},
    then: [
      { target: 'brightness', op: 'lerp_to', val: 0.35, rate: 0.01 },
      { target: 'speed', op: 'mult', val: 0.85 },
      { target: 'amplitude', op: 'mult', val: 0.7 },
    ],
  },
  {
    id: 'sys_idle',
    source: 'system',
    when: { type: 'idle_gt', val: 300 /* seconds */ },
    then: [
      { target: 'speed', op: 'mult', val: 0.85 },
      { target: 'density_max', op: 'set', val: 0.7 },
    ],
    endWhen: { type: 'event', val: 'user_activity' },
  },
  {
    id: 'sys_song_change',
    source: 'system',
    when: { type: 'event', val: 'song_change' },
    then: [
      { target: 'amplitude', op: 'mult', val: 1.8 },
    ],
    rampDown: { duration: 3000, target: 'amplitude', toVal: 1.0 },
  },
  {
    id: 'sys_density_guard',
    source: 'system',
    when: { type: 'count_gt', val: 500 },
    then: [
      { target: 'density_max', op: 'set', val: 0.8 },
    ],
  },
  {
    id: 'sys_daylight',
    source: 'system',
    when: { type: 'and', clauses: [
      { op: 'time_gt', val: '06:00' },
      { op: 'time_lt', val: '12:00' },
    ]},
    then: [
      { target: 'brightness', op: 'lerp_to', val: 1.0, rate: 0.02 },
    ],
  },
];

class ParticleRules {
  constructor (engine) {
    this.engine = engine;
    this.rules = [];
    this._idleTimer = 0;
    this._lastActivity = performance.now();
    this._songJustChanged = false;
    this._songChangeTimer = 0;

    /* load system rules */
    for (const r of SYSTEM_RULES) {
      this.rules.push({ ...r, _hits: 0, _lastFire: 0, _active: true });
    }

    /* listen for user activity */
    window.addEventListener('pointermove', () => this._onActivity());
    window.addEventListener('pointerdown', () => this._onActivity());
    window.addEventListener('keydown', () => this._onActivity());
  }

  _onActivity () {
    this._lastActivity = performance.now();
  }

  /* ── Public API ─────────────────────────────────────── */

  addRule (ruleJson) {
    const rule = {
      id: ruleJson.id || ('agent_' + Date.now()),
      source: ruleJson.source || 'agent',
      when: ruleJson.when,
      then: ruleJson.then || ruleJson.actions,
      endWhen: ruleJson.endWhen || null,
      rampDown: ruleJson.rampDown || null,
      priority: ruleJson.priority || 0,
      _hits: 0,
      _lastFire: 0,
      _active: true,
      _rampStart: 0,
      _endTriggered: false,
    };
    /* replace rule with same id */
    const idx = this.rules.findIndex(r => r.id === rule.id);
    if (idx >= 0) { this.rules[idx] = rule; }
    else { this.rules.push(rule); }
    return rule.id;
  }

  removeRule (id) {
    this.rules = this.rules.filter(r => r.id !== id);
  }

  triggerEvent (name) {
    if (name === 'song_change') {
      this._songJustChanged = true;
      this._songChangeTimer = performance.now();
    }
  }

  /* ── Frame evaluation ───────────────────────────────── */

  evaluate (now) {
    const ctx = this._buildContext(now);

    for (const rule of this.rules) {
      if (!rule._active) continue;

      /* handle ramp-down from previous fire */
      if (rule._rampStart && rule.rampDown) {
        const elapsed = now - rule._rampStart;
        if (elapsed < rule.rampDown.duration) {
          continue; /* ramp in progress */
        }
        rule._rampStart = 0;
      }

      /* check end condition first */
      if (rule.endWhen && rule._endTriggered && !this._checkCond(rule.when, ctx)) {
        rule._endTriggered = false;
        this._applyActions(rule.then.reverseActions ? rule.then.map(a => ({ ...a, op: 'revert' })) : []);
        continue;
      }
      if (rule._endTriggered) continue;

      /* evaluate WHEN condition */
      if (this._checkCond(rule.when, ctx)) {
        rule._hits += 1;
        rule._lastFire = now;
        this._applyActions(rule.then, ctx);
        rule._endTriggered = false;

        if (rule.rampDown) {
          rule._rampStart = now;
          /* schedule revert */
          const self = this;
          setTimeout(() => {
            rule._rampStart = 0;
            self._applyActions([{ target: rule.rampDown.target, op: 'set', val: rule.rampDown.toVal }]);
          }, rule.rampDown.duration);
        }
      }

      /* check END WHEN */
      if (rule.endWhen && this._checkEndCond(rule.endWhen, ctx)) {
        rule._endTriggered = true;
      }
    }
  }

  _buildContext (now) {
    const time = new Date();
    return {
      time: time,
      hour: time.getHours(),
      minute: time.getMinutes(),
      timeMin: time.getHours() * 60 + time.getMinutes(),
      day: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][time.getDay()],
      idle: Math.round((now - this._lastActivity) / 1000),
      audio: this.engine._audio || { bass: 0, mid: 0, treble: 0, beat: 0 },
      count: (this.engine.particles || this.engine._colsNear || []).length,
      event: this._eventNow(now),
    };
  }

  _eventNow (now) {
    if (this._songJustChanged && now - this._songChangeTimer < 500) {
      return 'song_change';
    }
    if (this.engine._audio && this.engine._audio.beat > 0.5) {
      return 'beat';
    }
    return 'none';
  }

  _checkCond (cond, ctx) {
    if (!cond) return true;
    if (cond.type === 'or') return cond.clauses.some(c => this._checkCond(c, ctx));
    if (cond.type === 'and') return cond.clauses.every(c => this._checkCond(c, ctx));

    switch (cond.op || cond.type) {
      case 'time_gt': { const m = cond.val.split(':').map(Number); return ctx.hour > m[0] || (ctx.hour === m[0] && ctx.minute > m[1]); }
      case 'time_lt': { const m = cond.val.split(':').map(Number); return ctx.hour < m[0] || (ctx.hour === m[0] && ctx.minute < m[1]); }
      case 'idle_gt': return ctx.idle > cond.val;
      case 'idle_lt': return ctx.idle < cond.val;
      case 'event': return ctx.event === cond.val;
      case 'count_gt': return ctx.count > cond.val;
      case 'count_lt': return ctx.count < cond.val;
      case 'bass_gt': return ctx.audio.bass > cond.val;
      case 'bass_lt': return ctx.audio.bass < cond.val;
      case 'mid_gt': return ctx.audio.mid > cond.val;
      case 'treble_gt': return ctx.audio.treble > cond.val;
      case 'day_in': return cond.val.includes(ctx.day);
      default: return false;
    }
  }

  _checkEndCond (cond, ctx) {
    if (cond.type === 'event' && cond.val === 'user_activity') {
      return ctx.idle < 2 && ctx.event !== 'none';
    }
    return this._checkCond(cond, ctx);
  }

  _applyActions (actions, ctx) {
    if (!actions || !actions.length) return;
    const p = this.engine._targetParams || this.engine.params || {};

    for (const a of actions) {
      const cur = p[a.target] !== undefined ? p[a.target] : a.target === 'brightness' ? 0.7 : a.target === 'amplitude' ? 0.4 : a.target === 'density_max' ? 1.0 : a.target === 'speed' ? 1.0 : 0;

      switch (a.op) {
        case 'set': p[a.target] = a.val; break;
        case 'mult': p[a.target] = cur * a.val; break;
        case 'add': p[a.target] = cur + a.val; break;
        case 'lerp_to':
          p[a.target] = cur + (a.val - cur) * (a.rate || 0.02);
          break;
        case 'clamp':
          p[a.target] = Math.max(a.min || 0, Math.min(a.max || 1, cur));
          break;
        case 'revert':
          p[a.target] = a.val !== undefined ? a.val : cur;
          break;
      }
      /* clamp physical ranges */
      if (a.target === 'brightness') p[a.target] = Math.max(0.1, Math.min(1.5, p[a.target]));
      if (a.target === 'speed') p[a.target] = Math.max(0.2, Math.min(3, p[a.target]));
      if (a.target === 'amplitude') p[a.target] = Math.max(0, Math.min(3, p[a.target]));
    }
  }
}

/* singleton — created by app.js */
let particleRules = null;
