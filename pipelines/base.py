# -*- coding: utf-8 -*-
"""
管线基类
提供数据处理管线的通用框架，子类实现具体业务逻辑
"""

import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Generator

from config_loader import config
from utils.supabase_utils import get_supabase_client, batch_upsert

logger = logging.getLogger(__name__)


class BasePipeline(ABC):
    """
    数据处理管线基类
    
    子类需要实现：
    - fetch_batch(): 获取一批待处理记录
    - process_record(): 处理单条记录
    - save_result(): 保存处理结果
    
    可选重写：
    - pre_run(): 运行前的初始化
    - post_run(): 运行后的清理
    - should_skip(): 判断记录是否应该跳过
    
    用法：
        class NewsPipeline(BasePipeline):
            name = "news"
            source_table = "raw_news"
            target_table = "processed_news"
            
            def process_record(self, record):
                # 处理逻辑
                return {"summary": "...", "embedding": [...]}
        
        pipeline = NewsPipeline(batch_size=20, max_batches=10)
        pipeline.run()
    """
    
    # 子类应重写这些属性
    name: str = "base"
    source_table: str = ""
    target_table: str = ""
    id_field: str = "id"
    
    def __init__(
        self,
        batch_size: int = 20,
        max_batches: int = 10,
        days: Optional[int] = None,
        sleep_sec: float = 0.5,
        only_missing: bool = True,
        dry_run: bool = False,
        debug: bool = False
    ):
        """
        初始化管线
        
        Args:
            batch_size: 每批处理条数
            max_batches: 最多处理批次数
            days: 只处理最近 N 天的数据（None 或 0 表示不限）
            sleep_sec: 处理完每条后的暂停时间（秒）
            only_missing: 是否只处理未处理过的记录
            dry_run: 是否为试运行模式（不写入数据库）
            debug: 是否启用调试模式
        """
        self.batch_size = batch_size
        self.max_batches = max_batches
        self.days = days if days and days > 0 else None
        self.sleep_sec = sleep_sec
        self.only_missing = only_missing
        self.dry_run = dry_run
        self.debug = debug
        
        # 统计数据
        self.stats = {
            "total_fetched": 0,
            "total_processed": 0,
            "total_skipped": 0,
            "total_errors": 0,
            "total_saved": 0,
            "start_time": None,
            "end_time": None,
        }
        
        # Supabase 客户端
        self._sb = None
        
        # 日志
        self.logger = logging.getLogger(f"pipeline.{self.name}")
        if debug:
            self.logger.setLevel(logging.DEBUG)
    
    @property
    def sb(self):
        """懒加载 Supabase 客户端"""
        if self._sb is None:
            self._sb = get_supabase_client()
        return self._sb
    
    @property
    def date_cutoff(self) -> Optional[datetime]:
        """计算日期截止点"""
        if self.days:
            return datetime.now() - timedelta(days=self.days)
        return None
    
    # ==================== 子类必须实现的方法 ====================
    
    @abstractmethod
    def fetch_batch(self, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取一批待处理记录
        
        Args:
            offset: 偏移量
            
        Returns:
            记录列表
        """
        pass
    
    @abstractmethod
    def process_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理单条记录
        
        Args:
            record: 原始记录
            
        Returns:
            处理结果字典，失败返回 None
        """
        pass
    
    def save_result(self, record_id: Any, result: Dict[str, Any]) -> bool:
        """
        保存处理结果
        
        默认实现：更新源表的对应记录
        子类可重写以实现不同的保存逻辑
        
        Args:
            record_id: 记录 ID
            result: 处理结果
            
        Returns:
            是否保存成功
        """
        if self.dry_run:
            self.logger.debug(f"[DRY-RUN] 跳过保存: {record_id}")
            return True
        
        try:
            self.sb.table(self.target_table or self.source_table)\
                .update(result)\
                .eq(self.id_field, record_id)\
                .execute()
            return True
        except Exception as e:
            self.logger.error(f"保存结果失败 [{record_id}]: {e}")
            return False
    
    # ==================== 可选重写的方法 ====================
    
    def should_skip(self, record: Dict[str, Any]) -> bool:
        """
        判断记录是否应该跳过
        
        默认实现：如果 only_missing=True，检查 processed_at 字段
        
        Args:
            record: 记录
            
        Returns:
            是否应该跳过
        """
        if not self.only_missing:
            return False
        
        # 检查是否已处理（可根据实际字段调整）
        processed_at = record.get("processed_at")
        if processed_at:
            return True
        
        return False
    
    def pre_run(self):
        """运行前的初始化（子类可重写）"""
        pass
    
    def post_run(self):
        """运行后的清理（子类可重写）"""
        pass
    
    def on_batch_complete(self, batch_num: int, results: List[Dict[str, Any]]):
        """
        每批完成后的回调（子类可重写）
        
        Args:
            batch_num: 批次号（从 1 开始）
            results: 本批处理结果
        """
        pass
    
    # ==================== 核心运行逻辑 ====================
    
    def run(self) -> Dict[str, Any]:
        """
        运行管线
        
        Returns:
            统计结果字典
        """
        self.stats["start_time"] = datetime.now()
        
        self.logger.info(f"="*60)
        self.logger.info(f"管线 [{self.name}] 开始运行")
        self.logger.info(f"配置: batch_size={self.batch_size}, max_batches={self.max_batches}, "
                        f"days={self.days}, only_missing={self.only_missing}")
        if self.dry_run:
            self.logger.info("** 试运行模式 - 不写入数据库 **")
        self.logger.info(f"="*60)
        
        try:
            self.pre_run()
            
            for batch_num in range(1, self.max_batches + 1):
                # 获取一批数据
                offset = (batch_num - 1) * self.batch_size
                records = self.fetch_batch(offset)
                
                if not records:
                    self.logger.info(f"批次 {batch_num}: 无更多数据")
                    break
                
                self.stats["total_fetched"] += len(records)
                self.logger.info(f"批次 {batch_num}/{self.max_batches}: 获取 {len(records)} 条记录")
                
                # 处理每条记录
                batch_results = []
                for i, record in enumerate(records, 1):
                    record_id = record.get(self.id_field)
                    
                    # 检查是否应该跳过
                    if self.should_skip(record):
                        self.stats["total_skipped"] += 1
                        self.logger.debug(f"  [{i}/{len(records)}] 跳过: {record_id}")
                        continue
                    
                    # 处理记录
                    try:
                        result = self.process_record(record)
                        
                        if result:
                            # 保存结果
                            if self.save_result(record_id, result):
                                self.stats["total_saved"] += 1
                                batch_results.append(result)
                            self.stats["total_processed"] += 1
                            self.logger.debug(f"  [{i}/{len(records)}] 完成: {record_id}")
                        else:
                            self.stats["total_errors"] += 1
                            self.logger.warning(f"  [{i}/{len(records)}] 处理失败: {record_id}")
                    
                    except Exception as e:
                        self.stats["total_errors"] += 1
                        self.logger.error(f"  [{i}/{len(records)}] 异常: {record_id} - {e}")
                    
                    # 暂停
                    if self.sleep_sec > 0 and i < len(records):
                        time.sleep(self.sleep_sec)
                
                # 批次完成回调
                self.on_batch_complete(batch_num, batch_results)
                
                self.logger.info(
                    f"批次 {batch_num} 完成: "
                    f"处理={len(batch_results)}, "
                    f"累计={self.stats['total_processed']}"
                )
            
            self.post_run()
        
        except Exception as e:
            self.logger.error(f"管线运行异常: {e}")
            raise
        
        finally:
            self.stats["end_time"] = datetime.now()
            self._print_summary()
        
        return self.stats
    
    def _print_summary(self):
        """打印运行摘要"""
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        
        self.logger.info(f"="*60)
        self.logger.info(f"管线 [{self.name}] 运行结束")
        self.logger.info(f"="*60)
        self.logger.info(f"  获取记录数: {self.stats['total_fetched']}")
        self.logger.info(f"  处理成功数: {self.stats['total_processed']}")
        self.logger.info(f"  跳过记录数: {self.stats['total_skipped']}")
        self.logger.info(f"  保存成功数: {self.stats['total_saved']}")
        self.logger.info(f"  处理失败数: {self.stats['total_errors']}")
        self.logger.info(f"  总耗时: {duration:.1f}s")
        self.logger.info(f"="*60)
    
    # ==================== 便捷方法 ====================
    
    def iter_records(self) -> Generator[Dict[str, Any], None, None]:
        """
        迭代所有待处理记录（生成器）
        
        Yields:
            单条记录
        """
        for batch_num in range(1, self.max_batches + 1):
            offset = (batch_num - 1) * self.batch_size
            records = self.fetch_batch(offset)
            
            if not records:
                break
            
            for record in records:
                if not self.should_skip(record):
                    yield record
    
    def process_batch(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量处理记录（用于子类批量处理优化）
        
        Args:
            records: 记录列表
            
        Returns:
            处理结果列表
        """
        results = []
        for record in records:
            result = self.process_record(record)
            if result:
                results.append(result)
        return results
    
    def batch_save_results(self, results: List[Dict[str, Any]], on_conflict: str = None) -> int:
        """
        批量保存结果
        
        Args:
            results: 结果列表
            on_conflict: 冲突时的字段
            
        Returns:
            保存成功的数量
        """
        if self.dry_run:
            self.logger.debug(f"[DRY-RUN] 跳过批量保存: {len(results)} 条")
            return len(results)
        
        return batch_upsert(
            self.target_table or self.source_table,
            results,
            on_conflict=on_conflict or self.id_field,
            client=self.sb
        )
