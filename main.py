#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubsCheck-Ubuntu: 基于Sing-box的代理节点测速工具
twj0 | 3150774524@qq.com
专为中国大陆网络环境设计，使用原生协议测试节点连通性
"""

import asyncio
import argparse
import yaml
import aiohttp
import time
import schedule
import pytz
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, time as dt_time
import json
from dotenv import load_dotenv

# 导入项目模块
from utils.logger import setup_logger, get_logger, log_pwsh_command
from parsers.base_parser import parse_node_url
from parsers.clash_parser import parse_clash_config
from testers.node_tester import NodeTester
from utils.subscription_backup import SubscriptionBackup
from utils.uploader import ResultUploader

class SubsCheckUbuntu:
    """
    SubsCheck-Ubuntu 主类
    使用 Sing-box 作为代理核心进行高性能节点测试
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.tester = NodeTester(config)
        # 获取当前的日志器实例
        from utils.logger import get_logger
        self.log = get_logger()
        
    async def fetch_subscription_content(self, url: str, retry_count: int = 3) -> str:
        """获取订阅内容，支持重试机制"""
        for attempt in range(retry_count):
            try:
                timeout = aiohttp.ClientTimeout(
                    total=30,  # 增加总超时时间
                    connect=15,  # 连接超时
                    sock_read=15  # 读取超时
                )
                headers = {
                    'User-Agent': self.config['network']['user_agent'],
                    'Accept': '*/*',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive'
                }
                
                # 使用更适合的连接器配置
                connector = aiohttp.TCPConnector(
                    limit=30,
                    limit_per_host=10,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    enable_cleanup_closed=True
                )
                
                async with aiohttp.ClientSession(
                    connector=connector, 
                    timeout=timeout,
                    trust_env=True  # 使用系统代理设置
                ) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.status == 200:
                            content = await response.text(encoding='utf-8', errors='ignore')
                            self.log.info(f"订阅获取成功: {url[:50]}...")
                            return content
                        elif response.status in [301, 302, 303, 307, 308]:
                            # 处理重定向
                            redirect_url = response.headers.get('Location')
                            if redirect_url and attempt == 0:  # 只在第一次尝试重定向
                                self.log.info(f"订阅被重定向到: {redirect_url}")
                                return await self.fetch_subscription_content(redirect_url, 1)
                        else:
                            self.log.warning(f"订阅返回错误 {response.status}: {url}")
                            
            except asyncio.TimeoutError:
                self.log.error(f"订阅获取超时 (attempt {attempt + 1}/{retry_count}): {url[:50]}...")
            except aiohttp.ClientConnectorError as e:
                self.log.error(f"订阅连接错误 (attempt {attempt + 1}/{retry_count}): {str(e)[:100]}")
            except aiohttp.ClientError as e:
                self.log.error(f"订阅客户端错误 (attempt {attempt + 1}/{retry_count}): {str(e)[:100]}")
            except Exception as e:
                self.log.error(f"订阅获取失败 (attempt {attempt + 1}/{retry_count}): {str(e)[:100]}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < retry_count - 1:
                wait_time = 2 ** attempt  # 指数退补
                self.log.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
        
        return ""
    
    def parse_subscription_content(self, content: str) -> List[Dict[str, Any]]:
        """智能解析订阅内容"""
        nodes = []
        
        # 尝试YAML解析 (Clash 格式)
        try:
            config_data = yaml.safe_load(content)
            if isinstance(config_data, dict) and 'proxies' in config_data:
                self.log.info("检测到Clash YAML格式")
                clash_nodes = parse_clash_config(config_data)
                nodes.extend(clash_nodes)
                return nodes
        except Exception:
            pass
        
        # 尝试Base64解码
        try:
            import base64
            decoded = base64.b64decode(content.strip()).decode('utf-8')
            if any(proto in decoded for proto in ['vless://', 'vmess://', 'trojan://', 'ss://']):
                self.log.info("检测到Base64编码内容")
                content = decoded
        except Exception:
            pass
        
        # 解析链接
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            node = parse_node_url(line)
            if node:
                nodes.append(node)
        
        return nodes
    
    def deduplicate_nodes(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """节点去重"""
        seen = set()
        unique_nodes = []
        
        for node in nodes:
            try:
                # 使用服务器、端口和类型作为唯一标识
                key = (node['server'], node['port'], node['type'])
                if key not in seen:
                    seen.add(key)
                    unique_nodes.append(node)
            except (KeyError, TypeError):
                continue
        
        return unique_nodes
    
    async def test_nodes(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量测试节点（增强稳定性）"""
        if not nodes:
            self.log.warning("没有节点可以测试")
            return []
        
        self.log.info(f"开始测试 {len(nodes)} 个节点...")
        
        # 根据节点数量动态调整并发数
        base_concurrency = self.config['test_settings']['concurrency']
        auto_adjust = self.config['test_settings'].get('concurrency_auto_adjust', True)

        if auto_adjust:
            if len(nodes) > 100:
                # 大量节点时降低并发数
                actual_concurrency = max(1, base_concurrency // 2)
                self.log.info(f"检测到大量节点，智能调整并发数至 {actual_concurrency} 以提高稳定性")
            elif len(nodes) < 10:
                # 少量节点时可以提高并发数
                actual_concurrency = min(len(nodes), base_concurrency + 1)
            else:
                actual_concurrency = base_concurrency
        else:
            actual_concurrency = base_concurrency
            self.log.info(f"智能并发调整已禁用，使用固定并发数: {actual_concurrency}")
        
        # 并发测试
        semaphore = asyncio.Semaphore(actual_concurrency)
        
        async def test_with_limit(node: Dict[str, Any], index: int) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.tester.test_single_node(node, index)
                except Exception as e:
                    self.log.error(f"节点测试异常 [{index+1}]: {e}")
                    return {
                        'name': node.get('name', 'Unnamed'),
                        'server': node.get('server', 'N/A'),
                        'port': node.get('port', 'N/A'),
                        'type': node.get('type', 'N/A'),
                        'status': 'failed',
                        'error': f'Test exception: {str(e)[:100]}',
                        'http_latency': None,
                        'download_speed': None
                    }
        
        # 创建任务
        tasks = [test_with_limit(node, i) for i, node in enumerate(nodes)]
        
        # 执行测试（增加进度显示）
        results = []
        completed = 0
        
        # 分批执行以提高稳定性
        batch_size = min(20, len(tasks))  # 每批最多20个任务
        
        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i:i+batch_size]
            self.log.info(f"正在执行第 {i//batch_size + 1} 批测试（{len(batch_tasks)} 个节点）")
            
            try:
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # 处理结果
                for result in batch_results:
                    if isinstance(result, Exception):
                        self.log.error(f"批量测试异常: {result}")
                        results.append({
                            'name': 'Unknown',
                            'server': 'N/A',
                            'port': 'N/A', 
                            'type': 'N/A',
                            'status': 'failed',
                            'error': f'Batch test exception: {str(result)[:100]}',
                            'http_latency': None,
                            'download_speed': None
                        })
                    else:
                        results.append(result)
                    
                completed += len(batch_tasks)
                self.log.info(f"测试进度: {completed}/{len(nodes)} ({completed/len(nodes)*100:.1f}%)")
                
                # 批次间隔稍作等待，减少系统负载
                if i + batch_size < len(tasks):
                    await asyncio.sleep(1)
                    
            except Exception as e:
                self.log.error(f"批量测试失败: {e}")
                # 继续处理下一批
                continue
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]]) -> str:
        """保存测试结果"""
        results_dir = Path(self.config['output']['results_dir'])
        results_dir.mkdir(exist_ok=True)
        
        # 筛选成功的结果并按下载速度排序（速度优先）
        success_results = [r for r in results if r['status'] == 'success']
        # 按下载速度降序排列（速度越快越好）
        success_results.sort(key=lambda x: x.get('download_speed') or 0, reverse=True)
        
        # 生成结果文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = results_dir / f"subscheck_results_{timestamp}.json"
        
        result_data = {
            'timestamp': datetime.now().isoformat(),
            'total_tested': len(results),
            'success_count': len(success_results),
            'success_rate': f"{len(success_results)/len(results)*100:.1f}%" if results else "0%",
            'test_config': {
                'max_nodes': self.config['test_settings']['max_test_nodes'],
                'concurrency': self.config['test_settings']['concurrency'],
                'timeout': self.config['test_settings']['timeout']
            },
            'top_nodes': success_results[:self.config['output']['show_top_nodes']],
            'all_results': results if self.config['output']['save_all_results'] else success_results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        self.log.info(f"结果已保存: {filename}")
        return str(filename)
    
    def display_results(self, results: List[Dict[str, Any]]):
        """显示测试结果"""
        success_results = [r for r in results if r['status'] == 'success']
        
        if not success_results:
            self.log.warning("没有成功的节点")
            return
        
        # 按下载速度排序（速度优先）
        success_results.sort(key=lambda x: x.get('download_speed') or 0, reverse=True)
        
        print(f"\n{'=' * 80}")
        print(f"测试结果统计")
        print(f"{'=' * 80}")
        print(f"总测试节点: {len(results)}")
        print(f"成功节点: {len(success_results)}")
        print(f"成功率: {len(success_results)/len(results)*100:.1f}%")
        
        # 显示最佳节点
        show_count = min(self.config['output']['show_top_nodes'], len(success_results))
        if show_count > 0:
            print(f"\n最佳节点 (按速度排名前{show_count}个):")
            print(f"{'-' * 80}")
            print(f"{'#':<3} {'Name':<30} {'Speed':<15} {'Latency':<10} {'IP Purity':<15} {'Server':<20}")
            print(f"{'-' * 95}")
            
            for i, node in enumerate(success_results[:show_count]):
                # 根據速度大小選擇合適的精度顯示
                if node.get('download_speed'):
                    speed_val = node.get('download_speed', 0)
                    if speed_val >= 1:
                        speed = f"{speed_val:.2f}Mbps"
                    elif speed_val >= 0.1:
                        speed = f"{speed_val:.3f}Mbps"
                    else:
                        speed = f"{speed_val:.6f}Mbps"
                else:
                    speed = "N/A"
                latency = f"{node.get('http_latency', 0):.0f}ms" if node.get('http_latency') else "N/A"
                ip_purity = node.get('ip_purity', 'N/A') or "N/A"
                print(f"{i+1:<3} {node['name'][:29]:<30} {speed:<15} {latency:<10} {ip_purity:<15} {node['server']:<20}")
    
    async def run(self, subscription_file: str):
        """主运行流程"""
        start_time = time.time()
        
        self.log.info("=" * 60)
        self.log.info("SubsCheck-Ubuntu v1.0 - 基于Sing-box的代理节点测速工具")
        self.log.info("=" * 60)
        
        # 检查订阅文件
        sub_file = Path(subscription_file)
        if not sub_file.exists():
            self.log.error(f"订阅文件不存在: {subscription_file}")
            return
        
        # 读取订阅链接
        with open(sub_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        self.log.info(f"发现 {len(urls)} 个订阅链接")
        
        if not urls:
            self.log.error("没有找到有效的订阅链接")
            return
        
        # 获取所有节点
        all_nodes = []
        for i, url in enumerate(urls, 1):
            self.log.info(f"正在获取订阅 {i}/{len(urls)}: {url[:50]}...")
            content = await self.fetch_subscription_content(url)
            if content:
                nodes = self.parse_subscription_content(content)
                all_nodes.extend(nodes)
                self.log.info(f"从订阅解析到 {len(nodes)} 个节点")
        
        if not all_nodes:
            self.log.error("没有解析到有效节点")
            return
        
        # 去重
        unique_nodes = self.deduplicate_nodes(all_nodes)
        self.log.info(f"去重后共 {len(unique_nodes)} 个节点")
        
        # 限制测试数量（如果配置了的话）
        max_test_nodes = self.config.get('test_settings', {}).get('max_test_nodes')
        if max_test_nodes and max_test_nodes > 0 and len(unique_nodes) > max_test_nodes:
            unique_nodes = unique_nodes[:max_test_nodes]
            self.log.info(f"限制测试节点数量为 {max_test_nodes}")
        else:
            self.log.info(f"将测试所有 {len(unique_nodes)} 个节点（未设置节点数量限制）")
        
        try:
            # 测试节点
            results = await self.test_nodes(unique_nodes)
            
            # 显示结果
            self.display_results(results)
            
            # 保存结果
            result_file = self.save_results(results)
            
            # 统计
            end_time = time.time()
            duration = end_time - start_time
            success_count = len([r for r in results if r['status'] == 'success'])
            
            self.log.info(f"\n测试完成! 耗时: {duration:.1f}s, 成功: {success_count}/{len(results)}")
            
            # 上传测试结果
            if self.config.get('upload_settings', {}).get('enabled', False):
                self.log.info("开始上传测试结果...")
                result_uploader = ResultUploader(self.config)
                await result_uploader.upload_results(results, len(unique_nodes))

            # 备份订阅
            if self.config.get('subscription_backup', {}).get('enabled', False):
                self.log.info("开始备份成功的节点...")
                backup_module = SubscriptionBackup(self.config)
                successful_nodes = [r for r in results if r['status'] == 'success']
                await backup_module.backup_subscription(successful_nodes)
            
        finally:
            # 清理资源
            await self.tester.cleanup()

def load_config(config_file: str = 'config.yaml') -> Dict[str, Any]:
    """加载配置文件并解析环境变量"""
    from utils.logger import get_logger
    from utils.config_utils import parse_env_variables
    log = get_logger()
    
    config_path = Path(config_file)
    if not config_path.exists():
        log.error(f"配置文件不存在: {config_file}")
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    # 解析环境变量
    config = parse_env_variables(config)
    
    log.info(f"配置加载成功: {config_file}")
    return config

async def run_speed_test(config_file: str, subscription_file: str, max_nodes: int = None, debug: bool = False):
    """执行一次完整的测速任务"""
    from utils.logger import setup_logger, get_logger
    
    # 设置日志
    setup_logger(debug_mode=debug, debug_dir='debug')
    log = get_logger()
    
    try:
        log.info("=" * 60)
        log.info("开始执行定时测速任务")
        log.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info("=" * 60)
        
        # 加载配置
        config = load_config(config_file)
        
        # 命令行参数覆盖配置
        if max_nodes:
            config['test_settings']['max_test_nodes'] = max_nodes
        
        # 创建并运行测试器
        checker = SubsCheckUbuntu(config)
        await checker.run(subscription_file)
        
        log.info("定时测速任务完成")
        
    except Exception as e:
        log.error(f"定时任务执行失败: {e}")
        raise

def schedule_job(config: Dict[str, Any]):
    """定时任务的包装函数"""
    # 使用传入的配置
    scheduler_config = config.get('scheduler', {})
    asyncio.run(run_speed_test(
        config_file='config.yaml',
        subscription_file='subscription.txt',
        max_nodes=config.get('test_settings', {}).get('max_test_nodes'),
        debug=False
    ))

def start_scheduler(config: Dict[str, Any]):
    """启动定时任务调度器"""
    from utils.logger import setup_logger, get_logger
    
    # 设置日志
    setup_logger(debug_mode=False, debug_dir='debug')
    log = get_logger()
    
    # 从配置文件读取定时任务设置
    scheduler_config = config.get('scheduler', {})
    
    if not scheduler_config.get('enabled', False):
        log.warning("🚫 定时任务未在配置中启用")
        return
    
    # 获取时间设置
    schedule_time = scheduler_config.get('time', '20:00')  # 默认中国时间20点
    timezone_name = scheduler_config.get('timezone', 'Asia/Shanghai')
    is_daily = scheduler_config.get('daily', True)
    
    try:
        # 设置时区
        tz = pytz.timezone(timezone_name)
        
        # 解析时间
        hour, minute = map(int, schedule_time.split(':'))
        
        # 计算UTC时间（用于Schedule库）
        # 创建一个今天的datetime对象
        local_dt = tz.localize(datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0))
        utc_dt = local_dt.astimezone(pytz.UTC)
        utc_time_str = utc_dt.strftime('%H:%M')
        
        log.info(f"🕑 定时任务调度器已启动")
        log.info(f"📅 执行时间: 每天 {schedule_time} ({timezone_name})")
        log.info(f"🌍 UTC时间: {utc_time_str}")
        log.info(f"🚪 按 Ctrl+C 停止调度器")
        
        # 设置定时任务（使用UTC时间）
        if is_daily:
            schedule.every().day.at(utc_time_str).do(lambda: schedule_job(config))
        
        # 立即检查是否已经到了执行时间
        now_utc = datetime.now(pytz.UTC)
        if now_utc.hour == utc_dt.hour and now_utc.minute == utc_dt.minute:
            log.info("🚀 当前时间正好是执行时间，立即执行一次")
            schedule_job(config)
        
    except Exception as e:
        log.error(f"时间配置解析失败: {e}")
        log.info("使用默认配置: 每天UTC 12:00 (中国时间20:00)")
        schedule.every().day.at("12:00").do(lambda: schedule_job(config))
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
    except KeyboardInterrupt:
        log.info("🛡️ 用户中断调度器")

async def main():
    """主函数"""
    # 加载 .env 文件
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="SubsCheck-Ubuntu - 基于Sing-box的代理节点测速工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                           # 使用默认配置
  python main.py -s my_subs.txt           # 指定订阅文件
  python main.py -c custom_config.yaml    # 指定配置文件
  python main.py -n 20                    # 限制测试节点数
  python main.py --scheduler              # 启动定时任务模式
  python main.py --run-once               # 立即执行一次测试

定时任务设置:
  在 config.yaml 中修改 scheduler 配置：
  scheduler:
    enabled: true
    time: "20:00"             # 中国时间
    timezone: "Asia/Shanghai"
    daily: true
        """
    )
    
    parser.add_argument('-s', '--subscription', default='subscription.txt',
                       help="订阅文件路径 (默认: subscription.txt)")
    parser.add_argument('-c', '--config', default='config.yaml',
                       help="配置文件路径 (默认: config.yaml)")
    parser.add_argument('-n', '--max-nodes', type=int,
                       help="最大测试节点数 (覆盖配置文件)")
    parser.add_argument('-d', '--debug', action='store_true',
                       help="启用debug模式，记录详细日志和PowerShell输出")
    parser.add_argument('--debug-dir', default='debug',
                       help="debug日志文件夹 (默认: debug)")
    parser.add_argument('--scheduler', action='store_true',
                       help="启用定时任务模式，每天中国时间20点(UTC 12点)执行")
    parser.add_argument('--run-once', action='store_true',
                       help="立即执行一次测试任务")
    parser.add_argument('--version', action='version', version='SubsCheck-Ubuntu v1.0')
    
    args = parser.parse_args()
    
    try:
        # 设置debug模式
        debug_logger = setup_logger(debug_mode=args.debug, debug_dir=args.debug_dir)
        log = get_logger()
        
        if args.debug:
            log.info("🐛 Debug模式已启用")
            
            # 记录系统信息
            import platform
            import sys
            debug_info = {
                'platform': platform.platform(),
                'python_version': sys.version,
                'command_args': vars(args),
                'timestamp': datetime.now().isoformat()
            }
            debug_logger.save_debug_info(debug_info, 'system_info.json')
            
            # 测试PowerShell命令
            log_pwsh_command('Get-Host | Select-Object Version')
        
        # 加载配置
        config = load_config(args.config)
        
        # 命令行参数覆盖配置
        if args.max_nodes:
            config['test_settings']['max_test_nodes'] = args.max_nodes
        
        # 根据参数决定运行模式
        if args.scheduler:
            # 定时任务模式
            log.info("🕑 启动定时任务模式")
            start_scheduler(config)
        elif args.run_once:
            # 立即执行一次
            log.info("🚀 立即执行一次测试")
            await run_speed_test(args.config, args.subscription, args.max_nodes, args.debug)
        else:
            # 默认模式：直接运行
            checker = SubsCheckUbuntu(config)
            await checker.run(args.subscription)
        
    except KeyboardInterrupt:
        log = get_logger()
        log.info("用户中断测试")
    except Exception as e:
        log = get_logger()
        log.error(f"程序运行失败: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())