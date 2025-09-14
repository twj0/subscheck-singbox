#!/usr/bin/env python3
"""
结果上传模块 - 支持多种云端存储
借鉴项目的结果保存机制
"""
import json
import os
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, Any, Optional
import base64
from datetime import datetime
from webdav3.client import Client as WebDAVClient

from utils.logger import log

class ResultUploader:
    """结果上传器 - 支持多种上传方式"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.upload_config = config.get('upload_settings', {})
        
    async def upload_results(self, results: list, nodes_count: int):
        """上传测试结果到配置的服务"""
        if not self.upload_config.get('enabled', False):
            log.info("结果上传未启用")
            return
        
        # 生成结果摘要
        summary = self._generate_summary(results, nodes_count)
        
        # 根据配置选择上传方式
        upload_type = self.upload_config.get('type', 'local')
        
        try:
            if upload_type == 'gist':
                await self._upload_to_gist(summary, results)
            elif upload_type == 'webhook':
                await self._upload_to_webhook(summary, results)
            elif upload_type == 'r2':
                await self._upload_to_r2(summary, results)
            elif upload_type == 'webdav':
                await self._upload_to_webdav(summary, results)
            else:
                self._save_local(summary, results)
                
        except Exception as e:
            log.error(f"结果上传失败: {e}")
    
    def _generate_summary(self, results: list, nodes_count: int) -> Dict[str, Any]:
        """生成结果摘要"""
        success_nodes = [r for r in results if r.get('status') == 'success']
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_nodes': nodes_count,
            'success_nodes': len(success_nodes),
            'success_rate': f"{len(success_nodes)/nodes_count*100:.1f}%" if nodes_count > 0 else "0%",
            'top_nodes': success_nodes[:10] if success_nodes else []
        }
        
        if success_nodes:
            avg_latency = sum(n.get('http_latency', 0) for n in success_nodes) / len(success_nodes)
            avg_speed = sum(n.get('download_speed', 0) for n in success_nodes) / len(success_nodes)
            summary['avg_latency'] = f"{avg_latency:.1f}ms"
            summary['avg_speed'] = f"{avg_speed:.2f}Mbps"
        
        return summary
    
    async def _upload_to_gist(self, summary: Dict, results: list):
        """上传到GitHub Gist"""
        gist_config = self.upload_config.get('gist', {})
        token = gist_config.get('token')
        
        if not token:
            log.error("GitHub Gist token未配置")
            return
        
        # 准备Gist内容
        files = {
            "subscheck_summary.json": {
                "content": json.dumps(summary, indent=2, ensure_ascii=False)
            },
            "subscheck_results.json": {
                "content": json.dumps(results, indent=2, ensure_ascii=False)
            }
        }
        
        gist_data = {
            "description": f"SubsCheck Results - {summary['timestamp']}",
            "public": gist_config.get('public', False),
            "files": files
        }
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.github.com/gists",
                json=gist_data,
                headers=headers
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    log.info(f"结果已上传到Gist: {result['html_url']}")
                else:
                    log.error(f"Gist上传失败: HTTP {response.status}")
    
    async def _upload_to_webhook(self, summary: Dict, results: list):
        """上传到Webhook"""
        webhook_config = self.upload_config.get('webhook', {})
        url = webhook_config.get('url')
        
        if not url:
            log.error("Webhook URL未配置")
            return
        
        payload = {
            'type': 'subscheck_results',
            'summary': summary,
            'results': results[:50]  # 限制结果数量
        }
        
        headers = webhook_config.get('headers', {})
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    log.info(f"结果已上传到Webhook: {url}")
                else:
                    log.error(f"Webhook上传失败: HTTP {response.status}")
    
    async def _upload_to_r2(self, summary: Dict, results: list):
        """上传到Cloudflare R2 (简化实现)"""
        # 注：完整的R2上传需要AWS S3兼容的SDK
        log.info("R2上传功能需要配置AWS S3兼容客户端")

    async def _upload_to_webdav(self, summary: Dict, results: list):
        """上传到 WebDAV"""
        webdav_config = self.upload_config.get('webdav', {})
        options = {
            'webdav_hostname': webdav_config.get('hostname'),
            'webdav_login': webdav_config.get('username'),
            'webdav_password': webdav_config.get('password'),
            'webdav_root': webdav_config.get('root', '/')
        }
        
        remote_path = webdav_config.get('remote_path', 'subscheck_results.json')
        
        if not all([options['webdav_hostname'], options['webdav_login'], options['webdav_password']]):
            log.error("WebDAV 配置不完整 (hostname, username, password)")
            return
            
        try:
            # 将摘要和结果合并到一个JSON对象中
            upload_content = json.dumps({
                'summary': summary,
                'results': results
            }, indent=2, ensure_ascii=False)

            client = WebDAVClient(options)
            client.write_to(upload_content, remote_path)
            log.info(f"测试结果已成功上传到 WebDAV: {remote_path}")
        except Exception as e:
            log.error(f"上传到 WebDAV 时发生异常: {e}")
        
    def _save_local(self, summary: Dict, results: list):
        """本地保存（VPS默认方式）"""
        results_dir = Path('results')
        results_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 保存摘要
        summary_file = results_dir / f'summary_{timestamp}.json'
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # 保存详细结果
        results_file = results_dir / f'results_{timestamp}.json'
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # 保存最新结果
        latest_file = results_dir / 'latest.json'
        with open(latest_file, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': summary,
                'results': results[:20]  # 只保存前20个结果
            }, f, indent=2, ensure_ascii=False)
        
        log.info(f"结果已保存到本地: {results_file}")

# 在main.py中集成使用
async def upload_results_if_configured(results: list, config: Dict, total_nodes: int):
    """如果配置了上传，则上传结果"""
    try:
        uploader = ResultUploader(config)
        await uploader.upload_results(results, total_nodes)
    except Exception as e:
        log.error(f"结果上传过程中出错: {e}")