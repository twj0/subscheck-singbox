#!/usr/bin/env python3
"""
流量统计和进度监控模块
学习Go版本的详细统计机制
"""
import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from utils.logger import log

@dataclass
class TestStats:
    """测试统计数据"""
    total_nodes: int = 0
    tested_nodes: int = 0
    success_nodes: int = 0
    failed_nodes: int = 0
    total_bytes: int = 0
    total_time: float = 0.0
    start_time: Optional[datetime] = None
    current_phase: str = "准备中"
    
    # 实时统计
    current_node_name: str = ""
    current_progress: float = 0.0
    
    # 性能统计
    avg_latency: float = 0.0
    avg_speed: float = 0.0
    max_speed: float = 0.0
    min_speed: float = float('inf')

class StatsMonitor:
    """统计监控器"""
    
    def __init__(self):
        self.stats = TestStats()
        self.lock = threading.Lock()
        self.speed_history = []
        self.latency_history = []
        self.node_results = []
        
    def start_test(self, total_nodes: int):
        """开始测试"""
        with self.lock:
            self.stats = TestStats(
                total_nodes=total_nodes,
                start_time=datetime.now(),
                current_phase="初始化"
            )
            self.speed_history.clear()
            self.latency_history.clear()
            self.node_results.clear()
        
        log.info(f"开始测试，总节点数: {total_nodes}")
    
    def update_phase(self, phase: str):
        """更新当前阶段"""
        with self.lock:
            self.stats.current_phase = phase
        log.info(f"阶段更新: {phase}")
    
    def update_current_node(self, node_name: str):
        """更新当前测试节点"""
        with self.lock:
            self.stats.current_node_name = node_name
            self.stats.tested_nodes += 1
            self.stats.current_progress = (self.stats.tested_nodes / self.stats.total_nodes) * 100
    
    def add_success_result(self, node_name: str, latency: float, speed: float, bytes_downloaded: int):
        """添加成功结果"""
        with self.lock:
            self.stats.success_nodes += 1
            self.stats.total_bytes += bytes_downloaded
            
            # 更新速度统计
            if speed > 0:
                self.speed_history.append(speed)
                self.stats.max_speed = max(self.stats.max_speed, speed)
                self.stats.min_speed = min(self.stats.min_speed, speed)
                self.stats.avg_speed = sum(self.speed_history) / len(self.speed_history)
            
            # 更新延迟统计
            if latency > 0:
                self.latency_history.append(latency)
                self.stats.avg_latency = sum(self.latency_history) / len(self.latency_history)
            
            # 保存节点结果
            self.node_results.append({
                'name': node_name,
                'latency': latency,
                'speed': speed,
                'bytes': bytes_downloaded,
                'status': 'success'
            })
    
    def add_failed_result(self, node_name: str, error: str):
        """添加失败结果"""
        with self.lock:
            self.stats.failed_nodes += 1
            self.node_results.append({
                'name': node_name,
                'error': error,
                'status': 'failed'
            })
    
    def add_bytes(self, bytes_count: int):
        """添加下载字节数"""
        with self.lock:
            self.stats.total_bytes += bytes_count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        with self.lock:
            elapsed_time = 0
            if self.stats.start_time:
                elapsed_time = (datetime.now() - self.stats.start_time).total_seconds()
            
            # 计算成功率
            success_rate = 0
            if self.stats.tested_nodes > 0:
                success_rate = (self.stats.success_nodes / self.stats.tested_nodes) * 100
            
            # 格式化流量
            total_mb = self.stats.total_bytes / (1024 * 1024)
            total_gb = total_mb / 1024
            
            return {
                'total_nodes': self.stats.total_nodes,
                'tested_nodes': self.stats.tested_nodes,
                'success_nodes': self.stats.success_nodes,
                'failed_nodes': self.stats.failed_nodes,
                'progress': round(self.stats.current_progress, 1),
                'success_rate': round(success_rate, 1),
                'current_phase': self.stats.current_phase,
                'current_node': self.stats.current_node_name,
                'elapsed_time': round(elapsed_time, 1),
                'total_bytes': self.stats.total_bytes,
                'total_mb': round(total_mb, 2),
                'total_gb': round(total_gb, 3),
                'avg_latency': round(self.stats.avg_latency, 1),
                'avg_speed': round(self.stats.avg_speed, 2),
                'max_speed': round(self.stats.max_speed, 2),
                'min_speed': round(self.stats.min_speed, 2) if self.stats.min_speed != float('inf') else 0,
                'speed_count': len(self.speed_history),
                'latency_count': len(self.latency_history)
            }
    
    def get_formatted_summary(self) -> str:
        """获取格式化的统计摘要"""
        stats = self.get_stats()
        
        summary = f"""
📊 测试统计摘要
========================================
总节点数: {stats['total_nodes']}
已测试: {stats['tested_nodes']} ({stats['progress']}%)
成功: {stats['success_nodes']} | 失败: {stats['failed_nodes']}
成功率: {stats['success_rate']}%
总耗时: {stats['elapsed_time']}秒
当前阶段: {stats['current_phase']}

📈 性能统计
========================================
平均延迟: {stats['avg_latency']}ms
平均速度: {stats['avg_speed']}Mbps
最高速度: {stats['max_speed']}Mbps
最低速度: {stats['min_speed']}Mbps

📦 流量统计
========================================
总下载量: {stats['total_gb']}GB ({stats['total_mb']}MB)
有效测速: {stats['speed_count']}次
有效延迟: {stats['latency_count']}次
"""
        return summary
    
    def get_top_nodes(self, limit: int = 10) -> list:
        """获取最优节点列表"""
        with self.lock:
            # 只返回成功的节点
            success_nodes = [node for node in self.node_results if node['status'] == 'success']
            
            # 按速度排序
            success_nodes.sort(key=lambda x: x.get('speed', 0), reverse=True)
            
            return success_nodes[:limit]
    
    def export_results(self) -> Dict[str, Any]:
        """导出完整结果"""
        with self.lock:
            return {
                'timestamp': datetime.now().isoformat(),
                'summary': self.get_stats(),
                'top_nodes': self.get_top_nodes(20),
                'all_results': self.node_results.copy()
            }
    
    def reset(self):
        """重置统计"""
        with self.lock:
            self.stats = TestStats()
            self.speed_history.clear()
            self.latency_history.clear()
            self.node_results.clear()

# 全局统计监控器
stats_monitor = StatsMonitor()