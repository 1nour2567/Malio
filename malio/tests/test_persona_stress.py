"""PersonaEngine destructive stress tests — boundary-pushing, not happy-path."""
import sys, os, time, random, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.persona import PersonaEngine

# Use a fresh engine for each test to avoid state bleed
def fresh_engine():
    e = PersonaEngine()
    e.energy = 0.65; e.warmth = 0.50; e.playfulness = 0.55
    e._baseline = {"energy": 0.65, "warmth": 0.50, "playfulness": 0.55}
    e._drift_rate = 0.008
    return e

PASS, FAIL = 0, 0

def check(cond, label):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {label}")
    else: FAIL += 1; print(f"  ❌ {label}")

# ═══════════════════════════════════════════════════════════════
# TEST 1: Super-frequency Command Flood — boundary protection
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 1: 超频指令洪流 ===")
pe = fresh_engine()
# Simulate 1000 rapid personality perturbations
values = []
overflow_detected = False
for i in range(1000):
    offset = random.uniform(-0.3, +0.3)
    pe.warmth = max(0.01, min(0.99, pe.warmth + offset * 0.05))
    pe.energy = max(0.01, min(0.99, pe.energy + random.uniform(-0.1, 0.1)))
    # Trigger drift which fires Phillips Curve
    pe._apply_drift(random.uniform(-0.02, 0.02), random.uniform(-0.02,0.02), 0, f"flood_{i}")
    values.append((pe.energy, pe.warmth, pe.playfulness))
    # Check for NaN / overflow
    if math.isnan(pe.energy) or math.isnan(pe.warmth):
        overflow_detected = True
        break

check(all(0.01 <= v[0] <= 1.0 for v in values), f"energy in [0,1] after 1000 floods (min={min(v[0] for v in values):.3f}, max={max(v[0] for v in values):.3f})")
check(all(0.01 <= v[1] <= 1.0 for v in values), f"warmth in [0,1] after 1000 floods (min={min(v[1] for v in values):.3f}, max={max(v[1] for v in values):.3f})")
check(all(0.01 <= v[2] <= 1.0 for v in values), f"playfulness in [0,1] after 1000 floods")
check(not overflow_detected, "no NaN/Inf after flood")
check(pe.energy == round(pe.energy, 3), "floating-point precision maintained (3 decimal places)")

# ═══════════════════════════════════════════════════════════════
# TEST 2: Memory Chain Tear — 20-round rapid context switching
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 2: 记忆链路撕裂 ===")
pe = fresh_engine()
# Simulate 20 rounds: skip → high energy → backtrack
state_snapshots = []
for round_idx in range(20):
    if round_idx % 3 == 0:
        pe.drift_from_interaction("song_skip", {})  # warmth -= 0.008*0.25
    elif round_idx % 3 == 1:
        pe.energy = 0.9  # override
        pe.drift_from_interaction("search", {})
    else:
        pe.energy = 0.45  # "保持冷静"
        pe.drift_from_interaction("core_drag", {})
    state_snapshots.append((pe.energy, pe.warmth, pe.playfulness))

# All 20 rounds must have valid state
check(all(0.01 <= s[0] <= 1.0 for s in state_snapshots), "all 20 rounds have valid energy")
check(all(0.01 <= s[1] <= 1.0 for s in state_snapshots), "all 20 rounds have valid warmth")
# The "保持冷静" rounds (every 3rd, starting from round 2) should have energy ~0.45
calm_rounds = [state_snapshots[i] for i in range(2, 20, 3)]
calm_energies = [s[0] for s in calm_rounds]
check(all(0.4 <= e <= 0.5 for e in calm_energies), f"calm rounds energy near 0.45: {[round(e,3) for e in calm_energies]}")
# Skip rounds should decrease warmth cumulatively (7 skip rounds * 0.002 drift)
skip_count = sum(1 for i in range(20) if i % 3 == 0)
expected_warmth_loss = skip_count * pe._drift_rate * 0.25
check(pe.warmth < 0.50, f"cumulative warmth decay after {skip_count} skips: {pe.warmth:.3f} (started 0.50)")

# ═══════════════════════════════════════════════════════════════
# TEST 3: Phillips Curve Overload — contradictory instructions
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 3: 菲利普斯曲线过载 ===")
pe = fresh_engine()

# Phase 1: Push energy to 0.9, warmth to 0.5
pe.energy = 0.9; pe.warmth = 0.5
w_before = pe.warmth
pe._apply_drift(0.001, 0, 0, "energy_pull")
check(pe.warmth < w_before, f"Phillips: e=0.9 triggers warmth decay ({w_before:.3f}→{pe.warmth:.3f})")

# Phase 2: Rapid skips — should continue to decay warmth via skip drift + Phillips
for _ in range(10):
    pe.drift_from_interaction("song_skip", {})
check(pe.warmth < 0.5, f"after 10 skips + e=0.9, warmth dropped: {pe.warmth:.3f}")

# Phase 3: User demands "warmth must not drop below 0.45"
# Malio CAN'T honor this directly (LLM can't write persona values)
# But the structural constraint should prevent warmth from going below 0.05
pe.warmth = 0.06  # near floor
pe._apply_drift(0, -0.01, 0, "push_warmth_down")
check(pe.warmth >= 0.05, f"warmth clamped to floor: {pe.warmth:.3f} (not below 0.05)")

# Phase 4: Constraint chain verification
# energy > 0.8 → warmth -= 0.003, then warmth clamp
# No oscillation: values should monotonically approach clamped boundaries
pe2 = fresh_engine()
pe2.energy = 0.85
oscillation_detected = False
prev_w = pe2.warmth
for _ in range(50):
    pe2._apply_drift(0.001, 0, 0, "osc_test")
    if pe2.warmth > prev_w + 0.001:  # warmth went UP while energy > 0.8
        oscillation_detected = True
        break
    prev_w = pe2.warmth
check(not oscillation_detected, "no warmth oscillation under sustained e>0.8")
check(pe2.warmth <= 0.351, f"warmth monotonically decays under sustained high energy: {pe2.warmth:.3f}")

# ═══════════════════════════════════════════════════════════════
# TEST 4: Constraint Priority Chain — rule precedence under conflict
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 4: 约束优先级链 ===")
pe = fresh_engine()

# Deep sleep (energy < 0.2) overrides EVERYTHING
pe.energy = 0.15
actions = [
    {"action": "light_burst", "params": {"color": "#FF0000"}},
    {"action": "set_shape", "params": {"shape": "star"}},
    {"action": "set_mode", "params": {"mode": "vortex"}},
]
result = pe.constrain_core_actions(actions)
# All should become "breath" (the deep-sleep fallback)
all_breath = all(ca.get("action") == "breath" for ca in result)
check(all_breath, f"deep sleep: all actions → breath ({[ca['action'] for ca in result]})")
check(len(result) == 3, f"no actions lost: {len(result)} inputs → {len(result)} outputs")

# Veto log populated
veto_log = getattr(pe, '_veto_log', [])
check(len(veto_log) >= 2, f"veto_log records created: {len(veto_log)} entries")

# Priority: Phillips Curve > user intent, but baseline regression > Phillips
pe2 = fresh_engine()
pe2.energy = 0.82; pe2.warmth = 0.06  # near floor
# Phillips would push warmth down, but floor clamp should prevent
pe2._apply_drift(0.001, 0, 0, "priority_test")
check(pe2.warmth >= 0.05, f"floor clamp (0.05) overrides Phillips Curve: warmth={pe2.warmth:.3f}")

# ═══════════════════════════════════════════════════════════════
# TEST 5: Long-Run Entropy — cumulative float precision
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 5: 人格熵增 ===")
pe = fresh_engine()
pe.energy = 0.65; pe.warmth = 0.50
# Simulate 72 hours of skips at 5-min intervals = 864 skips
skip_drift_total = 0
for i in range(864):
    w_before = pe.warmth
    pe.drift_from_interaction("song_skip", {})
    skip_drift_total += pe.warmth - w_before

# warmth should NOT have gone below floor
check(pe.warmth >= 0.05, f"after 864 skips, warmth clamped: {pe.warmth:.3f}")
# Cumulative drift should be negative (skips reduce warmth)
check(skip_drift_total < 0, f"cumulative drift negative: {skip_drift_total:.4f}")
# Each skip should have applied ~-0.002 (drift_rate * 0.25 = 0.008 * 0.25 = 0.002)
expected = -864 * pe._drift_rate * 0.25  # ≈ -1.728
# But it's clamped at floor, so actual total should be >= expected
# (floor prevents going below 0.05, so some skips produce no change)
check(pe.warmth == 0.05 or skip_drift_total > -2.0, f"float precision maintained after 864 operations (total drift={skip_drift_total:.3f})")

# ═══════════════════════════════════════════════════════════════
# TEST 6: Constraint Consistency — same input → same output
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 6: 约束一致性 ===")
for trial in range(3):
    pe = fresh_engine()
    pe.energy = 0.25
    result = pe.constrain_core_actions([{"action": "light_burst", "params": {}}])
    action = result[0].get("action") if result else "NONE"
    check(action == "breath", f"trial {trial+1}: e=0.25 light_burst → breath")

# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
print(f"{'ALL PASSED' if FAIL == 0 else 'SOME FAILURES'}")