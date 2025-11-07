#!/bin/bash
# 快速部署脚本

set -e

echo "=================================="
echo "Telegram Plan Bot 快速部署"
echo "=================================="
echo

# 检查 config.json 是否存在
if [ ! -f "config.json" ]; then
    echo "⚠️  未找到 config.json"
    echo "📝 正在创建配置文件..."

    if [ -f "config.example.json" ]; then
        cp config.example.json config.json
        echo "✅ 已创建 config.json（基于 config.example.json）"
        echo
        echo "⚠️  请编辑 config.json 并填入你的 Bot Token："
        echo "   vi config.json"
        echo "   或"
        echo "   nano config.json"
        echo
        read -p "编辑完成后按 Enter 继续..."
    else
        echo "❌ 错误：config.example.json 不存在"
        exit 1
    fi
fi

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ 错误：未安装 Docker"
    echo "请先安装 Docker：https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ 错误：未安装 docker-compose"
    echo "请先安装 docker-compose：https://docs.docker.com/compose/install/"
    exit 1
fi

# 创建数据目录
echo "📁 创建数据目录..."
mkdir -p data

# 构建并启动
echo "🐳 构建 Docker 镜像..."
docker-compose build

echo
echo "🚀 启动服务..."
docker-compose up -d

echo
echo "✅ 部署完成！"
echo
echo "📊 查看状态："
echo "   docker-compose ps"
echo
echo "📋 查看日志："
echo "   docker-compose logs -f"
echo
echo "🛑 停止服务："
echo "   docker-compose down"
echo
echo "🔄 重启服务："
echo "   docker-compose restart"
echo
echo "=================================="
echo "✨ 现在可以在 Telegram 中搜索你的 Bot 并发送 /start 初始化！"
echo "=================================="
