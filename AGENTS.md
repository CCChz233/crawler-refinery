# Repository Guidelines

## Project Structure & Module Organization
- Root scripts send processed data to Supabase: `daily-report-process.py`, `databoard-map-process.py`, `news_process.py`, `opportunity-process.py`.
- `config_loader.py` reads `config.yaml` (business defaults) and `.env` (secrets) to expose typed accessors for shared parameters.
- `config.yaml` holds processing, table, model, and view settings; `env.example` lists required keys; `embedding_utils.py` wraps Qwen embeddings.
- `requirements.txt` lists dependencies; `news.md` is a sample stub; imports are root-relative—no nested packages.

## Build, Test, and Development Commands
- Install: `pip install -r requirements.txt`.
- Configure secrets: `cp env.example .env` then fill Supabase, Volcano, and Qwen keys.
- Run jobs:
  - `python daily-report-process.py` — summarize competitor signals to daily tables.
  - `python databoard-map-process.py --view management --days 14` — map dashboard events for a view.
  - `python news_process.py` or `python opportunity-process.py` — ingest and summarize news/opportunity feeds.
- Dry-run safely with env vars like `BATCH_SIZE=10 MAX_BATCHES=1 DEBUG=1`.

## Coding Style & Naming Conventions
- Python 3; 4-space indentation; `snake_case` for functions/vars, `UPPER_SNAKE_CASE` for constants.
- Use `logging` instead of `print`; include key parameters in warning/error messages.
- Read settings via `config` properties to honor YAML + `.env` precedence.
- Keep docstrings/comments short; follow existing bilingual tone when touching shared modules.

## Configuration & Security
- Commit `config.yaml`; keep `.env` private and in `.gitignore`. Do not hardcode tokens or endpoints.
- Override defaults via env vars (`VIEW`, `DAYS`, `BATCH_SIZE`, `FORCE_REFRESH`, `ENABLE_NOISE_FILTER`); note overrides in PRs.
- When adding tables or models, update `config.yaml` and add accessors in `config_loader.py`.

## Testing Guidelines
- No automated tests yet; validate via dry runs with small `BATCH_SIZE`/`MAX_BATCHES` and `DEBUG=1`.
- Review logs for skips/failures and verify Supabase writes against staging before full batches.
- For embedding tweaks, call `embedding_utils.build_fact_event_embedding` with a sample payload and confirm the vector length matches `config.embedding_dimensions`.

## Commit & Pull Request Guidelines
- Current history uses short imperative titles (e.g., “Initial commit”); keep commits concise, ≤72 chars.
- Each PR should list: goal, scripts touched, config changes, runtime flags used, and sample command executed. Include Supabase row counts or screenshots when data changes are visible.
- Reference issue IDs when available and mention any follow-ups (tests, staging cleanups).
