# Malio — AI Music Agent Architecture

## Overview

Malio is an AI-powered personal radio DJ. The architecture follows a standard agent loop with Plan-and-Solve reasoning and ReAct-style tool use.

## Agent Loop (5-Stage Pipeline)

```
User Input
    │
    ▼
┌──────────────────────────────────────┐
│ 1. PERCEPTION（感知）                 │
│    - 接收用户消息                      │
│    - 获取环境上下文（时间、天气、日程）    │
│    - 加载用户偏好和历史                  │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ 2. ROUTING（路由）                    │
│    - 显式命令：直接执行（播放/暂停/切歌） │
│    - 自然语言：转入 Reasoning           │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ 3. REASONING（推理）                  │
│    Plan-and-Solve 三段式：             │
│    ┌──────────────────────────┐      │
│    │ PLAN:  分析用户需求，制定选歌策略  │      │
│    │ SOLVE: 执行工具调用，获取歌曲      │      │
│    │ REVIEW: 审查结果，调整不满意项     │      │
│    └──────────────────────────┘      │
│    ReAct 交替循环：                    │
│    Thought → Action → Observation →   │
│    Thought → Action → ... → Answer    │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ 4. TOOL USE（工具调用）                │
│    ┌──────────┬─────────────────────┐│
│    │ 音乐搜索  │ Netease / Spotify    ││
│    │ 播放控制  │ Audio element        ││
│    │ 音乐库   │ SQLite CRUD          ││
│    │ TTS      │ ElevenLabs / Fish    ││
│    │ 天气     │ OpenWeather          ││
│    │ 日程     │ Calendar API         ││
│    └──────────┴─────────────────────┘│
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│ 5. FEEDBACK（反馈）                   │
│    - 生成自然语言回复（DJ 口吻）         │
│    - 更新播放列表                      │
│    - 记录用户偏好                      │
│    - 通过 WebSocket 推送前端状态        │
└──────────────────────────────────────┘
```

## Plan-and-Solve Prompt Structure

```json
{
  "plan": {
    "intent": "用户想要什么",
    "strategy": "选歌策略",
    "constraints": ["排除最近播放", "匹配当前天气/时间", "考虑用户偏好"]
  },
  "solve": {
    "actions": [
      {"tool": "search_netease", "query": "温暖治愈 华语", "limit": 5},
      {"tool": "check_history", "user_id": "default"}
    ],
    "results": [...]
  },
  "review": {
    "self_check": "是否满足用户需求",
    "adjustments": "如果需要调整，怎么做",
    "segue": "下一首歌的过渡语"
  }
}
```

## Directory Structure

```
malio/
├── src/
│   ├── agent/
│   │   ├── perception.py    # Stage 1: 上下文组装
│   │   ├── router.py        # Stage 2: 意图路由
│   │   ├── reasoner.py      # Stage 3: Plan-and-Solve + ReAct
│   │   ├── tools.py         # Stage 4: 工具注册与调用
│   │   └── feedback.py      # Stage 5: 回复生成
│   ├── memory/
│   │   ├── short_term.py    # 当前对话上下文
│   │   ├── user_profile.py  # 用户偏好（taste.md 等）
│   │   └── history.py       # 播放历史
│   ├── integrations/
│   │   ├── kimi.py          # Kimi API
│   │   ├── netease.py       # 网易云音乐
│   │   ├── spotify.py       # Spotify（HK 开户后）
│   │   ├── tts.py           # TTS 合成
│   │   └── weather.py       # 天气
│   ├── server.py            # FastAPI + WebSocket
│   └── config.py            # 配置管理
├── frontend/                 # PWA 前端（不变）
├── user/
│   ├── taste.md
│   ├── routines.md
│   └── mood-rules.md
└── prompts/
    └── dj-persona.md
```

## Tool Registry

Each tool is a standard function with a JSON Schema description:

```python
TOOLS = {
    "search_music": {
        "description": "搜索歌曲，支持歌曲名、歌手、风格",
        "parameters": {
            "query": "string",
            "source": "netease | spotify",
            "limit": "int"
        }
    },
    "get_play_url": {
        "description": "获取歌曲播放链接",
        "parameters": {"track_id": "string"}
    },
    "check_play_history": {
        "description": "查询最近播放记录，避免重复推荐",
        "parameters": {"user_id": "string", "hours": "int"}
    },
    "get_weather": {
        "description": "获取当前天气",
        "parameters": {"city": "string"}
    }
}
```

## What Changes vs Current Claudio

| Current | New |
|---------|-----|
| Kimi prompt 是自由格式 | Plan → Solve → Review 结构化输出 |
| 意图识别 + 生成是两步 | ReAct 交替循环，边想边做 |
| 工具调用硬编码在 main.py | Tool Registry，LLM 按需选择 |
| 没有显式的 memory 层 | short_term / user_profile / history 三层记忆 |
| error 返回模糊字符串 | ReAct 循环中自我修正 |
