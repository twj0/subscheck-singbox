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

        # 获取sing-box的绝对路径，支持跨平台环境
        current_dir = Path(__file__).parent.parent
        
        # 根据操作系统类型配置sing-box路径
        import platform
        system = platform.system().lower()
        
        if system == "windows":
            # Windows环境路径
            possible_paths = [
                # 优先查找根目录中的sing-box.exe（Windows）
                current_dir / 'sing-box.exe',
                # Windows特定路径
                current_dir / 'sing-box-windows' / 'sing-box.exe',
                current_dir / 'bin' / 'sing-box.exe',
                Path('sing-box.exe'),  # 当前工作目录
                # 系统PATH中查找
                'sing-box.exe'  # 系统安装的版本
            ]
        else:
            # Linux/Unix环境路径
            possible_paths = [
                # 项目根目录
                current_dir / 'sing-box',
                current_dir / 'sing-box-linux' / 'sing-box',
                current_dir / 'bin' / 'sing-box',
                Path('./sing-box'),  # 当前目录
                # 系统标准路径
                Path('/usr/local/bin/sing-box'),
                Path('/usr/bin/sing-box'),
                Path('/opt/sing-box/sing-box'),
                # 用户本地路径
                Path.home() / '.local/bin/sing-box',
                # 系统PATH中查找
                'sing-box'
            ]
        
        singbox_path = None
        
        # 先尝试使用Path对象查找文件
        for path in possible_paths:
            if isinstance(path, str):
                # 在PATH中查找
                import shutil
                found_path = shutil.which(path)
                if found_path:
                    singbox_path = Path(found_path)
                    log.debug(f"在PATH中找到sing-box可执行文件: {singbox_path}")
                    break
            else:
                # 查找文件路径
                if path.exists():
                    singbox_path = path
                    log.debug(f"找到sing-box可执行文件: {singbox_path}")
                    break
        
        if not singbox_path:
            available_paths = [str(p) for p in possible_paths]
            raise RuntimeError(f"sing-box可执行文件未找到。查找过的路径: {available_paths}")
        
        # 强制添加执行权限 (解决 permission denied 问题)
        if os.name != 'nt':
            try:
                os.chmod(singbox_path, 0o755)
                log.debug(f"已为 {singbox_path} 添加执行权限")
            except Exception as e:
                log.warning(f"添加执行权限失败: {e}")

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
        await asyncio.sleep(3)  # 適度的启动等待时间

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

        port = self._config.get('inbounds', [{}])[0].get('listen_port', 'unknown')
        log.debug(f"sing-box进程启动成功，PID: {self._process.pid}，端口: {port}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stops the singbox process and cleans up the config file."""
        port = self._config.get('inbounds', [{}])[0].get('listen_port', 'unknown')
        
        if hasattr(self, '_process') and self._process and self._process.returncode is None:
            try:
                log.debug(f"開始終止 sing-box 進程 PID:{self._process.pid}, 端口:{port}")
                
                # 首先嘗試優雅終止
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
                    log.debug(f"sing-box進程 {self._process.pid} 正常終止")
                except asyncio.TimeoutError:
                    log.warning(f"進程 {self._process.pid} 未能正常終止，使用強制終止")
                    self._process.kill()
                    await self._process.wait()
                    log.debug(f"sing-box進程 {self._process.pid} 強制終止完成")
                    
            except Exception as e:
                log.debug(f"終止sing-box進程時出錯: {e}")
            finally:
                # 清理stdout和stderr管道
                try:
                    if hasattr(self._process, 'stdout') and self._process.stdout:
                        self._process.stdout.close()
                    if hasattr(self._process, 'stderr') and self._process.stderr:
                        self._process.stderr.close()
                except Exception:
                    pass
                
                # 在Windows下增加更長的等待時間確保端口完全釋放
                if os.name == 'nt':
                    log.debug(f"Windows環境下等待端口 {port} 釋放...")
                    await asyncio.sleep(3.0)  # 增加到3秒
                    
                    # 可選：檢查端口是否真正釋放（僅用於調試）
                    try:
                        import socket
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.bind(('127.0.0.1', port))
                            log.debug(f"端口 {port} 已成功釋放")
                    except OSError:
                        log.warning(f"端口 {port} 可能仍被佔用，額外等待...")
                        await asyncio.sleep(2.0)  # 額外等待
                else:
                    await asyncio.sleep(1.5)

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
        
        # 确保基础字段是字符串或数字而不是列表
        node_type = node['type']
        if isinstance(node_type, list):
            node_type = node_type[0] if node_type else 'unknown'
            
        node_server = node['server']
        if isinstance(node_server, list):
            node_server = node_server[0] if node_server else 'unknown'
            
        node_port = node['port']
        if isinstance(node_port, list):
            node_port = node_port[0] if node_port else 0
            
        outbound: Dict[str, Any] = {"type": node_type, "tag": "proxy"}

        if node_type == 'vless':
            outbound["server"] = node_server
            outbound["server_port"] = int(node_port)  # 确保端口是整数
            uuid = node['uuid']
            if isinstance(uuid, list):
                uuid = uuid[0] if uuid else ''
            outbound["uuid"] = uuid
            
            # 处理网络传输类型
            network = node.get('network', 'tcp')
            if isinstance(network, list):
                network = network[0] if network else 'tcp'
                
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
                    
                # 处理安全层设置
                security = node.get('security', 'none')
                if isinstance(security, list):
                    security = security[0] if security else 'none'
                
                # 处理REALITY等新安全协议
                if security == 'reality':
                    sni = node.get('sni', node_server)
                    if isinstance(sni, list):
                        sni = sni[0] if sni else node_server
                    
                    pbk = node.get('pbk', '')
                    if isinstance(pbk, list):
                        pbk = pbk[0] if pbk else ''
                    
                    sid = node.get('sid', '')
                    if isinstance(sid, list):
                        sid = sid[0] if sid else ''
                    
                    fp = node.get('fp', 'chrome')
                    if isinstance(fp, list):
                        fp = fp[0] if fp else 'chrome'
                    
                    outbound["tls"] = {
                        "enabled": True,
                        "server_name": sni,
                        "utls": {
                            "enabled": True,
                            "fingerprint": fp
                        },
                        "reality": {
                            "enabled": True,
                            "public_key": pbk,
                            "short_id": sid
                        },
                        "insecure": False  # REALITY不需要insecure
                    }
                    
                    # 添加flow参数（如果存在）
                    flow = node.get('flow', '')
                    if isinstance(flow, list):
                        flow = flow[0] if flow else ''
                    if flow:
                        outbound["flow"] = flow
                        
                elif security == 'tls' or node.get('tls'):
                    sni = node.get('sni', node_server)
                    # 确保server_name是字符串而不是数组
                    if isinstance(sni, list):
                        sni = sni[0] if sni else node_server
                    outbound["tls"] = {
                        "enabled": True,
                        "server_name": sni,
                        "insecure": True
                    }

        elif node_type == 'vmess':
            outbound["server"] = node_server
            outbound["server_port"] = int(node_port)  # 确保端口是整数
            uuid = node['uuid']
            if isinstance(uuid, list):
                uuid = uuid[0] if uuid else ''
            outbound["uuid"] = uuid
            
            alter_id = node.get('alterId', 0)
            if isinstance(alter_id, list):
                alter_id = alter_id[0] if alter_id else 0
            outbound["alter_id"] = int(alter_id)
            
            security = node.get('security', 'auto')
            if isinstance(security, list):
                security = security[0] if security else 'auto'
            outbound["security"] = security
            
            # 处理网络传输类型，适配sing-box支持的类型
            network = node.get('network', 'tcp')
            if isinstance(network, list):
                network = network[0] if network else 'tcp'
                
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
                sni = node.get('sni', node_server)
                # 确保server_name是字符串而不是数组
                if isinstance(sni, list):
                    sni = sni[0] if sni else node_server
                outbound["tls"] = {
                    "enabled": True,
                    "server_name": sni,
                    "insecure": True
                }

        elif node_type == 'trojan':
            outbound["server"] = node_server
            outbound["server_port"] = int(node_port)  # 确保端口是整数
            password = node['password']
            if isinstance(password, list):
                password = password[0] if password else ''
            outbound["password"] = password
            
            sni = node.get('sni', node_server)
            # 确保server_name是字符串而不是数组
            if isinstance(sni, list):
                sni = sni[0] if sni else node_server
            outbound["tls"] = {
                "enabled": True,
                "server_name": sni,
                "insecure": True
            }
        
        elif node_type == 'shadowsocks':
            outbound["server"] = node_server
            outbound["server_port"] = int(node_port)  # 确保端口是整数
            method = node['method']
            if isinstance(method, list):
                method = method[0] if method else ''
            outbound["method"] = method
            
            password = node['password']
            if isinstance(password, list):
                password = password[0] if password else ''
            outbound["password"] = password

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