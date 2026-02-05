**Docker Deployment (Scheduler)**

This document describes how to deploy the scheduler using Docker.

**Scope**
- Runs `scheduler.py` in a container
- Reads secrets from `.env`
- Reads schedule configuration from `config.yaml`
- Writes logs to `./logs`

**1. Prepare Files**

Ensure these files exist in the project root:
- `Dockerfile`
- `docker-compose.yml`
- `.env` (from `env.example`)
- `config.yaml`

**2. Configure Secrets**

```bash
cp env.example .env
# Edit .env:
# SUPABASE_URL / SUPABASE_SERVICE_KEY / VOLCANO_API_TOKEN / QWEN_API_KEY
```

**3. Build and Start**

```bash
docker compose up -d --build
```

Check status and logs:
```bash
docker compose ps
docker compose logs -f
```

**4. Stop / Restart**

```bash
docker compose stop
docker compose start
docker compose restart
```

**5. Run Catch-up Once (Optional)**

If you want to process all missing data immediately after deployment:

```bash
docker compose run --rm jobs-scheduler \
  python scripts/catch-up.py --days 0 --batch-size 40 --max-batches 10000
```

**Notes**

1. `config.yaml` is mounted read-only into the container. Edit it on the host.
2. `.env` is passed to the container via `env_file`.
3. Logs are persisted in `./logs` on the host.
4. If your server requires a custom timezone, set `TZ` in `.env` and (optionally)
   add `environment: ["TZ=Asia/Shanghai"]` to `docker-compose.yml`.
