# testers/node_tester.py
import asyncio
import time
import aiohttp
from typing import Dict, Optional, List, Any

from core.singbox_runner import SingBoxRunner
from utils.logger import log

class NodeTester:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_port = 10800
        self.singbox_runner = SingBoxRunner()
        self.max_retries = 2  # 最大重试次数
        log.info("🎵 使用Sing-box作为代理核心")

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
        
        # 使用递增的端口号避免冲突
        socks_port = self.base_port + index
        
        log.info(f"Testing [{index + 1: >3}] {result['name']}")
        
        # 多次重试机制
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                log.debug(f"  第 {attempt + 1} 次重试: {result['name']}")
                await asyncio.sleep(1.0)  # 重试前等待
            
            test_result = await self._test_single_attempt(node, socks_port, result.copy())
            if test_result['status'] == 'success':
                return test_result
            
            result = test_result  # 更新结果
            
            # 如果是配置错误，不重试
            if 'configuration error' in str(result.get('error', '')).lower():
                break
        
        log.warning(f"  ✗ {result['name']} - 所有重试均失败: {result.get('error', 'Unknown error')}")
        return result
    
    async def _test_single_attempt(self, node: Dict[str, Any], socks_port: int, result: Dict[str, Any]) -> Dict[str, Any]:
        """单次测试尝试"""
        process = None
        try:
            # 使用Sing-box
            success, process, error_msg = await self.singbox_runner.start_singbox(node, socks_port)
            if not success:
                result['error'] = f"Sing-box启动失败: {error_msg}"
                return result
            
            # 获取实际使用的端口
            actual_port = socks_port
            if socks_port in self.singbox_runner.processes:
                _, _, actual_port = self.singbox_runner.processes[socks_port]
            
            proxy_url = f"socks5://127.0.0.1:{actual_port}"
            
            # HTTP延迟测试
            http_latency = await self._test_connectivity(proxy_url)
            result['http_latency'] = http_latency

            if http_latency is None:
                result['error'] = "HTTP连接失败"
                return result

            # 下载速度测试
            download_speed = await self._test_download_speed(proxy_url)
            result['download_speed'] = download_speed

            if download_speed is None:
                result['error'] = "速度测试失败"
                return result

            result['status'] = 'success'
            result['error'] = None
            log.info(f"  ✓ {result['name']} - Latency: {http_latency:.0f}ms | Speed: {download_speed:.2f}Mbps")
            
            return result
        
        except Exception as e:
            result['error'] = f"测试异常: {str(e)}"
            return result
        
        finally:
            # 确保清理Sing-box进程
            if socks_port in self.singbox_runner.processes:
                try:
                    await self.singbox_runner.stop_singbox(socks_port)
                except Exception as e:
                    log.warning(f"清理Sing-box进程时出错: {e}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            await self.singbox_runner.cleanup_all()
            log.debug("所有Sing-box资源已清理")
        except Exception as e:
            log.warning(f"清理资源时出错: {e}")

    async def _test_connectivity(self, proxy_url: str) -> Optional[float]:
        """Tests proxy connectivity and returns average latency in ms."""
        latencies = []
        test_urls: List[str] = self.config['test_settings']['latency_urls']
        timeout_seconds: int = self.config['test_settings']['timeout']
        timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=timeout_seconds//2)

        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # 串行测试以避免过多并发连接
                for url in test_urls:
                    try:
                        start_time = time.monotonic()
                        async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                            if response.status in [200, 204]:
                                latency = (time.monotonic() - start_time) * 1000
                                latencies.append(latency)
                                # 只要有一个成功就可以提前返回
                                if len(latencies) >= 1:
                                    break
                    except Exception as e:
                        log.debug(f"连接测试失败 {url}: {e}")
                        continue
        except Exception as e:
            log.debug(f"创建连接时出错: {e}")
            return None
        finally:
            try:
                await connector.close()
            except:
                pass
        
        return sum(latencies) / len(latencies) if latencies else None

    async def _test_download_speed(self, proxy_url: str) -> Optional[float]:
        """
        Tests download speed against multiple URLs and returns the maximum speed in Mbps.
        """
        test_urls: List[str] = self.config['test_settings']['speed_urls']
        duration: int = self.config['test_settings']['speed_test_duration']
        
        async def download_task(url: str, session: aiohttp.ClientSession) -> Optional[float]:
            timeout = aiohttp.ClientTimeout(total=duration + 10)  # 增加缓冲
            try:
                start_time = time.monotonic()
                downloaded_bytes = 0
                
                async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                    if response.status != 200:
                        return None
                    
                    while True:
                        # 检查时间是否超过
                        elapsed = time.monotonic() - start_time
                        if elapsed > duration:
                            break
                        
                        try:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            downloaded_bytes += len(chunk)
                        except Exception:
                            break
                
                elapsed_time = time.monotonic() - start_time
                if elapsed_time > 0.1 and downloaded_bytes > 1024:  # 至少下载1KB且耗时0.1秒
                    speed_bps = (downloaded_bytes * 8) / elapsed_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    return speed_mbps
            except Exception as e:
                log.debug(f"下载测试失败 {url}: {e}")
                return None
            return None

        connector = aiohttp.TCPConnector(
            limit=5,
            limit_per_host=2,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # 串行测试以降低资源消耗
                speeds = []
                for url in test_urls:
                    speed = await download_task(url, session)
                    if speed is not None and speed > 0:
                        speeds.append(speed)
                        # 只要有一个成功的结果就可以返回
                        break
        except Exception as e:
            log.debug(f"创建下载连接时出错: {e}")
            return None
        finally:
            try:
                await connector.close()
            except:
                pass
        
        if not speeds:
            return None
            
        return round(max(speeds), 2)