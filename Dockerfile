# 1. 使用 Kasm 基础镜像 (Ubuntu 20.04 based)
FROM kasmweb/desktop:1.18.0

# 切换 root 用户进行安装
USER root

# 设置环境变量，防止 Python 生成 .pyc 文件和缓冲输出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 2. 安装 Python 3.10 和必要的系统库
# 基础镜像是 Ubuntu 20.04 (Python 3.8)，需要 PPA
RUN apt-get update && \
    apt-get install -y software-properties-common curl git \
    libsecret-1-0 dbus-x11 gnome-keyring && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.10 python3.10-distutils && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. 为 Python 3.10 安装 pip
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10

# 4. 设置工作目录
WORKDIR /gemini

# 5. 复制依赖文件并安装 (利用 Docker 缓存)
COPY requirements_linux.txt .
# 务必指定使用 python3.10 运行 pip
RUN python3.10 -m pip install --no-cache-dir -r requirements_linux.txt

# =======================================================
# 6. 关键步骤：自动给 gemini_webapi 打补丁适配 Python 3.10
# =======================================================
# 使用 'pip show' 获取路径，安全地给 constants.py 打补丁
RUN export LOCATION=$(python3.10 -m pip show gemini-webapi | grep Location | awk '{print $2}') && \
    export PACKAGE_PATH="$LOCATION/gemini_webapi" && \
    echo "Found package at: $PACKAGE_PATH" && \
    sed -i 's/from enum import Enum, IntEnum, StrEnum/from enum import Enum, IntEnum\ntry:\n    from enum import StrEnum\nexcept ImportError:\n    class StrEnum(str, Enum):\n        pass/' "$PACKAGE_PATH/constants.py" && \
    echo "✅ 补丁已应用到: $PACKAGE_PATH/constants.py"

# 7. 复制项目所有文件
COPY . .

# 8. 权限修正 (这是解决 Permission Error 的关键)
# 显式创建需要写入的目录，确保它们存在且权限正确
RUN mkdir -p stored_images conversations uploads static && \
    chown -R kasm-user:kasm-user /gemini

# 9. 切换回 Kasm 默认用户
USER kasm-user

# 10. 声明端口 (6901: Kasm桌面, 8000: API)
EXPOSE 6901 8000

# 保持默认启动命令 (启动 Kasm 桌面环境)