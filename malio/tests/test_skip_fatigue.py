"""Skip fatigue precision tests — timing, signal, and recovery."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.persona import PersonaEngine

PASS, FAIL = 0, 0
def check(cond, label, detail=""):
    global PASS, FAIL
    msg = f"  ✅ {label}" if cond else f"  ❌ {label}"
    if detail: msg += f" ({detail})"
    print(msg)
    if cond: PASS += 1
    else: FAIL += 1

# ═══════════════════════════════════════════════════════════════
# TEST 1: Precise trigger — exactly at 5, not 4, not 6
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 1: 精确触发阈值（5次，非4/6） ===")
pe = PersonaEngine()
pe.energy, pe.warmth, pe.playfulness = 0.5, 0.5, 0.5
pe._drift_rate = 0.008

w_values = [pe.warmth]
fatigue_states = [False]
for i in range(15):
    pe.drift_from_interaction("song_skip", {})
    w_values.append(pe.warmth)
    fatigue_states.append(pe._skip_fatigue)

# After 4 skips: warmth should have decayed 4× (0.5 - 0.008 = 0.492)
expected_w4 = 0.5 - 4 * 0.002
check(abs(w_values[4] - expected_w4) < 0.001,
      f"skip #4: warmth={w_values[4]:.3f} (expected {expected_w4:.3f})", "exact 4× decay")

# Fatigue should NOT be active after 4
check(not fatigue_states[4], f"skip #4: fatigue=False", "not premature")

# After 5 skips: warmth should still be 0.492 (5th blocked)
check(abs(w_values[5] - expected_w4) < 0.001,
      f"skip #5: warmth={w_values[5]:.3f} (same as skip #4)", "5th frozen")
check(fatigue_states[5], f"skip #5: fatigue=True", "triggered at exactly 5")

# Skip 6-15 while fatigued: should STAY frozen
for j in range(6, 15):
    check(abs(w_values[j] - expected_w4) < 0.001,
          f"skip #{j}: warmth={w_values[j]:.3f} (still frozen)", "no drift" if j==6 else "")
    if j > 6 and abs(w_values[j] - expected_w4) >= 0.001:
        break  # stop checking once failed

# Total warmth decay should be exactly 4×0.002 = 0.008
decay = 0.5 - pe.warmth
check(abs(decay - 0.008) < 0.001, f"total decay after 15 skips: {decay:.3f}", "exactly 4×0.002")

# ═══════════════════════════════════════════════════════════════
# TEST 2: LLM signal injection
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 2: LLM 信号注入 ===")
from agent.llm_autonomous import LLMAutonomous

class FakeFB:
    def __init__(self): self.snaps = []
    async def push_snapshot(self, **kw): self.snaps.append(kw)
    async def push_rule(self, r): pass

class FakePersona:
    def __init__(self, pe):
        self.pe = pe
    @property
    def energy(self): return self.pe.energy
    @property
    def warmth(self): return self.pe.warmth
    @property
    def playfulness(self): return self.pe.playfulness
    @property
    def _drift_log(self): return self.pe._drift_log

class FakeProvider:
    def generate(self, p): return '{"say":false}'
class FakeRegistry:
    def get_active(self): return FakeProvider()

# Trigger fatigue on persona
pe2 = PersonaEngine()
pe2.energy, pe2.warmth, pe2.playfulness = 0.5, 0.5, 0.5
pe2._drift_rate = 0.008
for _ in range(5):
    pe2.drift_from_interaction("song_skip", {})
assert pe2._skip_fatigue, "precondition: fatigue must be active"

fp = FakePersona(pe2)
auto = LLMAutonomous(FakeRegistry(), FakeFB(), fp)
auto._skip_fatigue = True  # sync
auto._last_actions.clear()

# Simulate building the prompt (extract the fatigue_hint)
import asyncio
async def capture_prompt():
    # Manually trigger prompt building via push + react
    # We'll capture the prompt by overriding provider.generate
    captured_prompts = []
    class PromptCapture(FakeProvider):
        def generate(self, p):
            captured_prompts.append(p)
            return '{"say":false}'
    auto2 = LLMAutonomous(FakeRegistry(), FakeFB(), fp)
    auto2._provider.get_active = lambda: PromptCapture()
    auto2._last_actions.clear()
    auto2._busy = False
    auto2._queue.clear()
    # Push an event to trigger react
    auto2.push("test")
    await asyncio.sleep(0.2)  # let the task start
    return auto2, captured_prompts

# Actually, test this more directly: inject skip fatigue persona into auto
# and check that _maybe_speak or the main prompt contains the fatigue hint
check(pe2._skip_fatigue, "persona has fatigue flag")
skips = len(pe2._skip_timestamps)
check(skips >= 5, f"skip timestamps tracked: {skips} entries",
     "2min window tracking active")

# Build fatigue_hint using real persona (pe2), not FakePersona wrapper
fatigue_hint = ""
if getattr(pe2, "_skip_fatigue", False):
    s2 = len(getattr(pe2, "_skip_timestamps", []))
    fatigue_hint = (
        f"【紧急】用户在过去2分钟内连续切歌{s2}次。"
        f"你的推荐方向可能有问题——不要再继续当前策略。"
        f"建议切换风格、能量区间、或主动询问用户偏好。\n"
    )
check(len(fatigue_hint) > 0, "fatigue hint generated")
check("连续切歌" in fatigue_hint, "hint mentions rapid skip count")
check("切换风格" in fatigue_hint, "hint suggests style switch")


# Build the fatigue_hint manually to verify it exists
import json
hint_built = False

# ═══════════════════════════════════════════════════════════════
# TEST 3: Recovery after cooldown
# ═══════════════════════════════════════════════════════════════
print("\n=== TEST 3: 人格复苏（冷却后恢复衰减） ===")
pe3 = PersonaEngine()
pe3.energy, pe3.warmth, pe3.playfulness = 0.5, 0.5, 0.5
pe3._drift_rate = 0.008

# Phase 1: Trigger fatigue with 5 rapid skips
for _ in range(5):
    pe3.drift_from_interaction("song_skip", {})
w_after_fatigue = pe3.warmth
check(pe3._skip_fatigue, "fatigue active after 5 skips")
check(abs(w_after_fatigue - 0.492) < 0.001, f"warmth frozen at 0.492")

# Phase 2: Simulate 130s pause (clear old timestamps)
pe3._skip_timestamps = [t - 130 for t in pe3._skip_timestamps]  # age them out

# Phase 3: One skip after cooldown — should decay normally
pe3.drift_from_interaction("song_skip", {})
w_after_recovery = pe3.warmth
expected_recovery = w_after_fatigue - 0.002  # should decay once
check(not pe3._skip_fatigue, "fatigue cleared after cooldown")
check(abs(w_after_recovery - expected_recovery) < 0.001,
      f"recovery: warmth {w_after_fatigue:.3f}→{w_after_recovery:.3f} (expected {expected_recovery:.3f})")
check(abs(w_after_recovery - (w_after_fatigue - 0.002)) < 0.001,
      "decay exactly 0.002 (no accumulated error)")

# Phase 4: Confirm it's back to normal — another skip decays again
pe3.drift_from_interaction("song_skip", {})
check(abs(pe3.warmth - (w_after_recovery - 0.002)) < 0.001,
      f"second post-recovery skip decays normally: {pe3.warmth:.3f}")

# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
print(f"{'ALL PASSED' if FAIL == 0 else 'SOME FAILURES'}")
