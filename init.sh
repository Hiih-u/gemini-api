#!/bin/bash

# =================配置区域=================
# 目标用户 UID (容器内为 kasm-user: 1000)
TARGET_UID=1000
TARGET_GID=1000
# compose 文件路径
COMPOSE_FILE="compose.yml"
# =========================================

echo "🚀 开始执行环境初始化检查..."

# 1. 检查 compose.yml 是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ 错误: 当前目录下未找到 $COMPOSE_FILE"
    exit 1
fi

# 2. 从 compose.yml 中提取 Worker 编号
# 逻辑：查找 container_name: gemini-worker-X 或 service name，提取数字
# 这里假设你的服务名格式为 worker-1, worker-2...
WORKER_IDS=$(grep "container_name: gemini-worker-" $COMPOSE_FILE | grep -o "[0-9]\+" | sort | uniq)

if [ -z "$WORKER_IDS" ]; then
    echo "⚠️  未在 compose.yml 中检测到 'gemini-worker-X' 格式的容器名。"
    echo "   将默认创建 worker1 和 worker2 的目录..."
    WORKER_IDS="1 2"
else
    echo "🔍 检测到 Worker 编号: $(echo $WORKER_IDS | tr '\n' ' ')"
fi

echo "---------------------------------------"

# 3. 循环创建目录和文件
for id in $WORKER_IDS; do
    # 构造目录名 (worker-1 -> worker1)
    DIR_NAME="worker${id}"

    echo "📂 正在处理 Worker $id (目录: $DIR_NAME)..."

    # 定义路径
    DATA_PATH="./data/$DIR_NAME"
    PROFILE_PATH="./profiles/$DIR_NAME"
    COOKIE_FILE="$DATA_PATH/cookie_cache.json"

    # A. 创建目录
    mkdir -p "$DATA_PATH/conversations"
    mkdir -p "$DATA_PATH/images"
    mkdir -p "$PROFILE_PATH"

    # B. 关键：创建空文件 (防止 Docker 把它当成目录创建)
    if [ ! -f "$COOKIE_FILE" ]; then
        touch "$COOKIE_FILE"
        echo "   ✅ 创建空文件: cookie_cache.json"
    else
        echo "   ℹ️  文件已存在: cookie_cache.json (跳过)"
    fi
done

echo "---------------------------------------"

# 4. 统一修正权限
echo "🔐 正在修正文件权限 (sudo chown -R 1000:1000)..."

# 确保 server.py 存在
if [ -f "server.py" ]; then
    sudo chmod 644 server.py
fi

# 修正 data 和 profiles 目录的权限
# 注意：如果目录不存在，chown 会报错，所以加个判断
if [ -d "./data" ]; then
    sudo chown -R $TARGET_UID:$TARGET_GID ./data
fi

if [ -d "./profiles" ]; then
    sudo chown -R $TARGET_UID:$TARGET_GID ./profiles
fi

echo "✅ 初始化完成！现在可以放心地运行 'docker compose up -d' 了。"