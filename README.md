# Gemini-FastAPI 项目指南

这是一个基于 FastAPI 构建的 Gemini 接口服务。本项目支持通过环境变量配置服务参数，并集成了虚拟环境管理。

## 🚀 快速开始

### 1. 环境准备

确保你的系统已安装 **Python 3.8+**。

### 2. 克隆项目与初始化

```bash
# 克隆仓库
git clone https://github.com/Hiih-u/gemini-api.git
cd gemini-api

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/macOS)
# source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt

```

### 4. 配置环境变量

项目根目录下必须包含一个 `.env` 文件。请参考以下配置（已根据你的需求预设）：

```ini
# Gemini 认证凭据 (Cookie 相关)
SECURE_1PSID=你的_1PSID_内容
SECURE_1PSIDTS=你的_1PSIDTS_内容

# 网络服务配置
HOST=0.0.0.0
PORT=61080
BASE_URL=http://localhost:61080

# 资源存储配置
IMAGES_DIR=stored_images
```

> **注意**：`.env` 文件包含敏感信息，已通过 `.gitignore` 忽略，请勿上传至 Git 仓库。

### 5. 启动服务

运行以下命令启动 FastAPI 服务：

```bash
python server.py
```

服务启动后，可以通过访问 `http://localhost:61080/docs` 查看 Swagger UI 接口文档。

---

## 📂 目录结构

* `server.py`: 项目入口文件。
* `static/`: 存放静态资源文件。
* `stored_images/`: 默认的图片存储目录（由 `IMAGES_DIR` 定义）。
* `.env`: 环境配置文件（需手动创建）。
* `.gitignore`: Git 忽略配置文件。
---

## 🛠️ 技术栈

* [FastAPI](https://fastapi.tiangolo.com/): 高性能 Python Web 框架。
* [Python-dotenv](https://saurabh-kumar.com/python-dotenv/): 环境变量管理。

---"# gemini-chat" 
