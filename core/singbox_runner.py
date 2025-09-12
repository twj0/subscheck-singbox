# core/singbox_runner.py
import asyncio
import json
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

from utils.logger import log

class singboxRunner:
    """Manages the lifecycle of a single singbox process for testing a node."""

    def __init__(self, node_config: Dict[str, Any], port: int):
        self._config = self._generate_singbox_config(node_config, port)
        self._process = None
        self._config_file_path = None

    async def __aenter__(self):
        """Starts the singbox process asynchronously."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(self._config, f, indent=2)
            self._config_file_path = f.name

        # 获取sing-box的绝对路径，支持Ubuntu环境
        current_dir = Path(__file__).parent.parent
        
        # 多个可能的sing-box路径（跨平台支持）
        possible_paths = [
            # 优先查找根目录中的sing-box.exe（Windows）
            current_dir / 'sing-box.exe',
            # 其他Windows环境路径
            current_dir / 'sing-box-1.12.5-windows-amd64' / 'sing-box-1.12.5-windows-amd64' / 'sing-box.exe',
            Path('sing-box.exe'),  # 当前工作目录
            # Ubuntu/Linux环境路径
            current_dir / 'sing-box',  # 项目根目录
            Path('/usr/local/bin/sing-box'),  # 系统安装路径
            Path('/usr/bin/sing-box'),  # 标准路径
            Path('./sing-box'),  # 当前目录
        ]
        
        singbox_path = None
        for path in possible_paths:
            if path.exists():
                singbox_path = path
                log.debug(f"找到sing-box可执行文件: {singbox_path}")
                break
        
        if not singbox_path:
            available_paths = [str(p) for p in possible_paths]
            raise RuntimeError(f"sing-box可执行文件未找到。查找过的路径: {available_paths}")
        
        # 检查配置文件内容
        log.debug(f"sing-box配置文件: {self._config_file_path}")
        log.debug(f"sing-box配置内容: {json.dumps(self._config, indent=2)}")
        
        # 启动sing-box进程，增加错误处理
        try:
            # 根据操作系统设置不同的进程创建标志
            creation_flags = 0x08000000 if os.name == 'nt' else 0  # Windows下隐藏窗口
            
            # 设置环境变量，禁用代理
            env = os.environ.copy()
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('http_proxy', None)
            env.pop('https_proxy', None)
            
            self._process = await asyncio.create_subprocess_exec(
                str(singbox_path), 'run', '-c', self._config_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creation_flags,
                env=env
            )
        except Exception as e:
            raise RuntimeError(f"sing-box进程启动失败: {e}")
        
        # 等待sing-box启动，增加启动检查
        await asyncio.sleep(4)  # 增加启动等待时间

        if self._process.returncode is not None:
            # 读取stderr输出以获取错误信息
            stderr_output = ""
            stdout_output = ""
            try:
                if self._process.stderr:
                    stderr_output = await self._process.stderr.read()
                    stderr_output = stderr_output.decode('utf-8', errors='ignore')
                if self._process.stdout:
                    stdout_output = await self._process.stdout.read()
                    stdout_output = stdout_output.decode('utf-8', errors='ignore')
            except Exception as e:
                log.debug(f"读取输出失败: {e}")
            
            # 检查配置文件是否存在并记录调试信息
            debug_info = []
            if self._config_file_path and os.path.exists(self._config_file_path):
                with open(self._config_file_path, 'r') as f:
                    config_content = f.read()
                debug_info.append(f"sing-box配置: {config_content[:800]}...")  # 增加配置详情
            
            debug_info.extend([
                f"sing-box路径: {singbox_path}",
                f"返回代码: {self._process.returncode}",
                f"stderr: {stderr_output[:500]}..." if stderr_output else "stderr: 无错误输出",
                f"stdout: {stdout_output[:500]}..." if stdout_output else "stdout: 无输出"
            ])
            
            for info in debug_info:
                log.debug(info)
            
            raise RuntimeError(f"sing-box启动失败。返回代码: {self._process.returncode}。错误: {stderr_output[:300]}...")

        log.debug(f"sing-box进程启动成功，PID: {self._process.pid}，端口: {self._config['inbounds'][0]['listen_port']}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stops the singbox process and cleans up the config file."""
        if hasattr(self, '_process') and self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    log.debug(f"sing-box进程 {self._process.pid} 正常终止")
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
                    log.warning(f"sing-box进程 {self._process.pid} 强制终止")
            except Exception as e:
                log.debug(f"终止sing-box进程时出错: {e}")
            finally:
                # 清理stdout和stderr管道以防止Windows资源警告
                try:
                    if hasattr(self._process, 'stdout') and self._process.stdout:
                        self._process.stdout.close()
                    if hasattr(self._process, 'stderr') and self._process.stderr:
                        self._process.stderr.close()
                except Exception:
                    pass
                
                # Windows下需要额外等待以确保端口释放
                if os.name == 'nt':
                    await asyncio.sleep(1.5)
                else:
                    await asyncio.sleep(1.0)

        # 清理配置文件
        if hasattr(self, '_config_file_path') and self._config_file_path and os.path.exists(self._config_file_path):
            try:
                os.unlink(self._config_file_path)
            except Exception as e:
                log.debug(f"删除配置文件失败: {e}")

    def _generate_singbox_config(self, node: Dict[str, Any], socks_port: int) -> Dict[str, Any]:
        """Generates a valid singbox configuration for a given node."""
        config = {
            "log": {"level": "error"},
            "inbounds": [{
                "type": "socks",
                "listen": "127.0.0.1",
                "listen_port": socks_port,
                "sniff": True
            }],
            "outbounds": []
        }
        outbound: Dict[str, Any] = {"type": node['type'], "tag": "proxy"}

        if node['type'] == 'vless':
            outbound["server"] = node['server']
            outbound["server_port"] = int(node['port'])  # 确保端口是整数
            outbound["uuid"] = node['uuid']
            
            # 处理网络传输类型
            network = node.get('network', 'tcp')
            if network in ['ws', 'websocket']:
                outbound["transport"] = {
                    "type": "ws",
                    "path": node.get('path', '/'),
                    "headers": self._format_headers(node.get('headers', {}))
                }
            elif network in ['grpc']:
                outbound["transport"] = {
                    "type": "grpc",
                    "service_name": node.get('serviceName', node.get('grpc-service-name', ''))
                }
            elif network in ['h2', 'http']:
                outbound["transport"] = {
                    "type": "http",
                    "path": node.get('path', '/'),
                    "headers": self._format_headers(node.get('headers', {}))
                }
            # 跳过不支持的网络类型
            elif network in ['xhttp', 'httpupgrade', 'splithttp']:
                log.debug(f"跳过VLESS不支持的网络类型 {network}，使用TCP")
                
            if node.get('security') == 'tls' or node.get('tls'):
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": node.get('sni', node['server']),
                    "insecure": True
                }

        elif node['type'] == 'vmess':
            outbound["server"] = node['server']
            outbound["server_port"] = int(node['port'])  # 确保端口是整数
            outbound["uuid"] = node['uuid']
            outbound["alter_id"] = int(node.get('alterId', 0))
            outbound["security"] = node.get('security', 'auto')
            
            # 处理网络传输类型，适配sing-box支持的类型
            network = node.get('network', 'tcp')
            if network in ['ws', 'websocket']:
                outbound["transport"] = {
                    "type": "ws",
                    "path": node.get('path', '/'),
                    "headers": self._format_headers(node.get('headers', {}))
                }
            elif network in ['grpc']:
                outbound["transport"] = {
                    "type": "grpc",
                    "service_name": node.get('serviceName', node.get('grpc-service-name', ''))
                }
            elif network in ['h2', 'http']:
                outbound["transport"] = {
                    "type": "http",
                    "path": node.get('path', '/'),
                    "headers": self._format_headers(node.get('headers', {}))
                }
            # 跳过不支持的网络类型，使用默认TCP
            elif network in ['xhttp', 'httpupgrade', 'splithttp']:
                log.debug(f"跳过不支持的网络类型 {network}，使用TCP")
                # 不添加transport字段，默认使用TCP
                
            if node.get('tls'):
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": node.get('sni', node['server']),
                    "insecure": True
                }

        elif node['type'] == 'trojan':
            outbound["server"] = node['server']
            outbound["server_port"] = int(node['port'])  # 确保端口是整数
            outbound["password"] = node['password']
            outbound["tls"] = {
                "enabled": True,
                "server_name": node.get('sni', node['server']),
                "insecure": True
            }
        
        elif node['type'] == 'shadowsocks':
            outbound["server"] = node['server']
            outbound["server_port"] = int(node['port'])  # 确保端口是整数
            outbound["method"] = node['method']
            outbound["password"] = node['password']

        config["outbounds"] = [outbound]
        return config
    
    def _format_headers(self, headers) -> Dict[str, str]:
        """格式化headers为sing-box需要的格式"""
        if isinstance(headers, dict):
            return headers
        elif isinstance(headers, str):
            # 如果是字符串，尝试解析为字典，失败则设为Host头
            try:
                import json
                return json.loads(headers)
            except:
                # 如果解析失败，假设是Host头
                if headers:
                    return {"Host": headers}
                return {}
        else:
            return {}