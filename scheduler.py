#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时任务调度器（增强版）
使用 APScheduler 管理数据处理脚本的定时执行

功能：
- 全局并发控制（可配置 max_workers）
- 失败重试机制（指数退避）
- 可配置超时
- 自动传递 days/batch_size/max_batches 参数
"""

import os
import sys
import time
import signal
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from logging.handlers import RotatingFileHandler

from config_loader import config

# 工作目录
WORK_DIR = Path(__file__).parent.absolute()

# 日志配置
LOG_DIR = WORK_DIR / config.scheduler_log_dir
LOG_DIR.mkdir(exist_ok=True)

# 设置日志
logger = logging.getLogger('scheduler')
logger.setLevel(logging.INFO)

# 控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# 文件处理器（轮转日志）
file_handler = RotatingFileHandler(
    LOG_DIR / 'scheduler.log',
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=10,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(console_formatter)
logger.addHandler(file_handler)


class ConcurrencyManager:
    """全局并发控制管理器"""
    
    def __init__(self, max_workers: int):
        self.max_workers = max_workers
        self.semaphore = threading.Semaphore(max_workers) if max_workers > 0 else None
        self.current_jobs = set()
        self.lock = threading.Lock()
    
    def acquire(self, job_name: str) -> bool:
        """获取执行许可"""
        if self.semaphore:
            logger.debug(f"任务 [{job_name}] 等待并发许可...")
            self.semaphore.acquire()
        
        with self.lock:
            self.current_jobs.add(job_name)
            logger.debug(f"任务 [{job_name}] 获得许可，当前运行: {self.current_jobs}")
        return True
    
    def release(self, job_name: str):
        """释放执行许可"""
        with self.lock:
            self.current_jobs.discard(job_name)
        
        if self.semaphore:
            self.semaphore.release()
            logger.debug(f"任务 [{job_name}] 释放许可")
    
    def get_running_jobs(self) -> List[str]:
        """获取当前运行的任务"""
        with self.lock:
            return list(self.current_jobs)


class JobRunner:
    """任务运行器（支持重试和超时）"""
    
    def __init__(self, job_name: str, job_config: Dict[str, Any], concurrency_manager: ConcurrencyManager):
        self.job_name = job_name
        self.script = job_config.get('script', '')
        self.enabled = job_config.get('enabled', True)
        self.log_file = LOG_DIR / f"{job_name}.log"
        self.concurrency_manager = concurrency_manager
        
        # 从 job_config 读取配置，回退到全局默认
        self.timeout = job_config.get('timeout', config.scheduler_default_timeout)
        self.days = job_config.get('days', config.scheduler_default_days)
        self.batch_size = job_config.get('batch_size', config.scheduler_default_batch_size)
        self.max_batches = job_config.get('max_batches', config.scheduler_default_max_batches)
        
        # 重试配置
        self.retry_on_fail = job_config.get('retry_on_fail', False)
        self.retry_attempts = job_config.get('retry_attempts', config.scheduler_retry_max_attempts)
        
        # 额外参数（用户自定义）
        self.extra_args = job_config.get('args', [])
    
    def _build_command(self) -> List[str]:
        """构建命令行参数"""
        script_path = WORK_DIR / self.script
        cmd = [sys.executable, str(script_path)]
        
        # 自动添加标准参数
        if self.days is not None:
            cmd.extend(['--days', str(self.days)])
        if self.batch_size is not None:
            cmd.extend(['--batch-size', str(self.batch_size)])
        if self.max_batches is not None:
            cmd.extend(['--max-batches', str(self.max_batches)])
        
        # 追加用户自定义 args
        if self.extra_args:
            cmd.extend(self.extra_args)
        
        return cmd
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """计算重试延迟（指数退避）"""
        delay = config.scheduler_retry_initial_delay * (config.scheduler_retry_backoff_multiplier ** (attempt - 1))
        return min(delay, config.scheduler_retry_max_delay)
    
    def _run_once(self) -> Dict[str, Any]:
        """执行一次任务"""
        script_path = WORK_DIR / self.script
        if not script_path.exists():
            return {"success": False, "error": f"脚本不存在: {script_path}"}
        
        start_time = datetime.now()
        cmd = self._build_command()
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as log_f:
                log_f.write(f"\n{'='*80}\n")
                log_f.write(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_f.write(f"命令: {' '.join(cmd)}\n")
                log_f.write(f"超时: {self.timeout}s\n")
                log_f.write(f"{'='*80}\n\n")
                
                result = subprocess.run(
                    cmd,
                    cwd=WORK_DIR,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=self.timeout
                )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                return {"success": True, "duration": duration}
            else:
                return {"success": False, "duration": duration, "returncode": result.returncode}
        
        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            return {"success": False, "duration": duration, "error": f"超时（{self.timeout}s）"}
        
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            return {"success": False, "duration": duration, "error": str(e)}
    
    def run(self) -> Dict[str, Any]:
        """执行任务（带重试）"""
        if not self.enabled:
            logger.info(f"任务 [{self.job_name}] 已禁用，跳过执行")
            return {"success": True, "skipped": True}
        
        # 获取并发许可
        self.concurrency_manager.acquire(self.job_name)
        
        try:
            max_attempts = self.retry_attempts + 1 if (self.retry_on_fail and config.scheduler_retry_enabled) else 1
            
            for attempt in range(1, max_attempts + 1):
                attempt_str = f"[{attempt}/{max_attempts}]" if max_attempts > 1 else ""
                logger.info(f"🚀 任务 [{self.job_name}] {attempt_str} 开始执行: {self.script}")
                logger.info(f"   参数: days={self.days}, batch_size={self.batch_size}, max_batches={self.max_batches}, timeout={self.timeout}s")
                
                result = self._run_once()
                
                if result.get("success"):
                    duration = result.get("duration", 0)
                    logger.info(f"✅ 任务 [{self.job_name}] 执行成功，耗时 {duration:.1f}s，日志: {self.log_file}")
                    return {"success": True, "attempts": attempt, "duration": duration}
                
                # 执行失败
                duration = result.get("duration", 0)
                error = result.get("error", f"退出码 {result.get('returncode', '未知')}")
                logger.error(f"❌ 任务 [{self.job_name}] {attempt_str} 执行失败，耗时 {duration:.1f}s: {error}")
                
                # 检查是否需要重试
                if attempt < max_attempts:
                    delay = self._calculate_retry_delay(attempt)
                    logger.info(f"⏳ 任务 [{self.job_name}] 将在 {delay:.0f}s 后重试...")
                    time.sleep(delay)
            
            # 所有重试都失败
            logger.error(f"💥 任务 [{self.job_name}] 重试 {max_attempts} 次后仍失败，日志: {self.log_file}")
            return {"success": False, "attempts": max_attempts, "duration": duration}
        
        finally:
            # 释放并发许可
            self.concurrency_manager.release(self.job_name)


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        self.scheduler = BlockingScheduler(timezone=config.scheduler_timezone)
        self.concurrency_manager = ConcurrencyManager(config.scheduler_max_workers)
        self.jobs: Dict[str, JobRunner] = {}
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """设置信号处理器（优雅停止）"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，开始优雅停止...")
            running = self.concurrency_manager.get_running_jobs()
            if running:
                logger.info(f"等待运行中的任务完成: {running}")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def load_jobs(self):
        """从配置加载任务"""
        jobs_config = config.scheduler_jobs
        
        if not jobs_config:
            logger.warning("配置文件中未找到任务定义 (scheduler.jobs)")
            return
        
        for job_name, job_config in jobs_config.items():
            if not job_config.get('enabled', True):
                logger.info(f"任务 [{job_name}] 已禁用")
                continue
            
            cron_expr = job_config.get('cron')
            if not cron_expr:
                logger.warning(f"任务 [{job_name}] 缺少 cron 表达式")
                continue
            
            script = job_config.get('script')
            if not script:
                logger.warning(f"任务 [{job_name}] 缺少 script 字段")
                continue
            
            # 创建任务运行器
            runner = JobRunner(job_name, job_config, self.concurrency_manager)
            self.jobs[job_name] = runner
            
            # 解析 cron 表达式
            try:
                cron_parts = cron_expr.split()
                if len(cron_parts) != 5:
                    raise ValueError(f"Cron 表达式必须是 5 个字段: {cron_expr}")
                
                minute, hour, day, month, day_of_week = cron_parts
                
                trigger = CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=day,
                    month=month,
                    day_of_week=day_of_week,
                    timezone=config.scheduler_timezone
                )
                
                misfire_grace_time = job_config.get('misfire_grace_time', config.scheduler_default_misfire_grace_time)
                max_instances = job_config.get('max_instances', config.scheduler_default_max_instances)
                
                self.scheduler.add_job(
                    runner.run,
                    trigger=trigger,
                    id=job_name,
                    name=job_name,
                    max_instances=max_instances,
                    misfire_grace_time=misfire_grace_time
                )
                
                # 构建配置摘要
                days = job_config.get('days', config.scheduler_default_days)
                timeout = job_config.get('timeout', config.scheduler_default_timeout)
                retry_on_fail = job_config.get('retry_on_fail', False)
                retry_str = f", 重试={runner.retry_attempts}次" if retry_on_fail else ""
                
                logger.info(
                    f"✓ 任务 [{job_name}] 已加载: {script} "
                    f"(cron: {cron_expr}, days={days}, timeout={timeout}s{retry_str})"
                )
            
            except Exception as e:
                logger.error(f"任务 [{job_name}] 配置错误: {e}")
    
    def print_job_list(self):
        """打印任务列表和下次运行时间"""
        logger.info("\n" + "="*80)
        logger.info("已调度的任务列表:")
        logger.info("="*80)
        
        jobs = self.scheduler.get_jobs()
        if not jobs:
            logger.info("(无任务)")
        else:
            for job in jobs:
                try:
                    next_run = getattr(job, 'next_run_time', None)
                    if next_run is None and hasattr(job, 'trigger'):
                        from datetime import datetime as dt
                        import pytz
                        tz = pytz.timezone(config.scheduler_timezone)
                        next_run = job.trigger.get_next_fire_time(None, dt.now(tz))
                except Exception:
                    next_run = None
                
                next_run_str = next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else '未知'
                logger.info(f"  • {job.name:30s} 下次运行: {next_run_str}")
        
        logger.info("="*80 + "\n")
    
    def print_config_summary(self):
        """打印配置摘要"""
        logger.info("="*80)
        logger.info("数据处理任务调度器启动")
        logger.info("="*80)
        logger.info(f"工作目录: {WORK_DIR}")
        logger.info(f"日志目录: {LOG_DIR}")
        logger.info(f"时区: {config.scheduler_timezone}")
        logger.info(f"全局并发数: {config.scheduler_max_workers}")
        
        if config.scheduler_retry_enabled:
            logger.info(f"重试策略: 最多 {config.scheduler_retry_max_attempts} 次, "
                       f"间隔 {config.scheduler_retry_initial_delay}s (x{config.scheduler_retry_backoff_multiplier} 退避)")
        else:
            logger.info("重试策略: 已禁用")
        
        logger.info("="*80 + "\n")
    
    def start(self):
        """启动调度器"""
        if not config.scheduler_enabled:
            logger.warning("调度器已禁用 (scheduler.enabled=false)")
            return
        
        self.print_config_summary()
        self.load_jobs()
        
        if not self.scheduler.get_jobs():
            logger.error("未加载任何任务，退出")
            return
        
        self.print_job_list()
        
        try:
            logger.info("调度器运行中... (按 Ctrl+C 停止)\n")
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("收到停止信号")
            self.shutdown()
    
    def shutdown(self):
        """停止调度器"""
        logger.info("正在停止调度器...")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        logger.info("调度器已停止")
        sys.exit(0)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='数据处理任务调度器')
    parser.add_argument('--test', type=str, help='测试运行指定任务（立即执行，不启动调度器）')
    parser.add_argument('--list', action='store_true', help='列出所有可用任务')
    args = parser.parse_args()
    
    # 列出任务
    if args.list:
        logger.info("可用的任务列表:")
        logger.info("-" * 80)
        jobs_config = config.scheduler_jobs
        for job_name, job_config in jobs_config.items():
            enabled = "✓" if job_config.get('enabled', True) else "✗"
            script = job_config.get('script', '')
            cron = job_config.get('cron', '')
            days = job_config.get('days', config.scheduler_default_days)
            timeout = job_config.get('timeout', config.scheduler_default_timeout)
            logger.info(f"  {enabled} {job_name:30s} {script:30s}")
            logger.info(f"      cron: {cron}, days: {days}, timeout: {timeout}s")
        return
    
    # 测试运行单个任务
    if args.test:
        logger.info(f"测试模式：立即执行任务 [{args.test}]")
        jobs_config = config.scheduler_jobs
        
        if args.test not in jobs_config:
            logger.error(f"任务 [{args.test}] 不存在")
            logger.info("使用 --list 查看所有可用任务")
            sys.exit(1)
        
        job_config = jobs_config[args.test]
        concurrency_manager = ConcurrencyManager(0)  # 测试模式不限制并发
        runner = JobRunner(args.test, job_config, concurrency_manager)
        result = runner.run()
        
        if result.get("success"):
            logger.info("测试完成 ✅")
        else:
            logger.error("测试失败 ❌")
            sys.exit(1)
        return
    
    # 正常启动调度器
    scheduler = TaskScheduler()
    scheduler.start()


if __name__ == '__main__':
    main()
