# main.py
import asyncio
import argparse
import yaml
import base64
from pathlib import Path
from typing import List, Dict, Set, Tuple

import aiohttp
from rich.table import Table
from rich.console import Console

from utils.logger import log
from parsers import clash_parser, base_parser
from testers.node_tester import NodeTester

console = Console()

async def fetch_subscription_content(url: str, session: aiohttp.ClientSession) -> str:
    """Fetches content from a single subscription URL."""
    max_retries = 2
    retry_delay = 1.0
    
    for attempt in range(max_retries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=15, connect=10)
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    content = await response.text()
                    return content
                else:
                    log.warning(f"订阅源返回错误状态 {response.status}: {url}")
                    
        except asyncio.TimeoutError:
            log.warning(f"订阅源访问超时 (第{attempt+1}次尝试): {url}")
        except Exception as e:
            log.warning(f"订阅源访问失败 (第{attempt+1}次尝试): {url} - {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(retry_delay)
            retry_delay *= 1.5  # 递增延迟
    
    return ""

def parse_content(content: str) -> List[Dict]:
    """Intelligently parses content, trying YAML then Base64/Plaintext."""
    try:
        config = yaml.safe_load(content)
        if isinstance(config, dict) and 'proxies' in config:
            log.info("Detected Clash (YAML) format, parsing proxies...")
            return clash_parser.parse_clash_proxies(config['proxies'])
    except yaml.YAMLError:
        pass # Not a valid YAML, proceed to next method

    try:
        # It's common for the entire file to be base64 encoded.
        decoded_content = base64.b64decode(content).decode('utf-8')
        log.info("Detected Base64 encoded content, decoding...")
        content = decoded_content
    except Exception:
        # Decoding failed, treat as plaintext.
        log.info("Not Base64 or YAML, processing as a list of plaintext links...")
        pass

    nodes = []
    for line in content.strip().split('\n'):
        node = base_parser.parse_node_url(line.strip())
        if node:
            nodes.append(node)
    return nodes

def deduplicate_nodes(nodes: List[Dict]) -> List[Dict]:
    """Removes duplicate nodes based on server, port, and type."""
    seen: Set[Tuple[str, int, str]] = set()
    unique_nodes = []
    for node in nodes:
        # Use a tuple of key properties to identify a unique node
        key = (node.get('server', ''), int(node.get('port', 0)), node.get('type', ''))
        if key not in seen:
            seen.add(key)
            unique_nodes.append(node)
    return unique_nodes

def save_and_display_results(results: List[Dict], config: Dict):
    """Sorts, saves, and prints results in a table."""
    success_nodes = [r for r in results if r['status'] == 'success']
    # Sort by download speed (desc) then latency (asc)
    success_nodes.sort(key=lambda x: (x.get('download_speed', 0), -x.get('http_latency', 9999)), reverse=True)

    output_settings = config['output_settings']
    results_dir = Path(output_settings['results_dir'])
    results_dir.mkdir(exist_ok=True)

    # Save full results to JSON
    # ... (Logic for saving to JSON can be added here if needed)

    log.info(f"Results will be saved to the '{results_dir}' directory.")

    # Display top N results in a table
    top_n = output_settings['top_n_results']
    table = Table(title=f"Top {top_n} Nodes")
    table.add_column("Rank", style="cyan")
    table.add_column("Name", style="magenta", max_width=40, overflow="ellipsis")
    table.add_column("Speed (Mbps)", style="green")
    table.add_column("Latency (ms)", style="yellow")
    
    for i, node in enumerate(success_nodes[:top_n]):
        speed = f"{node.get('download_speed', 0):.2f}"
        latency = f"{node.get('http_latency', 0):.2f}"
        table.add_row(str(i + 1), node['name'], speed, latency)
    
    console.print(table)

async def main():
    parser = argparse.ArgumentParser(description="SubCheck - A subscription node tester.")
    parser.add_argument('-f', '--file', default='subscription.txt', help="Path to the subscription file.")
    parser.add_argument('-c', '--config', default='config.yaml', help="Path to the configuration file.")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        log.error(f"Configuration file not found: {config_path}")
        return
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    sub_file = Path(args.file)
    if not sub_file.exists():
        log.error(f"Subscription file not found: {sub_file}")
        return

    urls = [line.strip() for line in sub_file.read_text(encoding='utf-8').splitlines() 
            if line.strip() and not line.startswith('#')]
    log.info(f"Found {len(urls)} subscription links.")
    
    if not urls:
        log.error("No valid subscription URLs found.")
        return

    # 使用连接池优化网络请求
    connector = aiohttp.TCPConnector(
        limit=20,
        limit_per_host=5,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
    
    tester = None
    try:
        async with aiohttp.ClientSession(
            headers={'User-Agent': 'SubCheck/1.0'}, 
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            # 串行获取订阅内容以避免过多并发连接
            contents = []
            for url in urls:
                content = await fetch_subscription_content(url, session)
                if content:
                    contents.append(content)
                await asyncio.sleep(0.1)  # 限制请求频率

        all_nodes = []
        valid_contents = [content for content in contents if content.strip()]
        log.info(f"Successfully fetched {len(valid_contents)} subscription contents.")
        
        for content in valid_contents:
            if content:
                nodes = parse_content(content)
                if nodes:
                    all_nodes.extend(nodes)
        
        unique_nodes = deduplicate_nodes(all_nodes)
        log.info(f"Total nodes: {len(all_nodes)}, Unique nodes: {len(unique_nodes)}")
        
        if not unique_nodes:
            log.error("No valid nodes found from all subscriptions.")
            return
        
        nodes_to_test = unique_nodes
        max_nodes = config['general_settings']['max_nodes_to_test']
        if max_nodes != -1 and len(unique_nodes) > max_nodes:
            # Sort nodes by name before slicing to ensure consistency
            unique_nodes.sort(key=lambda n: n.get('name', ''))
            nodes_to_test = unique_nodes[:max_nodes]
            log.info(f"Testing the first {max_nodes} nodes.")

        tester = NodeTester(config)
        concurrency = min(config['general_settings']['concurrency'], len(nodes_to_test), 10)  # 限制并发数
        semaphore = asyncio.Semaphore(concurrency)
        
        async def test_with_semaphore(node, index):
            async with semaphore:
                return await tester.test_single_node(node, index)

        log.info(f"Starting tests with concurrency: {concurrency}")
        test_tasks = [test_with_semaphore(node, i) for i, node in enumerate(nodes_to_test)]
        results = await asyncio.gather(*test_tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error(f"Node {i+1} test failed with exception: {result}")
                processed_results.append({
                    'name': nodes_to_test[i].get('name', 'Unknown'),
                    'status': 'failed',
                    'error': str(result)
                })
            else:
                processed_results.append(result)
        
        save_and_display_results(processed_results, config)
        
    except Exception as e:
        log.error(f"Main execution failed: {e}")
    finally:
        # 确保清理资源
        if tester:
            try:
                await tester.cleanup()
            except Exception as e:
                log.warning(f"Cleanup failed: {e}")
        
        try:
            await connector.close()
        except:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\nProcess interrupted by user.")
