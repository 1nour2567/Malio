# Malio - 智能音乐代理

Malio 是一个基于 AI 的音乐代理，通过结合音乐数据、实时天气、日程和心情信息，为用户提供个性化电台服务。

## 核心功能

- **个性化推荐**: 根据用户历史歌单和实时场景推荐音乐
- **多平台音乐源**: 同时支持 Spotify 和网易云音乐
- **智能聊天**: 可通过聊天界面与 Malio 互动，调整歌单或获取音乐推荐
- **场景感知**: 结合天气、时间、心情等信息提供合适的音乐

## 技术栈

### 后端
- Python 3.12+
- FastAPI
- Kimi API (Moonshot) / Claude API
- SQLAlchemy (数据库)
- Pydantic (配置和数据验证)

### 前端
- React 18
- Vite
- Howler.js (音频播放)
- Lucide React (图标)

## 项目结构

```
├── malio/              # 后端代码
│   ├── core/             # 核心模块
│   ├── config/           # 配置管理
│   ├── data/             # 数据导入和处理
│   ├── integrations/     # 外部服务集成
│   ├── models/           # 数据库模型
│   ├── main.py           # 主应用入口
│   ├── .env              # 环境变量（不提交）
│   └── .env.example      # 环境变量模板
├── frontend/             # 前端代码
│   ├── src/              # 源代码
│   ├── package.json      # 前端依赖
│   └── vite.config.js    # Vite 配置
└── README.md             # 项目说明
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+

### 后端设置

1. **安装依赖**
   ```bash
   cd malio
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/Mac:
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入 API 密钥
   ```

3. **启动后端服务**
   ```bash
   cd malio
   python main.py
   ```
   服务将在 http://localhost:8007 运行

### 前端设置

1. **安装依赖**
   ```bash
   cd frontend
   npm install
   ```

2. **启动前端开发服务器**
   ```bash
   cd frontend
   npm run dev
   ```
   前端将在 http://localhost:5173 运行

### 网易云音乐 API （可选）

如果需要使用网易云音乐的完整功能，需要部署网易云音乐 API：

```bash
# 使用 Docker 部署
docker run -d -p 3000:3000 moefurina/ncm-api:latest
```

或者访问项目仓库获取其他部署方式。

## API 端点

### 核心功能
- `POST /api/recommend` - 获取音乐推荐
- `POST /api/chat` - 与 Malio 聊天
- `POST /api/generate-playlist-name` - 生成播放列表名称
- `GET /api/context` - 获取当前场景上下文
- `POST /api/import-data` - 导入音乐数据

### 设备控制
- `GET /api/devices` - 获取可用设备列表
- `POST /api/devices/connect` - 连接设备
- `POST /api/devices/disconnect` - 断开设备连接
- `POST /api/devices/play` - 播放音乐
- `POST /api/devices/pause` - 暂停音乐
- `POST /api/devices/stop` - 停止音乐
- `POST /api/devices/volume` - 设置音量
- `GET /api/devices/status` - 获取设备状态

### 音乐库管理
- `GET /api/songs` - 获取所有歌曲
- `POST /api/songs` - 添加歌曲
- `DELETE /api/songs/{song_id}` - 删除歌曲
- `GET /api/library/stats` - 获取音乐库统计

### Spotify API
- `GET /api/spotify/search` - 搜索歌曲
- `POST /api/spotify/recommendations` - 获取推荐
- `GET /api/spotify/track/{track_id}` - 获取歌曲详情
- `GET /api/spotify/artists` - 搜索艺术家
- `POST /api/spotify/add-to-library` - 添加到本地库
- `POST /api/spotify/import` - 导入歌曲

### 网易云音乐 API
- `GET /api/netease/search` - 搜索歌曲
- `GET /api/netease/track/{track_id}` - 获取歌曲详情
- `GET /api/netease/track/{track_id}/url` - 获取播放链接
- `GET /api/netease/track/{track_id}/details` - 获取完整详情
- `GET /api/netease/top` - 获取热门歌曲
- `GET /api/netease/new` - 获取新歌
- `POST /api/netease/add-to-library` - 添加到本地库
- `POST /api/netease/import` - 导入歌曲

### 健康检查
- `GET /` - 根端点
- `GET /health` - 健康检查

## 配置说明

### .env 文件配置

```env
# Kimi API
KIMI_API_KEY=your_kimi_api_key_here
KIMI_MODEL=kimi-k2.5
KIMI_API_BASE=https://api.moonshot.cn/v1/

# Spotify（可选）
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=

# OpenWeather（可选）
OPENWEATHER_API_KEY=

# 网易云音乐
NETEASE_API_URL=http://localhost:3000
NCM_COOKIE=your_ncm_cookie_here  # 可选，用于获取完整音频

# 服务器
HOST=0.0.0.0
PORT=8007

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000
```

## 获取网易云音乐 Cookie

1. 打开浏览器，访问 https://music.163.com/
2. 登录你的网易云音乐账号
3. 按 F12 打开开发者工具
4. 切换到 Network 标签
5. 刷新页面，找到任意请求
6. 在请求头中找到 Cookie，复制完整的 Cookie 值

## 示例数据

项目包含示例数据，位于 `malio/data/` 目录下，可以直接用于测试。

## 安全说明

⚠️ **重要提醒**：
- 不要将 `.env` 文件提交到版本控制
- 不要在代码中硬编码 API 密钥
- 在生产环境中严格限制 CORS 来源
- 建议添加 API 速率限制

## 许可证

MIT
