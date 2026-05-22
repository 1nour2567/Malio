# Malio — AI Particle-Embodied Music Agent

## 核心命题

如果 AI agent 有身体，它应该怎样存在于人类的屏幕里？

Malio 的回答：**内核是 agent 的身体，粒子流是它的环境，手势是与它的对话，DSL 规则是它的学习能力。**

不是"带粒子背景的播放器"，而是"以粒子为身体的 AI 生命体"。

---

## 一、系统总览

```
┌────────────────────────────────────────────────────────┐
│  交互层 — 手势 + 粒子物理 + 音频同步                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 手势识别  │ │ 粒子引擎  │ │ DSL 规则  │ │ 音频分析  │ │
│  │ swipe     │ │ 800 粒子  │ │ 5 内置    │ │ 三频段    │ │
│  │ tap×2     │ │ 9 大系统  │ │ Agent 生成│ │ 节拍检测  │ │
│  │ longpress │ │ 星云捕获  │ │ OODA 闭环 │ │ 60fps 同步│ │
│  │ drag rel  │ │ 凸透镜    │ │ 元规则    │ │           │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├────────────────────────────────────────────────────────┤
│  Agent 智能层 — 多组件协同                             │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐              │
│  │Pipeline │ │MusicAgent│ │LLMAutonomous│              │
│  │5-stage  │ │ReAct loop│ │proactive   │              │
│  └─────────┘ └──────────┘ └────────────┘              │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐              │
│  │ Persona │ │VisualAgent│ │ Federation │              │
│  │Engine   │ │rule gov.  │ │ rule exch. │              │
│  └─────────┘ └──────────┘ └────────────┘              │
├────────────────────────────────────────────────────────┤
│  数据层 — 记忆 + 规则 + 偏好                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │ L2 短期   │ │ L3 偏好   │ │ L4 长期   │              │
│  │ 行为事件  │ │ 用户画像  │ │ 播放历史  │              │
│  └──────────┘ └──────────┘ └──────────┘              │
├────────────────────────────────────────────────────────┤
│  集成层                                                │
│  Kimi(k2.5) · Spotify · NetEase · ElevenLabs · 天气   │
└────────────────────────────────────────────────────────┘
```

---

## 二、交互层 — 粒子物理引擎

### 2.1 粒子系统参数

| 参数 | 值 |
|------|-----|
| POOL_SIZE | 800 |
| COLUMN_COUNT | 100（均匀分布，间距 16px） |
| TRAIL_ALPHA | 0.08 |
| SPRING_CONSTANT | 0.12（列位回复力） |
| REPEL_PADDING | 40px |
| FPS 熔断 | <30fps 关闭绕流/偏转/搜索物理，保留拖尾+lerp |

### 2.2 9 大物理系统

| # | 系统 | 描述 |
|---|------|------|
| 1 | 列弹簧 | `homeX` 锚定 + `(offsets) × 0.12` 回复力，绕流时自动放行 |
| 2 | 卡片绕流 | 上方预判分叉 + 侧方径向排斥 120/(dist+1) + 底部衰减 |
| 3 | Lerp 颜色过渡 | 跨 mood 0.03 / 同 mood 0.08，RGB 线性插值 |
| 4 | 内核放大 | 粒子穿过内核半径内 `size *= 1.5`，白光点+三层辉光 |
| 5 | 三层光爆 | 0ms 纯白 / 100ms 情绪色 / 200ms 暗波，力场 80/(dist+1) |
| 6 | 子弹时间 | 50px=5% ~ 600px=60% 时间梯度，拖拽粒子，recoveryAlpha 恢复 |
| 7 | 旋转音量 | 内核 10-80px 环带切向力，弧形指示器 |
| 8 | 搜索布朗球 | 150px 吸力 → 球壳约束 → 布朗运动 → 坍缩爆发 → 恢复力 |
| 9 | 凸透镜折射 | 子弹时间内折射率场 n(r)=1+0.5×(1-r/R)，向心弯曲+RGB 三通道色散 |

### 2.3 附加系统

| 系统 | 描述 |
|------|------|
| 星云捕获 (Nebula) | 长按拖拽收集粒子 → 释放生成歌单 |
| Matrix Code Rain | 三层视差深度、垂直亮度渐变、核心辉光 |
| 音频-粒子同步 | bass(0-340Hz)→速度+拖尾, mid(340-1400Hz)→饱和度, treble(1400-4100Hz)→振幅微抖 |
| 自适应节拍检测 | bass 超过历史均值×1.5 触发 beat 脉冲 |
| E/W/D 形状映射 | energy/warmth/density → swirl/pulse_ring/star/drop/bloom/hexagon/circle/diamond |

### 2.4 全手势交互

| 手势 | 触发条件 | 功能 | 粒子反馈 |
|------|---------|------|---------|
| 右划卡片 | 30px 横向 | 切歌 | deflection → 光爆 → 新歌 |
| 双击内核 | 350ms 内两次 tap | 子弹时间 | 时间梯度 + 拖拽 + 折射 |
| 内核+旋转 | 400ms 无移动 | 音量旋钮 | 切向力跟随手指 |
| 长按内核 | 600ms 无移动 | 搜索 | 布朗球 + 坍缩爆发 |
| 内核拖拽释放 | drag → release | 氛围推荐 | 释放到 warm/cool/energy/calm 区域 |
| Ctrl+H | — | 隐藏播放器 | 卡片+内核消失 |
| / | — | 聚焦聊天框 | — |

### 2.5 空闲时间梯度

| 等级 | 时间 | 行为 |
|------|------|------|
| 0 | 0-3min | 正常活跃 |
| 1 | 3-10min | 轻微衰减 |
| 2 | 10-20min | 明显减速 |
| 3 | 20-40min | 深度休眠 |
| 4 | 40min+ | 极静模式 |

夜间 (23-5h)：起点 level 2，10min 后进入 level 3+。

---

## 三、Agent 智能层

### 3.1 Agent 模块总览 (10 个模块)

| 模块 | 文件 | 职责 |
|------|------|------|
| Pipeline | `agent/pipeline.py` | 5 阶段流水线编排 |
| Perception | `agent/perception.py` | 环境感知（时间、天气、上下文） |
| Router | `agent/router.py` | 路由分发（direct / reasoning / plan） |
| Reasoner | `agent/reasoner.py` | Plan-and-Solve 推理 + atmosphere JSON |
| Providers | `agent/providers.py` | LLM 提供商注册与切换 |
| Tools | `agent/tools.py` | 工具注册与执行 |
| Feedback | `agent/feedback.py` | WebSocket 推送 + 快照构建 |
| MusicAgent | `agent/music_agent.py` | 单职责音乐推荐工作者 (ReAct loop) |
| VisualAgent | `agent/visual_agent.py` | 粒子规则治理（评分/归档/合并/冲突） |
| LLMAutonomous | `agent/llm_autonomous.py` | 自主行为（主动发言/FOIA/禁言） |
| PersonaEngine | `agent/persona.py` | 人格引擎（漂移/否决/Phillips Curve） |

### 3.2 5 阶段 Pipeline

```
User Input → Perception → Router → Reasoner → Tools → Feedback
```

**Perception** — 接收用户消息、获取环境上下文（时间、天气、空闲状态）

**Router** — 三种路由模式：
- `direct` — 显式命令（play/pause/stop/next/prev/volume）
- `plan` — 简单查询（天气之类），不经过 LLM
- `reasoning` — 自然语言，进入 Reasoner

**Reasoner** — Plan-and-Solve 三段式推理。加载 `prompts/dj-persona.md` 和 `user/color-map.json`。LLM 返回 JSON：

```json
{
  "intent": "music_recommendation",
  "reasoning": "Plan → Solve → Review",
  "response": "自然语言回复",
  "actions": [],
  "atmosphere": {
    "tag": "calm_focus",
    "color": "#27AE60",
    "speed": 0.6,
    "density": 0.3,
    "amplitude": 0.05
  }
}
```

**Tools** — 11 个注册工具：`get_local_songs`, `search_music`, `get_weather`, `check_history`, `get_lyrics`, `get_current_song`, `get_playlist`, `get_recommendations`, `get_l2_summary`, `get_l3_profile`

**Feedback** — WebSocket `/stream` 推送 `state_snapshot`（song + playlist + is_playing + agent_log + atmosphere + core_action）

### 3.3 PersonaEngine

人格三位一体参数：`energy`, `warmth`, `playfulness`。随时间自然漂移，用户交互修正。

**否决机制** — 低 energy 时阻止高能动作：
- energy < 0.25 时 `light_burst` 被否决 → 替代为 `breath`
- energy < 0.15 时 `set_shape` 被否决
- `set_color` 豁免（低能仍需色彩）

**Phillips Curve Trade-off** — 任一维度超过 0.8 时，自动衰减其他维度：
- energy > 0.8 → warmth -0.003
- warmth > 0.8 → playfulness -0.002
- playfulness > 0.8 → energy -0.002

### 3.4 VisualAgent — 规则治理

负责管理粒子 DSL 规则的生命周期：

| 元规则 | 场景 | 行为 |
|--------|------|------|
| 死规则归档 | hits=0 + inactive + 27h+ | 标记 `_archived: true` |
| 合并候选 | 多条规则 target 相同 | 标记 `_merge_candidate` |
| 冲突降级 | 同一 target 矛盾操作 | 低 priority 停用 + `_conflict_with` |
| 评分计算 | 每条规则 | hits × freshness × active |
| 天气联动 | rain → 降 speed | 自动调整 |

### 3.5 LLMAutonomous — 自主行为

- **主动发言** — LLM 决定是否在无提示时说话
- **FOIA 审计** — 每条发言记录 type/reason/message
- **节流** — 30min 内最多说 1 次
- **禁言机制** — 发言后 120s 无交互 → dismissed+1：
  - dismissed=2 → 禁言 2h
  - dismissed=3 → 禁言 6h
- **用户交互后** — dismissed 重置为 0

### 3.6 Reverse Embodiment (反向具身化)

用户拖拽内核释放 → 释放位置决定 zone (warm/cool/energy/calm) → 映射为音乐推荐 prompt → 推送 `/api/chat` → 切歌 + 换氛围

---

## 四、数据层 — 记忆与规则

### 4.1 三层记忆系统

| 层级 | 模块 | 存储 | 内容 |
|------|------|------|------|
| L2 短期 | `memory/short_term.py` | 内存 + state_store | 最近 30 天行为事件、每日摘要 |
| L3 用户偏好 | `memory/user_profile.py` | JSON 持久化 | 艺术家/流派偏好强度、行为模式 |
| L4 长期 | `memory/history.py` | JSONL 文件 | 完整播放/交互历史 |

**L2→L3 蒸馏** — 每 24h 自动运行，从 L2 摘要提取长期偏好模式

**偏好衰减** — 切歌 → L3 偏好 weaken（正常切歌 -0.03，URL 失效 -0.05）

### 4.2 DSL 规则引擎 (particle-rules.js)

Agent 输出 JSON 规则编程粒子行为：

```json
{
  "id": "agent_1712345678",
  "source": "agent",
  "when": {"type": "time_gt", "val": "23:00"},
  "then": [{"target": "speed", "op": "mult", "val": 0.7}],
  "endWhen": {"type": "time_gt", "val": "05:00"}
}
```

5 条系统预置规则：夜间降速、空闲减速、切歌余震、密度熔断、日光渐变。

**OODA 闭环** — 前端 `engine.onRuleFeedback` → WebSocket `core_event` → 后端 _rule_feedback_cache → LLM 评估规则健康

### 4.3 情绪-颜色映射 (color-map.json)

| 标签 | 颜色 | 速度 | 密度 | 振幅 | 用途 |
|------|------|------|------|------|------|
| joyful | #E6C200 | 1.3 | 0.7 | 0.3 | 开心/兴奋 |
| melancholy | #756BB1 | 0.7 | 0.4 | 0.1 | 忧郁/共情 |
| calm_focus | #27AE60 | 0.6 | 0.3 | 0.05 | 平静/工作 |
| energetic | #00D4AA | 1.8 | 0.9 | 0.5 | 运动/派对 |
| night_calm | #1A5B3A | 0.5 | 0.2 | 0.03 | 深夜安静 |
| rainy_introspect | #5B7FA5 | 0.9 | 0.6 | 0.08 | 雨天内省 |

---

## 五、联邦规则交换

- `GET /api/rules/export` — 导出全部规则（匿名化）
- `POST /api/rules/import` — 导入外部规则：
  - 去重（按 when 条件）
  - 外来规则 score × 0.7（观察期）
  - 保留 `_source: "federated"` 标签

---

## 六、后台协程

FastAPI `startup` 事件启动 3 个后台循环：

| 协程 | 周期 | 职责 |
|------|------|------|
| `_atmosphere_loop` | 10s | 时间/天气感知 → 人格漂移 → VisualAgent 规则管理 → LLM 主动发言 |
| `_distill_loop` | 1h | L2→L3 蒸馏（需 ≥5 条当日事件） |
| `_persist_loop` | 5min | 会话状态持久化 |

---

## 七、数据流

```
用户输入 → Perception(Router) → Reasoner(LLM) → atmosphere JSON + rules JSON
              ↓
        Pipeline.run() → 整合
              ↓
        feedback.push_snapshot(atmosphere={...}, core_action={...})
              ↓
        WebSocket → ws-client.js → wsClient.onSnapshot
              ↓
        engine.updateParams → 粒子颜色/速度/密度 lerp 过渡
              ↓
        particleRules.evaluate() → 持续影响粒子行为

反向路径 (OODA):
  前端 rule_feedback → WebSocket → _rule_feedback_cache
              ↓
  VisualAgent._manage_rules → 归档/合并/冲突降级

交互路径:
  手势 → 前端粒子响应 + sendCoreEvent
              ↓
  WebSocket → 后端状态变更 → L2 记录 → L4 记录 → snapshot 回推

反向具身化:
  内核拖拽释放 → zone 判定 → /api/chat → 推荐 → 切歌 + 氛围切换
```

---

## 八、集成层

| 服务 | 模块 | 功能 |
|------|------|------|
| Kimi API | `integrations/kimi_integration.py` | LLM 对话 + 推荐 + 歌单命名 |
| Spotify | `integrations/spotify_integration.py` | 搜索/推荐/曲库管理 |
| 网易云音乐 | `integrations/netease_integration.py` | 搜索/播放URL获取/导入 |
| ElevenLabs | `integrations/elevenlabs_integration.py` | TTS 语音合成 |
| 天气 API | `core/scene_aware_engine.py` | 实时天气 → 氛围调整 |

---

## 九、测试架构

40 个测试，全部通过。

| 类别 | 数量 | 框架 |
|------|------|------|
| Smoke (端到端) | 16 | httpx + ASGI transport |
| PersonaEngine | 8 | 单元测试 |
| VisualAgent | 6 | 单元测试 |
| LLMAutonomous | 6 | 单元测试 |
| Federation | 4 | 集成测试 |

覆盖：pipeline 全路径、Router 三模式、MusicAgent ReAct loop、DSL 规则生成、偏好衰减、OOB 边界、空歌单、事件完整性。

---

## 十、创新点

1. **Agent 具身化** — AI 不以对话框形态存在，而以粒子流生命体存在于屏幕中央
2. **手势 → 物理 → Agent 闭环** — 用户操作的不是 UI 按钮，而是 Agent 的身体物理互动
3. **情绪可视化** — LLM atmosphere JSON 直接驱动 800 个粒子的速度/颜色/密度
4. **粒子记忆指纹** — 每个粒子的交互历史编码用户行为模式
5. **DSL 规则 + OODA** — Agent 用 JSON 规则持续编程粒子行为，前端回传规则健康数据
6. **音频-粒子闭环** — Agent 选的歌反过来控制粒子的物理行为
7. **三层记忆 + 蒸馏** — 短期行为自动沉淀为长期偏好
8. **反向具身化** — 用户对 Agent 身体的物理操作被翻译为音乐请求
9. **联邦规则交换** — 多实例之间匿名共享规则，互相学习
