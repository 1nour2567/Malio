# Malio Core Expression System — Design

**Status**: Draft  
**Date**: 2026-05-12

## Overview

The core lens gets an expression system: a breathing ring (default), drag-with-emotional-return behavior, and transient state rings (volume/progress). The core is Malio's "face" — it expresses emotion through light, not text.

## 1. Breathing Ring (Default State)

### Appearance
- 1-2px circular stroke around the core lens
- Color: atmosphere emotional color from `color-map.json` (with smooth lerp transitions)
- Semi-transparent, like camera lens coating reflection

### Breathing Behavior
| State | Ring Behavior |
|-------|--------------|
| Playing music | Brightness pulses 60%→100% at ~0.5Hz (subtle, not distracting) |
| Paused (bullet time) | Brightness drops to 30%, static, "sleeping" |
| Agent thinking/speaking | Rapid subtle flicker, synced with core pulse |
| Emotion change | Color smoothly lerps to new emotional color over ~3s |

### Visual Spec
- Ring radius: core.radius + 6px (sits just outside the lens)
- Stroke width: 1.5px
- Opacity range: 0.15 (breath-low) to 0.35 (breath-high)
- Drawn with `ctx.arc()` + `ctx.stroke()`, separate from particle rendering

## 2. Drag Behavior

### Interaction
- User can grab the core by clicking/touching within the ring radius
- While dragging, core follows cursor/touch with slight inertia (weight feel)
- On release: core slowly drifts back to screen center

### Emotional Return Physics

The return behavior changes based on current emotional tag:

| Emotion | Return Speed | Trajectory | Visual |
|---------|-------------|-----------|--------|
| Joyful | Fast (3s), bouncy | Slight overshoot, "hops" | Ring brightens during return |
| Calm / Night calm | Medium (6s), smooth | Gentle arc, no oscillation | Ring gently pulses |
| Energetic | Fast (2s), snappy | Quick with micro-vibrations | Ring flickers rapidly |
| Melancholy | Slow (10s), heavy | Wide arc, particles trail behind | Ring dim, particles scatter wider |
| Focusing | Very slow (12s), resistant | Stays near release point, micro-tremors | Ring barely visible, core small |

### Return Speed Cap
- Maximum return speed: **300px/s**. On wide screens (e.g., 2560px), return time automatically extends rather than accelerating indefinitely.
- Formula: `return_time = max(emotional_base_time, distance / 300)`
- Example: melancholy core dragged to far corner on 2560px screen → ~8.5s return (capped), not instant.

### Focusing "First Touch" Hint
- First time a user drags the core while in Focusing state, a tiny particle text floats near the core: "正在专注..."
- Shown **once per session**, never repeated
- Prevents users from mistaking the near-static behavior as a bug

### Implementation
- Physics model: spring-damper with emotional parameters
- Target position: always screen center
- Spring constant (k) and damping (d) vary by emotion
- Return completes within 2-12 seconds depending on emotion

## 3. Transient State Rings

### Volume Ring
- Trigger: tap core → rotate/scroll to adjust volume
- Ring becomes a filled arc (0% → 100%)
- Filled portion = current volume level, bright
- Unfilled portion = dim outline
- Auto-fades back to breathing ring 2 seconds after last input

### Progress Ring
- Trigger: single tap on core (no rotation within 400ms)
- Ring becomes a progress arc (0% → 100%)
- Filled portion = current song progress
- Auto-fades back to breathing ring 3 seconds after display

### Future: Jump-Click Volume
- Clicking a point on the volume ring to jump to that volume level (e.g., 3-o'clock = 50%)
- Not in current implementation; noted for later enhancement

### Transition
- Switching between breathing ↔ state ring: 300ms smooth morph
- Implemented as lerp between arc endpoints and opacities

## 4. Technical Notes

- All ring drawing happens in `_animate()` after particle rendering but before `requestAnimationFrame`
- Emotional state comes from `this.params.color` (set by WebSocket atmosphere)
- Drag uses existing `mousedown`/`touchstart` on canvas — extend existing `_bindDrag()`
- Ring color lerp uses HSL interpolation for smoother transitions than RGB

## 5. Acceptance Criteria

- [ ] Breathing ring visible around core, color matches atmosphere
- [ ] Ring pulses subtly during playback, dims when paused
- [ ] Core is draggable, returns to center on release
- [ ] Return speed varies by emotion (joyful=fast, melancholy=slow)
- [ ] Volume ring appears when rotating, shows fill level
- [ ] Progress ring appears on single tap, fades after 3s
- [ ] All ring states transition smoothly (300ms morph)
