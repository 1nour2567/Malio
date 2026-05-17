from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    # API Keys
    kimi_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    kimi_model: str = "kimi-k2.5"
    kimi_api_base: str = "https://api.moonshot.cn/v1"
    anthropic_api_key: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    openweather_api_key: str = ""
    elevenlabs_api_key: str = ""
    
    # NetEase Cloud Music API
    netease_api_url: str = "http://localhost:3000"
    ncm_cookie: str = ""

    # Database
    database_url: str = "sqlite:////mnt/c/Users/m1916/Desktop/aimusic/AI_music-master/malio/malio.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8007
    
    # Environment
    environment: str = "development"
    
    # CORS settings
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8000"
    
    # Music data
    music_data_path: str = "./data"
    
    # Model
    kimi_model: str = "kimi-k2.5"
    kimi_api_base: str = "https://api.moonshot.cn/v1/"
    anthropic_model: str = "claude-sonnet-4-6"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Create settings instance
settings = Settings()
