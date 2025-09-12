# parsers/base_parser.py
import base64
import json
import urllib.parse
from typing import Optional, Dict, Any

from utils.logger import log

def parse_node_url(url: str) -> Optional[Dict[str, Any]]:
    """Parses a node URL and dispatches to the correct parser."""
    try:
        # 预处理URL，移除异常字符
        url = url.strip()
        if not url:
            return None
            
        if url.startswith('vless://'):
            return _parse_vless(url)
        elif url.startswith('vmess://'):
            return _parse_vmess(url)
        elif url.startswith('trojan://'):
            return _parse_trojan(url)
        elif url.startswith('ss://'):
            return _parse_shadowsocks(url)
        elif url.startswith('ssr://'):
            log.debug(f"SSR协议不支持，跳过: {url[:30]}...")
            return None
        elif url.startswith('hysteria2://') or url.startswith('hysteria://'):
            log.debug(f"Hysteria协议不支持，跳过: {url[:30]}...")
            return None
        else:
            log.debug(f"Unsupported protocol: {url[:30]}...")
            return None
    except Exception as e:
        log.debug(f"Failed to parse node URL: {url[:50]}..., Error: {e}")
        return None

def _parse_vless(url: str) -> Dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed_url.query)
    
    # 确保端口是有效的整数
    port = parsed_url.port
    if port is None:
        log.debug(f"VLESS URL missing port: {url[:50]}...")
        return None
    
    # 获取网络类型和相关参数
    network = params.get('type', ['tcp'])[0]
    
    node_data = {
        'name': urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{parsed_url.hostname}:{port}",
        'type': 'vless',
        'server': parsed_url.hostname,
        'port': int(port),
        'uuid': parsed_url.username,
        'security': params.get('security', ['none'])[0],
        'sni': params.get('sni', [parsed_url.hostname])[0],
        'network': network
    }
    
    # 添加网络类型相关参数
    if network in ['ws', 'websocket']:
        node_data['path'] = params.get('path', ['/'])[0]
        node_data['headers'] = params.get('host', [''])[0]
    elif network == 'grpc':
        node_data['serviceName'] = params.get('serviceName', params.get('grpc-service-name', ['']))[0]
    elif network in ['h2', 'http']:
        node_data['path'] = params.get('path', ['/'])[0]
        node_data['headers'] = params.get('host', [''])[0]
    
    return node_data

def _parse_vmess(url: str) -> Optional[Dict[str, Any]]:
    try:
        encoded_part = url[8:]
        decoded_bytes = base64.b64decode(encoded_part)
        config = json.loads(decoded_bytes.decode('utf-8'))
        
        # 确保端口是有效的整数
        port = config.get('port')
        if port is None:
            log.debug(f"VMess config missing port: {config}")
            return None
        
        try:
            port = int(port)
        except (ValueError, TypeError):
            log.debug(f"VMess config invalid port '{port}': {config}")
            return None
        
        # 扩展网络类型支持
        network = config.get('net', 'tcp')
        node_data = {
            'name': config.get('ps', f"{config.get('add', 'N/A')}:{port}"),
            'type': 'vmess',
            'server': config['add'],
            'port': port,
            'uuid': config['id'],
            'alterId': int(config.get('aid', 0)),
            'security': config.get('scy', 'auto'),
            'network': network,
            'tls': config.get('tls', '') == 'tls',
            'sni': config.get('sni', config['add'])
        }
        
        # 添加网络类型相关参数
        if network in ['ws', 'websocket']:
            node_data['path'] = config.get('path', '/')
            node_data['headers'] = config.get('host', '')
        elif network == 'grpc':
            node_data['serviceName'] = config.get('serviceName', config.get('grpc-service-name', ''))
        elif network in ['h2', 'http']:
            node_data['path'] = config.get('path', '/')
            node_data['headers'] = config.get('host', '')
        
        return node_data
        
    except Exception as e:
        log.debug(f"Failed to parse VMess URL: {e}")
        return None

def _parse_trojan(url: str) -> Dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    
    # 确保端口是有效的整数
    port = parsed_url.port
    if port is None:
        log.debug(f"Trojan URL missing port: {url[:50]}...")
        return None
    
    return {
        'name': urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{parsed_url.hostname}:{port}",
        'type': 'trojan',
        'server': parsed_url.hostname,
        'port': int(port),
        'password': parsed_url.username,
        'sni': urllib.parse.parse_qs(parsed_url.query).get('sni', [parsed_url.hostname])[0]
    }

def _parse_shadowsocks(url: str) -> Dict[str, Any]:
    """Parse Shadowsocks URL format."""
    try:
        parsed_url = urllib.parse.urlparse(url)
        
        # 确保端口是有效的整数
        port = parsed_url.port
        if port is None:
            log.debug(f"Shadowsocks URL missing port: {url[:50]}...")
            return None
        
        # Handle both formats: ss://method:password@host:port and ss://base64@host:port
        if parsed_url.username and parsed_url.password:
            # Format: ss://method:password@host:port
            method = parsed_url.username
            password = parsed_url.password
        else:
            # Format: ss://base64@host:port
            encoded_part = parsed_url.username or url[5:]  # Remove 'ss://'
            if '@' in encoded_part:
                encoded_part = encoded_part.split('@')[0]
            
            # Add padding if needed
            missing_padding = len(encoded_part) % 4
            if missing_padding:
                encoded_part += '=' * (4 - missing_padding)
            
            decoded = base64.b64decode(encoded_part, validate=False).decode('utf-8')
            if ':' in decoded:
                method, password = decoded.split(':', 1)
            else:
                return None
        
        return {
            'name': urllib.parse.unquote(parsed_url.fragment) if parsed_url.fragment else f"{parsed_url.hostname}:{port}",
            'type': 'shadowsocks',
            'server': parsed_url.hostname,
            'port': int(port),
            'method': method,
            'password': password
        }
    except Exception as e:
        log.debug(f"Failed to parse Shadowsocks URL: {e}")
        return None