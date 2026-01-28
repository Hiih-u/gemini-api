#!/bin/bash

CONTAINERS="gemini-kasm-1 gemini-kasm-2"

echo "🔄 准备重启 Gemini API 服务..."

for CONTAINER in $CONTAINERS; do
    if [ "$(docker ps -q -f name=$CONTAINER)" ]; then
        echo "---------------------------------------"
        echo "正在重启: $CONTAINER"
        docker exec -d $CONTAINER bash -c "cd /gemini && (pkill -f server.py || true) && sleep 2 && eval \$(dbus-launch --sh-syntax) && nohup python3.10 server.py > /proc/1/fd/1 2>&1 &"

        if [ $? -eq 0 ]; then
            echo "✅ $CONTAINER: 重启指令已发送"
        else
            echo "❌ $CONTAINER: 指令发送失败"
        fi
    else
        echo "⚠️  跳过 $CONTAINER (容器未运行)"
    fi
done

echo "---------------------------------------"
echo "🎉 重启完毕。请运行 'docker logs -f gemini-kasm-1' 查看启动日志。"