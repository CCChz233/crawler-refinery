# 数据处理脚本配置说明

本仓库包含若干 Python 脚本，用于从原始表读取事件/新闻/商机数据，经火山引擎 LLM 与 Qwen Embedding 处理后写回 Supabase（统一落到 fact_events）。配置与运行参数分离，便于快速调整。支持定时自动调度执行。

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
│   ├── catch-up.py              # 统一补齐入口（按顺序串行执行各脚本）
│   ├── news_process.py          # 新闻清洗、摘要
│   ├── opportunity-process.py   # 商机清洗、摘要
│   ├── daily-report-process.py  # 竞争情报/日报摘要
│   ├── databoard-map-process.py # 原始表 → fact_events（含新闻摘要/建议/地理/向量）
│   ├── backfill-embeddings.py   # 补充缺失的 embedding 向量
│   ├── monthly-series-process.py# 00_* → 11_* 月度序列统计
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

#### 统一补齐（推荐）
```bash
# 默认：按顺序补齐缺失数据（不重算已有结果）
python scripts/catch-up.py --days 0 --batch-size 40 --max-batches 10000

# 只跑部分步骤（逗号分隔）
python scripts/catch-up.py --steps databoard_map,news,opportunity

# 试运行（只打印命令）
python scripts/catch-up.py --dry-run

# 强制重算（会覆盖已有结果）
python scripts/catch-up.py --process-all
```

默认步骤顺序：
`databoard_map → news → opportunity → daily_report → backfill_embeddings → monthly_series`

> 说明：
> - `--days 0` 表示不限时间窗。
> - `--max-batches` 需要给正整数（`monthly_series` 支持 0=不限制，其它脚本不支持）。
> - `daily-report-process.py` 的批次参数在运行时通过环境变量读取；`catch-up.py` 已自动设置。

#### 手动运行单个脚本
```bash
# 日报处理
python scripts/daily-report-process.py

# 统一处理（RAW 默认：00_news / 00_competitors_news / 00_opportunity）
python scripts/databoard-map-process.py --days 7 --batch-size 15 --sleep 0.2

# 仅处理某一类（可选）
python scripts/databoard-map-process.py --days 7 --include-types news
python scripts/databoard-map-process.py --days 7 --include-types competitor
python scripts/databoard-map-process.py --days 7 --include-types opportunity

# 补充缺失的 embedding
python scripts/backfill-embeddings.py --batch-size 50 --max-batches 100
python scripts/backfill-embeddings.py --days 30  # 只处理最近30天
python scripts/backfill-embeddings.py --dry-run  # 试运行

# 00_* → 11_* 月度统计
python scripts/monthly-series-process.py --days 0 --batch-size 100 --max-batches 10000
```

#### 调试模式（小批次验证）
```bash
BATCH_SIZE=10 MAX_BATCHES=1 DEBUG=1 python scripts/daily-report-process.py
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

fact_events 相关：
- `databoard-map-process.py` 会直接写入 `fact_events`
- `news_type` 为单独列，可直接 SQL 过滤

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
      enabled: false
      cron: "0 8 * * *"
      script: "scripts/news_process.py"
      days: 3             # 覆盖默认值
      batch_size: 30
      timeout: 1800       # 30分钟超时
      retry_on_fail: true # 启用重试
    
    opportunity_process:
      enabled: false
      cron: "0 9 * * *"
      script: "scripts/opportunity-process.py"
      days: 7
      retry_on_fail: true
    
    databoard_map_hourly:
      enabled: true
      cron: "30 * * * *"
      script: "scripts/databoard-map-process.py"
      days: 1
      batch_size: 20
      max_batches: 5
      args: ["--source-mode", "raw"]
    
    daily_report:
      enabled: true
      cron: "0 23 * * *"
      script: "scripts/daily-report-process.py"
      args: ["--mode", "daily"]
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

### Linux (systemd) 快速部署

完整服务器部署文档见：`deployment/SERVER_DEPLOYMENT.md`
Docker 部署见：`deployment/DOCKER_DEPLOYMENT.md`

下面是面向服务器的最短可用流程。将路径和用户替换为你的实际值。

1. 创建目录并安装依赖
```bash
mkdir -p /opt/jobs
cd /opt/jobs
# 假设代码已放到 /opt/jobs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 配置环境变量
```bash
cp env.example .env
# 编辑 .env，填写 SUPABASE_URL / SUPABASE_SERVICE_KEY / VOLCANO_API_TOKEN / QWEN_API_KEY
```

3. 校验配置与任务
```bash
source .venv/bin/activate
python scheduler.py --list
# 可选：先手动跑一个任务验证
python scheduler.py --test databoard_map_hourly
```

4. 部署后立即处理所有任务（可选）
```bash
source .venv/bin/activate
python scripts/catch-up.py --days 0 --batch-size 40 --max-batches 10000
```

5. 配置 systemd 服务
推荐使用一个专用 service 文件（可在 `deployment/crawler-refinery.service` 基础上修改）。

**推荐模板（示例）**：
```ini
[Unit]
Description=Crawler Refinery Task Scheduler
After=network.target

[Service]
Type=simple
User=jobs
Group=jobs
WorkingDirectory=/opt/jobs
EnvironmentFile=/opt/jobs/.env
ExecStart=/opt/jobs/.venv/bin/python /opt/jobs/scheduler.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

将其保存为 `/etc/systemd/system/crawler-refinery.service`，然后执行：
```bash
sudo systemctl daemon-reload
sudo systemctl start crawler-refinery
sudo systemctl enable crawler-refinery
```

6. 查看状态与日志
```bash
sudo systemctl status crawler-refinery
sudo journalctl -u crawler-refinery -f
```

> 注意：
> - `.env` 必须可被 `systemd` 读取，推荐使用 `EnvironmentFile=/opt/jobs/.env`。
> - 若使用 venv，请确保 `ExecStart` 指向 venv 的 python。
> - `config.yaml` 中的 `scheduler.*` 决定定时任务与时区。

如果你更倾向直接改模板文件：
```bash
sudo cp deployment/crawler-refinery.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start crawler-refinery
sudo systemctl enable crawler-refinery
sudo journalctl -u crawler-refinery -f
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
