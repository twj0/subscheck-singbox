#!/usr/bin/env python3
"""
SubsCheck-Singbox v3.0 - Python+Go混合架構
基於Go語言核心的高性能代理節點測速工具
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import argparse
import re
import threading
import codecs
import signal
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
import logging
from datetime import datetime

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 顏色和樣式定義
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# 進度條顯示
class ProgressBar:
    def __init__(self, total: int, width: int = 50):
        self.total = total
        self.width = width
        self.current = 0
        self.available = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.active = True
        
    def update(self, current: int, available: int):
        with self.lock:
            self.current = current
            self.available = available
            
    def increment(self, available: bool = False):
        with self.lock:
            self.current += 1
            if available:
                self.available += 1
                
    def display(self):
        if not self.active:
            return
            
        percent = self.current / self.total if self.total > 0 else 0
        filled_width = int(self.width * percent)
        bar = '█' * filled_width + '░' * (self.width - filled_width)
        
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
        else:
            eta = 0
            
        # 計算成功率
        success_rate = (self.available / self.current * 100) if self.current > 0 else 0
        
        print(f'\r{Colors.OKBLUE}🔄 進度: {Colors.BOLD}{bar}{Colors.ENDC} {percent:.1%} '
              f'({self.current}/{self.total}) '
              f'{Colors.OKGREEN}✓{self.available}{Colors.ENDC} '
              f'{Colors.WARNING}⏱️ {elapsed:.1f}s{Colors.ENDC} '
              f'{Colors.OKBLUE}⏳ ETA: {eta:.1f}s{Colors.ENDC} '
              f'{Colors.OKGREEN}成功率: {success_rate:.1f}%{Colors.ENDC}', 
              end='', flush=True)
              
    def finish(self):
        self.active = False
        print()  # 換行

class GoSubsChecker:
    """Go核心測速器的Python包裝器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.go_executable = None
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """載入配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"載入配置文件失敗: {e}")
            return {}
    
    def _find_go_executable(self) -> Optional[str]:
        """查找Go可執行文件"""
        possible_names = [
            "subscheck.exe",
            "subscheck",
            "subs-check.exe", 
            "subs-check"
        ]
        
        # 首先檢查當前目錄
        for name in possible_names:
            if Path(name).exists():
                return str(Path(name).absolute())
        
        # 檢查構建目錄
        build_dir = Path("build")
        if build_dir.exists():
            for name in possible_names:
                exe_path = build_dir / name
                if exe_path.exists():
                    return str(exe_path.absolute())
        
        return None
    
    async def compile_go_if_needed(self) -> bool:
        """如果需要，編譯Go程序"""
        self.go_executable = self._find_go_executable()
        
        if self.go_executable and Path(self.go_executable).exists():
            logger.info(f"✅ 找到Go可執行文件: {self.go_executable}")
            return True
        
        logger.info("🔨 Go可執行文件不存在，開始編譯...")
        
        # 檢查Go環境
        try:
            result = subprocess.run(["go", "version"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.error("❌ Go環境未找到，請安裝Go語言")
                return False
            logger.info(f"✅ Go環境: {result.stdout.strip()}")
        except Exception as e:
            logger.error(f"❌ 檢查Go環境失敗: {e}")
            return False
        
        # 編譯Go程序
        try:
            build_dir = Path("build")
            build_dir.mkdir(exist_ok=True)
            
            executable_name = "subscheck.exe" if os.name == 'nt' else "subscheck"
            output_path = build_dir / executable_name
            
            compile_cmd = [
                "go", "build", 
                "-ldflags", "-s -w",
                "-o", str(output_path),
                "."
            ]
            
            logger.info("🔨 編譯中...")
            result = subprocess.run(
                compile_cmd, 
                capture_output=True, 
                text=True, 
                timeout=120
            )
            
            if result.returncode != 0:
                logger.error(f"❌ 編譯失敗: {result.stderr}")
                return False
            
            self.go_executable = str(output_path)
            logger.info(f"✅ 編譯成功: {self.go_executable}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 編譯過程出錯: {e}")
            return False
    
    async def parse_subscriptions(self, subscription_file: str = "subscription.txt") -> List[str]:
        """解析訂閱文件，獲取所有訂閱鏈接"""
        subscription_urls = []
        
        # 從subscription.txt讀取
        if Path(subscription_file).exists():
            with open(subscription_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and line.startswith('http'):
                        subscription_urls.append(line)
        
        # 從config.yaml的sub-urls讀取
        config_urls = self.config.get('sub-urls', [])
        subscription_urls.extend(config_urls)
        
        # 去重
        subscription_urls = list(set(subscription_urls))
        logger.info(f"📋 解析到 {len(subscription_urls)} 個訂閱鏈接")
        
        return subscription_urls

    async def _fetch_and_parse_single(self, url: str) -> List[str]:
        try:
            content = await self.fetch_subscription_content(url)
            if not content:
                return []
            nodes = await self.parse_nodes_from_content(content)
            return nodes
        except Exception:
            return []

    async def collect_nodes_concurrently(self, urls: List[str], max_nodes: int, concurrency: int = 3) -> List[str]:
        """並發獲取並解析多個訂閱，達到上限即停止"""
        semaphore = asyncio.Semaphore(concurrency)
        collected: List[str] = []
        lock = asyncio.Lock()

        async def worker(u: str):
            nonlocal collected
            async with semaphore:
                nodes = await self._fetch_and_parse_single(u)
                async with lock:
                    if nodes:
                        collected.extend(nodes)
                        try:
                            from urllib.parse import urlparse
                            host = urlparse(u).netloc or u
                        except Exception:
                            host = u
                        print(f"{Colors.OKGREEN}✅ 來源[{host}] 解析到 {len(nodes)} 個節點{Colors.ENDC}")
                    else:
                        try:
                            from urllib.parse import urlparse
                            host = urlparse(u).netloc or u
                        except Exception:
                            host = u
                        logger.warning(f"來源[{host}] 未解析到有效節點")
        
        tasks = []
        for i, u in enumerate(urls, 1):
            print(f"{Colors.OKBLUE}📡 獲取訂閱 {i}/{len(urls)}: {u[:60]}...{Colors.ENDC}")
            tasks.append(asyncio.create_task(worker(u)))
        
        # 等待任務完成，同時檢查是否達到上限
        for t in asyncio.as_completed(tasks):
            await t
            async with lock:
                if len(collected) >= max_nodes:
                    break
        
        # 取消剩餘任務
        for t in tasks:
            if not t.done():
                t.cancel()
        
        return collected[:max_nodes]
    
    async def fetch_subscription_content(self, url: str) -> str:
        """獲取訂閱內容"""
        import aiohttp
        import random
        import ssl
        from urllib.parse import urlparse
        
        max_retries = 5  # 增加重試次数
        retry_delay = 1.0  # 初始重試延遲時間
        
        # 常見瀏覽器的User-Agent列表
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
            'SubCheck-Singbox/3.0'
        ]
        
        # 解析域名用於SNI
        parsed = urlparse(url)
        ssl_ctx = ssl.create_default_context()
        
        # 使用连接池优化
        connector = aiohttp.TCPConnector(
            limit_per_host=5,
            ssl=ssl_ctx
        )
        
        # 應用 GitHub 代理鏡像（如配置提供），加速大陸環境訪問
        gh_proxy = (self.config.get('github-proxy') or self.config.get('github_proxy') or '').strip()
        request_url = url
        if gh_proxy and url.startswith(('https://raw.githubusercontent.com', 'https://github.com', 'https://gist.github.com', 'https://api.github.com')):
            # 常見鏡像寫法：'https://ghproxy.com/' + 原始URL
            request_url = gh_proxy.rstrip('/') + '/' + url

        # 支持在大陸環境下通過本地/上游代理拉取訂閱
        http_proxy = (self.config.get('proxy') or self.config.get('http_proxy') or '').strip() or None

        async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
            for attempt in range(max_retries + 1):
                try:
                    # 使用更灵活的超时设置
                    timeout = aiohttp.ClientTimeout(
                        total=60,  # 增加总超时时间
                        connect=30,  # 增加连接超时时间
                        sock_read=45,  # 增加套接字读取超时
                        sock_connect=20  # 增加套接字连接超时
                    )
                    
                    # 隨機选择User-Agent
                    headers = {
                        'User-Agent': random.choice(user_agents),
                        'Accept': '*/*',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Cache-Control': 'no-cache'
                    }
                    
                    async with session.get(request_url, headers=headers, timeout=timeout, proxy=http_proxy) as response:
                        if response.status == 200:
                            content = await response.text()
                            logger.debug(f"✅ 獲取訂閱成功: {request_url[:50]}... (嘗試次數: {attempt + 1})")
                            
                            # 关闭连接池中的连接以避免资源泄漏
                            await session.connector.close()
                            return content
                        elif response.status == 301 or response.status == 302:
                            # 处理重定向
                            redirect_url = response.headers.get('Location')
                            if redirect_url:
                                logger.info(f"🔄 訂閱源重定向到: {redirect_url} (嘗試次數: {attempt + 1})")
                                request_url = redirect_url  # 更新URL以进行重试
                                continue
                        else:
                            logger.warning(f"⚠️ 訂閱響應錯誤 {response.status}: {request_url[:50]}... (嘗試次數: {attempt + 1})")
                            
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ 訂閱源訪問超時 (第{attempt + 1}次嘗試): {request_url} (連接超時)")
                except aiohttp.ClientResponseError as e:
                    logger.warning(f"🌐 訂閱源響應錯誤 (第{attempt + 1}次嘗試): {request_url} - {e}")
                except aiohttp.ClientConnectionError as e:
                    logger.warning(f"🔌 訂閱源連接錯誤 (第{attempt + 1}次嘗試): {request_url} - {e}")
                except aiohttp.ClientError as e:
                    logger.warning(f"🌐 訂閱源網絡錯誤 (第{attempt + 1}次嘗試): {request_url} - {e}")
                except Exception as e:
                    logger.warning(f"❌ 訂閱源訪問失敗 (第{attempt + 1}次嘗試): {request_url} - {e}")
                
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避策略
                    # 隨机抖动，避免所有请求同步
                    retry_delay += random.uniform(0, retry_delay)
        
        logger.error(f"❌ 訂閱源 {request_url} 在 {max_retries + 1} 次嘗試後仍然無法訪問")
        # 关闭连接池中的连接以避免资源泄漏
        await session.connector.close()
        return ""
    
    async def parse_nodes_from_content(self, content: str) -> List[str]:
        """從訂閱內容解析節點（多策略解碼，選擇最優結果）"""
        import base64
        import re
        import gzip
        import zlib

        def extract_nodes_from_text(text: str) -> List[str]:
            nodes_local: List[str] = []
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if any(line.startswith(proto) for proto in ['ss://', 'vmess://', 'vless://', 'trojan://', 'hysteria://', 'tuic://']):
                    nodes_local.append(line)
            return nodes_local

        def try_decoders(raw_bytes: bytes) -> List[str]:
            candidates: List[str] = []
            # 1) 原始文本
            try:
                candidates.append(raw_bytes.decode('utf-8', errors='ignore'))
            except Exception:
                candidates.append(str(content))
            # 2) Base64（寬鬆，忽略空白）
            try:
                b64_clean = re.sub(rb"\s+", b"", raw_bytes)
                candidates.append(base64.b64decode(b64_clean, validate=False).decode('utf-8', errors='ignore'))
            except Exception:
                pass
            # 3) gzip
            try:
                candidates.append(gzip.decompress(raw_bytes).decode('utf-8', errors='ignore'))
            except Exception:
                pass
            # 4) zlib
            try:
                candidates.append(zlib.decompress(raw_bytes).decode('utf-8', errors='ignore'))
            except Exception:
                pass
            return candidates

        raw_bytes = content if isinstance(content, (bytes, bytearray)) else str(content).encode('utf-8', errors='ignore')
        texts = try_decoders(raw_bytes)

        # 選擇包含最多節點URI的文本作為最優解碼結果
        best_text: str = ''
        best_nodes: List[str] = []
        for t in texts:
            nodes_candidate = extract_nodes_from_text(t)
            if len(nodes_candidate) > len(best_nodes):
                best_nodes = nodes_candidate
                best_text = t

        # 若所有解碼都未提取到節點，退回最可能的文本（原始文本）
        if not best_nodes:
            best_text = texts[0] if texts else (content if isinstance(content, str) else '')

        nodes: List[str] = []
        for raw_line in best_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(line.startswith(proto) for proto in ['ss://', 'vmess://', 'vless://', 'trojan://', 'hysteria://', 'tuic://']):
                nodes.append(line)
            elif line.startswith('http') and ('subscribe' in line or 'sub' in line):
                # 嵌套訂閱，遞歸獲取
                nested_content = await self.fetch_subscription_content(line)
                if nested_content:
                    nested_nodes = await self.parse_nodes_from_content(nested_content)
                    nodes.extend(nested_nodes)

        return nodes
    
    async def run_speed_test(self, subscription_file: str = "subscription.txt") -> Dict[str, Any]:
        """Python解析訂閱 + Go核心測速的混合方案"""
        if not self.go_executable:
            logger.error(f"{Colors.FAIL}❌ Go可執行文件未找到{Colors.ENDC}")
            return {"success": False, "error": "Go executable not found"}

        temp_dir = Path("temp_subscheck")
        temp_dir.mkdir(exist_ok=True)
        
        httpd = None
        progress_bar = None
        temp_config_file = Path("temp_config.yaml")
        process = None

        try:
            print(f"\n{Colors.OKGREEN}🚀 開始Python+Go混合測速...{Colors.ENDC}")
            print(f"{Colors.OKBLUE}📁 配置文件: {self.config_path}{Colors.ENDC}")
            print(f"{Colors.OKBLUE}📄 訂閱文件: {subscription_file}{Colors.ENDC}")

            # Phase 1: Python解析訂閱
            print(f"\n{Colors.WARNING}🐍 Phase 1: Python解析訂閱...{Colors.ENDC}")
            subscription_urls = await self.parse_subscriptions(subscription_file)

            if not subscription_urls:
                print(f"{Colors.FAIL}❌ 沒有找到有效的訂閱鏈接{Colors.ENDC}")
                return {"success": False, "error": "No valid subscription URLs found"}

            all_nodes: List[str] = []
            max_test_nodes = 100
            # 並發抓取與解析，加速慢源
            all_nodes = await self.collect_nodes_concurrently(subscription_urls, max_test_nodes, concurrency=min(4, len(subscription_urls)))

            unique_nodes = list(set(all_nodes))
            print(f"{Colors.OKBLUE}📊 總節點數: {len(all_nodes)}, 去重後: {len(unique_nodes)}{Colors.ENDC}")

            if not unique_nodes:
                print(f"{Colors.FAIL}❌ 沒有解析到有效節點{Colors.ENDC}")
                return {"success": False, "error": "No valid nodes found"}
            if len(unique_nodes) > max_test_nodes:
                unique_nodes = unique_nodes[:max_test_nodes]
                print(f"{Colors.WARNING}⚡ 限制測試節點數量為 {max_test_nodes}{Colors.ENDC}")

            # Phase 2: Go核心測速
            print(f"\n{Colors.WARNING}⚡ Phase 2: Go核心測速...{Colors.ENDC}")

            from http.server import HTTPServer, BaseHTTPRequestHandler

            test_port = 8299
            nodes_content = '\n'.join(unique_nodes)

            class NodeHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/nodes':
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(nodes_content.encode('utf-8'))
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def log_message(self, format, *args):
                    pass

            httpd = HTTPServer(('127.0.0.1', test_port), NodeHandler)
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            print(f"{Colors.OKGREEN}🌐 臨時HTTP服務器啟動: http://127.0.0.1:{test_port}/nodes{Colors.ENDC}")

            temp_config = self.config.copy()
            temp_config['sub-urls'] = [f"http://127.0.0.1:{test_port}/nodes"]
            # 强制设置cron表达式为空，确保Go程序立即执行而不是等待定时任务
            temp_config['cron-expression'] = ""
            # 强制禁用Go侧HTTP服务器，避免其常驻导致Python等待退出
            temp_config['listen-port'] = ""
            
            with open(temp_config_file, 'w', encoding='utf-8') as f:
                import yaml
                yaml.dump(temp_config, f, default_flow_style=False, allow_unicode=True)

            cmd = [self.go_executable, "-f", str(temp_config_file)]
            start_time = time.time()
            print(f"{Colors.OKBLUE}🔄 啟動Go測速程序...{Colors.ENDC}")

            progress_bar = ProgressBar(len(unique_nodes))
            progress_thread = threading.Thread(target=self._show_progress, args=(progress_bar,))
            progress_thread.daemon = True
            progress_thread.start()

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=Path.cwd()
            )

            # 實時讀取Go輸出，根據進度行更新進度條；檢測到完成後立即結束Go進程
            stdout_lines: List[str] = []
            stderr_lines: List[str] = []
            timeout_occurred = False

            completion_event = asyncio.Event()

            async def _read_stream(stream: asyncio.StreamReader, is_stdout: bool):
                nonlocal stdout_lines, stderr_lines
                buffer = ''
                while True:
                    try:
                        chunk = await stream.read(1024)
                    except Exception:
                        break
                    if not chunk:
                        # flush remaining buffer
                        if buffer:
                            text = buffer
                            if is_stdout:
                                stdout_lines.append(text)
                            else:
                                stderr_lines.append(text)
                            # parse once more
                            for seg in re.split(r"[\r\n]", text):
                                if not seg:
                                    continue
                                try:
                                    # 支持簡體/繁體的『进度/進度』關鍵詞
                                    m = re.search(r"[进進]度:\s*\[[^\]]*\]\s*(\d+\.\d+)%\s*\((\d+)/(\d+)\)\s*可用:\s*(\d+)", seg)
                                    if m:
                                        _, cur, total, available = m.groups()
                                        progress_bar.update(int(cur), int(available))
                                        if int(total) > 0 and int(cur) >= int(total):
                                            completion_event.set()
                                    if ('检测完成' in seg) or ('檢測完成' in seg):
                                        completion_event.set()
                                    if '可用节点数量' in seg:
                                        completion_event.set()
                                except Exception:
                                    pass
                        break
                    text = chunk.decode('utf-8', errors='ignore')
                    buffer += text
                    # split by CR or LF to form segments
                    parts = re.split(r"([\r\n])", buffer)
                    # reassemble complete segments (ending with a delimiter), keep tail
                    assembled = []
                    tail = ''
                    for i in range(0, len(parts)-1, 2):
                        seg = parts[i]
                        delim = parts[i+1]
                        if delim in ('\r', '\n'):
                            assembled.append(seg)
                        else:
                            tail += seg + delim
                    if len(parts) % 2 == 1:
                        tail += parts[-1]
                    buffer = tail
                    for seg in assembled:
                        if not seg:
                            continue
                        if is_stdout:
                            stdout_lines.append(seg + '\n')
                        else:
                            stderr_lines.append(seg + '\n')
                        try:
                            # 支持簡體/繁體的『进度/進度』關鍵詞
                            m = re.search(r"[进進]度:\s*\[[^\]]*\]\s*(\d+\.\d+)%\s*\((\d+)/(\d+)\)\s*可用:\s*(\d+)", seg)
                            if m:
                                _, cur, total, available = m.groups()
                                progress_bar.update(int(cur), int(available))
                                if int(total) > 0 and int(cur) >= int(total):
                                    completion_event.set()
                            if ('检测完成' in seg) or ('檢測完成' in seg):
                                completion_event.set()
                            if '可用节点数量' in seg:
                                completion_event.set()
                        except Exception:
                            pass

            reader_tasks = [
                asyncio.create_task(_read_stream(process.stdout, True)),
                asyncio.create_task(_read_stream(process.stderr, False))
            ]

            # 估算最大等待時間，亦作為保險超時
            wait_time = min(120 + len(unique_nodes) // 5, 600)
            print(f"{Colors.WARNING}⏳ 等待Go程序完成測速 (最長 {wait_time} 秒)...{Colors.ENDC}")

            try:
                # 等待完成事件或總超時
                await asyncio.wait_for(completion_event.wait(), timeout=wait_time)
            except asyncio.TimeoutError:
                timeout_occurred = True
                print(f"{Colors.WARNING}⚠️ Go程序超時，強制終止{Colors.ENDC}")
            finally:
                # 嘗試優雅結束Go進程
                try:
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=3)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()
                except Exception:
                    pass

                # 等待讀取任務結束
                try:
                    await asyncio.wait_for(asyncio.gather(*reader_tasks, return_exceptions=True), timeout=3)
                except asyncio.TimeoutError:
                    for t in reader_tasks:
                        t.cancel()

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)


            duration = time.time() - start_time
            print(f"{Colors.OKGREEN}✅ Go核心測速完成 (耗時: {duration:.1f}s){Colors.ENDC}")

            results = self._parse_go_output(stdout, stderr)
            
            return {
                "success": True,
                "results": results,
                "total_nodes": len(all_nodes),
                "tested_nodes": len(unique_nodes),
                "duration": duration,
                "stdout": stdout,
                "stderr": stderr,
                "timeout": timeout_occurred
            }

        finally:
            if progress_bar:
                progress_bar.finish()
            if httpd:
                httpd.shutdown()
                httpd.server_close()
            if temp_config_file.exists():
                try:
                    os.remove(temp_config_file)
                except OSError as e:
                    logger.warning(f"無法刪除臨時配置文件: {e}")
            
            # 確保進程被徹底清理
            if process and process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except Exception as e:
                    logger.warning(f"清理Go進程時出錯: {e}")
    
    def _show_progress(self, progress_bar: ProgressBar):
        """顯示進度條的線程函數"""
        while progress_bar.active:
            progress_bar.display()
            time.sleep(0.5)
    
    def _parse_go_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """解析Go程序的輸出，提取測速結果"""
        import re
        
        results = {
            "progress_info": [],
            "test_results": [],
            "statistics": {},
            "successful_nodes": [],
            "failed_nodes": []
        }
        
        if not stdout:
            return results
        
        lines = stdout.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 解析進度信息（支持簡體/繁體『进度/進度』）
            if (('进度:' in line) or ('進度:' in line)) and '可用:' in line:
                progress_match = re.search(r'[进進]度:.*?(\d+\.\d+)%.*?\((\d+)/(\d+)\).*?可用:\s*(\d+)', line)
                if progress_match:
                    percent, current, total, available = progress_match.groups()
                    results["progress_info"].append({
                        "percent": float(percent),
                        "current": int(current),
                        "total": int(total),
                        "available": int(available)
                    })
            
            # 解析統計信息
            elif 'INFO' in line:
                if '获取节点数量:' in line:
                    match = re.search(r'获取节点数量:\s*(\d+)', line)
                    if match:
                        results["statistics"]["total_nodes"] = int(match.group(1))
                elif '去重后节点数量:' in line:
                    match = re.search(r'去重后节点数量:\s*(\d+)', line)
                    if match:
                        results["statistics"]["unique_nodes"] = int(match.group(1))
                elif '可用节点数量:' in line:
                    match = re.search(r'可用节点数量:\s*(\d+)', line)
                    if match:
                        results["statistics"]["available_nodes"] = int(match.group(1))
                elif '测试总消耗流量:' in line:
                    match = re.search(r'测试总消耗流量:\s*([\d.]+)GB', line)
                    if match:
                        results["statistics"]["total_traffic"] = float(match.group(1))
            
            # 解析節點測試結果 (假設Go程序會輸出類似格式)
            # 我們需要修改Go程序來輸出更詳細的節點信息
            elif '✓' in line or '✗' in line:
                # 嘗試解析節點測試結果
                # 格式: ✓ [協議] 節點名 - IP:端口 | 延遲: XXXms | 速度: XXX Mbps
                node_match = re.search(r'([✓✗])\s*\[([^\]]+)\]\s*([^-]+)-\s*([^|]+)\|.*?延遲:\s*(\d+)ms.*?速度:\s*([\d.]+)\s*Mbps', line)
                if node_match:
                    status, protocol, name, ip_port, latency, speed = node_match.groups()
                    node_result = {
                        "name": name.strip(),
                        "protocol": protocol.strip(),
                        "ip_port": ip_port.strip(),
                        "latency": int(latency),
                        "speed": float(speed),
                        "success": status == '✓'
                    }
                    
                    if node_result["success"]:
                        results["successful_nodes"].append(node_result)
                    else:
                        results["failed_nodes"].append(node_result)
        
        return results
    
    def display_results(self, result: Dict[str, Any]):
        """顯示測速結果"""
        if not result.get("success"):
            print(f"\n{Colors.FAIL}❌ 測速失敗: {result.get('error', 'Unknown error')}{Colors.ENDC}")
            return
        
        # 顯示結果標題
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}🎯 SubsCheck-Singbox v3.0 Python+Go混合測速結果{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")
        
        # 顯示基本統計
        total_nodes = result.get("total_nodes", 0)
        tested_nodes = result.get("tested_nodes", 0)
        duration = result.get("duration", 0)
        
        # 優先使用Go端去重後的節點數或進度總數，以避免與Python側統計不一致
        results = result.get("results", {})
        statistics = results.get("statistics", {})
        progress_info = results.get("progress_info", [])
        tested_nodes_display = tested_nodes
        if isinstance(statistics.get("unique_nodes"), int) and statistics.get("unique_nodes") > 0:
            tested_nodes_display = statistics.get("unique_nodes")
        elif progress_info:
            tested_nodes_display = progress_info[-1].get("total", tested_nodes)

        print(f"{Colors.OKBLUE}📊 節點統計:{Colors.ENDC}")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} Python解析節點: {Colors.BOLD}{total_nodes:,}{Colors.ENDC}")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 實際測試節點: {Colors.BOLD}{tested_nodes_display:,}{Colors.ENDC}")
        
        # 解析並顯示Go程序的結果
        statistics = results.get("statistics", {})
        successful_nodes = results.get("successful_nodes", [])
        failed_nodes = results.get("failed_nodes", [])
        
        # 嘗試從stderr獲取更多統計信息
        available_count = 0
        total_traffic = 0.0
        
        if result.get("stderr"):
            stderr_lines = result["stderr"].split('\n')
            for line in stderr_lines:
                if 'INFO' in line:
                    if '可用节点数量:' in line:
                        match = re.search(r'可用节点数量:\s*(\d+)', line)
                        if match:
                            available_count = int(match.group(1))
                    elif '测试总消耗流量:' in line:
                        match = re.search(r'测试总消耗流量:\s*([\d.]+)GB', line)
                        if match:
                            total_traffic = float(match.group(1))
        
        # 如果沒有從stderr獲取到，使用之前解析的數據
        if available_count == 0 and "available_nodes" in statistics:
            available_count = statistics["available_nodes"]
        if total_traffic == 0.0 and "total_traffic" in statistics:
            total_traffic = statistics["total_traffic"]
        
        # 顯示Go核心測速統計
        print(f"\n{Colors.WARNING}⚡ Go核心測速統計:{Colors.ENDC}")
        if "total_nodes" in statistics:
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} Go接收節點: {Colors.BOLD}{statistics['total_nodes']}{Colors.ENDC}")
        if "unique_nodes" in statistics:
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 去重後節點: {Colors.BOLD}{statistics['unique_nodes']}{Colors.ENDC}")
        if available_count > 0:
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 可用節點: {Colors.BOLD}{Colors.OKGREEN}{available_count}{Colors.ENDC}")
        if total_traffic > 0:
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 消耗流量: {Colors.BOLD}{total_traffic:.3f} GB{Colors.ENDC}")
        
        # 如果沒有解析到詳細節點信息，顯示原始Go輸出的統計
        if not successful_nodes and not failed_nodes and result.get("stdout"):
            print(f"\n{Colors.OKBLUE}📄 Go程序原始輸出摘要:{Colors.ENDC}")
            stdout_lines = result["stdout"].split('\n')
            for line in stdout_lines[-20:]:  # 顯示最後20行
                if 'INFO' in line and any(keyword in line for keyword in ['节点数量', '可用节点', '消耗流量', '检测完成']):
                    print(f"   {Colors.OKGREEN}└─{Colors.ENDC} {line.split('INFO')[-1].strip()}")
        
        # 顯示成功的節點詳情
        if successful_nodes:
            print(f"\n{Colors.OKGREEN}✅ 成功節點詳情 ({len(successful_nodes)}個):{Colors.ENDC}")
            print(f"{Colors.OKBLUE}{'-' * 80}{Colors.ENDC}")
            for i, node in enumerate(successful_nodes[:10], 1):  # 只顯示前10個
                protocol_emoji = {
                    'ss': '🔐', 'vmess': '🚀', 'vless': '⚡', 
                    'trojan': '🏛️', 'hysteria': '💨', 'tuic': '🔥'
                }.get(node.get('protocol', '').lower(), '📡')
                
                print(f"{Colors.BOLD}{i:2d}.{Colors.ENDC} {protocol_emoji} [{Colors.OKBLUE}{node.get('protocol', 'Unknown')}{Colors.ENDC}] {Colors.BOLD}{node.get('name', 'Unnamed')}{Colors.ENDC}")
                print(f"    📍 {node.get('ip_port', 'Unknown IP')}")
                print(f"    ⏱️  延遲: {Colors.WARNING}{node.get('latency', 0)}ms{Colors.ENDC} | 🚀 速度: {Colors.OKGREEN}{node.get('speed', 0):.2f} Mbps{Colors.ENDC}")
                if i < len(successful_nodes) and i < 10:
                    print()
            
            if len(successful_nodes) > 10:
                print(f"    {Colors.WARNING}... 還有 {len(successful_nodes) - 10} 個成功節點{Colors.ENDC}")
        
        # 顯示失敗節點統計
        if failed_nodes:
            print(f"\n{Colors.FAIL}❌ 失敗節點: {len(failed_nodes)}個{Colors.ENDC}")
            
            # 按協議分組統計失敗節點
            failed_by_protocol = {}
            for node in failed_nodes:
                protocol = node.get('protocol', 'Unknown')
                failed_by_protocol[protocol] = failed_by_protocol.get(protocol, 0) + 1
            
            for protocol, count in failed_by_protocol.items():
                print(f"   {Colors.OKGREEN}└─{Colors.ENDC} {protocol}: {count}個")
        
        # 顯示進度信息（最後一個進度）
        if progress_info:
            last_progress = progress_info[-1]
            print(f"\n{Colors.OKBLUE}📈 測速進度:{Colors.ENDC}")
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 完成度: {Colors.BOLD}{last_progress['percent']:.1f}%{Colors.ENDC}")
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 已測試: {Colors.BOLD}{last_progress['current']}/{last_progress['total']}{Colors.ENDC}")
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 實時可用: {Colors.BOLD}{Colors.OKGREEN}{last_progress['available']}{Colors.ENDC}")
        
        print(f"\n{Colors.WARNING}⏱️  執行時間:{Colors.ENDC}")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 總耗時: {Colors.BOLD}{duration:.1f} 秒{Colors.ENDC}")
        if tested_nodes > 0:
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 平均每節點: {Colors.BOLD}{duration/tested_nodes:.2f} 秒{Colors.ENDC}")
        
        # 計算成功率
        total_tested = len(successful_nodes) + len(failed_nodes)
        if total_tested > 0:
            success_rate = len(successful_nodes) / total_tested * 100
            print(f"\n{Colors.OKBLUE}📈 測試結果:{Colors.ENDC}")
            print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 成功率: {Colors.BOLD}{success_rate:.1f}%{Colors.ENDC} ({Colors.OKGREEN}{len(successful_nodes)}{Colors.ENDC}/{total_tested})")
            if successful_nodes:
                avg_speed = sum(node.get('speed', 0) for node in successful_nodes) / len(successful_nodes)
                avg_latency = sum(node.get('latency', 0) for node in successful_nodes) / len(successful_nodes)
                print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 平均速度: {Colors.BOLD}{Colors.OKGREEN}{avg_speed:.2f} Mbps{Colors.ENDC}")
                print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 平均延遲: {Colors.BOLD}{Colors.WARNING}{avg_latency:.0f}ms{Colors.ENDC}")
        
        print(f"\n{Colors.OKBLUE}🔧 版本信息:{Colors.ENDC}")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} Python橋接: v3.0 (智能訂閱解析)")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} Go核心: v3.0 (原生協議測速)")
        
        # 如果是超時終止，顯示提示
        if result.get("timeout"):
            print(f"\n{Colors.WARNING}⚠️  注意: Go程序因超時被終止，結果可能不完整{Colors.ENDC}")
        
        # 添加使用提示
        print(f"\n{Colors.OKBLUE}💡 使用提示:{Colors.ENDC}")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 編輯 {Colors.BOLD}config.yaml{Colors.ENDC} 添加您的訂閱鏈接")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 創建 {Colors.BOLD}.env{Colors.ENDC} 文件配置 GitHub Gist 或 WebDAV")
        print(f"   {Colors.OKGREEN}└─{Colors.ENDC} 使用 {Colors.BOLD}uv run main.py --help{Colors.ENDC} 查看更多選項")
        
        print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.ENDC}")

class PythonScheduler:
    """Python定時調度器 - 保留Python的調度優勢"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scheduler_config = config.get("scheduler", {})
    
    async def setup_scheduler(self):
        """設置定時任務"""
        if not self.scheduler_config.get("enabled", False):
            logger.info("定時調度器已禁用")
            return
        
        schedule_time = self.scheduler_config.get("time", "20:00")
        timezone = self.scheduler_config.get("timezone", "Asia/Shanghai")
        
        logger.info(f"📅 定時調度已啟用: 每天 {schedule_time} ({timezone})")
        # 這裡可以集成APScheduler等Python調度庫
        # 暫時保留接口，後續擴展

async def main():
    """主入口函數"""
    parser = argparse.ArgumentParser(description="SubsCheck-Singbox v3.0 - Python+Go混合架構")
    parser.add_argument("-f", "--config", default="config.yaml", help="配置文件路徑")
    parser.add_argument("-s", "--subscription", default="subscription.txt", help="訂閱文件路徑")
    parser.add_argument("--compile-only", action="store_true", help="僅編譯Go程序")
    parser.add_argument("--python-scheduler", action="store_true", help="啟用Python定時調度器")
    parser.add_argument("--version", action="version", version="SubsCheck-Singbox v3.0")
    
    args = parser.parse_args()
    
    print("🚀 SubsCheck-Singbox v3.0 - Python+Go混合架構")
    print("=" * 60)
    print("🐍 Python層: 配置管理、結果展示、定時調度")  
    print("⚡ Go核心: 高性能測速、併發控制、代理檢測")
    print("=" * 60)
    
    # 初始化Go測速器
    checker = GoSubsChecker(args.config)
    
    # 編譯Go程序
    if not await checker.compile_go_if_needed():
        logger.error("❌ Go程序編譯失敗，退出")
        return 1
    
    if args.compile_only:
        logger.info("✅ 僅編譯模式完成")
        return 0
    
    # 初始化Python調度器
    if args.python_scheduler:
        scheduler = PythonScheduler(checker.config)
        await scheduler.setup_scheduler()
        logger.info("Python定時調度器已啟動，程序將保持運行...")
        try:
            while True:
                await asyncio.sleep(60)  # 保持運行
        except KeyboardInterrupt:
            logger.info("收到中斷信號，退出程序")
            return 0
    
    # 執行測速
    result = await checker.run_speed_test(args.subscription)
    
    # 顯示結果
    checker.display_results(result)
    
    return 0 if result.get("success") else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("程序被用戶中斷")
        sys.exit(130)
    except Exception as e:
        logger.error(f"程序執行失敗: {e}")
        sys.exit(1)
