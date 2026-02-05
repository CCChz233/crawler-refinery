**Server Deployment (Linux + systemd)**

This document is the shortest reliable path to deploy the scheduler on a server.

**Scope**
- OS: Linux with `systemd`
- Service: `scheduler.py`
- Config: `.env` (secrets) + `config.yaml` (jobs & defaults)

**1. Prepare Code and Python**

1. Create a project directory and place the code there.
```bash
mkdir -p /opt/jobs
cd /opt/jobs
```

2. Create a virtual environment and install dependencies.
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Configure Secrets and Jobs**

1. Create `.env` and fill in required keys.
```bash
cp env.example .env
# Edit .env:
# SUPABASE_URL / SUPABASE_SERVICE_KEY / VOLCANO_API_TOKEN / QWEN_API_KEY
```

2. Edit `config.yaml` and confirm `scheduler.*` and `scheduler.jobs`.

3. Validate locally before running as a service.
```bash
source .venv/bin/activate
python scheduler.py --list
python scheduler.py --test databoard_map_hourly
```

**3. (Optional) Run Catch-up Immediately**

If you want the server to start processing all missing data right after deployment,
run the catch-up pipeline once before enabling the scheduler.

```bash
source .venv/bin/activate
python scripts/catch-up.py --days 0 --batch-size 40 --max-batches 10000
```

If you want this to happen automatically on every service start, you can add
an `ExecStartPre` line in the systemd service (use with caution, it will block
the scheduler until catch-up finishes):

```ini
ExecStartPre=/opt/jobs/.venv/bin/python /opt/jobs/scripts/catch-up.py --days 0 --batch-size 40 --max-batches 10000
```

**4. Create systemd Service**

Create `/etc/systemd/system/crawler-refinery.service` with the content below.
Replace `User`, `Group`, and paths to match your server.

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

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl start crawler-refinery
sudo systemctl enable crawler-refinery
```

**5. Verify and Monitor**

```bash
sudo systemctl status crawler-refinery
sudo journalctl -u crawler-refinery -f
```

Scheduler logs are also written to `logs/scheduler.log`.

**6. Common Operations**

Restart after changing `config.yaml` or `.env`:
```bash
sudo systemctl restart crawler-refinery
```

Stop the service:
```bash
sudo systemctl stop crawler-refinery
```

**Notes**

1. `.env` must be readable by the service user (recommended via `EnvironmentFile`).
2. If you use a venv, always point `ExecStart` to the venv Python.
3. Timezone and cron schedules come from `config.yaml` → `scheduler.timezone` and `scheduler.jobs`.
4. Some scripts read batch parameters from environment variables at import time.
   If you need strict per-job overrides, ensure those scripts honor CLI params or set env vars.
