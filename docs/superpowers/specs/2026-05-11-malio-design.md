# Malio — AI Music Agent Design Spec

**Status**: Approved  
**Date**: 2026-05-11  
**Author**: User + Claude Code

## 1. Overview

Malio is the successor to Claudio — an AI-powered personal radio DJ rebuilt on a proper agent architecture. It applies ReAct and Plan-and-Solve patterns to create a music agent that thinks before acting, uses tools deliberately, and explains its reasoning.

### 1.1 Core Principle

Learning-first, features-second. The architecture is the product. Every feature serves to demonstrate agent design patterns.

### 1.2 Name

"Malio" replaces "Claudio".

## 2. Agent Architecture (5-Stage Pipeline)

```
User Input → Perception → Routing → Reasoning → Tool Use → Feedback
```

### 2.1 Perception

- Receive user message (text via chat panel)
- Load environment context (time, weather, calendar)
- Load user profile (taste.md, routines.md, mood-rules.md)
- Load recent play history (avoid repeats)

### 2.2 Routing

- Explicit commands ("play", "pause", "next") → direct execution
- Natural language → forward to Reasoning stage

### 2.3 Reasoning (Plan-and-Solve + ReAct)

Structured prompt output:

```json
{
  "plan": {
    "intent": "what the user wants",
    "strategy": "how to select songs",
    "constraints": ["no repeats", "match weather", "consider mood"]
  },
  "solve": {
    "actions": [{"tool": "search_music", "query": "...", "limit": 5}],
    "results": [...]
  },
  "review": {
    "self_check": "does this satisfy the user?",
    "adjustments": "what to change if not",
    "segue": "transition to next song"
  }
}
```

ReAct loop: Thought → Action → Observation → Thought → ... → Final Answer. The agent alternates between reasoning and tool calls within a single interaction.

### 2.3.1 Tool Error Handling

Every tool call can fail. The agent must degrade gracefully, never silently drop a failure.

**State snapshot includes `tool_error` field:**

```json
{
  "type": "state_snapshot",
  "tool_error": {
    "tool": "get_weather",
    "message": "天气服务暂不可用",
    "degraded": true
  },
  "agent_log": "天气获取失败，但依然为你选了一些适合此刻的歌。"
}
```

**Degradation strategies per tool:**

| Tool Failure | Agent Response |
|-------------|---------------|
| `search_music` fails | "搜索暂时出了点问题，让我从你的本地曲库中为你推荐几首。" → query local SQLite instead |
| `get_weather` fails | Skip weather context, use only time+mood for selection. No retry loop. |
| `get_play_url` fails | Skip this track, try next in playlist. Log failure, don't report to user unless all tracks fail. |
| `add_to_library` fails | Silent retry once. If still fails, queue for later (write to pending list). |
| `tts` fails | Silent degradation — text reply still works. |

**Core rule**: The agent must always produce a response, even with partial information. Graceful degradation > silent failure.

### 2.4 Tool Use

Tool Registry — standardized JSON Schema definitions for each tool. The LLM selects tools based on the plan, not hardcoded in main.py.

| Tool | Description |
|------|-------------|
| `search_music` | Search songs by query, source, limit |
| `get_play_url` | Get playable URL for a track |
| `check_history` | Query recent play records |
| `get_weather` | Fetch current weather |
| `add_to_library` | Save track to local DB |
| `get_library_stats` | Get library statistics |

### 2.5 Feedback

- Generate natural-language DJ response
- Update playlist state
- Push state snapshot to frontend via WebSocket
- Record user preference signal

## 3. State Management

### 3.1 WebSocket Protocol

Agent pushes immutable state snapshots, not incremental deltas:

```json
{
  "type": "state_snapshot",
  "song": {"id": "...", "title": "...", "artist": [...], "duration": 0},
  "playlist": [...],
  "is_playing": false,
  "agent_log": "Malio 正在感受你的情绪...",
  "timestamp": 1234567890,
  "seq": 42
}
```

- Frontend only renders snapshots — no derived state
- Reconnect: server re-pushes latest snapshot
- Heartbeat every 30s to detect disconnection

### 3.2 Memory Layers

| Layer | Storage | Scope |
|-------|---------|-------|
| Short-term | In-memory dict | Current conversation |
| User profile | Markdown files (user/*.md) | Persistent preferences |
| History | SQLite (existing claudio.db) | Play records |

Phase 3 migration: Markdown → SQLite for user profile when access frequency increases.

## 4. Visual System

### 4.1 Theme

- Background: `#000000` (OLED black)
- Fonts: JetBrains Mono (code/mono) + IBM Plex Sans (UI text)
- Accent: `#22C55E` (green — interactive surface layer)
- Player controls: white/light gray neutral palette; only progress bar uses ambient color

### 4.2 Canvas Code Rain (Bottom Layer)

- 256-particle pool with recycling
- Emission sources: code lines on left and right edges (characters "evaporate" from static code)
- Waterfall flow: particles fall vertically from top and emission sources
- Collision: when particles enter expanded bounding box of player card, apply radial push-out force + tangential velocity for smooth绕流
- Dissipation: below player card, particles decelerate, blur, opacity fades in a 20px buffer zone
- Performance failsafe: FPS counter. If sustained < 30fps, auto-disable绕流, switch to transparency-based avoidance

### 4.3 Dynamic Parameter Mapping

Sample environment every 5-10 seconds, smooth transition over 5 seconds:

| Parameter | Visual Property |
|-----------|----------------|
| Mood: happy | Flow speed ↑, color warm green-yellow |
| Mood: sad | Flow speed ↓, color blue-purple |
| Weather: clear | Density low, opacity high |
| Weather: rain | Density high, speed slightly faster |
| Time: night | Brightness reduced, colors dim |
| Music: energetic | Amplitude high, particles pulse with beat |
| Music: calm | Amplitude low, smooth steady fall |

Color mapping table:
- Joyful/excited → warm yellow `#E6C200`
- Content/satisfied → warm orange `#E67E22`
- Calm/peaceful → soft green `#27AE60`
- Melancholy → blue-purple `#756BB1`
- Energetic → bright cyan `#00D4AA`

### 4.4 Agent Log Overlay (Top Layer)

- Frosted glass bar (`backdrop-filter: blur(8px)`) with semi-transparent dark background
- Floats up from bottom to ~16px below player card
- Auto-fades after 3 seconds
- Pin/expand button (📌) to keep log visible for inspection
- Humanized prefix: "Malio 正在感受你的情绪… 决定为你选一些明亮的调子。"
- Content: actual agent reasoning steps (not decorations)

### 4.5 Player Card

- Centered on screen, positioned above the dissipation buffer zone
- Subtle outer glow (ambient color) rendered above Canvas layer
- Left/right swipe on card: next/previous song, with particles collectively deflecting in swipe direction
- Card glow intensifies slightly when music is playing

## 5. Layout — Fullscreen Player

### 5.1 Desktop (≥768px)

```
┌──────────────────────────────────────────┐
│ ☰ Malio              🔍 💬 ⚙️          │ 48px top bar
├──────────────────────────────────────────┤
│                                          │
│     [Canvas code rain background]        │
│                                          │
│         ┌─────────────────┐              │
│         │   🎵 Player     │              │  Centered card
│         │   Album Art     │              │  Particles绕流
│         │   Title/Artist  │              │
│         │   Progress bar  │              │
│         │   ⏮ ▶ ⏭      │              │
│         └─────────────────┘              │
│                                          │
│     [Agent log — frosted glass float]    │
│                                          │
└──────────────────────────────────────────┘

Side panels (chat/search): slide from right, 40% width + translucent overlay
```

### 5.2 Mobile (<768px)

- Left/right code emission sources shrink to thin top bar
- Chat/search panels: fullscreen overlay instead of 40%
- Bottom gesture hint hidden, all edge-swipe based
- Player card scales down proportionally

### 5.3 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Space | Play/Pause |
| ← → | Previous/Next song |
| / | Focus chat input |
| Ctrl+K | Open search |
| Esc | Close panel |

## 6. DJ Persona (prompts/dj-persona.md)

Core rule: Malio is not a passive player. It has judgment.

- Knows the user's preferences and routines
- Makes recommendations with reasons
- Politely suggests alternatives when appropriate ("深夜了，也许一首舒缓的爵士会更适合？")
- Tone: warm but not cheesy, knowledgeable but not pretentious
- Language: Chinese with occasional English music terms

**Core Forbidden List (硬性安全护栏):**

1. **Never judge the user's music taste.** No "这首品味不错" or "你怎么听这种歌"。品味没有高低，只有适不适合当下。
2. **Never force cheerfulness on a low mood.** 用户情绪低落时，不要强行推欢快歌曲。可以先选同频的音乐（共情），再温和过渡到稍明亮的调子。不可以说"开心点"。
3. **Never suggest content outside music.** Malio 是 DJ，不是人生导师、心理医生或金融顾问。被问到非音乐问题时，温和引导回音乐场景。
4. **Never override explicit user commands.** "放快歌"就是放快歌。可以在放完后说"下一首要不要试试舒缓一点的？"但不能拒绝执行。
5. **Never retain or repeat sensitive information.** 如果用户在对话中透露了个人敏感信息（健康状况、财务等），不存入记忆，不在此后的对话中引用。

## 7. Project Structure

```
malio/
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── perception.py   # Stage 1: context assembly
│   │   ├── router.py       # Stage 2: intent routing
│   │   ├── reasoner.py     # Stage 3: P&S + ReAct prompt builder
│   │   ├── tools.py        # Stage 4: tool registry + executor
│   │   └── feedback.py     # Stage 5: response generation + state push
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── short_term.py   # In-memory conversation context
│   │   ├── user_profile.py # Read/write user/*.md files
│   │   └── history.py      # SQLite play history queries
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── kimi.py         # Kimi API (kimi-k2.5, temperature=1)
│   │   ├── netease.py      # Netease Cloud Music search + play
│   │   ├── spotify.py      # Spotify (Phase 3, after HK card)
│   │   ├── tts.py          # ElevenLabs TTS
│   │   └── weather.py      # OpenWeather API
│   ├── server.py           # FastAPI + WebSocket (state snapshot protocol)
│   └── config.py           # Pydantic Settings
├── frontend/
│   ├── index.html          # PWA entry
│   ├── src/
│   │   ├── app.js          # Main application
│   │   ├── style.css       # OLED dark theme
│   │   ├── particles.js    # Canvas粒子引擎 + FPS熔断
│   │   └── ws-client.js    # WebSocket client (snapshot consumer)
│   ├── public/
│   │   ├── manifest.json
│   │   └── sw.js           # Service Worker
│   └── vite.config.js
├── prompts/
│   └── dj-persona.md       # DJ personality system prompt
├── user/
│   ├── taste.md
│   ├── routines.md
│   ├── mood-rules.md
│   └── color-map.json      # Mood/weather → color mapping
├── MALIO_ARCHITECTURE.md
└── docs/superpowers/specs/2026-05-11-malio-design.md
```

## 8. Phased Plan

### Phase 1 — Core Agent + Visual Foundation
- [ ] Rename project from Claudio to Malio
- [ ] Implement 5-stage agent pipeline (perception → routing → reasoning → tools → feedback)
- [ ] Plan-and-Solve structured prompt for Kimi integration
- [ ] Tool Registry with JSON Schema definitions
- [ ] Fullscreen player layout (HTML/CSS)
- [ ] Canvas code rain bottom layer (particle system +绕流 + FPS failsafe)
- [ ] WebSocket state snapshot protocol
- [ ] Backward compatible: existing features must still work

### Phase 2 — Agent UX + Dynamics
- [ ] Agent log overlay (frosted glass + pin button + auto-fade)
- [ ] Dynamic parameter mapping (mood/weather/time → particle properties)
- [ ] Swipe gesture → particle deflection
- [ ] DJ persona with judgment boundaries
- [ ] Color mapping table

### Phase 3 — Polish + External Services
- [ ] Mobile responsive (fullscreen panels, edge gestures)
- [ ] PWA offline (Service Worker caching)
- [ ] Spotify integration (after HK bank card)
- [ ] SQLite migration for user profile files

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| WebSocket state drift | Immutable snapshots, not deltas; reconnect re-pushes latest |
| Agent latency feels frozen | Push agent log immediately when reasoning starts; turn wait into "AI thinking show" |
| Canvas perf on low-end devices | FPS counter + auto熔断 at < 30fps; disable绕流, use transparency avoidance |
| User file I/O bottleneck | Phase 1-2 use Markdown/JSON files; Phase 3 migrate to SQLite with version control |
| Kimi API rate limit | Cache recent responses; degrade gracefully to offline DJ mode |
| Tool call failures break flow | `tool_error` field in snapshot + per-tool degradation strategy; agent always produces a response |
| DJ overreach | Core forbidden list in persona prompt; never judge taste, never force cheerfulness, never act as therapist |
