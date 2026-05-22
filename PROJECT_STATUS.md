# Malio AI Music 项目状态分析

**分析时间**: 2026-05-18
**Git 仓库**: 已初始化，12 commits

---

## 一、项目结构概览

```
├── malio/                  ← 后端（FastAPI + agent 系统）
│   ├── agent/              ← 10 个 agent 模块
│   ├── core/               ← 推荐引擎、场景感知、状态管理
│   ├── integrations/       ← Kimi / NetEase / Spotify / ElevenLabs
│   ├── memory/             ← L2 短期 / L3 偏好 / L4 长期
│   ├── config/             ← 配置管理
│   ├── data/               ← 数据导入
│   ├── models/             ← SQLAlchemy 数据模型
│   ├── tests/              ← 40 个测试（16 smoke + 24 单元）
│   └── main.py             ← FastAPI 入口（1314 行，含全部路由）
├── frontend/               ← 前端（vanilla JS/CSS 零框架）
│   └── src/
│       ├── app.js          ← 主逻辑（2031 行）
│       ├── particles.js    ← 粒子系统
│       ├── particle-rules.js ← DSL 规则引擎
│       ├── ws-client.js    ← WebSocket 客户端
│       ├── audio-analyzer.js ← 音频分析
│       ├── color-extractor.js ← 封面颜色提取
│       └── particles/
│           └── nebula.js   ← 星云粒子
├── docs/superpowers/
│   ├── specs/              ← 4 个设计规范文档
│   └── plans/              ← 阶段计划
├── prompts/
│   └── dj-persona.md       ← DJ 人格定义
├── user/
│   └── color-map.json      ← 情绪→颜色映射
├── malio.db                ← SQLite 数据库
├── CLAUDE.md
├── MALIO_ARCHITECTURE.md
└── TEST_REPORT.md           ← 测试报告
```

---

## 二、Git 提交历史

```
87387d4 fix: playlist delete + nebula capture + confirm bar
22e4695 feat: Agent jurisdiction + proactive speech + rule governance
2c7c9f2 feat: aliveness — core animation overhaul + rule OODA loop
1feafb0 feat: reverse embodiment + nebula capture optimization
dce6937 feat: embodiment v0.3 — shapes, beat pulse, ripples, LLM autonomous, bug fixes
4f6ce4e feat: Malio v2.0 — Multi-Agent Embodied AI Music System
7f39685 fix: idle timer wake-up transition always 30s due to assignment order
791105f feat: L2 short-term memory + swipe rework
7ba3edd fix: recommendation engine missing audio_path and preview_url
8cb69e7 fix: playlist songs not playable due to innerHTML stripping event listeners
6d1d42b feat: audio reactivity + particle rules DSL + core state machine
73a7c3b Phase A-C: E/W/D classification + particle nebula + memory corridor
```

---

## 三、当前开发阶段（已完成以 ✅ 标记）

### Agent 系统

| 组件 | 状态 |
|------|------|
| 5 阶段 Pipeline (Perception → Router → Reasoner → Tools → Feedback) | ✅ |
| Router (Plan / Agent / YOLO 三种模式) | ✅ |
| Reasoner (Plan-and-Solve + atmosphere JSON) | ✅ |
| ToolRegistry (11 个注册工具) | ✅ |
| Feedback (WebSocket 推送 + 快照) | ✅ |
| MusicAgent (单职责音乐工作者) | ✅ |
| VisualAgent (规则管理 + 评分 + 合并 + 冲突检测) | ✅ |
| PersonaEngine (人格漂移 + 否决 + Phillips Curve) | ✅ |
| LLMAutonomous (主动发言 + FOIA 审计 + 节流 + 禁言) | ✅ |

### 记忆系统

| 层级 | 状态 |
|------|------|
| L2 短期记忆 (行为事件 + 摘要) | ✅ |
| L3 用户偏好 (偏好衰减 + 强化 + 蒸馏) | ✅ |
| L4 长期历史 (播放记录持久化) | ✅ |

### 粒子引擎 (frontend)

| 系统 | 状态 |
|------|------|
| 列弹簧 + 绕流 + 轨迹 | ✅ |
| 核心动画 (呼吸环 + 拖拽回弹) | ✅ |
| 三层光爆仪式 | ✅ |
| 子弹时间 (双击) | ✅ |
| 搜索布朗球 (长按) | ✅ |
| 旋转音量 (内核环带) | ✅ |
| 音频-粒子同步 (三频段) | ✅ |
| E/W/D 颜色映射 + 形状切换 | ✅ |
| 空闲时间梯度 (5 级衰减) | ✅ |
| 凸透镜折射 | ✅ |
| Matrix Code Rain 三层视差 | ✅ |
| 星云捕获 → 歌单生成 | ✅ |

### 交互

| 手势 | 状态 |
|------|------|
| 右滑切歌 | ✅ |
| 双击内核 → 子弹时间 | ✅ |
| 长按内核 → 搜索 | ✅ |
| 内核拖拽释放 → 推荐 (反向具身化) | ✅ |
| Ctrl+K 搜索 / H 隐藏 / / 聊天 | ✅ |

### 联邦与规则

| 功能 | 状态 |
|------|------|
| DSL 规则引擎 (particle-rules.js) | ✅ |
| Agent 生成 JSON 规则 | ✅ |
| 元规则管理 (归档/合并/冲突降级) | ✅ |
| OODA 闭环 (前端规则反馈 → LLM) | ✅ |
| 联邦规则交换 (export/import) | ✅ |

### 集成

| 服务 | 状态 |
|------|------|
| Kimi API (LLM) | ✅ |
| 网易云音乐 (搜索/播放/导入) | ✅ |
| Spotify (搜索/推荐) | ✅ |
| ElevenLabs (TTS) | ✅ |
| 天气场景感知 | ✅ |
| 设备控制 | ✅ |

### 测试

| 类别 | 数量 | 通过 |
|------|------|------|
| Smoke tests (httpx + ASGI) | 16 | 16 |
| PersonaEngine 单元 | 8 | 8 |
| VisualAgent 单元 | 6 | 6 |
| LLMAutonomous 单元 | 6 | 6 |
| Federation 集成 | 4 | 4 |
| **总计** | **40** | **40** |

---

## 四、已知限制

- WebSocket 未测（依赖浏览器环境）
- 并发请求未测（单线程 ASGI transport）
- 100+ 规则性能未知
- 畸形输入恢复路径未覆盖
- LLM 依赖导致部分测试偶发 flaky
- `main.py` 1314 行，`app.js` 2031 行，单文件偏大
- 文档更新滞后于代码迭代

---

## 五、下一步建议

| 优先级 | 事项 | 原因 |
|--------|------|------|
| 1 | 拆分 `main.py` 路由到独立模块 | 可维护性 |
| 2 | `app.js` 模块化 (ES modules) | 可维护性 |
| 3 | 补 WebSocket 集成测试 | 测试覆盖完整性 |
| 4 | 并发测试 | 生产就绪 |
