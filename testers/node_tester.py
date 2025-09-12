# testers/node_tester.py
import asyncio
import time
import aiohttp
from typing import Dict, Optional, List, Any

from core.singbox_runner import singboxRunner
from utils.logger import log

class NodeTester:
    """Tests a single proxy node using singbox."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_port = 40000  # 使用更高的端口范围避免冲突
        self._active_processes = []
        self._used_ports = set()
        self._released_ports = {}  # Track when ports were released
        self._port_lock = asyncio.Lock()
        self._port_recycle_delay = 5.0  # 增加端口回收延迟
    
    async def cleanup(self):
        """Clean up any remaining processes."""
        for process in self._active_processes:
            try:
                if process and process.returncode is None:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=3)
            except Exception as e:
                log.debug(f"Cleanup error: {e}")
        self._active_processes.clear()
        self._used_ports.clear()
        self._released_ports.clear()

    async def _allocate_port(self, index: int) -> int:
        """Allocate a unique port for testing."""
        async with self._port_lock:
            current_time = time.monotonic()
            
            # Clean up expired released ports
            expired_ports = [port for port, release_time in self._released_ports.items() 
                           if current_time - release_time > self._port_recycle_delay]
            for port in expired_ports:
                del self._released_ports[port]
            
            # Try to find an available port starting from base_port + index
            max_attempts = 100
            for attempt in range(max_attempts):
                port = self.base_port + index + attempt
                if (port not in self._used_ports and 
                    port not in self._released_ports):
                    self._used_ports.add(port)
                    return port
            
            # If we can't find a port in the expected range, find any available port
            for port in range(self.base_port, self.base_port + 5000):
                if (port not in self._used_ports and 
                    port not in self._released_ports):
                    self._used_ports.add(port)
                    return port
            
            raise RuntimeError("No available ports for testing")

    async def _release_port(self, port: int):
        """Release a port back to the pool."""
        async with self._port_lock:
            self._used_ports.discard(port)
            self._released_ports[port] = time.monotonic()
        # Add a small delay to ensure the port is fully released by the OS
        await asyncio.sleep(0.5)

    async def test_single_node(self, node: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Complete test suite for a single node."""
        result = {
            'name': node.get('name', 'Unnamed'),
            'server': node.get('server', 'N/A'),
            'port': node.get('port', 'N/A'),
            'type': node.get('type', 'N/A'),
            'status': 'failed',
            'error': None,
            'http_latency': None,
            'download_speed': None
        }

        log.info(f"Testing [{index + 1: >3}] {result['name']}")

        try:
            socks_port = await self._allocate_port(index)
            try:
                async with singboxRunner(node, socks_port):
                    proxy_url = f"socks5://127.0.0.1:{socks_port}"

                    # 1. HTTP Latency Test
                    http_latency = await self._test_connectivity(proxy_url)
                    result['http_latency'] = http_latency

                    if http_latency is None:
                        result['error'] = "HTTP connection failed"
                        log.warning(f"  ✗ {result['name']} - HTTP connection failed")
                        return result

                    # 2. Download Speed Test
                    download_speed = await self._test_download_speed(proxy_url)
                    result['download_speed'] = download_speed

                    if download_speed is None:
                        result['error'] = "Speed test failed"
                        log.warning(f"  ✗ {result['name']} - Speed test failed")
                        return result

                    result['status'] = 'success'
                    log.info(f"  ✓ {result['name']} - Latency: {http_latency:.0f}ms | Speed: {download_speed:.2f}Mbps")
            finally:
                await self._release_port(socks_port)

        except Exception as e:
            result['error'] = str(e)
            log.warning(f"  ✗ {result['name']} - Test failed with exception: {e}")
            if 'socks_port' in locals():
                await self._release_port(socks_port)

        return result

    async def _test_connectivity(self, proxy_url: str) -> Optional[float]:
        """Tests proxy connectivity and returns average latency in ms."""
        latencies = []
        test_urls: List[str] = self.config['test_settings']['latency_urls']
        timeout_seconds: int = self.config['test_settings']['timeout']
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)

        async with aiohttp.ClientSession() as session:
            for url in test_urls:
                try:
                    start_time = time.monotonic()
                    async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                        if response.status in [200, 204]:
                            latency = (time.monotonic() - start_time) * 1000
                            latencies.append(latency)
                except Exception:
                    continue
        
        return sum(latencies) / len(latencies) if latencies else None

    async def _test_download_speed(self, proxy_url: str) -> Optional[float]:
        """Tests download speed and returns speed in Mbps."""
        test_url: str = self.config['test_settings']['speed_url']
        duration: int = self.config['test_settings']['speed_test_duration']
        timeout = aiohttp.ClientTimeout(total=duration + 5) # Add buffer

        try:
            async with aiohttp.ClientSession() as session:
                start_time = time.monotonic()
                downloaded_bytes = 0
                
                async with session.get(test_url, proxy=proxy_url, timeout=timeout) as response:
                    if response.status != 200:
                        return None
                    
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        
                        downloaded_bytes += len(chunk)
                        elapsed_time = time.monotonic() - start_time
                        
                        if elapsed_time >= duration:
                            break
                
                final_elapsed_time = time.monotonic() - start_time
                if final_elapsed_time > 0 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / final_elapsed_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    return round(speed_mbps, 2)

        except Exception:
            return None
        return None