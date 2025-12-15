# 数据处理脚本配置说明

本仓库包含若干 Python 脚本，用于从内部视图读取事件/新闻/商机数据，经火山引擎 LLM 与 Qwen Embedding 处理后写回 Supabase。配置与运行参数分离，便于快速调整。支持定时自动调度执行。

## 目录结构

```
jobs/
├── config.yaml              # 业务配置（视角、批次、表名、模型、调度任务）
├── config_loader.py         # 统一读取 config.yaml 与 .env
├── scheduler.py             # 定时任务调度器（APScheduler，支持并发控制/重试）
├── requirements.txt         # Python 依赖
├── env.example              # 环境变量模板
├── README.md
│
├── scripts/                 # 业务脚本
│   ├── news_process.py          # 新闻清洗、摘要
│   ├── opportunity-process.py   # 商机清洗、摘要
│   ├── daily-report-process.py  # 竞争情报/日报摘要
│   ├── databoard-map-process.py # 统一事件视图 → fact_events 加工
│   ├── backfill-embeddings.py   # 补充缺失的 embedding 向量
│   └── embedding_utils.py       # Qwen text-embedding-v4 封装
│
├── utils/                   # 公共工具模块
│   ├── llm.py               # LLM 调用封装（火山引擎 API）
│   ├── supabase_utils.py    # Supabase 数据库操作
│   ├── text.py              # 文本处理工具
│   └── cli.py               # CLI 参数工具
│
├── pipelines/               # 管线框架
│   └── base.py              # BasePipeline 抽象基类
│
├── logs/                    # 任务执行日志目录
│
└── deployment/              # 部署配置文件
    ├── crawler-refinery.service      # Linux systemd 服务
    ├── com.chz.crawler-refinery.plist # macOS launchd 服务
    └── README.md
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
cp env.example .env
# 编辑 .env 填写：SUPABASE_URL / SUPABASE_SERVICE_KEY / VOLCANO_API_TOKEN / QWEN_API_KEY
```

### 3. 修改业务配置
根据需要编辑 `config.yaml`（视角、批次大小、表名等）。

### 4. 运行脚本

#### 手动运行单个脚本
```bash
# 日报处理
python scripts/daily-report-process.py

# 统一事件 → fact_events（可指定时间窗、批次）
python scripts/databoard-map-process.py --days 7 --batch-size 15 --sleep 0.2

# 新闻 / 商机处理
python scripts/news_process.py
python scripts/opportunity-process.py

# 补充缺失的 embedding
python scripts/backfill-embeddings.py --batch-size 50 --max-batches 100
python scripts/backfill-embeddings.py --days 30  # 只处理最近30天
python scripts/backfill-embeddings.py --dry-run  # 试运行
```

#### 调试模式（小批次验证）
```bash
BATCH_SIZE=10 MAX_BATCHES=1 DEBUG=1 python daily-report-process.py
```

## 配置说明

### 环境变量 (.env)
仅存放敏感信息，已在 `.gitignore` 中，不要提交到代码仓库。

### 业务配置 (config.yaml)
字段覆盖优先级：**命令行参数 > 环境变量 > config.yaml 默认值**

常用覆盖项：
- `VIEW=management|market|sales|product`
- `DAYS`、`BATCH_SIZE`、`MAX_BATCHES`、`SLEEP_SEC`
- `FORCE_REFRESH`、`ENABLE_NOISE_FILTER`、`DEBUG`

---

## 定时调度服务

`scheduler.py` 是基于 APScheduler 的定时任务调度器，支持：
- ✅ 按 cron 表达式定时执行任务
- ✅ 全局并发控制（可配置 max_workers）
- ✅ 失败自动重试（指数退避）
- ✅ 可配置超时（per-job）
- ✅ 自动传递 days/batch_size/max_batches 参数
- ✅ 常驻后台服务运行
- ✅ 任务日志独立记录
- ✅ 优雅停止（响应 SIGINT/SIGTERM）
- ✅ 测试模式（立即执行指定任务）

### 调度配置示例

在 `config.yaml` 中配置：
```yaml
scheduler:
  enabled: true
  timezone: "Asia/Shanghai"
  log_dir: logs
  
  # 全局默认值
  defaults:
    timeout: 3600       # 默认超时时间（秒）
    days: 7             # 默认处理天数
    batch_size: 20      # 默认批大小
    max_batches: 10     # 默认最大批次数
    misfire_grace_time: 300
    max_instances: 1
  
  # 并发控制
  concurrency:
    max_workers: 1      # 全局最大并发数（1=串行）
  
  # 重试策略
  retry:
    enabled: true
    max_attempts: 2     # 最大重试次数
    initial_delay: 60   # 初始重试延迟（秒）
    backoff_multiplier: 2
    max_delay: 600
  
  # 任务定义
  jobs:
    news_process:
      enabled: true
      cron: "0 8 * * *"
      script: "news_process.py"
      days: 3             # 覆盖默认值
      batch_size: 30
      timeout: 1800       # 30分钟超时
      retry_on_fail: true # 启用重试
    
    opportunity_process:
      enabled: true
      cron: "0 9 * * *"
      script: "opportunity-process.py"
      days: 7
      retry_on_fail: true
    
    databoard_map_hourly:
      enabled: true
      cron: "30 * * * *"
      script: "databoard-map-process.py"
      days: 1
      batch_size: 20
      max_batches: 5
    
    daily_report:
      enabled: true
      cron: "0 23 * * *"
      script: "daily-report-process.py"
      args: ["--mode", "daily"]
```
    news_process:
      enabled: true
      cron: "0 8 * * *"        # 每天 08:00
      script: "news_process.py"
      args: []
    opportunity_process:
      enabled: true
      cron: "0 9 * * *"        # 每天 09:00
      script: "opportunity-process.py"
    databoard_map_hourly:
      enabled: true
      cron: "30 * * * *"       # 每小时 30 分
      script: "databoard-map-process.py"
      args: ["--days", "1", "--batch-size", "20"]
    daily_report:
      enabled: true
      cron: "0 23 * * *"       # 每天 23:00
      script: "daily-report-process.py"
```

### 调度器命令

```bash
# 列出所有可用任务及其配置
python scheduler.py --list

# 立即测试运行指定任务（不等待调度时间）
python scheduler.py --test news_process
python scheduler.py --test daily_report
python scheduler.py --test databoard_map_hourly

# 启动调度器（常驻运行，按 Ctrl+C 停止）
python scheduler.py
```

调度器会自动：
1. 根据 config.yaml 读取每个任务的 `days`、`batch_size`、`max_batches` 配置
2. 自动传递这些参数给脚本（`--days X --batch-size Y --max-batches Z`）
3. 如果任务失败且启用了 `retry_on_fail`，按指数退避策略重试

### 查看任务日志

```bash
# 查看调度器日志
tail -f logs/scheduler.log

# 查看特定任务执行日志
tail -f logs/news_process.log
tail -f logs/daily_report.log
```

### Cron 表达式说明

格式：`分 时 日 月 星期`

| 表达式 | 含义 |
|--------|------|
| `0 8 * * *` | 每天 08:00 |
| `30 * * * *` | 每小时 30 分 |
| `*/15 * * * *` | 每 15 分钟 |
| `0 */2 * * *` | 每 2 小时 |
| `0 0 * * 0` | 每周日 00:00 |
| `0 2 1 * *` | 每月 1 号 02:00 |

---

## 生产部署

### Linux (systemd)

1. 编辑 `deployment/crawler-refinery.service`：
   - 修改 `User` 和 `Group` 为你的用户名
   - 修改 `WorkingDirectory` 为项目绝对路径
   - 修改 `ExecStart` 中的 Python 路径

2. 安装并启动服务：
```bash
sudo cp deployment/crawler-refinery.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start crawler-refinery
sudo systemctl enable crawler-refinery  # 开机自启动
```

3. 管理服务：
```bash
sudo systemctl status crawler-refinery   # 查看状态
sudo journalctl -u crawler-refinery -f   # 查看日志
sudo systemctl restart crawler-refinery  # 重启
sudo systemctl stop crawler-refinery     # 停止
```

### macOS (launchd)

1. 编辑 `deployment/com.chz.crawler-refinery.plist`：
   - 修改 Python 路径（`which python3`）
   - 修改 `WorkingDirectory` 为项目路径

2. 安装并启动服务：
```bash
cp deployment/com.chz.crawler-refinery.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.chz.crawler-refinery.plist
```

3. 管理服务：
```bash
launchctl list | grep crawler-refinery   # 查看状态
tail -f logs/scheduler.log               # 查看日志
launchctl unload ~/Library/LaunchAgents/com.chz.crawler-refinery.plist  # 停止
```

---

## 故障排查

### 任务执行失败
1. 查看任务日志：`logs/<job_name>.log`
2. 手动运行测试：`python scheduler.py --test <job_name>`
3. 直接运行脚本：`python <script_name>.py`
4. 检查 `.env` 中的 API 密钥是否有效

### 调度器无法启动
1. 检查 Python 路径：`which python3`
2. 检查依赖是否安装：`pip install -r requirements.txt`
3. 检查 `.env` 文件是否存在
4. 查看错误日志：`logs/scheduler-stderr.log`

### 任务未按时执行
1. 确认 `config.yaml` 中 `enabled: true`
2. 检查 cron 表达式语法
3. 确认时区设置：`scheduler.timezone: "Asia/Shanghai"`
4. 查看调度器日志确认任务是否被加载
