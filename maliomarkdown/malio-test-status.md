# Malio 测试状态 — 2026-05-17

## 已测 ✓ (17/17)

| 测试 | 结果 | 备注 |
|------|------|------|
| 推荐链路 | ✓ | `🎵 歌名 — 歌手` + 播放一致 |
| 闲聊不换歌 | ✓ | intent=general_chat 时歌单不动 |
| 右划切歌 | ✓ | 队列前进，粒子光爆 |
| 连续快速切歌 | ✓ | agent_log "方向可能需要调整" |
| 对话记忆 | ✓ | chat_history 注入生效 |
| 粒子 atmosphere | ✓ | 四源加权混合变色 |
| 内核自主行为 | ✓ | 每30s随机breath/move/变色 |
| Plan 模式 | ✓ | 天气/曲库秒回不调LLM |
| Plan 天气 | ✓ | 温度、体感、风速、能见度、日出日落 |
| 网易云搜歌 | ✓ | NeteaseCloudMusicApi 本地运行 |
| ReAct 早停 | ✓ | ≥5首歌→1轮结束 |
| 多用户隔离 | ✓ | session 文件各自独立 |
| 重启恢复 | ✓ | 歌单/对话/队列全部恢复 |
| 会话检查点 | ✓ | `/api/session/resume` 欢迎回来 |
| DSL 规则生成 | ✓ | "以后暗一点" → rule 存入+推送 |
| 粒子颜色跟随歌曲 | ✓ | HSL 映射 E/W/D → 色相环 |
| 歌 404 路径修复 | ✓ | 20首歌路径补全 |

## 架构级验证

| 能力 | 状态 |
|------|------|
| 5 阶段管线 | ✓ test_agent_pipeline (6个) |
| ReAct 硬停 | ✓ test_react_hard_stop |
| DSL 规则 | ✓ test_dsl_rule_generation |
| Plan 天气 | ✓ test_plan_weather |
| 对话记忆 | ✓ test_chat_history_accumulates |
| selected_song_id | ✓ test_selected_song_id_consistency |
| 切歌减弱偏好 | ✓ test_skip_weakens_preference |
| 推荐返回歌曲 | ✓ test_chat_recommend_returns_songs |
| 闲聊不换歌 | ✓ test_chat_chat_does_not_crash |
| 切歌队列前进 | ✓ test_skip_advances_queue |
| 歌曲字段完整 | ✓ test_recommendations_have_required_fields |

## 已知限制

| 问题 | 严重度 | 说明 |
|------|--------|------|
| ElevenLabs 欠费 | 低 | TTS 不能用，不影响核心功能 |
| ReAct 仍 2 次 API 调用 | 低 | 硬停只减了工具轮数，Phase 2 LLM 仍需调 |
| L3 语义检索 | 低 | jieba + context metadata，非向量检索 |
| 30 人 A/B 测试 | 论文级 | 需要被试 |
| YOLO 模式 | 未触发 | "全部/所有/批量" 关键词 |
| 飞书/日程集成 | 未接 | config 有但未启用 |
