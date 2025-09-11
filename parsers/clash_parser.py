# parsers/clash_parser.py
from typing import List, Dict, Optional
from utils.logger import log

def parse_clash_proxies(proxies: List[Dict]) -> List[Dict]:
    """Parses a list of proxy dictionaries from a Clash config."""
    nodes = []
    for proxy in proxies:
        node = None
        proxy_type = proxy.get('type')
        
        if proxy_type == 'vmess':
            node = _parse_vmess(proxy)
        elif proxy_type == 'vless':
            node = _parse_vless(proxy)
        elif proxy_type == 'trojan':
            node = _parse_trojan(proxy)
        # Can be extended to support 'ss' (Shadowsocks) as well
        
        if node:
            nodes.append(node)
    return nodes

def _parse_vmess(p: Dict) -> Optional[Dict]:
    try:
        return {
            'name': p.get('name', 'VMess'), 'type': 'vmess',
            'server': p['server'], 'port': int(p['port']), 'uuid': p['uuid'],
            'alterId': int(p.get('alterId', p.get('aid', 0))),
            'security': p.get('cipher', 'auto'), 'network': p.get('network', 'tcp'),
            'tls': p.get('tls', False),
            'sni': p.get('servername', p['server'])
        }
    except KeyError as e:
        log.debug(f"Skipping Clash VMess node due to missing key: {e}")
        return None

def _parse_vless(p: Dict) -> Optional[Dict]:
    try:
        return {
            'name': p.get('name', 'VLESS'), 'type': 'vless',
            'server': p['server'], 'port': int(p['port']), 'uuid': p['uuid'],
            'security': 'tls' if p.get('tls') else 'none',
            'network': p.get('network', 'tcp'),
            'sni': p.get('servername', p['server'])
        }
    except KeyError as e:
        log.debug(f"Skipping Clash VLESS node due to missing key: {e}")
        return None

def _parse_trojan(p: Dict) -> Optional[Dict]:
    try:
        return {
            'name': p.get('name', 'Trojan'), 'type': 'trojan',
            'server': p['server'], 'port': int(p['port']),
            'password': p['password'],
            'sni': p.get('sni', p['server'])
        }
    except KeyError as e:
        log.debug(f"Skipping Clash Trojan node due to missing key: {e}")
        return None