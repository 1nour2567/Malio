# Matrix Code Rain — Depth System Design

**Status**: Approved  
**Date**: 2026-05-12

## Overview

Add spatial depth to the existing Matrix code rain without compromising performance or the current visual identity. Three mechanisms working together: dual-layer parallax, vertical luminance gradient, and core-local glow.

## 1. Dual-Layer Parallax

Two independent MatrixRain instances sharing one canvas.

### Background Layer (distant)

| Property | Value |
|----------|-------|
| Columns | ~40 (wider spacing, ~28px gap) |
| Trail length | 4-8 chars (shorter) |
| Font size | 10px (smaller) |
| Color | `#0a2a0a` (darker, desaturated) |
| Speed multiplier | 0.4x (slower) |
| Fade alpha | 0.10 (faster fade = shorter trail) |
| Character set | Katakana only (simpler, less cognitive load) |

### Foreground Layer (near)

The current MatrixRain instance — unchanged. All interaction (绕流, gestures, core effects) happens here.

### Parallax Relationship

- Background layer draws first
- Foreground layer draws on top
- Shared `requestAnimationFrame` loop
- Background uses simplified physics: no card collision, no gesture response, pure vertical fall with column spring

### Performance Budget

| Layer | Columns | Chars/col | Total draw calls |
|-------|---------|-----------|-----------------|
| Background | ~40 | ~6 avg | ~240 |
| Foreground | ~90 | ~10 avg | ~900 |
| **Combined** | | | **~1140** |

Well within 60fps budget. No additional canvas needed — both layers render to same context.

## 2. Vertical Luminance Gradient

Zero-cost depth cue applied during foreground draw.

### Formula

For a character at screen Y position `y`, total screen height `H`:

```
brightness = 0.4 + 0.6 * (y / H)
```

- Top of screen (y=0): brightness = 0.4 (40% — distant, dim)
- Bottom of screen (y=H): brightness = 1.0 (100% — near, bright)

### Implementation

Applied per-character in the draw loop:

```javascript
const bright = 0.4 + 0.6 * (c.y / h);
ctx.fillStyle = lerpColor(BODY_COLOR, HEAD_COLOR, bright);
```

Where `lerpColor` interpolates between the dark body color and bright head color based on screen position.

### Why Bottom-Bright

- Matches how light falls in physical space: things closer to you are brighter
- Consistent with Matrix film aesthetic (characters "arrive" bright at bottom)
- Creates natural focal point at the interaction zone (card/core area, typically center-lower on screen)

## 3. Core-Local Glow

Subtle glow only on particles within 100px of the core position.

### Trigger Zone

- Particles within 100px Euclidean distance of core (x, y)
- Typically 20-40 particles at any moment
- Glow disabled entirely when core is inactive

### Implementation

```javascript
if (core.active) {
  const dist = Math.hypot(c.x - core.x, c.y - core.y);
  if (dist < 100) {
    const glowAlpha = (1 - dist / 100) * 0.3;
    ctx.shadowBlur = 8;
    ctx.shadowColor = core.color || '#22C55E';
    ctx.globalAlpha *= (1 + glowAlpha);
  }
}
// ... draw char ...
ctx.shadowBlur = 0;
ctx.shadowColor = 'transparent';
```

### Why Only Core-Local

- `shadowBlur` is the most expensive Canvas operation per draw call
- Limiting to ~30 particles keeps performance safe
- Focuses visual attention on the interaction target
- Glow color follows atmosphere color for emotional consistency

## 4. What We Don't Change

- Foreground column physics (绕流, trail, character cycling)
- Frame-buffer fade model
- Character set and phrase system
- `updateParams` API (backward compatible)
- Gesture system binding

## 5. Implementation Plan

### Step 1: Background Layer

Add a second column set to MatrixRain. Run simplified update (no physics) before foreground. ~30 lines.

### Step 2: Luminance Gradient

Modify foreground draw loop to apply Y-based brightness. ~5 lines.

### Step 3: Core-Local Glow

Add distance check + shadowBlur in foreground draw. Core position from existing core.js (Phase 2) or hardcoded to screen center for now. ~10 lines.

### Step 4: Tune

Adjust fade alpha, column counts, glow radius until layers feel balanced. Parameter tweaks only.

## 6. Acceptance Criteria

- [ ] Background layer visible as darker, slower, smaller rain
- [ ] Foreground characters visibly brighter at bottom than top
- [ ] Core area has subtle green glow (when core active)
- [ ] 60fps sustained on reference machine
- [ ] Existing gestures and interactions unaffected
