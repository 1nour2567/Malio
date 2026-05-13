# Malio 音乐代理 - 启动说明

## 📋 项目概述

Malio 是一款智能音乐代理，支持：
- 🎵 智能音乐推荐（基于 Kimi API）
- 🔍 网易云音乐搜索与播放
- 🎤 ElevenLabs 语音合成（TTS）
- 💬 自然语言对话交互

---

## 🛠️ 环境要求

### 必需软件

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 后端运行环境 |
| Node.js | 18+ | 前端运行环境 |
| npm | 9+ | 前端包管理器 |

---

## ⚙️ 首次配置

### 1. 配置环境变量

复制配置文件：

```powershell
cd malio
copy .env.example .env
```

编辑 `malio/.env` 文件，填入您的 API Key：

```env
# ===== Kimi API (必需) =====
KIMI_API_KEY=your_kimi_api_key_here

# ===== ElevenLabs API (TTS 功能必需) =====
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# ===== 网易云音乐 API (可选) =====
NETEASE_API_URL=http://localhost:3000
NCM_COOKIE=your_netease_cookie_here

# ===== CORS 设置 =====
CORS_ORIGINS=http://localhost:5173,http://localhost:8000,http://127.0.0.1:5173
```

### 2. 获取 API Key

| 服务 | 获取地址 | 免费额度 |
|------|----------|----------|
| Kimi API | https://platform.moonshot.cn/ | 有免费额度 |
| ElevenLabs | https://elevenlabs.io/app/settings/api-keys | 10,000 字符/月 |
| 网易云音乐增强版 API | https://github.com/owenowl/NeteaseCloudMusicApi (自行部署) | 免费 |

---

## 🚀 启动服务

### 方式一：手动启动

#### 第一步：安装依赖

```powershell
cd malio

# 创建虚拟环境（首次）
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate

# 安装 Python 依赖
pip install -r requirements.txt
```

#### 第二步：启动后端服务

```powershell
# 在 malio 目录下，确保虚拟环境已激活
python main.py
```
后端将在 http://localhost:8007 运行

#### 第三步：启动前端服务

```powershell
# 新开一个终端窗口

# 1. 进入前端目录
cd frontend

# 2. 安装依赖（如首次运行）
npm install

# 3. 启动前端 (端口 5173)
npm run dev
```

### 第四步：访问网页

打开浏览器访问：**http://localhost:5173**

---

## 📡 API 端点

### 核心端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/recommend` | GET | 获取音乐推荐 |
| `POST /api/chat` | POST | 与 Malio 对话 |
| `GET /api/library/stats` | GET | 获取本地库统计 |

### 网易云音乐端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/netease/search` | GET | 搜索歌曲 |
| `GET /api/netease/track/{id}/url` | GET | 获取播放链接 |
| `POST /api/netease/add-to-library` | POST | 添加到本地库 |
| `GET /api/netease/hot` | GET | 获取热门歌曲 |
| `GET /api/netease/new` | GET | 获取新歌榜 |

### TTS 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /api/tts/speak` | POST | 文字转语音 |
| `GET /api/tts/voices` | GET | 获取音色列表 |

### 请求示例

```bash
# 搜索歌曲
curl "http://localhost:8007/api/netease/search?query=周杰伦&limit=10"

# TTS 语音合成
curl -X POST "http://localhost:8007/api/tts/speak" \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，我是 Malio！", "voice_id": "CwhRBWXzGAHq8TQ4Fs17"}' \
  --output output.mp3

# 与 Malio 对话
curl -X POST "http://localhost:8007/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"input": "推荐一些中文歌曲"}'
```

---

## 🎵 功能说明

### 智能推荐
- Malio 会根据当前时间和场景推荐合适的音乐
- 支持自然语言对话，如"推荐一些轻松的音乐"

### 网易云音乐搜索
- 点击右上角搜索图标
- 输入歌曲名或歌手名搜索
- 支持添加到本地音乐库

### 语音合成（TTS）
- Malio 的回复会自动用语音播放
- 点击喇叭图标可开启/关闭语音
- 下拉框可选择不同音色

### 本地音乐库
- 点击右上角设置图标
- 查看和管理本地音乐
- 支持手动添加/删除歌曲

---

## 🔧 常见问题

### 1. 端口被占用

```
Error: [Errno 10048] address already in use
```

解决方法：使用其他端口或关闭占用程序

```powershell
# 查看端口占用
netstat -ano | findstr :8007

# 关闭进程（PID 替换为实际值）
taskkill /PID <PID> /F
```

### 2. 模块导入错误

```
ModuleNotFoundError: No module named 'xxx'
```

解决方法：安装缺失的依赖

```powershell
cd malio
pip install -r requirements.txt
```

### 3. TTS 无法获取音色列表

```
missing_permissions: The API key you used is missing the permission voices_read
```

解决方法：在 ElevenLabs 仪表盘中创建一个具有 `voices_read` 权限的新 API Key

### 4. 前端无法连接后端

```
ECONNREFUSED
```

解决方法：确保后端服务已启动，并检查 `vite.config.js` 中的代理配置

### 5. 网易云音乐无法播放

检查项：
1. 网易云 API 服务是否启动（端口 3000）
2. Cookie 是否配置正确
3. Cookie 是否过期（重新登录获取）

---

## 📁 项目结构

```
AI_music-master/
├── malio/                    # 后端目录
│   ├── config/
│   │   └── config.py           # 配置文件
│   ├── core/
│   │   ├── device_control.py   # 设备控制
│   │   ├── recommendation_engine.py  # 推荐引擎
│   │   └── scene_aware_engine.py    # 场景感知
│   ├── data/
│   │   ├── history/             # 播放历史
│   │   ├── playlists/          # 播放列表
│   │   └── songs/              # 歌曲数据
│   ├── integrations/
│   │   ├── elevenlabs_integration.py  # ElevenLabs TTS
│   │   ├── kimi_integration.py         # Kimi API
│   │   └── netease_integration.py      # 网易云音乐
│   ├── models/
│   │   └── music.py            # 数据模型
│   ├── venv/                   # Python 虚拟环境
│   ├── main.py                 # FastAPI 入口
│   └── .env                    # 环境变量（勿提交）
│
├── frontend/                   # 前端目录
│   ├── src/
│   │   ├── App.jsx            # 主应用组件
│   │   ├── SongManager.jsx   # 歌曲管理组件
│   │   ├── index.css          # 样式文件
│   │   └── main.jsx           # 前端入口
│   ├── vite.config.js         # Vite 配置
│   └── package.json           # 前端依赖
│
├── .gitignore                 # Git 忽略文件
└── README.md                  # 项目说明
```

---

## 📄 许可证

本项目仅供学习和研究使用。请遵守各第三方服务的使用条款。
