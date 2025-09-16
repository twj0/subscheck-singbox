#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
速度限制器和流量統計模組
學習Go版本的ratelimit實現
"""

import time
import threading
from typing import Optional, IO
from io import BytesIO


class TokenBucket:
    """
    令牌桶速度限制器
    學習Go版本的github.com/juju/ratelimit實現
    """
    
    def __init__(self, rate_bytes_per_sec: float, capacity_bytes: int):
        """
        初始化令牌桶
        
        Args:
            rate_bytes_per_sec: 每秒補充的令牌數（字節）
            capacity_bytes: 桶的容量（字節）
        """
        self.rate = rate_bytes_per_sec
        self.capacity = capacity_bytes
        self.tokens = capacity_bytes
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def take(self, bytes_count: int) -> bool:
        """
        嘗試從桶中取出指定數量的令牌
        
        Args:
            bytes_count: 需要的字節數
            
        Returns:
            bool: 是否成功取出令牌
        """
        with self.lock:
            now = time.time()
            # 計算應該補充的令牌數
            time_passed = now - self.last_update
            tokens_to_add = time_passed * self.rate
            
            # 補充令牌，但不超過容量
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_update = now
            
            # 檢查是否有足夠的令牌
            if self.tokens >= bytes_count:
                self.tokens -= bytes_count
                return True
            return False
    
    def wait(self, bytes_count: int) -> float:
        """
        等待直到有足夠的令牌可用
        
        Args:
            bytes_count: 需要的字節數
            
        Returns:
            float: 等待的時間（秒）
        """
        with self.lock:
            now = time.time()
            time_passed = now - self.last_update
            tokens_to_add = time_passed * self.rate
            
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_update = now
            
            if self.tokens >= bytes_count:
                self.tokens -= bytes_count
                return 0.0
            
            # 計算需要等待的時間
            tokens_needed = bytes_count - self.tokens
            wait_time = tokens_needed / self.rate
            return wait_time


class RateLimitedReader:
    """
    速度限制的讀取器
    包裝任何IO對象，添加速度限制功能
    """
    
    def __init__(self, reader: IO[bytes], rate_limiter: Optional[TokenBucket] = None):
        """
        初始化速度限制讀取器
        
        Args:
            reader: 原始讀取器
            rate_limiter: 速度限制器，None表示不限制
        """
        self.reader = reader
        self.rate_limiter = rate_limiter
    
    def read(self, size: int = -1) -> bytes:
        """
        讀取數據，受速度限制
        
        Args:
            size: 讀取的字節數，-1表示讀取所有
            
        Returns:
            bytes: 讀取的數據
        """
        data = self.reader.read(size)
        
        if self.rate_limiter and data:
            # 等待直到速度限制允許
            wait_time = self.rate_limiter.wait(len(data))
            if wait_time > 0:
                time.sleep(wait_time)
        
        return data
    
    def __getattr__(self, name):
        """代理其他方法到原始讀取器"""
        return getattr(self.reader, name)


class GlobalStats:
    """
    全局流量統計
    學習Go版本的原子操作統計
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.total_bytes = 0
            self.total_nodes_tested = 0
            self.successful_nodes = 0
            self.failed_nodes = 0
            self.lock = threading.Lock()
            self._initialized = True
    
    def add_bytes(self, bytes_count: int):
        """添加流量統計"""
        with self.lock:
            self.total_bytes += bytes_count
    
    def add_node_tested(self, success: bool = True):
        """添加節點測試統計"""
        with self.lock:
            self.total_nodes_tested += 1
            if success:
                self.successful_nodes += 1
            else:
                self.failed_nodes += 1
    
    def get_total_gb(self) -> float:
        """獲取總流量（GB）"""
        with self.lock:
            return self.total_bytes / (1024**3)
    
    def get_success_rate(self) -> float:
        """獲取成功率"""
        with self.lock:
            if self.total_nodes_tested == 0:
                return 0.0
            return self.successful_nodes / self.total_nodes_tested * 100
    
    def reset(self):
        """重置統計"""
        with self.lock:
            self.total_bytes = 0
            self.total_nodes_tested = 0
            self.successful_nodes = 0
            self.failed_nodes = 0
    
    def get_stats_summary(self) -> str:
        """獲取統計摘要"""
        with self.lock:
            return (f"總流量: {self.get_total_gb():.3f}GB | "
                   f"測試節點: {self.total_nodes_tested} | "
                   f"成功: {self.successful_nodes} | "
                   f"失敗: {self.failed_nodes} | "
                   f"成功率: {self.get_success_rate():.1f}%")


# 全局實例
global_stats = GlobalStats()


def create_rate_limiter(speed_limit_mbps: float) -> Optional[TokenBucket]:
    """
    創建速度限制器
    
    Args:
        speed_limit_mbps: 速度限制（MB/s），0表示不限制
        
    Returns:
        TokenBucket or None: 速度限制器，None表示不限制
    """
    if speed_limit_mbps <= 0:
        return None
    
    # 轉換為字節/秒
    rate_bytes_per_sec = speed_limit_mbps * 1024 * 1024
    # 容量設為10倍速率，允許突發
    capacity_bytes = int(rate_bytes_per_sec * 10)
    
    return TokenBucket(rate_bytes_per_sec, capacity_bytes)


def wrap_reader_with_rate_limit(reader: IO[bytes], rate_limiter: Optional[TokenBucket] = None) -> RateLimitedReader:
    """
    包裝讀取器，添加速度限制
    
    Args:
        reader: 原始讀取器
        rate_limiter: 速度限制器
        
    Returns:
        RateLimitedReader: 速度限制的讀取器
    """
    return RateLimitedReader(reader, rate_limiter)
