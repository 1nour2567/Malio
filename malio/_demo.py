"""Malio PersonaEngine Demo — constraint architecture in action.

Run from the repository root:
    python malio/_demo.py

Demonstrates that a forbidden action proposed by the LLM is replaced in code,
not filtered by prompt text.
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent.persona import PersonaEngine

pe = PersonaEngine()

# Force energy to 0.2 to trigger veto — simulate "tired agent"
pe.energy = 0.2

print("=" * 55)
print("  MALIO PersonaEngine — Constraint Architecture Demo")
print("=" * 55)
print(f"\n  Current persona: energy={pe.energy:.2f} warmth={pe.warmth:.2f}")

# LLM proposes light_burst (high-intensity visual effect)
llm_output = [
    {"action": "light_burst", "params": {"intensity": 0.9, "color": "#FF4444"}},
]

print("\n  LLM proposed: light_burst (intensity=0.9)")
print("  → PersonaEngine.constrain_core_actions() called...")

result = pe.constrain_core_actions(llm_output)

print(f"\n  Result:")
for r in result:
    print(f"    action: {r['action']}")
    print(f"    params: {r.get('params', {})}")

print(f"\n  Veto log ({len(pe._veto_log)} entries):")
for v in pe._veto_log[-3:]:
    print(f"    VETOED {v['vetoed']} → alt={v['alternative']}  ({v['reason']})")

print(f"\n  {'=' * 55}")
print("  LLM proposed light_burst. PersonaEngine vetoed it.")
print("  Substituted 'breath' — a gentle, low-energy alternative.")
print("  The LLM cannot override this. The code is the gate.")
print(f"  {'=' * 55}")