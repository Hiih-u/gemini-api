# Gemini Chat (Kasm Docker Edition)

这是一个基于 **FastAPI** 和 **Kasm Workspaces** 构建的 Gemini AI 聊天服务。

本项目使用定制的 Docker 镜像，在一个完整的 Ubuntu 桌面环境中运行。这使得 `browser_cookie3` 能够直接读取容器内 Chrome 浏览器的 Cookie，从而实现 **全自动的 Gemini 鉴权**，无需手动复制 Cookie。

## ✨ 特性

* **自动鉴权**: 集成 Kasm 桌面，登录一次 Google 账号即可自动获取/更新 Cookie。
* **环境隔离**: 基于 `kasmweb/desktop`，通过 Docker 完全隔离。
* **Python 3.10**: 镜像内置 Python 3.10 环境，完美兼容最新依赖。
* **自动补丁**: 构建过程中自动修复 `gemini-webapi` 的 `StrEnum` 兼容性问题。
* **多模态支持**: 支持文本对话、文件上传分析和图片生成。

---

## 🛠️ 部署指南

### 1. 前置准备

确保你的机器安装了 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

### 2. 目录与权限设置 (⚠️ 重要)

由于 Kasm 容器内部使用非 Root 用户 (`kasm-user`, UID 1000) 运行，**必须**在宿主机上调整目录权限，否则会导致 `Permission denied` 错误。

在项目根目录下执行：

```bash
# 1. 创建必要的数据目录
mkdir -p kasm_profile stored_images conversations uploads

# 2. 将当前目录下所有文件的所有权交给 UID 1000 (容器内的 kasm-user)
sudo chown -R 1000:1000 .

```

### 3. 构建镜像

使用提供的 `Dockerfile` 构建定制镜像（包含 Python 3.10 和依赖补丁）：

```bash
docker build -t www527/gemini-kasm:1.0 .

```

### 4. 启动容器

使用 Docker Compose 启动服务：

```bash
docker compose up -d

```

* **Kasm 桌面端口**: `6901` (HTTPS)
* **API 服务端口**: `8000` (HTTP)

---

## 🖥️ 使用流程 (首次配置)

容器启动后，你需要进入桌面环境登录 Google 账号并启动服务。

### 第一步：登录 Kasm 桌面

1. 在浏览器访问：`https://localhost:6901`
* *注意：如果提示证书不安全，请点击“高级” -> “继续访问”。*


2. 输入默认账号密码（如果在 `compose.yml` 中未修改）：
* **用户**: `kasm_user`
* **密码**: `password`



### 第二步：登录 Google 账号

1. 在 Kasm 桌面中，打开 **Chrome 浏览器**。
2. 访问 `google.com` 或 `gemini.google.com` 并登录你的 Google 账号。
3. *这是自动获取 Cookie 的关键步骤。*

### 第三步：启动 API 服务

1. 在 Kasm 桌面中，打开 **终端 (Terminal)**。
2. 执行以下命令启动服务（注意必须加载 D-Bus）：

```bash
# 1. 进入项目目录
cd /gemini

# 2. 加载 D-Bus 环境变量 (用于读取加密的 Cookie)
eval $(dbus-launch --sh-syntax)

# 3. 启动服务 (务必使用 python3.10)
python3.10 server.py

```

看到以下日志即表示启动成功：

```text
ℹ️ 🚀 启动 Gemini Chat 服务器
ℹ️ 📍 地址: http://0.0.0.0:8000
ℹ️ ✅ 自动获取成功! TS: ...

```

---

## 📂 项目结构

```text
.
├── Dockerfile              # 构建脚本 (自动安装 Py3.10 和补丁)
├── compose.yml             # 容器编排配置
├── server.py               # FastAPI 后端服务
├── requirements_linux.txt  # Linux 专用依赖列表
├── static/                 # 前端 HTML 资源
│   ├── index.html          # 主聊天界面
│   └── ...
├── kasm_profile/           # (自动生成) 映射 Chrome 用户数据
├── stored_images/          # (自动生成) 保存 AI 生成的图片
├── uploads/                # (自动生成) 用户上传的文件
└── conversations/          # (自动生成) 对话历史记录

```

## ❓ 常见问题排查

### 1. 启动时报错 `Permission denied: 'stored_images'`

**原因**: 宿主机目录权限属于 root。
**解决**: 在宿主机运行 `sudo chown -R 1000:1000 .`。

### 2. 报错 `ImportError: cannot import name 'StrEnum'`

**原因**: 使用了错误的 Python 版本。
**解决**: 确保在容器内使用的是 `python3.10 server.py`，而不是 `python3` (可能是 3.8)。

### 3. 报错 `DBUS_SESSION_BUS_ADDRESS` 或无法获取 Cookie

**原因**: 缺少 D-Bus 会话环境。
**解决**: 启动服务前必须运行 `eval $(dbus-launch --sh-syntax)`。

### 4. 桌面显示 "Unable to load a failsafe session"

**原因**: `compose.yml` 挂载了错误的 `/home/kasm-user/.config` 路径，覆盖了系统配置。
**解决**: 确保只挂载 Chrome 目录（如 `compose.yml` 中配置的那样），并执行 `docker compose down` 彻底删除旧容器后重启。

---

## 🔗 API 文档

服务启动后，可访问：

* **Web 界面**: `http://localhost:8000`
* **Swagger API 文档**: `http://localhost:8000/docs`
