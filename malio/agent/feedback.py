"""Stage 5: Real-time feedback — WebSocket state broadcasting."""
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import WebSocket
import asyncio
import json
import os


STRATEGY_TARGETS = {"genre_boost", "genre_suppress", "energy_bias",
                   "novelty_bias", "language_bias"}


def _is_strategy_rule(rule: dict) -> bool:
    """Strategy rules affect recommendation, not particles — frontend doesn't need them."""
    for action in (rule.get("then") if isinstance(rule.get("then"), list) else []):
        if action.get("target") in STRATEGY_TARGETS:
            return True
    return False


class Feedback:
    def __init__(self):
        self._connections: List[WebSocket] = []
        self._seq = 0
        self._color_map = self._load_color_map()
        self._perception = None  # set by main.py after init

    @staticmethod
    def _load_color_map() -> Dict[str, Any]:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, "user", "color-map.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def register(self, ws: WebSocket):
        self._connections.append(ws)

    def unregister(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    def build_snapshot(self, **overrides) -> Dict[str, Any]:
        self._seq += 1
        snapshot: Dict[str, Any] = {
            "type": "state_snapshot",
            "song": None,
            "playlist": [],
            "is_playing": False,
            "agent_log": "",
            "tool_error": None,
            "atmosphere": None,
            "core_mode": "dot",      # dot / vortex / error
            "core_action": None,     # Agent-commanded core action
            "weather": None,          # raw weather context for DSL rules
            "timestamp": datetime.now().isoformat(),
            "seq": self._seq,
        }
        snapshot.update(overrides)
        return snapshot

    async def push_snapshot(self, **overrides):
        snapshot = self.build_snapshot(**overrides)
        dead: List[WebSocket] = []

        async def _send_one(ws):
            try:
                await ws.send_json(snapshot)
            except Exception as exc:
                print(f"[feedback] send failed: {exc}")
                dead.append(ws)

        await asyncio.gather(*[_send_one(ws) for ws in self._connections], return_exceptions=True)
        for ws in dead:
            self.unregister(ws)

    async def push_agent_log(self, message: str):
        await self.push_snapshot(agent_log=message)

    async def push_rule(self, rule: Dict[str, Any]):
        """Broadcast a DSL rule to all connected WebSocket clients.

        Strategy rules (genre_boost, energy_bias, etc.) are server-side only —
        they affect the recommendation engine, not particle rendering.
        Skip WebSocket broadcast for those.
        """
        if _is_strategy_rule(rule):
            return  # server-side rule, no frontend broadcast needed

        dead = []
        for ws in self._connections:
            try:
                await ws.send_json({"type": "rule", "rule": rule})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    def push_atmosphere_sync(self, atmosphere: Dict[str, Any]):
        """同步构建 atmosphere 快照，供规则引擎或 Agent 调用后由外部 await push."""
        return self.build_snapshot(atmosphere=atmosphere)

    async def push_atmosphere_by_rules(self):
        """规则引擎：根据当前时间查 color-map.json，构建并推送 atmosphere。无 LLM 调用。"""
        if not self._perception:
            return
        time_ctx = self._perception._get_time_context()
        tod = time_ctx.get("time_of_day", "afternoon")
        hour = time_ctx.get("hour", 12)

        # 夜间细分
        if 23 <= hour or hour < 5:
            tag = "night_calm"
        else:
            rules = self._color_map.get("_rules", {}).get("time_of_day", {})
            tag = rules.get(tod, {}).get("tag", "calm_focus")

        params = self._color_map.get(tag, {})
        atmosphere = {
            "tag": tag,
            "color": params.get("color", "#27AE60"),
            "speed": params.get("speed", 0.6),
            "density": params.get("density", 0.3),
            "amplitude": params.get("amplitude", 0.05),
            "brightness": params.get("brightness", 0.7),
        }
        await self.push_snapshot(atmosphere=atmosphere)
