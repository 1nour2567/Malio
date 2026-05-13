"""Stage 2: Route explicit commands to direct execution, everything else to reasoning."""
from typing import Dict, Any


class Router:
    COMMANDS = {"play", "pause", "stop", "next", "previous", "volume"}

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
