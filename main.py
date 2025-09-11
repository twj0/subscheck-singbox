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
    try:
        async with session.get(url, timeout=15) as response:
            return await response.text()
    except Exception as e:
        log.error(f"Failed to fetch {url}: {e}")
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

    urls = [line.strip() for line in sub_file.read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')]
    log.info(f"Found {len(urls)} subscription links.")

    async with aiohttp.ClientSession(headers={'User-Agent': 'SubCheck/1.0'}) as session:
        tasks = [fetch_subscription_content(url, session) for url in urls]
        contents = await asyncio.gather(*tasks)

    all_nodes = []
    for content in contents:
        if content:
            all_nodes.extend(parse_content(content))
    
    unique_nodes = deduplicate_nodes(all_nodes)
    log.info(f"Total nodes: {len(all_nodes)}, Unique nodes: {len(unique_nodes)}")
    
    nodes_to_test = unique_nodes
    max_nodes = config['general_settings']['max_nodes_to_test']
    if max_nodes != -1 and len(unique_nodes) > max_nodes:
        # Sort nodes by name before slicing to ensure consistency
        unique_nodes.sort(key=lambda n: n.get('name', ''))
        nodes_to_test = unique_nodes[:max_nodes]
        log.info(f"Testing the first {max_nodes} nodes.")

    tester = NodeTester(config)
    concurrency = config['general_settings']['concurrency']
    semaphore = asyncio.Semaphore(concurrency)
    
    async def test_with_semaphore(node, index):
        async with semaphore:
            return await tester.test_single_node(node, index)

    test_tasks = [test_with_semaphore(node, i) for i, node in enumerate(nodes_to_test)]
    results = await asyncio.gather(*test_tasks)

    save_and_display_results(results, config)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\nProcess interrupted by user.")
