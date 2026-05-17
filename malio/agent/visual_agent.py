"""VisualAgent — particle and atmosphere control worker. Rule-based, no LLM.

Router delegates visual tasks → VisualAgent returns structured atmosphere/color/actions.
Wraps PersonaEngine for consistent personality constraints.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime


class VisualAgent:
    """Handles all particle, color, and atmosphere control.

    Rule-engine, not LLM. Uses PersonaEngine for consistent personality.
    Can be extended with LLM for creative visual descriptions.
    """

    def __init__(self, persona_engine, feedback_mgr=None, scene_engine=None):
        self.persona = persona_engine
        self.feedback_mgr = feedback_mgr
        self.scene_engine = scene_engine

    # ── Task dispatcher ──────────────────────────────────────

    async def execute(self, task: str, context: Dict = None) -> Dict:
        """Dispatch visual tasks. Returns results that Router can use."""
        ctx = context or {}

        if task == "atmosphere":
            return self._derive_atmosphere(ctx)
        if task == "constrain":
            return self._constrain(ctx.get("core_actions", []))
        if task == "color_blend":
            return self._color_blend(ctx)
        if task == "autonomous":
            return self._autonomous_action()
        if task == "weather_blend":
            return self._weather_blend(ctx.get("atmosphere", {}))
        return {"error": f"VisualAgent: unknown task '{task}'"}

    # ── Atmosphere derivation ────────────────────────────────

    def _derive_atmosphere(self, ctx: Dict) -> Dict:
        """Persona × time → atmosphere. No LLM."""
        now = datetime.now()
        tod = ("morning" if 5 <= now.hour < 12 else
               "afternoon" if 12 <= now.hour < 18 else
               "evening" if 18 <= now.hour < 22 else "night")
        atm = self.persona.derive_atmosphere(tod, now.hour)

        # Weather blend
        if self.scene_engine:
            try:
                weather = self.scene_engine.get_weather_context(24.9175, 118.6465) or {}
                atm = self.persona.blend_weather(atm, weather)
            except Exception:
                pass

        return {"atmosphere": atm}

    # ── Constraint filtering ─────────────────────────────────

    def _constrain(self, actions: List[Dict]) -> Dict:
        """Filter core_actions through persona boundaries."""
        constrained = self.persona.constrain_core_actions(actions)
        return {"core_actions": constrained}

    # ── Color blend ──────────────────────────────────────────

    def _color_blend(self, ctx: Dict) -> Dict:
        """Compute weighted blend: persona 45% + E/W/D 40% + cover 10% + jitter 5%."""
        persona_color = ctx.get("persona_color", "#27AE60")
        ewd_color = ctx.get("ewd_color", persona_color)
        cover_color = ctx.get("cover_color", ewd_color)

        weights = [0.45, 0.40, 0.10]
        hexes = [persona_color, ewd_color, cover_color]
        tr = tg = tb = tw = 0

        for i in range(3):
            h = hexes[i] or "#27AE60"
            wt = weights[i]
            tr += int(h[1:3], 16) * wt
            tg += int(h[3:5], 16) * wt
            tb += int(h[5:7], 16) * wt
            tw += wt

        # Jitter 5%
        import random
        tr += (random.random() - 0.5) * 13
        tg += (random.random() - 0.5) * 13
        tb += (random.random() - 0.5) * 13
        tw += 0.05

        r = max(0, min(255, round(tr / tw)))
        g = max(0, min(255, round(tg / tw)))
        b = max(0, min(255, round(tb / tw)))

        return {"blended_color": f"#{r:02x}{g:02x}{b:02x}"}

    # ── Autonomous behavior ──────────────────────────────────

    def _autonomous_action(self) -> Dict:
        """Random autonomous core_action based on persona state."""
        action = self.persona.maybe_autonomous_action()
        return {"core_action": action} if action else {}

    # ── Weather blend standalone ─────────────────────────────

    def _weather_blend(self, atmosphere: Dict) -> Dict:
        """Apply weather adjustments to an existing atmosphere."""
        if not self.scene_engine:
            return {"atmosphere": atmosphere}
        try:
            weather = self.scene_engine.get_weather_context(24.9175, 118.6465) or {}
            blended = self.persona.blend_weather(atmosphere, weather)
            return {"atmosphere": blended}
        except Exception:
            return {"atmosphere": atmosphere}
