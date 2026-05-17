# Malio 架构文档

## 总览

```
┌────────────────────────────────────────────────────────────┐
│                    前端 PWA (Vite + Vanilla JS)              │
│  particles.js  │  ws-client.js  │  app.js  │  audio API    │
│   800粒子引擎    │  WebSocket客户端  │  播放器UI  │  Web Audio    │
└──────────┬─────────────────────────────────────┬──────────┘
           │  HTTP/WS                           │ ws://:8007/stream
           ▼                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (:8007)                        │
│                                                              │
│  /api/chat ──→ Pipeline ──→ 5 阶段 Agent 管线                │
│                     │        Perception → Router              │
│                     │          ├─ music intent → MusicAgent   │
│                     │          ├─ chat intent  → (direct)     │
│                     │          └─ rule intent  → YOLO path    │
│                     │                                        │
│  /api/songs         ├──→ Persona Engine (三维人格)            │
│  /api/playlists     ├──→ State Manager (多用户状态)           │
│  /api/spotify/*     └──→ Memory (L2/L3/L4)                   │
│  /api/netease/*                                               │
│  /api/tts/*                                                   │
│  /stream (WS)                                                 │
│                                                              │
│  Multi-Agent:                                                │
│  ┌─────────────┐  ┌─────────────┐                             │
│  │ MusicAgent  │  │  (VisualAgent │  ← 下一步)               │
│  │ 独立ReAct   │  │   粒子控制    │                            │
│  │ 选歌+DJ文案 │  │   独立Worker  │                            │
│  └─────────────┘  └─────────────┘                             │
└──────────────────────────────────────────────────────────────┘
```

## 目录结构

```
malio/
├── main.py                 ← API 路由 + WebSocket + 后台循环
├── agent/
│   ├── pipeline.py         ← 5 阶段管线 + ReAct + DSL 规则
│   ├── persona.py          ← 三维人格引擎 + 天气混合
│   ├── reasoner.py         ← prompt 组装 + JSON output 强制
│   ├── router.py           ← Plan/Agent/YOLO 三模式分类
│   ├── tools.py            ← ToolRegistry 注册制
│   ├── feedback.py         ← WebSocket 广播
│   ├── providers.py        ← 多 LLM Provider 抽象
│   └── perception.py       ← 环境感知 + 时间槽
├── core/
│   ├── state_manager.py    ← 多用户状态 + JSON 持久化
│   ├── recommendation_engine.py
│   ├── scene_aware_engine.py  ← 天气/日历上下文
│   ├── audio_analyzer.py
│   ├── device_control.py
│   └── metrics.py          ← CSV 量化指标
├── memory/
│   ├── short_term.py       ← L2: 24h 行为快照
│   ├── user_profile.py     ← L3: 蒸馏画像 + 偏好衰减
│   └── history.py          ← L4: 不可变追加日志
├── integrations/
│   ├── kimi_integration.py
│   ├── netease_integration.py
│   ├── spotify_integration.py
│   └── elevenlabs_integration.py
├── config/
│   └── config.py           ← 配置类（从 .env 读取）
├── tests/
│   ├── test_smoke.py       ← 5 个端到端冒烟测试
│   └── test_agent_pipeline.py ← 6 个管线单元测试
├── data/
│   ├── audio/songs/        ← 本地音频文件
│   ├── sessions/           ← 用户会话持久化 JSON
│   └── metrics.csv         ← 量化指标
├── prompts/
│   └── dj-persona.md       ← DJ 人设 prompt
└── user/
    └── color-map.json      ← 颜色映射表

frontend/
├── src/
│   ├── particles.js        ← 800粒子引擎
│   ├── app.js              ← 播放器 + 聊天 + 手势
│   ├── ws-client.js        ← WebSocket 客户端
│   ├── particle-rules.js   ← DSL 规则引擎
│   ├── audio-analyzer.js
│   └── particles/          ← 粒子子系统
├── index.html
└── vite.config.js
```

## 数据流：一次"推荐一首歌"

```
用户输入 "推荐一首歌"
        │
        ▼
   /api/chat (POST) → Pipeline.run()
        │
        ▼
   Stage 1: Perception
   ┌─────────────────────────────┐
   │ 环境感知 (时间/天气)          │
   │ L2 摘要 (24h行为)            │
   │ L3 画像 (偏好画像)            │
   │ chat_history (对话记忆)       │
   │ persona_style (人格状态)      │
   └─────────────┬───────────────┘
                 ▼
   Stage 2: Router
   ┌─────────────────────────────┐
   │ Plan  → 只读查询，不调 LLM    │
   │ Agent → 5 阶段管线 (默认)     │
   │ YOLO  → 全自动 (白名单限制)   │
   └─────────────┬───────────────┘
                 ▼
   Stage 3: Reasoner (ReAct loop, max 3 rounds)
   ┌─────────────────────────────┐
   │ Round 1: LLM 决定调哪些工具   │
   │   → 执行 → 收集歌曲           │
   │   → "已获取50首歌，够了就停"   │
   │ Round 2: LLM 看到结果 → 输出 JSON │
   │   {selected_song_id, response, atmosphere, core_actions} │
   └─────────────┬───────────────┘
                 ▼
   Stage 4: Tools
   ┌─────────────────────────────┐
   │ 优先用 _react_songs (ReAct 真实数据) │
   │ 缺歌时 fallback 到推荐引擎    │
   │ 闲聊时不换歌 (intent=general_chat) │
   └─────────────┬───────────────┘
                 ▼
   Stage 5: Feedback
   ┌─────────────────────────────┐
   │ selected_song_id → 精确定位  │
   │ persona 约束 core_actions    │
   │ 天气 mix 调色                 │
   │ response = "🎵 歌名 — 歌手\n\nDJ文案" │
   │ push_snapshot (WS)           │
   │ → 前端收到 → TTS + 播放 + 粒子变色 │
   └─────────────────────────────┘
```

## API 端点

### Chat

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 主对话入口。Body: `{user_id, input}` → `{response, recommendations, auto_play}` |
| POST | `/api/recommend` | 纯推荐（无对话）。Body: `{user_id, context, limit}` |

### 歌曲管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/songs` | 获取全部歌曲 |
| POST | `/api/songs` | 添加歌曲。Body: `{id, title, artist, album, ...}` |
| DELETE | `/api/songs/{id}` | 删除歌曲 |
| PUT | `/api/songs/{id}/energy` | 手动调整 E/W/D 值。Body: `{energy?, warmth?, density?}` |

### 播放列表 (Memory Corridor)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/playlists` | 全部播放列表 |
| POST | `/api/playlists` | 创建播放列表 |
| GET | `/api/playlists/{id}` | 播放列表详情 + 歌曲 |
| PUT | `/api/playlists/{id}` | 更新元数据 |
| DELETE | `/api/playlists/{id}` | 删除播放列表 |
| POST | `/api/playlists/generate` | 从捕获歌曲生成歌单 (星云捕获) |
| POST | `/api/playlists/{id}/songs` | 添加歌曲到列表 |
| DELETE | `/api/playlists/{id}/songs/{song_id}` | 从列表移除歌曲 |
| GET | `/api/playlists/scenes` | 场景歌单 (按时段自动匹配) |

### Spotify

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/spotify/search` | 搜索曲目。Query: `query, limit` |
| POST | `/api/spotify/recommendations` | Spotify 推荐 |
| GET | `/api/spotify/track/{id}` | 曲目详情 |
| GET | `/api/spotify/artists` | 搜索艺术家 |
| POST | `/api/spotify/add-to-library` | 添加到库 |
| POST | `/api/spotify/import` | 导入曲目详情到本地 DB |

### 网易云音乐

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/netease/search` | 搜索曲目 |
| GET | `/api/netease/track/{id}` | 曲目详情 |
| GET | `/api/netease/track/{id}/url` | 获取可播放 URL |
| GET | `/api/netease/track/{id}/details` | 完整详情 |
| GET | `/api/netease/top` | 热门歌曲 |
| GET | `/api/netease/new` | 新歌 |
| POST | `/api/netease/add-to-library` | 添加到库 |
| POST | `/api/netease/import` | 搜索并导入 |

### TTS

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tts/speak` | 文字转语音。Body: `{text, voice_id?}` → audio/mpeg |
| GET | `/api/tts/voices` | 可用语音列表 |
| GET | `/api/tts/voice/{id}` | 语音详情 |

### 设备控制

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 设备列表 |
| POST | `/api/devices/connect` | 连接设备 |
| POST | `/api/devices/disconnect` | 断开设备 |
| POST | `/api/devices/play` | 播放 |
| POST | `/api/devices/pause` | 暂停 |
| POST | `/api/devices/stop` | 停止 |
| POST | `/api/devices/volume` | 设置音量 |
| GET | `/api/devices/status` | 设备状态 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/context` | 当前场景上下文 |
| GET | `/api/library/stats` | 曲库统计 (E/W/D 分布) |
| POST | `/api/import-data` | 批量导入 |
| GET | `/api/generate-playlist-name` | 生成歌单名 |
| GET | `/` | 健康检查 |
| GET | `/health` | 健康检查 |
| WS | `/stream` | WebSocket 实时状态推送 |

## WebSocket 消息

### 前端 → 后端

| Action | Body | 说明 |
|--------|------|------|
| `get_state` | `{user_id}` | 请求当前状态快照 |
| `sync_playlist` | `{user_id, songs[]}` | 同步前端歌单到后端 |
| `core_event` | `{user_id, event: {type, detail}}` | 手势/交互事件 |
| `heartbeat` | `{user_id, current_song_id, is_playing}` | 30s 心跳 |

### 后端 → 前端

| Type | 字段 | 说明 |
|------|------|------|
| `state_snapshot` | `song, playlist, is_playing, atmosphere, core_mode, core_action, seq` | 完整状态快照 |
| `agent_log` | `message` | Agent 思考日志 |
| `rule` | `rule` | DSL 规则 (Agent 生成) |

## 依赖

```txt
fastapi>=0.115.0          # Web 框架
uvicorn>=0.30.0           # ASGI 服务器
pydantic>=2.10.0          # 数据验证
pydantic-settings>=2.5.0  # 配置管理
sqlalchemy>=2.0.0         # ORM
requests>=2.31.0          # HTTP 客户端
anthropic>=0.39.0         # Claude API (可通过 Provider 抽象切换)
python-dotenv>=1.0.0      # 环境变量

开发/测试:
pytest>=8.0.0
pytest-asyncio>=0.24.0
httpx>=0.28.0
```

## 启动

```bash
cd malio
pip install -r requirements.txt
python main.py            # 后端 :8007
cd ../frontend && npx vite --host   # 前端 :5173
```

---

## 多 Agent 架构（v0.3+）

### 设计原则

- **单职责**：每个 Agent 只做一件事，只做自己擅长的
- **无状态**：Worker Agent 不存状态，所有状态在 StateManager
- **Router 委派**：所有通信经过 Router，Agent 间不直接通信
- **共享 LLM**：当前阶段共用相同的 Provider，未来可各自独立模型

### 当前 Agent

| Agent | 职责 | LLM | 状态 |
|-------|------|-----|------|
| **Router** (Pipeline) | 意图分类 + 任务委派 + 结果组装 | ✓ DeepSeek Flash | 生产 |
| **MusicAgent** | 音乐搜索、推荐、选歌、DJ 文案 | ✓ 独立 ReAct | 生产 |
| **VisualAgent** | 粒子控制、颜色生成、core_actions | ✗ 规则引擎 | 下一步 |
| **MemoryAgent** | L3 蒸馏、偏好衰减、确认队列 | ✗ 定时任务 | 后续 |

### MusicAgent 数据流

```
用户:"推荐一首歌"
  → Pipeline(Perception) → Router: 识别为 music intent
  → Pipeline 委派 MusicAgent.reason(user_input, constraints, context)
  → MusicAgent:
      构建 DJ prompt → 加载音乐 tools (search/get_local/recommend)
      → ReAct loop (max 3 rounds):
          Round 1: LLM 调工具 → get_local_songs(80) → 30 songs
          ≥5 songs → Hard Stop → Phase 2 LLM → JSON
      → 返回 {selected_song_id, response, _react_songs, atmosphere, core_actions}
  → Pipeline Stage 4/5: 按 selected_song_id 设播放队列
  → 前端: 🎵 歌名 — 歌手 + DJ 文案
```

### 下一步：VisualAgent

```
用户:"换成天空蓝"
  → Router: 识别为 visual intent
  → VisualAgent: 规则引擎直接设色，不需要 LLM
  → 或者 LLM 根据用户描述生成 atmosphere+core_actions JSON
```
