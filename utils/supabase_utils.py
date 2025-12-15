# -*- coding: utf-8 -*-
"""
Supabase 数据库操作封装
提供客户端获取、批量 upsert、记录查询等功能
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from supabase import create_client, Client

from config_loader import config

logger = logging.getLogger(__name__)

# 全局客户端缓存
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    获取 Supabase 客户端（单例模式）
    
    Returns:
        Supabase Client 实例
    """
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(config.supabase_url, config.supabase_key)
    return _supabase_client


def batch_upsert(
    table: str,
    records: List[Dict[str, Any]],
    on_conflict: str = "id",
    batch_size: int = 100,
    client: Optional[Client] = None
) -> int:
    """
    批量 upsert 记录到 Supabase
    
    Args:
        table: 目标表名
        records: 记录列表
        on_conflict: 冲突时的主键字段
        batch_size: 每批大小
        client: Supabase 客户端（可选，默认使用全局客户端）
        
    Returns:
        成功插入/更新的记录数
    """
    if not records:
        return 0
    
    sb = client or get_supabase_client()
    total_success = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        try:
            result = sb.table(table).upsert(batch, on_conflict=on_conflict).execute()
            total_success += len(batch)
            logger.debug(f"批量 upsert {table}: {len(batch)} 条")
        except Exception as e:
            logger.error(f"批量 upsert {table} 失败 (批次 {i // batch_size + 1}): {e}")
    
    return total_success


def fetch_records(
    table: str,
    columns: str = "*",
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[str] = None,
    order_desc: bool = True,
    limit: Optional[int] = None,
    offset: int = 0,
    client: Optional[Client] = None
) -> List[Dict[str, Any]]:
    """
    从 Supabase 查询记录
    
    Args:
        table: 表名或视图名
        columns: 要查询的列（逗号分隔）
        filters: 过滤条件字典，支持简单等值过滤
        order_by: 排序字段
        order_desc: 是否降序
        limit: 返回记录数限制
        offset: 偏移量
        client: Supabase 客户端（可选）
        
    Returns:
        记录列表
    """
    sb = client or get_supabase_client()
    
    try:
        query = sb.table(table).select(columns)
        
        # 应用过滤条件
        if filters:
            for key, value in filters.items():
                if value is not None:
                    query = query.eq(key, value)
        
        # 排序
        if order_by:
            query = query.order(order_by, desc=order_desc)
        
        # 分页
        if limit:
            query = query.limit(limit)
        if offset > 0:
            query = query.offset(offset)
        
        result = query.execute()
        return result.data or []
    
    except Exception as e:
        logger.error(f"查询 {table} 失败: {e}")
        return []


def fetch_records_raw(
    table: str,
    query_builder: Callable,
    client: Optional[Client] = None
) -> List[Dict[str, Any]]:
    """
    使用自定义 query builder 查询记录
    
    Args:
        table: 表名
        query_builder: 接收 query 对象，返回修改后的 query
        client: Supabase 客户端（可选）
        
    Returns:
        记录列表
        
    用法：
        records = fetch_records_raw(
            "my_table",
            lambda q: q.select("*").gt("score", 80).order("created_at", desc=True)
        )
    """
    sb = client or get_supabase_client()
    
    try:
        query = sb.table(table)
        query = query_builder(query)
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"查询 {table} 失败: {e}")
        return []


def update_record(
    table: str,
    record_id: Any,
    data: Dict[str, Any],
    id_column: str = "id",
    client: Optional[Client] = None
) -> bool:
    """
    更新单条记录
    
    Args:
        table: 表名
        record_id: 记录 ID
        data: 要更新的字段字典
        id_column: ID 字段名
        client: Supabase 客户端（可选）
        
    Returns:
        是否成功
    """
    sb = client or get_supabase_client()
    
    try:
        sb.table(table).update(data).eq(id_column, record_id).execute()
        return True
    except Exception as e:
        logger.error(f"更新 {table} 记录 {record_id} 失败: {e}")
        return False


def delete_records(
    table: str,
    filters: Dict[str, Any],
    client: Optional[Client] = None
) -> int:
    """
    删除符合条件的记录
    
    Args:
        table: 表名
        filters: 过滤条件字典
        client: Supabase 客户端（可选）
        
    Returns:
        删除的记录数
    """
    sb = client or get_supabase_client()
    
    try:
        query = sb.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        result = query.execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"删除 {table} 记录失败: {e}")
        return 0


def count_records(
    table: str,
    filters: Optional[Dict[str, Any]] = None,
    client: Optional[Client] = None
) -> int:
    """
    统计记录数
    
    Args:
        table: 表名
        filters: 过滤条件字典
        client: Supabase 客户端（可选）
        
    Returns:
        记录数
    """
    sb = client or get_supabase_client()
    
    try:
        query = sb.table(table).select("*", count="exact")
        if filters:
            for key, value in filters.items():
                if value is not None:
                    query = query.eq(key, value)
        result = query.execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"统计 {table} 记录数失败: {e}")
        return 0
