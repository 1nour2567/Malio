import requests
from typing import Optional, Dict, Any
from config.config import settings
import logging

logger = logging.getLogger(__name__)


class ElevenLabsIntegration:
    """Integration with ElevenLabs TTS API"""
    
    def __init__(self):
        """Initialize ElevenLabs integration"""
        self.api_key = settings.elevenlabs_api_key
        self.api_base = "https://api.elevenlabs.io/v1"
        self.default_voice_id = "21m00Tcm4TlvDq8ikWAM"  # 默认声音：Rachel
        self.default_model = "eleven_multilingual_v2"
        logger.info(f"ElevenLabs integration initialized - API Key configured: {'Yes' if self.api_key else 'No'}")

    def text_to_speech(self, text: str, voice_id: Optional[str] = None, model_id: Optional[str] = None) -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs API
        
        :param text: The text to convert to speech
        :param voice_id: Optional voice ID (default: Rachel)
        :param model_id: Optional model ID (default: eleven_multilingual_v2)
        :return: Audio bytes (MP3 format) or None if failed
        """
        if not self.api_key:
            logger.error("ElevenLabs API key not configured")
            return None
        
        if not text.strip():
            logger.warning("Empty text provided for TTS")
            return None
        
        try:
            endpoint = f"{self.api_base}/text-to-speech/{voice_id or self.default_voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            body = {
                "text": text,
                "model_id": model_id or self.default_model,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }
            
            response = requests.post(endpoint, headers=headers, json=body, timeout=30)
            
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"ElevenLabs API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling ElevenLabs API: {e}")
            return None

    def list_voices(self) -> Optional[Dict[str, Any]]:
        """
        Get list of available voices
        
        :return: Dictionary containing voice information
        """
        if not self.api_key:
            logger.error("ElevenLabs API key not configured")
            return None
        
        try:
            endpoint = f"{self.api_base}/voices"
            headers = {"xi-api-key": self.api_key}
            
            response = requests.get(endpoint, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"ElevenLabs API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error listing voices: {e}")
            return None

    def get_voice_info(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific voice
        
        :param voice_id: The voice ID to get info for
        :return: Voice information dictionary
        """
        if not self.api_key:
            logger.error("ElevenLabs API key not configured")
            return None
        
        try:
            endpoint = f"{self.api_base}/voices/{voice_id}"
            headers = {"xi-api-key": self.api_key}
            
            response = requests.get(endpoint, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"ElevenLabs API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting voice info: {e}")
            return None
