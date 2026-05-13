# CLAUDE.md — Claudio AI Music Project

## About the user

- 大一学生，数据科学与大数据技术专业
- 偏好命令行操作
- Python 为主，前端 HTML/CSS/JS
- 国内网络环境，部分外网服务需代理

## Project: Claudio AI 音乐电台

AI 驱动的私人音乐 DJ，FastAPI 后端 + 原生 PWA 前端。

- 后端入口：`malio/main.py`（端口 8007）
- 前端入口：`frontend/index.html`（端口 5173）
- AI 引擎：Kimi API（kimi-k2.5）
- TTS：ElevenLabs
- 音乐源：网易云音乐 API

## 关键文件

- `malio/main.py` — FastAPI 全部路由
- `malio/integrations/kimi_integration.py` — Kimi API 调用
- `malio/integrations/netease_integration.py` — 网易云搜索与播放
- `malio/config/config.py` — 配置管理
- `frontend/src/app.js` — 前端全部逻辑
- `frontend/src/style.css` — 深色 OLED 主题样式

## 用户偏好

- 回复简洁，不要废话
- 代码不加注释，除非逻辑非显而易见
- 不做未要求的重构
- 用中文交流

## Skills 使用要求

以下是本项目常用 skills，在相应场景下必须主动调用 Skill 工具（不要等用户提醒）：

| 场景 | 必须调用的 Skill |
|------|-----------------|
| 遇到 bug / 报错 / 行为异常 | `systematic-debugging` |
| 写新功能前 / 设计 UI / 选风格配色 | `ui-ux-pro-max` |
| 需求不明确需要先讨论 | `brainstorming` |
| 大型多步骤任务 | `make-plan` → 用户确认后 `do` |
| 写完代码声称完成前 | `verification-before-completion` |
| 收到代码审查反馈 | `receiving-code-review` |
| 审查自己的改动 | `simplify` |
| 写 UI 组件 / 调整样式 | `ui-styling` |
| 日常写代码 | `karpathy-guidelines` |

**重要**：Skills 由 Claude 主动调用（Skill 工具），不是让用户在飞书里输入 `/skill-name`。
