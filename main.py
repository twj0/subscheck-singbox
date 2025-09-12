#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubsCheck-Ubuntu: 基于Sing-box的代理节点测速工具
作者: subscheck-ubuntu team
受到 tmpl/subs-check 和 tmpl/SubsCheck-Win-GUI 项目启发
"""

import asyncio
import argparse
import yaml
import aiohttp
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import json

# 导入项目模块
from utils.logger import log
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
                        log.info(f"订阅获取成功: {url[:50]}...")
                        return content
                    else:
                        log.warning(f"订阅返回错误 {response.status}: {url}")
        except Exception as e:
            log.error(f"订阅获取失败: {e}")
        return ""
    
    def parse_subscription_content(self, content: str) -> List[Dict[str, Any]]:
        """智能解析订阅内容"""
        nodes = []
        
        # 尝试YAML解析 (Clash 格式)
        try:
            config_data = yaml.safe_load(content)
            if isinstance(config_data, dict) and 'proxies' in config_data:
                log.info("检测到Clash YAML格式")
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
                log.info("检测到Base64编码内容")
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
            log.warning("没有节点可以测试")
            return []
        
        log.info(f"开始测试 {len(nodes)} 个节点...")
        
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
                log.error(f"测试异常: {result}")
            else:
                valid_results.append(result)
        
        return valid_results
    
    def save_results(self, results: List[Dict[str, Any]]) -> str:
        """保存测试结果"""
        results_dir = Path(self.config['output']['results_dir'])
        results_dir.mkdir(exist_ok=True)
        
        # 筛选成功的结果并按延迟排序
        success_results = [r for r in results if r['status'] == 'success']
        success_results.sort(key=lambda x: x.get('http_latency', 9999))
        
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
        
        log.info(f"结果已保存: {filename}")
        return str(filename)
    
    def display_results(self, results: List[Dict[str, Any]]):
        """显示测试结果"""
        success_results = [r for r in results if r['status'] == 'success']
        
        if not success_results:
            log.warning("没有成功的节点")
            return
        
        # 按延迟排序
        success_results.sort(key=lambda x: x.get('http_latency', 9999))
        
        print(f"\n{'=' * 80}")
        print(f"测试结果统计")
        print(f"{'=' * 80}")
        print(f"总测试节点: {len(results)}")
        print(f"成功节点: {len(success_results)}")
        print(f"成功率: {len(success_results)/len(results)*100:.1f}%")
        
        # 显示最佳节点
        show_count = min(self.config['output']['show_top_nodes'], len(success_results))
        if show_count > 0:
            print(f"\n最佳节点 (前{show_count}个):")
            print(f"{'-' * 80}")
            print(f"{'#':<3} {'Name':<35} {'Latency':<10} {'Speed':<12} {'Server':<20}")
            print(f"{'-' * 80}")
            
            for i, node in enumerate(success_results[:show_count]):
                latency = f"{node.get('http_latency', 0):.0f}ms" if node.get('http_latency') else "N/A"
                speed = f"{node.get('download_speed', 0):.2f}Mbps" if node.get('download_speed') else "N/A"
                print(f"{i+1:<3} {node['name'][:34]:<35} {latency:<10} {speed:<12} {node['server']:<20}")
    
    async def run(self, subscription_file: str):
        """主运行流程"""
        start_time = time.time()
        
        log.info("=" * 60)
        log.info("SubsCheck-Ubuntu v1.0 - 基于Sing-box的代理节点测速工具")
        log.info("=" * 60)
        
        # 检查订阅文件
        sub_file = Path(subscription_file)
        if not sub_file.exists():
            log.error(f"订阅文件不存在: {subscription_file}")
            return
        
        # 读取订阅链接
        with open(sub_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        log.info(f"发现 {len(urls)} 个订阅链接")
        
        if not urls:
            log.error("没有找到有效的订阅链接")
            return
        
        # 获取所有节点
        all_nodes = []
        for i, url in enumerate(urls, 1):
            log.info(f"正在获取订阅 {i}/{len(urls)}: {url[:50]}...")
            content = await self.fetch_subscription_content(url)
            if content:
                nodes = self.parse_subscription_content(content)
                all_nodes.extend(nodes)
                log.info(f"从订阅解析到 {len(nodes)} 个节点")
        
        if not all_nodes:
            log.error("没有解析到有效节点")
            return
        
        # 去重
        unique_nodes = self.deduplicate_nodes(all_nodes)
        log.info(f"去重后共 {len(unique_nodes)} 个节点")
        
        # 限制测试数量
        max_test_nodes = self.config['test_settings']['max_test_nodes']
        if len(unique_nodes) > max_test_nodes:
            unique_nodes = unique_nodes[:max_test_nodes]
            log.info(f"限制测试节点数量为 {max_test_nodes}")
        
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
            
            log.info(f"\n测试完成! 耗时: {duration:.1f}s, 成功: {success_count}/{len(results)}")
            
        finally:
            # 清理资源
            await self.tester.cleanup()

def load_config(config_file: str = 'config.yaml') -> Dict[str, Any]:
    """加载配置文件"""
    config_path = Path(config_file)
    if not config_path.exists():
        log.error(f"配置文件不存在: {config_file}")
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    log.info(f"配置加载成功: {config_file}")
    return config

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
        """
    )
    
    parser.add_argument('-s', '--subscription', default='subscription.txt',
                       help="订阅文件路径 (默认: subscription.txt)")
    parser.add_argument('-c', '--config', default='config.yaml',
                       help="配置文件路径 (默认: config.yaml)")
    parser.add_argument('-n', '--max-nodes', type=int,
                       help="最大测试节点数 (覆盖配置文件)")
    parser.add_argument('--version', action='version', version='SubsCheck-Ubuntu v1.0')
    
    args = parser.parse_args()
    
    try:
        # 加载配置
        config = load_config(args.config)
        
        # 命令行参数覆盖配置
        if args.max_nodes:
            config['test_settings']['max_test_nodes'] = args.max_nodes
        
        # 创建并运行测试器
        checker = SubsCheckUbuntu(config)
        await checker.run(args.subscription)
        
    except KeyboardInterrupt:
        log.info("用户中断测试")
    except Exception as e:
        log.error(f"程序运行失败: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())