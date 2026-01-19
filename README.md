# Gemini Chat (Kasm Docker Edition)

这是一个基于 **FastAPI** 和 **Kasm Workspaces** 构建的 Gemini AI 智能对话系统。

本项目利用 Kasm 的容器化桌面环境，完美解决了 Gemini Web API 的 Cookie 获取与保活问题。通过在容器内部运行 Chrome 浏览器，配合 `browser_cookie3`，系统能够**全自动获取和刷新 Google 账号 Cookie**，无需手动抓包，实现稳定、免费的 Gemini Pro/Flash 接口调用。

## ✨ 核心特性

* **🛡️ 零配置自动鉴权**: 集成完整 Ubuntu 桌面环境，在容器内登录一次 Google 账号，即可自动抓取并维护 `__Secure-1PSID`，彻底告别手动复制 Cookie 的烦恼。
* **💾 智能 Cookie 缓存**: 系统会将获取到的凭证缓存至本地 (`cookie_cache.json`)，服务重启后优先读取缓存，减少对浏览器的依赖，提升启动速度。
* **🔌 熔断保护机制**: 内置智能熔断逻辑。当连续认证失败 3 次时，系统自动进入 300 秒冷却期，有效防止因频繁请求导致的 Google 账号风控。
* **🧠 多模型支持**: 完美支持 `gemini-3.0-pro`, `gemini-2.5-pro`, `gemini-2.5-flash` 等最新模型。
* **🖼️ 多模态交互**:
* **文件分析**: 支持上传并分析各种格式的文件。
* **图片生成**: 支持调用 Gemini 生成图片，并自动保存至本地归档。


* **🚀 兼容 OpenAI 接口**: 提供兼容 OpenAI 格式的 `/v1/chat/completions` 接口，可轻松接入第三方客户端（如 NextChat, Cherry Studio）。
* **💻 现代化 Web UI**: 内置 React 编写的精美聊天界面，支持 Markdown 渲染、代码高亮、打字机效果及历史对话管理。

---

## 🏗️ 架构原理

本项目使用 **Kasm Desktop** 镜像作为基础：

1. **环境层**: 提供一个可以通过 Web (VNC) 访问的 Ubuntu 桌面。
2. **浏览器层**: 容器内包含 Chrome，用于模拟真实用户登录。
3. **应用层**: Python 后端 (`server.py`) 通过 `browser_cookie3` 直接读取 Chrome 的本地数据库解密 Cookie。
4. **补丁层**: 构建时自动修复 `gemini-webapi` 在 Python 3.10 下的 `StrEnum` 兼容性问题。

---

## 🛠️ 部署指南

### 1. 环境准备

确保已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 2. 获取代码与权限设置 (⚠️ 关键步骤)

由于容器内部使用非 Root 用户 (`kasm-user`, UID 1000) 运行，**必须**在宿主机上预先调整目录权限，否则会报错 `Permission denied`。

```bash
# 1. 克隆或下载代码到本地目录
git clone https://github.com/Hiih-u/gemini-api.git
cd gemini-chat

# 2. 创建必要的数据目录
mkdir -p kasm_profile stored_images conversations uploads

# 3. 将当前目录下所有文件的所有权交给 UID 1000 (容器内的运行用户)
sudo chown -R 1000:1000 .

```

### 3. 构建镜像

使用提供的 `Dockerfile` 构建定制镜像（包含 Python 3.10 和依赖补丁）：

```bash
docker build -t gemini-kasm:1.0 .

```

### 4. 启动服务

使用 Docker Compose 一键构建并启动：

```bash
# 启动服务
docker compose up -d

```

---

## 🖥️ 使用流程 (首次配置)

服务启动后，需要进行一次性的登录操作以激活 Cookie。

### 第一步：进入 Kasm 桌面

1. 在浏览器访问：`https://localhost:6901`
* *注意：HTTPS 证书自签名，请点击“高级” -> “继续访问”。*


2. 输入默认账号密码（可在 `compose.yml` 修改）：
* **用户**: `kasm_user`
* **密码**: `password`



### 第二步：登录 Google 账号

1. 在 Kasm 桌面内部，点击左下角菜单或桌面图标打开 **Chrome 浏览器**。
2. 访问 `https://gemini.google.com` 并登录你的 Google 账号。
3. *登录成功后，Cookie 即已被写入容器内的浏览器数据库。*

### 第三步：启动 API 服务

1. 在 Kasm 桌面中，打开 **终端 (Terminal)**。
2. 执行以下命令启动后端服务（**必须加载 D-Bus 环境**）：

```bash
# 1. 进入项目目录
cd /gemini

# 2. 加载 D-Bus 环境变量 (用于解锁系统的钥匙串以读取加密 Cookie)
eval $(dbus-launch --sh-syntax)

# 3. 启动服务 (使用内置的 python3.10)
python3.10 server.py

```

看到以下日志即表示成功：

```text
ℹ️ 🚀 启动 Gemini Chat 服务器
ℹ️ 🌍 正在从 Kasm Chrome 浏览器抓取最新 Cookie...
✅ 浏览器抓取成功! TS: ...
💾 Cookie 已保存到本地缓存文件 (cookie_cache.json)

```

---

## 🎨 前端与 API 使用

### Web 聊天界面

服务启动后，在**宿主机**浏览器访问：

* **主界面**: `http://localhost:8000` (或 `http://localhost:8000/static/chatui.html`)
* **并发测试版**: `http://localhost:8000/static/pic.html` (支持并发发送多次请求)

### API 接入

后端地址: `http://localhost:8000`
API Key: 留空或随意填写（由后端 Cookie 托管）

**OpenAI 兼容接口示例**:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.0-pro",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

```

---

## ⚙️ 配置说明

### 环境变量 (`.env` 或 `compose.yml`)

| 变量名 | 说明 | 默认值 |
| --- | --- | --- |
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 容器内部端口 | `8000` |
| `IMAGES_DIR` | 图片存储目录 | `stored_images` |
| `DEBUG` | 开启调试日志 | `true` |
| `SECURE_1PSID` | (可选) 手动指定 Cookie | 空 |

### Docker 卷挂载

* `./kasm_profile`: 持久化 Chrome 的用户数据（保留登录状态）。
* `./stored_images`: 持久化 AI 生成的图片。
* `./conversations`: 持久化对话历史 JSON 文件。

---

## ❓ 常见问题 (FAQ)

**Q: 启动时提示 `Permission denied: 'stored_images'`?**
A: 你的宿主机目录权限属于 root。请务必在宿主机执行 `sudo chown -R 1000:1000 .`。

**Q: 报错 `ImportError: cannot import name 'StrEnum'`?**
A: 你可能直接使用了 `python3` 运行。请确保在容器内使用的是 `python3.10 server.py`。

**Q: 日志提示 `System cooling down`?**
A: 触发了熔断保护。这通常是因为 Cookie 失效且自动刷新失败超过 3 次。请进入 Kasm 桌面，手动刷新一下 Gemini 页面，等待 5 分钟后重试。

**Q: 为什么需要 D-Bus (`eval $(dbus-launch ...)`)?**
A: Chrome 在 Linux 下使用加密存储 Cookie，Python 脚本需要通过 D-Bus 与系统的 Secret Service 通信才能解密读取这些 Cookie。

---

## 📂 项目结构

```text
.
├── Dockerfile              # 定制镜像构建脚本 (Py3.10 + 依赖补丁)
├── compose.yml             # 容器编排配置
├── server.py               # 核心后端逻辑 (FastAPI, 熔断, Cookie管理)
├── requirements_linux.txt  # 依赖列表
├── kasm_profile/           # Chrome 数据映射目录
├── stored_images/          # 生成图片存放处
├── conversations/          # 对话历史存档
└── static/                 # 前端资源
    ├── chatui.html         # React 版主界面
    ├── pic.html            # 并发请求测试界面
    └── index.html          # 入口页面

```