# testers/node_tester.py
import asyncio
import time
import os
import aiohttp
from typing import Dict, Optional, List, Any

from core.singbox_runner import singboxRunner
from testers.direct_proxy_tester import DirectProxyTester
from utils.logger import log
from utils.ip_checker import IPChecker

class NodeTester:
    """Tests a single proxy node using singbox."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_port = 41000  # 使用更高的端口范围避免冲突
        self._active_processes = []
        self._used_ports = set()
        self._released_ports = {}  # Track when ports were released
        self._port_lock = asyncio.Lock()
        self._port_recycle_delay = 8.0  # 增加端口回收延迟到8秒
        
        # 初始化直接代理测试器
        self.direct_tester = DirectProxyTester(timeout=config.get('test_settings', {}).get('timeout', 15))
        self.ip_checker = IPChecker(config)
    
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
        
        # Windows下需要更長的等待時間確保端口完全釋放
        if os.name == 'nt':
            await asyncio.sleep(2.0)  # Windows下延長等待時間
        else:
            await asyncio.sleep(1.0)
            
        log.debug(f"端口 {port} 釋放完成")

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
            'download_speed': None,
            'ip_purity': None
        }

        log.info(f"Testing [{index + 1: >3}] {result['name']}")

        socks_port = None
        try:
            socks_port = await self._allocate_port(index)
            log.debug(f" {result['name']} 分配端口 {socks_port}")
            try:
                # 增加更长的启动等待时间
                async with singboxRunner(node, socks_port) as runner:
                    # 额外等待确保 sing-box 完全启动
                    await asyncio.sleep(2)
                    
                    proxy_url = f"socks5://127.0.0.1:{socks_port}"
                    log.debug(f"Using proxy: {proxy_url}")

                    # 1. 优先进行直接协议测试（不依赖HTTP）
                    direct_latency = await self.direct_tester.test_node_direct_connectivity(node)
                    
                    # 2. 如果直接测试成功，再进行通过sing-box的SOCKS5测试
                    socks5_latency = None
                    if direct_latency is not None:
                        log.debug(f"直接协议测试成功: {direct_latency:.0f}ms")
                        socks5_latency = await self.direct_tester.test_through_singbox_socks5(
                            proxy_url, "8.8.8.8", 53
                        )
                        if socks5_latency is not None:
                            log.debug(f"SOCKS5代理测试成功: {socks5_latency:.0f}ms")
                    
                    # 3. 如果上述测试都失败，尝试传统的HTTP测试
                    http_latency = None
                    if direct_latency is None and socks5_latency is None:
                        log.debug("直接协议和SOCKS5测试失败，尝试HTTP测试")
                        http_latency = await self._test_connectivity(proxy_url)
                    
                    # 选择最佳的延迟结果
                    best_latency = None
                    test_method = "failed"
                    
                    if direct_latency is not None:
                        best_latency = direct_latency
                        test_method = "direct"
                    elif socks5_latency is not None:
                        best_latency = socks5_latency  
                        test_method = "socks5"
                    elif http_latency is not None:
                        best_latency = http_latency
                        test_method = "http"
                    
                    result['http_latency'] = best_latency
                    log.debug(f"最终测试结果: {test_method} - {best_latency:.0f}ms" if best_latency else f"所有测试方法失败")

                    if best_latency is None:
                        result['error'] = "All connectivity tests failed"
                        log.warning(f"  ✗ {result['name']} - 所有连接测试失败")
                        return result

                    # 4. 只有在连接测试成功时才进行速度测试
                    download_speed = None
                    if best_latency is not None:
                        # 5. 进行IP纯净度测试
                        ip_purity = await self.ip_checker.check_ip_purity(proxy_url)
                        result['ip_purity'] = ip_purity
                        if ip_purity:
                            log.info(f"  - IP类型: {ip_purity}")

                        log.debug(f"开始速度测试...使用代理: {proxy_url}")
                        
                        # 确保sing-box已经完全启动并可用
                        await asyncio.sleep(1)
                        
                        # 先测试SOCKS5代理是否正常工作
                        socks_test = await self._test_socks5_proxy(proxy_url)
                        if socks_test:
                            log.debug("✅ SOCKS5代理可用，继续速度测试")
                            # 测试代理是否能转发HTTP流量
                            http_test = await self._test_proxy_http_forwarding(proxy_url)
                            if http_test:
                                log.debug("✅ HTTP转发测试成功，开始下载测试")
                                download_speed = await self._test_download_speed(proxy_url)
                            else:
                                log.debug("❌ HTTP转发测试失败，可能是协议配置问题")
                        else:
                            log.debug("❌ SOCKS5代理不可用，跳过速度测试")
                            
                        result['download_speed'] = download_speed

                        if download_speed is None:
                            log.debug("速度测试失败，但连接测试成功")
                            # 速度测试失败不影响整体结果，只要连接测试成功即可
                            result['status'] = 'success'
                            result['error'] = "Speed test failed but connectivity OK"
                            log.info(f"  ✓ {result['name']} - 延迟: {best_latency:.0f}ms ({test_method}) | 速度: 测试失败")
                        else:
                            result['status'] = 'success'
                            # 显示更高精度的速度值
                            log.info(f"  ✓ {result['name']} - 延迟: {best_latency:.0f}ms ({test_method}) | 速度: {download_speed:.4f}Mbps")
                    else:
                        result['download_speed'] = None
            finally:
                if socks_port is not None:
                    log.debug(f"釋放端口 {socks_port} for 節點 {result['name']}")
                    await self._release_port(socks_port)

        except Exception as e:
            result['error'] = str(e)
            log.warning(f"  ✗ {result['name']} - Test failed with exception: {e}")
            log.debug(f"Exception details: {type(e).__name__}: {e}")
        finally:
            # 確保端口一定會被釋放
            if socks_port is not None:
                try:
                    await self._release_port(socks_port)
                    log.debug(f"最終釋放端口 {socks_port} 完成")
                except Exception as release_error:
                    log.debug(f"端口釋放失敗: {release_error}")

        return result

    async def _test_connectivity(self, proxy_url: str) -> Optional[float]:
        """Tests proxy connectivity and returns average latency in ms."""
        latencies = []
        test_urls: List[str] = self.config['test_settings']['latency_urls']
        timeout_seconds: int = self.config['test_settings']['timeout']
        
        # 使用更长的连接超时和更短的单次请求超时
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=3,
            enable_cleanup_closed=True,
            force_close=True  # 强制关闭连接，不使用keep-alive
        )
        timeout = aiohttp.ClientTimeout(
            total=timeout_seconds,
            connect=timeout_seconds // 2,  # 连接超时
            sock_read=timeout_seconds // 2  # 读取超时
        )

        try:
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,  # 不使用系统代理
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as session:
                for url in test_urls:
                    try:
                        log.debug(f"Testing connectivity to {url} via {proxy_url}")
                        start_time = time.monotonic()
                        
                        async with session.get(
                            url, 
                            proxy=proxy_url, 
                            timeout=timeout,
                            allow_redirects=False,  # 不允许重定向以加快测试
                            ssl=False  # 对于HTTP测试URL禁用SSL验证
                        ) as response:
                            elapsed = (time.monotonic() - start_time) * 1000
                            log.debug(f"Response: {response.status} in {elapsed:.0f}ms")
                            
                            if response.status in [200, 204, 301, 302]:
                                latencies.append(elapsed)
                            elif response.status >= 400:
                                log.debug(f"HTTP error {response.status} for {url}")
                                
                    except asyncio.TimeoutError:
                        log.debug(f"Timeout testing {url}")
                        continue
                    except Exception as e:
                        log.debug(f"Error testing {url}: {type(e).__name__}: {e}")
                        continue
        except Exception as e:
            log.debug(f"Session creation error: {type(e).__name__}: {e}")
            return None

    async def _test_stability(self, proxy_url: str, duration: int) -> Optional[float]:
        """
        测试连接的稳定性，通过分析速度波动来计算稳定性分数
        分数越高表示越稳定
        """
        try:
            import statistics
            
            test_url: str = self.config['test_settings']['speed_url']
            timeout_seconds: int = self.config['test_settings']['timeout'] + 15
            
            # 使用较短的超时时间以快速检测波动
            timeout = aiohttp.ClientTimeout(
                total=timeout_seconds,
                connect=timeout_seconds // 3,
                sock_read=timeout_seconds // 3
            )
            
            connector = aiohttp.TCPConnector(
                limit=3,
                limit_per_host=1,
                enable_cleanup_closed=True,
                force_close=True
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as session:
                start_time = time.monotonic()
                downloaded_bytes = 0
                speed_samples = []  # 收集速度样本
                
                async with session.get(test_url, proxy=proxy_url, timeout=timeout) as response:
                    if response.status != 200:
                        return None
                    
                    last_sample_time = start_time
                    last_downloaded_bytes = 0
                    
                    while True:
                        try:
                            chunk = await response.content.read(4096)
                            if not chunk:
                                break
                            
                            downloaded_bytes += len(chunk)
                            current_time = time.monotonic()
                            elapsed_time = current_time - start_time
                            
                            # 每0.5秒采样一次速度
                            if current_time - last_sample_time >= 0.5:
                                sample_duration = current_time - last_sample_time
                                sample_bytes = downloaded_bytes - last_downloaded_bytes
                                
                                if sample_duration > 0 and sample_bytes > 0:
                                    sample_speed_bps = (sample_bytes * 8) / sample_duration
                                    sample_speed_mbps = sample_speed_bps / (1024 * 1024)
                                    speed_samples.append(sample_speed_mbps)
                                
                                last_sample_time = current_time
                                last_downloaded_bytes = downloaded_bytes
                            
                            if elapsed_time >= (duration // 2):  # 稳定性测试时间减半以提高效率
                                break
                                
                        except Exception:
                            break
                
                if len(speed_samples) >= 2:
                    # 计算速度的标准差，标准差越小越稳定
                    mean_speed = statistics.mean(speed_samples)
                    if mean_speed > 0:
                        std_dev = statistics.stdev(speed_samples)
                        # 稳定性分数 = 平均速度 / (标准差 + 1) ，加1避免除零
                        # 这样分数越高表示越稳定且速度快
                        stability_score = mean_speed / (std_dev + 1)
                        return stability_score
                
                return None
                
        except Exception as e:
            log.debug(f"稳定性测试异常: {type(e).__name__}: {e}")
            return None
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            log.debug(f"Average latency: {avg_latency:.0f}ms from {len(latencies)} successful tests")
            return avg_latency
        else:
            log.debug("No successful connectivity tests")
            return None

    async def _test_download_speed(self, proxy_url: str) -> Optional[float]:
        """Tests download speed using native protocol through sing-box."""
        duration: int = self.config['test_settings']['speed_test_duration']
        
        log.debug("開始原生協議速度測試")
        
        # 獲取重複測試次數
        repeats: int = self.config['test_settings'].get('speed_test_repeats', 1)
        stability_test_enabled: bool = self.config['test_settings'].get('stability_test_enabled', False)
        
        # 獲取備用測試URL列表
        speed_urls = self.config['test_settings'].get('speed_urls', [])
        if not speed_urls:
            speed_urls = [self.config['test_settings']['speed_url']]
        
        speeds = []
        stability_scores = []
        
        # 尝试多个URL直到有一个成功
        for test_url in speed_urls:
            log.debug(f"嘗試測試URL: {test_url}")
            original_speed_url = self.config['test_settings']['speed_url']
            self.config['test_settings']['speed_url'] = test_url
            
            # 增加URL切换后的等待时间
            await asyncio.sleep(1)
            
            for i in range(repeats):
                if repeats > 1:
                    log.debug(f"執行第 {i+1}/{repeats} 輪速度測試")
                
                # 增加重试机制
                retry_count = 3
                for retry in range(retry_count):
                    # 使用原生協議速度測試，而不是HTTP
                    speed_result = await self._test_native_protocol_speed(proxy_url, duration)
                    if speed_result is not None and speed_result > 0.00005:
                        speeds.append(speed_result)
                        log.debug(f"第 {i+1} 輪原生協議速度測試成功: {speed_result:.4f}Mbps (重试 {retry+1}/{retry_count})")
                        
                        # 如果啟用了穩定性測試，計算穩定性分數
                        if stability_test_enabled and repeats > 1:
                            stability_score = await self._test_stability(proxy_url, duration)
                            if stability_score is not None:
                                stability_scores.append(stability_score)
                                log.debug(f"第 {i+1} 輪穩定性測試分數: {stability_score:.2f}")
                        break  # 成功一次就足够了
                    else:
                        log.debug(f"第 {i+1} 輪原生協議速度測試失敗 (重试 {retry+1}/{retry_count})")
                        if retry < retry_count - 1:
                            # 在重试前等待一段时间
                            await asyncio.sleep(2)
                        else:
                            # 所有重试都失败了
                            log.debug(f"第 {i+1} 輪所有重試都失敗")
                else:
                    # 成功完成了一轮测试
                    pass
            
            # 恢复原始speed_url配置
            self.config['test_settings']['speed_url'] = original_speed_url
            
            # 如果当前URL测试成功，就不再尝试其他URL
            if speeds:
                log.debug(f"URL {test_url} 測試成功，不再嘗試其他URL")
                break
            else:
                log.debug(f"URL {test_url} 測試失敗，嘗試下一個URL")
                # 在尝试下一个URL前等待一段时间
                await asyncio.sleep(3)
        
        if speeds:
            # 計算平均速度
            avg_speed = sum(speeds) / len(speeds)
            log.debug(f"平均速度: {avg_speed:.4f}Mbps (基於 {len(speeds)} 次有效測試)")
            
            # 如果有穩定性分數，也記錄下來
            if stability_scores:
                avg_stability = sum(stability_scores) / len(stability_scores)
                log.debug(f"平均穩定性分數: {avg_stability:.2f}")
                # 可以將穩定性信息存儲在結果中，供後續使用
                
            # 只有在速度合理時才返回結果，返回更高精度的值
            if avg_speed > 0.00005:  # 进一步降低最小速度阈值
                return round(avg_speed, 4)
            else:
                log.debug(f"平均速度過低: {avg_speed:.4f}Mbps")
                return None
        else:
            log.debug("所有速度測試輪次都失敗了")
            return None
    
    async def _test_proxy_with_simple_request(self, proxy_url: str) -> bool:
        """使用简单HTTP请求测试代理是否正常工作"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            connector = aiohttp.TCPConnector(
                limit=1,
                limit_per_host=1,
                force_close=True
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                headers={'User-Agent': 'SubsCheck-Ubuntu/1.0'}
            ) as session:
                # 使用一个小的测试URL
                test_url = "http://httpbin.org/ip"
                
                log.debug(f"测试代理功能: GET {test_url}")
                
                async with session.get(
                    test_url, 
                    proxy=proxy_url, 
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        response_text = await response.text()
                        log.debug(f"代理测试成功，响应: {response_text[:100]}")
                        return True
                    else:
                        log.debug(f"代理测试失败，状态码: {response.status}")
                        return False
                        
        except Exception as e:
            log.debug(f"代理功能测试异常: {type(e).__name__}: {e}")
            return False
    
    async def _test_socks5_proxy(self, proxy_url: str) -> bool:
        """
        测试SOCKS5代理是否正常工作
        简化版本，主要验证代理的可用性
        """
        try:
            import socket
            import struct
            
            # 解析代理URL
            proxy_parts = proxy_url[9:].split(':')  # 去掉socks5://
            proxy_host = proxy_parts[0]
            proxy_port = int(proxy_parts[1])
            
            # 创建socket连接到代理
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 短超时，快速检测
            
            try:
                sock.connect((proxy_host, proxy_port))
                
                # SOCKS5握手
                sock.send(b'\x05\x01\x00')
                response = sock.recv(2)
                
                if len(response) == 2 and response[0] == 5:
                    log.debug("SOCKS5代理握手成功")
                    return True
                else:
                    log.debug("SOCKS5代理握手失败")
                    return False
                    
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"SOCKS5代理测试失败: {type(e).__name__}: {e}")
            return False
    
    async def _test_proxy_http_forwarding(self, proxy_url: str) -> bool:
        """测试SOCKS5代理是否能正常转发HTTP流量"""
        try:
            # 使用更简单的测试方法
            import socket
            import struct
            
            # 解析代理URL
            proxy_parts = proxy_url[9:].split(':')  # 去掉socks5://
            proxy_host = proxy_parts[0]
            proxy_port = int(proxy_parts[1])
            
            # 创建socket连接到代理
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            try:
                sock.connect((proxy_host, proxy_port))
                
                # SOCKS5握手
                sock.send(b'\x05\x01\x00')
                response = sock.recv(2)
                
                if len(response) != 2 or response[0] != 5:
                    return False
                
                # 尝试连接到google.com:80
                target_host = "www.google.com"
                target_port = 80
                
                # 构造SOCKS5连接请求
                request = b'\x05\x01\x00\x03'  # SOCKS5, CONNECT, 保留字节, 域名类型
                request += bytes([len(target_host)])  # 域名长度
                request += target_host.encode()  # 域名
                request += struct.pack('>H', target_port)  # 端口（大端序）
                
                sock.send(request)
                response = sock.recv(10)
                
                if len(response) >= 2 and response[1] == 0:  # 连接成功
                    log.debug("SOCKS5代理能够转发HTTP流量")
                    return True
                else:
                    log.debug(f"SOCKS5代理连接失败，响应代码: {response[1] if len(response) > 1 else 'unknown'}")
                    return False
                    
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"代理转发测试失败: {type(e).__name__}: {e}")
            return False
    
    async def _test_single_speed_url(self, proxy_url: str, test_url: str, duration: int, timeout: aiohttp.ClientTimeout) -> Optional[float]:
        """Tests download speed for a single URL."""
        try:
            # Windows下aiohttp的SOCKS5支持有问题，使用替代方案
            if os.name == 'nt':  # Windows环境
                return await self._test_speed_via_socket(proxy_url, test_url, duration)
            
            # Linux环境使用aiohttp
            return await self._test_speed_via_aiohttp(proxy_url, test_url, duration, timeout)
            
        except Exception as e:
            log.debug(f"速度测试异常: {type(e).__name__}: {e}")
            return None
    
    async def _test_speed_via_socket(self, proxy_url: str, test_url: str, duration: int) -> Optional[float]:
        """使用socket直接通过SOCKS5代理下载（Windows环境）"""
        try:
            import socket
            import struct
            from urllib.parse import urlparse
            
            # 解析URL
            parsed_url = urlparse(test_url)
            target_host = parsed_url.hostname
            target_port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            path = parsed_url.path or '/'
            
            # 解析代理
            proxy_parts = proxy_url[9:].split(':')
            proxy_host = proxy_parts[0]
            proxy_port = int(proxy_parts[1])
            
            log.debug(f"使用Socket方法下载: {target_host}:{target_port}{path}")
            
            # 创建连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(duration + 10)
            
            try:
                # 连接到SOCKS5代理
                sock.connect((proxy_host, proxy_port))
                
                # SOCKS5握手
                sock.send(b'\x05\x01\x00')
                response = sock.recv(2)
                if len(response) != 2 or response[0] != 5:
                    log.debug(f"SOCKS5握手失败: {response.hex() if response else 'no response'}")
                    return None
                
                # 连接到目标服务器
                request = b'\x05\x01\x00\x03'
                request += bytes([len(target_host)])
                request += target_host.encode()
                request += struct.pack('>H', target_port)
                
                sock.send(request)
                response = sock.recv(10)
                if len(response) < 2 or response[1] != 0:
                    log.debug(f"SOCKS5连接失败: 响应代码 {response[1] if len(response) > 1 else 'unknown'}")
                    return None
                
                log.debug("✅ SOCKS5连接成功，发送HTTP请求")
                
                # 发送HTTP请求
                http_request = f"GET {path} HTTP/1.1\r\n"
                http_request += f"Host: {target_host}\r\n"
                http_request += "Connection: close\r\n"
                http_request += "User-Agent: SubsCheck-Ubuntu/1.0\r\n"
                http_request += "Accept: */*\r\n"
                http_request += "\r\n"
                
                sock.send(http_request.encode())
                
                # 读取响应
                start_time = time.monotonic()
                downloaded_bytes = 0
                header_received = False
                content_length = None
                header_buffer = b''
                
                log.debug("开始接收数据...")
                
                while True:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= duration:
                        log.debug(f"达到测试时间限制: {duration}秒")
                        break
                    
                    try:
                        sock.settimeout(2.0)  # 短超时以便检查时间
                        data = sock.recv(8192)
                        if not data:
                            log.debug("连接关闭")
                            break
                        
                        if not header_received:
                            # 处理HTTP响应头
                            header_buffer += data
                            if b'\r\n\r\n' in header_buffer:
                                header_end_pos = header_buffer.find(b'\r\n\r\n') + 4
                                header_part = header_buffer[:header_end_pos-4].decode('utf-8', errors='ignore')
                                body_part = header_buffer[header_end_pos:]
                                
                                log.debug(f"HTTP响应头: {header_part[:200]}...")
                                
                                # 检查HTTP状态码
                                status_line = header_part.split('\r\n')[0]
                                if '200 OK' not in status_line:
                                    log.debug(f"HTTP错误: {status_line}")
                                    return None
                                
                                # 获取内容长度
                                for line in header_part.split('\r\n'):
                                    if line.lower().startswith('content-length:'):
                                        try:
                                            content_length = int(line.split(':')[1].strip())
                                            log.debug(f"内容长度: {content_length} 字节")
                                        except:
                                            pass
                                
                                header_received = True
                                downloaded_bytes += len(body_part)
                                log.debug(f"开始下载，已收到 {len(body_part)} 字节")
                            else:
                                continue
                        else:
                            downloaded_bytes += len(data)
                            
                            # 每2秒记录一次进度
                            if int(elapsed) % 2 == 0 and elapsed > 0:
                                current_speed = (downloaded_bytes * 8) / elapsed / (1024 * 1024)
                                log.debug(f"下载进度: {downloaded_bytes/1024:.1f}KB, 当前速度: {current_speed:.2f}Mbps")
                        
                    except socket.timeout:
                        continue
                    except Exception as e:
                        log.debug(f"接收数据错误: {type(e).__name__}: {e}")
                        break
                
                final_elapsed = time.monotonic() - start_time
                
                if final_elapsed > 0 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / final_elapsed
                    speed_mbps = speed_bps / (1024 * 1024)
                    log.debug(f"Socket下载成功: {downloaded_bytes}字节, {final_elapsed:.2f}秒, {speed_mbps:.4f}Mbps")
                    
                    # 只有在速度合理时才返回结果，返回更高精度的值
                    if speed_mbps > 0.001:  # 降低最小速度阈值
                        return round(speed_mbps, 4)
                    else:
                        log.debug(f"速度过低: {speed_mbps:.4f}Mbps")
                        return None
                else:
                    log.debug(f"下载失败: 时间={final_elapsed:.2f}s, 字节={downloaded_bytes}")
                    return None
                
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"Socket下载异常: {type(e).__name__}: {e}")
            return None
    
    async def _test_speed_via_aiohttp(self, proxy_url: str, test_url: str, duration: int, timeout: aiohttp.ClientTimeout) -> Optional[float]:
        """Tests download speed for a single URL using aiohttp."""
        try:
            # 使用更适合的连接器配置
            connector = aiohttp.TCPConnector(
                limit=5,
                limit_per_host=2,
                enable_cleanup_closed=True,
                force_close=True,
                keepalive_timeout=30
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as session:
                start_time = time.perf_counter()  # 使用更高精度的计时器
                downloaded_bytes = 0
                
                log.debug(f"发起下载请求: GET {test_url}")
                
                async with session.get(test_url, proxy=proxy_url, timeout=timeout) as response:
                    log.debug(f"收到响应: {response.status} {response.reason}")
                    
                    if response.status != 200:
                        log.debug(f"下载失败，HTTP状态码: {response.status}")
                        return None
                    
                    # 检查响应头
                    content_length = response.headers.get('content-length')
                    if content_length:
                        log.debug(f"文件大小: {content_length} 字节")
                    
                    chunk_count = 0
                    last_log_time = start_time
                    
                    # 记录开始时间
                    first_byte_time = None
                    
                    while True:
                        try:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            
                            # 记录接收到第一个字节的时间
                            if first_byte_time is None:
                                first_byte_time = time.perf_counter()
                            
                            downloaded_bytes += len(chunk)
                            chunk_count += 1
                            elapsed_time = time.perf_counter() - start_time
                            
                            # 每1秒记录一次进度
                            current_time = time.perf_counter()
                            if current_time - last_log_time >= 1.0:
                                current_speed = (downloaded_bytes * 8) / elapsed_time / (1024 * 1024)
                                log.debug(f"下载进度: {downloaded_bytes/1024:.1f}KB, 当前速度: {current_speed:.4f}Mbps")
                                last_log_time = current_time
                            
                            if elapsed_time >= duration:
                                log.debug(f"达到测试时间限制: {duration}秒")
                                break
                                
                        except asyncio.TimeoutError:
                            log.debug(f"读取数据超时，已下载: {downloaded_bytes}字节")
                            break
                        except Exception as e:
                            log.debug(f"读取数据错误: {type(e).__name__}: {e}")
                            break
                
                final_elapsed_time = time.perf_counter() - start_time
                log.debug(f"下载完成: {downloaded_bytes}字节，耗时: {final_elapsed_time:.3f}秒")
                
                if final_elapsed_time > 0 and downloaded_bytes > 0:
                    # 计算考虑连接建立时间的精确速度
                    effective_time = final_elapsed_time
                    if first_byte_time is not None:
                        # 从接收到第一个字节开始计算时间，排除连接建立时间
                        effective_time = time.perf_counter() - first_byte_time + 0.1  # 添加少量缓冲时间
                    
                    speed_bps = (downloaded_bytes * 8) / effective_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    log.debug(f"计算速度: {speed_mbps:.4f}Mbps (基于{effective_time:.3f}秒有效时间)")
                    # 返回更高精度的速度值，保留4位小数
                    return round(speed_mbps, 4)
                else:
                    log.debug(f"无法计算速度: 时间={final_elapsed_time:.3f}, 字节={downloaded_bytes}")
                    return None

        except asyncio.TimeoutError:
            log.debug(f"速度测试超时: {duration + 15}秒")
            return None
        except aiohttp.ClientError as e:
            log.debug(f"客户端错误: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            log.debug(f"速度测试异常: {type(e).__name__}: {e}")
            return None
    
    async def _test_native_protocol_speed(self, proxy_url: str, duration: int) -> Optional[float]:
        """
        使用原生協議進行速度測試，通過sing-box SOCKS5代理
        這避免了HTTP協議被防火墻阻斷的問題
        """
        try:
            import socket
            import struct
            import time
            
            # 解析代理URL
            proxy_parts = proxy_url[9:].split(':')  # 去掉socks5://
            proxy_host = proxy_parts[0]
            proxy_port = int(proxy_parts[1])
            
            # 解析測試URL
            test_url: str = self.config['test_settings']['speed_url']
            url_parts = test_url.split('/', 3)
            protocol = url_parts[0][:-1]  # 去掉末尾的冒号
            host_port = url_parts[2]
            host_parts = host_port.split(':')
            target_host = host_parts[0]
            target_port = int(host_parts[1]) if len(host_parts) > 1 else (443 if protocol == 'https' else 80)
            target_path = '/' + url_parts[3] if len(url_parts) > 3 else '/'
            
            log.debug(f"開始原生協議速度測試: {test_url}")
            log.debug(f"目標主機: {target_host}:{target_port}, 路徑: {target_path}")
            
            # 創建socket連接到代理
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 增加连接超时时间以适应高延迟网络
            sock.settimeout(20)
            
            try:
                # 記錄連接開始時間
                connection_start = time.perf_counter()
                log.debug(f"連接到代理: {proxy_host}:{proxy_port}")
                sock.connect((proxy_host, proxy_port))
                log.debug("代理連接成功")
                
                # SOCKS5握手
                log.debug("開始SOCKS5握手")
                sock.send(b'\x05\x01\x00')
                response = sock.recv(2)
                log.debug(f"握手響應: {response}")
                
                if len(response) != 2 or response[0] != 5:
                    log.debug(f"SOCKS5握手失敗: 響應={response}")
                    return None
                
                # 建立到目標主機的連接
                log.debug(f"連接到目標主機: {target_host}:{target_port}")
                request = b'\x05\x01\x00\x03'  # SOCKS5, CONNECT, 保留字節, 域名類型
                request += bytes([len(target_host)])  # 域名長度
                request += target_host.encode()  # 域名
                request += struct.pack('>H', target_port)  # 端口（大端序）
                
                sock.send(request)
                # 增加接收超时时间
                sock.settimeout(15)
                response = sock.recv(10)
                log.debug(f"連接響應: {response}")
                
                if len(response) < 2 or response[1] != 0:  # 連接失敗
                    log.debug(f"連接到目標主機失敗: 響應代碼={response[1] if len(response) > 1 else 'unknown'}")
                    return None
                
                # 構造HTTP請求
                log.debug(f"構造HTTP請求: GET {target_path}")
                http_request = f"GET {target_path} HTTP/1.1\r\n"
                http_request += f"Host: {target_host}\r\n"
                # 使用更通用的User-Agent以避免被防火墙识别和阻止
                http_request += "User-Agent: Mozilla/5.0\r\n"
                http_request += "Accept: */*\r\n"
                http_request += "Connection: close\r\n"
                http_request += "\r\n"
                
                # 發送HTTP請求
                log.debug("發送HTTP請求")
                sock.send(http_request.encode())
                
                # 開始計時和下載
                start_time = time.perf_counter()  # 使用更高精度的計時器
                downloaded_bytes = 0
                header_received = False
                header_buffer = b''
                
                log.debug("開始接收數據...")
                
                # 增加总的测试时间以适应慢速连接
                extended_duration = duration * 3
                
                while True:
                    elapsed = time.perf_counter() - start_time
                    # 使用扩展的测试时间
                    if elapsed >= extended_duration:
                        log.debug(f"達到測試時間限制: {extended_duration}秒")
                        break
                    
                    try:
                        # 增加接收超时时间
                        sock.settimeout(8.0)
                        data = sock.recv(8192)
                        if not data:
                            # 如果没有数据但在合理时间内下载了一些数据，则认为测试成功
                            if downloaded_bytes > 0 and elapsed >= duration / 3:
                                log.debug("連接關閉，但已下載足夠數據")
                                break
                            else:
                                log.debug("連接關閉，下載數據不足")
                                break
                        
                        if not header_received:
                            # 處理HTTP響應頭
                            header_buffer += data
                            if b'\r\n\r\n' in header_buffer:
                                header_end_pos = header_buffer.find(b'\r\n\r\n') + 4
                                header_part = header_buffer[:header_end_pos-4].decode('utf-8', errors='ignore')
                                body_part = header_buffer[header_end_pos:]
                                
                                log.debug(f"HTTP響應頭: {header_part[:200]}...")
                                
                                # 檢查HTTP狀態碼
                                status_line = header_part.split('\r\n')[0]
                                # 接受更多种类的成功状态码
                                if not any(code in status_line for code in ['200 OK', '206 Partial', '304 Not Modified', '200']):
                                    log.debug(f"HTTP錯誤: {status_line}")
                                    # 即使状态码不是200，如果有数据也继续下载
                                    if not body_part and elapsed < 5:
                                        # 如果在前5秒内没有收到有效数据，则失败
                                        return None
                                
                                header_received = True
                                downloaded_bytes += len(body_part)
                                log.debug(f"開始下載，已收到 {len(body_part)} 字節")
                            else:
                                continue
                        else:
                            downloaded_bytes += len(data)
                            
                            # 每2秒記錄一次進度
                            if int(elapsed) % 2 == 0 and elapsed > 0:
                                current_speed = (downloaded_bytes * 8) / elapsed / (1024 * 1024)
                                log.debug(f"下載進度: {downloaded_bytes/1024:.1f}KB, 當前速度: {current_speed:.4f}Mbps")
                        
                    except socket.timeout:
                        log.debug(f"Socket接收超時，當前已下載: {downloaded_bytes} 字節")
                        # 即使超时，如果已下载足够数据也认为测试成功
                        if downloaded_bytes > 0 and elapsed >= duration / 3:
                            log.debug("超時但已下載足夠數據")
                            break
                        # 如果在前5秒就超时且没有下载到数据，则失败
                        if downloaded_bytes == 0 and elapsed < 5:
                            break
                        continue
                    except Exception as e:
                        log.debug(f"接收數據錯誤: {type(e).__name__}: {e}")
                        # 遇到异常，如果已下载足够数据则认为测试成功
                        if downloaded_bytes > 0 and elapsed >= duration / 3:
                            log.debug("異常但已下載足夠數據")
                            break
                        # 如果在前5秒就出错且没有下载到数据，则失败
                        if downloaded_bytes == 0 and elapsed < 5:
                            break
                        break
                
                final_elapsed = time.perf_counter() - start_time
                log.debug(f"下載完成: {downloaded_bytes}字節, 耗時: {final_elapsed:.3f}秒")
                
                # 放宽成功条件，只要有数据下载且用时合理就算成功
                if final_elapsed > 1 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / final_elapsed
                    speed_mbps = speed_bps / (1024 * 1024)
                    log.debug(f"Socket下載成功: {downloaded_bytes}字節, {final_elapsed:.3f}秒, {speed_mbps:.4f}Mbps")
                    
                    # 只有在速度合理時才返回結果，返回更高精度的值
                    if speed_mbps > 0.00005:  # 进一步降低最小速度阈值
                        return round(speed_mbps, 4)
                    else:
                        log.debug(f"速度過低: {speed_mbps:.4f}Mbps")
                        return None
                else:
                    log.debug(f"下載失敗: 時間={final_elapsed:.3f}s, 字節={downloaded_bytes}")
                    return None
                
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"Socket下載異常: {type(e).__name__}: {e}")
            import traceback
            log.debug(f"詳細錯誤信息: {traceback.format_exc()}")
            return None