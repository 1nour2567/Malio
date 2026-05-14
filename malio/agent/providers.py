"""Multi-LLM Provider Interface — model-agnostic reasoning backend."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import requests


class LLMProvider(ABC):
    """Abstract base for LLM providers. Add new models by subclassing."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any OpenAI-compatible API (Kimi, DeepSeek, Groq, etc.)."""

    def __init__(self, name: str, api_key: str, base_url: str, model: str,
                 temperature: float = 0.7, max_tokens: int = 4096):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(self, prompt: str, **kwargs) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers, json=data, timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return f"API Error: {result['error'].get('message', str(result['error']))}"
        choices = result.get("choices", [])
        if not choices:
            return ""
        content = choices[0].get("message", {}).get("content", "")
        if not content and choices[0].get("message", {}).get("reasoning_content"):
            content = choices[0]["message"]["reasoning_content"]
        return content

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key not in ("", "your_api_key_here"))


class ProviderRegistry:
    """Manages multiple LLM providers with runtime switching."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._active: Optional[str] = None

    def register(self, provider: LLMProvider):
        self._providers[provider.name] = provider
        if self._active is None:
            self._active = provider.name

    def set_active(self, name: str) -> bool:
        if name in self._providers and self._providers[name].is_available():
            self._active = name
            return True
        return False

    def get_active(self) -> Optional[LLMProvider]:
        if self._active and self._active in self._providers:
            p = self._providers[self._active]
            if p.is_available():
                return p
        # Fallback: find first available
        for p in self._providers.values():
            if p.is_available():
                self._active = p.name
                return p
        return None

    def list_providers(self) -> list:
        return [{"name": n, "available": p.is_available(), "active": n == self._active}
                for n, p in self._providers.items()]


# Pre-built factory for common providers
def create_providers_from_config(settings) -> ProviderRegistry:
    registry = ProviderRegistry()

    # Kimi (always register — primary Chinese LLM)
    if settings.kimi_api_key:
        registry.register(OpenAICompatibleProvider(
            name="kimi", api_key=settings.kimi_api_key,
            base_url=getattr(settings, 'kimi_api_base', 'https://api.moonshot.cn/v1'),
            model=getattr(settings, 'kimi_model', 'kimi-k2.5'),
            temperature=1.0  # kimi-k2.5 requires temperature=1
        ))

    # DeepSeek
    ds_key = getattr(settings, 'deepseek_api_key', '')
    if ds_key:
        registry.register(OpenAICompatibleProvider(
            name="deepseek", api_key=ds_key,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat", temperature=0.7
        ))

    return registry
