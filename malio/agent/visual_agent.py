"""VisualAgent — particle and atmosphere control worker. Rule-based, no LLM.

Router delegates visual tasks → VisualAgent returns structured atmosphere/color/actions.
Wraps PersonaEngine for consistent personality constraints.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import re


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
        if task == "manage_rules":
            return await self._manage_rules(ctx.get("weather", {}))
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

    # ── Rule lifecycle management ────────────────────────────

    @staticmethod
    def _score_rule(rule: Dict, now_ts: float = None) -> float:
        """Score rule quality: f(hits, active, lifespan). 0=dead, 1=excellent."""
        hits = rule.get("_hits", 0)
        active = rule.get("_active", True)
        created_at = rule.get("_created_at") or rule.get("_added_at", 0)

        # Base: hits/50 caps at 1.0
        score = min(1.0, hits / 50.0)

        # Suppressed/dead rules heavily penalized
        if not active:
            score *= 0.2

        # Never-fired rules that are old → likely wrong
        lifespan_s = (now_ts or __import__('time').time()) - created_at if created_at else 0
        if hits == 0 and lifespan_s > 3600:
            score *= 0.1

        # Proven rules (hits > 10) get bonus
        if hits > 10:
            score = min(1.0, score + 0.15)

        return round(score, 2)

    async def _manage_rules(self, weather: Dict = None) -> Dict:
        """Evaluate all active rules against persona + weather + time.
        Suppress/boost/adjust rules without LLM. Called from atmosphere loop."""
        from core.state_manager import get_agent_rules

        rules = get_agent_rules()
        if not rules:
            return {"managed": 0, "changes": []}

        now = datetime.now()
        now_ts = now.timestamp()
        weather = weather or {}
        changes = []
        scored_ids = []

        for rule in rules:
            actions = rule.get("then", [])
            if not isinstance(actions, list):
                continue
            rule_changed = False

            # Track first-seen time for scoring
            if not rule.get("_added_at"):
                rule["_added_at"] = now_ts

            cond = (weather.get("condition") or "").lower()
            is_rain = any(w in cond for w in ("rain", "drizzle", "thunderstorm"))
            is_cloudy = "cloud" in cond
            is_deep_night = now.hour >= 23 or now.hour < 6
            is_bright_day = 8 <= now.hour < 18 and "clear" in cond

            for a in actions:
                target = a.get("target", "")
                val = a.get("val", 1)

                # Low energy: suppress speed/brightness boosts
                if self.persona.energy < 0.2:
                    if target == "speed" and isinstance(val, (int, float)) and val > 1.0:
                        rule["_active"] = False
                        rule["_suppressed_by"] = "low_energy"
                        rule_changed = True
                        changes.append(f"deactivated speed {val} (energy={self.persona.energy:.2f})")
                    if target == "brightness" and isinstance(val, (int, float)) and val > 0.7:
                        rule["_active"] = False
                        rule["_suppressed_by"] = "low_energy"
                        rule_changed = True

                # Rain/cloudy: warmify cool colors
                if (is_rain or is_cloudy) and target == "color":
                    if isinstance(val, str) and self._is_cool_color(val):
                        a["val"] = self._warmify_color(val)
                        rule_changed = True
                        changes.append(f"warmed {val} → {a['val']} ({cond})")

                # Deep night: cap speed, dim brightness
                if is_deep_night:
                    if target == "speed" and isinstance(val, (int, float)) and val > 0.8:
                        a["_night_val"] = val
                        a["val"] = round(val * 0.85, 2)
                        rule.setdefault("endWhen", {"type": "time_gt", "val": "06:00"})
                        rule_changed = True
                        changes.append(f"night-capped speed {val} → {a['val']}")
                    if target == "brightness" and isinstance(val, (int, float)) and val > 0.6:
                        a["val"] = round(val * 0.7, 2)
                        rule.setdefault("endWhen", {"type": "time_gt", "val": "06:00"})
                        rule_changed = True

                # Bright day: lift night caps
                if is_bright_day and target == "speed" and rule.get("endWhen", {}).get("val") == "06:00":
                    if "_night_val" in a:
                        a["val"] = a.pop("_night_val")
                    rule.pop("endWhen", None)
                    rule_changed = True
                    changes.append("lifted night speed cap")

            # Compute quality score and attach to rule
            score = self._score_rule(rule, now_ts)
            if rule.get("_score") != score:
                rule["_score"] = score
                rule_changed = True
            scored_ids.append(f"{rule.get('id','?')[-6:]}:{score}")

            if rule_changed and self.feedback_mgr:
                await self.feedback_mgr.push_rule(rule)

        return {"managed": len(rules), "changes": changes, "scores": scored_ids}

    # ── Color utilities ──────────────────────────────────────

    @staticmethod
    def _is_cool_color(hex_color: str) -> bool:
        """Check if a hex color is cool (blue-dominant, not near-black)."""
        m = re.match(r'#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', hex_color)
        if not m:
            return False
        r, g, b = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)
        return b > r and b > g and b > 120

    @staticmethod
    def _warmify_color(hex_color: str) -> str:
        """Shift a cool color toward warm by moving blue→red."""
        m = re.match(r'#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})', hex_color)
        if not m:
            return hex_color
        r, g, b = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16)
        nr = min(255, r + int(b * 0.6))
        nb = max(0, b - int(b * 0.5))
        return f"#{nr:02x}{g:02x}{nb:02x}"

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
