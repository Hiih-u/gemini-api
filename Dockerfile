# 1. 使用基础镜像 (自带 Python 3.10)
FROM kasmweb/desktop:1.18.0

# 切换 root 用户进行安装
USER root

# 2. 安装系统级依赖 (用于 browser-cookie3 读取 Cookie)
RUN apt-get update && \
    apt-get install -y \
    libsecret-1-0 \
    dbus-x11 \
    gnome-keyring \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 3. 设置工作目录
WORKDIR /gemini

# 4. 安装 Python 依赖
COPY requirements_linux.txt .
# 注意：这里直接使用系统自带的 python3 (即 3.10)
RUN pip3 install --no-cache-dir -r requirements_linux.txt

# =======================================================
# 5. 关键步骤：自动给 gemini_webapi 打补丁适配 Python 3.10
# =======================================================
# 原理：找到 constants.py，把 "from enum import ..., StrEnum" 替换为兼容代码
RUN export PACKAGE_PATH=$(python3 -c "import gemini_webapi; import os; print(os.path.dirname(gemini_webapi.__file__))") && \
    sed -i 's/from enum import Enum, IntEnum, StrEnum/from enum import Enum, IntEnum\ntry:\n    from enum import StrEnum\nexcept ImportError:\n    class StrEnum(str, Enum):\n        pass/' "$PACKAGE_PATH/constants.py" && \
    echo "✅ Patch applied to $PACKAGE_PATH/constants.py"

# 6. 复制项目代码
COPY . .

# 7. 权限修正 (确保 kasm-user 能写入数据)
RUN chown -R kasm-user:kasm-user /gemini

# 8. 切换回普通用户
USER kasm-user

# 9. 声明端口
EXPOSE 6901 8000

# 保持默认启动命令 (进入桌面)