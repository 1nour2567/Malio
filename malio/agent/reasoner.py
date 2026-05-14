"""Stage 3: Model-agnostic reasoner — Plan-and-Solve structured reasoning."""
import json
import os
from typing import Dict, Any, Optional
from .providers import ProviderRegistry


class Reasoner:
    def __init__(self, provider_registry: ProviderRegistry):
        self.registry = provider_registry
        self._persona_prompt = self._load_file("prompts/dj-persona.md")
        self._color_map = self._load_json("user/color-map.json")

    @staticmethod
    def _load_file(rel_path: str) -> str:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, rel_path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    @staticmethod
    def _load_json(rel_path: str) -> Dict[str, Any]:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, rel_path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def reason(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        provider = self.registry.get_active()
        if not provider:
            return {
                "error": "No available LLM provider",
                "response": "I'm sorry, no AI provider is currently available.",
                "intent": "unknown",
            }

        prompt = self._build_prompt(user_input, context or {})
        raw = provider.generate(prompt)
        result = self._parse_response(raw)
        # Attach atmosphere if present
        if "atmosphere" not in result:
            result["atmosphere"] = None
        return result

    def _build_prompt(self, user_input: str, context: Dict[str, Any]) -> str:
        time_info = context.get("time", {})

        # Build color reference table from color-map
        color_rows = []
        for tag, params in self._color_map.items():
            if tag.startswith("_"): continue
            color_rows.append(
                f"| {tag} | {params.get('color','')} | {params.get('speed','')} | "
                f"{params.get('density','')} | {params.get('amplitude','')} | "
                f"{params.get('brightness','')} | {params.get('note','')} |"
            )

        lines = []
        # Persona
        if self._persona_prompt:
            lines.append(self._persona_prompt)
        else:
            lines.append("You are Malio, an intelligent music assistant with DJ personality.")

        lines.extend([
            "",
            "## Current context",
        ])
        if time_info:
            lines.append(f"- Time of day: {time_info.get('time_of_day', 'unknown')}, "
                         f"hour: {time_info.get('hour', '?')}, "
                         f"day: {time_info.get('day_of_week', '')}")

        # Recent core interactions (user touched Agent's body)
        core_events = context.get("core_events", [])
        if core_events:
            lines.append("")
            lines.append("## Recent user interactions with your core (body)")
            for evt in core_events[-8:]:
                label = {"song_skip":"切歌","time_warp":"子弹时间","search":"搜索","spin":"调音量","core_drag":"拖拽内核","nebula_capture":"捕获歌曲"}.get(evt.get("type",""), evt.get("type",""))
                lines.append(f"- [{evt.get('received_at', '?')}] {label}")

        lines.extend([
            "",
            f"User input: {user_input}",
            "",
            "## Response format",
            "Respond with ONLY a JSON object (no markdown fences):",
        ])
        format_obj = {
            "intent": "music_recommendation | mood_change | general_chat | command | unknown",
            "reasoning": "Step-by-step reasoning (Plan → Solve → Review)",
            "response": "Your natural-language reply to the user in Chinese",
            "actions": [],
            "atmosphere": {
                "tag": "one of: joyful / melancholy / calm_focus / energetic / night_calm / rainy_introspect",
                "color": "#hex", "speed": 0.0, "density": 0.0, "amplitude": 0.0, "brightness": 0.0
            }
        }
        lines.append(json.dumps(format_obj, ensure_ascii=False))

        if color_rows:
            lines.append("")
            lines.append("## Atmosphere color reference (pick one tag from below)")
            lines.append("| tag | color | speed | density | amplitude | brightness | note |")
            lines.append("|-----|-------|-------|---------|-----------|------------|------|")
            lines.extend(color_rows)

        lines.append("")
        lines.append("Respond with ONLY the JSON object, no other text.")

        return "\n".join(lines)

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        # Try to extract JSON from the response
        cleaned = raw.strip()
        # Remove markdown code fences if present
        if cleaned.startswith("```"):
            # Find the first { or [ after the fence
            start = cleaned.find("{")
            if start == -1:
                start = cleaned.find("[")
            if start != -1:
                cleaned = cleaned[start:]
            # Remove trailing fence
            end = cleaned.rfind("}")
            if end == -1:
                end = cleaned.rfind("]")
            if end != -1:
                cleaned = cleaned[: end + 1]

        try:
            result = json.loads(cleaned)
            if not isinstance(result, dict):
                raise ValueError("Response is not a dict")
            return result
        except (json.JSONDecodeError, ValueError):
            # Fallback: wrap the raw text
            return {
                "intent": "general_chat",
                "reasoning": "Failed to parse structured response, using raw output.",
                "response": raw,
                "actions": [],
            }
