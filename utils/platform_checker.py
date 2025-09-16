#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
平台檢測器
學習Go版本的多平台檢測邏輯 (Cloudflare、Google、Netflix等)
"""

import aiohttp
import asyncio
import json
import re
from typing import Dict, Any, Optional, Tuple
from utils.logger import log


class PlatformChecker:
    """
    平台可用性檢測器，學習Go版本的平台檢測
    """
    
    def __init__(self, timeout: int = 10):
        """
        初始化平台檢測器
        
        Args:
            timeout: 請求超時時間
        """
        self.timeout = timeout
        
    async def check_cloudflare(self, session: aiohttp.ClientSession) -> bool:
        """
        檢測Cloudflare可達性
        學習Go版本的CheckCloudflare實現
        
        Args:
            session: HTTP會話
            
        Returns:
            bool: 是否可達
        """
        try:
            async with session.get(
                "https://www.cloudflare.com/cdn-cgi/trace",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # 檢查響應是否包含Cloudflare的標識信息
                    return "colo=" in text and "ip=" in text
                return False
        except Exception as e:
            log.debug(f"Cloudflare檢測失敗: {e}")
            return False
    
    async def check_google(self, session: aiohttp.ClientSession) -> bool:
        """
        檢測Google可達性
        學習Go版本的CheckGoogle實現
        
        Args:
            session: HTTP會話
            
        Returns:
            bool: 是否可達
        """
        try:
            async with session.get(
                "https://www.google.com/generate_204",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # Google的204端點應該返回204狀態碼且無內容
                return response.status == 204
        except Exception as e:
            log.debug(f"Google檢測失敗: {e}")
            return False
    
    async def check_youtube(self, session: aiohttp.ClientSession) -> Optional[str]:
        """
        檢測YouTube可用性和地區
        學習Go版本的CheckYoutube實現
        
        Args:
            session: HTTP會話
            
        Returns:
            Optional[str]: 地區代碼，None表示不可用
        """
        try:
            # 使用YouTube的API端點檢測
            async with session.get(
                "https://www.youtube.com/feed/trending",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # 嘗試從頁面中提取地區信息
                    region_match = re.search(r'"countryCode":"([A-Z]{2})"', text)
                    if region_match:
                        return region_match.group(1)
                    return "Unknown"
                return None
        except Exception as e:
            log.debug(f"YouTube檢測失敗: {e}")
            return None
    
    async def check_netflix(self, session: aiohttp.ClientSession) -> bool:
        """
        檢測Netflix可用性
        學習Go版本的CheckNetflix實現
        
        Args:
            session: HTTP會話
            
        Returns:
            bool: 是否可用
        """
        try:
            # 檢測Netflix的登錄頁面
            async with session.get(
                "https://www.netflix.com/login",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # 檢查是否被重定向到地區不可用頁面
                    return "Not Available" not in text and "不可用" not in text
                return False
        except Exception as e:
            log.debug(f"Netflix檢測失敗: {e}")
            return False
    
    async def check_disney(self, session: aiohttp.ClientSession) -> bool:
        """
        檢測Disney+可用性
        學習Go版本的CheckDisney實現
        
        Args:
            session: HTTP會話
            
        Returns:
            bool: 是否可用
        """
        try:
            async with session.get(
                "https://www.disneyplus.com/",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # 檢查是否包含Disney+的內容
                    return "disney" in text.lower() and "unavailable" not in text.lower()
                return False
        except Exception as e:
            log.debug(f"Disney+檢測失敗: {e}")
            return False
    
    async def check_openai(self, session: aiohttp.ClientSession) -> Tuple[bool, bool]:
        """
        檢測OpenAI可用性
        學習Go版本的CheckOpenAI實現
        
        Args:
            session: HTTP會話
            
        Returns:
            Tuple[bool, bool]: (API可用性, Web可用性)
        """
        api_available = False
        web_available = False
        
        try:
            # 檢測API可用性
            async with session.get(
                "https://api.openai.com/v1/models",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # 即使沒有認證，API端點也應該返回401而不是其他錯誤
                if response.status in [401, 200]:
                    api_available = True
        except Exception as e:
            log.debug(f"OpenAI API檢測失敗: {e}")
        
        try:
            # 檢測Web可用性
            async with session.get(
                "https://chat.openai.com/",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    # 檢查是否包含ChatGPT的標識
                    web_available = "chatgpt" in text.lower() or "openai" in text.lower()
        except Exception as e:
            log.debug(f"OpenAI Web檢測失敗: {e}")
        
        return api_available, web_available
    
    async def check_gemini(self, session: aiohttp.ClientSession) -> bool:
        """
        檢測Gemini可用性
        學習Go版本的CheckGemini實現
        
        Args:
            session: HTTP會話
            
        Returns:
            bool: 是否可用
        """
        try:
            async with session.get(
                "https://gemini.google.com/",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    text = await response.text()
                    return "gemini" in text.lower() and "unavailable" not in text.lower()
                return False
        except Exception as e:
            log.debug(f"Gemini檢測失敗: {e}")
            return False
    
    async def check_tiktok(self, session: aiohttp.ClientSession) -> Optional[str]:
        """
        檢測TikTok可用性和地區
        學習Go版本的CheckTikTok實現
        
        Args:
            session: HTTP會話
            
        Returns:
            Optional[str]: 地區代碼，None表示不可用
        """
        try:
            async with session.get(
                "https://www.tiktok.com/",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    # 檢查重定向或地區信息
                    final_url = str(response.url)
                    region_match = re.search(r'tiktok\.com/([a-z]{2})', final_url)
                    if region_match:
                        return region_match.group(1).upper()
                    return "Unknown"
                return None
        except Exception as e:
            log.debug(f"TikTok檢測失敗: {e}")
            return None
    
    async def check_ip_info(self, session: aiohttp.ClientSession) -> Tuple[Optional[str], Optional[str]]:
        """
        獲取IP信息和地區
        學習Go版本的IP檢測實現
        
        Args:
            session: HTTP會話
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (IP地址, 國家/地區)
        """
        try:
            async with session.get(
                "http://ip-api.com/json/?fields=query,country",
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('query'), data.get('country')
                return None, None
        except Exception as e:
            log.debug(f"IP信息檢測失敗: {e}")
            return None, None
    
    async def run_all_checks(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """
        運行所有平台檢測
        學習Go版本的檢測流程
        
        Args:
            session: HTTP會話
            
        Returns:
            Dict[str, Any]: 檢測結果
        """
        results = {}
        
        # 基礎連通性檢測（必須通過）
        cloudflare_ok = await self.check_cloudflare(session)
        google_ok = await self.check_google(session)
        
        results['cloudflare'] = cloudflare_ok
        results['google'] = google_ok
        
        # 如果基礎檢測失敗，返回失敗結果
        if not (cloudflare_ok and google_ok):
            log.debug("基礎連通性檢測失敗，跳過其他檢測")
            return results
        
        # 獲取IP信息
        ip_address, country = await self.check_ip_info(session)
        results['ip_address'] = ip_address
        results['country'] = country
        
        # 並發執行其他檢測
        tasks = {
            'youtube': self.check_youtube(session),
            'netflix': self.check_netflix(session),
            'disney': self.check_disney(session),
            'gemini': self.check_gemini(session),
            'tiktok': self.check_tiktok(session),
        }
        
        # OpenAI檢測返回元組
        openai_task = self.check_openai(session)
        
        # 執行所有檢測
        completed_tasks = await asyncio.gather(*tasks.values(), openai_task, return_exceptions=True)
        
        # 處理結果
        task_names = list(tasks.keys())
        for i, result in enumerate(completed_tasks[:-1]):  # 除了最後的openai結果
            if isinstance(result, Exception):
                log.debug(f"{task_names[i]}檢測異常: {result}")
                results[task_names[i]] = None
            else:
                results[task_names[i]] = result
        
        # 處理OpenAI結果
        openai_result = completed_tasks[-1]
        if isinstance(openai_result, Exception):
            log.debug(f"OpenAI檢測異常: {openai_result}")
            results['openai_api'] = False
            results['openai_web'] = False
        else:
            results['openai_api'], results['openai_web'] = openai_result
        
        return results


async def create_platform_session(proxy_url: str, timeout: int = 10) -> aiohttp.ClientSession:
    """
    創建用於平台檢測的HTTP會話
    
    Args:
        proxy_url: 代理URL
        timeout: 超時時間
        
    Returns:
        aiohttp.ClientSession: HTTP會話
    """
    connector = aiohttp.TCPConnector(
        force_close=True,
        enable_cleanup_closed=True
    )
    
    timeout_config = aiohttp.ClientTimeout(total=timeout)
    
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout_config,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    )
    
    # 配置代理（這裡需要根據實際情況配置SOCKS5代理）
    # aiohttp目前不直接支持SOCKS5，可能需要使用aiohttp-socks
    
    return session
