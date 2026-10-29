# Malio 完整开发记录 — 2026-05-15~16

## 核心问题

**"说的≠放的"**：AI 口头推荐的歌和实际播放的歌不是同一首。
**"切不了歌"**：歌放完或右划手势后，音频不更新。

## 根因

系统里没有播放队列的**单一真相源**。数据在四个地方各自存了一份互不相同——LLM 脑子里的歌、推荐引擎的歌、前端 state、后端 playback_state。

---

## 第一天：修复"说≠放"（6 处）

| # | 位置 | 做了什么 |
|---|------|---------|
| 1 | `main.py` `_react_loop` | Phase 1 tool results 收集进 `all_songs`，注入 `_react_songs` |
| 2 | `reasoner.py` format_obj | response 字段加 `"CRITICAL: never mention specific song titles"` |
| 3 | `main.py` Stage 4 | 优先用 `_react_songs`，只有音乐意图且没歌时才 fallback |
| 4 | `main.py` Stage 5 | 实际歌名 `🎵 稻香 — 周杰伦` 放口播文本最前面 |
| 5 | `reasoner.py` + `main.py` | `selected_song_id`：LLM 输出歌 ID，系统按 ID 精确定位 |
| 6 | `main.py` + `app.js` | 歌曲补全 `audio_path`/`preview_url` + `_enrich_songs` |

## 第二天：切歌链路 + 同步（4 处）

| # | 位置 | 做了什么 |
|---|------|---------|
| 7 | `main.py` WebSocket | `song_skip` 队列为空时自动从 DB 加载 |
| 8 | `app.js` `nextSong` | 前端本地立刻切歌，不等后端 |
| 9 | `app.js` + `main.py` | `sync_playlist` 前后端歌单同步 |
| 10 | `main.py` `get_state` | 返回真实 playback_state，不再永远推空的 |

## 第三天：四个边缘情况 + 五层防御

| # | 位置 | 做了什么 |
|---|------|---------|
| 11 | `main.py` `_react_loop` | 统一字段出口，所有路径返回完整 schema |
| 12 | `app.js` `onSnapshot` | `_seq` 版本号拒绝过期 snapshot，防 ABA |
| 13 | `ws-client.js` | 消息队列 `sendGuaranteed` + TTL 30s + 上限 100 |
| 14 | `app.js` + `main.py` | 30s 心跳 + 后端一致性纠正 |
| 15 | `main.py` Stage 4 | 闲聊时 `_react_songs` 空 → 不换歌 |
| 16 | `app.js` `refreshExpiredUrl` | 刷新 URL 失败 → 自动 nextSong |
| 17 | `main.py` + `reasoner.py` | 对话历史 `chat_history` 注入 prompt |

### 五层防御体系

```
第一层：_react_loop 统一字段补全 → 所有路径返回完整字段
第二层：_react_songs + selected_song_id → 说的歌跟播的歌同一来源
第三层：_seq 版本号 → 拒绝过期 snapshot，防 ABA 快速切歌回跳
第四层：消息队列 + sendGuaranteed → WebSocket 没连上不丢同步消息
第五层：30s 心跳 + 后端一致性检查 → 所有防御都失效后 30s 内自动纠正
```

## 第四天：架构改进

| # | 位置 | 做了什么 |
|---|------|---------|
| 18 | `main.py` `StateStore` | JSON 文件持久化：playback_state + core_events + chat_history |
| 19 | `main.py` | 启动时 restore 上次会话，每 5 分钟 auto-save |
| 20 | `main.py` WebSocket | 切歌实时削弱 L3 偏好（artist + genre） |
| 21 | `main.py` | 30s 内连切 2+ 次 → push "方向可能需要调整" |

## 第五天：人格系统

### PersonaEngine — 三维人格空间

```
energy (0-1)      → 0=安静慵懒  1=亢奋活跃
warmth (0-1)      → 0=冷淡疏离  1=亲切热情
playfulness (0-1) → 0=严肃克制  1=爱玩随性
```

### 五个机制，五个论文来源

| 机制 | 论文来源 | 做了什么 |
|------|---------|---------|
| **随机初始化** | Takata et al. 2024 | 首次启动三维度随机 0.3-0.7，每个 Malio 不一样 |
| **结构性约束** | Mooney et al. 2025 的批判 | energy<0.3 → 光爆和子弹时间被删掉，不是 prompt 建议 |
| **P-GEM 氛围推导** | Kovacevic et al. 2025 | atmosphere = f(persona × time)，不经过 LLM |
| **GLA 漂移** | Majumder 2025 | 每个核心交互微调 persona，所有变化记录在 traceable log |
| **基线回归** | 自研 | 向 baseline 重力拉回，防漂到极端 |

### 关键设计决策

**行为约束是结构性的，不是 prompt 文本。**

```
energy=0.25 → constrain_core_actions() 删除 light_burst
             → LLM 想发光爆也发不出来
             → 不是一个 prompt 说"你能量低，少发光爆"
```

### 人格漂移链路

```
用户切歌 → drift_from_interaction("song_skip")
  → energy -= 0.01, warmth -= 0.004
  → _drift_log: {"reason":"用户切歌","from":"e0.523 w0.604 p0.512","to":"e0.513 w0.600 p0.512"}

30 分钟自然漂移 → drift_natural(hour)
  → 深夜: energy 微降
  → 清晨: energy 微升
  → 任何时候: 向基线回归
```

### 氛围推导（P-GEM 模式）

```
atmosphere = f(persona, time)
  energy=0.7 → speed 偏高 (0.78)
  playfulness=0.3 → density 偏低 (0.42)
  warmth=0.8 → brightness 偏高 (0.80)
  time=morning → tag=joyful

不经过 LLM，不查 color-map.json
```

---

## 创新总结

| 创新 | 级别 | 说明 |
|------|------|------|
| **Agent 具身化** | A 级 | atmosphere + core_actions 直接驱动 800 粒子 |
| **手势 → 物理 → Agent 闭环** | B+ 级 | 用户操作的是 Agent 身体，不是 UI 按钮 |
| **DSL 规则引擎** | B 级 | Agent 输出 JSON 规则持续编程粒子行为 |

三个创新任何一个单独拎出来，都不是工程修补级别的。今天修的所有东西，是在给这三个搭不崩的基础设施。

---

## 文件变更

| 文件 | 类型 |
|------|------|
| `malio/main.py` | 重度修改（+~250 行） |
| `malio/agent/reasoner.py` | 修改 5 处 |
| `malio/agent/persona.py` | **新文件**（180 行） |
| `malio/agent/feedback.py` | 修改 `build_snapshot`，加 seq |
| `frontend/src/app.js` | 修改 7 处 |
| `frontend/src/ws-client.js` | 加 `sendGuaranteed` + 消息队列 |

## 当前 Malio Agent 知识覆盖度

```
✓ 5 阶段流水线
✓ Plan-and-Solve 推理
✓ ReAct（简化版，Phase 1 tool-call + Phase 2 生成）
✓ 工具注册制（类 MCP，8 个工具）
✓ L2/L3/L4 三层记忆
✓ 记忆蒸馏自动化
✓ 偏好衰减 + 确认队列
✓ 结构化输出强制（selected_song_id）
✓ 五层防御体系
✓ 状态 JSON 持久化
✓ 实时负反馈 → L3 偏好削弱
✓ 对话历史注入
✓ 人格引擎（结构性约束 + P-GEM 氛围推导 + GLA 漂移 + 随机初始化）
✗ 真 ReAct 多轮循环（仍是 1+1）
✗ 语义向量检索（L3 仍是 key-match）
✗ 会话检查点（方案写了，未实现）
✗ DSL 规则引擎 Agent 自主生成（仍是 5 条预置）
✗ Plan/Agent/YOLO 三模式（Router 只做了一半）
```

---

## Day 6～7: 颜色系统 + 粒子同步 + 测试

| # | 位置 | 做了什么 |
|---|------|---------|
| — | `particles.js` | 粒子渲染从硬编码绿色改为 atmosphere 颜色驱动（`_rr/_gg/_bb`） |
| — | `particles.js` | 透镜渐变从 `rgba(34,197,94,...)` 改为动态色 |
| — | `particles.js` | 颜色 lerp 平滑过渡（`params.color` → `_targetParams.color`） |
| — | `app.js` | 切歌 700ms 延迟 → 1s 渐变，粒子和星云同步 |
| — | `app.js` | 四源加权混合：氛围45%、FFT频谱40%、封面10%、随机5% |
| — | `app.js` | E/W/D → HSL 色相环映射（能量→色相、温暖→饱和、密度→亮度） |
| — | `nebula.js` | 星云引擎引用 `_targetParams.color`，统一色调 |
| — | `state_manager.py` | `query_local_songs` 补全 E/W/D + album_art |
| — | `audio_analyzer.py` | 批量 FFT 分析 100 首歌 E/W/D（零 LLM） |

---

## Day 7: ReAct 优化 + 测试补充

| # | 位置 | 做了什么 |
|---|------|---------|
| — | `pipeline.py` | ReAct 硬停：Round 1 ≥5 首歌 → 跳过后续轮次直接 Phase 2 |
| — | `tests/test_smoke.py` | 新增 6 个测试（硬停/DSL规则/Plan天气/对话记忆/selected_song_id/切歌减弱） |
| — | `tests/` | 全量 17/17 pass，2:21 |
| — | 网易云 API | `npx NeteaseCloudMusicApi` 本地启动 :3000 |
| — | `providers.py` | DeepSeek 主 / Kimi 备 |

---

## 最终架构覆盖度

```
✓ 5 阶段 Pipeline (Perception→Router→Reasoner→Tools→Feedback)
✓ 真 ReAct 多轮 + 硬停优化 (≤2 轮)
✓ ToolRegistry 注册制 (类 MCP, 10 个工具)
✓ 多 Provider 抽象 (DeepSeek/Kimi, 自动 fallback)
✓ L2/L3/L4 三层记忆 + 自动蒸馏
✓ 偏好衰减 + 确认队列
✓ 结构化输出 (selected_song_id)
✓ 五层防御体系 (字段→_react_songs→_seq→队列→心跳)
✓ 状态持久化 + 多用户隔离
✓ 实时负反馈 (切歌→L3削弱)
✓ 对话历史注入
✓ 人格引擎 (P-GEM + GLA + 结构性约束 + 自主行为)
✓ P-GEM 氛围推导 (persona × time → atmosphere)
✓ 天气混合 (blend_weather, 论文支撑)
✓ DSL 规则生成 + WebSocket 推送
✓ 会话检查点 (/api/session/resume)
✓ 网易云 API 集成
✓ 100 首歌 FFT 音频分析 (E/W/D)
✓ HSL 色相环颜色系统 (四源加权)
✓ 17 个自动化测试
✓ 完整架构文档
```

## 文件变更—新增/重度修改

| 文件 | 类型 |
|------|------|
| `malio/main.py` | 重度修改 |
| `malio/agent/pipeline.py` | **重写**（350→450 行） |
| `malio/agent/persona.py` | 新文件（350 行） |
| `malio/agent/reasoner.py` | 修改 15 处 |
| `malio/core/state_manager.py` | **重写**（多用户） |
| `malio/core/metrics.py` | 新文件 |
| `malio/memory/user_profile.py` | 语义检索 + 情境匹配 |
| `frontend/src/particles.js` | **重写**颜色系统 |
| `frontend/src/particles/nebula.js` | 引擎颜色同步 |
| `frontend/src/app.js` | **重度修改**颜色/渐变/混合 |
| `frontend/src/ws-client.js` | Vite 绕过 + 多用户 |
| `tests/test_smoke.py` | 11→17 个测试 |
