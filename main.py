#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubsCheck-Ubuntu: 基于Sing-box的代理节点测速工具
作者: subscheck-ubuntu team
受到 tmpl/subs-check 和 tmpl/SubsCheck-Win-GUI 项目启发
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

# 导入项目模块
from utils.logger import setup_logger, get_logger, log_pwsh_command
from parsers.base_parser import parse_node_url
from parsers.clash_parser import parse_clash_config
from testers.node_tester import NodeTester

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
        
    async def fetch_subscription_content(self, url: str) -> str:
        """获取订阅内容"""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {
                'User-Agent': self.config['network']['user_agent']
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout, headers=headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        self.log.info(f"订阅获取成功: {url[:50]}...")
                        return content
                    else:
                        self.log.warning(f"订阅返回错误 {response.status}: {url}")
        except Exception as e:
            self.log.error(f"订阅获取失败: {e}")
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
        """批量测试节点"""
        if not nodes:
            self.log.warning("没有节点可以测试")
            return []
        
        self.log.info(f"开始测试 {len(nodes)} 个节点...")
        
        # 并发测试
        semaphore = asyncio.Semaphore(self.config['test_settings']['concurrency'])
        
        async def test_with_limit(node: Dict[str, Any], index: int) -> Dict[str, Any]:
            async with semaphore:
                return await self.tester.test_single_node(node, index)
        
        # 创建任务
        tasks = [test_with_limit(node, i) for i, node in enumerate(nodes)]
        
        # 执行测试
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                self.log.error(f"测试异常: {result}")
            else:
                valid_results.append(result)
        
        return valid_results
    
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
            print(f"{'#':<3} {'Name':<35} {'Speed':<12} {'Latency':<10} {'Server':<20}")
            print(f"{'-' * 80}")
            
            for i, node in enumerate(success_results[:show_count]):
                speed = f"{node.get('download_speed', 0):.2f}Mbps" if node.get('download_speed') else "N/A"
                latency = f"{node.get('http_latency', 0):.0f}ms" if node.get('http_latency') else "N/A"
                print(f"{i+1:<3} {node['name'][:34]:<35} {speed:<12} {latency:<10} {node['server']:<20}")
    
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
        
        # 限制测试数量
        max_test_nodes = self.config['test_settings']['max_test_nodes']
        if len(unique_nodes) > max_test_nodes:
            unique_nodes = unique_nodes[:max_test_nodes]
            self.log.info(f"限制测试节点数量为 {max_test_nodes}")
        
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
            
        finally:
            # 清理资源
            await self.tester.cleanup()

def load_config(config_file: str = 'config.yaml') -> Dict[str, Any]:
    """加载配置文件"""
    from utils.logger import get_logger
    log = get_logger()
    
    config_path = Path(config_file)
    if not config_path.exists():
        log.error(f"配置文件不存在: {config_file}")
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
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