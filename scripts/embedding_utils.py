# -*- coding: utf-8 -*-
"""
Embedding helpers for fact_events using DashScope (Qwen) text-embedding-v4.
"""

import json
import logging
import sys
from typing import Any, List, Optional
from pathlib import Path

import dashscope

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config_loader import config

logger = logging.getLogger(__name__)

QWEN_API_KEY = config.qwen_api_key
EMBEDDING_MODEL = config.embedding_model
EMBEDDING_DIM = config.embedding_dimensions


def _truncate(s: str, n: int) -> str:
    return s[:n] if len(s) > n else s


def build_fact_event_embedding(
    type_: str,
    title: str,
    summary: Optional[str] = None,
    source: Optional[str] = None,
    keywords: Optional[list] = None,
    payload: Optional[Any] = None,
) -> Optional[List[float]]:
    """
    Build a text embedding for a fact_event record using Qwen text-embedding-v4.
    Returns None when API key is missing or any error happens.
    """
    if not QWEN_API_KEY:
        logger.warning("QWEN_API_KEY not set, skip embedding generation.")
        return None

    dashscope.api_key = QWEN_API_KEY

    payload_str: str
    try:
        payload_str = json.dumps(payload, ensure_ascii=False)
    except Exception:
        payload_str = str(payload)
    payload_str = _truncate(payload_str, 2000)

    text_parts = [
        f"事件类型: {type_ or ''}",
        f"标题: {title or ''}",
        f"摘要: {summary or ''}",
        f"来源: {source or ''}",
        f"关键词: {', '.join(keywords) if keywords else ''}",
        f"额外数据: {payload_str}",
    ]
    input_text = "\n".join(text_parts)

    try:
        resp = dashscope.TextEmbedding.call(
            model=EMBEDDING_MODEL,
            input=input_text,
            parameters={"dimensions": EMBEDDING_DIM},
        )
        embeddings = (resp.get("output") or {}).get("embeddings") if isinstance(resp, dict) else None
        if not embeddings and hasattr(resp, "output"):
            embeddings = getattr(resp, "output", {}).get("embeddings")
        if not embeddings:
            raise ValueError("No embeddings returned from DashScope.")
        emb = embeddings[0].get("embedding") if embeddings else None
        if not emb:
            raise ValueError("Embedding vector missing in response.")
        return list(emb)
    except Exception as e:
        logger.error(f"Failed to build embedding: {e}", exc_info=True)
        return None
