# Server Monitor Dashboard

> 🌐 自建服务器监控仪表盘 · DFshmily の🌐

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](backend/requirements.txt)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](backend/)
[![Vue 3](https://img.shields.io/badge/frontend-Vue%203-42b883.svg)](frontend/)
[![Vite](https://img.shields.io/badge/build-Vite-646cff.svg)](frontend/)
[![ECharts](https://img.shields.io/badge/charts-ECharts%206-da4453.svg)](frontend/)
[![globe.gl](https://img.shields.io/badge/3D-globe.gl-2ea8d8.svg)](frontend/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/DFshmily/server-monitor/pulls)

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

### ⚙️ 服务状态说明（systemd）
- **系统服务 ≠ 进程**：服务是 systemd 的"岗位编制"（unit 定义），进程是实际运行的实例。一个服务可对应 0 / 1 / 多个进程。
- 状态判定：Agent 每 `MONITOR_INTERVAL`（默认 2s）实时执行 `systemctl list-units --type=service` 采集，按 `active` 字段统计。
- **显示自动消**：前端仅当 `failed > 0` 时显示"(N 异常)"。服务恢复运行 → 下一次采集 `failed` 归零 → 异常标识自动消失，无需人工干预。
- **常见假异常**：`systemd-run` 创建的一次性临时服务（如 `gw-restart-*.service`）执行完后会残留为 `failed` 状态，被误判为故障。清理：`sudo systemctl reset-failed <unit>`；排查：`systemctl --failed`。

### 📈 自定义监控项（管理页配置，Agent 执行）
- **管理页直接配置**：选服务器 + 命令 + 间隔（秒/分钟/小时）+ 单位，无需 SSH，支持编辑/启停/删除
- 管理页列表直接显示**最新执行结果**（值 / 失败原因 / 未上报）
- 详情页支持**历史趋势曲线**（最近 24 小时）+ **阈值告警**（告警规则里选"自定义: 名称"）
- 配置存后端数据库，agent 每分钟自动拉取执行（本地文件 `/etc/server-monitor/custom-commands.json` 保留为兜底）
- ⚠️ 注意：登录用户可见该页面，**不要放会泄露敏感信息（如公网 IP）的命令**

### 🔄 系统更新提醒
- agent 每小时统计 `apt` 可升级包数量，首页卡片与详情页显示"待更新 N 个"
- 告警规则支持"待安装更新"指标（如 > 20 提醒打补丁）

### 🌍 登录日志 IP 归属地
- 登录日志自动显示 IP 地理位置（ip2region 离线库，无外部 API 依赖，支持国内精确到城市/运营商）
- 异常登录一眼识别来源地区

### 📊 探活延迟历史
- 管理页探活规则可查看 24 小时延迟趋势曲线（判断稳定性/网络抖动）

### 💓 心跳监控（定时任务守护）
- Healthchecks.io 风格：给备份 / cron 任务配一个专属心跳 URL，任务末尾 curl 一下
- 超过预期时间未收到心跳 → 自动推送告警（💔 丢失 / 💚 恢复），任务"悄悄挂了"也能第一时间知道
- 管理页配置心跳项（名称/间隔/宽限）、复制 URL、查看最近心跳与状态
- 已接入：数据库备份（每天 03:10 自动心跳）

### 📊 图表事件标注（Grafana Annotations 风格）
- 详情页趋势图上，告警🚨 / 离线⚠️ / 恢复✅ 自动画成彩色虚线竖线，维护窗口显示紫色高亮区域
- 悬停竖线可查看事件详情；时间粒度切换时自动加载对应窗口的事件

### 📈 自定义监控项（管理页配置，Agent 执行）
- **管理页直接配置**：选服务器 + 命令 + 间隔（秒/分钟/小时）+ 单位，无需 SSH，支持编辑/启停/删除
- 管理页列表直接显示**最新执行结果**（值 / 失败原因 / 未上报）
- 配置存后端数据库，agent 每分钟自动拉取执行（本地文件 `/etc/server-monitor/custom-commands.json` 保留为兜底）
- 详情页概览自动展示为指标卡片，支持数值型与字符串型输出
- ⚠️ 注意：登录用户可见该页面，**不要放会泄露敏感信息（如公网 IP）的命令**

### 🔍 服务探活（外部可达性）
- **HTTP(S)** — 状态码 / 响应时间 / 关键词匹配
- **TCP 端口** — 端口是否开放可连接
- **Ping** — ICMP 可达性
- **DNS** — 域名解析（返回解析出的 IP）
- 规则支持**新增 / 编辑 / 启停 / 删除 / 手动测试**；探测间隔可选单位（秒 / 分钟 / 小时，10s ~ 24h）
- 失败自动推送通知，恢复自动提醒（30 分钟冷却）；24h 可用率统计
- 弥补"内部健康监控"盲区：服务器指标正常 ≠ 用户能访问到服务

### 🔐 登录安全
- 邮箱验证码注册 + 邀请码机制（生成 / 自定义 / 取消）
- 登录失败锁定：同账号 5 次 / 同 IP 10 次 → 锁 15 分钟
- 登录日志：谁 / 什么时候 / 哪个 IP / 什么设备 / 成功失败（管理页可查，保留 30 天）

### 🛠 告警系统
- 阈值规则（CPU / 内存 / 磁盘 / 负载 / 网络 / 证书天数 / 月流量）+ 恢复通知 + 30 分钟冷却
- 离线检测（心跳超时）+ 恢复通知
- **维护模式**：窗口内对应服务器告警静默（事件仍记录）
- 通知渠道：Telegram / Bark
- 告警事件记录 + 管理操作审计

### 🤖 Agent 健康
- 每台 agent 版本 / 最后上报时间 / 10 分钟推送次数 / 在线状态

### 💾 数据安全
- SQLite 轻量备份：每天 03:10 只备份关键表（账号 / 邀请码 / 告警规则 / 探活规则 / 审计等，几十 KB），保留最近 1 份自动清理旧备份
- 监控原始数据可再生产物，不占备份空间

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
- 登录/注册接口安全：JWT 独立密钥（`MONITOR_JWT_SECRET`）、CORS 仅放行本站域名、生产环境关闭 API 文档（`/docs`）、登录按邮箱 5 次/15 分钟与按 IP 10 次/15 分钟锁定、验证码发送按 IP 限流（防邮箱轰炸）、验证码验证尝试限流（防爆破）
- 建议 Nginx 层对 `/api/auth/` 加 `limit_req` 限流（参考 `deploy/nginx-rate-limit.conf`，本仓库已附模板）
- 对外可叠加 Cloudflare 免费防护：WAF 托管规则集（Log4j/Shellshock/WordPress 等漏洞特征拦截）+ WAF 自定义规则（拦截已知机器人 UA）+ 非中国区 IP 访问登录接口托管质询（challenge 在边缘拦截海外爆破）

## 📄 License

MIT
