# 🌌 Gemini API (Kasm Enterprise Edition)

> **基于 Kasm Workspaces 容器化技术的 Gemini API 高可用代理节点。**
> 通过在 Docker 容器内运行真实的桌面环境和 Chrome 浏览器，实现 Cookie 自动抓取、会话保活、429 熔断保护以及基于数据库的负载均衡注册。

---

## 📖 项目简介

本项目专为解决 Gemini Web 接口调用中的 **Cookie 获取难**、**风控严格 (429/403)** 以及 **会话持久化** 问题而设计。

核心原理利用 **Kasm Ubuntu 桌面容器** 运行一个完整的 GUI 环境。用户通过 VNC 登录 Google 账号后，后台服务 (`server.py`) 会自动通过 `browser_cookie3` 读取 Chrome 浏览器的凭证，并提供兼容 OpenAI 格式的 API 接口。

### ✨ 核心特性

* **🛡️ 物理级账号隔离**: 通过 Docker Compose 编排多个 Worker，每个容器拥有独立的 `data` 和 `profiles` 挂载，彻底规避关联封号风险。
* **🍪 智能 Cookie 管理**:
    * **自动热加载**: 启动时自动抓取 Chrome Cookie，并缓存至 `cookie_cache.json`。
    * **认证熔断 & 自愈**: 遇到 401/403 自动尝试刷新 Cookie；遇到 **429 (严重限流)** 自动进入 1 小时冷却模式，保护账号安全。
* **📡 数据库服务发现**: 直接利用 **PostgreSQL** 进行轻量级心跳注册 (`gemini_service_nodes` 表)，配合网关实现动态负载均衡。
* **🚀 OpenAI 兼容接口**: 提供标准的 `/v1/chat/completions`，无缝对接 NextChat、OneAPI 等前端。
* **🖼️ 多模态支持**: 支持图片上传与分析，生成的图片自动保存并提供静态访问链接。


## 🛠️ 部署指南

### 1. 环境要求
* Docker & Docker Compose
* PostgreSQL 数据库 (用于服务注册和心跳)

### 2. 克隆与初始化
由于 Kasm 容器内使用非 Root 用户 (UID 1000)，必须先执行脚本初始化挂载目录的权限。

```bash
# 1. 克隆项目
git clone https://github.com/Hiih-u/gemini-api.git
cd gemini-api

# 2. 赋予脚本执行权限并运行
chmod +x init.sh
./init.sh

```

> **注意**: `init.sh` 会自动读取 `compose.yml` 中的 worker 数量，创建对应的 `data/workerX` 目录并修正权限。

### 3. 配置环境变量

修改 `compose.yml` 或创建 `.env` 文件，确保数据库连接正确：

```yaml
environment:
  - DB_HOST=192.168.202.155  # 你的 PostgreSQL 地址
  - DB_PORT=61020
  - DB_USER=postgres
  - DB_PASSWORD=YourPassword
  - EXTERNAL_IP=192.168.202.155 # 当前宿主机 IP (供网关访问)

```

### 4. 启动服务

```bash
docker compose up -d

```

---

## 🔐 账号登录 (关键步骤)

服务启动后，API 尚不可用，需要手动登录 Google 账号以生成 Cookie。

### 步骤 A: 访问 Kasm 桌面

在浏览器访问 Worker 的 VNC 地址 (忽略 HTTPS 证书警告)：

* **Worker 1**: `https://<宿主机IP>:6901`
* **Worker 2**: `https://<宿主机IP>:6902`
* **默认账号**: `kasm_user`
* **默认密码**: `password` (可在 compose.yml 中修改)

### 步骤 B: 登录 Google

1. 在 Kasm 桌面内，点击左下角菜单打开 **Chrome** 浏览器。
2. 访问 `google.com` 并登录你的 Google 账号。
3. **强烈建议**: 访问一次 `gemini.google.com` 确保通过了欢迎页且能正常对话。

### 步骤 C: 激活 API

登录完成后，以下命令来激活后端服务：

```bash

docker exec -it gemini-kasm-1 bash
# 在容器内:
eval $(dbus-launch --sh-syntax)
python3.10 server.py

```

*当看到日志输出 `✅ Gemini 客户端初始化成功` 和 `💓 数据库心跳已启动` 时，服务即就绪。*

---

## 🔌 API 接口文档

### 1. 对话补全 (Chat Completions)

兼容 OpenAI 格式，支持流式和非流式（本项目默认非流式）。

* **Endpoint**: `POST /v1/chat/completions`

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "分析这张图片，并写一首诗。"}
    ]
  }'

```

### 2. 文件/图片上传

* **Endpoint**: `POST /upload`
* **Body**: `multipart/form-data`, key=`files`

### 3. 健康检查 & 状态

* **Endpoint**: `GET /health`
* **Response**: 返回当前活跃会话数和存储的图片数量。

---

## ⚙️ 详细配置

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DB_HOST` | **[必填]** PostgreSQL 主机地址 | `127.0.0.1` |
| `DB_PORT` | PostgreSQL 端口 | `5432` |
| `EXTERNAL_IP` | **[重要]** 容器宿主机的局域网 IP (用于注册到数据库供网关调用) | 自动探测 |
| `EXTERNAL_PORT` | 容器映射出来的 API 端口 | `8001` |
| `GEMINI_WORKER_ID` | 当前节点的唯一标识 ID | `gemini-worker-01` |
| `GEMINI_WEIGHT` | 负载均衡权重 | `1.0` |
| `VNC_PW` | Kasm VNC 桌面密码 | `password` |
| `DEBUG` | 是否开启详细调试日志 | `true` |

---

## 📂 目录结构

```text
gemini-api/
├── compose.yml             # 多容器编排
├── init.sh                 # 权限初始化脚本
├── server.py               # 核心服务 (FastAPI + SQLAlchemy)
├── Dockerfile              # Kasm 定制镜像
├── data/                   # [自动生成] 数据持久化目录
│   ├── worker1/
│   │   ├── cookie_cache.json  # 缓存的 Cookie (核心凭证)
│   │   ├── conversations/     # 对话历史 JSON
│   │   └── images/            # 生成的图片
│   └── worker2/ ...
└── profiles/               # [自动生成] Chrome 配置文件挂载

```

## ❓ 常见问题 (FAQ)

**Q: 遇到 `429 Resource Exhausted` 怎么办？**
A: 这是 Google 的严重限流。系统会自动触发 **1小时熔断保护**，控制台会打印 `🔥 Google 严重流控 (429) 生效中`。此时该节点会自动在数据库中标记为不可用，网关会将流量转发到其他 Worker。

**Q: 为什么日志提示 `Browser cookie3 not found`？**
A: 请确保使用 `init.sh` 启动，并且不要随意更改 `Dockerfile` 中的 Python 版本。我们依赖 Kasm 环境中的特定 Chrome 配置。

**Q: 如何更换 Google 账号？**
A:

1. 进入 Kasm 桌面 (https://IP:6901)。
2. 在 Chrome 中退出当前 Google 账号并登录新账号。
3. 删除 `data/workerX/cookie_cache.json` 文件。
4. 重启容器：`docker restart gemini-kasm-X`。

---

## ⚖️ 免责声明

本项目仅供技术研究与学术交流使用。用户应自行承担使用本工具产生的风险，并遵守 Google 服务条款。请勿用于任何商业用途或大规模滥用 API。

```

```
