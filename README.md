# Telegram 计划提醒机器人

基于 Telegram Bot 的个人任务计划管理工具，严格按照 `docs/planbot-checklist.v1.0.md` 规范实现。

## 功能特性

- ✅ **智能日期解析**：支持多种中文日期格式（今天/明天/后天/周X/下周X/MM-DD/+Nd等）
- 📅 **定时提醒**：晚间例行核对（22:00）+ 早间清单（08:30）
- 🔘 **交互式操作**：完成/取消/顺延任务，支持按钮点击，任务按视图内从 #1 开始编号
- 🌍 **多时区支持**：自动适配用户时区，精确计算"今天/明天"
- 💾 **数据持久化**：SQLite 本地存储，支持 Docker 卷挂载
- 🔄 **停机恢复**：重启后自动补发昨日未清任务

## 快速开始

### 1. 准备工作

#### 1.1 创建 Telegram Bot

1. 在 Telegram 中搜索 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 创建新机器人
3. 按提示设置名称和用户名
4. 保存生成的 **Bot Token**（格式：`123456789:ABCdefGHIjklMNOpqrsTUVwxyz`）

#### 1.2 克隆项目

```bash
git clone <repository-url>
cd Telegram_Plan_bot
```

### 2. 配置

#### 2.1 创建配置文件

```bash
cp config.example.json config.json
```

#### 2.2 编辑 `config.json`

```json
{
  "bot": {
    "token": "YOUR_BOT_TOKEN_HERE"  // 替换为你的 Bot Token
  },
  "database": {
    "path": "data/bot.db"
  },
  "defaults": {
    "timezone": "Asia/Shanghai",
    "evening_hour": 22,
    "evening_minute": 0,
    "morning_hour": 8,
    "morning_minute": 30
  },
  "logging": {
    "level": "INFO",
    "file": "data/bot.log"
  }
}
```

### 3. 部署方式

#### 方式一：Docker Compose（推荐）

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

#### 方式二：Docker

```bash
# 构建镜像
docker build -t telegram-planbot .

# 运行容器
docker run -d \
  --name telegram-planbot \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config.json:/app/config.json:ro \
  telegram-planbot

# 查看日志
docker logs -f telegram-planbot
```

#### 方式三：本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 4. 首次使用

1. 在 Telegram 中搜索你的机器人
2. 发送 `/start` 初始化
3. 开始使用！

## 使用指南

### 命令列表

| 命令 | 功能 | 示例 |
|------|------|------|
| `/start` | 初始化机器人 | `/start` |
| `/add` | 录入计划（多行=多任务） | `/add` |
| `/today` | 查看今日清单 | `/today` |
| `/week` | 查看未来 7 天 | `/week` |
| `/setevening HH:MM` | 设置晚间时间 | `/setevening 22:00` |
| `/setmorning HH:MM` | 设置早间时间 | `/setmorning 08:30` |
| `/setmorning off` | 关闭早间清单 | `/setmorning off` |
| `/timezone <IANA>` | 设置时区 | `/timezone Asia/Shanghai` |

### 任务编号规则

任务编号按**当前视图内**从 #1 开始顺序编号，而不是使用数据库ID：

- **/today**：今日任务独立编号 #1, #2, #3...
- **/week**：每个日期组内独立编号
  ```
  【2025-11-07 (今天)】
  • #1 买菜
  • #2 去银行

  【2025-11-08 (明天)】
  • #1 检查服务器
  • #2 还信用卡
  ```
- **日终核对/早间清单**：当次推送的任务独立编号

> 💡 **说明**：编号仅用于显示和识别，按钮操作（完成/取消/顺延）使用内部ID确保准确性

### 日期格式支持

#### 中文关键词
- **今天/明天/后天**：`今天买菜`、`明天开会`
- **周X**：`周五下午开会`（下一个周五，不含今天）
- **下周X**：`下周一客户回访`（下周对应星期几）

#### 显式日期
- **YYYY-MM-DD**：`2025-11-15 固件更新`
- **MM-DD**：`11-15 固件更新`（默认当年）
- **MM/DD**：`11/15 固件更新`
- **MM.DD**：`11.15 固件更新`

#### 偏移量
- **+Nd**：`+2d RAID 校验`（2天后）
- **+Nw**：`+1w 月度总结`（1周后）

#### 默认行为
- **未指定日期**：默认归档到「明天」

### 日常流程

#### 晚间例行（22:00）

1. **日终核对**：推送当日到期任务
   - 每个任务有三个按钮：`✅ 完成` / `⏳ 未完成` / `🗑 取消`
   - 点击「⏳ 未完成」后可选择顺延：`+1 天` / `+2 天`

2. **新计划征集**：询问是否录入新计划
   - `现在录入`：进入一次性输入模式
   - `稍后再说`：当晚不再询问

#### 早间清单（08:30）

- 推送当日待办任务
- 若无任务则不发送（静默）

#### 随时录入

发送 `/add` 进入一次性输入模式，每行一个任务：

```
明天 买菜
周五 下午 3 点开会
+2d 跑 RAID 校验
下周一 客户回访
11-15 NAS 固件更新
```

回执示例：

```
已创建 5 项：
• 明天 买菜  →  2025-11-09
• 周五 下午 3 点开会  →  2025-11-14
• +2d 跑 RAID 校验  →  2025-11-10
• 下周一 客户回访  →  2025-11-10
• 11-15 NAS 固件更新  →  2025-11-15
```

## 数据备份

### 手动备份

```bash
# 备份数据库
cp data/bot.db data/bot.db.backup.$(date +%Y%m%d)

# 或使用 tar 打包
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

### 自动备份（推荐）

在 NAS 上设置定时任务：

```bash
# 每天凌晨 2 点备份，保留 30 天
0 2 * * * /path/to/backup.sh
```

`backup.sh` 示例：

```bash
#!/bin/bash
BACKUP_DIR="/path/to/backups"
DATA_DIR="/path/to/Telegram_Plan_bot/data"

# 创建备份
tar -czf "$BACKUP_DIR/planbot-$(date +\%Y\%m\%d).tar.gz" -C "$DATA_DIR" .

# 删除 30 天前的备份
find "$BACKUP_DIR" -name "planbot-*.tar.gz" -mtime +30 -delete
```

## 故障排查

### 1. Bot 无响应

```bash
# 查看日志
docker-compose logs -f

# 或
docker logs -f telegram-planbot
```

### 2. 时区不正确

检查配置文件中的 `timezone` 设置：

```json
{
  "defaults": {
    "timezone": "Asia/Shanghai"  // 使用 IANA 时区名称
  }
}
```

常见时区：
- 北京时间：`Asia/Shanghai`
- 东京时间：`Asia/Tokyo`
- 纽约时间：`America/New_York`
- 伦敦时间：`Europe/London`

### 3. 数据库损坏

```bash
# 停止容器
docker-compose down

# 恢复备份
cp data/bot.db.backup.YYYYMMDD data/bot.db

# 重启
docker-compose up -d
```

### 4. 调度任务未触发

检查调度器是否启动：

```bash
# 查看日志中是否有 "Scheduler ready"
docker-compose logs | grep "Scheduler ready"
```

## 开发与测试

### 运行单元测试

```bash
# 测试日期解析器
python -m unittest tests.test_date_parser -v

# 测试所有模块（待实现更多测试）
python -m unittest discover -s tests -v
```

### 调试模式

修改 `config.json` 中的日志级别：

```json
{
  "logging": {
    "level": "DEBUG"  // 输出详细日志
  }
}
```

## 技术架构

### 技术栈

- **Python 3.11+**
- **python-telegram-bot 20.7**：Telegram Bot API
- **SQLAlchemy 2.0**：ORM 和数据库管理
- **APScheduler 3.10**：定时任务调度
- **pytz**：时区处理

### 目录结构

```
Telegram_Plan_bot/
├── src/
│   ├── bot/              # Bot 交互层
│   │   ├── handlers.py   # 命令处理器
│   │   ├── callbacks.py  # 回调处理器
│   │   └── messages.py   # 消息文案模板
│   ├── core/             # 核心逻辑
│   │   ├── date_parser.py    # 日期解析引擎
│   │   ├── state_machine.py  # 任务状态机
│   │   └── scheduler.py      # 定时调度系统
│   ├── db/               # 数据层
│   │   ├── models.py     # 数据模型
│   │   ├── database.py   # 数据库操作
│   │   └── init_db.py    # 数据库初始化
│   ├── utils/            # 工具模块
│   │   ├── config.py     # 配置管理
│   │   ├── logger.py     # 日志系统
│   │   └── validators.py # 验证器
│   └── constants.py      # 常量定义
├── tests/                # 测试
│   └── test_date_parser.py
├── docs/                 # 文档
│   └── planbot-checklist.v1.0.md
├── main.py               # 主程序入口
├── requirements.txt      # Python 依赖
├── Dockerfile            # Docker 镜像
├── docker-compose.yml    # Docker Compose 配置
├── config.example.json   # 配置示例
└── README.md             # 项目文档
```

## 许可证

MIT License

## 致谢

本项目严格按照 `docs/planbot-checklist.v1.0.md` 开发清单实现，感谢原作者的详细规范。
