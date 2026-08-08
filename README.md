# Server Monitor Dashboard

> 🌐 自建服务器监控仪表盘 · DFshmily の 🌍

基于 FastAPI + Vue 3 的轻量级多服务器监控系统，支持实时数据推送与历史数据回溯，内置 **3D 交互地球** 展示服务器全球分布。

线上示例：https://dashboard.dfshmily.icu

## ✨ 功能特性

### 📊 实时监控
- **CPU** — 总使用率 / 每核心使用率（可点击展开）/ iowait / steal
- **内存** — used / cached / buffers / swap
- **磁盘** — 每分区使用率 / IOPS / 读写速度
- **网络** — 每接口速率 / TCP 连接数 / 累计流量
- **进程** — Top 10 CPU / 内存 排行
- **系统** — 负载 (1/5/15 分钟) / 运行时长 / 服务状态
- **Docker** — 容器资源占用

### 🌍 3D 交互地球（/map）
- NASA 夜晚灯光地球贴图 + 地形凹凸纹理 + 星空背景
- 服务器所在国家区域青色高亮，悬停提亮、点击波纹扩散
- 国旗 emoji + 国家代码标签（🇯🇵JP / 🇨🇳CN）
- 青色光点 + 脉冲波纹环标记服务器位置
- 青 → 品红渐变虚线弧连接各节点
- 自动旋转 / 拖拽 / 缩放，全屏沉浸式体验

### 🎨 界面
- Apple 极简白 + 紫色点缀 + 玻璃拟态卡片
- GSAP 动效（标题/卡片入场动画）
- 首页标题内嵌霓虹地球图标（辉光脉冲 / 光斑扫过 / 双涟漪环 / 环绕卫星）
- ECharts 趋势图，多时间粒度（实时 / 1min / 5min / 1h / 1d / 1w）
- 响应式布局，移动端友好

## 🏗️ 架构

```
┌─────────────┐  POST /api/agent   ┌─────────────────────┐
│ Agent 甲     │ ─────────────────▶ │                     │
│             │                    │   FastAPI Backend   │
├─────────────┤                    │   (port 8000)       │
│ Agent 乙     │ ─────────────────▶ │         │           │
│             │                    │         ▼           │
└─────────────┘                    │      SQLite          │
                                   │         │           │
                                   │  WebSocket / REST    │
                                   └─────────┬───────────┘
                                             ▼
                                  ┌─────────────────────┐
                                  │   Vue 3 Frontend     │
                                  │  (Nginx 静态托管)     │
                                  └─────────────────────┘
```

- **Agent**（每台被监控服务器）：psutil 采集 → HTTP POST 推送
- **Backend**（中央服务器）：FastAPI 接收 → SQLite 存储 → WebSocket 实时广播
- **Frontend**：Vue 3 + Pinia + ECharts + globe.gl，Nginx 托管静态文件

## 📁 目录结构

```
server-monitor/
├── agent/                    # 数据采集代理（部署到每台被监控服务器）
│   ├── main.py               # 主循环：采集 → 推送
│   ├── collector.py          # psutil 采集逻辑
│   └── requirements.txt
├── backend/                  # FastAPI 后端（部署到中央服务器）
│   ├── app/
│   │   ├── main.py           # 入口（含前端静态托管）
│   │   ├── api/
│   │   │   ├── agent.py      # Agent 数据上报接口
│   │   │   ├── dashboard.py  # 仪表盘 REST API
│   │   │   └── ws.py         # WebSocket 实时推送
│   │   ├── core/             # 配置 / 数据库
│   │   ├── models/           # 数据模型
│   │   └── services/         # 历史数据聚合
│   └── requirements.txt
├── frontend/                 # Vue 3 前端
│   ├── src/
│   │   ├── views/            # Overview / MapPage / ServerDetail
│   │   ├── components/       # ServerCard / ServerMap / FloatingGlobe ...
│   │   └── stores/           # Pinia 状态管理
│   └── public/maps/          # 地球贴图与 GeoJSON 数据
└── README.md
```

## 🚀 快速开始

### 1. 后端（中央服务器）

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 环境变量
export MONITOR_DB=/var/lib/server-monitor/data.db
export MONITOR_API_KEY=your-secret-key
export MONITOR_HOST=0.0.0.0
export MONITOR_PORT=8000

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. 前端（构建静态文件）

```bash
cd frontend
npm install
npm run build        # 产物输出到 dist/
# 将 dist/ 目录交给 Nginx 托管，或由后端 StaticFiles 直接服务
```

### 3. Agent（每台被监控服务器）

```bash
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export MONITOR_BACKEND_URL=http://<中央服务器IP>:8000
export MONITOR_API_KEY=your-secret-key
export MONITOR_SERVER_NAME=oracle   # 服务器标识，需与前端 LOCATIONS 对应
python main.py
```

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MONITOR_BACKEND_URL` | 后端地址 | `http://localhost:8000` |
| `MONITOR_INTERVAL` | 采集间隔（秒） | `2` |
| `MONITOR_SERVER_NAME` | 服务器名称标识 | 自动检测 hostname |
| `MONITOR_API_KEY` | Agent 认证密钥 | `default-key` |
| `MONITOR_DB` | SQLite 数据库路径 | `/var/lib/server-monitor/data.db` |
| `MONITOR_HOST` | 后端监听地址 | `0.0.0.0` |
| `MONITOR_PORT` | 后端监听端口 | `8000` |

## 🗺️ 添加新服务器

1. 在被监控服务器部署 Agent，设置 `MONITOR_SERVER_NAME` 为新标识（如 `vultr`）
2. 在 `frontend/src/components/ServerMap.vue` 的 `LOCATIONS` / `REGION_CODES` / `ISO_TO_ID` 中添加该服务器的经纬度与国家代码
3. 在 `frontend/src/components/ServerCard.vue` 中添加显示名称与国旗图标映射
4. 重新构建前端即可，地球会自动高亮新国家并绘制连接弧

## 🔒 安全

- Agent → Backend 使用 `MONITOR_API_KEY` 请求头认证
- 生产环境建议通过 Nginx 反向代理 + HTTPS（如 Cloudflare CDN）对外提供服务
- 数据库文件默认位于 `/var/lib/server-monitor/`

## 📄 License

MIT
