# Malio Particle Body — Architecture Spec

**Status**: Draft  
**Date**: 2026-05-12  

## 1. Core Concept

Malio has no traditional player UI. The particle flow IS the AI's body. Users interact through gestures that produce physical particle feedback. Information is encoded in particle motion properties — speed (time perception), density (presence), orbit radius (intensity), waveform (emotion).

## 2. File Structure

```
frontend/src/
├── particles/
│   ├── engine.js        # Main loop, column grid, particle pool (~200 lines)
│   ├── core.js           # Core state machine: idle/thinking/speaking/error (~100 lines)
│   ├── physics.js        # Flow-around, time warp, refraction (~150 lines)
│   ├── gestures.js       # Gesture recognition: swipe/spin/double-tap/long-press (~150 lines)
│   ├── effects.js        # Shockwaves, search ball, light-burst choreography (~150 lines)
│   └── render.js         # Drawing: trails, chromatic aberration, core glow (~100 lines)
├── app.js                # Main logic (thin coordinator)
├── ws-client.js          # WebSocket + atmosphere dispatch
└── style.css             # Minimal — body background, overlay elements only
```

## 3. Particle Engine (engine.js)

- 512-particle pool
- 100 fixed columns, evenly spaced
- Column spring — particles gently restore to column X
- Character set: katakana + hiragana + simple kanji + A-Z + 0-9
- Default speed 0.8, density 0.6
- FPS failsafe at < 30fps (disable绕流)
- Trail spawn: every 1.5-4s, 4-9 particles dropped in same column

## 4. Core State Machine (core.js)

**Position**: screen center when no player card, card center when player visible

**States**:

| State | Visual | Trigger |
|-------|--------|---------|
| idle | Steady white dot, radius 10px, soft glow | Default, playing music |
| thinking | Mini vortex — particles near core rotate inward | Agent reasoning (WebSocket `agent_log`) |
| speaking | Core pulses at ~2Hz, particles ripple outward | Agent has response text |
| loading | Double helix — two particle streams counter-rotate | Music buffering or API loading |
| error | Weak red dot, surrounding particles brownian | API/tool failure, auto-recovers after 3-4s |

**State transitions** driven by WebSocket events from backend.

## 5. Physics (physics.js)

- **Flow-around**: radial + tangential push when particles enter card bounding box
- **Dissipation**: below card, particles decelerate and fade in 20px buffer zone
- **Time warp**: bullet-time gradient around core — 5% speed at core, 10% at 100px, 30% at 300px, 100% at edges
- **Refraction**: when particles pass through core area, path bends slightly (convex lens effect). RGB channels offset slightly differently (chromatic aberration)

## 6. Gesture System (gestures.js)

### 6.1 Swipe Right → Next Song

- Touch: single finger swipe right on canvas
- Mouse: mousedown + drag right on canvas
- Threshold: 50px horizontal, vertical < 2x horizontal to prevent diagonal cancellation
- Distance + speed determine "skip决心" — short+slow = 1 song, long+fast = skip album
- Particle feedback: particles pushed in swipe direction, creating visible wave

### 6.2 Tap Core → Spin (Volume)

- Touch: tap core, then rotate finger around it
- Mouse: click core to activate (brightens), then scroll wheel
- Activation: core brightness increases, subtle pulse
- Auto-exit: 2 seconds of inactivity
- Clockwise = volume down, counter-clockwise = volume up
- 360° rotation = 50% volume change
- Particle feedback: orbit radius tightens (loud) or expands (quiet)

### 6.3 Double Tap Core → Bullet Time (Pause/Play)

- Touch: double-tap core
- Mouse: double-click core
- Detection: 300ms window between clicks
- Toggles time warp mode
- Audio pauses/resumes accordingly

### 6.4 Long Press Core → Search

- Touch: press and hold core
- Mouse: mousedown on core, hold
- Threshold: 600ms hold
- Particles gather into ball around core, brownian motion
- Search input appears near core
- Typing increases brownian intensity
- Enter: collapse → burst → normal
- Escape: cancel, particles return

## 7. Effects (effects.js)

### 7.1 Song Change Ceremony (Triple Light Burst)

Timeline from swipe gesture:
- 0ms: Core collapses (shrink to 0.3x)
- 60ms: Phase 1 — Pure white shockwave (fast, strong, radius 240px)
- 140ms: Phase 2 — Cover art dominant color wave (medium, radius 300px, particles briefly tinted)
- 220ms: Phase 3 — Dark收束 wave (slow, radius 360px, clears background)
- 300ms: Cover art image radiates from core, stays 1.5s then fades
- 300ms: Song title text floats from core, stays 2-3s then dissolves into particles
- 300ms+: Core restores, particles resume绕流 with new emotional color

### 7.2 Search Ball

- Particles within 150px of core gather into a sphere
- Sphere radius shrinks from 80px to 55px over 500ms
- Inside: brownian motion, intensity proportional to input length
- On Enter: all particles collapse inward → burst outward → return to columns

## 8. Information Encoding (No Traditional UI)

| Information | Encoding |
|------------|----------|
| Song title/artist | Text floats from core on song change, dissolves into particles after 2-3s |
| Play progress | Particle ring density around core — sparse at start, dense near end, particles escape when song ending |
| Volume | Particle orbit radius around core — tight= loud, loose= quiet. Core brightness secondary cue. |
| Play/Pause | Flow speed — pause = time gradient (near-static at core), play = normal flow |
| Agent speaking | Core pulse at ~2Hz + particle ripple outward |
| Error | Core turns red, surrounding particles do brownian motion |
| Emotion | Particle color via atmosphere system (6-tag mapping from color-map.json) |

## 9. Data Flow

```
Backend Agent (reasoner.py)
  → outputs: { atmosphere, core_state, say, gesture }
  → WebSocket /stream → ws-client.js
  → onAtmosphere → engine.updateParams() (color/speed/density lerp)
  → onCoreState → core.setState()
  → onSay → effects.showSongText()

Frontend Gestures (gestures.js)
  → right swipe → triggerTripleShockwave() → nextSong()
  → tap + scroll → setVolume()
  → double tap → toggleTimeWarp() → togglePlay()
  → long press → startSearchBall()

Core State Machine (core.js)
  → WebSocket events → state transitions
  → visual feedback driven by state
```

## 10. Phase Plan

| Phase | Scope | Verification |
|-------|-------|-------------|
| 1 | engine.js — column rain +绕流 + trails | Particles display correctly with columns |
| 2 | core.js — idle dot at screen center | White dot visible when player hidden |
| 3 | gestures.js — right swipe → nextSong | Swipe changes song, particles deflect |
| 4 | effects.js — triple light burst ceremony | Song change shows 3-phase shockwave |
| 5 | Song info overlay (title/artist from core) | Text floats from core position |
| 6 | gestures.js — scroll wheel volume | Core click + scroll changes volume, orbit changes |
| 7 | physics.js — bullet time | Double-click toggles time gradient |
| 8 | gestures.js — long press search | Hold core → particles gather → search |
| 9 | core.js — state machine (thinking/speaking/error) | WebSocket events change core visual |
| 10 | Atmosphere auto-push + color lerp | Particles change color every 30s based on rules |
