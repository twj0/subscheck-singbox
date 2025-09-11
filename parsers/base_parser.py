# parsers/base_parser.py
import base64
import json
from typing import Optional, Dict
from urllib.parse import urlparse, parse_qs, unquote

from utils.logger import log

def parse_node_url(url: str) -> Optional[Dict]:
    """Parses a node URL (vmess, vless, trojan) and returns a dictionary."""
    if url.startswith('vmess://'):
        return _parse_vmess_url(url)
    elif url.startswith('vless://'):
        return _parse_vless_url(url)
    elif url.startswith('trojan://'):
        return _parse_trojan_url(url)
    else:
        log.debug(f"Unsupported protocol for URL: {url[:30]}...")
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
        
        return {
            'name': unquote(parsed_url.fragment) if parsed_url.fragment else server,
            'type': 'vless',
            'server': server,
            'port': int(port),
            'uuid': uuid,
            'security': query_params.get('security', ['none']),
            'network': query_params.get('type', ['tcp']),
            'sni': query_params.get('sni', [server])
        }
    except Exception as e:
        log.warning(f"Failed to parse VLESS URL: {e}")
        return None

def _parse_trojan_url(url: str) -> Optional[Dict]:
    """Parses a trojan:// URL."""
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        password = parsed_url.username
        server = parsed_url.hostname
        port = parsed_url.port

        return {
            'name': unquote(parsed_url.fragment) if parsed_url.fragment else server,
            'type': 'trojan',
            'server': server,
            'port': int(port),
            'password': password,
            'sni': query_params.get('sni', [server])
        }
    except Exception as e:
        log.warning(f"Failed to parse Trojan URL: {e}")
        return None