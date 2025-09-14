# utils/ip_checker.py
import aiohttp
from typing import Dict, Any, Optional

from utils.logger import log

class IPChecker:
    """
    通过代理查询出口IP的纯净度
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('ip_purity_check', {})
        self.enabled = self.config.get('enabled', False)
        self.api_token = self.config.get('api_token')
        self.ip_echo_urls = [
            "https://api.ipify.org?format=json",
            "http://ip-api.com/json/?fields=query"
        ]
        self.findip_api_url = "https://api.findip.net/{ip}/?token={token}"

    async def check_ip_purity(self, proxy_url: str) -> Optional[str]:
        """
        执行IP纯净度检查
        :param proxy_url: SOCKS5代理URL
        :return: IP类型字符串 (e.g., "Hosting", "Residential") or None
        """
        if not self.enabled or not self.api_token:
            return None

        try:
            # 1. 通过代理获取出口IP
            exit_ip = await self._get_exit_ip(proxy_url)
            if not exit_ip:
                log.debug("未能获取出口IP，跳过纯净度检查")
                return None
            
            log.debug(f"获取到出口IP: {exit_ip}")

            # 2. 查询 findip.net API
            ip_info = await self._query_findip_api(exit_ip)
            if not ip_info:
                log.debug(f"未能从findip.net获取IP信息: {exit_ip}")
                return None

            # 3. 解析IP类型
            traits = ip_info.get('traits', {})
            user_type = traits.get('user_type')
            connection_type = traits.get('connection_type')
            
            # 优先使用user_type，如果不存在则使用connection_type
            purity_type = user_type if user_type else connection_type
            
            if purity_type:
                log.debug(f"IP {exit_ip} 的纯净度类型为: {purity_type}")
                return purity_type
            else:
                log.debug(f"IP {exit_ip} 未找到纯净度信息")
                return "Unknown"

        except Exception as e:
            log.warning(f"IP纯净度检查失败: {e}")
            return None

    async def _get_exit_ip(self, proxy_url: str) -> Optional[str]:
        """通过代理访问IP回显服务获取出口IP"""
        timeout = aiohttp.ClientTimeout(total=15)
        for url in self.ip_echo_urls:
            try:
                async with aiohttp.ClientSession(trust_env=False) as session:
                    async with session.get(url, proxy=proxy_url, timeout=timeout) as response:
                        if response.status == 200:
                            data = await response.json()
                            # 兼容不同API的返回格式
                            if 'ip' in data:
                                return data['ip']
                            if 'query' in data:
                                return data['query']
            except Exception as e:
                log.debug(f"获取出口IP失败 ({url}): {e}")
                continue
        return None

    async def _query_findip_api(self, ip: str) -> Optional[Dict[str, Any]]:
        """查询findip.net API"""
        url = self.findip_api_url.format(ip=ip, token=self.api_token)
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        log.warning(f"Findip.net API返回错误: {response.status}")
                        return None
        except Exception as e:
            log.warning(f"查询Findip.net API失败: {e}")
            return None