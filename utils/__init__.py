# -*- coding: utf-8 -*-
"""
公共工具模块
提供 LLM 调用、Supabase 操作、文本处理、CLI 参数等复用功能
"""

from .llm import LLMClient, llm_chat, llm_chat_json
from .supabase_utils import get_supabase_client, batch_upsert, fetch_records
from .text import clean_text, truncate_text, extract_json_from_text
from .cli import create_common_parser, add_common_args

__all__ = [
    # LLM
    'LLMClient', 'llm_chat', 'llm_chat_json',
    # Supabase
    'get_supabase_client', 'batch_upsert', 'fetch_records',
    # Text
    'clean_text', 'truncate_text', 'extract_json_from_text',
    # CLI
    'create_common_parser', 'add_common_args',
]
