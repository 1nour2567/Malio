# Malio 测试报告

## 概览

| 类别 | 测试数 | 通过 | 失败 |
|------|--------|------|------|
| Smoke tests (httpx + ASGI) | 16 | 16 | 0 |
| PersonaEngine 单元测试 | 8 | 8 | 0 |
| VisualAgent 单元测试 | 6 | 6 | 0 |
| Federation 集成测试 | 4 | 4 | 0 |
| LLMAutonomous 单元测试 | 6 | 6 | 0 |
| **总计** | **40** | **40** | **0** |

---

## 核心模块覆盖矩阵

| 模块 | 单元测试 | 集成测试 | 覆盖状态 |
|------|---------|---------|---------|
| Pipeline (5-stage) | — | ✅ httpx | ✅ |
| Router (Plan/Agent/YOLO) | — | ✅ httpx | ✅ |
| Reasoner (prompt + JSON) | — | ✅ httpx | ✅ |
| MusicAgent (ReAct loop) | — | ✅ httpx | ✅ |
| VisualAgent (_manage_rules) | ✅ 元规则 | — | ✅ |
| VisualAgent (_score_rule) | ✅ 评分 | — | ✅ |
| PersonaEngine (veto) | ✅ 否决+替代 | — | ✅ |
| PersonaEngine (Phillips Curve) | ✅ trade-off | — | ✅ |
| PersonaEngine (save) | ✅ 持久化 | — | ✅ |
| LLMAutonomous (event queue) | ✅ 事件完整性 | — | ✅ |
| LLMAutonomous (proactive speech) | ✅ 发言+FOIA | — | ✅ |
| LLMAutonomous (dismissal) | ✅ 禁言逻辑 | — | ✅ |
| L3 (preference weaken) | ✅ 偏好衰减 | — | ✅ |
| Federation (export/import) | — | ✅ httpx | ✅ |
| state_manager (playlist) | ✅ OOB/empty | — | ✅ |
| WebSocket (stream) | — | ❌ 未测 | ❌ |
| 并发请求 | — | ❌ 未测 | ❌ |
| 100+ 规则性能 | — | ❌ 未测 | ❌ |
| malformed input 恢复 | — | ❌ 未测 | ❌ |

---

## 1. Smoke Tests（`tests/test_smoke.py`）

16 个 httpx + ASGI transport 集成测试，每次运行约 2-3 分钟。

| # | 测试 | 覆盖模块 |
|---|------|---------|
| 1 | `test_root_health` | FastAPI 启动 |
| 2 | `test_chat_recommend_returns_songs` | Pipeline + MusicAgent + Reasoner |
| 3 | `test_chat_chat_does_not_crash` | Router + Pipeline |
| 4 | `test_skip_advances_queue` | state_manager.next_in_queue |
| 5 | `test_recommendations_have_required_fields` | Pipeline + Reasoner |
| 6 | `test_react_hard_stop` | MusicAgent ReAct loop |
| 7 | `test_dsl_rule_generation` | Pipeline + DSL rule extraction |
| 8 | `test_plan_weather` | Router Plan mode |
| 9 | `test_chat_history_accumulates` | state_manager chat history |
| 10 | `test_selected_song_id_consistency` | Pipeline + structured output |
| 11 | `test_skip_weakens_preference` | L3 user profile |
| 12 | `test_set_playlist_oob_index_clamped` | set_playlist OOB fix |
| 13 | `test_set_playlist_empty_songs` | set_playlist empty |
| 14 | `test_set_playlist_zero_songs_index_clamped` | set_playlist zero |
| 15 | `test_llm_auto_events_not_lost` | LLMAutonomous event queue |
| 16 | `test_persona_drift_triggers_save` | PersonaEngine save |

---

## 2. PersonaEngine（单元测试）

### Veto → Alternative

| # | 输入 | 条件 | 输出 | 结果 |
|---|------|------|------|------|
| 1 | `light_burst` | energy=0.25 | `breath`（否决替代） | ✅ |
| 2 | `set_shape(star)` | energy=0.15 (deep sleep) | `breath`（强转为极浅呼吸） | ✅ |
| 3 | `set_color` | energy=0.15 | `set_color`（豁免，低能仍允许） | ✅ |
| 4 | 任意动作 + 否决 | — | `_veto_log` 记录 {vetoed, alternative, reason} | ✅ |

### Phillips Curve Trade-off

| # | 输入 | 条件 | 预期 | 结果 |
|---|------|------|------|------|
| 1 | e=0.82, w=0.50, p=0.50 | energy > 0.8 | warmth 减少 0.003 | ✅ |
| 2 | e=0.50, w=0.82, p=0.50 | warmth > 0.8 | playfulness 减少 0.002 | ✅ |
| 3 | e=0.50, w=0.50, p=0.82 | playfulness > 0.8 | energy 减少 0.002 | ✅ |
| 4 | e=0.70, w=0.70, p=0.70 | 全部低于阈值 | 无 trade-off（仅 drift delta） | ✅ |

---

## 3. VisualAgent（单元测试）

### Rule Scoring

| # | 场景 | 输入 | 分数 | 结果 |
|---|------|------|------|------|
| 1 | 高命中规则 | hits=47, active=true, recent | 1.0 | ✅ |
| 2 | 死规则 | hits=0, active=false, 27h+ old | 0.0 | ✅ |

### Meta-Rules（通过 `_manage_rules` 测试）

| # | 元规则 | 场景 | 预期 | 结果 |
|---|--------|------|------|------|
| 1 | 死规则归档 | hits=0 + inactive + 27h+ | `_archived: true` | ✅ |
| 2 | 合并候选 | 3 条 rules target=speed | 每条标 `_merge_candidate: [ids]` | ✅ |
| 3 | 冲突降级 | speed mult=0.5 (pri=1) vs mult=1.5 (pri=2) | 低 priority 停用 + `_conflict_with` | ✅ |
| 4 | 评分计算 | 2 条规则 | 每条带分数 | ✅ |

### Color Utilities

| # | 场景 | 输入 | 预期 | 结果 |
|---|------|------|------|------|
| 1 | 冷色检测 | `#0044FF` | true | ✅ |
| 2 | 暖色检测 | `#FF4400` | false | ✅ |
| 3 | 暖色转换 | `#0044FF` | r↑ b↓ | ✅ |

---

## 4. LLMAutonomous（单元测试）

### Event Queue

| # | 场景 | 预期 | 结果 |
|---|------|------|------|
| 1 | 快速 push 5 个事件 | 全部入队，单 reactor | ✅ |
| 2 | busy 时 push | 事件累积不丢失 | ✅ |

### Proactive Speech

| # | 场景 | 预期 | 结果 |
|---|------|------|------|
| 1 | LLM 决策 say=true | agent_log 推送消息 | ✅ |
| 2 | FOIA audit trail | `_speech_log` 含 type/reason/message | ✅ |
| 3 | 30min 节流 | 连续两次调用只有第一次发言 | ✅ |

### Dismissal Suppression

| # | 场景 | 输入 | 预期 | 结果 |
|---|------|------|------|------|
| 1 | 发言后 >120s 无交互 | `_last_speak_time` + 130s | `consecutive_dismissed += 1` | ✅ |
| 2 | 连续 2 次被忽视 | dismissed=2 | `_speak_suppress_until` = now + 7200s (2h) | ✅ |
| 3 | 连续 3 次被忽视 | dismissed=3 | `_speak_suppress_until` = now + 21600s (6h) | ✅ |
| 4 | 用户交互后 | `push(label, detail)` | `consecutive_dismissed` 重置为 0 | ✅ |

---

## 5. Federation（集成测试）

| # | 场景 | 预期 | 结果 |
|---|------|------|------|
| 1 | `GET /api/rules/export` | 200 + rules 列表 | ✅ |
| 2 | `POST /api/rules/import` 新规则 | imported=1, `_source: federated` | ✅ |
| 3 | 重复规则 (同 when 条件) | duplicates=1 | ✅ |
| 4 | 导入规则降分 | score *= 0.7 | ✅ |

---

## 已知限制

- **未测试 WebSocket** — 无 WS 集成测试（前端依赖浏览器环境）
- **未测试并发** — 单线程 ASGI transport，无竞态测试
- **未测试大量规则** — 100+ 规则时的 manage_rules 性能未知
- **未测试 malformed input** — 异常路径恢复未覆盖
- **LLM 依赖** — `test_chat_recommend_returns_songs` 偶尔因 LLM 超时 flaky

---

**测试日期**: 2026-05-18
**测试环境**: Python 3.11.5 + httpx ASGI transport + DeepSeek/Kimi LLM
