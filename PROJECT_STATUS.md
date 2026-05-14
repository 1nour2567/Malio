# Malio AI Music 项目状态分析

**分析时间**: 2026-05-13
**注意**: 项目无 git 仓库，以下基于文件修改时间和内容对比分析。

---

## 一、项目结构概览

```
├── malio/              ← 当前后端（活跃开发中）
├── malio_new/          ← 后端快照（5/12 17:05，已过时）
├── frontend/           ← 当前前端（活跃开发中）
├── frontend_new/       ← 前端快照（5/12 17:05，已过时）
├── docs/superpowers/   ← 设计文档
├── prompts/            ← AI prompt 模板
├── user/               ← 用户配置
├── CLAUDE.md
├── MALIO_ARCHITECTURE.md
└── START.md
```

**关键发现**: `_new` 目录是 5/12 下午的快照，真正的开发继续在 `malio/` 和 `frontend/` 中进行。当前版本已经比快照版本多了大量改动。

---

## 二、5月12日 ~ 13日 主要改动（按时间线）

### 2.1 前端粒子系统 — 重大重构

| 时间 | 文件 | 变更 |
|------|------|------|
| **5/13 02:34** | `frontend/src/particles.js` (30KB) | 最新的 Matrix Code Rain 实现，3 层深度视差、垂直亮度渐变、核心辉光 |
| **5/12 17:43** | `frontend/src/particles/engine.js` (10KB) | **新增** — 模块化粒子引擎：512 粒子池、100 列网格、绕流物理、FPS 故障保护 |
| 5/12 23:47 | `frontend/src/style.css` (19.4KB) | OLED 深色主题，设计 Token 系统 |
| 5/12 23:38 | `frontend/index.html` (8.9KB) | 全屏播放器布局，粒子 canvas 背景，顶部栏 + 播放器卡片 |

**架构演进**: 粒子系统从单文件 `particles.js` 拆分为模块化结构 `particles/engine.js`（为后续拆分为 core.js、physics.js、gestures.js、effects.js、render.js 做准备）。

`particles/engine.js` 已实现:
- 512 粒子池 + 100 可变间距列
- 列弹簧物理（粒子恢复列 X 位置）
- 绕流（flow-around）+ 消散（dissipation）
- 轨迹 + 角色循环
- FPS 故障保护（<30fps 禁用绕流）

### 2.2 前端 app.js — 主逻辑更新

| 时间 | 文件 | 大小 |
|------|------|------|
| **5/13 02:00** | `frontend/src/app.js` | 41.8KB |
| 5/12 17:05 | `frontend_new/src/app.js` | 58.8KB |

当前版本比快照版本**小 17KB**，说明进行了精简重构。保留了核心状态管理、面板系统、WebSocket 通信。

### 2.3 后端 Agent 系统 — reasoner 增强

| 文件 | 变更 |
|------|------|
| `malio/agent/reasoner.py` | 新增加载 `prompts/dj-persona.md` + `user/color-map.json` |

reasoner 现在会自动加载 DJ 人格提示词和色彩映射配置，提供给 LLM 作为 atmosphere 输出的参考。

### 2.4 新增文件

| 文件 | 用途 | 时间 |
|------|------|------|
| `prompts/dj-persona.md` (2.5KB) | Malio DJ 人格定义：5 条硬性规则、6 种 atmosphere 标签、色彩转场原则、回复语气规范 | 5/12 09:13 |
| `user/color-map.json` (1.4KB) | 情绪→颜色映射：joyful/melancholy/calm_focus/energetic/night_calm/rainy_introspect，含时间规则 | 5/12 09:12 |
| `docs/superpowers/specs/2026-05-12-malio-particle-body.md` (7.2KB) | 粒子身体架构设计：核心状态机、手势系统、特效编排、信息编码 | 5/12 17:31 |
| `docs/superpowers/specs/2026-05-12-matrix-depth.md` (4.3KB) | 矩阵深度系统：双层视差、垂直亮度渐变、核心局部辉光 | 5/12 18:28 |
| `docs/superpowers/specs/2026-05-12-core-expression.md` (4.5KB) | 核心表达系统：呼吸环、拖拽情绪回弹、音量/进度暂态环 | 5/12 20:33 |

### 2.5 音乐文件下载

5/12 23:22 ~ 23:31 下载了 **12 首歌曲**（MP3/FLAC），总大小约 105MB：

| 文件 | 大小 |
|------|------|
| 椎名林檎 - 17.mp3 | 10.4MB |
| 周杰伦 - 龙卷风.mp3 | 9.6MB |
| 周杰伦 - 给我一首歌的时间.mp3 | 9.7MB |
| 周杰伦 - 爱在西元前.mp3 | 8.9MB |
| 周杰伦 - 反方向的钟.mp3 | 9.8MB |
| 周杰伦 - 你听得到.mp3 | 8.8MB |
| Terror Squad - Take Me Home.mp3 | 8.1MB |
| Ray Saetta - Somehow.mp3 | 7.0MB |
| MC Sniper - 夜间飞行.flac | 25.5MB |
| Kid Cudi - Maui Wowie.mp3 | 5.5MB |

---

## 三、当前开发阶段总结

按照 `malio-particle-body.md` 中定义的 **10 阶段计划**：

| 阶段 | 内容 | 状态 |
|------|------|------|
| 1 | engine.js — 列雨 + 绕流 + 轨迹 | **已完成** |
| 2 | core.js — 屏幕中心空闲点 | 规划中 |
| 3 | gestures.js — 右滑切歌 | 规划中 |
| 4 | effects.js — 三重光爆仪式 | 规划中 |
| 5 | 歌曲信息覆盖层 | 规划中 |
| 6 | 滚轮音量控制 | 规划中 |
| 7 | physics.js — 子弹时间 | 规划中 |
| 8 | 长按搜索球 | 规划中 |
| 9 | 核心状态机 (thinking/speaking/error) | 规划中 |
| 10 | Atmosphere 自动推送 + 颜色渐变 | 规划中 |

**当前进度**: 阶段 1 完成，准备进入阶段 2+3。

---

## 四、三个 Spec 文档的关系

```
matrix-depth.md     → 粒子渲染层的空间深度（背景层 + 前景层 + 亮度 + 辉光）
    ↓ 依赖
malio-particle-body.md → 粒子作为 AI 身体的完整交互系统（手势 + 特效 + 信息编码）
    ↓ 扩展
core-expression.md  → 核心透镜的表情系统（呼吸环 + 拖拽 + 暂态环）
```

三个 spec 层层递进：先有深度系统，再有身体交互，最后是核心表情。
