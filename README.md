# Gemini Chat (Kasm Multi-Account Edition)

这是一个基于 **FastAPI** 和 **Kasm Workspaces** 构建的 Gemini AI 智能对话系统。

本项目利用 Kasm 的容器化桌面环境，完美解决了 Gemini Web API 的 Cookie 获取与保活问题。通过在容器内部运行 Chrome 浏览器，系统能够**全自动获取和刷新 Google 账号 Cookie**。

**特别增强**：本项目已升级为**多实例架构**，支持同时运行多个独立的 Worker，每个 Worker 绑定独立的 Google 账号和浏览器环境，实现物理级的数据隔离与负载分担。

## ✨ 核心特性

* **🛡️ 零配置自动鉴权**: 集成完整 Ubuntu 桌面环境，在容器内登录一次 Google 账号，即可自动抓取并维护 `__Secure-1PSID`。
* **👥 多账户支持 (New)**: 通过 `docker-compose` 轻松扩展多个 Worker，每个 Worker 拥有独立的数据目录 (`profiles/`, `data/`)，互不干扰，有效规避单账号速率限制。
* **⚡ 自动化部署 (New)**: 提供 `init.sh` 脚本，自动识别 Worker 数量并初始化所需的文件结构与权限，告别繁琐的手动配置。
* **💾 智能 Cookie 缓存**: 系统会将凭证缓存至本地 (`cookie_cache.json`)，重启后优先读取缓存，减少对浏览器的依赖。
* **🔌 熔断保护机制**: 内置智能熔断逻辑，连续认证失败 3 次自动冷却 300 秒。
* **🚀 兼容 OpenAI 接口**: 提供兼容 OpenAI 格式的 `/v1/chat/completions` 接口。

---

## 🛠️ 部署指南

### 1. 环境准备

确保已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 2. 获取代码

```bash
git clone https://github.com/Hiih-u/gemini-api.git
cd gemini-chat

```

### 3. 配置 Worker 数量 (可选)

默认的 `compose.yml` 已经配置了 **2 个 Worker** (`worker-1` 和 `worker-2`)。
如果您需要更多账户，请直接复制 `compose.yml` 中的服务定义，并修改对应的端口号。

### 4. ⚡ 一键初始化 (核心步骤)

我们提供了一个自动化脚本来解决 Docker 挂载文件时的权限问题和目录结构创建。

**请务必运行此脚本，而不是手动创建目录！**

```bash
# 1. 赋予脚本执行权限
chmod +x init.sh

# 2. 运行初始化脚本
./init.sh

```

### 5. 启动容器

```bash
docker compose up -d

```

---

## 👥 多账户配置与启动 (核心流程)

启动容器后，您需要分别进入每个 Worker 的桌面环境登录账号，并手动启动 API 服务。

### Worker 1 配置 (账号 A)

**1. 登录 Google 账号**

* **进入桌面**: 浏览器访问 `https://localhost:6901` (用户: `kasm_user` / 密码: `password`)
* **登录**: 在 Kasm 桌面内打开 Chrome，登录 **Google 账号 A**。

**2. 启动 API 服务**
您可以在 Kasm 桌面的终端中运行，也可以在宿主机通过 Docker 命令启动：

```bash
# 进入 Worker 1 容器
docker exec -it gemini-kasm-1 bash

# --- 容器内执行 ---
# 1. 加载 D-Bus 环境 (解锁 Cookie 读取权限)
eval $(dbus-launch --sh-syntax)

# 2. 启动后端服务
python3.10 server.py

```

*看到 `🚀 启动 Gemini Chat 服务器` 日志即表示 Worker 1 (端口 8001) 就绪。*

---

## 🔌 API 调用

您现在拥有多个独立的 API 端点：

* **Worker 1**: `http://localhost:8001` (对应账号 A)
* **Worker 2**: `http://localhost:8002` (对应账号 B)

**OpenAI 兼容接口示例:**

```bash
curl http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.0-pro",
    "messages": [{"role": "user", "content": "你好"}]
  }'

```

---

## 📂 目录结构

在使用 `init.sh` 初始化后，您的目录结构将如下所示：

```text
.
├── init.sh                 # ⚡ 自动化部署脚本
├── compose.yml             # 多 Worker 编排配置
├── profiles/               # Chrome 配置文件 (自动生成)
│   ├── worker1/            # Worker 1 的浏览器数据
│   └── worker2/            # Worker 2 的浏览器数据
├── data/                   # 运行时数据 (自动生成)
│   ├── worker1/
│   │   ├── conversations/  # 账号 A 的对话历史
│   │   ├── images/         # 账号 A 生成的图片
│   │   └── cookie_cache.json # 账号 A 的 Cookie
│   └── worker2/
│       ├── ...             # 账号 B 的数据 (完全隔离)
└── server.py               # 核心代码

```

---

## ❓ 常见问题 (FAQ)

**Q: 为什么必须手动执行 `python3.10 server.py`？**
A: 因为 Kasm 镜像默认启动的是桌面环境 (VNC)。我们需要桌面环境来运行 Chrome 浏览器保持登录状态，所以 Python API 服务需要作为一个后台进程手动启动。

**Q: 报错 `ImportError: cannot import name 'StrEnum'`?**
A: 请确保使用的是 `python3.10 server.py`。Kasm 镜像自带多个 Python 版本，直接用 `python3` 可能会调用旧版本。

**Q: 如何增加 Worker 3?**
A:

1. 修改 `compose.yml`，复制 `worker-2` 的配置，改为 `worker-3` (容器名 `gemini-kasm-3`)，端口改为 `6903/8003`。
2. 运行 `./init.sh` 自动创建目录。
3. 运行 `docker compose up -d`。
4. 参照上述步骤登录账号并启动服务。