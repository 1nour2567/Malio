# Malio — AI 粒子具身音乐 Agent

## 一句话

Malio 不是带粒子背景的播放器——**是以粒子为身体的 AI 生命体**。内核是 Agent 的身体，粒子流是它的情绪表达，手势是与它的物理对话。

Spotify AI DJ 和 YouTube Music 的推荐都是纯 UI 的——推荐结果出现在屏幕上，用户点一下播放。Malio 是唯一一个**让 AI 拥有物理身体**的音乐 Agent：Agent 的情绪、人格、推理过程全部通过视觉行为外显。用户和 Agent 的对话不经过对话框——经过手势和物理反馈。

### Malio 与传统音乐 Agent 的对比

| | 对话式 Agent | 推荐引擎式 Agent | **Malio** |
|---|------------|---------------|-----------|
| **交互方式** | 文字聊天 | 按钮 + 推荐卡片 | 手势 + 粒子物理反馈 |
| **状态表达** | 文字描述（"我推荐……"） | 无——只推结果 | 颜色/速度/内核模式/光爆 |
| **记忆** | 上下文窗口内的对话 | 播放历史统计 | L2 实时 + L3 蒸馏 + L4 不可变日志 |
| **人格** | System prompt 写死 | 不存在 | 三维连续参数 + 结构性约束 + 自主漂移 |
| **自主性** | 完全被动响应 | 被动响应 | 主动行为：呼吸/漂移/变色/光爆 |

---

## 核心创新

### 1. Agent 具身化——让 Agent 有身体

LLM 不以对话框形态存在。Agent 通过三层递进控制视觉行为：

| 层级 | 机制 | 说明 |
|------|------|------|
| atmosphere | 情绪标签 → 粒子颜色/速度/密度 | 一次性情绪，即时生效 |
| core_actions | LLM 输出动作指令（光爆/呼吸/内核切换/位移） | 主动表达，不等用户输入 |
| DSL 规则 | Agent 生成的持久规则（when/then/endWhen） | 跨会话生效，Agent 编程自己的身体 |

用户不看文字就知道 Agent 在想什么：推理时旋转（vortex），回答时稳定（dot），出错时变红（error）。**Agent 还有自主行为**——即使无人交互，它也会根据人格参数（energy/warmth/playfulness）自己呼吸、变色、微移内核。像活物，不像程序。

**这不是"创意编程"。** 具身化解决的是 Agent 交互范式的根本问题：LLM 的内部状态（推理过程、信心水平、情绪变化）对于用户是不可见的。对话式 Agent 只能通过文字描述自己的状态——具身化 Agent 直接用身体表达。视觉通道比文字通道带宽高几个数量级。

**学术基础**：P-GEM (Kovacevic et al. 2025) 联合人格-情绪模型、GLA (Majumder 2025) 人格漂移框架、Takata et al. (2024) 性格从交互中涌现、Mooney et al. (2025) LLM 行为一致性批判。

### 2. 手势 → 物理 → Agent 闭环

用户不操作 UI 按钮。五种手势直接与 Agent 内核交互：

| 手势 | 触发 | 功能 | 粒子反馈 |
|------|------|------|---------|
| 右划卡片 | 30px 横向滑动 | 切歌 | deflection → 三层光爆 |
| 双击内核 | 350ms 内两次 tap | 子弹时间 | 时间梯度 + 拖拽粒子 |
| 内核 + 旋转 | 触摸旋转 | 音量调节 | 切向力环带 |
| 长按内核 | 600ms 长按 | 搜索 | 布朗球 + 坍缩爆发 |
| Ctrl+H | 键盘 | 隐藏播放器 | 卡片消失 |

每次交互回传 WebSocket → Agent 感知到"用户碰了我的身体" → 记录到记忆系统。

### 3. DSL 规则引擎——Agent 自我编程

Agent 输出的不只是一次性动作，还能生成持久规则：

```json
{
  "id": "agent_1716123456",
  "when": {"type": "time_gt", "val": "22:00"},
  "then": [{"target": "brightness", "op": "mult", "val": 0.5}],
  "endWhen": {"type": "time_gt", "val": "06:00"},
  "note": "用户要求晚上暗一点"
}
```

规则有生命周期（startWhen/endWhen）、支持多种条件（time_gt/lt、idle_gt、event、audio）、每帧评估。Agent 最多同时持有 3 条活跃规则，系统预设规则优先级更高。规则重启不丢失（持久化到 StateStore）。

---

## 架构

```
malio/agent/
├── pipeline.py      ← 5 阶段管线 + 真 ReAct + DSL 规则管理 + metrics
├── persona.py       ← 三维人格引擎（P-GEM + GLA + 结构性约束）
├── reasoner.py      ← prompt 组装 + 结构化输出强制（selected_song_id）
├── router.py        ← Plan/Agent/YOLO 三模式路由
├── tools.py         ← ToolRegistry 注册制（类 MCP）
├── feedback.py      ← WebSocket 广播 + DSL 规则推送
├── providers.py     ← 多 Provider 抽象（DeepSeek 主 / Kimi 备）
└── perception.py    ← 环境感知 + 时间槽

malio/core/
├── state_manager.py ← 播放队列 + 事件缓冲 + 会话持久化
├── metrics.py       ← CSV 量化指标
└── recommendation_engine.py ← 情境化推荐

malio/memory/
├── short_term.py    ← L2：24h 行为快照 + 每小时自动摘要
├── user_profile.py  ← L3：蒸馏画像 + 偏好衰减 + 确认队列
└── history.py       ← L4：不可变追加日志（SHA256 校验）

tests/
└── test_smoke.py    ← 5 个端到端冒烟测试
```

---

## 核心特性

### 真 ReAct 多轮推理

不是一次性 tool-call + 生成。LLM 在最多 3 轮中自主决策：每轮观察上一轮的工具结果，决定继续搜索还是生成回复。搜不到换关键词重试，全失败时系统硬兜底 + LLM 诚实告知。

### 结构化输出强制

`selected_song_id` 字段让 LLM 不编歌名——输出歌曲 ID，系统按 ID 精确查找。口播文本（TTS）和播放队列永远一致。解决了 AI Agent"说的≠放的"这一核心痛点。

### 五层防御体系

| 层级 | 机制 | 防止什么 |
|------|------|---------|
| 1 | `_react_loop` 统一字段出口 | 任何路径返回完整 schema |
| 2 | `_react_songs` + `selected_song_id` | 说的歌跟播的歌同一来源 |
| 3 | `_seq` 版本号 | 过期 snapshot 被拒，防 ABA 快速切歌回跳 |
| 4 | 消息队列 `sendGuaranteed` | WebSocket 未连时不丢同步消息 |
| 5 | 30s 心跳 + 后端一致性纠正 | 所有防御失效后自动同步 |

### 三层记忆系统

| 层 | 存储 | 容量 | 更新方式 |
|----|------|------|---------|
| L2 短期 | 24h 行为事件 | 2000 条 | 实时追加 + 每小时摘要 |
| L3 长期 | 蒸馏结论（偏好/行为/情绪/规则） | 结构化 JSON | 每日蒸馏 + 事件驱动衰减 |
| L4 永久 | 原始事件日志 | 按日分片 | 追加不修改 + SHA256 校验 |

L3 偏好使用 MARS 风格操作：reinforce（强化）/ weaken（削弱）/ decay（衰减）/ queue_confirmation（确认队列）。

### 三维人格引擎

```
energy (0-1)      → 0=安静慵懒  1=亢奋活跃
warmth (0-1)      → 0=冷淡疏离  1=亲切热情
playfulness (0-1) → 0=严肃克制  1=爱玩随性
```

人格不是 prompt 文本——是结构性约束。`energy<0.3` → LLM 输出的 `light_burst` 被直接过滤，不是"建议少用"。漂移有三个来源：自然节律（每小时微调）、交互扰动（切歌降 energy）、基线回归（向中性拉回）。

### 实时负反馈

切歌瞬间 → L3 偏好削弱（artist -0.03, genre -0.03）→ 30s 内连切 2+ 首 → Agent 被告知"方向可能需要调整" → 下次推荐自动避开被跳过的歌手。

### 跨会话持久化

歌单、对话历史、Agent 规则、人格状态全部 JSON 持久化。服务重启后自动恢复——用户感知不到中断。

---

## 量化指标系统

每轮 chat 写入 CSV：`ts, intent, react_rounds, song_count, had_songs, auto_play, input_has_recommend, ...`

攒一周数据 → `pandas.read_csv("data/metrics.csv")` → 三张图：
- 推荐接受率（had_songs / 推荐请求数）
- 平均 ReAct 轮数（LLM 效率）
- 闲聊 vs 推荐占比

就是论文的 Evaluation 章节。

---

## 测试

```
11 passed in 55s
├── 6 个 Agent 管线单元测试
└── 5 个端到端冒烟测试
    ├── GET /health → 200
    ├── 推荐返回 response + recommendations
    ├── 闲聊不崩
    ├── 切歌队列前进
    └── 歌曲有 id/title/artist + 可播源
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI (Python) + SQLAlchemy + SQLite |
| Agent | 自研 5 阶段管线 + ReAct 循环 |
| LLM | DeepSeek V4 Flash（主）、Kimi K2.5（备） |
| 前端 | Vanilla HTML5/CSS/JS + Vite + PWA |
| 粒子 | Canvas 2D + 800 粒子 + 100 列阵 + 9 大物理系统 |
| 通信 | WebSocket + 类型化消息（state_snapshot / rule / agent_log） |
| 音频 | 网易云音乐 API + ElevenLabs TTS |

---

## 下一步

**30 人 A/B 用户测试**：具身化 Malio vs 纯文字对话版（相同后端，去掉粒子和手势交互），测量推荐接受率、切歌频率、交互满意度。这是将原型推向论文的最后一个环节——量化指标系统已就绪，只差被试数据。

---

## 作者与学术背景

**宋浩诚**，大一，数据科学与大数据技术专业。

研究方向为 AI 人格建模与具身化 Agent 交互。相关学术探索包括：与 Noson S. Yanofsky 教授（《The Outer Limits of Reason》作者，Brooklyn College, CUNY）的学术通信，以及在 LLM 行为一致性、Agent 长记忆架构等领域的研究积累。Malio 是将这些理论基础——人格建模（P-GEM, GLA）、长期记忆蒸馏、结构化输出约束——工程化为可运行系统的尝试。
