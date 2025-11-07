# GitHub Actions + Docker Hub 多架构构建指南

本文档说明如何配置 GitHub Actions 自动构建并推送多架构 Docker 镜像到 Docker Hub。

---

## 📋 目录

1. [前置准备](#前置准备)
2. [配置 GitHub Secrets](#配置-github-secrets)
3. [工作流说明](#工作流说明)
4. [缓存优化](#缓存优化)
5. [使用方法](#使用方法)
6. [常见问题](#常见问题)

---

## 前置准备

### 1. Docker Hub 账号

如果还没有 Docker Hub 账号：
1. 访问 https://hub.docker.com/
2. 注册账号
3. 创建访问令牌（Access Token）

### 2. 创建 Docker Hub 访问令牌

**推荐使用访问令牌而非密码**（更安全）：

1. 登录 Docker Hub
2. 点击右上角头像 → **Account Settings**
3. 选择 **Security** → **New Access Token**
4. 输入令牌描述（如 `GitHub Actions`）
5. 权限选择 **Read & Write**
6. 复制生成的令牌（**只显示一次**）

---

## 配置 GitHub Secrets

在你的 GitHub 仓库中配置以下 Secrets：

### 步骤：

1. 进入仓库页面
2. 点击 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret** 添加以下两个密钥：

| Secret 名称 | 值 | 说明 |
|------------|-----|------|
| `DOCKER_USERNAME` | 你的 Docker Hub 用户名 | 例如：`johndoe` |
| `DOCKER_PASSWORD` | Docker Hub 访问令牌 | 前面步骤创建的 Token |

### 示例：

```
DOCKER_USERNAME = myusername
DOCKER_PASSWORD = dckr_pat_abc123xyz...
```

---

## 工作流说明

### 触发条件

工作流会在以下情况下自动触发：

| 事件 | 说明 | 推送镜像 |
|------|------|---------|
| `push` 到 `main` 分支 | 代码合并到主分支 | ✅ 是 |
| `push` tag `v*.*.*` | 发布新版本（如 v1.0.0） | ✅ 是 |
| `pull_request` | PR 请求 | ❌ 否（仅构建测试） |
| `workflow_dispatch` | 手动触发 | ✅ 是 |

### 支持的架构

- ✅ `linux/amd64` (x86_64)
- ✅ `linux/arm64` (ARM 64-bit)

### 生成的镜像标签

根据触发事件自动生成标签：

| 触发事件 | 生成的标签 | 示例 |
|---------|-----------|------|
| `main` 分支 push | `latest`, `main`, `main-<sha>` | `latest`, `main-abc1234` |
| Tag `v1.2.3` | `v1.2.3`, `1.2`, `1`, `latest` | `v1.2.3`, `1.2`, `1` |
| PR #42 | `pr-42` | `pr-42` |

---

## 缓存优化

### 多层缓存策略

工作流使用了**双重缓存**来加速构建：

#### 1. Registry Cache（Docker Hub 缓存）

```yaml
cache-from: type=registry,ref=${{ env.DOCKER_IMAGE }}:buildcache
cache-to: type=registry,ref=${{ env.DOCKER_IMAGE }}:buildcache,mode=max
```

- **优点**：持久化、跨 runner 共享
- **缺点**：需要推送到 Docker Hub
- **适用**：生产构建

#### 2. GitHub Actions Cache

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

- **优点**：速度快、不占用 Docker Hub 存储
- **缺点**：有 10GB 限制、7天未使用会清除
- **适用**：频繁构建

### 缓存效果对比

| 构建类型 | 第一次构建 | 有缓存后 | 节省时间 |
|---------|-----------|---------|---------|
| 无缓存 | ~8-12 分钟 | ~8-12 分钟 | 0% |
| Registry Cache | ~8-12 分钟 | ~3-5 分钟 | ~60% |
| 双重缓存 | ~8-12 分钟 | ~2-4 分钟 | ~70% |

### Dockerfile 优化建议

```dockerfile
# ✅ 好的实践：依赖文件优先复制
COPY requirements.txt .
RUN pip install -r requirements.txt

# 代码文件最后复制（代码变更频繁，依赖变更少）
COPY src/ ./src/
COPY main.py .

# ❌ 不好的实践：一次性复制所有文件
COPY . .
RUN pip install -r requirements.txt
```

---

## 使用方法

### 方式 1：推送代码（自动触发）

```bash
# 推送到 main 分支
git add .
git commit -m "Update code"
git push origin main

# 构建完成后镜像会推送到 Docker Hub
# 镜像标签：yourusername/telegram-planbot:latest
```

### 方式 2：发布版本（推荐）

```bash
# 创建版本标签
git tag v1.0.0
git push origin v1.0.0

# 构建完成后会生成多个标签：
# - yourusername/telegram-planbot:v1.0.0
# - yourusername/telegram-planbot:1.0
# - yourusername/telegram-planbot:1
# - yourusername/telegram-planbot:latest
```

### 方式 3：手动触发

1. 进入 GitHub 仓库页面
2. 点击 **Actions** 标签
3. 选择 **Build and Push Docker Image** 工作流
4. 点击 **Run workflow** 按钮
5. 选择分支，点击 **Run workflow**

### 使用构建好的镜像

#### 拉取镜像

```bash
# 拉取最新版本
docker pull yourusername/telegram-planbot:latest

# 拉取特定版本
docker pull yourusername/telegram-planbot:v1.0.0

# 拉取特定架构（自动选择）
docker pull yourusername/telegram-planbot:latest
# Docker 会自动选择匹配你系统架构的镜像
```

#### 运行容器

```bash
# 使用 Docker Hub 镜像
docker run -d \
  --name telegram-planbot \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.json:/app/config.json:ro \
  yourusername/telegram-planbot:latest
```

#### 更新 docker-compose.yml

```yaml
services:
  planbot:
    # 使用 Docker Hub 镜像而非本地构建
    image: yourusername/telegram-planbot:latest
    # build: .  # 注释掉本地构建

    container_name: telegram-planbot
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./config.json:/app/config.json:ro
    user: "1000:1000"
    environment:
      - TZ=Asia/Shanghai
```

---

## 常见问题

### Q1: 构建失败，提示 "unauthorized: authentication required"

**原因**：Docker Hub 认证失败

**解决方案**：
1. 检查 GitHub Secrets 中的 `DOCKER_USERNAME` 和 `DOCKER_PASSWORD` 是否正确
2. 确认使用的是访问令牌（Access Token），而非密码
3. 检查令牌权限是否包含 **Read & Write**

### Q2: 构建时间太长

**原因**：缓存未生效

**解决方案**：
1. 第一次构建会比较慢（8-12分钟），后续会使用缓存
2. 检查 `buildcache` 标签是否存在：
   ```bash
   docker pull yourusername/telegram-planbot:buildcache
   ```
3. 如果缓存标签不存在，手动触发一次完整构建

### Q3: 如何查看构建日志？

**步骤**：
1. 进入 GitHub 仓库 → **Actions** 标签
2. 点击最近的工作流运行
3. 展开 **Build and push Docker image** 步骤
4. 查看详细日志

### Q4: 如何修改镜像名称？

**步骤**：

编辑 `.github/workflows/docker-build.yml`：

```yaml
env:
  # 修改为你的镜像名称
  DOCKER_IMAGE: your-dockerhub-username/your-image-name
```

或者删除 `env` 部分，使用固定值：

```yaml
- name: Extract Docker metadata
  id: meta
  uses: docker/metadata-action@v5
  with:
    images: your-dockerhub-username/your-image-name  # 直接写死
```

### Q5: 如何禁用某个架构？

编辑 `.github/workflows/docker-build.yml`：

```yaml
- name: Build and push Docker image
  uses: docker/build-push-action@v5
  with:
    # 只构建 amd64
    platforms: linux/amd64

    # 或只构建 arm64
    # platforms: linux/arm64
```

### Q6: 构建后如何验证多架构？

```bash
# 使用 docker manifest 查看
docker manifest inspect yourusername/telegram-planbot:latest

# 输出会显示支持的架构
# "architecture": "amd64"
# "architecture": "arm64"
```

### Q7: 本地如何测试多架构构建？

```bash
# 启用 buildx
docker buildx create --use

# 本地构建多架构（不推送）
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t telegram-planbot:test \
  .

# 本地构建并推送
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t yourusername/telegram-planbot:test \
  --push \
  .
```

---

## 进阶配置

### 添加更多架构

支持更多架构（如 ARM v7）：

```yaml
platforms: linux/amd64,linux/arm64,linux/arm/v7
```

### 自定义构建参数

```yaml
build-args: |
  PYTHON_VERSION=3.11
  BUILD_ENV=production
```

### 添加构建后测试

```yaml
- name: Test Docker image
  run: |
    docker run --rm yourusername/telegram-planbot:latest python -c "import sys; print(sys.version)"
```

---

## 最佳实践

### 1. 版本管理

使用语义化版本（Semantic Versioning）：

```bash
git tag v1.0.0    # 主要版本
git tag v1.1.0    # 次要版本（新功能）
git tag v1.1.1    # 修订版本（Bug 修复）
```

### 2. 分支策略

- `main` 分支：稳定版本，推送后自动构建 `latest` 标签
- `develop` 分支：开发版本，可配置构建 `dev` 标签
- `feature/*` 分支：功能分支，PR 时仅测试构建

### 3. 安全建议

- ✅ 使用访问令牌而非密码
- ✅ 定期轮换访问令牌
- ✅ 使用非 root 用户运行容器（已配置）
- ✅ 限制容器资源（已配置 memory/cpu limits）

---

## 相关链接

- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Docker Buildx 文档](https://docs.docker.com/buildx/working-with-buildx/)
- [Docker Hub](https://hub.docker.com/)
- [Semantic Versioning](https://semver.org/)

---

**编写完成时间**：2025-11-07
