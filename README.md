# 🌌 Gemini API (Kasm Enterprise Edition)

> 基于 Kasm Workspaces 容器化技术的 Gemini API 代理网关。
> 通过真实的桌面环境运行 Chrome 浏览器，实现 Cookie 自动保活、多账号负载均衡与 Nacos 服务发现。

## 📖 项目简介

本项目专为解决 Gemini Web 接口调用中的 **Cookie 获取难**、**风控严格 (429/403)** 以及 **会话持久化** 问题而设计。

核心原理利用 **Kasm Ubuntu 桌面容器** 运行一个完整的 GUI 环境。用户通过 VNC 登录 Google 账号后，后台服务 (`server.py`) 会自动通过 `browser_cookie3` 读取 Chrome 浏览器的凭证，并提供兼容 OpenAI 格式的 API 接口。

### ✨ 核心特性

* **🛡️ 物理级账号隔离**: 通过 Docker Compose 编排多个 Worker，每个容器拥有独立的 `data` 和 `profiles` 挂载，彻底规避关联封号风险。
* **🍪 智能 Cookie 管理**:
    * **自动热加载**: 启动时自动抓取 Chrome Cookie，并缓存至 `cookie_cache.json`。
    * **认证熔断 & 自愈**: 遇到 401/403 自动尝试刷新 Cookie；遇到 **429 (严重限流)** 自动进入 1 小时冷却模式，保护账号安全。
* **📡 数据库服务发现**: 利用 **PostgreSQL** 进行轻量级心跳注册 (`gemini_service_nodes` 表)，配合网关实现动态负载均衡。
* **🚀 OpenAI 兼容接口**: 提供标准的 `/v1/chat/completions`，无缝对接 NextChat、OneAPI 等前端。
* **🖼️ 多模态支持**: 支持图片上传与分析，生成的图片自动保存并提供静态访问链接。

---

## 🛠️ 快速部署

### 1. 环境准备

确保已安装 Docker 和 Docker Compose。

```bash
git clone https://github.com/Hiih-u/gemini-api.git
cd gemini-api

# windows 下部署单体
python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 初始化目录 (重要)

由于容器内运行非 Root 用户 (kasm-user)，必须先运行初始化脚本创建挂载目录并修正权限。

```bash
chmod +x init.sh
./init.sh

```

*该脚本会自动读取 `compose.yml` 中的 worker 数量，创建对应的 `data/workerX` 和 `profiles/workerX` 目录。*

### 3. 启动服务

```bash
docker compose up -d

```

*默认启动 Nacos (8848) 和 2 个 Worker 节点 (8001, 8002)。*

---

## 🔐 账号登录与服务启动 (关键步骤)

启动容器后，你需要**手动**进入每个 Worker 的桌面环境登录 Google 账号。

### 第一步：访问 Kasm 桌面

在浏览器访问 Worker 的 VNC 地址：

* **Worker 1**: `https://<你的IP>:6901`
* **Worker 2**: `https://<你的IP>:6902`
* **默认凭证**: 用户名 `kasm_user` / 密码 `password`

### 第二步：登录 Google

1. 在 Kasm 桌面中，打开 **Chrome** 浏览器。
2. 访问 `google.com` 并登录你的 Google 账号。
3. 确保能正常访问 Gemini 网页版。

### 第三步：启动 API 服务

登录完成后，你需要启动 Python 后端服务。：

**方式 A：通过 Docker Exec 启动**
在宿主机终端执行：

```bash
# 进入容器
docker exec -it gemini-kasm-1 bash

# 加载环境变量并启动
eval $(dbus-launch --sh-syntax)
python3.10 server.py > /proc/1/fd/1 2>&1

```

*看到 `✅ Gemini 客户端初始化成功` 和 `✅ Nacos 注册成功` 即表示服务就绪。*

---

## 🔌 API 接口文档

### 对话补全 (Chat Completions)

完全兼容 OpenAI 格式。

* **URL**: `http://localhost:8001/v1/chat/completions`
* **Method**: `POST`

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下你自己"}
    ],
    "stream": false
  }'

```

### 文件上传 (Upload)

支持上传图片或文档用于多模态分析。

* **URL**: `http://localhost:8001/upload`
* **Method**: `POST`
* **Body**: `multipart/form-data` (字段名: `files`)

---

## ⚙️ 配置说明

修改 `compose.yml` 或 `.env` 调整配置。

| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `NACOS_SERVER_ADDR` | Nacos 注册中心地址 | `nacos:8848` |
| `EXTERNAL_IP` | 容器对外暴露的 IP (注册到 Nacos 用) | `192.168.202.155` |
| `EXTERNAL_PORT` | 容器对外暴露的端口 | `8001` / `8002` |
| `VNC_PW` | Kasm 桌面访问密码 | `password` |
| `DEBUG` | 开启调试日志 | `true` |

## 📂 目录结构

```text
gemini-api/
├── compose.yml             # 多容器编排 (Nacos + Workers)
├── init.sh                 # 初始化脚本 (权限修正)
├── server.py               # 核心 FastAPI 服务端
├── Dockerfile              # Kasm 镜像构建文件
├── data/                   # [自动生成] 数据挂载目录
│   ├── worker1/
│   │   ├── cookie_cache.json  # 缓存的 Cookie
│   │   └── stored_images/     # 生成的图片
│   └── worker2/
├── profiles/               # [自动生成] Chrome 配置文件挂载
└── requirements_linux.txt  # Python 依赖

```

## ❓ 常见问题

**Q: 为什么日志提示 `Browser cookie3 not found`？**
A: 请确保你在 Kasm 容器内使用的是 `python3.10` 运行服务。系统默认 Python 版本可能较低，而我们在 Dockerfile 中专门安装了 Python 3.10 环境。

**Q: Nacos 注册的 IP 是 127.0.0.1？**
A: 请检查 `compose.yml` 中的 `EXTERNAL_IP` 变量。服务会自动读取该变量作为注册 IP，如果未设置，它会尝试探测 Docker 内部 IP。

**Q: 遇到 `429 Resource Exhausted` 怎么办？**
A: 系统会自动触发熔断机制，并在控制台打印警告 `🔥 Google 严重流控 (429) 生效中`。服务会强制休眠 1 小时以保护账号安全。建议轮询切换到另一个 Worker 节点。
