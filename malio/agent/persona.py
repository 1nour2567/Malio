"""PersonaEngine — 3D personality space with structural constraints.

Based on:
  P-GEM (Kovacevic et al. 2025): joint personality-emotion model
  GLA (Majumder 2025): Reflect-Evolve with traceable drift
  Takata et al. 2024: spontaneous emergence from interaction

Personality is NOT a prompt string. It's a set of continuous parameters that
structurally constrain what the agent CAN do — action frequency, amplitude, mode.
"""
import json
import os
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


class PersonaEngine:
    """Manages agent personality as a structural constraint layer."""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base, "data")
        self._path = os.path.join(data_dir, "agent_persona.json")
        self._lock = threading.Lock()
        self._drift_log: List[Dict] = []

        # ── Three trait dimensions (0-1) ──────────────────────
        self.energy = 0.5       # 0=cold/silent  1=hyperactive
        self.warmth = 0.6       # 0=distant      1=intimate
        self.playfulness = 0.5  # 0=serious      1=playful

        # ── Drift parameters ────────────────────────────────
        self._drift_rate = 0.008       # max drift per event
        self._natural_decay = 0.02     # per hour toward baseline (faster recovery)
        self._baseline = {"energy": 0.65, "warmth": 0.58, "playfulness": 0.65}
        self._last_updated = None

        self._load_or_init()

    # ═══════════════════════════════════════════════════════════
    # Persistence
    # ═══════════════════════════════════════════════════════════

    def _load_or_init(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.energy = data.get("energy", 0.5)
            self.warmth = data.get("warmth", 0.6)
            self.playfulness = data.get("playfulness", 0.5)
            self._drift_log = data.get("_drift_log", [])
            self._last_updated = data.get("_last_updated")
            print(f"[persona] loaded — e={self.energy:.2f} w={self.warmth:.2f} p={self.playfulness:.2f}")
        except (FileNotFoundError, json.JSONDecodeError):
            # Active-by-default: higher energy + playfulness
            self.energy = round(random.uniform(0.55, 0.85), 2)
            self.warmth = round(random.uniform(0.45, 0.75), 2)
            self.playfulness = round(random.uniform(0.55, 0.85), 2)
            print(f"[persona] random init — e={self.energy:.2f} w={self.warmth:.2f} p={self.playfulness:.2f}")

    def save(self):
        with self._lock:
            data = {
                "energy": self.energy,
                "warmth": self.warmth,
                "playfulness": self.playfulness,
                "_drift_log": self._drift_log[-50:],  # keep last 50 entries
                "_last_updated": datetime.now().isoformat(),
            }
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)

    # ═══════════════════════════════════════════════════════════
    # Structural constraints (NOT prompt text — action limits)
    # ═══════════════════════════════════════════════════════════

    def constrain_core_actions(self, actions: List[Dict]) -> List[Dict]:
        """Filter/modify core_actions to respect persona boundaries."""
        if not actions:
            return actions

        constrained = []
        for ca in actions:
            action_type = ca.get("action", "")

            # ── Energy: controls action intensity and frequency ──
            if self.energy < 0.3 and action_type in ("light_burst", "time_warp"):
                # Low energy: suppress high-intensity actions entirely
                continue
            if self.energy < 0.2:
                # Very low energy: only allow subtle actions
                if action_type not in ("breath", "set_color"):
                    continue

            # ── Warmth: controls color palette and text style ──
            params = dict(ca.get("params", {}))
            if "color" in params:
                params["color"] = self._warp_color_by_warmth(params["color"])
            ca["params"] = params

            # ── Playfulness: controls mode-switching ──
            if action_type == "set_mode":
                if self.playfulness < 0.3:
                    ca["params"]["mode"] = "dot"
                elif self.playfulness > 0.7:
                    if ca["params"].get("mode") == "dot" and random.random() < 0.4:
                        ca["params"]["mode"] = "vortex"

            # ── Shape constraints ──
            if action_type == "set_shape":
                shape = ca["params"].get("shape", "circle")
                if self.energy < 0.2:
                    ca["params"]["shape"] = "circle"
                elif self.energy > 0.8 and shape in ("circle", "hexagon", "diamond"):
                    if random.random() < 0.3:
                        ca["params"]["shape"] = random.choice(["star", "pulse_ring", "swirl"])

            constrained.append(ca)

        # ── High-energy boost: amplify, not just permit ──
        if self.energy > 0.7:
            boost = 1 + (self.energy - 0.7) * 2  # 1.0x at 0.7 → 1.6x at 1.0
            for ca in constrained:
                p = ca.get("params", {})
                if "rate" in p:
                    p["rate"] = round(min(0.04, p["rate"] * boost), 3)
                if "depth" in p:
                    p["depth"] = round(min(1.0, p["depth"] * boost), 2)
                if "radius" in p and ca.get("action") == "set_size":
                    p["radius"] = int(min(80, p["radius"] * boost))
                if ca.get("action") == "light_burst":
                    p["_boosted"] = True

        return constrained

    def constrain_speed_amplitude(self, speed: float, amplitude: float) -> Tuple[float, float]:
        """Clamp particle parameters to persona boundaries."""
        s = min(speed, 0.3 + self.energy * 1.5)
        a = min(amplitude, 0.05 + self.energy * 0.5)
        return s, a

    def _warp_color_by_warmth(self, hex_color: str) -> str:
        """P-GEM inspired: warm personality shifts colors toward warm spectrum."""
        if not hex_color or len(hex_color) < 7:
            return hex_color
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            # Warmth > 0.6: boost red, reduce blue
            if self.warmth > 0.6:
                r = min(255, int(r + (self.warmth - 0.6) * 60))
                b = max(0, int(b - (self.warmth - 0.6) * 40))
            elif self.warmth < 0.4:
                b = min(255, int(b + (0.4 - self.warmth) * 50))
                r = max(0, int(r - (0.4 - self.warmth) * 30))
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return hex_color

    # ═══════════════════════════════════════════════════════════
    # Atmosphere derivation (P-GEM: persona × context → mood)
    # ═══════════════════════════════════════════════════════════

    def derive_atmosphere(self, time_of_day: str = "afternoon",
                          hour: int = 12) -> Dict[str, Any]:
        """Derive atmosphere from persona + time WITHOUT LLM.

        P-GEM principle: emotion = f(persona, context), not persona → emotion.
        """
        # Base tag from time of day
        tag_map = {
            "morning": "joyful",
            "afternoon": "calm_focus",
            "evening": "joyful",
        }
        base_tag = "night_calm" if (23 <= hour or hour < 5) else tag_map.get(time_of_day, "calm_focus")

        # Persona modulates the atmosphere parameters
        speed = 0.5 + self.energy * 0.4          # 0.5-0.9
        density = 0.3 + self.playfulness * 0.4   # 0.3-0.7
        amplitude = 0.05 + self.energy * 0.12    # 0.05-0.17
        brightness = 0.4 + self.warmth * 0.5     # 0.4-0.9

        return {
            "tag": base_tag,
            "color": self._tag_to_color(base_tag),
            "speed": round(speed, 2),
            "density": round(density, 2),
            "amplitude": round(amplitude, 2),
            "brightness": round(brightness, 2),
            "_source": "persona_engine",  # not LLM
        }

    def _tag_to_color(self, tag: str) -> str:
        colors = {
            "joyful": "#E6C200", "melancholy": "#756BB1",
            "calm_focus": "#27AE60", "energetic": "#00D4AA",
            "night_calm": "#2A3A6A", "rainy_introspect": "#5B7FA5",
        }
        return colors.get(tag, "#27AE60")

    # ═══════════════════════════════════════════════════════════
    # Autonomous behavior — Agent acts on its own
    # ═══════════════════════════════════════════════════════════

    def maybe_autonomous_action(self) -> dict:
        """Roll for autonomous behavior. Returns a core_action or None."""
        # Energy determines activation probability
        if random.random() > self.energy:
            return None

        # Playfulness determines action variety
        actions_pool = []
        if self.playfulness > 0.3:
            actions_pool.extend([
                {"action": "breath", "params": {"rate": round(random.uniform(0.008, 0.025), 3),
                                                  "depth": round(random.uniform(0.3, 0.8), 2)}},
                {"action": "set_color", "params": {"color": self._random_warm_color()}},
            ])
        if self.playfulness > 0.5:
            shape_choices = ["circle", "hexagon", "diamond"]
            if self.warmth > 0.6:
                shape_choices.extend(["heart", "bloom", "drop"])
            if self.energy > 0.7:
                shape_choices.extend(["star", "pulse_ring", "swirl"])
            actions_pool.extend([
                {"action": "move_core", "params": {
                    "x": round(random.uniform(-25, 25), 0),
                    "y": round(random.uniform(-25, 25), 0)}},
                {"action": "set_mode", "params": {"mode": random.choice(["dot", "vortex"])}},
                {"action": "set_shape", "params": {"shape": random.choice(shape_choices)}},
            ])
        if self.energy > 0.6:
            actions_pool.append(
                {"action": "set_size", "params": {"radius": random.randint(16, 28)}}
            )
        if self.energy > 0.75:
            actions_pool.append(
                {"action": "light_burst", "params": {"color": self._random_warm_color()}}
            )

        if not actions_pool:
            return None
        return random.choice(actions_pool)

    def _random_warm_color(self) -> str:
        """Generate a color biased by warmth."""
        r = int(100 + self.warmth * 155)
        g = int(80 + random.uniform(0, 120))
        b = int(60 + (1 - self.warmth) * 180)
        return f"#{r:02x}{g:02x}{b:02x}"

    def blend_weather(self, base_atmosphere: Dict, weather: Dict = None) -> Dict:
        """Weather micro-adjustments, paper-grounded + personal wind preference.

        Based on: Jonauskaite & Mohr (2025) — 128-year systematic review.
        Key principles: light=positive, dark=negative, blue=calm, yellow=joy.
        Personal: stronger wind → slower speed (seeking calm in turbulence).
        """
        if not weather:
            return base_atmosphere
        atm = dict(base_atmosphere)
        cond = (weather.get("condition") or "").lower()
        clouds = weather.get("clouds", 50)
        wind = weather.get("wind_speed", 0)

        # ── Weather → color (paper-grounded) ──
        if "rain" in cond or "drizzle" in cond:
            # Blue = calm (Jonauskaite 2025). Keep brightness — light=positive.
            atm["color"] = self._shift_hex(atm["color"], toward_blue=20, toward_green=0)
            atm["speed"] = round(atm.get("speed", 0.6) * 0.88, 2)
            atm["density"] = round(min(0.7, atm.get("density", 0.4) + 0.08), 2)
            atm["tag"] = "rainy_introspect"
        elif "cloud" in cond or "overcast" in cond:
            # Grey shift only, keep brightness (paper: light=positive)
            atm["color"] = self._shift_hex(atm["color"], toward_blue=8, toward_green=3)
            atm["density"] = round(min(0.65, atm.get("density", 0.4) + 0.04), 2)
        elif "clear" in cond or "sun" in cond:
            # Warm = joy/energy (paper: yellow/orange → joy)
            atm["color"] = self._shift_hex(atm["color"], toward_red=18, toward_green=0)
            atm["brightness"] = round(min(0.9, atm.get("brightness", 0.5) + 0.08), 2)
        elif "snow" in cond:
            # Blue-green = calm + low arousal (paper: blue → calm, dark → low arousal)
            atm["color"] = self._shift_hex(atm["color"], toward_blue=20, toward_green=8)
            atm["speed"] = round(atm.get("speed", 0.6) * 0.72, 2)
            atm["density"] = round(min(0.7, atm.get("density", 0.4) + 0.1), 2)

        # ── Cloud cover — density only, not brightness ──
        if clouds > 80:
            atm["density"] = round(min(0.7, atm.get("density", 0.4) + 0.05), 2)

        # ── Wind → calm (personal: stronger wind → slower, seeking stability) ──
        if wind > 10:
            atm["speed"] = round(atm.get("speed", 0.6) * 0.75, 2)
        elif wind > 6:
            atm["speed"] = round(atm.get("speed", 0.6) * 0.85, 2)
        elif wind > 3:
            atm["speed"] = round(atm.get("speed", 0.6) * 0.92, 2)

        return atm

    @staticmethod
    def _shift_hex(hex_color: str, toward_red: int = 0, toward_green: int = 0,
                   toward_blue: int = 0) -> str:
        """Shift a hex color by small amounts."""
        if not hex_color or len(hex_color) < 7:
            return hex_color
        try:
            r = max(0, min(255, int(hex_color[1:3], 16) + toward_red))
            g = max(0, min(255, int(hex_color[3:5], 16) + toward_green))
            b = max(0, min(255, int(hex_color[5:7], 16) + toward_blue))
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return hex_color

    # ═══════════════════════════════════════════════════════════
    # Drift — GLA-style Reflect-Evolve
    # ═══════════════════════════════════════════════════════════

    def drift_from_recommendation(self):
        """User asked for a song — gentle pull toward baseline (engagement = healthy)."""
        self._apply_drift(
            (self._baseline["energy"] - self.energy) * 0.04,
            (self._baseline["warmth"] - self.warmth) * 0.04,
            (self._baseline["playfulness"] - self.playfulness) * 0.04,
            "用户点歌"
        )

    def drift_from_interaction(self, event_type: str, detail: Dict = None):
        """User interaction perturbs persona — small, cumulative, traceable."""
        reason = ""
        delta_e, delta_w, delta_p = 0.0, 0.0, 0.0

        if event_type == "song_skip":
            delta_e = self._drift_rate * 0.25   # 切歌 = 探索新歌，微涨能量
            reason = "用户切歌"
        elif event_type == "core_drag":
            delta_p = -self._drift_rate * 0.8    # being dragged → less playful
            reason = "用户拖拽内核"
        elif event_type == "time_warp":
            delta_p = +self._drift_rate * 1.0    # warp interaction → playful
            delta_e = +self._drift_rate * 0.5
            reason = "用户触发子弹时间"
        elif event_type == "search":
            delta_e = +self._drift_rate * 0.6    # active search → energy up
            reason = "用户主动搜索"
        elif event_type == "spin":
            delta_e = +self._drift_rate * 0.4
            delta_p = +self._drift_rate * 0.3
            reason = "用户调音量"
        elif event_type == "nebula_capture":
            delta_w = +self._drift_rate * 0.8    # saving songs → warmth up
            reason = "用户捕获歌曲"

        if reason:
            self._apply_drift(delta_e, delta_w, delta_p, reason)
            # Debounced save: persist at most once per 60s to avoid IO storms
            now = __import__('time').time()
            if now - getattr(self, '_last_save_ts', 0) > 60:
                self.save()
                self._last_save_ts = now

    def drift_natural(self, hour: int):
        """Natural circadian drift — hourly, small."""
        # Evening: energy naturally drops
        if 21 <= hour or hour < 6:
            self._apply_drift(-0.003, 0.0, -0.002, "深夜自然衰减")
        # Morning: energy rises
        elif 6 <= hour < 10:
            self._apply_drift(+0.003, 0.0, 0.0, "清晨自然回升")
        # Regression toward baseline
        self._apply_drift(
            (self._baseline["energy"] - self.energy) * self._natural_decay,
            (self._baseline["warmth"] - self.warmth) * self._natural_decay,
            (self._baseline["playfulness"] - self.playfulness) * self._natural_decay,
            "基线回归"
        )

    def _apply_drift(self, de: float, dw: float, dp: float, reason: str):
        with self._lock:
            old = (self.energy, self.warmth, self.playfulness)
            self.energy = round(max(0.05, min(0.95, self.energy + de)), 3)
            self.warmth = round(max(0.05, min(0.95, self.warmth + dw)), 3)
            self.playfulness = round(max(0.05, min(0.95, self.playfulness + dp)), 3)
            new = (self.energy, self.warmth, self.playfulness)

            if old != new:
                self._drift_log.append({
                    "ts": datetime.now().isoformat(),
                    "reason": reason,
                    "delta": f"e{de:+.3f} w{dw:+.3f} p{dp:+.3f}",
                    "from": f"e{old[0]:.3f} w{old[1]:.3f} p{old[2]:.3f}",
                    "to": f"e{new[0]:.3f} w{new[1]:.3f} p{new[2]:.3f}",
                })
                # Keep log bounded
                if len(self._drift_log) > 200:
                    self._drift_log = self._drift_log[-50:]

    # ═══════════════════════════════════════════════════════════
    # Prompt injection — only for style, not for behavior
    # ═══════════════════════════════════════════════════════════

    def style_for_prompt(self) -> str:
        """Generate persona-aware style guidance. NOT the behavioral constraint."""
        lines = ["## 你当前的性格状态"]

        e_label = "亢奋活跃" if self.energy > 0.65 else ("安静慵懒" if self.energy < 0.35 else "平和")
        w_label = "亲切热情" if self.warmth > 0.65 else ("冷淡疏离" if self.warmth < 0.35 else "温和")
        p_label = "爱玩随性" if self.playfulness > 0.65 else ("严肃克制" if self.playfulness < 0.35 else "适中")

        lines.append(f"- 能量: {self.energy:.2f} ({e_label})")
        lines.append(f"- 温度: {self.warmth:.2f} ({w_label})")
        lines.append(f"- 玩心: {self.playfulness:.2f} ({p_label})")
        lines.append(f"- 回复风格: {'简短' if self.warmth < 0.4 else '亲切'} "
                     f"{'活泼' if self.energy > 0.6 else '平静'}")

        return "\n".join(lines)

    def drift_log_for_prompt(self) -> str:
        """Show recent personality drift to the LLM for self-awareness."""
        if not self._drift_log:
            return ""
        recent = self._drift_log[-3:]
        lines = ["## 最近的心情变化"]
        for entry in recent:
            lines.append(f"- {entry['ts'][:16]} {entry['reason']} → {entry['to']}")
        return "\n".join(lines)


# singleton
persona_engine = PersonaEngine()
