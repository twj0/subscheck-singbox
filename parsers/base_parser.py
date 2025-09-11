# parsers/base_parser.py
import base64
import json
from typing import Optional, Dict
from urllib.parse import urlparse, parse_qs, unquote

from utils.logger import log

def parse_node_url(url: str) -> Optional[Dict]:
    """Parses a node URL (vmess, vless, trojan, ss, ssr) and returns a dictionary."""
    if not url or not isinstance(url, str):
        return None
        
    url = url.strip()
    if not url:
        return None
        
    if url.startswith('vmess://'):
        return _parse_vmess_url(url)
    elif url.startswith('vless://'):
        return _parse_vless_url(url)
    elif url.startswith('trojan://'):
        return _parse_trojan_url(url)
    elif url.startswith('ss://'):
        return _parse_shadowsocks_url(url)
    elif url.startswith('ssr://'):
        return _parse_shadowsocksr_url(url)
    elif url.startswith('hysteria://') or url.startswith('hysteria2://'):
        log.debug(f"Hysteria协议暂不支持: {url[:50]}...")
        return None
    elif url.startswith('tuic://'):
        log.debug(f"TUIC协议暂不支持: {url[:50]}...")
        return None
    else:
        log.debug(f"不支持的协议: {url[:50]}...")
        return None

def _parse_vmess_url(url: str) -> Optional[Dict]:
    """Parses a vmess:// URL."""
    try:
        decoded_part = base64.b64decode(url[8:]).decode('utf-8')
        vmess_config = json.loads(decoded_part)
        
        return {
            'name': vmess_config.get('ps', vmess_config.get('add', 'VMess')),
            'type': 'vmess',
            'server': vmess_config['add'],
            'port': int(vmess_config['port']),
            'uuid': vmess_config['id'],
            'alterId': int(vmess_config.get('aid', 0)),
            'security': vmess_config.get('scy', 'auto'),
            'network': vmess_config.get('net', 'tcp'),
            'tls': vmess_config.get('tls', '') == 'tls',
            'sni': vmess_config.get('sni', vmess_config.get('host', vmess_config['add']))
        }
    except Exception as e:
        log.warning(f"Failed to parse VMess URL: {e}")
        return None

def _parse_vless_url(url: str) -> Optional[Dict]:
    """Parses a vless:// URL."""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        
        uuid = parsed_url.username
        server = parsed_url.hostname
        port = parsed_url.port
        
        if not uuid or not server or port is None:
            log.warning(f"VLESS URL缺少必要参数: {url[:100]}...")
            return None
        
        # 处理IPv6地址中的端口解析问题
        if isinstance(port, str):
            try:
                port = int(port)
            except (ValueError, TypeError):
                log.warning(f"VLESS URL端口格式错误 '{port}': {url[:100]}...")
                return None
        
        if not isinstance(port, int) or port <= 0 or port > 65535:
            log.warning(f"VLESS URL端口无效 '{port}': {url[:100]}...")
            return None

        return {
            'name': unquote(parsed_url.fragment) if parsed_url.fragment else f"{server}:{port}",
            'type': 'vless',
            'server': server,
            'port': port,
            'uuid': uuid,
            'security': query_params.get('security', ['none'])[0] if query_params.get('security') else 'none',
            'network': query_params.get('type', ['tcp'])[0] if query_params.get('type') else 'tcp',
            'sni': query_params.get('sni', [server])[0] if query_params.get('sni') else server,
            'host': query_params.get('host', [server])[0] if query_params.get('host') else server,
            'path': query_params.get('path', ['/'])[0] if query_params.get('path') else '/'
        }
    except Exception as e:
        log.warning(f"解析VLESS URL失败: {e}")
        return None

def _parse_trojan_url(url: str) -> Optional[Dict]:
    """Parses a trojan:// URL."""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        password = parsed_url.username
        server = parsed_url.hostname
        port_str = str(parsed_url.port)
        
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            log.warning(f"Invalid port '{port_str}' in Trojan URL, skipping node: {url[:100]}...")
            return None

        return {
            'name': unquote(parsed_url.fragment) if parsed_url.fragment else server,
            'type': 'trojan',
            'server': server,
            'port': port,
            'password': password,
            'sni': query_params.get('sni', [server])[0] if query_params.get('sni') else server
        }
    except Exception as e:
        log.warning(f"Failed to parse Trojan URL: {e}")
        return None

def _parse_shadowsocks_url(url: str) -> Optional[Dict]:
    """Parses a ss:// (Shadowsocks) URL."""
    try:
        # 移除 'ss://' 前缀
        encoded_part = url[5:]
        
        # 检查是否有 fragment (节点名称)
        if '#' in encoded_part:
            encoded_part, fragment = encoded_part.split('#', 1)
            name = unquote(fragment)
        else:
            name = None
        
        # 尝试多种解析方式
        node = None
        
        # 方式1: 标准SIP002格式 - method:password@server:port (base64编码)
        try:
            decoded = base64.b64decode(encoded_part).decode('utf-8')
            node = _parse_ss_standard_format(decoded, name)
            if node:
                return node
        except Exception:
            pass
        
        # 方式2: SIP002格式 - method:password@server:port (明文)
        try:
            node = _parse_ss_standard_format(encoded_part, name)
            if node:
                return node
        except Exception:
            pass
        
        # 方式3: 新格式 - ss://base64(method:password)@server:port
        try:
            if '@' in encoded_part:
                auth_part, server_part = encoded_part.split('@', 1)
                try:
                    decoded_auth = base64.b64decode(auth_part).decode('utf-8')
                    if ':' in decoded_auth:
                        method, password = decoded_auth.split(':', 1)
                        node = _parse_ss_server_part(server_part, method, password, name)
                        if node:
                            return node
                except Exception:
                    pass
        except Exception:
            pass
        
        log.debug(f"无法解析Shadowsocks URL: {url[:50]}...")
        return None
        
    except Exception as e:
        log.debug(f"解析Shadowsocks URL时发生错误: {e}")
        return None

def _parse_ss_standard_format(content: str, name: Optional[str]) -> Optional[Dict]:
    """解析标准SS格式: method:password@server:port"""
    if '@' not in content:
        return None
        
    auth_part, server_part = content.split('@', 1)
    
    if ':' not in auth_part:
        return None
        
    method, password = auth_part.split(':', 1)
    
    return _parse_ss_server_part(server_part, method, password, name)

def _parse_ss_server_part(server_part: str, method: str, password: str, name: Optional[str]) -> Optional[Dict]:
    """解析SS的服务器部分"""
    try:
        # 处理IPv6地址的情况
        if server_part.startswith('['):
            # IPv6 格式: [::1]:8080
            bracket_end = server_part.find(']')
            if bracket_end == -1:
                return None
            server = server_part[1:bracket_end]
            port_part = server_part[bracket_end+1:]
            if not port_part.startswith(':'):
                return None
            port_str = port_part[1:]
        else:
            # IPv4 格式: 1.2.3.4:8080 或域名格式
            if ':' not in server_part:
                return None
            server, port_str = server_part.rsplit(':', 1)
        
        try:
            port = int(port_str)
            if port <= 0 or port > 65535:
                return None
        except ValueError:
            return None
        
        return {
            'name': name or f"{server}:{port}",
            'type': 'shadowsocks',
            'server': server,
            'port': port,
            'method': method,
            'password': password
        }
    except Exception:
        return None

def _parse_shadowsocksr_url(url: str) -> Optional[Dict]:
    """Parses a ssr:// (ShadowsocksR) URL."""
    try:
        # 移除 'ssr://' 前缀并解码 base64
        encoded_part = url[6:]
        decoded = base64.b64decode(encoded_part).decode('utf-8')
        
        # SSR 格式: server:port:protocol:method:obfs:password_base64/?params
        if '?' in decoded:
            main_part, params_part = decoded.split('?', 1)
            params = parse_qs(params_part)
        else:
            main_part = decoded
            params = {}
        
        parts = main_part.split(':', 5)
        if len(parts) != 6:
            log.debug(f"Invalid ShadowsocksR format: {url[:50]}...")
            return None
        
        server, port_str, protocol, method, obfs, password_b64 = parts
        
        try:
            port = int(port_str)
            password = base64.b64decode(password_b64).decode('utf-8')
        except (ValueError, Exception):
            log.debug(f"Invalid data in ShadowsocksR URL: {url[:50]}...")
            return None
        
        # 获取节点名称
        name = None
        if 'remarks' in params:
            try:
                name = base64.b64decode(params['remarks'][0]).decode('utf-8')
            except Exception:
                pass
        
        return {
            'name': name or f"{server}:{port}",
            'type': 'shadowsocksr',
            'server': server,
            'port': port,
            'protocol': protocol,
            'method': method,
            'obfs': obfs,
            'password': password
        }
        
    except Exception as e:
        log.debug(f"Failed to parse ShadowsocksR URL: {e}")
        return None