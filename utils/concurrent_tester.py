#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
並發測試器
學習Go版本的工作池模式和並發控制
"""

import asyncio
import time
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from utils.logger import log
from utils.rate_limiter import global_stats


class WorkerPool:
    """
    工作池，學習Go版本的worker goroutine模式
    """
    
    def __init__(self, worker_count: int = 20, success_limit: int = 0):
        """
        初始化工作池
        
        Args:
            worker_count: 工作線程數
            success_limit: 成功節點數量限制，0表示不限制
        """
        self.worker_count = worker_count
        self.success_limit = success_limit
        self.task_queue = asyncio.Queue()
        self.result_queue = asyncio.Queue()
        self.workers = []
        self.results = []
        self.progress = 0
        self.successful_count = 0
        self.force_stop = False
        
    async def worker(self, worker_id: int, test_func: Callable):
        """
        工作線程，學習Go版本的worker函數
        
        Args:
            worker_id: 工作線程ID
            test_func: 測試函數
        """
        log.debug(f"Worker {worker_id} 啟動")
        
        while True:
            try:
                # 獲取任務
                task = await self.task_queue.get()
                if task is None:  # 結束信號
                    break
                
                node, index = task
                
                # 檢查是否需要停止
                if self.force_stop:
                    self.task_queue.task_done()
                    break
                
                # 檢查成功數量限制
                if self.success_limit > 0 and self.successful_count >= self.success_limit:
                    log.debug(f"達到成功節點數量限制: {self.success_limit}")
                    self.task_queue.task_done()
                    break
                
                # 執行測試
                log.debug(f"Worker {worker_id} 處理節點: {node.get('name', 'Unknown')}")
                result = await test_func(node, index)
                
                if result:
                    await self.result_queue.put(result)
                    if result.get('status') == 'success':
                        self.successful_count += 1
                
                # 更新進度
                self.progress += 1
                global_stats.add_node_tested(result.get('status') == 'success' if result else False)
                
                self.task_queue.task_done()
                
            except Exception as e:
                log.error(f"Worker {worker_id} 異常: {e}")
                self.task_queue.task_done()
        
        log.debug(f"Worker {worker_id} 退出")
    
    async def distribute_tasks(self, nodes: List[Dict[str, Any]]):
        """
        分發任務，學習Go版本的task distribution
        
        Args:
            nodes: 節點列表
        """
        log.debug(f"開始分發 {len(nodes)} 個任務")
        
        for index, node in enumerate(nodes):
            # 檢查是否需要停止
            if self.force_stop:
                log.warning("收到停止信號，停止分發任務")
                break
            
            # 檢查成功數量限制
            if self.success_limit > 0 and self.successful_count >= self.success_limit:
                log.info(f"達到成功節點數量限制: {self.success_limit}")
                break
            
            await self.task_queue.put((node, index))
        
        # 發送結束信號給所有worker
        for _ in self.workers:
            await self.task_queue.put(None)
        
        log.debug("任務分發完成")
    
    async def collect_results(self):
        """
        收集結果，學習Go版本的result collection
        """
        log.debug("開始收集結果")
        
        while True:
            try:
                result = await asyncio.wait_for(self.result_queue.get(), timeout=1.0)
                if result is None:  # 結束信號
                    break
                
                self.results.append(result)
                log.debug(f"收集到結果: {result.get('name', 'Unknown')} - {result.get('status', 'unknown')}")
                
            except asyncio.TimeoutError:
                # 檢查是否所有worker都完成了
                if all(worker.done() for worker in self.workers):
                    break
                continue
        
        log.debug(f"結果收集完成，共 {len(self.results)} 個結果")
    
    async def run_tests(self, nodes: List[Dict[str, Any]], test_func: Callable) -> List[Dict[str, Any]]:
        """
        運行測試，學習Go版本的主運行邏輯
        
        Args:
            nodes: 節點列表
            test_func: 測試函數
            
        Returns:
            List[Dict[str, Any]]: 測試結果
        """
        # 調整worker數量
        actual_worker_count = min(self.worker_count, len(nodes))
        log.info(f"啟動 {actual_worker_count} 個工作線程測試 {len(nodes)} 個節點")
        
        # 啟動workers
        self.workers = [
            asyncio.create_task(self.worker(i, test_func))
            for i in range(actual_worker_count)
        ]
        
        # 啟動任務分發和結果收集
        distributor = asyncio.create_task(self.distribute_tasks(nodes))
        collector = asyncio.create_task(self.collect_results())
        
        # 等待所有任務完成
        await asyncio.gather(distributor, *self.workers, return_exceptions=True)
        
        # 結束結果收集
        await self.result_queue.put(None)
        await collector
        
        log.info(f"測試完成: {len(self.results)} 個結果, 成功率: {global_stats.get_success_rate():.1f}%")
        return self.results
    
    def stop(self):
        """停止測試"""
        self.force_stop = True
        log.warning("工作池收到停止信號")


class ProgressReporter:
    """
    進度報告器，學習Go版本的進度顯示
    """
    
    def __init__(self, total_nodes: int, print_interval: float = 1.0):
        """
        初始化進度報告器
        
        Args:
            total_nodes: 總節點數
            print_interval: 打印間隔（秒）
        """
        self.total_nodes = total_nodes
        self.print_interval = print_interval
        self.start_time = time.time()
        self.last_print_time = 0
        
    async def start_reporting(self, worker_pool: WorkerPool):
        """
        開始進度報告
        
        Args:
            worker_pool: 工作池實例
        """
        log.info("開始進度監控")
        
        while True:
            current_time = time.time()
            
            # 檢查是否需要打印進度
            if current_time - self.last_print_time >= self.print_interval:
                await self._print_progress(worker_pool, current_time)
                self.last_print_time = current_time
            
            # 檢查是否完成
            if worker_pool.progress >= self.total_nodes or worker_pool.force_stop:
                await self._print_final_progress(worker_pool, current_time)
                break
            
            await asyncio.sleep(0.1)
    
    async def _print_progress(self, worker_pool: WorkerPool, current_time: float):
        """打印進度信息"""
        if self.total_nodes == 0:
            return
        
        progress_percent = (worker_pool.progress / self.total_nodes) * 100
        elapsed_time = current_time - self.start_time
        
        # 計算ETA
        if worker_pool.progress > 0:
            avg_time_per_node = elapsed_time / worker_pool.progress
            remaining_nodes = self.total_nodes - worker_pool.progress
            eta = remaining_nodes * avg_time_per_node
        else:
            eta = 0
        
        # 生成進度條
        bar_length = 40
        filled_length = int(bar_length * progress_percent / 100)
        bar = '=' * filled_length + '-' * (bar_length - filled_length)
        
        log.info(f"進度: [{bar}] {progress_percent:.1f}% ({worker_pool.progress}/{self.total_nodes}) "
                f"成功: {worker_pool.successful_count} ETA: {eta:.1f}s")
    
    async def _print_final_progress(self, worker_pool: WorkerPool, current_time: float):
        """打印最終進度"""
        elapsed_time = current_time - self.start_time
        success_rate = (worker_pool.successful_count / worker_pool.progress * 100) if worker_pool.progress > 0 else 0
        
        log.info(f"✅ 測試完成! 用時: {elapsed_time:.1f}s, "
                f"處理: {worker_pool.progress}/{self.total_nodes}, "
                f"成功: {worker_pool.successful_count}, "
                f"成功率: {success_rate:.1f}%")
