# Malio 启动指南

**最后更新**: 2026-05-20
**项目路径**: `C:\Users\m1916\Desktop\aimusic\AI_music-master`

---

## 一、项目概述

Malio 是一款具身 AI 音乐 Agent。与传统播放器不同，Malio 拥有 800 个粒子的物理身体，AI 的思考、情感、人格状态实时映射为粒子运动、颜色、光爆等可视化表达。

```
User Input → Perception → Router → Reasoner (ReAct Loop) → Tools → Feedback
                                                                    ↓
Frontend Particle Engine ← WebSocket ←── atmosphere / core_actions / rules
```

### 核心模块

| 层 | 技术 | 作用 |
|---|------|------|
| 后端 API | FastAPI (Python 3.10+) | REST + WebSocket 服务，端口 8007 |
| Agent 管线 | 5 阶段 Pipeline | 感知 → 路由 → 推理 → 工具调用 → 反馈 |
| LLM | Kimi K2.5 (主), DeepSeek V4 Flash (备) | 对话、推荐、DJ 文案生成 |
| 记忆系统 | SQLite + JSONL | L2 短期 / L3 偏好 / L4 永久日志 |
| 前端 | Vanilla JS + Vite + PWA | Canvas 2D 粒子引擎，端口 5173 |
| 音乐源 | 网易云音乐 API / Spotify / 本地文件 | 搜索、播放、导入 |
| TTS | ElevenLabs | Malio 语音合成 |

---

## 二、环境要求

| 软件 | 版本 | 检查命令 |
|------|------|----------|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

---

## 三、首次配置

### 3.1 克隆并进入项目

```bash
cd C:\Users\m1916\Desktop\aimusic\AI_music-master
```

### 3.2 配置 .env 文件

复制模板并编辑 `malio/.env`：

```bash
cd malio
copy .env.example .env    # 如无 .env.example，直接创建 .env
```

`.env` 必要字段：

```env
# ===== Kimi API (必需，LLM 对话与推荐) =====
KIMI_API_KEY=sk-your-kimi-api-key-here
KIMI_MODEL=kimi-k2.5
KIMI_API_BASE=https://api.moonshot.cn/v1/

# ===== ElevenLabs API (TTS 语音，可选) =====
ELEVENLABS_API_KEY=your-elevenlabs-api-key-here

# ===== 网易云音乐 API (可选，需自行部署 NeteaseCloudMusicApi) =====
NETEASE_API_URL=http://localhost:3000
NCM_COOKIE=your-netease-cookie-here

# ===== Spotify API (可选) =====
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret

# ===== DeepSeek API (可选，备选 LLM) =====
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# ===== CORS =====
CORS_ORIGINS=http://localhost:5173,http://localhost:8007

# ===== 数据库路径 (自动生成，一般不改) =====
DATABASE_URL=sqlite:///malio.db
```

**API Key 获取地址**：

| 服务 | 注册地址 | 免费额度 |
|------|----------|----------|
| Kimi (Moonshot) | https://platform.moonshot.cn/ | 有 |
| ElevenLabs | https://elevenlabs.io/app/settings/api-keys | 10,000 字符/月 |
| 网易云音乐 API | https://github.com/owenowl/NeteaseCloudMusicApi | 自部署，免费 |

### 3.3 安装 Python 依赖

```bash
cd malio

# 创建虚拟环境（仅首次）
python -m venv venv

# 激活虚拟环境
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows CMD:
venv\Scripts\activate.bat
# WSL / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

依赖清单：

```
fastapi>=0.115.0        # Web 框架
uvicorn>=0.30.0         # ASGI 服务器
pydantic>=2.10.0        # 数据验证
sqlalchemy>=2.0.0       # ORM
anthropic>=0.39.0       # Claude API (备用)
python-dotenv>=1.0.0    # 环境变量
requests>=2.31.0        # HTTP 客户端
```

### 3.4 安装前端依赖

```bash
cd frontend
npm install
```

---

## 四、导入本地音乐

项目自带 `import_local_music.py` 脚本，可将指定目录的 MP3/FLAC 文件导入数据库。

### 4.1 脚本工作原理

1. 扫描源目录所有 `.mp3` / `.flac` / `.m4a` / `.wav` / `.ogg` 文件
2. 从文件名解析 `Artist - Title` 格式
3. 跳过已存在的歌曲（按标题去重）
4. 复制音频文件到 `malio/data/audio/songs/`
5. 写入 SQLite 数据库

### 4.2 执行导入

```bash
cd malio
source venv/bin/activate    # 或 Windows: .\venv\Scripts\activate

# 确认脚本中的 MUSIC_DIR 路径正确
python -c "
import import_local_music
# MUSIC_DIR 默认为 /mnt/e/音乐
# 如需修改路径，直接编辑 import_local_music.py 第 5 行
"
```

### 4.3 验证导入结果

```bash
# 查看数据库歌曲数
curl http://localhost:8007/api/library/stats

# 响应示例：
# {"total_songs": 108, "analyzed_count": 100, "pending_analysis_count": 8, ...}
```

`analyzed_count` 低于 `total_songs` 是正常的——FFT 音频分析是懒加载的，首次播放时会自动分析。

---

## 五、启动服务

### 5.1 启动后端

```bash
cd malio

# 激活虚拟环境后
python main.py
```

成功标志：

```
[persona] loaded — e=0.86 w=0.28 p=0.71
Kimi API Key: Set
INFO:     Uvicorn running on http://0.0.0.0:8007
```

> **注意**: 虚拟机/WSL 中运行时，`host` 设为 `0.0.0.0` 才能从宿主机浏览器访问。

### 5.2 启动前端

```bash
cd frontend
npm run dev
```

成功标志：

```
VITE v5.4.21  ready in 754 ms
➜  Local:   http://localhost:5173/
```

### 5.3 访问

浏览器打开 `http://localhost:5173`

---

## 六、服务验证

### 6.1 后端健康检查

```bash
# 音乐库统计
curl http://localhost:8007/api/library/stats

# 推荐接口
curl "http://localhost:8007/api/recommend?mood=relaxed&limit=5"

# 聊天接口
curl -X POST http://localhost:8007/api/chat \
  -H "Content-Type: application/json" \
  -d '{"input": "推荐一首中文歌"}'

# 网易云搜索
curl "http://localhost:8007/api/netease/search?query=周杰伦&limit=5"
```

### 6.2 预期 API 端点一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/library/stats` | GET | 本地音乐库统计 |
| `/api/recommend` | GET | 获取推荐 |
| `/api/chat` | POST | 与 Malio 对话 |
| `/api/netease/search` | GET | 网易云搜索 |
| `/api/netease/hot` | GET | 热门歌曲 |
| `/api/netease/new` | GET | 新歌榜 |
| `/api/tts/speak` | POST | TTS 语音合成 |
| `/api/tts/voices` | GET | 可用音色列表 |
| `/api/import-data` | POST | 导入本地音乐数据 |
| `/api/rules/export` | GET | 导出 DSL 规则 |
| `/api/rules/import` | POST | 导入联邦规则 |
| `/ws` | WebSocket | 实时状态推送 |

### 6.3 前端验证

1. 打开 `http://localhost:5173`
2. 应看到 800 个粒子的动态背景
3. 核心 (core) 在屏幕中央呼吸
4. Ctrl+K 可搜索，`/` 可聊天
5. 右滑切歌

---

## 七、WSL 特殊说明

本项目代码位于 Windows 文件系统 (`C:\Users\m1916\Desktop\aimusic\`)，但通过 WSL 运行。

### 端口转发检查

WSL 默认将 `localhost` 端口转发到 Windows，无需额外配置。如果 Windows 浏览器无法访问 WSL 服务：

```bash
# WSL 内查看 IP
ip addr show eth0 | grep inet

# Windows PowerShell 中设置端口转发（一般不需要）
netsh interface portproxy add v4tov4 listenport=8007 listenaddress=0.0.0.0 connectport=8007 connectaddress=<WSL_IP>
```

### 路径注意事项

- `import_local_music.py` 使用 Linux 路径 `/mnt/e/音乐`
- `config.py` 中 `database_url` 使用 WSL 路径格式
- Windows 和 WSL 两边都能访问 `/mnt/c/...`

---

## 八、常见问题

### 端口被占用

```
ERROR: [Errno 98] Address already in use
```

```bash
# 查看端口占用
lsof -i :8007    # Linux/WSL
netstat -ano | findstr :8007    # Windows

# 终止占用进程
kill $(lsof -ti :8007)    # Linux/WSL
taskkill /PID <PID> /F    # Windows
```

### 前端无法连接后端

```
ECONNREFUSED http://localhost:8007/
```

检查项：
1. 后端是否已启动 (`python main.py`)
2. `vite.config.js` 中代理配置是否指向 `http://localhost:8007`
3. 防火墙是否放行 8007/5173

### 网易云音乐无法播放

检查项：
1. `NETEASE_API_URL` 指向的 API 服务是否已启动（默认 `http://localhost:3000`）
2. `NCM_COOKIE` 是否过期（重新登录获取）

### 模块导入错误

```
ModuleNotFoundError: No module named 'xxx'
```

```bash
cd malio
source venv/bin/activate    # 确保虚拟环境已激活
pip install -r requirements.txt
```

### TTS 音色列表为空

```
missing_permissions: The API key you used is missing the permission voices_read
```

在 ElevenLabs 控制台重新创建一个具有 `voices_read` 权限的 API Key。

### Spotify Token 400 错误

```
Error refreshing Spotify access token: 400 Client Error
```

Spotify Client ID / Secret 配置错误或已过期，需在 Spotify Developer Dashboard 重新获取。

> 此错误不影响核心功能（Kimi + 网易云 + 本地音乐均可独立工作）。

---

## 九、数据库说明

### 位置

`malio/malio.db` — SQLite 单文件数据库

### 核心表

| 表 | 内容 |
|----|------|
| `songs` | 歌曲元数据 (title, artist, album, duration, audio_path, energy, warmth, density) |
| `playlists` | 用户创建的播放列表 |
| `playlist_songs` | 播放列表-歌曲关联 |

### 手动查询

```bash
cd malio
source venv/bin/activate
python -c "
from models.music import Song
from core.recommendation_engine import RecommendationEngine
engine = RecommendationEngine()
session = engine.Session()
songs = session.query(Song).all()
print(f'{len(songs)} songs in DB')
for s in songs[:5]:
    print(f'  {s.id} | {s.title} — {s.artist} | E={getattr(s, \"energy\", \"?\")}')
"
```

---

## 十、一键启动脚本 (可选)

创建 `start.sh` (WSL) 或 `start.ps1` (Windows PowerShell) 放在项目根目录：

### WSL / Linux (`start.sh`)

```bash
#!/bin/bash
set -e
echo "=== Malio ==="

# Backend
cd "$(dirname "$0")/malio"
source venv/bin/activate
python main.py &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Frontend
cd ../frontend
npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo "Backend:  http://localhost:8007"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
```

### Windows PowerShell (`start.ps1`)

```powershell
Write-Host "=== Malio ==="

# Backend
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "main.py" -WorkingDirectory "malio"

# Frontend
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory "frontend"

Write-Host "Backend:  http://localhost:8007"
Write-Host "Frontend: http://localhost:5173"
```
