# testers/node_tester.py
import asyncio
import time
import aiohttp
from typing import Dict, Optional, List, Any

from core.xray_runner import XrayRunner
from utils.logger import log

class NodeTester:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_port = 10800

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
        socks_port = self.base_port + index

        log.info(f"Testing [{index + 1: >3}] {result['name']}")

        try:
            async with XrayRunner(node, socks_port):
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

        except Exception as e:
            result['error'] = str(e)
            log.warning(f"  ✗ {result['name']} - Test failed with exception: {e}")

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
        """
        Concurrently tests download speed against multiple URLs and returns the maximum speed in Mbps.
        """
        test_urls: List[str] = self.config['test_settings']['speed_urls']
        duration: int = self.config['test_settings']['speed_test_duration']
        
        async def download_task(url: str, session: aiohttp.ClientSession) -> Optional[float]:
            timeout = aiohttp.ClientTimeout(total=duration + 5) # Add buffer
            try:
                start_time = time.monotonic()
                downloaded_bytes = 0
                
                async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                    if response.status != 200:
                        return None
                    
                    while True:
                        # Stop downloading if the duration is exceeded
                        if time.monotonic() - start_time > duration:
                            break
                        
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        
                        downloaded_bytes += len(chunk)
                
                elapsed_time = time.monotonic() - start_time
                if elapsed_time > 0 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / elapsed_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    return speed_mbps
            except (asyncio.TimeoutError, aiohttp.ClientError):
                return None
            except Exception:
                return None
            return None

        async with aiohttp.ClientSession() as session:
            tasks = [download_task(url, session) for url in test_urls]
            results = await asyncio.gather(*tasks)
        
        successful_speeds = [speed for speed in results if speed is not None and speed > 0]
        
        if not successful_speeds:
            return None
            
        # Return the maximum speed found from all test URLs
        return round(max(successful_speeds), 2)