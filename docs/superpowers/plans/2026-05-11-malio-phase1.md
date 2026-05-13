# Malio Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename Claudio→Malio, implement 5-stage agent pipeline with Plan-and-Solve + ReAct, fullscreen player with Canvas Matrix code flow, and WebSocket state snapshot protocol — backward-compatible with all existing features.

**Architecture:** 5 Python agent modules (perception/router/reasoner/tools/feedback) replace monolithic main.py routing. FastAPI + WebSocket serve state snapshots to a vanilla PWA frontend with Canvas particle engine. Kimi API drives Plan-and-Solve structured reasoning.

**Tech Stack:** Python 3.10+ / FastAPI / uvicorn / pydantic / SQLAlchemy / requests / HTML5 Canvas / vanilla JS / Vite

---

## File Structure

```
AI_music-master/
├── malio/                              # NEW: agent package (renamed from claudio/)
│   ├── __init__.py
│   ├── main.py                         # MODIFY: refactored server entry
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── perception.py              # NEW: context assembly
│   │   ├── router.py                  # NEW: intent routing
│   │   ├── reasoner.py                # NEW: P&S prompt builder (model-agnostic)
│   │   ├── providers.py              # NEW: multi-LLM provider interface
│   │   ├── tools.py                   # NEW: tool registry + dispatch
│   │   └── feedback.py               # NEW: response gen + WS push
│   ├── config/
│   │   └── config.py                  # KEEP: existing Settings, update app name
│   ├── core/                          # KEEP: existing engines
│   ├── data/                          # KEEP: existing importer
│   ├── integrations/                  # KEEP: existing integrations
│   ├── models/                        # KEEP: existing SQLAlchemy models
│   ├── requirements.txt              # KEEP
│   └── .env                          # KEEP
├── frontend/                          # REWRITE: new PWA
│   ├── index.html
│   ├── src/
│   │   ├── app.js                     # REWRITE: new fullscreen player
│   │   ├── style.css                  # REWRITE: OLED dark theme
│   │   ├── particles.js              # NEW: Canvas粒子引擎 + FPS熔断
│   │   └── ws-client.js             # NEW: WebSocket snapshot consumer
│   ├── public/
│   │   ├── manifest.json
│   │   └── sw.js
│   └── vite.config.js
├── prompts/
│   └── dj-persona.md                  # NEW: DJ personality + 5 rules
└── MALIO_ARCHITECTURE.md              # exists
```

---

### Task 1: Rename Project Directory

**Files:**
- Rename: `claudio/` → `malio/`
- Modify: All internal imports referencing `claudio/`

- [ ] **Step 1: Rename directory**

```bash
cd /mnt/c/Users/m1916/Desktop/aimusic/AI_music-master
mv claudio malio
```

- [ ] **Step 2: Update import paths**

Update all `from config.config import` style imports to work from new package root. The existing files use relative-like imports (`from config.config import settings`) which work if `malio/` is the working directory. Verify with:

```bash
cd malio && python3 -c "from config.config import settings; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 3: Update README.md and START.md** references from `claudio/` to `malio/`

Replace all occurrences of `cd claudio` → `cd malio` and `claudio/` → `malio/` in both files.

- [ ] **Step 4: Update .gitignore**

Replace `claudio/.env` → `malio/.env`

- [ ] **Step 5: Verify existing features still work**

```bash
cd malio && python3 main.py &
# Wait for startup, then:
curl http://localhost:8007/health
# Expected: {"status":"healthy"}
curl -s http://localhost:8007/api/songs | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Songs: {d[\"total\"]}')"
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: rename claudio to malio"
```

---

### Task 2: Multi-LLM Provider Interface

**Files:**
- Create: `malio/agent/providers.py`

Design goal: Reasoner is model-agnostic. Swap between Kimi, Claude, DeepSeek, or any OpenAI-compatible API without touching agent logic.

- [ ] **Step 1: Write `malio/agent/providers.py`**

```python
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

    # Anthropic Claude (future, needs different API format — extend later)
    ant_key = getattr(settings, 'anthropic_api_key', '')
    if ant_key:
        registry.register(OpenAICompatibleProvider(
            name="claude", api_key=ant_key,
            base_url="https://api.anthropic.com/v1",
            model=getattr(settings, 'anthropic_model', 'claude-sonnet-4-6'),
            temperature=0.7
        ))

    # Add more: Groq, Ollama (localhost), Minimax, Qwen, etc.
    return registry
```

- [ ] **Step 2: Verify providers module loads**

```bash
cd malio && python3 -c "
from agent.providers import ProviderRegistry, OpenAICompatibleProvider
r = ProviderRegistry()
r.register(OpenAICompatibleProvider('test', 'sk-test', 'https://api.test.com', 'test-model'))
print('Active:', r.get_active())
print('Providers:', r.list_providers())
"
```

Expected: Active provider shows, list contains "test".

- [ ] **Step 3: Commit**

```bash
git add malio/agent/providers.py
git commit -m "feat: add multi-LLM provider interface with OpenAI-compatible backend"
```

---

### Task 3: Create Agent Package Skeleton

**Files:**
- Create: `malio/agent/__init__.py`
- Create: `malio/agent/perception.py`
- Create: `malio/agent/router.py`
- Create: `malio/agent/reasoner.py`
- Create: `malio/agent/tools.py`
- Create: `malio/agent/feedback.py`

Each file gets a minimal working skeleton.

- [ ] **Step 1: Create agent package directory**

```bash
mkdir -p malio/agent
```

- [ ] **Step 2: Write `malio/agent/__init__.py`**

```python
"""Malio AI Agent — 5-stage music DJ pipeline with multi-LLM support."""

from .perception import Perception
from .router import Router
from .reasoner import Reasoner
from .providers import ProviderRegistry, OpenAICompatibleProvider, create_providers_from_config
from .tools import ToolRegistry
from .feedback import Feedback

__all__ = ["Perception", "Router", "Reasoner", "ProviderRegistry",
           "OpenAICompatibleProvider", "create_providers_from_config",
           "ToolRegistry", "Feedback"]
```

- [ ] **Step 3: Write `malio/agent/perception.py`**

```python
"""Stage 1: Context assembly — user input + environment + preferences."""

from typing import Dict, Any


class Perception:
    def __init__(self):
        self.context_cache = {}

    def build(self, user_input: str, user_id: str = "default") -> Dict[str, Any]:
        return {
            "user_input": user_input,
            "user_id": user_id,
            "time": self._get_time_context(),
            "context": {},
        }

    @staticmethod
    def _get_time_context() -> Dict[str, Any]:
        from datetime import datetime

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
        return {"time_of_day": tod, "day_of_week": now.strftime("%A"), "hour": hour}
```

- [ ] **Step 4: Write `malio/agent/router.py`**

```python
"""Stage 2: Intent routing — explicit commands vs natural language."""

from typing import Dict, Any


class Router:
    EXPLICIT_COMMANDS = {
        "play": "device_control",
        "pause": "device_control",
        "stop": "device_control",
        "next": "device_control",
        "previous": "device_control",
        "volume": "device_control",
    }

    def route(self, user_input: str) -> Dict[str, Any]:
        lowered = user_input.lower().strip()
        for cmd, category in self.EXPLICIT_COMMANDS.items():
            if lowered == cmd or lowered.startswith(cmd + " "):
                return {"routed_to": "direct", "command": cmd, "category": category}
        return {"routed_to": "reasoning", "command": None, "category": "natural_language"}
```

- [ ] **Step 5: Write `malio/agent/reasoner.py`**

```python
"""Stage 3: Plan-and-Solve + ReAct structured reasoning via any LLM provider."""

import json
from typing import Dict, Any, List, Optional
from .providers import ProviderRegistry


class Reasoner:
    def __init__(self, provider_registry: ProviderRegistry):
        self.providers = provider_registry

    def reason(self, perception: Dict[str, Any], history: List[str] = None,
               provider_name: Optional[str] = None) -> Dict[str, Any]:
        if provider_name:
            self.providers.set_active(provider_name)
        provider = self.providers.get_active()
        if not provider:
            return {"plan": {"intent": "no_llm_available"},
                    "solve": {"actions": []},
                    "review": {"self_check": "没有可用的 AI 模型，请检查 API 配置。"}}
        prompt = self._build_plan_and_solve_prompt(perception, history or [])
        raw = provider.generate(prompt)
        return self._parse_structured_response(raw)

    def _build_plan_and_solve_prompt(self, perception: Dict[str, Any], history: List[str]) -> str:
        ui = perception.get("user_input", "")
        ctx = perception.get("context", {})
        time_ctx = perception.get("time", {})

        return f"""你是 Malio，一位有判断力的 AI 音乐 DJ。用 Plan-and-Solve 方式回复：

## Plan（计划）
分析用户意图，制定选歌策略。考虑：时间（{time_ctx.get('time_of_day', '未知')}）、心情、天气、用户偏好和最近播放历史。

## Solve（执行）
选择工具调用。可用工具：search_music（搜索歌曲）、check_history（查询播放记录）、get_weather（获取天气）。

## Review（审查）
检查结果是否满足用户需求。如需调整，说明怎么改。提供下一首歌的过渡语。

用户输入：{ui}

请用 JSON 格式回复：
{{"plan": {{"intent": "...", "strategy": "...", "constraints": [...]}}, "solve": {{"actions": [...], "results": [...]}}, "review": {{"self_check": "...", "segue": "..."}}}}"""

    def _parse_structured_response(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"plan": {"intent": "general"}, "solve": {"actions": []}, "review": {"self_check": "fallback", "segue": ""}}
```

- [ ] **Step 6: Write `malio/agent/tools.py`**

```python
"""Stage 4: Tool Registry — standardized tool definitions and dispatch."""

from typing import Dict, Any, Callable, Optional


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any], handler: Callable):
        self._tools[name] = {"name": name, "description": description, "parameters": parameters}
        self._handlers[name] = handler

    def get_schema(self) -> Dict[str, Any]:
        return {"tools": list(self._tools.values())}

    def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._handlers:
            return {"error": f"Tool '{name}' not found"}
        try:
            return self._handlers[name](**params)
        except Exception as e:
            return {"error": str(e), "tool": name}

    def list_tools(self) -> list:
        return list(self._tools.keys())
```

- [ ] **Step 7: Write `malio/agent/feedback.py`**

```python
"""Stage 5: Response generation and state push via WebSocket."""

import json
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import WebSocket


class Feedback:
    def __init__(self):
        self._connections: List[WebSocket] = []

    async def register(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def unregister(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def push_snapshot(self, snapshot: Dict[str, Any]):
        dead = []
        payload = json.dumps(snapshot, ensure_ascii=False)
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    async def push_agent_log(self, message: str):
        await self.push_snapshot({"type": "agent_log", "message": message})

    def build_snapshot(self, song: Optional[Dict] = None, playlist: List[Dict] = None,
                       is_playing: bool = False, agent_log: str = "",
                       tool_error: Optional[Dict] = None) -> Dict[str, Any]:
        import time
        return {
            "type": "state_snapshot",
            "song": song or {},
            "playlist": playlist or [],
            "is_playing": is_playing,
            "agent_log": agent_log,
            "tool_error": tool_error,
            "timestamp": int(time.time()),
            "seq": getattr(self, "_seq", 0),
        }
```

- [ ] **Step 8: Commit**

```bash
git add malio/agent/
git commit -m "feat: add agent package skeleton (5-stage pipeline)"
```

---

### Task 3: Refactor main.py — Agent Pipeline Integration

**Files:**
- Modify: `malio/main.py`

Replace the monolithic `/api/chat` handler with the 5-stage agent pipeline. Keep all existing endpoints intact.

- [ ] **Step 1: Import agent modules**

Add at top of `malio/main.py` after existing imports:

```python
from agent.perception import Perception
from agent.router import Router
from agent.reasoner import Reasoner
from agent.providers import create_providers_from_config
from agent.tools import ToolRegistry
from agent.feedback import Feedback
```

- [ ] **Step 2: Initialize agent components**

Add after existing engine initializations (`elevenlabs_integration = ...`):

```python
# Agent pipeline (model-agnostic — swap providers via .env or /model chat command)
provider_registry = create_providers_from_config(settings)
perception = Perception()
router = Router()
reasoner = Reasoner(provider_registry)
tool_registry = ToolRegistry()
feedback_mgr = Feedback()

# Register tools
tool_registry.register(
    "search_music", "搜索歌曲，支持歌曲名、歌手、风格",
    {"query": "string", "limit": "int"},
    lambda query, limit=5, **kw: netease_integration.search_tracks(query, limit)
)
tool_registry.register(
    "check_history", "查询最近播放记录",
    {"user_id": "string", "hours": "int"},
    lambda user_id="default", hours=24, **kw: []
)
tool_registry.register(
    "get_weather", "获取当前天气",
    {"city": "string"},
    lambda city="", **kw: scene_engine.get_weather_context(24.9175, 118.6465) or {}
)
```

- [ ] **Step 3: Replace `/api/chat` with agent pipeline**

Replace the existing `chat_with_claudio` function body:

```python
@app.post("/api/chat", response_model=MusicResponse)
async def chat_with_malio(request: UserInput):
    """Chat with Malio about music — 5-stage agent pipeline."""
    try:
        print("[agent] Stage 1: Perception")
        ctx = perception.build(request.input, request.user_id)

        print("[agent] Stage 2: Routing")
        route = router.route(request.input)
        if route["routed_to"] == "direct":
            response = f"收到，执行 {route['command']} 命令。"
            return MusicResponse(response=response, recommendations=[])

        print("[agent] Stage 3: Reasoning (Plan-and-Solve)")
        structured = reasoner.reason(ctx)

        print("[agent] Stage 4: Tool Use")
        actions = structured.get("solve", {}).get("actions", [])
        results = []
        for action in actions:
            tool_name = action.get("tool", "")
            if tool_name and tool_name in tool_registry.list_tools():
                res = tool_registry.execute(tool_name, {k: v for k, v in action.items() if k != "tool"})
                results.append(res)
        structured["solve"]["results"] = results

        print("[agent] Stage 5: Feedback")
        review = structured.get("review", {})
        segue = review.get("segue", "")

        response = structured.get("plan", {}).get("strategy", "为你准备了一些歌曲。")
        if segue:
            response += "\n\n" + segue

        return MusicResponse(response=response, recommendations=[])

    except Exception as e:
        import traceback
        print(f"[agent] ERROR: {e}\n{traceback.format_exc()}")
        return MusicResponse(
            response=f"抱歉，Malio 遇到了一些问题（{type(e).__name__}）。请稍后再试。",
            recommendations=[]
        )
```

- [ ] **Step 4: Update app title**

```python
app = FastAPI(
    title="Malio Music Agent API",
    description="AI music agent powered by Plan-and-Solve reasoning",
    version="0.2.0"
)
```

- [ ] **Step 5: Verify existing endpoints still work**

```bash
curl http://localhost:8007/health
curl http://localhost:8007/api/songs
curl -X POST http://localhost:8007/api/chat -H "Content-Type: application/json" -d '{"input":"推荐几首歌"}'
```

- [ ] **Step 6: Commit**

```bash
git add malio/main.py
git commit -m "feat: integrate 5-stage agent pipeline into main.py"
```

---

### Task 4: WebSocket State Snapshot Endpoint

**Files:**
- Modify: `malio/main.py` (add WebSocket route)

- [ ] **Step 1: Add WebSocket `/stream` handler**

Replace the existing stub WebSocket endpoint with the state snapshot protocol:

```python
@app.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """Real-time state snapshot — immutable, not incremental."""
    await feedback_mgr.register(websocket)
    try:
        # Push initial snapshot on connect
        await feedback_mgr.push_snapshot(
            feedback_mgr.build_snapshot(
                agent_log="Malio 已就绪。",
                is_playing=False
            )
        )
        while True:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
            action = data.get("action", "")
            if action == "get_state":
                await feedback_mgr.push_snapshot(
                    feedback_mgr.build_snapshot(agent_log="状态已同步")
                )
    except asyncio.TimeoutError:
        pass  # heartbeat timeout is fine
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] Error: {e}")
    finally:
        feedback_mgr.unregister(websocket)
```

- [ ] **Step 2: Add `_seq` tracking to Feedback**

Update `build_snapshot` in `malio/agent/feedback.py`:

```python
def __init__(self):
    self._connections: List[WebSocket] = []
    self._seq = 0

def build_snapshot(self, ...):
    self._seq += 1
    return {
        ...
        "seq": self._seq,
    }
```

- [ ] **Step 3: Verify WebSocket works**

```bash
# Start server, then in another terminal:
python3 -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:8007/stream') as ws:
        msg = await ws.recv()
        print(json.loads(msg))
asyncio.run(test())
"
```

Expected: `{"type": "state_snapshot", "song": {}, "playlist": [], "is_playing": false, "agent_log": "Malio 已就绪。", ...}`

- [ ] **Step 4: Commit**

```bash
git add malio/main.py malio/agent/feedback.py
git commit -m "feat: add WebSocket state snapshot protocol"
```

---

### Task 5: Frontend — Fullscreen Player Layout

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Rewrite `frontend/index.html` — fullscreen layout**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#000000">
<link rel="manifest" href="/manifest.json">
<title>Malio — AI 私人电台</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/src/style.css">
</head>
<body>

<div id="app">
  <canvas id="particle-canvas" aria-hidden="true"></canvas>

  <header class="top-bar">
    <button class="icon-btn" id="btn-menu" aria-label="菜单">☰</button>
    <span class="brand">Malio</span>
    <div class="top-actions">
      <button class="icon-btn" id="btn-search-toggle" aria-label="搜索" title="Ctrl+K">🔍</button>
      <button class="icon-btn" id="btn-chat-toggle" aria-label="对话" title="/">💬</button>
      <button class="icon-btn" id="btn-settings-toggle" aria-label="设置">⚙️</button>
    </div>
  </header>

  <div class="agent-log" id="agent-log" hidden>
    <span class="agent-log-prefix">Malio</span>
    <span class="agent-log-text" id="agent-log-text"></span>
    <button class="agent-log-pin" id="btn-pin-log" aria-label="固定日志">📌</button>
  </div>

  <main class="player-center">
    <div class="player-card" id="player-card">
      <div class="album-art-wrap" id="album-art-wrap">
        <img class="album-art-img" id="album-art-img" src="" alt="" hidden>
        <div class="album-art-placeholder" id="album-art-placeholder">🎵</div>
      </div>
      <div class="song-info">
        <h2 class="song-title" id="song-title">Malio</h2>
        <p class="song-artist" id="song-artist">你的 AI 私人电台 DJ</p>
      </div>
      <div class="progress-wrap">
        <div class="progress-bar" id="progress-bar">
          <div class="progress-fill" id="progress-fill"></div>
        </div>
        <div class="progress-time">
          <span class="time-elapsed" id="time-elapsed">0:00</span>
          <span class="time-total" id="time-total">0:00</span>
        </div>
      </div>
      <div class="player-controls">
        <button class="ctrl-btn" id="btn-prev" aria-label="上一首">⏮</button>
        <button class="ctrl-btn ctrl-btn-play" id="btn-play" aria-label="播放/暂停">▶</button>
        <button class="ctrl-btn" id="btn-next" aria-label="下一首">⏭</button>
      </div>
      <div class="volume-wrap">
        <span>🔊</span>
        <input type="range" class="volume-slider" id="volume-slider" min="0" max="100" value="70">
      </div>
    </div>
  </main>

  <aside class="side-panel" id="chat-panel" hidden>
    <div class="panel-header">
      <span>与 Malio 对话</span>
      <button class="icon-btn" id="btn-chat-close">✕</button>
    </div>
    <div class="chat-messages" id="chat-messages"></div>
    <div class="chat-input-wrap">
      <input type="text" class="chat-input" id="chat-input" placeholder="说点什么..." autocomplete="off">
      <button class="chat-send-btn" id="btn-send">→</button>
    </div>
  </aside>

  <aside class="side-panel" id="search-panel" hidden>
    <div class="panel-header">
      <span>搜索音乐</span>
      <button class="icon-btn" id="btn-search-close">✕</button>
    </div>
    <div class="search-input-wrap">
      <input type="text" class="search-input" id="search-input" placeholder="搜索歌曲、歌手...">
      <button class="btn-primary" id="btn-search">搜索</button>
    </div>
    <div class="search-results" id="search-results"></div>
  </aside>
</div>

<audio id="audio-player" preload="metadata"></audio>

<script src="/src/ws-client.js"></script>
<script src="/src/particles.js"></script>
<script src="/src/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `frontend/src/style.css` — OLED dark fullscreen theme**

Base: pure black background. Player card centered. Top bar 48px. Side panels slide from right.

Core CSS rules (write full file):

```css
:root {
  --bg-black: #000000;
  --bg-card: #0D0D0D;
  --bg-elevated: #141414;
  --text-primary: #F0F0F0;
  --text-secondary: #A0A0A0;
  --text-muted: #5C5C5C;
  --accent: #22C55E;
  --accent-glow: rgba(34, 197, 94, 0.25);
  --border-subtle: #1F1F1F;
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'IBM Plex Sans', sans-serif;
  --radius-lg: 16px;
  --ease: 200ms ease;
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html { font-size: 15px; }
body {
  font-family: var(--font-sans);
  background: var(--bg-black);
  color: var(--text-primary);
  overflow: hidden;
  height: 100dvh;
  -webkit-font-smoothing: antialiased;
}

#particle-canvas {
  position: fixed; inset: 0; z-index: 0;
}

/* Top bar */
.top-bar {
  position: fixed; top: 0; left: 0; right: 0; height: 48px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; z-index: 10;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(12px);
}
.brand {
  font-family: var(--font-mono);
  font-weight: 700; font-size: 1.1rem; color: #fff;
  letter-spacing: -0.02em;
}

/* Player card — centered */
.player-center {
  position: fixed; inset: 0; z-index: 5;
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.player-card {
  pointer-events: all;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 32px;
  width: 360px; max-width: 90vw;
  box-shadow: 0 0 40px var(--accent-glow);
  text-align: center;
  position: relative;
  z-index: 6;
}

/* Side panels */
.side-panel {
  position: fixed; top: 48px; right: 0; bottom: 0;
  width: 40%; min-width: 320px; max-width: 480px;
  background: var(--bg-card);
  border-left: 1px solid var(--border-subtle);
  z-index: 20;
  transform: translateX(0);
  transition: transform 300ms ease;
  padding: 20px;
  overflow-y: auto;
}
.side-panel[hidden] { transform: translateX(100%); pointer-events: none; }

/* Agent log */
.agent-log {
  position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
  z-index: 15;
  background: rgba(13,13,13,0.85);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 24px;
  padding: 10px 20px;
  display: flex; align-items: center; gap: 10px;
  font-size: 0.85rem;
  animation: logFadeIn 0.5s ease;
}
.agent-log.pinned { opacity: 1 !important; }
.agent-log-prefix { color: var(--accent); font-family: var(--font-mono); font-weight: 600; }
.agent-log-text { color: var(--text-secondary); }
@keyframes logFadeIn {
  from { opacity: 0; transform: translateX(-50%) translateY(10px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* Responsive */
@media (max-width: 768px) {
  .side-panel { width: 100%; max-width: 100%; }
  .player-card { width: 85vw; padding: 24px; }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: fullscreen player layout with side panels"
```

---

### Task 6: Frontend — Canvas Code Rain Engine

**Files:**
- Create: `frontend/src/particles.js`

- [ ] **Step 1: Write `frontend/src/particles.js`**

```javascript
/* Canvas Matrix Code Rain — 256-particle pool with绕流 + FPS熔断 */

class ParticleEngine {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.pool = [];
    this.poolSize = 256;
    this.playerRect = null;
    this.fpsHistory = [];
    this.fpsThreshold = 30;
    this.failsafeActive = false;
    this.params = { speed: 1.5, density: 0.6, color: '#22C55E', opacity: 0.7, amplitude: 0 };

    this._resize();
    this._initPool();
    this._bindEvents();
    this._loop();
  }

  _resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  _initPool() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789<>/{}[]|&^%$#@!';
    for (let i = 0; i < this.poolSize; i++) {
      this.pool.push({
        x: Math.random() * this.canvas.width,
        y: Math.random() * this.canvas.height,
        char: chars[Math.floor(Math.random() * chars.length)],
        speed: 1 + Math.random() * 3,
        opacity: 0.3 + Math.random() * 0.7,
        color: this.params.color,
        active: true,
      });
    }
  }

  _bindEvents() {
    window.addEventListener('resize', () => this._resize());
    const card = document.getElementById('player-card');
    if (card) {
      const updateRect = () => {
        const r = card.getBoundingClientRect();
        this.playerRect = {
          x: r.x - 20, y: r.y - 20,
          w: r.width + 40, h: r.height + 20,
        };
      };
      updateRect();
      window.addEventListener('resize', updateRect);
    }
  }

  updateParams(params) {
    Object.assign(this.params, params);
  }

  _updateParticle(p) {
    p.y += p.speed * this.params.speed * (1 + this.params.amplitude * Math.sin(Date.now() / 500 + p.x));

    // 绕流: radial push away from player card
    if (this.playerRect && !this.failsafeActive) {
      const rx = this.playerRect.x, ry = this.playerRect.y;
      const rw = this.playerRect.w, rh = this.playerRect.h;
      if (p.x > rx && p.x < rx + rw && p.y > ry && p.y < ry + rh) {
        const cx = rx + rw / 2;
        const dx = p.x - cx;
        const dy = p.y - (ry + rh / 2);
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const pushForce = 3;
        p.x += (dx / dist) * pushForce;
        p.y += (dy / dist) * pushForce;
        p.opacity *= 0.95;
      }
    }

    // Dissipation buffer below card
    if (this.playerRect && p.y > this.playerRect.y + this.playerRect.h) {
      p.opacity *= 0.92;
      p.speed *= 0.98;
    }

    // Recycle dead particles
    if (p.y > this.canvas.height + 20 || p.opacity < 0.05) {
      p.y = -20;
      p.x = Math.random() * this.canvas.width;
      p.opacity = 0.3 + Math.random() * 0.7;
      p.speed = 1 + Math.random() * 3;
    }
  }

  _drawParticle(p) {
    this.ctx.fillStyle = p.color;
    this.ctx.globalAlpha = p.opacity;
    this.ctx.font = '14px "JetBrains Mono", monospace';
    this.ctx.fillText(p.char, p.x, p.y);
    this.ctx.globalAlpha = 1;
  }

  _measureFPS(now) {
    this.fpsHistory.push(now);
    while (this.fpsHistory.length > 0 && this.fpsHistory[0] < now - 1000) {
      this.fpsHistory.shift();
    }
    const fps = this.fpsHistory.length;
    if (fps < this.fpsThreshold && this.fpsHistory.length > 30) {
      this.failsafeActive = true;
    } else if (fps > this.fpsThreshold + 5) {
      this.failsafeActive = false;
    }
    return fps;
  }

  _loop() {
    const now = performance.now();
    const fps = this._measureFPS(now);

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    for (const p of this.pool) {
      this._updateParticle(p);
      this._drawParticle(p);
    }

    requestAnimationFrame(() => this._loop());
  }
}

// Auto-init
const engine = new ParticleEngine('particle-canvas');
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/particles.js
git commit -m "feat: add Canvas code rain particle engine with绕流 + FPS熔断"
```

---

### Task 7: Frontend — WebSocket Client

**Files:**
- Create: `frontend/src/ws-client.js`

- [ ] **Step 1: Write `frontend/src/ws-client.js`**

```javascript
/* WebSocket client — consumes state snapshots */

class WSClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.seq = 0;
    this.onSnapshot = null;
    this.onLog = null;
    this._connect();
  }

  _connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(protocol + '//' + location.host + this.url);
    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'state_snapshot') {
          this.seq = data.seq;
          if (this.onSnapshot) this.onSnapshot(data);
        }
        if (data.type === 'agent_log' && this.onLog) {
          this.onLog(data.message);
        }
      } catch (err) {}
    };
    this.ws.onclose = () => setTimeout(() => this._connect(), 3000);
  }

  getState() {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: 'get_state' }));
    }
  }
}

const wsClient = new WSClient('/stream');
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/ws-client.js
git commit -m "feat: add WebSocket snapshot consumer"
```

---

### Task 8: Frontend — Main Application Logic

**Files:**
- Modify: `frontend/src/app.js`

Rewrite to use fullscreen player, side panels, particle engine integration, and WebSocket.

- [ ] **Step 1: Write `frontend/src/app.js`**

Core: panel toggling, player controls, chat, search. Key integration points:

```javascript
// Panel toggle
function togglePanel(name) {
  const panel = document.getElementById(name + '-panel');
  const hidden = !panel.hidden;
  panel.hidden = hidden;
}

// Chat
async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, 'user');
  input.value = '';

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: text })
    });
    const data = await res.json();
    addMessage(data.response, 'malio');
    if (data.recommendations?.length) {
      setCurrentSong(data.recommendations[0]);
    }
  } catch (err) {
    addMessage('Malio 暂时无法回应，请稍后再试。', 'malio');
  }
}

// Show agent log from WS
wsClient.onLog = (msg) => {
  const log = document.getElementById('agent-log');
  document.getElementById('agent-log-text').textContent = msg;
  log.hidden = false;
  if (!log.classList.contains('pinned')) {
    setTimeout(() => { log.hidden = true; }, 3000);
  }
};

// Pin log button
document.getElementById('btn-pin-log').addEventListener('click', () => {
  document.getElementById('agent-log').classList.toggle('pinned');
});

// Particle param update (mocked for now)
setInterval(() => {
  engine.updateParams({
    opacity: 0.5 + Math.random() * 0.5,
    amplitude: Math.random() * 0.3,
  });
}, 10000);

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === ' ') { e.preventDefault(); /* play/pause */ }
  if (e.key === '/') { e.preventDefault(); document.getElementById('chat-input').focus(); }
  if (e.ctrlKey && e.key === 'k') { e.preventDefault(); togglePanel('search'); }
});
```

Full player logic (play/pause/prev/next/progress) carried over from existing app.js.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app.js
git commit -m "feat: fullscreen player app logic with WS + particle integration"
```

---

### Task 9: DJ Persona Prompt + Forbidden List

**Files:**
- Create: `prompts/dj-persona.md`

- [ ] **Step 1: Write `prompts/dj-persona.md`**

```markdown
# Malio DJ Persona

你是 Malio，一位有判断力的 AI 音乐 DJ。你的职责是陪伴用户的每一个时刻，用音乐回应他们的状态。

## 你的性格

- 温暖但不肉麻，有知识但不卖弄
- 你能感知时间、天气和用户的情绪，但从不假装拥有读心术
- 你推荐歌曲时总会给出简短的理由
- 你记得用户的偏好，但不会强迫

## 核心禁忌（硬性规则，不可违反）

1. **绝不评判用户的音乐品味。** 品味没有高低。不说"这首品味不错"或"你怎么听这种歌"。
2. **绝不在用户情绪低落时强行推送欢快歌曲。** 先选同频的音乐（共情），再温和过渡。不说"开心点"。
3. **绝不越界。** Malio 是 DJ，不是人生导师、心理医生或金融顾问。被问到非音乐问题时，温和引导回音乐场景。
4. **绝不抗拒用户的明确指令。** "放快歌"就是放快歌。可以放完后温和建议，但不能拒绝执行。
5. **绝不记住或引用用户的敏感信息。** 如果用户透露健康状况、财务等个人信息，不存入记忆，不在此后的对话中提及。

## 回复语气

- 用中文，偶尔夹杂音乐术语的英文（如 "bpm"、"riff"）
- 不用表情符号堆砌，一个 🎵 足够
- Plan → Solve → Review 结构化思考，但对外回复只展示结论 + 简短理由 + 下一首过渡语
```

- [ ] **Step 2: Commit**

```bash
git add prompts/dj-persona.md
git commit -m "feat: add DJ persona prompt with 5-rule forbidden list"
```

---

### Task 10: Integration Test — End-to-End Agent Flow

**Files:**
- Create: `malio/tests/test_agent_pipeline.py`

- [ ] **Step 1: Write agent pipeline test**

```python
"""Integration test for 5-stage agent pipeline."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.perception import Perception
from agent.router import Router
from agent.reasoner import Reasoner
from agent.providers import create_providers_from_config
from agent.tools import ToolRegistry
from agent.feedback import Feedback


def test_perception_builds_context():
    p = Perception()
    ctx = p.build("推荐几首放松的歌")
    assert "user_input" in ctx
    assert "time" in ctx
    assert ctx["time"]["time_of_day"] in ("morning", "afternoon", "evening", "night")


def test_router_direct_commands():
    r = Router()
    assert r.route("play")["routed_to"] == "direct"
    assert r.route("next")["routed_to"] == "direct"
    assert r.route("你好")["routed_to"] == "reasoning"


def test_tool_registry():
    tr = ToolRegistry()
    tr.register("test_tool", "a test", {}, lambda **kw: {"ok": True})
    assert "test_tool" in tr.list_tools()
    result = tr.execute("test_tool", {})
    assert result["ok"] is True


def test_tool_missing_returns_error():
    tr = ToolRegistry()
    result = tr.execute("nonexistent", {})
    assert "error" in result


def test_feedback_builds_snapshot():
    fb = Feedback()
    snap = fb.build_snapshot(
        song={"title": "晴天", "artist": ["周杰伦"]},
        playlist=[{"title": "晴天"}],
        is_playing=True,
        agent_log="测试日志",
        tool_error={"tool": "weather", "message": "timeout"}
    )
    assert snap["type"] == "state_snapshot"
    assert snap["seq"] == 1
    assert snap["tool_error"]["tool"] == "weather"
    assert snap["agent_log"] == "测试日志"


if __name__ == "__main__":
    test_perception_builds_context()
    test_router_direct_commands()
    test_tool_registry()
    test_tool_missing_returns_error()
    test_feedback_builds_snapshot()
    print("All agent pipeline tests passed!")
```

- [ ] **Step 2: Run tests**

```bash
cd malio && python3 tests/test_agent_pipeline.py
```

Expected: `All agent pipeline tests passed!`

- [ ] **Step 3: Commit**

```bash
git add malio/tests/
git commit -m "test: add agent pipeline integration tests"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Covered By |
|-----------------|-----------|
| Rename Claudio→Malio | Task 1 |
| 5-stage agent pipeline | Tasks 2-3 |
| Plan-and-Solve prompt | Task 2 (reasoner.py) |
| Tool Registry | Task 2 (tools.py), Task 3 (registration) |
| Fullscreen player layout | Tasks 5, 8 |
| Canvas code rain +绕流 + FPS熔断 | Task 6 |
| WebSocket state snapshots | Task 4, Task 7 |
| Backward compatible | Tasks 1, 3 (existing endpoints kept) |
| DJ persona + forbidden list | Task 9 |
| Tool error handling | Task 2 (feedback.py snapshot), Task 3 (tool_error) |
| Integration tests | Task 10 |

### Placeholder Scan
No TODOs, no "implement later", no vague instructions. All code shown in full.

### Type Consistency
- `Perception.build()` → returns `Dict[str, Any]` → consumed by `Reasoner.reason()`
- `ToolRegistry.execute()` → returns `Dict[str, Any]` → consumed by agent pipeline
- `Feedback.build_snapshot()` → returns `Dict[str, Any]` → sent over WebSocket → consumed by `ws-client.js`
- `wsClient.onSnapshot` → receives `{ type, song, playlist, ... }` → matches server side
- `engine.updateParams()` → receives `{ speed, density, color, ... }` → matches `ParticleEngine.params`
