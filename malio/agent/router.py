"""Stage 2: Three-mode routing — Plan (no LLM) / Agent (LLM+Tools) / YOLO (auto-approve)."""
from typing import Dict, Any


class Router:
    COMMANDS = {"play", "pause", "stop", "next", "previous", "volume"}

    PLAN_PATTERNS = {
        "local_lookup": ["库里", "有哪些歌", "曲库", "本地", "歌曲列表", "我有什么"],
        "history":      ["播放记录", "听过什么", "历史", "history", "听了哪些"],
        "weather":      ["天气", "温度", "下雨", "weather", "几度"],
        "status":       ["当前", "正在", "now playing", "在放什么", "现在放什么"],
    }

    def classify(self, user_input: str) -> dict:
        cleaned = user_input.strip().lower()

        for cmd in self.COMMANDS:
            if cleaned == cmd or cleaned.startswith(cmd + " "):
                return {"mode": "yolo", "command": cmd}

        for source, keywords in self.PLAN_PATTERNS.items():
            if any(kw in cleaned for kw in keywords):
                return {"mode": "plan", "plan_source": source}

        # Persistence / rule commands — handle without songs
        persist_kw = ["以后", "一直", "永远", "每次", "总是"]

        # Immediate color/style commands → system executes directly
        COLOR_MAP = {
            "天空蓝": "#87CEEB", "蓝色": "#4169E1", "红色": "#E74C3C",
            "绿色": "#27AE60", "紫色": "#8E44AD", "橙色": "#E67E22",
            "黄色": "#F1C40F", "粉色": "#FF69B4", "白色": "#ECF0F1",
            "暖色": "#E6C200", "冷色": "#5B7FA5",
        }
        for name, hexc in COLOR_MAP.items():
            if name in cleaned:
                return {"mode": "direct_color", "color": hexc, "color_name": name}

        # Full reset commands
        reset_kw = ["全部清空", "全部清除", "全部清零", "重置所有", "全部重置",
                    "删除所有", "清空所有", "清除所有"]
        if any(kw in cleaned for kw in reset_kw):
            return {"mode": "yolo", "rule_command": True, "reset_all": True}
        if any(kw in cleaned for kw in persist_kw):
            return {"mode": "yolo", "rule_command": True}

        yolo_kw = ["全部", "所有", "每个", "批量", "一口气", "全加", "都加"]
        if any(kw in cleaned for kw in yolo_kw):
            return {"mode": "yolo"}

        return {"mode": "agent"}

    def route(self, user_input: str) -> Dict[str, Any]:
        cleaned = user_input.strip().lower()

        for cmd in self.COMMANDS:
            if cleaned == cmd or cleaned.startswith(cmd + " ") or cleaned.startswith(cmd + " to "):
                parts = cleaned.split(maxsplit=1)
                params = {}
                if len(parts) > 1:
                    params["value"] = parts[1]
                return {
                    "routed_to": "direct",
                    "command": cmd,
                    "params": params,
                    "original_input": user_input,
                }

        return {
            "routed_to": "reasoning",
            "original_input": user_input,
        }
