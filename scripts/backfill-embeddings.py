# -*- coding: utf-8 -*-
"""
补充 fact_events 表中缺失的 embedding 向量

用途：
- 为已有 AI 建议但缺少 embedding 的老记录补充向量
- 不重新调用 LLM，直接使用已有字段生成 embedding

依赖:
    pip install supabase python-dotenv pyyaml

环境变量:
    从 .env 文件读取 QWEN_API_KEY（用于 Embedding）

配置:
    从 config.yaml 读取批处理参数

示例:
    python backfill-embeddings.py --batch-size 50 --max-batches 100
    python backfill-embeddings.py --days 30  # 只处理最近30天的记录
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from supabase import create_client, Client
from config_loader import config
from embedding_utils import build_fact_event_embedding

# ---------------- 日志配置 ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill-embeddings")

# ---------------- 配置加载 ----------------
SUPABASE_URL = config.supabase_url
SUPABASE_KEY = config.supabase_key

if not all([SUPABASE_URL, SUPABASE_KEY]):
    raise SystemExit("请设置 SUPABASE_URL / SUPABASE_SERVICE_KEY（在 .env 文件中）")

if not config.qwen_api_key:
    raise SystemExit("请设置 QWEN_API_KEY（在 .env 文件中）用于生成 embedding")

# ---------------- Supabase 客户端 ----------------
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- 命令行参数 ----------------
import argparse

def parse_args():
    p = argparse.ArgumentParser(description="补充 fact_events 表中缺失的 embedding 向量")
    p.add_argument("--batch-size", type=int, default=config.batch_size, help="每批处理条数")
    p.add_argument("--max-batches", type=int, default=config.max_batches, help="最多处理批次数")
    p.add_argument("--sleep", type=float, default=config.sleep_sec, help="每条记录处理间隔（秒）")
    p.add_argument("--days", type=int, default=0, help="只处理最近N天的记录（0=不限制）")
    p.add_argument("--fact-table", default="fact_events", help="目标表名")
    p.add_argument("--dry-run", action="store_true", help="试运行模式，不实际更新数据库")
    return p.parse_args()


def fetch_missing_embeddings(
    table: str,
    offset: int,
    limit: int,
    days: int = 0
) -> List[Dict[str, Any]]:
    """
    读取缺少 embedding 的记录
    
    Args:
        table: 表名
        offset: 偏移量
        limit: 限制条数
        days: 只处理最近N天的记录（0=不限制）
    
    Returns:
        记录列表
    """
    q = (
        sb.table(table)
        .select("*")
        .is_("embedding", "null")  # embedding 为 NULL
        .order("created_at", desc=True)
    )
    
    # 如果指定了天数，添加时间过滤
    if days > 0:
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        since_iso = since_dt.isoformat()
        q = q.gte("created_at", since_iso)
    
    res = q.range(offset, offset + limit - 1).execute()
    return res.data or []


def update_embedding(table: str, record_id: int, embedding: List[float], dry_run: bool = False) -> bool:
    """
    更新记录的 embedding 字段
    
    Args:
        table: 表名
        record_id: 记录ID
        embedding: embedding 向量
        dry_run: 是否为试运行模式
    
    Returns:
        是否成功
    """
    if dry_run:
        logger.info(f"[DRY-RUN] 将更新 id={record_id} 的 embedding（维度={len(embedding)}）")
        return True
    
    try:
        sb.table(table).update({"embedding": embedding}).eq("id", record_id).execute()
        return True
    except Exception as e:
        logger.error(f"更新 embedding 失败: id={record_id}, error={e}", exc_info=True)
        return False


def process_record(record: Dict[str, Any], table: str, dry_run: bool = False) -> bool:
    """
    处理单条记录：生成并更新 embedding
    
    Args:
        record: 记录字典
        table: 表名
        dry_run: 是否为试运行模式
    
    Returns:
        是否成功
    """
    record_id = record.get("id")
    if not record_id:
        logger.warning(f"记录缺少 id 字段，跳过")
        return False
    
    # 提取已有字段用于生成 embedding
    type_ = record.get("type") or ""
    title = record.get("title") or ""
    summary = record.get("summary")  # 使用已有的 summary
    source = record.get("source")
    keywords = record.get("keywords")  # 使用已有的 keywords（可能是数组）
    payload = record.get("payload")  # 使用已有的 payload
    
    # 生成 embedding
    embedding = build_fact_event_embedding(
        type_=type_,
        title=title,
        summary=summary,
        source=source,
        keywords=keywords,
        payload=payload,
    )
    
    if embedding is None:
        logger.warning(f"id={record_id} embedding 生成失败，跳过")
        return False

    # 维度校验，方便发现表定义与配置不一致的问题
    expected_dim = config.embedding_dimensions
    if expected_dim and len(embedding) != expected_dim:
        logger.warning(
            f"id={record_id} embedding 维度={len(embedding)} 与配置 models.embedding.dimensions={expected_dim} 不一致，请确认表 vector 维度与配置匹配"
        )
    
    # 更新 embedding
    success = update_embedding(table, record_id, embedding, dry_run)
    if success:
        logger.info(f"✅ id={record_id} | title={title[:40]} | embedding维度={len(embedding)}")
    
    return success


def run_backfill(
    table: str = "fact_events",
    batch_size: int = 50,
    max_batches: int = 100,
    sleep_sec: float = 0.5,
    days: int = 0,
    dry_run: bool = False,
):
    """
    执行 embedding 补充任务
    
    Args:
        table: 目标表名
        batch_size: 每批处理条数
        max_batches: 最多批次数
        sleep_sec: 每条记录处理间隔
        days: 只处理最近N天的记录（0=不限制）
        dry_run: 是否为试运行模式
    """
    logger.info(
        f"开始补充 embedding | 表={table} | 批大小={batch_size} | "
        f"批次数={max_batches} | 间隔={sleep_sec}s | "
        f"{f'最近{days}天' if days > 0 else '全部记录'} | "
        f"{'[试运行]' if dry_run else '[实际更新]'}"
    )
    
    processed = 0
    failed = 0
    skipped = 0
    
    for batch_num in range(max_batches):
        # 实际更新时始终从 offset=0 重新读取缺失记录，避免前一批更新后因 offset 偏移而跳过未处理数据
        offset = batch_num * batch_size if dry_run else 0
        rows = fetch_missing_embeddings(table, offset, batch_size, days)
        
        if not rows:
            logger.info(f"没有更多缺少 embedding 的记录，提前结束。")
            break
        
        logger.info(f"批次 {batch_num + 1}/{max_batches}: 读取到 {len(rows)} 条记录")
        
        for record in rows:
            try:
                success = process_record(record, table, dry_run)
                if success:
                    processed += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                logger.error(f"处理失败: id={record.get('id')}, error={e}", exc_info=True)
            
            time.sleep(sleep_sec)
        
        logger.info(f"批次 {batch_num + 1} 完成: 成功={processed} 跳过={skipped} 失败={failed}")
    
    logger.info(
        f"补充任务结束: 成功={processed} 跳过={skipped} 失败={failed} | "
        f"{'[试运行]' if dry_run else '[实际更新]'}"
    )


def main():
    args = parse_args()
    
    if args.dry_run:
        logger.warning("⚠️  试运行模式：不会实际更新数据库")
    
    run_backfill(
        table=args.fact_table,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        sleep_sec=args.sleep,
        days=args.days,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
