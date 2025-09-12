#!/usr/bin/env python3
"""
Cron调度支持模块
学习Go版本的灵活调度机制
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Callable, Optional
from croniter import croniter

from utils.logger import log

class CronScheduler:
    """Cron表达式调度器"""
    
    def __init__(self):
        self.is_running = False
        self.cron_task = None
        self.interval_task = None
        self.callback = None
        
    def set_callback(self, callback: Callable[[], None]):
        """设置回调函数"""
        self.callback = callback
    
    async def start_cron_schedule(self, cron_expression: str):
        """启动Cron调度"""
        if not cron_expression:
            log.error("Cron表达式不能为空")
            return False
            
        try:
            # 验证Cron表达式
            cron = croniter(cron_expression, datetime.now())
            next_time = cron.get_next(datetime)
            log.info(f"Cron调度启动，表达式: {cron_expression}")
            log.info(f"下次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 停止现有任务
            await self.stop()
            
            self.is_running = True
            self.cron_task = asyncio.create_task(self._cron_loop(cron_expression))
            return True
            
        except Exception as e:
            log.error(f"Cron表达式解析失败: {cron_expression}, 错误: {e}")
            return False
    
    async def start_interval_schedule(self, interval_minutes: int):
        """启动间隔调度"""
        if interval_minutes <= 0:
            log.error("间隔时间必须大于0")
            return False
            
        log.info(f"间隔调度启动，间隔: {interval_minutes}分钟")
        
        # 停止现有任务
        await self.stop()
        
        self.is_running = True
        self.interval_task = asyncio.create_task(self._interval_loop(interval_minutes))
        return True
    
    async def _cron_loop(self, cron_expression: str):
        """Cron调度循环"""
        cron = croniter(cron_expression, datetime.now())
        
        while self.is_running:
            try:
                # 计算下次执行时间
                next_time = cron.get_next(datetime)
                now = datetime.now()
                sleep_seconds = (next_time - now).total_seconds()
                
                if sleep_seconds > 0:
                    log.info(f"下次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    # 使用可中断的睡眠
                    await self._interruptible_sleep(sleep_seconds)
                
                if self.is_running and self.callback:
                    log.info("Cron调度触发执行")
                    try:
                        if asyncio.iscoroutinefunction(self.callback):
                            await self.callback()
                        else:
                            self.callback()
                    except Exception as e:
                        log.error(f"调度回调执行失败: {e}")
                        
            except Exception as e:
                log.error(f"Cron调度循环异常: {e}")
                await asyncio.sleep(60)  # 出错时等待1分钟再继续
    
    async def _interval_loop(self, interval_minutes: int):
        """间隔调度循环"""
        interval_seconds = interval_minutes * 60
        
        while self.is_running:
            try:
                next_time = datetime.now() + timedelta(minutes=interval_minutes)
                log.info(f"下次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 可中断的睡眠
                await self._interruptible_sleep(interval_seconds)
                
                if self.is_running and self.callback:
                    log.info("间隔调度触发执行")
                    try:
                        if asyncio.iscoroutinefunction(self.callback):
                            await self.callback()
                        else:
                            self.callback()
                    except Exception as e:
                        log.error(f"调度回调执行失败: {e}")
                        
            except Exception as e:
                log.error(f"间隔调度循环异常: {e}")
                await asyncio.sleep(60)
    
    async def _interruptible_sleep(self, seconds: float):
        """可中断的睡眠"""
        end_time = time.time() + seconds
        
        while time.time() < end_time and self.is_running:
            remaining = end_time - time.time()
            sleep_time = min(remaining, 10)  # 每10秒检查一次是否需要停止
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    async def trigger_manual(self):
        """手动触发执行"""
        if self.callback:
            log.info("手动触发执行")
            try:
                if asyncio.iscoroutinefunction(self.callback):
                    await self.callback()
                else:
                    self.callback()
            except Exception as e:
                log.error(f"手动触发执行失败: {e}")
        else:
            log.warning("未设置回调函数，无法执行")
    
    async def stop(self):
        """停止调度"""
        self.is_running = False
        
        if self.cron_task and not self.cron_task.done():
            self.cron_task.cancel()
            try:
                await self.cron_task
            except asyncio.CancelledError:
                pass
        
        if self.interval_task and not self.interval_task.done():
            self.interval_task.cancel()
            try:
                await self.interval_task
            except asyncio.CancelledError:
                pass
        
        log.info("调度器已停止")
    
    def get_next_execution_time(self, cron_expression: str = None, interval_minutes: int = None) -> Optional[datetime]:
        """获取下次执行时间"""
        try:
            if cron_expression:
                cron = croniter(cron_expression, datetime.now())
                return cron.get_next(datetime)
            elif interval_minutes:
                return datetime.now() + timedelta(minutes=interval_minutes)
        except Exception as e:
            log.error(f"计算下次执行时间失败: {e}")
        return None
    
    def is_valid_cron(self, cron_expression: str) -> bool:
        """验证Cron表达式是否有效"""
        try:
            cron = croniter(cron_expression, datetime.now())
            cron.get_next()  # 尝试获取下次执行时间
            return True
        except Exception:
            return False

# 全局调度器实例
scheduler = CronScheduler()