# Python 3.11 基础镜像
FROM python:3.11-slim

# 构建参数（由 GitHub Actions 传入）
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

# 镜像元数据
LABEL org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.authors="Telegram Plan Bot" \
      org.opencontainers.image.url="https://github.com/yourusername/Telegram_Plan_bot" \
      org.opencontainers.image.source="https://github.com/yourusername/Telegram_Plan_bot" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Telegram Plan Bot" \
      org.opencontainers.image.description="A Telegram bot for task planning and reminders"

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 优化：先安装系统依赖（如果需要）
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     gcc \
#     && rm -rf /var/lib/apt/lists/*

# 复制依赖文件（利用 Docker 层缓存）
COPY requirements.txt .

# 安装 Python 依赖
# 使用 --no-cache-dir 减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件（放在后面以利用缓存）
COPY src/ ./src/
COPY main.py .

# 创建数据目录
RUN mkdir -p /app/data

# 设置时区（默认 UTC）
ENV TZ=UTC

# 创建非 root 用户（安全最佳实践）
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# 切换到非 root 用户
USER botuser

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# 启动命令
CMD ["python", "-u", "main.py"]
