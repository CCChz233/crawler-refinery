# -*- coding: utf-8 -*-
"""
CLI 参数工具
提供统一的命令行参数定义，确保各脚本参数一致性
"""

import argparse
import logging
from typing import Optional

from config_loader import config

logger = logging.getLogger(__name__)


def create_common_parser(
    description: str = "数据处理脚本",
    include_days: bool = True,
    include_batch: bool = True,
    include_sleep: bool = True
) -> argparse.ArgumentParser:
    """
    创建带有通用参数的 ArgumentParser
    
    Args:
        description: 脚本描述
        include_days: 是否包含 --days 参数
        include_batch: 是否包含 batch 相关参数
        include_sleep: 是否包含 --sleep 参数
        
    Returns:
        配置好的 ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    add_common_args(
        parser,
        include_days=include_days,
        include_batch=include_batch,
        include_sleep=include_sleep
    )
    
    return parser


def add_common_args(
    parser: argparse.ArgumentParser,
    include_days: bool = True,
    include_batch: bool = True,
    include_sleep: bool = True,
    days_default: Optional[int] = None,
    batch_size_default: Optional[int] = None,
    max_batches_default: Optional[int] = None,
    sleep_default: float = 0.5
) -> argparse.ArgumentParser:
    """
    向现有 parser 添加通用参数
    
    标准参数名称：
    - --days: 处理天数范围
    - --batch-size: 每批处理条数
    - --max-batches: 最多处理批次数
    - --sleep: API 调用间隔
    
    Args:
        parser: 要添加参数的 parser
        include_days: 是否包含 --days
        include_batch: 是否包含 batch 相关参数
        include_sleep: 是否包含 --sleep
        days_default: --days 默认值
        batch_size_default: --batch-size 默认值
        max_batches_default: --max-batches 默认值
        sleep_default: --sleep 默认值
        
    Returns:
        修改后的 parser
    """
    # 时间范围参数
    if include_days:
        parser.add_argument(
            "--days",
            type=int,
            default=days_default or config.scheduler_default_days,
            help=f"仅处理最近 N 天的数据（0=不限，默认: {days_default or config.scheduler_default_days}）"
        )
    
    # 批处理参数
    if include_batch:
        parser.add_argument(
            "--batch-size",
            type=int,
            default=batch_size_default or config.scheduler_default_batch_size,
            help=f"每批处理条数（默认: {batch_size_default or config.scheduler_default_batch_size}）"
        )
        
        parser.add_argument(
            "--max-batches",
            type=int,
            default=max_batches_default or config.scheduler_default_max_batches,
            help=f"最多处理批次数（默认: {max_batches_default or config.scheduler_default_max_batches}）"
        )
    
    # 延迟参数
    if include_sleep:
        parser.add_argument(
            "--sleep",
            type=float,
            default=sleep_default,
            help=f"两次 API 调用间的暂停秒数（默认: {sleep_default}）"
        )
    
    # 通用调试参数
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式（更详细的日志）"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式（不写入数据库）"
    )
    
    return parser


def setup_logging_from_args(args: argparse.Namespace, logger_name: Optional[str] = None):
    """
    根据命令行参数配置日志级别
    
    Args:
        args: 解析后的命令行参数
        logger_name: 日志记录器名称（None 表示 root logger）
    """
    log = logging.getLogger(logger_name)
    
    if getattr(args, 'debug', False):
        log.setLevel(logging.DEBUG)
        # 如果还没有 handler，添加一个
        if not log.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
            handler.setFormatter(formatter)
            log.addHandler(handler)
        logger.debug("调试模式已启用")


def log_args(args: argparse.Namespace, logger_instance: Optional[logging.Logger] = None):
    """
    打印所有命令行参数（用于调试）
    
    Args:
        args: 解析后的命令行参数
        logger_instance: 日志记录器
    """
    log = logger_instance or logger
    log.info("命令行参数:")
    for key, value in vars(args).items():
        log.info(f"  {key}: {value}")
