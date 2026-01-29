#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monthly series counts for policy news, industry news, and bids.
"""

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from dateutil import parser as dateparser

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for older Python
    ZoneInfo = None

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config_loader import config
from utils.supabase_utils import batch_upsert, get_supabase_client


logger = logging.getLogger("monthly-series")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monthly series aggregation for dashboard charts.")
    parser.add_argument("--days", type=int, default=config.days, help="Scan recent N days (0=all).")
    parser.add_argument("--months", type=int, default=0, help="Override --days with last N months.")
    parser.add_argument("--batch-size", type=int, default=config.batch_size, help="Rows per fetch batch.")
    parser.add_argument("--max-batches", type=int, default=config.max_batches, help="Max fetch batches (0=unlimited).")
    parser.add_argument("--timezone", default=config.scheduler_timezone, help="Timezone for grouping months.")
    parser.add_argument("--include-competitors", dest="include_competitors", action="store_true")
    parser.add_argument("--exclude-competitors", dest="include_competitors", action="store_false")
    parser.set_defaults(include_competitors=True)
    parser.add_argument("--industry-from-news", dest="industry_from_news", action="store_true")
    parser.add_argument("--no-industry-from-news", dest="industry_from_news", action="store_false")
    parser.set_defaults(industry_from_news=True)
    parser.add_argument("--fill-missing", dest="fill_missing", action="store_true")
    parser.add_argument("--no-fill-missing", dest="fill_missing", action="store_false")
    parser.set_defaults(fill_missing=True)
    parser.add_argument("--fallback-to-created-at", dest="fallback_to_created_at", action="store_true")
    parser.add_argument("--no-fallback-to-created-at", dest="fallback_to_created_at", action="store_false")
    parser.set_defaults(fallback_to_created_at=True)
    parser.add_argument("--news-table", default=config.raw_news_table)
    parser.add_argument("--competitor-table", default=config.raw_competitors_news_table)
    parser.add_argument("--opportunity-table", default=config.raw_opportunity_table)
    parser.add_argument("--bid-table", default=config.bid_monthly_table)
    parser.add_argument("--industry-table", default=config.industry_news_monthly_table)
    parser.add_argument("--policy-table", default=config.policy_news_monthly_table)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def resolve_timezone(tz_name: str):
    if ZoneInfo is None:
        logger.warning("zoneinfo unavailable, falling back to UTC timezone.")
        return timezone.utc
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:
        logger.warning("Invalid timezone %s, falling back to UTC. err=%s", tz_name, exc)
        return ZoneInfo("UTC")


def first_day_of_month(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def resolve_range(now: datetime, days: int, months: int) -> Tuple[Optional[datetime], datetime]:
    if months and months > 0:
        start = first_day_of_month(add_months(now, -(months - 1)))
        return start, now
    if days and days > 0:
        start = first_day_of_month(now - timedelta(days=days))
        return start, now
    return None, now


def iter_month_keys(start: datetime, end: datetime) -> Iterable[Tuple[int, int]]:
    cursor = first_day_of_month(start)
    last = first_day_of_month(end)
    while cursor <= last:
        yield cursor.year, cursor.month
        cursor = add_months(cursor, 1)


def format_dt(dt: datetime, with_tz: bool) -> str:
    if with_tz:
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    local = dt.astimezone(dt.tzinfo) if dt.tzinfo else dt
    return local.replace(tzinfo=None, microsecond=0).isoformat(sep=" ")


def parse_dt(value: Optional[object], tzinfo: timezone) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = dateparser.isoparse(str(value))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tzinfo)
    return dt.astimezone(tzinfo)


def classify_bucket(
    raw_type: Optional[str],
    event_type: str,
    include_competitors: bool,
) -> Optional[str]:
    if event_type == "competitor":
        return "industry" if include_competitors else None
    if event_type == "news":
        raw = (raw_type or "").strip()
        if raw == "政策新闻":
            return "policy"
        if raw == "行业动态":
            return "industry"
    return None


def get_row_time(
    row: Dict[str, object],
    tzinfo: timezone,
    fallback_to_created_at: bool,
    allow_fallback: bool,
) -> Optional[datetime]:
    dt = parse_dt(row.get("publish_time"), tzinfo)
    if dt is not None:
        return dt
    if fallback_to_created_at and allow_fallback:
        return parse_dt(row.get("created_at"), tzinfo)
    return None


def fetch_batches(
    table: str,
    columns: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    batch_size: int,
    max_batches: int,
    time_col: str,
    time_with_tz: bool,
    null_publish_time: bool,
):
    sb = get_supabase_client()
    start_iso = format_dt(start_dt, time_with_tz) if start_dt else None
    end_iso = format_dt(end_dt, time_with_tz) if end_dt else None
    offset = 0
    batches = 0
    while True:
        query = sb.table(table).select(columns)
        if null_publish_time:
            query = query.is_(time_col, "null")
            if start_iso:
                query = query.gte("created_at", start_iso)
            if end_iso:
                query = query.lte("created_at", end_iso)
            order_col = "created_at"
        else:
            if start_iso:
                query = query.gte(time_col, start_iso)
            if end_iso:
                query = query.lte(time_col, end_iso)
            order_col = time_col
        query = query.order(order_col, desc=False).range(offset, offset + batch_size - 1)
        result = query.execute()
        rows = result.data or []
        if not rows:
            break
        yield rows
        offset += batch_size
        batches += 1
        if max_batches and batches >= max_batches:
            logger.warning(
                "Reached max_batches=%s for table=%s null_publish_time=%s",
                max_batches,
                table,
                null_publish_time,
            )
            break


def aggregate_news_table(
    table: str,
    event_type: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    batch_size: int,
    max_batches: int,
    tzinfo: timezone,
    time_with_tz: bool,
    include_competitors: bool,
    industry_from_news: bool,
    fallback_to_created_at: bool,
    counts: Dict[str, Dict[Tuple[int, int], int]],
) -> int:
    processed = 0
    columns = "publish_time,created_at,news_type"
    for rows in fetch_batches(
        table,
        columns,
        start_dt,
        end_dt,
        batch_size,
        max_batches,
        "publish_time",
        time_with_tz,
        False,
    ):
        for row in rows:
            dt = get_row_time(row, tzinfo, fallback_to_created_at, allow_fallback=False)
            if dt is None:
                continue
            bucket = classify_bucket(row.get("news_type"), event_type, include_competitors)
            if bucket == "industry" and event_type == "news" and not industry_from_news:
                continue
            if bucket:
                key = (dt.year, dt.month)
                counts[bucket][key] = counts[bucket].get(key, 0) + 1
                processed += 1
    if fallback_to_created_at:
        for rows in fetch_batches(
            table,
            columns,
            start_dt,
            end_dt,
            batch_size,
            max_batches,
            "publish_time",
            time_with_tz,
            True,
        ):
            for row in rows:
                dt = get_row_time(row, tzinfo, fallback_to_created_at, allow_fallback=True)
                if dt is None:
                    continue
                bucket = classify_bucket(row.get("news_type"), event_type, include_competitors)
                if bucket == "industry" and event_type == "news" and not industry_from_news:
                    continue
                if bucket:
                    key = (dt.year, dt.month)
                    counts[bucket][key] = counts[bucket].get(key, 0) + 1
                    processed += 1
    return processed


def aggregate_simple_table(
    table: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    batch_size: int,
    max_batches: int,
    tzinfo: timezone,
    time_with_tz: bool,
    fallback_to_created_at: bool,
    target_bucket: str,
    counts: Dict[str, Dict[Tuple[int, int], int]],
) -> int:
    processed = 0
    columns = "publish_time,created_at"
    for rows in fetch_batches(
        table,
        columns,
        start_dt,
        end_dt,
        batch_size,
        max_batches,
        "publish_time",
        time_with_tz,
        False,
    ):
        for row in rows:
            dt = get_row_time(row, tzinfo, fallback_to_created_at, allow_fallback=False)
            if dt is None:
                continue
            key = (dt.year, dt.month)
            counts[target_bucket][key] = counts[target_bucket].get(key, 0) + 1
            processed += 1
    if fallback_to_created_at:
        for rows in fetch_batches(
            table,
            columns,
            start_dt,
            end_dt,
            batch_size,
            max_batches,
            "publish_time",
            time_with_tz,
            True,
        ):
            for row in rows:
                dt = get_row_time(row, tzinfo, fallback_to_created_at, allow_fallback=True)
                if dt is None:
                    continue
                key = (dt.year, dt.month)
                counts[target_bucket][key] = counts[target_bucket].get(key, 0) + 1
                processed += 1
    return processed


def build_records(
    counts: Dict[Tuple[int, int], int],
    fill_missing: bool,
    month_keys: Optional[List[Tuple[int, int]]],
) -> List[Dict[str, int]]:
    records: List[Dict[str, int]] = []
    if fill_missing and month_keys:
        for year, month in month_keys:
            records.append({"year": year, "month": month, "value": counts.get((year, month), 0)})
        return records
    for (year, month), value in sorted(counts.items()):
        records.append({"year": year, "month": month, "value": value})
    return records


def upsert_records(
    table: str,
    records: List[Dict[str, int]],
    batch_size: int,
    dry_run: bool,
) -> int:
    if not records:
        logger.info("No records to upsert for table=%s", table)
        return 0
    if dry_run:
        logger.info("Dry run: would upsert %s records into table=%s", len(records), table)
        return 0
    return batch_upsert(table, records, on_conflict="year,month", batch_size=batch_size)


def main() -> int:
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.debug:
        logger.setLevel(logging.DEBUG)

    if not config.supabase_url or not config.supabase_key:
        raise SystemExit("Missing SUPABASE_URL / SUPABASE_SERVICE_KEY in .env")

    tzinfo = resolve_timezone(args.timezone)
    now = datetime.now(tzinfo)
    start_dt, end_dt = resolve_range(now, args.days, args.months)

    if start_dt:
        logger.info("Range: %s -> %s", start_dt.isoformat(), end_dt.isoformat())
    else:
        logger.info("Range: full history (no date filter)")

    counts: Dict[str, Dict[Tuple[int, int], int]] = defaultdict(dict)

    bid_rows = aggregate_simple_table(
        args.opportunity_table,
        start_dt,
        end_dt,
        args.batch_size,
        args.max_batches,
        tzinfo,
        True,
        args.fallback_to_created_at,
        "bid",
        counts,
    )
    logger.info("Bids aggregated from %s: %s rows", args.opportunity_table, bid_rows)

    policy_rows = aggregate_news_table(
        args.news_table,
        "news",
        start_dt,
        end_dt,
        args.batch_size,
        args.max_batches,
        tzinfo,
        False,
        args.include_competitors,
        args.industry_from_news,
        args.fallback_to_created_at,
        counts,
    )
    logger.info("News aggregated from %s: %s rows", args.news_table, policy_rows)

    if args.include_competitors:
        competitor_rows = aggregate_news_table(
            args.competitor_table,
            "competitor",
            start_dt,
            end_dt,
            args.batch_size,
            args.max_batches,
            tzinfo,
            True,
            args.include_competitors,
            True,
            args.fallback_to_created_at,
            counts,
        )
        logger.info("Competitor news aggregated from %s: %s rows", args.competitor_table, competitor_rows)

    month_keys = None
    if args.fill_missing and start_dt:
        month_keys = list(iter_month_keys(start_dt, end_dt))

    bid_records = build_records(counts.get("bid", {}), args.fill_missing, month_keys)
    industry_records = build_records(counts.get("industry", {}), args.fill_missing, month_keys)
    policy_records = build_records(counts.get("policy", {}), args.fill_missing, month_keys)

    upsert_records(args.bid_table, bid_records, args.batch_size, args.dry_run)
    upsert_records(args.industry_table, industry_records, args.batch_size, args.dry_run)
    upsert_records(args.policy_table, policy_records, args.batch_size, args.dry_run)

    logger.info(
        "Done. bid=%s industry=%s policy=%s dry_run=%s",
        len(bid_records),
        len(industry_records),
        len(policy_records),
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
