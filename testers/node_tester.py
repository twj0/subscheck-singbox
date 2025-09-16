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
from utils.rate_limiter import create_rate_limiter, global_stats, RateLimitedReader
from utils.resource_manager import resource_manager

class NodeTester:
    """Tests a single proxy node using singbox."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # 使用統一資源管理器（學習Go版本）
        resource_manager.register_cleanup_handlers()
        
        # 初始化直接代理测试器
        self.direct_tester = DirectProxyTester(timeout=config.get('test_settings', {}).get('timeout', 15))
        self.ip_checker = IPChecker(config)
        
        # 初始化速度限制器（學習Go版本）
        native_config = self.config.get('native_speed_test', {})
        speed_limit = native_config.get('total_speed_limit', 0)
        self.rate_limiter = create_rate_limiter(speed_limit)
        
        # 測速參數（學習Go版本配置）
        self.download_timeout = native_config.get('download_timeout', 10)
        self.download_mb = native_config.get('download_mb', 20)
        self.min_speed_kbps = native_config.get('min_speed', 512)
        
        log.debug(f"NodeTester初始化: 速度限制={speed_limit}MB/s, 下載限制={self.download_mb}MB, 最低速度={self.min_speed_kbps}KB/s")
    
    async def cleanup(self):
        """清理資源（學習Go版本的自動清理）"""
        await resource_manager.cleanup_all()
        log.debug("NodeTester cleanup completed")

    async def _allocate_port(self, index: int) -> int:
        """Allocate a unique port for testing (using resource manager)."""
        # 使用資源管理器分配端口
        return await resource_manager.port_manager.allocate_port(f"node-{index}")

    async def _release_port(self, port: int):
        """Release a port back to the pool (using resource manager)."""
        # 使用資源管理器釋放端口
        await resource_manager.port_manager.release_port(port)
        
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
                        
                        # 使用優化的原生 Socket 測速
                        log.debug("⚡ 使用原生 Socket 測速（跨平台兼容）")
                        # 先测试SOCKS5代理是否正常工作
                        socks_test = await self._test_socks5_proxy(proxy_url)
                        if socks_test:
                            log.debug("✅ SOCKS5代理可用，继续速度测试")
                            # 使用原生協議測速（真正的協議測速）
                            download_speed = await self._test_native_protocol_bandwidth(node, proxy_url)
                            if download_speed is not None:
                                log.debug(f"✅ 原生協議測速成功: {download_speed:.4f}Mbps")
                            else:
                                log.debug("❌ 原生協議測速失敗，嘗試傳統方法")
                                # 備用：測試代理是否能轉發HTTP流量
                                http_test = await self._test_proxy_http_forwarding(proxy_url)
                                if http_test:
                                    log.debug("✅ HTTP转发测试成功，开始下载测试")
                                    download_speed = await self._test_download_speed(proxy_url)
                                else:
                                    log.debug("❌ HTTP转发测试失败，可能是协议配置问题")
                                    download_speed = None
                        else:
                            log.debug("❌ SOCKS5代理不可用，跳过速度测试")
                            download_speed = None
                            
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
                            allow_redirects=True,  # 允许重定向
                            ssl=False  # 对于被屏蔽网站可能需要禁用SSL验证
                        ) as response:
                            elapsed = (time.monotonic() - start_time) * 1000
                            log.debug(f"Response: {response.status} in {elapsed:.0f}ms")
                            
                            # 对于被屏蔽的网站，即使返回404或403等错误状态码，也表明连接是通的
                            if response.status < 500:  # 任何小于500的状态码都表示连接成功
                                latencies.append(elapsed)
                            elif response.status >= 500:
                                log.debug(f"HTTP server error {response.status} for {url}")
                                
                    except asyncio.TimeoutError:
                        log.debug(f"Timeout testing {url}")
                        continue
                    except Exception as e:
                        log.debug(f"Error testing {url}: {type(e).__name__}: {e}")
                        # 即使出现异常，也可能表明连接已建立，只是内容获取失败
                        # 这在测试被屏蔽网站时是常见情况
                        elapsed = (time.monotonic() - start_time) * 1000
                        if elapsed < timeout_seconds * 1000:  # 如果在超时前有响应
                            latencies.append(elapsed)
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
        """实现两阶段测速逻辑：预测试和正式测试"""
        speed_test_config = self.config['test_settings'].get('speed_test', {})
        pre_test_url = speed_test_config.get('pre_test_url')
        main_test_urls = speed_test_config.get('main_test_urls', [])
        duration: int = self.config['test_settings']['speed_test_duration']
        repeats: int = self.config['test_settings'].get('speed_test_repeats', 1)

        if not pre_test_url or not main_test_urls:
            log.warning("配置文件中缺少 'speed_test' 相关配置，跳过速度测试。")
            return None

        # --- 阶段一：预测试 ---
        log.debug(f"开始预测试: {pre_test_url}")
        pre_test_speed = await self._test_native_protocol_speed(proxy_url, pre_test_url, duration=5, is_pre_test=True)
        
        if pre_test_speed is None or pre_test_speed < 0.01:
            log.warning(f"  - 预测试失败或速度过低 ({pre_test_speed or 0:.4f}Mbps)，节点可能不可用，终止测速。")
            return None
        
        log.info(f"  - 预测试成功: {pre_test_speed:.4f}Mbps。继续进行正式测试...")

        # --- 阶段二：正式测试 ---
        speeds = []
        for test_url in main_test_urls:
            log.debug(f"开始正式测试: {test_url}")
            url_speeds = []
            for i in range(repeats):
                log.debug(f"执行第 {i+1}/{repeats} 轮正式测试")
                speed_result = await self._test_native_protocol_speed(proxy_url, test_url, duration, is_pre_test=False)
                if speed_result is not None and speed_result > 0.01:
                    url_speeds.append(speed_result)
                    log.debug(f"第 {i+1} 轮测试成功: {speed_result:.4f}Mbps")
                else:
                    log.debug(f"第 {i+1} 轮测试失败")
            
            if url_speeds:
                avg_url_speed = sum(url_speeds) / len(url_speeds)
                speeds.append(avg_url_speed)
                log.debug(f"URL {test_url} 平均速度: {avg_url_speed:.4f}Mbps")
                # 成功测试一个大文件后即可认为测速完成
                break 
            else:
                log.debug(f"URL {test_url} 所有轮次测试失败，尝试下一个URL")
                await asyncio.sleep(2)

        if speeds:
            final_speed = sum(speeds) / len(speeds)
            log.debug(f"最终平均速度: {final_speed:.4f}Mbps")
            return round(final_speed, 4)
        else:
            log.warning("  - 所有正式测速URL均失败。")
            return None
    
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
            if len(proxy_parts) != 2:
                log.debug(f"無效的代理URL格式: {proxy_url}")
                return False
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
            if len(proxy_parts) != 2:
                log.debug(f"無效的代理URL格式: {proxy_url}")
                return False
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
                
                if len(response) != 2 or response != 5:
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
                
                if len(response) >= 2 and response == 0:  # 连接成功
                    log.debug("SOCKS5代理能够转发HTTP流量")
                    return True
                else:
                    log.debug(f"SOCKS5代理连接失败，响应代码: {response if len(response) > 1 else 'unknown'}")
                    return False
                    
            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"代理转发测试失败: {type(e).__name__}: {e}")
            return False

    async def _test_native_speed_optimized(self, proxy_url: str) -> Optional[float]:
        """
        優化的原生 Socket 測速方法
        使用多個測試服務器，提供更準確的跨 GFW 測速結果
        """
        native_config = self.config.get('native_speed_test', {})
        if not native_config.get('enabled', True):
            log.debug("原生測速已禁用，使用傳統方法")
            return None
            
        test_servers = native_config.get('servers', [
            {
                "host": "releases.ubuntu.com",
                "port": 80,
                "path": "/20.04/ubuntu-20.04.6-live-server-amd64.iso",
                "name": "Ubuntu官方"
            },
            {
                "host": "download.mozilla.org",
                "port": 443,
                "path": "/pub/firefox/releases/latest/win64/en-US/Firefox%20Setup.exe",
                "name": "Mozilla官方"
            }
        ])
        
        duration = native_config.get('duration', 15)
        
        # 嘗試每個測試服務器
        for server in test_servers:
            try:
                test_url = f"http{'s' if server['port'] == 443 else ''}://{server['host']}{server['path']}"
                log.debug(f"  [原生測速] 嘗試服務器: {server['name']} ({server['host']})")
                
                speed = await self._test_native_protocol_speed(proxy_url, test_url, duration, False)
                if speed is not None and speed > 0:
                    log.debug(f"  [原生測速] ✅ {server['name']} 測速成功: {speed:.4f}Mbps")
                    return speed
                else:
                    log.debug(f"  [原生測速] ❌ {server['name']} 測速失敗")
                    
            except Exception as e:
                log.debug(f"  [原生測速] ❌ {server['name']} 發生異常: {e}")
                continue
        
        log.debug("  [原生測速] ❌ 所有測試服務器都失敗")
        return None

    async def _test_native_protocol_speed(self, proxy_url: str, test_url: str, duration: int, is_pre_test: bool = False) -> Optional[float]:
        """
        使用原生协议进行速度测试，支持预测试和正式测试模式。
        - 预测试: 使用短时间、小文件快速验证连通性。
        - 正式测试: 引入预热阶段，使用更长时间和更大文件获取精确速度。
        """
        try:
            import socket
            import struct
            import time
            from urllib.parse import urlparse
            
            # 正確解析 SOCKS5 代理URL格式: socks5://127.0.0.1:41001
            proxy_parts = proxy_url[9:].split(':')  # 移除 'socks5://' 前綴
            if len(proxy_parts) != 2:
                log.debug(f"無效的代理URL格式: {proxy_url}")
                return None
            proxy_host, proxy_port = proxy_parts[0], int(proxy_parts[1])
            
            parsed_url = urlparse(test_url)
            target_host = parsed_url.hostname
            target_port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            target_path = parsed_url.path or '/'

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15) # 统一连接超时

            try:
                # 連接到SOCKS5代理
                log.debug(f"  [Socket] 連接到代理: {proxy_host}:{proxy_port}")
                sock.connect((proxy_host, proxy_port))
                
                # SOCKS5握手 - 發送認證方法
                sock.send(b'\x05\x01\x00')  # 版本5, 1個方法, 無認證
                response = sock.recv(2)
                if len(response) != 2 or response[0] != 5:
                    log.debug(f"  [Socket] SOCKS5握手失敗，響應: {response.hex()}")
                    return None
                log.debug(f"  [Socket] SOCKS5握手成功")

                # 發送連接請求
                target_host_bytes = target_host.encode()
                request = b'\x05\x01\x00\x03' + bytes([len(target_host_bytes)]) + target_host_bytes + struct.pack('>H', target_port)
                sock.send(request)
                response = sock.recv(10)
                if len(response) < 2 or response[1] != 0:
                    log.debug(f"  [Socket] SOCKS5連接失敗，響應: {response.hex()}")
                    return None
                log.debug(f"  [Socket] 成功連接到目標: {target_host}:{target_port}")

                # 發送HTTP請求
                http_request = (f"GET {target_path} HTTP/1.1\r\n"
                                f"Host: {target_host}\r\n"
                                "User-Agent: Mozilla/5.0\r\n"
                                "Accept: */*\r\n"
                                "Connection: close\r\n\r\n").encode()
                sock.send(http_request)
                log.debug(f"  [Socket] 發送HTTP請求: GET {target_path}")

                header_buffer = b''
                while b'\r\n\r\n' not in header_buffer:
                    chunk = sock.recv(1024)
                    if not chunk: break
                    header_buffer += chunk
                
                header_end_pos = header_buffer.find(b'\r\n\r\n') + 4
                body_part = header_buffer[header_end_pos:]
                downloaded_bytes = len(body_part)

                # --- 预热阶段 (仅正式测试) ---
                warm_up_bytes = 256 * 1024  # 256KB
                if not is_pre_test:
                    while downloaded_bytes < warm_up_bytes:
                        data = sock.recv(8192)
                        if not data: break
                        downloaded_bytes += len(data)
                    log.debug(f"预热完成，已下载 {downloaded_bytes / 1024:.1f}KB")

                # --- 正式计时下载 ---
                start_time = time.perf_counter()
                downloaded_bytes = 0 # 重置计数器
                
                while True:
                    elapsed = time.perf_counter() - start_time
                    if elapsed >= duration:
                        break
                    
                    try:
                        sock.settimeout(max(1.0, duration - elapsed))
                        data = sock.recv(8192)
                        if not data: break
                        downloaded_bytes += len(data)
                    except socket.timeout:
                        break
                    except Exception:
                        break
                
                final_elapsed = time.perf_counter() - start_time
                if final_elapsed > 0.5 and downloaded_bytes > 0:
                    speed_mbps = (downloaded_bytes * 8) / final_elapsed / (1024 * 1024)
                    log.debug(f"  [Socket] 下載成功: {downloaded_bytes/1024:.1f}KB, 用時{final_elapsed:.2f}秒, 速度{speed_mbps:.4f}Mbps")
                    return round(speed_mbps, 4)
                else:
                    log.debug(f"  [Socket] 下載失敗: 數據量{downloaded_bytes}字節, 用時{final_elapsed:.2f}秒")
                    return None

            finally:
                sock.close()
                
        except Exception as e:
            log.debug(f"  [Socket] 原生協議測速異常: {type(e).__name__}: {e}")
            import traceback
            log.debug(f"  [Socket] 詳細錯誤: {traceback.format_exc()}")
            return None

    async def _test_native_protocol_bandwidth(self, node: Dict[str, Any], proxy_url: str) -> Optional[float]:
        """
        使用節點的原生協議進行帶寬測速
        根據節點類型（VLESS、VMess、Shadowsocks等）使用對應的原生協議
        """
        protocol = node.get('protocol', node.get('type', '')).lower()
        log.debug(f"  [原生協議] 開始 {protocol.upper()} 協議測速")
        
        try:
            # 根據協議類型選擇測速方法
            if protocol in ['vless', 'vmess']:
                return await self._test_vmess_vless_bandwidth(node, proxy_url)
            elif protocol in ['shadowsocks', 'ss']:
                return await self._test_shadowsocks_bandwidth(node, proxy_url)
            elif protocol == 'trojan':
                return await self._test_trojan_bandwidth(node, proxy_url)
            else:
                log.debug(f"  [原生協議] 不支持的協議類型: {protocol}")
                return None
                
        except Exception as e:
            log.debug(f"  [原生協議] 測速異常: {e}")
            return None

    async def _test_vmess_vless_bandwidth(self, node: Dict[str, Any], proxy_url: str) -> Optional[float]:
        """
        VMess/VLESS 協議帶寬測試
        通過SOCKS5代理建立連接，然後使用原生協議進行數據傳輸測試
        """
        import socket
        import time
        import secrets
        
        try:
            # 解析代理URL
            proxy_parts = proxy_url[9:].split(':')
            if len(proxy_parts) != 2:
                return None
            proxy_host, proxy_port = proxy_parts[0], int(proxy_parts[1])
            
            # 測試目標（使用GitHub Release大文件，避免CDN影響）
            test_targets = [
                ("github.com", 443, "/AaronFeng753/Waifu2x-Extension-GUI/releases/download/v2.21.12/Waifu2x-Extension-GUI-v2.21.12-Portable.7z"),  # ~100MB
                ("releases.ubuntu.com", 80, "/20.04/ubuntu-20.04.6-live-server-amd64.iso"),  # ~1GB
                ("download.mozilla.org", 443, "/pub/firefox/releases/latest/win64/en-US/Firefox%20Setup.exe"),  # ~50MB
            ]
            
            for target_host, target_port, target_path in test_targets:
                try:
                    # 建立SOCKS5連接
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(30)
                    
                    # 連接到代理
                    sock.connect((proxy_host, proxy_port))
                    
                    # SOCKS5握手
                    sock.send(b'\x05\x01\x00')
                    response = sock.recv(2)
                    if len(response) != 2 or response[0] != 5:
                        sock.close()
                        continue
                    
                    # 連接到目標
                    target_host_bytes = target_host.encode()
                    request = b'\x05\x01\x00\x03' + bytes([len(target_host_bytes)]) + target_host_bytes + target_port.to_bytes(2, 'big')
                    sock.send(request)
                    response = sock.recv(10)
                    if len(response) < 2 or response[1] != 0:
                        sock.close()
                        continue
                    
                    log.debug(f"  [原生協議] 已連接到 {target_host} 通過 {node.get('protocol', 'unknown').upper()} 代理")
                    
                    # 發送HTTP請求
                    http_request = (f"GET {target_path} HTTP/1.1\r\n"
                                  f"Host: {target_host}\r\n"
                                  "Connection: close\r\n\r\n").encode()
                    sock.send(http_request)
                    
                    # 跳過HTTP響應頭
                    header_buffer = b''
                    while b'\r\n\r\n' not in header_buffer:
                        chunk = sock.recv(1024)
                        if not chunk:
                            break
                        header_buffer += chunk
                    
                    # 開始計時下載（學習Go版本參數）
                    start_time = time.perf_counter()
                    downloaded_bytes = 0
                    duration = self.download_timeout  # 使用配置的超時
                    download_limit = self.download_mb * 1024 * 1024  # 下載限制
                    
                    while True:
                        elapsed = time.perf_counter() - start_time
                        if elapsed >= duration or downloaded_bytes >= download_limit:
                            break
                            
                        try:
                            sock.settimeout(max(1.0, duration - elapsed))
                            data = sock.recv(8192)
                            if not data:
                                break
                            
                            # 模擬速度限制（如果有的話）
                            if self.rate_limiter:
                                wait_time = self.rate_limiter.wait(len(data))
                                if wait_time > 0:
                                    time.sleep(wait_time)
                            
                            downloaded_bytes += len(data)
                            
                            # 統計流量
                            global_stats.add_bytes(len(data))
                            
                        except socket.timeout:
                            break
                        except Exception:
                            break
                    
                    final_elapsed = time.perf_counter() - start_time
                    sock.close()
                    
                    if final_elapsed > 1.0 and downloaded_bytes > 0:
                        # 計算速度（KB/s，學習Go版本）
                        speed_kbps = (downloaded_bytes / 1024) / final_elapsed
                        speed_mbps = speed_kbps / 1024
                        
                        # 檢查是否達到最低速度要求
                        if speed_kbps >= self.min_speed_kbps:
                            log.debug(f"  [原生協議] {node.get('protocol', 'unknown').upper()} 測速成功: {downloaded_bytes/1024:.1f}KB, {final_elapsed:.2f}秒, {speed_kbps:.1f}KB/s ({speed_mbps:.4f}Mbps)")
                            global_stats.add_node_tested(True)
                            return round(speed_mbps, 4)
                        else:
                            log.debug(f"  [原生協議] 速度過慢: {speed_kbps:.1f}KB/s < {self.min_speed_kbps}KB/s")
                            global_stats.add_node_tested(False)
                            return None
                    
                except Exception as e:
                    log.debug(f"  [原生協議] 目標 {target_host} 測試失敗: {e}")
                    continue
            
            log.debug(f"  [原生協議] 所有測試目標都失敗")
            return None
            
        except Exception as e:
            log.debug(f"  [原生協議] VMess/VLESS 測速異常: {e}")
            return None

    async def _test_shadowsocks_bandwidth(self, node: Dict[str, Any], proxy_url: str) -> Optional[float]:
        """
        Shadowsocks 協議帶寬測試
        """
        # 對於 Shadowsocks，通過 SOCKS5 代理的方式與 VMess/VLESS 類似
        return await self._test_vmess_vless_bandwidth(node, proxy_url)

    async def _test_trojan_bandwidth(self, node: Dict[str, Any], proxy_url: str) -> Optional[float]:
        """
        Trojan 協議帶寬測試
        """
        # 對於 Trojan，通過 SOCKS5 代理的方式與 VMess/VLESS 類似
        return await self._test_vmess_vless_bandwidth(node, proxy_url)