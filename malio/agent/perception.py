"""Stage 1: Context assembly — user input + environment + preferences."""
from typing import Dict, Any
from datetime import datetime


class Perception:
    def build(self, user_input: str, user_id: str = "default") -> Dict[str, Any]:
        return {
            "user_input": user_input,
            "user_id": user_id,
            "time": self._get_time_context(),
            "context": {},
        }

    @staticmethod
    def _get_time_context() -> Dict[str, Any]:
        now = datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            tod = "morning"
        elif 12 <= hour < 18:
            tod = "afternoon"
        elif 18 <= hour < 22:
            tod = "evening"
        else:
            tod = "night"
        return {
            "time_of_day": tod,
            "day_of_week": now.strftime("%A"),
            "hour": hour,
        }
