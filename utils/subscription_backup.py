#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订阅备份模块 - 支持 Gist 和 WebDAV
"""
import asyncio
import aiohttp
import base64
from typing import Dict, Any, List
from webdav3.client import Client as WebDAVClient

from utils.logger import log

class SubscriptionBackup:
    """订阅备份器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('subscription_backup', {})
        if not self.config.get('enabled', False):
            log.info("订阅备份功能未启用")
            return
            
        self.gist_config = self.config.get('gist', {})
        self.webdav_config = self.config.get('webdav', {})

    async def backup_subscription(self, successful_nodes: List[Dict[str, Any]]):
        """备份成功的节点到指定的平台"""
        if not self.config.get('enabled', False):
            return
            
        if not successful_nodes:
            log.warning("没有成功的节点可供备份")
            return
            
        # 提取原始链接并生成订阅内容
        node_urls = [node['original_url'] for node in successful_nodes if 'original_url' in node]
        if not node_urls:
            log.warning("没有找到可备份的原始节点链接")
            return
            
        subscription_content = "\n".join(node_urls)
        base64_content = base64.b64encode(subscription_content.encode('utf-8')).decode('utf-8')
        
        # 根据配置上传
        if self.gist_config.get('enabled', False):
            await self._upload_to_gist(base64_content)
            
        if self.webdav_config.get('enabled', False):
            self._upload_to_webdav(base64_content)

    async def _upload_to_gist(self, content: str):
        """上传到 GitHub Gist"""
        token = self.gist_config.get('token')
        gist_id = self.gist_config.get('gist_id')
        filename = self.gist_config.get('filename', 'subscheck_backup.txt')
        
        if not token or not gist_id:
            log.error("Gist token 或 gist_id 未配置")
            return
            
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        data = {
            "files": {
                filename: {
                    "content": content
                }
            }
        }
        
        url = f"https://api.github.com/gists/{gist_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.patch(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        log.info(f"订阅已成功备份到 Gist: {gist_id}")
                    else:
                        error_text = await response.text()
                        log.error(f"Gist 备份失败: HTTP {response.status} - {error_text}")
        except Exception as e:
            log.error(f"上传到 Gist 时发生异常: {e}")

    def _upload_to_webdav(self, content: str):
        """上传到 WebDAV"""
        options = {
            'webdav_hostname': self.webdav_config.get('hostname'),
            'webdav_login': self.webdav_config.get('username'),
            'webdav_password': self.webdav_config.get('password'),
            'webdav_root': self.webdav_config.get('root', '/')
        }
        
        remote_path = self.webdav_config.get('remote_path', 'subscheck_backup.txt')
        
        if not all([options['webdav_hostname'], options['webdav_login'], options['webdav_password']]):
            log.error("WebDAV 配置不完整 (hostname, username, password)")
            return
            
        try:
            client = WebDAVClient(options)
            # 直接写入字符串内容
            client.write_to(content, remote_path)
            log.info(f"订阅已成功备份到 WebDAV: {remote_path}")
        except Exception as e:
            log.error(f"上传到 WebDAV 时发生异常: {e}")
