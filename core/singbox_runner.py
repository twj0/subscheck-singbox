# core/singbox_runner.py

import os
import json
import asyncio
import tempfile
import socket
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from utils.logger import log

class SingBoxConfig:
    """Sing-box配置生成器"""
    
    @staticmethod
    def generate_shadowsocks_config(node: Dict, port: int) -> Dict:
        """生成Shadowsocks配置"""
        return {
            "type": "shadowsocks",
            "tag": "proxy",
            "server": node['server'],
            "server_port": node['port'],
            "method": node['method'],
            "password": node['password']
        }
    
    @staticmethod
    def generate_vmess_config(node: Dict, port: int) -> Dict:
        """生成VMess配置"""
        outbound = {
            "type": "vmess",
            "tag": "proxy",
            "server": node['server'],
            "server_port": node['port'],
            "uuid": node['uuid'],
            "alter_id": node.get('alterId', 0)
        }
        
        # 处理传输设置
        if node.get('network') == 'ws':
            outbound["transport"] = {
                "type": "ws",
                "path": node.get('path', '/'),
                "headers": {
                    "Host": node.get('host', node['server'])
                }
            }
        
        # 处理TLS设置
        if node.get('tls') == 'tls':
            outbound["tls"] = {
                "enabled": True,
                "server_name": node.get('sni', node.get('host', node['server']))
            }
        
        return outbound
    
    @staticmethod
    def generate_vless_config(node: Dict, port: int) -> Dict:
        """生成VLESS配置"""
        outbound = {
            "type": "vless",
            "tag": "proxy",
            "server": node['server'],
            "server_port": node['port'],
            "uuid": node['uuid']
        }
        
        # 处理传输设置
        if node.get('network') == 'ws':
            outbound["transport"] = {
                "type": "ws",
                "path": node.get('path', '/'),
                "headers": {
                    "Host": node.get('host', node['server'])
                }
            }
        
        # 处理TLS设置
        if node.get('tls') == 'tls':
            outbound["tls"] = {
                "enabled": True,
                "server_name": node.get('sni', node.get('host', node['server']))
            }
        
        return outbound
    
    @staticmethod
    def generate_trojan_config(node: Dict, port: int) -> Dict:
        """生成Trojan配置"""
        outbound = {
            "type": "trojan",
            "tag": "proxy",
            "server": node['server'],
            "server_port": node['port'],
            "password": node['password']
        }
        
        # 处理TLS设置
        if node.get('tls') == 'tls':
            outbound["tls"] = {
                "enabled": True,
                "server_name": node.get('sni', node.get('host', node['server']))
            }
        
        return outbound
    
    @staticmethod
    def generate_config(node: Dict, port: int) -> Dict:
        """根据节点类型生成完整的Sing-box配置"""
        
        # 根据节点类型生成出站配置
        node_type = node.get('type', '').lower()
        
        if node_type == 'shadowsocks' or node_type == 'ss':
            outbound = SingBoxConfig.generate_shadowsocks_config(node, port)
        elif node_type == 'vmess':
            outbound = SingBoxConfig.generate_vmess_config(node, port)
        elif node_type == 'vless':
            outbound = SingBoxConfig.generate_vless_config(node, port)
        elif node_type == 'trojan':
            outbound = SingBoxConfig.generate_trojan_config(node, port)
        else:
            raise ValueError(f"不支持的节点类型: {node_type}")
        
        # 完整的Sing-box配置
        config = {
            "log": {
                "level": "error",
                "output": "sing-box.log"
            },
            "inbounds": [
                {
                    "type": "socks",
                    "tag": "socks-in",
                    "listen": "127.0.0.1",
                    "listen_port": port,
                    "users": []
                }
            ],
            "outbounds": [
                outbound,
                {
                    "type": "direct",
                    "tag": "direct"
                }
            ],
            "route": {
                "rules": [
                    {
                        "outbound": "proxy"
                    }
                ]
            }
        }
        
        return config

class SingBoxRunner:
    """Sing-box运行器，用于启动和管理Sing-box进程"""
    
    def __init__(self):
        self.processes = {}
        self.executable = self._find_singbox_executable()
        self.port_range_start = 10800
        self.port_range_end = 11800
    
    def _find_singbox_executable(self) -> str:
        """查找Sing-box可执行文件"""
        possible_paths = [
            "sing-box-1.12.5-windows-amd64/sing-box-1.12.5-windows-amd64/sing-box.exe",
            "sing-box.exe",
            "sing-box"
        ]
        
        project_root = Path(__file__).parent.parent
        
        for path in possible_paths:
            full_path = project_root / path
            if full_path.exists():
                log.debug(f"找到Sing-box可执行文件: {full_path}")
                return str(full_path)
        
        raise FileNotFoundError("未找到Sing-box可执行文件")
    
    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False
    
    def _find_available_port(self, preferred_port: int) -> int:
        """查找可用端口，优先使用首选端口"""
        # 首先检查首选端口
        if self._is_port_available(preferred_port):
            return preferred_port
        
        # 在范围内寻找可用端口
        for port in range(self.port_range_start, self.port_range_end):
            if port not in self.processes and self._is_port_available(port):
                return port
        
        raise RuntimeError(f"无法在范围 {self.port_range_start}-{self.port_range_end} 内找到可用端口")
    
    async def start_singbox(self, node: Dict, port: int) -> Tuple[bool, Optional[asyncio.subprocess.Process], Optional[str]]:
        """启动Sing-box进程"""
        config_file = None
        try:
            # 确保端口可用
            if port in self.processes:
                await self.stop_singbox(port)
                await asyncio.sleep(1.0)  # 增加等待时间确保端口释放
            
            # 查找可用端口
            actual_port = self._find_available_port(port)
            if actual_port != port:
                log.debug(f"端口 {port} 不可用，使用端口 {actual_port}")
            
            # 生成配置
            config = SingBoxConfig.generate_config(node, actual_port)
            
            # 创建临时配置文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                config_file = f.name
            
            log.debug(f"Sing-box配置文件创建于: {config_file}")
            
            # 启动Sing-box
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "run",
                "-c", config_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待进程启动，并检查进程状态
            for _ in range(10):  # 最多检查10次，每次0.2秒
                await asyncio.sleep(0.2)
                if process.returncode is not None:
                    # 进程已退出
                    break
                # 检查端口是否已被监听
                if not self._is_port_available(actual_port):
                    # 端口已被占用，说明进程启动成功
                    break
            
            if process.returncode is None and not self._is_port_available(actual_port):
                # 进程仍在运行且端口被占用
                self.processes[actual_port] = (process, config_file, actual_port)
                log.debug(f"Sing-box进程启动成功，PID: {process.pid}，端口: {actual_port}")
                return True, process, None
            else:
                # 进程启动失败或已退出
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                
                stdout, stderr = await process.communicate()
                error_msg = stderr.decode('utf-8') if stderr else stdout.decode('utf-8')
                log.error(f"Sing-box启动失败，返回码: {process.returncode}")
                log.error(f"错误输出: {error_msg}")
                
                # 清理临时文件
                if config_file and os.path.exists(config_file):
                    try:
                        os.unlink(config_file)
                    except Exception as e:
                        log.warning(f"清理配置文件失败: {e}")
                
                return False, None, f"Sing-box启动失败。返回码: {process.returncode}\n错误: {error_msg[:500]}"  # 限制错误信息长度
                
        except Exception as e:
            log.error(f"启动Sing-box时发生异常: {e}")
            return False, None, f"启动Sing-box时发生异常: {e}"
    
    async def stop_singbox(self, port: int):
        """停止指定端口的Sing-box进程"""
        if port in self.processes:
            process, config_file, actual_port = self.processes[port]
            try:
                if process.returncode is None:  # 进程仍在运行
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                        log.debug(f"Sing-box进程 {process.pid} 正常终止")
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                        log.debug(f"Sing-box进程 {process.pid} 被强制终止")
                else:
                    log.debug(f"Sing-box进程 {process.pid} 已经退出")
            except Exception as e:
                log.warning(f"终止Sing-box进程时出错: {e}")
            
            # 清理临时配置文件
            if config_file and os.path.exists(config_file):
                try:
                    os.unlink(config_file)
                    log.debug(f"已清理配置文件: {config_file}")
                except Exception as e:
                    log.warning(f"清理配置文件失败: {e}")
            
            del self.processes[port]
            
            # 等待端口释放
            for _ in range(10):
                if self._is_port_available(actual_port):
                    break
                await asyncio.sleep(0.1)
    
    async def cleanup_all(self):
        """清理所有Sing-box进程"""
        for port in list(self.processes.keys()):
            await self.stop_singbox(port)