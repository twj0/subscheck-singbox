#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
資源管理器
學習Go版本的ProxyClient自動資源清理機制
"""

import asyncio
import time
import signal
import psutil
import os
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from utils.logger import log


class ProcessManager:
    """
    進程管理器，學習Go版本的資源自動清理
    """
    
    def __init__(self):
        self.active_processes: List[asyncio.subprocess.Process] = []
        self.process_info: Dict[int, Dict[str, Any]] = {}
        self._cleanup_lock = asyncio.Lock()
        
    async def create_process(self, cmd: List[str], cwd: Optional[str] = None, **kwargs) -> asyncio.subprocess.Process:
        """
        創建進程並註冊到管理器
        
        Args:
            cmd: 命令列表
            cwd: 工作目錄
            **kwargs: 其他參數
            
        Returns:
            asyncio.subprocess.Process: 創建的進程
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs
            )
            
            # 註冊進程
            self.active_processes.append(process)
            self.process_info[process.pid] = {
                'cmd': cmd,
                'created_at': time.time(),
                'cwd': cwd
            }
            
            log.debug(f"進程管理器: 創建進程 PID={process.pid}, CMD={' '.join(cmd)}")
            return process
            
        except Exception as e:
            log.error(f"創建進程失敗: {e}")
            raise
    
    async def terminate_process(self, process: asyncio.subprocess.Process, timeout: float = 5.0) -> bool:
        """
        優雅地終止進程
        
        Args:
            process: 要終止的進程
            timeout: 等待超時時間
            
        Returns:
            bool: 是否成功終止
        """
        if process.returncode is not None:
            # 進程已經結束
            await self._cleanup_process(process)
            return True
        
        try:
            log.debug(f"正在終止進程 PID={process.pid}")
            
            # 嘗試優雅終止
            process.terminate()
            
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
                log.debug(f"進程 PID={process.pid} 優雅終止成功")
            except asyncio.TimeoutError:
                # 強制殺死
                log.warning(f"進程 PID={process.pid} 優雅終止超時，強制殺死")
                process.kill()
                await process.wait()
            
            await self._cleanup_process(process)
            return True
            
        except Exception as e:
            log.error(f"終止進程 PID={process.pid} 失敗: {e}")
            return False
    
    async def _cleanup_process(self, process: asyncio.subprocess.Process):
        """清理進程記錄"""
        async with self._cleanup_lock:
            if process in self.active_processes:
                self.active_processes.remove(process)
            if process.pid in self.process_info:
                del self.process_info[process.pid]
    
    async def cleanup_all(self):
        """清理所有活動進程"""
        log.debug(f"正在清理 {len(self.active_processes)} 個活動進程")
        
        cleanup_tasks = []
        for process in self.active_processes.copy():
            cleanup_tasks.append(self.terminate_process(process))
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        log.debug("所有進程清理完成")
    
    def get_active_processes(self) -> List[Dict[str, Any]]:
        """獲取活動進程信息"""
        result = []
        for process in self.active_processes:
            if process.pid in self.process_info:
                info = self.process_info[process.pid].copy()
                info['pid'] = process.pid
                info['returncode'] = process.returncode
                result.append(info)
        return result


class PortManager:
    """
    端口管理器，學習Go版本的端口自動回收
    """
    
    def __init__(self, base_port: int = 41000):
        self.base_port = base_port
        self.allocated_ports: Dict[int, Dict[str, Any]] = {}
        self.released_ports: Dict[int, float] = {}  # port -> release_time
        self.recycle_delay = 8.0  # 端口回收延遲
        self._lock = asyncio.Lock()
    
    async def allocate_port(self, node_name: str = "unknown") -> int:
        """
        分配端口
        
        Args:
            node_name: 節點名稱
            
        Returns:
            int: 分配的端口號
        """
        async with self._lock:
            # 清理過期的已釋放端口
            current_time = time.time()
            expired_ports = [
                port for port, release_time in self.released_ports.items()
                if current_time - release_time > self.recycle_delay
            ]
            for port in expired_ports:
                del self.released_ports[port]
            
            # 找可用端口
            port = self.base_port
            while True:
                if (port not in self.allocated_ports and 
                    port not in self.released_ports and
                    not self._is_port_in_use(port)):
                    break
                port += 1
                
                # 防止無限循環
                if port > self.base_port + 1000:
                    raise RuntimeError("無法找到可用端口")
            
            # 分配端口
            self.allocated_ports[port] = {
                'node_name': node_name,
                'allocated_at': current_time
            }
            
            log.debug(f"端口管理器: 分配端口 {port} 給節點 {node_name}")
            return port
    
    async def release_port(self, port: int):
        """
        釋放端口
        
        Args:
            port: 要釋放的端口號
        """
        async with self._lock:
            if port in self.allocated_ports:
                node_name = self.allocated_ports[port]['node_name']
                del self.allocated_ports[port]
                self.released_ports[port] = time.time()
                
                log.debug(f"端口管理器: 釋放端口 {port} (節點: {node_name})")
    
    def _is_port_in_use(self, port: int) -> bool:
        """檢查端口是否被占用"""
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == port:
                    return True
            return False
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False
    
    async def cleanup_all(self):
        """清理所有端口"""
        async with self._lock:
            log.debug(f"端口管理器: 清理 {len(self.allocated_ports)} 個分配的端口")
            self.allocated_ports.clear()
            self.released_ports.clear()


class ResourceManager:
    """
    統一資源管理器，學習Go版本的自動清理機制
    """
    
    def __init__(self):
        self.process_manager = ProcessManager()
        self.port_manager = PortManager()
        self._cleanup_registered = False
    
    def register_cleanup_handlers(self):
        """註冊清理處理器"""
        if self._cleanup_registered:
            return
        
        def signal_handler(signum, frame):
            log.info("收到中斷信號，開始清理資源...")
            asyncio.create_task(self.cleanup_all())
        
        # 註冊信號處理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self._cleanup_registered = True
        log.debug("資源管理器: 清理處理器已註冊")
    
    async def cleanup_all(self):
        """清理所有資源"""
        log.info("🧹 開始清理所有資源...")
        
        # 並行清理
        await asyncio.gather(
            self.process_manager.cleanup_all(),
            self.port_manager.cleanup_all(),
            return_exceptions=True
        )
        
        log.info("✅ 資源清理完成")
    
    @asynccontextmanager
    async def managed_process(self, cmd: List[str], **kwargs):
        """
        受管理的進程上下文管理器
        學習Go版本的defer機制
        
        Args:
            cmd: 命令列表
            **kwargs: 其他參數
            
        Yields:
            asyncio.subprocess.Process: 進程對象
        """
        process = None
        try:
            process = await self.process_manager.create_process(cmd, **kwargs)
            yield process
        finally:
            if process:
                await self.process_manager.terminate_process(process)
    
    @asynccontextmanager
    async def managed_port(self, node_name: str = "unknown"):
        """
        受管理的端口上下文管理器
        
        Args:
            node_name: 節點名稱
            
        Yields:
            int: 端口號
        """
        port = None
        try:
            port = await self.port_manager.allocate_port(node_name)
            yield port
        finally:
            if port:
                await self.port_manager.release_port(port)
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """獲取資源統計"""
        return {
            'active_processes': len(self.process_manager.active_processes),
            'allocated_ports': len(self.port_manager.allocated_ports),
            'released_ports': len(self.port_manager.released_ports),
            'process_details': self.process_manager.get_active_processes()
        }


# 全局資源管理器實例
resource_manager = ResourceManager()
