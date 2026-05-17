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

        # Chat history
        history = context.get("chat_history", [])
        if history:
            lines.append("")
            lines.append("## 对话历史（最近几轮）")
            for h in history[-6:]:
                role = "用户" if h.get("role") == "user" else "Malio"
                lines.append(f"- {role}: {h.get('content', '')[:200]}")

        # Auto-executed tool results (system pre-fetched, use directly)
        auto_tools = context.get("auto_tools", {})
        if auto_tools.get("local_songs"):
            lines.append("")
            lines.append("## 本地曲库（系统已查询，直接使用）")
            for s in auto_tools["local_songs"][:10]:
                artist_str = ', '.join(s.get('artist', [])[:2]) if isinstance(s.get('artist'), list) else str(s.get('artist', ''))
                lines.append(f"- [{s.get('id','?')}] {s['title']} — {artist_str}")
        if auto_tools.get("recommendations"):
            lines.append("")
            lines.append("## 系统推荐（可直接引用）")
            for r in auto_tools["recommendations"][:5]:
                lines.append(f"- [{r.get('id','?')}] {r.get('title','?')} — {', '.join(r.get('artist',[])) if isinstance(r.get('artist'),list) else r.get('artist','')}")
        if auto_tools.get("history_summary"):
            lines.append(f"\n## 播放历史\n{auto_tools['history_summary']}")

        # If song data is available, remind LLM to use selected_song_id
        has_songs = auto_tools.get("local_songs") or auto_tools.get("recommendations")
        if has_songs:
            lines.append("")
            lines.append("## IMPORTANT: You have real song data above with IDs in [brackets].")
            lines.append("Set selected_song_id to the ID of the song you recommend as the primary choice.")

        # Recent core interactions + L2 memory
        core_events = context.get("core_events", [])
        if core_events:
            lines.append("")
            lines.append("## Recent user interactions with your core (body)")
            for evt in core_events[-8:]:
                label = {"song_skip":"切歌","time_warp":"子弹时间","search":"搜索","spin":"调音量","core_drag":"拖拽内核","nebula_capture":"捕获歌曲"}.get(evt.get("type",""), evt.get("type",""))
                lines.append(f"- [{evt.get('received_at', '?')}] {label}")

        l2_summary = context.get("l2_summary", "")
        if l2_summary:
            lines.append("")
            lines.append(l2_summary)

        persona_style = context.get("persona_style", "")
        if persona_style:
            lines.append("")
            lines.append(persona_style)

        drift_log_text = context.get("persona_drift_log", "")
        if drift_log_text:
            lines.append("")
            lines.append(drift_log_text)

        active_rules = context.get("agent_active_rules", [])
        if active_rules:
            lines.append("")
            lines.append("## 你已创建的活跃规则")
            for rule in active_rules:
                lines.append(f"- [{rule.get('id','?')}] {rule.get('note','')}: "
                             f"when {rule.get('when',{}).get('type','?')}={rule.get('when',{}).get('val','?')} "
                             f"→ {rule.get('then',[{}])[0].get('target','?')}")
            lines.append("(避免创建重复规则，最多3条)")

        l3_profile = context.get("l3_profile", "")
        if l3_profile:
            lines.append("")
            lines.append(l3_profile)

        lines.extend([
            "",
            f"User input: {user_input}",
            "",
            "## Response format",
            "CRITICAL: 当用户要求持久变化（如'暗一点''慢一点''不要太亮'），必须在rules字段输出规则。不要在response里口头答应而不填rules。",
            "Respond with ONLY a JSON object (no markdown fences):",
        ])
        format_obj = {
            "intent": "music_recommendation | mood_change | general_chat | command | unknown",
            "reasoning": "Step-by-step reasoning (Plan → Solve → Review)",
            "response": "Your natural-language reply to the user in Chinese. CRITICAL: never mention specific song titles in this field — use descriptive terms like '一首温暖的慢歌' instead. Song names will be inserted by the system.",
            "selected_song_id": "song_id from the tool results that you picked as the primary recommendation, or empty string if not recommending",
            "actions": [],
            "core_actions": [{
                "#note": "内核是你的身体。move_core可移动内核在屏幕上的物理位置(x,y)。light_burst是光爆。set_mode切换形态(dot/vortex)。用户说'往左一点'→move_core x-50。用户说'变小'→set_size。你确实可以物理移动内核。",
                "action": "set_mode | light_burst | move_core | set_size | time_warp | breath | set_speed | set_color | set_density",
                "params": {"mode": "dot|vortex|error", "color": "#hex", "x": 0, "y": 0, "radius": 0, "rate": 0.016, "depth": 0.7, "speed": 3.8, "amplitude": 0.4}
            }],
            "atmosphere": {
                "tag": "one of: joyful / melancholy / calm_focus / energetic / night_calm / rainy_introspect",
                "color": "#hex", "speed": 0.0, "density": 0.0, "amplitude": 0.0, "brightness": 0.0
            },
            "rules": [{
                "#IMPORTANT": "当用户要求持久变化（如'以后晚上暗一点'），必须在此字段生成规则。不是口头答应——要输出JSON规则。最多3条，系统预设规则优先。",
                "id": "agent_<timestamp>",
                "when": {"type": "time_gt | time_lt | idle_gt | event", "val": "23:00 or 300 or song_change"},
                "then": [{"target": "speed | brightness | amplitude | density | color", "op": "set | mult | add | lerp_to", "val": 0.7}],
                "endWhen": {"type": "time_gt | time_lt", "val": "05:00"},
                "note": "简短说明为什么创建这条规则"
            }]
        }
        lines.append(json.dumps(format_obj, ensure_ascii=False))

        if color_rows:
            lines.append("")
            lines.append("## Atmosphere color reference (pick one tag from below)")
            lines.append("| tag | color | speed | density | amplitude | brightness | note |")
            lines.append("|-----|-------|-------|---------|-----------|------------|------|")
            lines.extend(color_rows)

        lines.append("")
        lines.append("## DSL Rule reference (for the optional 'rules' field)")
        lines.append("- Conditions: time_gt(HH:MM), time_lt(HH:MM), idle_gt(seconds), event(song_change|beat)")
        lines.append("- Actions: set, mult, add, lerp_to")
        lines.append("- Targets: speed, brightness, amplitude, density, color")
        lines.append("- System rules (higher priority) always override agent rules.")
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
            result = {
                "intent": "general_chat",
                "reasoning": "Failed to parse structured response, using raw output.",
                "response": raw,
                "actions": [],
            }
            rules = self._extract_rules_from_text(raw)
            if rules:
                result["rules"] = rules
                result["intent"] = "command"
            return result

    @staticmethod
    def _extract_rules_from_text(text: str) -> list:
        """Try to extract DSL rules from natural language agent responses."""
        import re
        rules = []

        persistence_kw = ["记下了", "记住了", "已记录", "已保存", "已经帮你", "设置好了", "调整好了"]
        if not any(kw in text for kw in persistence_kw):
            return rules

        # ── Extract parameter changes first ──
        then = []
        is_dim = ("暗" in text or "低" in text or "降" in text or "亮度" in text
                   or "不要" in text and ("亮" in text or "快" in text))
        is_bright = ("亮" in text and "不" not in text and "暗" not in text and "低" not in text
                      and "不要" not in text)
        is_slow = ("慢" in text or "速度" in text
                    or "不要" in text and "快" in text)
        is_fast = ("快" in text and "不" not in text and "不要" not in text)

        if is_dim and not is_bright:
            then.append({"target": "brightness", "op": "mult", "val": 0.5})
        if is_bright:
            then.append({"target": "brightness", "op": "mult", "val": 1.3})
        if is_slow and not is_fast:
            then.append({"target": "speed", "op": "mult", "val": 0.7})
        if is_fast:
            then.append({"target": "speed", "op": "mult", "val": 1.3})

        if not then:
            return rules

        # ── Extract time range ──
        time_patterns = [
            (r"(\d{1,2}):00\s*(?:之后|以后|开始|起)", "time_gt", "start"),
            (r"(?:到|直到|恢复)\s*(\d{1,2}):00", "time_lt", "end"),
            (r"(\d{1,2})点\s*(?:之后|以后|开始)", "time_gt", "start"),
            (r"(?:到|直到|恢复)\s*(\d{1,2})点", "time_lt", "end"),
        ]
        when = {}
        end_when = {}
        for pattern, op, pos in time_patterns:
            m = re.search(pattern, text)
            if m:
                hour = int(m.group(1))
                val = f"{hour:02d}:00"
                if pos == "start":
                    when = {"type": op, "val": val}
                else:
                    end_when = {"type": op, "val": val}

        if not when:
            if "晚上" in text or "晚一点" in text or "暗" in text:
                when = {"type": "time_gt", "val": "22:00"}
                end_when = {"type": "time_lt", "val": "06:00"}
            else:
                when = {"type": "always", "val": "true"}

        import time
        rules.append({
            "id": f"agent_{int(time.time())}",
            "when": when,
            "then": then,
            "endWhen": end_when,
            "note": text[:80].replace("\n", " "),
        })
        return rules
