中文 | [English](README-en.md)
# SubsCheck-Ubuntu 使用指南

## 🚀 项目概述

SubsCheck-Ubuntu 是一个基于 Sing-box 的高性能代理节点测速工具，适用于 Ubuntu VPS 环境，也支持本地开发。

### ✨ 核心功能

- **多协议支持**: 支持 VLESS, VMess, Trojan, Shadowsocks 等主流协议的解析。
- **高性能测速**: 基于 `sing-box` 核心，提供准确的 HTTP 延迟和真实下载速度测试。
- **结果自动化**:
    - **上传测试结果**: 可将详细的 JSON 格式测试结果上传到 Gist, WebDAV, 或通过 Webhook 发送。
    - **备份可用节点**: 可将所有测试成功的节点生成一个新的订阅文件，并上传到 Gist 或 WebDAV，方便客户端直接使用。
- **定时任务**: 支持通过 `cron` 或内置调度器实现每日自动测速和上传。
- **环境安全**: 支持通过 `.env` 文件管理敏感信息，避免密码等硬编码在配置文件中。

## 🛠️ 使用方式

### 本地开发 (推荐使用 uv)

```bash
# 1. 安装依赖 (uv 会自动创建虚拟环境)
uv pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 Gist, WebDAV 等服务的凭据

# 3. 配置 config.yaml
# 根据你的需求，启用并配置 upload_settings 和 subscription_backup

# 4. 运行程序
uv run python main.py

# 5. 指定参数运行
uv run python main.py -s my_subscription.txt -n 20

# 6. 启用 debug 模式
uv run python main.py -d
```

### 远程 VPS 部署

```bash
# 1. 一键安装和配置
chmod +x install.sh
./install.sh

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 3. 运行程序
./run.sh

# 或手动运行
source .venv/bin/activate
python main.py
```

## ⚙️ 配置文件

### `.env` (环境变量)

用于存放所有敏感信息，例如 API tokens 和密码。

```env
# Gist Configuration
GIST_TOKEN="your_github_token"
GIST_ID="your_gist_id"

# WebDAV Configuration for Result Uploads
WEBDAV_HOSTNAME="https://your.webdav.host/dav/"
WEBDAV_USERNAME="your_username"
WEBDAV_PASSWORD="your_password"

# WebDAV Configuration for Subscription Backup
WEBDAV_BACKUP_HOSTNAME="https://your.webdav.host/dav/"
WEBDAV_BACKUP_USERNAME="your_username"
WEBDAV_BACKUP_PASSWORD="your_password"
```

### `config.yaml` (主要配置)

在此文件中配置程序的行为，例如测速参数、上传目标等。所有敏感信息都应使用 `${VAR_NAME}` 的形式从 `.env` 文件中引用。

```yaml
# 结果上传设置
upload_settings:
  enabled: false
  type: "webdav"  # 可选: local, gist, webhook, webdav, r2
  
  webdav:
    enabled: true
    hostname: "${WEBDAV_HOSTNAME}"
    username: "${WEBDAV_USERNAME}"
    password: "${WEBDAV_PASSWORD}"
    remote_path: "subscheck_results.json"

# 订阅备份设置
subscription_backup:
  enabled: false
  
  gist:
    enabled: false
    token: "${GIST_TOKEN}"
    gist_id: "${GIST_ID}"
    filename: "subscheck_backup.txt"
```

### `subscription.txt` (订阅源)

在此文件中添加您的订阅链接，一行一个。

```
https://example.com/subscription1
https://example.com/subscription2
```

## 📦 项目结构

```
subscheck-ubuntu/
├── core/
│   └── singbox_runner.py       # sing-box 核心接口
├── parsers/
│   └── ...                     # 协议解析器
├── testers/
│   └── node_tester.py          # 节点测试逻辑
├── utils/
│   ├── config_utils.py         # 环境变量解析
│   ├── uploader.py             # 结果上传模块
│   └── subscription_backup.py  # 订阅备份模块
├── .env                        # 环境变量 (私密)
├── .env.example                # 环境变量示例
├── config.yaml                 # 核心配置
├── main.py                     # 主程序入口
├── requirements.txt            # 依赖列表
└── install.sh                  # VPS 自动安装脚本
```

