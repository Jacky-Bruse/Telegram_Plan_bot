# Docker 多架构构建 - 快速参考

## 🚀 快速开始（3步配置）

### 1️⃣ 配置 Docker Hub Secrets

在 GitHub 仓库设置中添加：

```
Settings → Secrets and variables → Actions → New repository secret
```

| Secret 名称 | 值 | 获取方式 |
|------------|-----|---------|
| `DOCKER_USERNAME` | Docker Hub 用户名 | 你的登录用户名 |
| `DOCKER_PASSWORD` | Access Token | [创建 Token](https://hub.docker.com/settings/security) |

### 2️⃣ 修改镜像名称

编辑 `.github/workflows/docker-build.yml` 第 12 行：

```yaml
env:
  DOCKER_IMAGE: 你的用户名/telegram-planbot  # 改这里
```

### 3️⃣ 推送触发构建

```bash
# 方式 1：推送代码
git push origin main

# 方式 2：发布版本（推荐）
git tag v1.0.0
git push origin v1.0.0

# 方式 3：手动触发
# GitHub 网页 → Actions → Run workflow
```

---

## 📊 构建状态

查看构建进度：
```
GitHub 仓库 → Actions 标签
```

构建时间：
- 首次构建：~8-12 分钟
- 有缓存后：~2-4 分钟

---

## 🐳 使用镜像

### 拉取镜像

```bash
docker pull 你的用户名/telegram-planbot:latest
```

### 更新 docker-compose.yml

```yaml
services:
  planbot:
    image: 你的用户名/telegram-planbot:latest  # 使用远程镜像
    # build: .  # 注释掉本地构建
```

### 运行

```bash
docker-compose up -d
```

---

## 🏷️ 版本标签

| 触发方式 | 生成的标签 |
|---------|-----------|
| Push to `main` | `latest`, `main` |
| Tag `v1.2.3` | `v1.2.3`, `1.2`, `1`, `latest` |

---

## 🔧 故障排查

### 构建失败？

✅ 检查 Secrets 是否正确配置
✅ 检查 Docker Hub Token 是否有 **Read & Write** 权限
✅ 查看 Actions 日志获取详细错误

### 镜像拉取失败？

✅ 检查镜像名称是否正确
✅ 确认构建已成功完成
✅ 检查 Docker Hub 仓库是否公开

---

## 📚 完整文档

详细说明请查看：`docs/DOCKER_BUILD_GUIDE.md`

---

**支持的架构**：
- ✅ linux/amd64 (x86_64)
- ✅ linux/arm64 (ARM 64-bit)

**缓存策略**：双重缓存（Registry + GitHub Actions）

**安全性**：非 root 用户运行
