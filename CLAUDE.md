# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Chinese data processing pipeline that fetches raw event/news/opportunity data from Supabase, processes it through Volcano Engine LLM (DeepSeek-v3) and Qwen Embedding APIs, then writes enriched results back to Supabase fact tables. The system supports scheduled execution via APScheduler.

## Key Commands

### Setup
```bash
pip install -r requirements.txt
cp env.example .env  # Then edit with SUPABASE_URL, SUPABASE_SERVICE_KEY, VOLCANO_API_TOKEN, QWEN_API_KEY
```

### Running Scripts
```bash
# Daily report generation (fact_events → dashboard_daily_events)
python scripts/daily-report-process.py
python scripts/daily-report-process.py --mode weekly   # 15-day summaries
python scripts/daily-report-process.py --mode monthly  # Monthly summaries

# Unified event processing (raw tables → fact_events with LLM summaries + embeddings)
python scripts/databoard-map-process.py --days 7 --batch-size 15 --sleep 0.2
python scripts/databoard-map-process.py --source-mode raw  # Read from raw tables
python scripts/databoard-map-process.py --source-mode view  # Read from unified view

# Filter by type
python scripts/databoard-map-process.py --include-types news
python scripts/databoard-map-process.py --include-types news,competitor

# Backfill missing embeddings
python scripts/backfill-embeddings.py --batch-size 50 --max-batches 100
python scripts/backfill-embeddings.py --days 30 --dry-run
```

### Scheduler
```bash
# List all configured jobs
python scheduler.py --list

# Test run a specific job immediately
python scheduler.py --test databoard_map_hourly
python scheduler.py --test daily_report

# Start scheduler (runs continuously)
python scheduler.py
```

### Debugging
```bash
# Small batches for testing
BATCH_SIZE=10 MAX_BATCHES=1 DEBUG=1 python scripts/daily-report-process.py
```

## Architecture

### Configuration System (`config_loader.py`)
- **config.yaml**: Non-sensitive business config (tables, models, batch sizes, scheduler jobs)
- **.env**: Sensitive credentials (API keys, URLs) - never commit this
- **Precedence**: CLI args > environment variables > config.yaml defaults

Key configuration properties accessed via `config` singleton:
- `config.view`, `config.days`, `config.batch_size`, `config.max_batches`
- `config.supabase_url`, `config.supabase_key`, `config.volcano_api_token`, `config.qwen_api_key`
- `config.llm_model`, `config.embedding_model`, `config.llm_endpoint`
- `config.raw_news_table`, `config.raw_competitors_news_table`, `config.raw_opportunity_table`
- `config.fact_ddr_table`, `config.daily_reports_table`

### Core Modules

**`pipelines/base.py`**: Abstract `BasePipeline` class for batch processing
- Subclasses implement: `fetch_batch()`, `process_record()`, `save_result()`
- Handles batching, progress tracking, statistics, dry-run mode

**`utils/llm.py`**: `LLMClient` wrapping Volcano Engine API (OpenAI-compatible)
- `chat()`: Basic LLM call
- `chat_json()`: Forces JSON response with schema validation
- Auto-retry with exponential backoff

**`utils/supabase_utils.py`**: Database helpers
- `get_supabase_client()`: Singleton client
- `batch_upsert()`: Batch insert/update
- `fetch_records()`: Query builder pattern

**`scripts/embedding_utils.py`**: Qwen text-embedding-v4 wrapper
- `build_fact_event_embedding()`: Generates embeddings for event records

### Main Scripts

**`scripts/databoard-map-process.py`**: Core ETL pipeline
- Reads from raw tables (`00_news`, `00_competitors_news`, `00_opportunity`) or unified view (`v_events_ready`)
- Calls LLM for: summary, keywords, country/province extraction, action suggestions
- Generates Qwen embeddings
- Writes to `fact_events` with deduplication via `row_hash`

**`scripts/daily-report-process.py`**: Dashboard report generation
- Reads from `fact_events` (or legacy `analysis_results`)
- Generates prioritized briefs per view (management/market/sales/product)
- Writes to `dashboard_daily_events` (or `dashboard_daily_reports`)
- Modes: daily (per-event), weekly (15-day summaries), monthly (30-day summaries)

### Scheduler (`scheduler.py`)

APScheduler-based task runner with:
- Global concurrency control (`max_workers`)
- Per-job timeout and retry (exponential backoff)
- Auto-passes `--days`, `--batch-size`, `--max-batches` to scripts
- Graceful shutdown on SIGINT/SIGTERM

Jobs defined in `config.yaml` under `scheduler.jobs`.

### Data Flow

```
Raw Tables (00_news/00_competitors_news/00_opportunity)
    ↓ (databoard-map-process.py)
fact_events (with LLM summaries + embeddings)
    ↓ (daily-report-process.py)
dashboard_daily_events (per-view reports)
```

### Event Types & Categories

- `news` → "行业新闻"
- `competitor` → "竞品动态"
- `opportunity` → "销售机会"
- `paper` → "科技论文"

## Important Notes

### Chinese Language Handling
- LLM prompts enforce Chinese output (`PROMPT_SUMMARY`, `FACT_PROMPT_TPL`)
- Fallback translation (`llm_fix_to_zh`) if LLM returns English
- Province mapping uses Chinese names from `dim_cn_region`

### Geographic Inference
1. LLM extracts country/province from text
2. Fallback to URL/domain inference (`.gov.cn` province codes, ccTLD for countries)
3. Province codes mapped via `dim_cn_region`, countries via `dim_country`

### Adding New Scripts
1. Import `config_loader.config` for all settings
2. Use `utils.supabase_utils.get_supabase_client()` for DB access
3. Use `utils.llm.LLMClient` or `llm_chat_json()` for LLM calls
4. Follow CLI pattern: argparse with `--days`, `--batch-size`, `--max-batches`

### Scheduler Job Configuration
Jobs in `config.yaml` require:
- `enabled`: true/false
- `cron`: 5-field cron expression
- `script`: path relative to project root
- Optional: `days`, `batch_size`, `max_batches`, `timeout`, `retry_on_fail`
