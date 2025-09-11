# SubCheck 问题诊断与解决方案

## 📋 问题分析

根据你提供的日志文件 `debug/app_20250911_202000.log`，我发现了以下主要问题：

### 1. 🌐 网络连接问题
```
Failed to fetch https://gcore.jsdelivr.net/gh/linzjian666/chromego_extractor@main/outputs/base64.txt: Cannot connect to host gcore.jsdelivr.net:443 ssl:default [getaddrinfo failed]
```

**问题原因：**
- DNS解析失败 (`getaddrinfo failed`)
- 可能的网络环境限制
- 某些GitHub相关的CDN域名访问受限

### 2. 🔗 协议支持不足
```
Unsupported protocol for URL: ss://...
Unsupported protocol for URL: ssr://...
Unsupported protocol for URL: hysteria2://...
```

**问题原因：**
- 原代码只支持 vmess、vless、trojan
- 缺少 Shadowsocks (ss://) 支持
- ShadowsocksR (ssr://) 和 Hysteria2 不被 Xray 核心支持

## 🛠️ 已实施的解决方案

### 1. ✅ 扩展协议解析器

**文件：** `parsers/base_parser.py`

- ✅ 添加了 Shadowsocks (ss://) 协议支持
- ✅ 添加了 ShadowsocksR (ssr://) 解析（但会跳过，因为 Xray 不支持）
- ✅ 改进了错误处理和日志记录

### 2. ✅ 更新 Xray 配置生成器

**文件：** `core/xray_runner.py`

- ✅ 添加了 Shadowsocks 协议的 Xray 配置生成
- ✅ 添加了对 ShadowsocksR 的检测和警告
- ✅ 改进了 Windows 下的 Xray 可执行文件路径处理

### 3. ✅ 配置文件优化

**文件：** `config.yaml`

- ✅ 修正了测试URL的配置格式
- ✅ 分离了延迟测试和速度测试的URL列表

### 4. ✅ 创建调试工具

**新文件：**
- `run_debug.py` - Windows 调试专用运行脚本
- `network_test.py` - 网络连接诊断工具
- `subscription_debug.txt` - 简化的测试订阅列表

## 🚀 使用方法

### 步骤 1: 网络连接测试
```bash
python network_test.py
```
这将帮助诊断：
- DNS解析是否正常
- HTTP连接是否可用
- 订阅URL是否可访问
- 代理端口是否可用

### 步骤 2: 调试模式运行
```bash
python run_debug.py
```
这将：
- 使用简化的订阅列表
- 限制测试节点数量（5个）
- 降低并发数（2个）
- 提供详细的错误信息

### 步骤 3: 正常模式运行
```bash
python main.py
```
当调试模式工作正常后，使用完整的订阅列表进行测试。

## 🔧 故障排除

### 问题 1: DNS解析失败
**症状：** `getaddrinfo failed` 错误

**解决方案：**
1. 检查网络连接
2. 尝试更换DNS服务器（如 8.8.8.8, 1.1.1.1）
3. 使用VPN或代理

### 问题 2: Xray进程启动失败
**症状：** `Xray failed to start` 错误

**解决方案：**
1. 确保 `Xray-windows-64/xray.exe` 存在
2. 检查防火墙设置
3. 确保端口 10800-10820 可用

### 问题 3: 大量协议不支持
**症状：** 很多 `Unsupported protocol` 警告

**解决方案：**
- 这是正常的，因为Xray不支持所有协议
- 重点关注支持的协议：vmess, vless, trojan, shadowsocks
- ShadowsocksR和Hysteria2需要专门的客户端

## 📊 支持的协议

| 协议 | 支持状态 | 说明 |
|------|---------|------|
| VMess | ✅ 完全支持 | V2Ray原生协议 |
| VLESS | ✅ 完全支持 | 轻量级协议 |
| Trojan | ✅ 完全支持 | 伪装HTTPS |
| Shadowsocks | ✅ 新增支持 | 经典代理协议 |
| ShadowsocksR | ❌ 不支持 | Xray不支持此协议 |
| Hysteria2 | ❌ 不支持 | 需要专门客户端 |

## 🎯 下一步建议

1. **先运行网络测试**：确保基本连接正常
2. **使用调试模式**：验证代码逻辑是否正确
3. **逐步扩大测试范围**：从少量节点开始
4. **监控日志文件**：关注 `debug/` 目录下的日志
5. **优化订阅源**：移除不可访问的订阅链接

## 📝 注意事项

- Windows 下需要确保 Xray 可执行文件正确放置
- 某些订阅源可能需要代理才能访问
- 大量节点测试可能需要较长时间
- 建议在稳定的网络环境下进行测试