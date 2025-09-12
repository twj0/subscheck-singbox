# testers/node_tester.py
import asyncio
import time
import os
import aiohttp
from typing import Dict, Optional, List, Any

from core.singbox_runner import singboxRunner
from testers.direct_proxy_tester import DirectProxyTester
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
        
        # 初始化直接代理测试器
        self.direct_tester = DirectProxyTester(timeout=config.get('test_settings', {}).get('timeout', 15))
    
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
                        log.debug(f"开始速度测试...使用代理: {proxy_url}")
                        
                        # 先测试SOCKS5代理是否正常工作
                        socks_test = await self._test_socks5_proxy(proxy_url)
                        if socks_test:
                            log.debug("✅ SOCKS5代理可用，继续速度测试")
                            download_speed = await self._test_download_speed(proxy_url)
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
                            log.info(f"  ✓ {result['name']} - 延迟: {best_latency:.0f}ms ({test_method}) | 速度: {download_speed:.2f}Mbps")
                    else:
                        result['download_speed'] = None
            finally:
                await self._release_port(socks_port)

        except Exception as e:
            result['error'] = str(e)
            log.warning(f"  ✗ {result['name']} - Test failed with exception: {e}")
            log.debug(f"Exception details: {type(e).__name__}: {e}")
            if 'socks_port' in locals():
                await self._release_port(socks_port)

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
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            log.debug(f"Average latency: {avg_latency:.0f}ms from {len(latencies)} successful tests")
            return avg_latency
        else:
            log.debug("No successful connectivity tests")
            return None

    async def _test_download_speed(self, proxy_url: str) -> Optional[float]:
        """Tests download speed and returns speed in Mbps."""
        # 支持多个备用URL
        test_urls = self.config['test_settings'].get('speed_urls', [self.config['test_settings']['speed_url']])
        duration: int = self.config['test_settings']['speed_test_duration']
        timeout = aiohttp.ClientTimeout(total=duration + 15)  # 增加更多缓冲时间
        
        log.debug(f"开始速度测试，尝试 {len(test_urls)} 个测试URL")
        
        # 首先测试SOCKS5代理是否真的能转发流量
        proxy_test_result = await self._test_proxy_http_forwarding(proxy_url)
        if not proxy_test_result:
            log.debug("SOCKS5代理无法转发HTTP流量，跳过速度测试")
            return None
        
        # 尝试每个测试URL
        for i, test_url in enumerate(test_urls, 1):
            log.debug(f"尝试第 {i}/{len(test_urls)} 个测试URL: {test_url}")
            
            speed_result = await self._test_single_speed_url(proxy_url, test_url, duration, timeout)
            if speed_result is not None:
                log.debug(f"速度测试成功，使用URL: {test_url}")
                return speed_result
            else:
                log.debug(f"速度测试失败，URL: {test_url}")
        
        log.debug("所有速度测试URL都失败")
        return None
    
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
            target_port = parsed_url.port or 80
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
                    return None
                
                # 连接到目标服务器
                request = b'\x05\x01\x00\x03'
                request += bytes([len(target_host)])
                request += target_host.encode()
                request += struct.pack('>H', target_port)
                
                sock.send(request)
                response = sock.recv(10)
                if len(response) < 2 or response[1] != 0:
                    return None
                
                # 发送HTTP请求
                http_request = f"GET {path} HTTP/1.1\r\n"
                http_request += f"Host: {target_host}\r\n"
                http_request += "Connection: close\r\n"
                http_request += "User-Agent: SubsCheck-Ubuntu/1.0\r\n"
                http_request += "\r\n"
                
                sock.send(http_request.encode())
                
                # 读取响应
                start_time = time.monotonic()
                downloaded_bytes = 0
                header_end = False
                
                while True:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= duration:
                        break
                    
                    try:
                        sock.settimeout(1.0)  # 短超时以便检查时间
                        data = sock.recv(8192)
                        if not data:
                            break
                        
                        if not header_end:
                            # 找到HTTP响应头结束标记
                            if b'\r\n\r\n' in data:
                                header_end_pos = data.find(b'\r\n\r\n') + 4
                                data = data[header_end_pos:]  # 只计算body的字节数
                                header_end = True
                        
                        downloaded_bytes += len(data)
                        
                    except socket.timeout:
                        continue
                    except Exception:
                        break
                
                final_elapsed = time.monotonic() - start_time
                
                if final_elapsed > 0 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / final_elapsed
                    speed_mbps = speed_bps / (1024 * 1024)
                    log.debug(f"Socket下载成功: {downloaded_bytes}字节, {final_elapsed:.2f}秒, {speed_mbps:.2f}Mbps")
                    return round(speed_mbps, 2)
                    
                return None
                
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"Socket下载失败: {type(e).__name__}: {e}")
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
                start_time = time.monotonic()
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
                    
                    while True:
                        try:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            
                            downloaded_bytes += len(chunk)
                            chunk_count += 1
                            elapsed_time = time.monotonic() - start_time
                            
                            # 每2秒记录一次进度
                            current_time = time.monotonic()
                            if current_time - last_log_time >= 2.0:
                                current_speed = (downloaded_bytes * 8) / elapsed_time / (1024 * 1024)
                                log.debug(f"下载进度: {downloaded_bytes/1024:.1f}KB, 当前速度: {current_speed:.2f}Mbps")
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
                
                final_elapsed_time = time.monotonic() - start_time
                log.debug(f"下载完成: {downloaded_bytes}字节，耗时: {final_elapsed_time:.2f}秒")
                
                if final_elapsed_time > 0 and downloaded_bytes > 0:
                    speed_bps = (downloaded_bytes * 8) / final_elapsed_time
                    speed_mbps = speed_bps / (1024 * 1024)
                    log.debug(f"计算速度: {speed_mbps:.2f}Mbps")
                    return round(speed_mbps, 2)
                else:
                    log.debug(f"无法计算速度: 时间={final_elapsed_time}, 字节={downloaded_bytes}")
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