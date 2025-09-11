# core/xray_runner.py
import asyncio
import json
import tempfile
import os
from typing import Dict, Any

from utils.logger import log

class XrayRunner:
    """Manages the lifecycle of a single Xray process for testing a node."""

    def __init__(self, node_config: Dict[str, Any], port: int):
        self._config = self._generate_xray_config(node_config, port)
        self._process = None
        self._config_file_path = None

    async def __aenter__(self):
        """Starts the Xray process asynchronously."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(self._config, f)
            self._config_file_path = f.name

        self._process = await asyncio.create_subprocess_exec(
            'xray', '-config', self._config_file_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await asyncio.sleep(2)  # Wait for Xray to start up

        if self._process.returncode is not None:
            raise RuntimeError(f"Xray failed to start. Return code: {self._process.returncode}")

        log.debug(f"Xray process started with PID: {self._process.pid} on port {self._config['inbounds'][0]['port']}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stops the Xray process and cleans up the config file."""
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3)
                log.debug(f"Xray process {self._process.pid} terminated gracefully.")
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
                log.warning(f"Xray process {self._process.pid} killed forcefully.")

        if self._config_file_path and os.path.exists(self._config_file_path):
            os.remove(self._config_file_path)

    def _generate_xray_config(self, node: Dict[str, Any], socks_port: int) -> Dict[str, Any]:
        """Generates a valid Xray configuration for a given node."""
        inbound_settings = {
            "port": socks_port,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"}
        }

        outbound: Dict[str, Any] = {"protocol": node['type'], "settings": {}}
        stream_settings: Dict[str, Any] = {"network": node.get('network', 'tcp')}

        # Common TLS settings
        if node.get('tls') or (isinstance(node.get('security'), str) and node.get('security') == 'tls'):
            stream_settings["security"] = "tls"
            stream_settings["tlsSettings"] = {
                "serverName": node.get('sni', node['server']),
                "allowInsecure": True  # Often needed for self-signed certs
            }

        # Protocol-specific settings
        if node['type'] in ['vless', 'vmess']:
            user_info = {
                "id": node['uuid'],
                "security": node.get('security', 'auto') if node['type'] == 'vmess' else 'none',
            }
            if node['type'] == 'vmess':
                user_info["alterId"] = node.get('alterId', 0)
            
            outbound["settings"]["vnext"] = [{
                "address": node['server'],
                "port": node['port'],
                "users": [user_info]
            }]
        elif node['type'] == 'trojan':
            outbound["settings"]["servers"] = [{
                "address": node['server'],
                "port": node['port'],
                "password": node['password']
            }]
            # Trojan always requires TLS
            if "security" not in stream_settings:
                 stream_settings["security"] = "tls"
                 stream_settings["tlsSettings"] = {"serverName": node.get('sni', node['server'])}


        # Transport-specific settings (e.g., ws, grpc)
        network = node.get('network', 'tcp')
        if network == 'ws':
            stream_settings["wsSettings"] = {
                "path": node.get('path', '/'),
                "headers": {"Host": node.get('host', node['server'])}
            }
        elif network == 'grpc':
            stream_settings["grpcSettings"] = {
                "serviceName": node.get('serviceName', '')
            }

        outbound["streamSettings"] = stream_settings
        
        return {
            "log": {"loglevel": "error"},
            "inbounds": [inbound_settings],
            "outbounds": [outbound]
        }