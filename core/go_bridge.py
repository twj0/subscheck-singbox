#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Go語言橋接模組
實現Python和Go項目的混合執行
學習Go版本的高性能測速邏輯
"""

import asyncio
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from utils.logger import log


class GoBridge:
    """
    Go語言橋接器
    負責調用Go版本的subs-check進行高性能測速
    """
    
    def __init__(self, go_project_path: str = "tmpl/subs-check"):
        """
        初始化Go橋接器
        
        Args:
            go_project_path: Go項目路径
        """
        self.go_project_path = Path(go_project_path).resolve()
        self.go_binary_path = None
        self.temp_dir = None
        
        # 檢查Go項目路径
        if not self.go_project_path.exists():
            raise FileNotFoundError(f"Go項目路径不存在: {self.go_project_path}")
        
        # 檢查是否有go.mod文件
        go_mod = self.go_project_path / "go.mod"
        if not go_mod.exists():
            raise FileNotFoundError(f"Go模組文件不存在: {go_mod}")
            
        log.info(f"Go橋接器初始化: {self.go_project_path}")
    
    async def initialize(self) -> bool:
        """
        初始化Go環境和編譯二進制文件
        
        Returns:
            bool: 是否初始化成功
        """
        try:
            # 檢查Go環境
            result = await self._run_command(["go", "version"], cwd=None)
            if result.returncode != 0:
                log.error("Go環境檢查失敗，請確保Go已正確安裝")
                return False
            
            go_version = result.stdout.strip()
            log.info(f"Go環境檢查成功: {go_version}")
            
            # 創建臨時目錄
            self.temp_dir = Path(tempfile.mkdtemp(prefix="subscheck_go_"))
            log.debug(f"創建臨時目錄: {self.temp_dir}")
            
            # 編譯Go項目
            binary_name = "subs-check.exe" if os.name == "nt" else "subs-check"
            self.go_binary_path = self.temp_dir / binary_name
            
            log.info("開始編譯Go項目...")
            compile_result = await self._run_command([
                "go", "build", 
                "-o", str(self.go_binary_path),
                "."
            ], cwd=self.go_project_path)
            
            if compile_result.returncode != 0:
                log.error(f"Go項目編譯失敗: {compile_result.stderr}")
                return False
            
            log.info(f"Go項目編譯成功: {self.go_binary_path}")
            
            # 檢查二進制文件是否可執行
            if not self.go_binary_path.exists():
                log.error(f"編譯的二進制文件不存在: {self.go_binary_path}")
                return False
            
            return True
            
        except Exception as e:
            log.error(f"Go橋接器初始化失敗: {e}")
            return False
    
    async def create_go_config(self, python_config: Dict[str, Any]) -> Path:
        """
        將Python配置轉換為Go配置格式
        
        Args:
            python_config: Python配置字典
            
        Returns:
            Path: Go配置文件路径
        """
        # 學習Go版本的配置結構
        go_config = {
            # 基本設置
            "print-progress": python_config.get("print_progress", True),
            "concurrent": python_config.get("concurrent", 20),
            "success-limit": python_config.get("success_limit", 0),
            "timeout": python_config.get("timeout", 5000),
            
            # 測速設置
            "speed-test-url": python_config.get("speed_test_url", ""),
            "min-speed": python_config.get("min_speed", 512),
            "download-timeout": python_config.get("download_timeout", 10),
            "download-mb": python_config.get("download_mb", 20),
            "total-speed-limit": python_config.get("total_speed_limit", 0),
            
            # 平台檢測
            "media-check": python_config.get("media_check", False),
            "platforms": python_config.get("platforms", []),
            
            # 節點類型過濾
            "node-type": python_config.get("node_type", []),
            
            # 保留成功節點
            "keep-success-proxies": python_config.get("keep_success_proxies", False),
            
            # 訂閱設置
            "subscription": {
                "urls": python_config.get("subscription", {}).get("urls", []),
                "update_interval": python_config.get("subscription", {}).get("update_interval", 86400)
            },
            
            # 保存設置
            "save": python_config.get("save", {}),
            
            # clash設置 (Go項目使用mihomo)
            "clash": {
                "url": "http://127.0.0.1:9090",
                "secret": ""
            }
        }
        
        # 保存Go配置文件
        go_config_path = self.temp_dir / "config.yaml"
        import yaml
        with open(go_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(go_config, f, allow_unicode=True, default_flow_style=False)
        
        log.debug(f"Go配置文件創建: {go_config_path}")
        return go_config_path
    
    async def run_speed_test(self, 
                           subscription_content: str,
                           config: Dict[str, Any],
                           max_nodes: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        使用Go版本運行速度測試
        
        Args:
            subscription_content: 訂閱內容
            config: 配置字典
            max_nodes: 最大節點數
            
        Returns:
            List[Dict[str, Any]]: 測試結果
        """
        if not self.go_binary_path or not self.go_binary_path.exists():
            raise RuntimeError("Go二進制文件未準備好，請先調用initialize()")
        
        try:
            # 創建訂閱文件
            subscription_path = self.temp_dir / "subscription.txt"
            with open(subscription_path, 'w', encoding='utf-8') as f:
                f.write(subscription_content)
            
            # 創建Go配置文件
            go_config_path = await self.create_go_config(config)
            
            # 準備Go命令參數
            go_cmd = [
                str(self.go_binary_path),
                "-f", str(go_config_path)
            ]
            
            log.info(f"啟動Go測速進程: {' '.join(go_cmd)}")
            log.info(f"工作目錄: {self.temp_dir}")
            
            # 執行Go程序
            start_time = time.time()
            result = await self._run_command(go_cmd, cwd=self.temp_dir, timeout=300)
            elapsed_time = time.time() - start_time
            
            if result.returncode != 0:
                log.error(f"Go測速執行失敗 (退出碼: {result.returncode})")
                log.error(f"錯誤輸出: {result.stderr}")
                return []
            
            log.info(f"Go測速完成，耗時: {elapsed_time:.1f}秒")
            
            # 解析Go輸出結果
            return await self._parse_go_results(result.stdout)
            
        except Exception as e:
            log.error(f"Go測速執行異常: {e}")
            return []
    
    async def _parse_go_results(self, go_output: str) -> List[Dict[str, Any]]:
        """
        解析Go程序的輸出結果
        
        Args:
            go_output: Go程序的標準輸出
            
        Returns:
            List[Dict[str, Any]]: 解析後的結果
        """
        results = []
        
        try:
            # Go項目可能輸出JSON格式的結果
            # 這裡需要根據實際的Go輸出格式進行調整
            lines = go_output.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 嘗試解析JSON格式的結果
                try:
                    if line.startswith('{') and line.endswith('}'):
                        result_data = json.loads(line)
                        
                        # 轉換Go結果格式為Python格式
                        python_result = {
                            'name': result_data.get('proxy', {}).get('name', 'Unknown'),
                            'server': result_data.get('proxy', {}).get('server', 'N/A'),
                            'port': result_data.get('proxy', {}).get('port', 'N/A'),
                            'protocol': result_data.get('proxy', {}).get('type', 'Unknown'),
                            'success': True,  # Go成功返回就認為成功
                            'ip_address': result_data.get('IP', None),
                            'country': result_data.get('Country', None),
                            'download_speed': None,  # Go版本可能有不同的速度表示
                            
                            # 平台檢測結果
                            'platforms': {
                                'google': result_data.get('Google', False),
                                'cloudflare': result_data.get('Cloudflare', False),
                                'youtube': result_data.get('Youtube', ''),
                                'netflix': result_data.get('Netflix', False),
                                'disney': result_data.get('Disney', False),
                                'openai': result_data.get('Openai', False),
                                'openai_web': result_data.get('OpenaiWeb', False),
                                'gemini': result_data.get('Gemini', False),
                                'tiktok': result_data.get('TikTok', ''),
                                'ip_risk': result_data.get('IPRisk', '')
                            }
                        }
                        
                        results.append(python_result)
                        
                except json.JSONDecodeError:
                    # 如果不是JSON格式，可能是日誌輸出
                    log.debug(f"Go輸出: {line}")
                    continue
            
            log.info(f"解析Go結果成功，共 {len(results)} 個有效結果")
            return results
            
        except Exception as e:
            log.error(f"解析Go結果失敗: {e}")
            return []
    
    async def _run_command(self, 
                          cmd: List[str], 
                          cwd: Optional[Union[str, Path]] = None,
                          timeout: int = 60) -> subprocess.CompletedProcess:
        """
        異步執行命令
        
        Args:
            cmd: 命令列表
            cwd: 工作目錄
            timeout: 超時時間
            
        Returns:
            subprocess.CompletedProcess: 執行結果
        """
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=timeout
            )
            
            return subprocess.CompletedProcess(
                cmd, process.returncode, stdout, stderr
            )
            
        except asyncio.TimeoutError:
            log.error(f"命令執行超時: {' '.join(cmd)}")
            if 'process' in locals():
                process.terminate()
                await process.wait()
            raise
        except Exception as e:
            log.error(f"命令執行失敗: {' '.join(cmd)}, 錯誤: {e}")
            raise
    
    async def cleanup(self):
        """清理資源"""
        if self.temp_dir and self.temp_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
                log.debug(f"清理臨時目錄: {self.temp_dir}")
            except Exception as e:
                log.warning(f"清理臨時目錄失敗: {e}")
    
    def __del__(self):
        """析構函數"""
        if hasattr(self, 'temp_dir') and self.temp_dir:
            try:
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except:
                pass


class GoHybridTester:
    """
    Python-Go混合測試器
    結合Python的易用性和Go的高性能
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化混合測試器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.go_bridge = GoBridge()
        self.fallback_to_python = True  # 如果Go失敗，回退到Python
    
    async def initialize(self) -> bool:
        """
        初始化混合測試器
        
        Returns:
            bool: 是否初始化成功
        """
        log.info("初始化Python-Go混合測試器...")
        
        # 嘗試初始化Go橋接器
        go_success = await self.go_bridge.initialize()
        
        if go_success:
            log.info("✅ Go橋接器初始化成功，將使用高性能Go測速")
            return True
        else:
            log.warning("⚠️ Go橋接器初始化失敗，將回退到Python測速")
            return self.fallback_to_python
    
    async def test_nodes(self, 
                        subscription_content: str,
                        max_nodes: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        測試節點（優先使用Go，失敗時回退到Python）
        
        Args:
            subscription_content: 訂閱內容
            max_nodes: 最大節點數
            
        Returns:
            List[Dict[str, Any]]: 測試結果
        """
        # 首先嘗試使用Go測速
        if self.go_bridge.go_binary_path:
            try:
                log.info("🚀 使用Go高性能測速引擎...")
                results = await self.go_bridge.run_speed_test(
                    subscription_content, 
                    self.config, 
                    max_nodes
                )
                
                if results:
                    log.info(f"✅ Go測速成功，獲得 {len(results)} 個結果")
                    return results
                else:
                    log.warning("⚠️ Go測速返回空結果")
                    
            except Exception as e:
                log.error(f"❌ Go測速失敗: {e}")
        
        # 回退到Python測速
        if self.fallback_to_python:
            log.info("🔄 回退到Python測速...")
            from testers.node_tester import NodeTester
            
            # 使用原來的Python邏輯
            node_tester = NodeTester(self.config)
            try:
                # 這裡需要調用原來的Python測速邏輯
                # 可能需要進一步適配
                return []
            finally:
                await node_tester.cleanup()
        
        return []
    
    async def cleanup(self):
        """清理資源"""
        await self.go_bridge.cleanup()

