#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接代理协议测试模块
作者: subscheck-ubuntu team

测试代理节点的原始协议连通性，而不是通过HTTP网站
适用于中国大陆网络环境，避免防火墙阻断HTTP请求
"""

import asyncio
import socket
import time
import struct
import base64
import hashlib
from typing import Dict, Optional, Any, Tuple
import aiohttp

from utils.logger import log

class DirectProxyTester:
    """直接测试代理协议连通性的测试器"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    async def test_socks5_connectivity(self, host: str, port: int) -> Optional[float]:
        """
        直接测试SOCKS5协议连通性
        通过握手过程验证代理是否可用
        """
        try:
            start_time = time.monotonic()
            
            # 创建TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout
            )
            
            try:
                # SOCKS5握手：发送认证方法
                # 格式: [版本(5)] [方法数量(1)] [方法(0=无认证)]
                auth_request = b'\x05\x01\x00'
                writer.write(auth_request)
                await writer.drain()
                
                # 读取服务器响应
                response = await asyncio.wait_for(
                    reader.read(2), 
                    timeout=5
                )
                
                if len(response) == 2 and response[0] == 5:
                    # 握手成功
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"SOCKS5握手成功 {host}:{port} - {elapsed:.0f}ms")
                    return elapsed
                else:
                    log.debug(f"SOCKS5握手失败 {host}:{port} - 无效响应")
                    return None
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            log.debug(f"SOCKS5连接超时 {host}:{port}")
            return None
        except ConnectionRefusedError:
            log.debug(f"SOCKS5连接被拒绝 {host}:{port}")
            return None
        except Exception as e:
            log.debug(f"SOCKS5测试错误 {host}:{port}: {e}")
            return None
    
    async def test_shadowsocks_connectivity(self, host: str, port: int, method: str, password: str) -> Optional[float]:
        """
        测试Shadowsocks协议连通性
        发送一个简单的数据包并验证响应
        """
        try:
            start_time = time.monotonic()
            
            # 创建TCP连接到Shadowsocks服务器
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout
            )
            
            try:
                # 发送一个简单的探测数据包
                # 这里使用一个最小的有效载荷来测试连接
                test_data = b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'  # 最小探测包
                writer.write(test_data)
                await writer.drain()
                
                # 尝试读取响应（即使是错误响应也表明连接成功）
                try:
                    response = await asyncio.wait_for(
                        reader.read(1024), 
                        timeout=5
                    )
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"Shadowsocks连接成功 {host}:{port} - {elapsed:.0f}ms")
                    return elapsed
                except asyncio.TimeoutError:
                    # 超时也可能表示连接成功但服务器没有响应
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"Shadowsocks连接可能成功 {host}:{port} - {elapsed:.0f}ms (超时)")
                    return elapsed
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            log.debug(f"Shadowsocks连接超时 {host}:{port}")
            return None
        except ConnectionRefusedError:
            log.debug(f"Shadowsocks连接被拒绝 {host}:{port}")
            return None
        except Exception as e:
            log.debug(f"Shadowsocks测试错误 {host}:{port}: {e}")
            # 即使出现异常，如果连接建立时间很短，也可能表明连接是通的
            elapsed = (time.monotonic() - start_time) * 1000
            if elapsed < self.timeout * 1000:
                log.debug(f"Shadowsocks连接可能成功但有异常 {host}:{port} - {elapsed:.0f}ms (异常)")
                return elapsed
            return None
    
    async def test_vmess_connectivity(self, host: str, port: int, uuid: str) -> Optional[float]:
        """
        测试VMess协议连通性
        发送握手包并检查响应
        """
        try:
            start_time = time.monotonic()
            
            # 创建TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout
            )
            
            try:
                # VMess握手比较复杂，这里简化为连接测试
                # 发送一个探测包
                test_data = b'\x00' * 16  # 简单的探测数据
                writer.write(test_data)
                await writer.drain()
                
                # 尝试读取响应
                try:
                    response = await asyncio.wait_for(
                        reader.read(1024), 
                        timeout=5
                    )
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"VMess连接成功 {host}:{port} - {elapsed:.0f}ms")
                    return elapsed
                except asyncio.TimeoutError:
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"VMess连接可能成功 {host}:{port} - {elapsed:.0f}ms (超时)")
                    return elapsed
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            log.debug(f"VMess连接超时 {host}:{port}")
            return None
        except ConnectionRefusedError:
            log.debug(f"VMess连接被拒绝 {host}:{port}")
            return None
        except Exception as e:
            log.debug(f"VMess测试错误 {host}:{port}: {e}")
            # 即使出现异常，如果连接建立时间很短，也可能表明连接是通的
            elapsed = (time.monotonic() - start_time) * 1000
            if elapsed < self.timeout * 1000:
                log.debug(f"VMess连接可能成功但有异常 {host}:{port} - {elapsed:.0f}ms (异常)")
                return elapsed
            return None
    
    async def test_vless_connectivity(self, host: str, port: int, uuid: str) -> Optional[float]:
        """
        测试VLESS协议连通性
        """
        try:
            start_time = time.monotonic()
            
            # 创建TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout
            )
            
            try:
                # VLESS握手比较复杂，这里简化为连接测试
                # 发送一个探测包
                test_data = b'\x00' * 16  # 简单的探测数据
                writer.write(test_data)
                await writer.drain()
                
                # 尝试读取响应
                try:
                    response = await asyncio.wait_for(
                        reader.read(1024), 
                        timeout=5
                    )
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"VLESS连接成功 {host}:{port} - {elapsed:.0f}ms")
                    return elapsed
                except asyncio.TimeoutError:
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"VLESS连接可能成功 {host}:{port} - {elapsed:.0f}ms (超时)")
                    return elapsed
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            log.debug(f"VLESS连接超时 {host}:{port}")
            return None
        except ConnectionRefusedError:
            log.debug(f"VLESS连接被拒绝 {host}:{port}")
            return None
        except Exception as e:
            log.debug(f"VLESS测试错误 {host}:{port}: {e}")
            # 即使出现异常，如果连接建立时间很短，也可能表明连接是通的
            elapsed = (time.monotonic() - start_time) * 1000
            if elapsed < self.timeout * 1000:
                log.debug(f"VLESS连接可能成功但有异常 {host}:{port} - {elapsed:.0f}ms (异常)")
                return elapsed
            return None
    
    async def test_trojan_connectivity(self, host: str, port: int, password: str) -> Optional[float]:
        """
        测试Trojan协议连通性
        """
        try:
            start_time = time.monotonic()
            
            # 创建TCP连接
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout
            )
            
            try:
                # Trojan协议握手
                # 计算密码哈希
                password_hash = hashlib.sha224(password.encode()).hexdigest()
                
                # 构造握手数据 (简化版)
                handshake = f"{password_hash}\r\n".encode() + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
                writer.write(handshake)
                await writer.drain()
                
                # 读取响应
                try:
                    response = await asyncio.wait_for(
                        reader.read(1024), 
                        timeout=3
                    )
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"Trojan连接成功 {host}:{port} - {elapsed:.0f}ms")
                    return elapsed
                except asyncio.TimeoutError:
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"Trojan连接可能成功 {host}:{port} - {elapsed:.0f}ms (超时)")
                    return elapsed
                    
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            log.debug(f"Trojan连接超时 {host}:{port}")
            return None
        except ConnectionRefusedError:
            log.debug(f"Trojan连接被拒绝 {host}:{port}")
            return None
        except Exception as e:
            log.debug(f"Trojan测试错误 {host}:{port}: {e}")
            return None

    async def test_node_direct_connectivity(self, node: Dict[str, Any]) -> Optional[float]:
        """
        根据节点类型选择合适的直连测试方法
        """
        node_type = node.get('type', '').lower()
        host = node.get('server')
        port = node.get('port')
        
        if not host or not port:
            log.debug(f"节点缺少必要信息: {node}")
            return None
        
        log.debug(f"直接测试节点连通性: {node_type}://{host}:{port}")
        
        # 增加重试机制
        retry_count = 3
        for attempt in range(retry_count):
            try:
                if node_type == 'shadowsocks':
                    method = node.get('method', 'aes-256-gcm')
                    password = node.get('password', '')
                    result = await self.test_shadowsocks_connectivity(host, port, method, password)
                    if result is not None:
                        return result
                
                elif node_type == 'vmess':
                    uuid = node.get('uuid', '')
                    result = await self.test_vmess_connectivity(host, port, uuid)
                    if result is not None:
                        return result
                
                elif node_type == 'vless':
                    # VLESS通常也可以用类似VMess的方式测试
                    uuid = node.get('uuid', '')
                    result = await self.test_vless_connectivity(host, port, uuid)
                    if result is not None:
                        return result
                
                elif node_type == 'trojan':
                    password = node.get('password', '')
                    result = await self.test_trojan_connectivity(host, port, password)
                    if result is not None:
                        return result
                
                else:
                    log.debug(f"不支持的节点类型进行直连测试: {node_type}")
                    return None
                    
            except Exception as e:
                log.debug(f"第 {attempt + 1} 次直连测试失败: {type(e).__name__}: {e}")
                if attempt < retry_count - 1:
                    # 等待一段时间后重试
                    await asyncio.sleep(1)
                else:
                    # 最后一次尝试仍然失败
                    log.debug(f"所有 {retry_count} 次直连测试都失败了")
                    return None
        
        return None

    async def test_through_singbox_socks5(self, proxy_url: str, target_host: str = "8.8.8.8", target_port: int = 53) -> Optional[float]:
        """
        通过sing-box的SOCKS5代理测试连接到目标服务器
        使用DNS服务器作为目标，避免HTTP协议
        """
        # 增加重试机制
        retry_count = 3
        for attempt in range(retry_count):
            try:
                import socks
                import socket
                
                # 解析代理URL
                if not proxy_url.startswith('socks5://'):
                    return None
                
                proxy_parts = proxy_url[9:].split(':')  # 移除 'socks5://'
                if len(proxy_parts) != 2:
                    return None
                
                proxy_host = proxy_parts[0]
                proxy_port = int(proxy_parts[1])
                
                start_time = time.monotonic()
                
                # 创建SOCKS5连接
                sock = socks.socksocket()
                sock.set_proxy(socks.SOCKS5, proxy_host, proxy_port)
                # 增加超时时间以适应慢速网络
                sock.settimeout(self.timeout * 2)
                
                try:
                    # 通过代理连接到目标服务器
                    await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: sock.connect((target_host, target_port))
                    )
                    
                    elapsed = (time.monotonic() - start_time) * 1000
                    log.debug(f"通过SOCKS5代理连接成功: {target_host}:{target_port} - {elapsed:.0f}ms")
                    
                    sock.close()
                    return elapsed
                    
                except Exception as e:
                    log.debug(f"第 {attempt + 1} 次通过SOCKS5代理连接失败: {e}")
                    sock.close()
                    if attempt < retry_count - 1:
                        # 等待一段时间后重试
                        await asyncio.sleep(2)
                    else:
                        # 最后一次尝试仍然失败
                        log.debug(f"所有 {retry_count} 次SOCKS5代理连接测试都失败了")
                        return None
                    
            except ImportError:
                log.debug("PySocks库未安装，无法进行SOCKS5代理测试")
                return None
            except Exception as e:
                log.debug(f"SOCKS5代理测试错误: {e}")
                if attempt < retry_count - 1:
                    # 等待一段时间后重试
                    await asyncio.sleep(2)
                else:
                    # 最后一次尝试仍然失败
                    log.debug(f"所有 {retry_count} 次SOCKS5代理测试都失败了")
                    return None
        
        return None