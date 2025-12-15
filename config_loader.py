# -*- coding: utf-8 -*-
"""
统一配置加载器
从 config.yaml 和 .env 文件加载配置
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# 加载 .env 文件（仅包含敏感信息）
load_dotenv()

# 配置文件路径
CONFIG_FILE = Path(__file__).parent / "config.yaml"


class Config:
    """统一配置管理类"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or CONFIG_FILE
        self._config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """加载 YAML 配置文件"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值，支持点号分隔的路径
        例如: get('processing.batch_size') 或 get('tables.analysis_table')
        """
        keys = key_path.split('.')
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default
    
    # ========== 便捷属性访问 ==========
    
    @property
    def view(self) -> str:
        return self.get('processing.view', 'management')
    
    @property
    def days(self) -> int:
        return self.get('processing.days', 30)
    
    @property
    def batch_size(self) -> int:
        return self.get('processing.batch_size', 40)
    
    @property
    def max_batches(self) -> int:
        return self.get('processing.max_batches', 10)
    
    @property
    def sleep_sec(self) -> float:
        return self.get('processing.sleep_sec', 0.8)
    
    @property
    def force_refresh(self) -> bool:
        return self.get('processing.force_refresh', False)
    
    @property
    def debug(self) -> bool:
        return self.get('processing.debug', False)
    
    @property
    def enable_noise_filter(self) -> bool:
        return self.get('processing.enable_noise_filter', False)
    
    @property
    def mode(self) -> str:
        return self.get('processing.mode', 'daily')
    
    @property
    def analysis_table(self) -> str:
        return self.get('tables.analysis_table', 'fact_events')
    
    @property
    def fact_ddr_table(self) -> str:
        return self.get('tables.fact_ddr_table', 'dashboard_daily_events')
    
    @property
    def monthly_table(self) -> str:
        return self.get('tables.monthly_table', 'dashboard_daily_events')
    
    @property
    def monthly_source_table(self) -> str:
        return self.get('tables.monthly_source_table', 'fact_events')
    
    @property
    def raw_news_table(self) -> str:
        return self.get('tables.raw_news_table', '00_news')
    
    @property
    def raw_opportunity_table(self) -> str:
        return self.get('tables.raw_opportunity_table', '00_opportunity')
    
    @property
    def competitors_table(self) -> str:
        return self.get('tables.competitors_table', '00_competitors')
    
    @property
    def daily_reports_table(self) -> str:
        return self.get('tables.daily_reports_table', 'dashboard_daily_reports')
    
    @property
    def weekly_reports_table(self) -> str:
        return self.get('tables.weekly_reports_table', 'dashboard_weekly_reports')
    
    @property
    def news_summaries_table(self) -> str:
        return self.get('tables.news_summaries_table', 'news_summaries')
    
    @property
    def opportunity_insights_table(self) -> str:
        return self.get('tables.opportunity_insights_table', 'opportunity_insights')
    
    @property
    def monthly_days(self) -> int:
        return self.get('monthly.days', 30)
    
    @property
    def monthly_limit(self) -> int:
        return self.get('monthly.limit', 10)
    
    @property
    def monthly_summary_max_length(self) -> int:
        return self.get('monthly.summary_max_length', 1000)
    
    @property
    def llm_model(self) -> str:
        return self.get('models.llm.model', 'deepseek-v3-1-terminus')
    
    @property
    def llm_temperature(self) -> float:
        return self.get('models.llm.temperature', 0.0)
    
    @property
    def llm_endpoint(self) -> str:
        # 优先使用环境变量，其次使用配置文件
        return os.getenv('VOLCANO_API_ENDPOINT') or self.get('models.llm.endpoint', 'https://ark.cn-beijing.volces.com/api/v3')
    
    @property
    def embedding_model(self) -> str:
        return self.get('models.embedding.model', 'text-embedding-v4')
    
    @property
    def embedding_dimensions(self) -> int:
        return self.get('models.embedding.dimensions', 768)
    
    @property
    def unified_view(self) -> str:
        return self.get('views.unified_view', 'v_events_ready')
    
    @property
    def dim_cn_region(self) -> str:
        return self.get('views.dim_cn_region', 'dim_cn_region')
    
    @property
    def dim_country(self) -> str:
        return self.get('views.dim_country', 'dim_country')
    
    # ========== 环境变量访问（敏感信息） ==========
    
    @property
    def supabase_url(self) -> Optional[str]:
        return os.getenv('SUPABASE_URL')
    
    @property
    def supabase_key(self) -> Optional[str]:
        return os.getenv('SUPABASE_SERVICE_KEY')
    
    @property
    def volcano_api_token(self) -> Optional[str]:
        return os.getenv('VOLCANO_API_TOKEN')
    
    @property
    def qwen_api_key(self) -> Optional[str]:
        return os.getenv('QWEN_API_KEY')
    
    # ========== 调度器配置 ==========
    
    @property
    def scheduler_enabled(self) -> bool:
        return self.get('scheduler.enabled', True)
    
    @property
    def scheduler_timezone(self) -> str:
        return self.get('scheduler.timezone', 'Asia/Shanghai')
    
    @property
    def scheduler_log_dir(self) -> str:
        return self.get('scheduler.log_dir', 'logs')
    
    @property
    def scheduler_jobs(self) -> Dict[str, Any]:
        return self.get('scheduler.jobs', {})
    
    # ========== 调度器默认配置 ==========
    
    @property
    def scheduler_default_timeout(self) -> int:
        return self.get('scheduler.defaults.timeout', 3600)
    
    @property
    def scheduler_default_misfire_grace_time(self) -> int:
        return self.get('scheduler.defaults.misfire_grace_time', 300)
    
    @property
    def scheduler_default_max_instances(self) -> int:
        return self.get('scheduler.defaults.max_instances', 1)
    
    @property
    def scheduler_default_days(self) -> int:
        return self.get('scheduler.defaults.days', 7)
    
    @property
    def scheduler_default_batch_size(self) -> int:
        return self.get('scheduler.defaults.batch_size', 40)
    
    @property
    def scheduler_default_max_batches(self) -> int:
        return self.get('scheduler.defaults.max_batches', 10)
    
    # ========== 调度器并发控制 ==========
    
    @property
    def scheduler_max_workers(self) -> int:
        return self.get('scheduler.concurrency.max_workers', 1)
    
    # ========== 调度器重试策略 ==========
    
    @property
    def scheduler_retry_enabled(self) -> bool:
        return self.get('scheduler.retry.enabled', True)
    
    @property
    def scheduler_retry_max_attempts(self) -> int:
        return self.get('scheduler.retry.max_attempts', 2)
    
    @property
    def scheduler_retry_initial_delay(self) -> int:
        return self.get('scheduler.retry.initial_delay', 60)
    
    @property
    def scheduler_retry_backoff_multiplier(self) -> int:
        return self.get('scheduler.retry.backoff_multiplier', 2)
    
    @property
    def scheduler_retry_max_delay(self) -> int:
        return self.get('scheduler.retry.max_delay', 300)


# 全局配置实例
config = Config()

