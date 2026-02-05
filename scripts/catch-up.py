#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一补齐管线（仅处理缺失结果，按顺序串行执行）
"""

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config_loader import config


logger = logging.getLogger("catch-up")


@dataclass
class Step:
    key: str
    label: str
    script: str
    build_cmd: Callable[[argparse.Namespace], List[str]]
    build_env: Optional[Callable[[argparse.Namespace], Dict[str, str]]] = None


def _python_cmd(script: str) -> List[str]:
    return [sys.executable, str(ROOT_DIR / script)]


def build_databoard_map_cmd(args: argparse.Namespace) -> List[str]:
    if args.max_batches <= 0:
        raise ValueError("databoard_map 需要 max_batches >= 1")
    cmd = _python_cmd("scripts/databoard-map-process.py")
    cmd += [
        "--source-mode", args.source_mode,
        "--days", str(args.days),
        "--batch-size", str(args.batch_size),
        "--max-batches", str(args.max_batches),
        "--sleep", str(args.sleep),
    ]
    if args.process_all:
        cmd.append("--process-all")
    if args.include_types:
        cmd += ["--include-types", args.include_types]
    if args.exclude_types:
        cmd += ["--exclude-types", args.exclude_types]
    return cmd


def build_news_cmd(args: argparse.Namespace) -> List[str]:
    if args.max_batches <= 0:
        raise ValueError("news 需要 max_batches >= 1")
    cmd = _python_cmd("scripts/news_process.py")
    cmd += [
        "--mode", args.news_mode,
        "--max-batches", str(args.max_batches),
        "--batch-size", str(args.batch_size),
        "--sleep", str(args.sleep),
        "--days", str(args.days),
    ]
    if args.process_all:
        cmd.append("--process-all")
    return cmd


def build_opportunity_cmd(args: argparse.Namespace) -> List[str]:
    if args.max_batches <= 0:
        raise ValueError("opportunity 需要 max_batches >= 1")
    cmd = _python_cmd("scripts/opportunity-process.py")
    cmd += [
        "--max-batches", str(args.max_batches),
        "--batch-size", str(args.batch_size),
        "--sleep", str(args.sleep),
        "--days", str(args.days),
    ]
    if args.process_all:
        cmd.append("--all")
    return cmd


def build_daily_report_cmd(args: argparse.Namespace) -> List[str]:
    cmd = _python_cmd("scripts/daily-report-process.py")
    cmd += ["--mode", args.daily_mode]
    # 注意：daily-report-process.py 的 --days/--batch-size/--max-batches 仅用于日志记录
    # 实际批次参数通过环境变量在模块加载时读取
    cmd += ["--days", str(args.days), "--batch-size", str(args.batch_size), "--max-batches", str(args.max_batches)]
    return cmd


def build_daily_report_env(args: argparse.Namespace) -> Dict[str, str]:
    return {
        "MAX_BATCHES": str(args.max_batches),
        "BATCH_SIZE": str(args.batch_size),
        "SLEEP_SEC": str(args.sleep),
    }


def build_backfill_cmd(args: argparse.Namespace) -> List[str]:
    if args.max_batches <= 0:
        raise ValueError("backfill_embeddings 需要 max_batches >= 1")
    cmd = _python_cmd("scripts/backfill-embeddings.py")
    cmd += [
        "--days", str(args.days),
        "--batch-size", str(args.batch_size),
        "--max-batches", str(args.max_batches),
        "--sleep", str(args.sleep),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def build_monthly_series_cmd(args: argparse.Namespace) -> List[str]:
    # monthly-series 支持 max_batches=0 表示不限制
    cmd = _python_cmd("scripts/monthly-series-process.py")
    cmd += [
        "--days", str(args.days),
        "--batch-size", str(args.batch_size),
        "--max-batches", str(args.max_batches),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


STEPS: Dict[str, Step] = {
    "databoard_map": Step(
        key="databoard_map",
        label="databoard-map (raw → fact_events)",
        script="scripts/databoard-map-process.py",
        build_cmd=build_databoard_map_cmd,
    ),
    "news": Step(
        key="news",
        label="news_process (00_news → news_summaries)",
        script="scripts/news_process.py",
        build_cmd=build_news_cmd,
    ),
    "opportunity": Step(
        key="opportunity",
        label="opportunity-process (00_opportunity → opportunity_insights)",
        script="scripts/opportunity-process.py",
        build_cmd=build_opportunity_cmd,
    ),
    "daily_report": Step(
        key="daily_report",
        label="daily-report (fact_events → dashboard_daily_events)",
        script="scripts/daily-report-process.py",
        build_cmd=build_daily_report_cmd,
        build_env=build_daily_report_env,
    ),
    "backfill_embeddings": Step(
        key="backfill_embeddings",
        label="backfill-embeddings (fact_events.embedding)",
        script="scripts/backfill-embeddings.py",
        build_cmd=build_backfill_cmd,
    ),
    "monthly_series": Step(
        key="monthly_series",
        label="monthly-series (00_* → 11_*)",
        script="scripts/monthly-series-process.py",
        build_cmd=build_monthly_series_cmd,
    ),
}


DEFAULT_STEPS = ",".join(STEPS.keys())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="统一补齐管线：按顺序执行各脚本（默认仅处理缺失数据）")
    p.add_argument("--steps", default=DEFAULT_STEPS,
                   help=f"逗号分隔的步骤列表，默认：{DEFAULT_STEPS}")
    p.add_argument("--days", type=int, default=config.days, help="处理最近 N 天（0=不限）")
    p.add_argument("--batch-size", type=int, default=config.batch_size, help="每批处理条数")
    p.add_argument("--max-batches", type=int, default=config.max_batches,
                   help="最大批次数（部分脚本要求 >=1；monthly-series 支持 0=不限制）")
    p.add_argument("--sleep", type=float, default=config.sleep_sec, help="每条处理间隔秒数")
    p.add_argument("--process-all", action="store_true", help="不论是否已有结果，全部重算")
    p.add_argument("--source-mode", choices=["raw", "view"], default="raw", help="databoard-map 的读取模式")
    p.add_argument("--news-mode", choices=["single", "multi"], default="multi", help="news_process 模式")
    p.add_argument("--daily-mode", choices=["daily", "weekly", "monthly"], default="daily",
                   help="daily-report 运行模式")
    p.add_argument("--include-types", default="", help="databoard-map 仅处理这些类型（逗号分隔）")
    p.add_argument("--exclude-types", default="", help="databoard-map 排除这些类型（逗号分隔）")
    p.add_argument("--dry-run", action="store_true", help="仅打印命令，不执行")
    p.add_argument("--continue-on-error", action="store_true", help="单步失败后继续执行后续步骤")
    return p.parse_args()


def parse_steps(raw: str) -> List[Step]:
    items = [s.strip() for s in (raw or "").split(",") if s.strip()]
    if not items:
        raise ValueError("steps 不能为空")
    unknown = [s for s in items if s not in STEPS]
    if unknown:
        raise ValueError(f"未知步骤: {', '.join(unknown)}")
    return [STEPS[s] for s in items]


def run_step(step: Step, args: argparse.Namespace) -> int:
    cmd = step.build_cmd(args)
    env = os.environ.copy()
    if step.build_env:
        env.update(step.build_env(args))
    logger.info("▶ %s", step.label)
    logger.info("  命令: %s", " ".join(cmd))
    if args.dry_run:
        return 0
    result = subprocess.run(cmd, cwd=ROOT_DIR, env=env)
    return result.returncode


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
    args = parse_args()

    steps = parse_steps(args.steps)
    logger.info("步骤顺序: %s", " → ".join(s.key for s in steps))
    logger.info("参数: days=%s batch_size=%s max_batches=%s sleep=%s process_all=%s",
                args.days, args.batch_size, args.max_batches, args.sleep, args.process_all)

    if args.max_batches == 0:
        logger.warning(
            "max_batches=0 仅对 monthly-series 有效，其他脚本会导致不执行。请确认 steps 或改成正整数。"
        )

    failures: List[str] = []
    for step in steps:
        try:
            code = run_step(step, args)
        except Exception as exc:
            logger.error("步骤失败: %s | %s", step.key, exc)
            failures.append(step.key)
            if not args.continue_on_error:
                break
            continue
        if code != 0:
            logger.error("步骤失败: %s | exit=%s", step.key, code)
            failures.append(step.key)
            if not args.continue_on_error:
                break

    if failures:
        logger.error("完成，但存在失败步骤: %s", ", ".join(failures))
        sys.exit(1)
    logger.info("全部步骤完成 ✅")


if __name__ == "__main__":
    main()
