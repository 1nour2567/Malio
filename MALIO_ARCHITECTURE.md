# Malio — AI Particle-Embodied Music Agent

## 核心命题

如果 AI agent 有身体，它应该怎样存在于人类的屏幕里？

Malio 的回答：**内核是 agent 的身体，粒子流是它的环境，手势是与它的对话，DSL 规则是它的学习能力。**

不是"带粒子背景的播放器"，而是"以粒子为身体的 AI 生命体"。

---

## 三层架构

```
┌─────────────────────────────────────────────┐
│  交互层 — 手势 + 粒子物理                    │
│  ┌─────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ 手势识别 │ │ 粒子引擎  │ │ 内核渲染     │  │
│  │ swipe    │ │ 800粒子  │ │ 光点/涡旋    │  │
│  │ rotate   │ │ 100列阵  │ │ 折射/色散    │  │
│  │ tap×2    │ │ 9大系统  │ │ 冲击波       │  │
│  │ longpress│ │          │ │ 搜索球       │  │
│  └─────────┘ └──────────┘ └─────────────┘  │
├─────────────────────────────────────────────┤
│  Agent 智能层 — 5 阶段流水线                 │
│  Perception → Router → Reasoner → Tools → Feedback │
├─────────────────────────────────────────────┤
│  数据层 — 记忆 + 规则 + 偏好                 │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │粒子记忆   │ │ DSL规则  │ │ 用户偏好    │  │
│  │localStor │ │5条内置   │ │color-map   │  │
│  │800条日志  │ │Agent生成 │ │persona提示  │  │
│  └──────────┘ └──────────┘ └────────────┘  │
└─────────────────────────────────────────────┘
```

---

## 一、交互层 — 粒子物理引擎

### 粒子系统参数

| 参数 | 值 |
|------|-----|
| POOL_SIZE | 800 |
| COLUMN_COUNT | 100（均匀分布，间距 16px） |
| TRAIL_ALPHA | 0.08 |
| SPRING_CONSTANT | 0.12（列位回复力） |
| REPEL_PADDING | 40px |
| FPS 熔断 | <30fps 关闭绕流/偏转/搜索物理，保留拖尾+lerp |

### 9 大物理系统

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

### 字符集

日文片假名 + 平假名 + 日汉字 + 中文常用 + 希腊字母 + 俄语字母 + 英文数字

### 全手势交互

| 手势 | 触发条件 | 功能 | 粒子反馈 |
|------|---------|------|---------|
| 右划卡片 | 30px 横向 | 切歌 | deflection → 光爆 → 新歌 |
| Ctrl+H | — | 隐藏播放器 | 卡片+内核消失 |
| 双击内核 | 350ms 内两次 tap | 子弹时间 | 时间梯度 + 拖拽 + 折射 |
| 内核+旋转 | 400ms 无移动 | 音量旋钮 | 切向力跟随手指 |
| 长按内核 | 600ms 无移动 | 搜索 | 布朗球 + 坍缩爆发 |

---

## 二、Agent 智能层 — 5 阶段流水线

```
User Input → Perception → Router → Reasoner → Tools → Feedback
```

### Perception
接收用户消息、获取环境上下文（时间、天气）、加载用户偏好

### Router
显式命令直接执行（play/pause/stop/next/prev/volume），自然语言转入 Reasoner

### Reasoner
Plan-and-Solve 三段式 + atmosphere 输出。加载 `prompts/dj-persona.md` 和 `user/color-map.json`，要求 LLM 返回 JSON：

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

### Tools
Tool Registry 注册制：`search_music` / `get_weather` / `check_history`

### Feedback
- 构建 state_snapshot（song + playlist + is_playing + agent_log + atmosphere + tool_error）
- WebSocket `/stream` 推送
- `push_atmosphere_by_rules()` — 无 LLM 规则引擎，查 `color-map.json` 时段映射，每 30s 循环

### 后端协程

`@app.on_event("startup")` 启动 `asyncio.create_task(_atmosphere_loop())`，每 30s 根据时间自动推送 atmosphere

---

## 三、数据层 — 记忆与规则

### 粒子记忆系统

每个粒子携带 `{mem, memType}` 字段，记录被拖拽/光爆炸/内核穿越的次数。老兵粒子自动增亮（`+mem×0.05`）放大（`+mem×0.01`）。`localStorage` 持久化总交互计数。

### DSL 规则引擎（particle-rules.js）

Agent 可以输出 JSON 规则编程粒子行为：

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

规则每帧评估，支持：`time_gt/lt`、`idle_gt/lt`、`event`、`count_gt/lt`、`bass_gt/lt`、`day_in`。
动作支持：`set`、`mult`、`add`、`lerp_to`、`clamp`。
支持 `rampDown` 定时回退和 `endWhen` 终止条件。

### 情绪-颜色映射 (color-map.json)

| 标签 | 颜色 | 速度 | 密度 | 振幅 | 用途 |
|------|------|------|------|------|------|
| joyful | #E6C200 | 1.3 | 0.7 | 0.3 | 开心/兴奋 |
| melancholy | #756BB1 | 0.7 | 0.4 | 0.1 | 忧郁/共情 |
| calm_focus | #27AE60 | 0.6 | 0.3 | 0.05 | 平静/工作 |
| energetic | #00D4AA | 1.8 | 0.9 | 0.5 | 运动/派对 |
| night_calm | #1A5B3A | 0.5 | 0.2 | 0.03 | 深夜安静 |
| rainy_introspect | #5B7FA5 | 0.9 | 0.6 | 0.08 | 雨天内省 |

`_rules.time_of_day`：morning→joyful, afternoon→calm_focus, evening→joyful, 23-5h→night_calm

---

## 四、音频-粒子实时同步

`AudioAnalyzer` 封装 Web Audio API，提取三频段能量：
- bass (0-340Hz) → 粒子速度 + 拖尾拉长
- mid (340-1400Hz) → 颜色饱和度
- treble (1400-4100Hz) → 振幅微抖
- 自适应节拍检测（bass 超过历史均值×1.5 触发 beat）

---

## 五、数据流

```
用户输入 → Reasoner(LLM) → atmosphere JSON + rules JSON
              ↓
        feedback.push_snapshot(atmosphere={...})
              ↓
        WebSocket → ws-client.js
              ↓
        判断 tag 变/不变 → 选 lerp 速度
              ↓
        engine.updateParams → 粒子颜色/速度/密度 lerp 过渡

后台协程 → push_atmosphere_by_rules() → 查 color-map.json
              ↓
        同样推 atmosphere（低优先级，用户输入覆盖）

Agent 规则 → WebSocket → wsClient.onRule → particleRules.addRule()
              ↓
        每帧 evaluate() → engine.params 实时修改

音频 → AudioAnalyzer.analyze() → engine.setAudioData({bass,mid,treble,beat})
              ↓
        粒子速度/拖尾/密度 60fps 同步音乐
```

---

## 六、创新点

1. **Agent 具身化**：AI 不以对话框形态存在，而以粒子流生命体形态存在于屏幕中央
2. **手势 → 物理 → Agent 闭环**：用户操作的不是 UI 按钮，而是和 Agent 的身体进行物理互动
3. **情绪可视化**：LLM 输出的 atmosphere JSON 直接驱动 800 个粒子的速度/颜色/密度变化
4. **粒子记忆指纹**：每个粒子的交互历史编码了用户的行为模式，形成唯一视觉指纹
5. **DSL 规则引擎**：Agent 通过自然语言接收需求，输出 JSON 规则持续编程粒子行为，规则有生命周期自进化
6. **音频-粒子闭环**：Agent 选的歌反过来控制粒子的物理行为
