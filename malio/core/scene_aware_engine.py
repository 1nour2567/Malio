import requests
from datetime import datetime
from typing import Optional, Dict, Any
from config.config import settings


class SceneAwareEngine:
    """Scene aware engine for detecting time, weather, and calendar events"""
    
    def __init__(self):
        """Initialize the scene aware engine"""
        pass
    
    def get_current_time_context(self) -> Dict[str, Any]:
        """Get current time context"""
        now = datetime.now()
        hour = now.hour
        
        # Determine time of day
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 18:
            time_of_day = "afternoon"
        elif 18 <= hour < 22:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        
        # Determine day of week
        day_of_week = now.strftime("%A")
        day_of_week_num = now.weekday()  # 0 = Monday, 6 = Sunday
        
        # Determine season (simplified for demonstration)
        month = now.month
        if 3 <= month <= 5:
            season = "spring"
        elif 6 <= month <= 8:
            season = "summer"
        elif 9 <= month <= 11:
            season = "autumn"
        else:
            season = "winter"
        
        return {
            "timestamp": now.isoformat(),
            "time_of_day": time_of_day,
            "hour": hour,
            "day_of_week": day_of_week,
            "day_of_week_num": day_of_week_num,
            "season": season,
            "month": month,
            "day": now.day
        }
    
    def get_weather_context(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get current weather context"""
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={settings.openweather_api_key}&units=metric"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return {
                "condition": data.get("weather", [{}])[0].get("main"),
                "description": data.get("weather", [{}])[0].get("description"),
                "temperature": data.get("main", {}).get("temp"),
                "humidity": data.get("main", {}).get("humidity"),
                "wind_speed": data.get("wind", {}).get("speed"),
                "icon": data.get("weather", [{}])[0].get("icon")
            }
        except Exception as e:
            print(f"Error getting weather: {e}")
            return None
    
    def get_calendar_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get calendar context (placeholder implementation)"""
        # This would integrate with Google Calendar API or similar
        # For demonstration, return mock data
        return {
            "events": [
                {
                    "summary": "Work meeting",
                    "start": "2024-01-01T10:00:00",
                    "end": "2024-01-01T11:00:00",
                    "location": "Office"
                },
                {
                    "summary": "Lunch break",
                    "start": "2024-01-01T12:00:00",
                    "end": "2024-01-01T13:00:00",
                    "location": "Cafeteria"
                }
            ],
            "current_event": None,
            "next_event": None
        }
    
    def get_full_context(self, user_id: str, lat: float = 24.9175, lon: float = 118.6465) -> Dict[str, Any]:
        """Get full scene context"""
        context = {
            "time": self.get_current_time_context(),
            "weather": self.get_weather_context(lat, lon),
            "calendar": self.get_calendar_context(user_id)
        }
        return context


# Example usage
if __name__ == "__main__":
    engine = SceneAwareEngine()
    context = engine.get_full_context("default")
    print("Full context:")
    print(context)
