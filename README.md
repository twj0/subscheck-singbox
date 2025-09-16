# SubsCheck-Singbox v3.0

🚀 **Python+Go混合架构的高性能代理节点测速工具**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Go](https://img.shields.io/badge/Go-1.21+-00ADD8.svg)](https://golang.org/)


## ✨ 特色功能

### 🐍 Python层 (智能订阅解析)
- ✅ **多格式订阅支持**：base64、plain text、嵌套订阅、YAML、JSON
- ✅ **多协议支持**：ss://, vmess://, vless://, trojan://, hysteria://, tuic://
- ✅ **智能去重**：自动去除重复节点，提高测试效率
- ✅ **数量控制**：智能限制测试节点数量，避免超时
- ✅ **临时HTTP服务器**：解决Go程序文件读取问题

### ⚡ Go核心 (原生协议测速)
- ✅ **原生协议测速**：每个节点使用其原生协议测试，结果更准确
- ✅ **高性能并发**：10个并发线程高效测速，支持自定义并发数
- ✅ **实时进度显示**：清晰的进度条和状态，实时掌握测试进度
- ✅ **资源管理**：自动清理临时文件和服务器，避免资源泄漏
- ✅ **跨GFW测试**：真实的翻墙环境速度测试，结果更可靠

### 🌐 流媒体检测
- ✅ **多平台支持**：YouTube、Netflix、OpenAI、Disney+、Gemini、TikTok
- ✅ **IP风险检测**：检测代理IP的风险等级和地理位置
- ✅ **区域解锁检测**：检测不同流媒体平台的解锁区域

### 💾 多种结果保存方式
- ✅ **本地保存**：保存到本地文件，支持YAML、Base64等多种格式
- ✅ **GitHub Gist**：保存到GitHub Gist，方便分享和同步
- ✅ **WebDAV**：保存到WebDAV服务器，支持私有云存储
- ✅ **S3/MinIO**：保存到S3/MinIO对象存储，支持大规模部署
- ✅ **Cloudflare R2**：保存到Cloudflare R2，全球CDN加速

## 🏗️ 项目结构

```
SubsCheck-Singbox v3.0/
├── 🐍 Python层
│   ├── main.py              # 主程序入口，混合架构控制
│   ├── config.yaml          # 配置文件
│   ├── requirements.txt     # Python依赖
│   ├── .env.example         # 环境变量模板
│   ├── parsers/             # 订阅解析器
│   ├── testers/             # 测速器
│   ├── core/                # 核心功能
│   └── utils/               # 工具函数
│
├── ⚡ Go核心
│   ├── main.go              # Go程序入口
│   ├── go.mod/go.sum        # Go模块管理
│   ├── app/                 # 应用逻辑
│   ├── check/               # 测速和检测
│   ├── proxy/               # 代理处理
│   ├── save/                # 结果保存
│   └── utils/               # Go工具函数
│
└── 📁 其他
    ├── build/               # 编译输出
    ├── install.sh           # Linux/Unix安装脚本
    ├── install_windows.bat  # Windows安装脚本
    ├── python_legacy/       # 旧版Python代码
    └── config.example.yaml  # 配置示例
```

## 🚀 快速开始

### 方法一：自动安装脚本 (推荐)

#### Ubuntu/Debian 系统
```bash
# 下载并运行安装脚本
curl -fsSL https://raw.githubusercontent.com/your-repo/subscheck-singbox/main/install.sh | bash

# 或者手动下载
wget https://raw.githubusercontent.com/your-repo/subscheck-singbox/main/install.sh
chmod +x install.sh
./install.sh
```

#### CentOS/RHEL 系统
```bash
# 下载并运行安装脚本
curl -fsSL https://raw.githubusercontent.com/your-repo/subscheck-singbox/main/install.sh | bash

# 或者手动下载
wget https://raw.githubusercontent.com/your-repo/subscheck-singbox/main/install.sh
chmod +x install.sh
./install.sh
```

#### Windows 系统
```powershell
# 使用 PowerShell 运行安装脚本
irm https://raw.githubusercontent.com/your-repo/subscheck-singbox/main/install_windows.bat | iex

# 或者手动下载后运行
# 下载 install_windows.bat 并双击运行
```

### 方法二：手动安装

#### 1. 环境要求
- Python 3.8+
- Go 1.21+
- Git

#### 2. 克隆项目
```bash
git clone https://github.com/your-repo/subscheck-singbox.git
cd subscheck-singbox
```

#### 3. 安装依赖
```bash
# 安装 uv Python 包管理器
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装 Python 依赖
uv sync

# 编译 Go 程序
go mod download
go build -o build/subscheck main.go
```

#### 4. 配置设置
```bash
# 创建配置文件
cp config.example.yaml config.yaml

# 创建环境变量文件 (可选)
cp env.example .env

# 编辑配置文件，添加您的订阅链接
nano config.yaml
```

### 🎯 运行测速

```bash
# 基本测速
uv run main.py

# 仅编译Go核心
uv run main.py --compile-only

# 调试模式
DEBUG=1 uv run main.py

# 指定配置文件
uv run main.py -c custom_config.yaml

# 指定订阅文件
uv run main.py -s subscription.txt

# 查看帮助
uv run main.py --help
```

## 🔄 工作流程

```
1. Python解析订阅 → 2. 创建临时HTTP服务器 → 3. Go程序获取节点 → 4. Go高性能测速 → 5. Python展示结果
```

## 📊 输出示例

```
================================================================================
🎯 SubsCheck-Singbox v3.0 Python+Go混合测速结果
================================================================================
📊 节点统计:
   └─ Python解析节点: 5,252
   └─ 实际测试节点: 100

⚡ Go核心测速统计:
   └─ Go接收节点: 100
   └─ 去重后节点: 99
   └─ 可用节点: 15
   └─ 消耗流量: 0.156 GB

✅ 成功节点详情 (15个):
--------------------------------------------------------------------------------
 1. 🚀 [vmess] 美国-洛杉矶
    📍 104.21.45.78:443
    ⏱️  延迟: 234ms | 🚀 速度: 45.67 Mbps

 2. ⚡ [vless] 日本-东京
    📍 172.67.182.45:8080
    ⏱️  延迟: 156ms | 🚀 速度: 78.23 Mbps

📈 测试结果:
   └─ 成功率: 15.2% (15/99)
   └─ 平均速度: 52.45 Mbps
   └─ 平均延迟: 198ms

🔧 版本信息:
   └─ Python桥接: v3.0 (智能订阅解析)
   └─ Go核心: v3.0 (原生协议测速)
================================================================================
```

## 🌐 部署方案

### Windows 本地测试
```bash
uv run main.py
```

### Ubuntu VPS 定时测速
```bash
# 克隆项目
git clone https://github.com/your-repo/subscheck-singbox
cd subscheck-singbox

# 运行安装脚本
./install.sh

# 设置定时任务
crontab -e
# 添加: 0 */6 * * * cd /path/to/subscheck-singbox && uv run main.py
```

### Docker 部署
```dockerfile
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY . .
RUN go mod download
RUN go build -o build/subscheck main.go

FROM python:3.11-alpine
RUN pip install uv
COPY --from=builder /app/build /app/build
COPY --from=builder /app/requirements.txt /app/
COPY --from=builder /app/main.py /app/
COPY --from=builder /app/parsers /app/parsers
COPY --from=builder /app/testers /app/testers
COPY --from=builder /app/utils /app/utils
COPY --from=builder /app/core /app/core

RUN uv sync

CMD ["uv", "run", "main.py"]
```

## 🔧 配置说明

### config.yaml 主要配置项

```yaml
# 基础设置
concurrent: 10              # 并发线程数 (建议: 5-20)
timeout: 5000               # 超时时间(毫秒) (建议: 3000-10000)
check-interval: 60          # 定时检查间隔(分钟)

# 测速配置
speed-test-url: "https://github.com/AaronFeng753/Waifu2x-Extension-GUI/releases/download/v2.21.12/Waifu2x-Extension-GUI-v2.21.12-Portable.7z"
download-timeout: 10        # 下载测试时间(秒)
download-mb: 20            # 单节点测速下载数据大小(MB)
total-speed-limit: 0       # 总下载速度限制(MB/s)
min-speed: 512             # 最低测速结果舍弃(KB/s)

# 节点处理
rename-node: true          # 是否重命名节点
node-prefix: ""            # 节点名称前缀
filter-regex: ""           # 节点名称过滤正则表达式
node-type: []              # 只测试指定协议的节点

# 流媒体检测
media-check: false         # 是否开启流媒体检测
platforms:                 # 检测平台列表
  - iprisk
  - youtube
  - netflix
  - openai

# 结果保存
save-method: "local"       # 保存方式 (local/gist/webdav/s3/r2)
output-dir: ""             # 输出目录

# 订阅链接
sub-urls:
  - "https://raw.githubusercontent.com/example/sub1.txt"
  - "https://raw.githubusercontent.com/example/sub2.yaml"
```

### .env 环境变量配置

创建 `.env` 文件来保存敏感信息：

```bash
# 复制模板文件
cp env.example .env

# 编辑配置
nano .env
```

#### GitHub Gist 配置 (推荐)
1. 创建 GitHub Personal Access Token：
   - 访问：https://github.com/settings/tokens
   - 点击 "Generate new token (classic)"
   - 勾选 `gist` 权限
   - 复制生成的 token

2. 创建空白 Gist：
   - 访问：https://gist.github.com/
   - 创建一个新的 Gist
   - 复制 URL 中的 Gist ID

3. 配置 `.env`：
```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
GITHUB_GIST_ID=your_gist_id_here
```

#### WebDAV 配置
```bash
WEBDAV_URL=https://your-webdav-server.com/dav/
WEBDAV_USERNAME=your_username
WEBDAV_PASSWORD=your_password
```

#### S3/MinIO 配置
```bash
S3_ENDPOINT=https://s3.amazonaws.com
S3_ACCESS_ID=your_access_key_id
S3_SECRET_KEY=your_secret_access_key
S3_BUCKET=your_bucket_name
```

#### 通知配置
```bash
# Telegram 通知
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789
TELEGRAM_CHAT_ID=123456789

# Bark 通知 (iOS)
BARK_URL=https://api.day.app/YOUR_BARK_KEY

# Server酱通知 (微信)
SERVERCHAN_URL=https://sctapi.ftqq.com/YOUR_SCT_KEY.send
```

## 📝 高级用法

### 流媒体检测
开启流媒体检测可以获取更多节点信息，但会增加测试时间：

```yaml
# config.yaml
media-check: true
platforms:
  - iprisk
  - youtube
  - netflix
  - openai
  - disney
  - gemini
  - tiktok
```

### 节点过滤
使用正则表达式过滤特定节点：

```yaml
# config.yaml
filter-regex: ".*香港.*"  # 只测试名称包含"香港"的节点
node-type: ["vmess", "vless"]  # 只测试vmess和vless协议的节点
```

### 定时任务
设置定时任务自动执行测试：

```bash
# Linux (crontab)
crontab -e
# 添加以下行，每6小时执行一次
0 */6 * * * cd /path/to/subscheck-singbox && uv run main.py

# Windows (任务计划程序)
# 创建基本任务，设置触发器为"每天"，重复间隔为"6小时"
# 操作为"启动程序"，程序为"uv.exe"，参数为"run main.py"
```

### 自定义通知
配置多种通知方式，及时获取测试结果：

```yaml
# config.yaml
save-method: "gist"  # 保存到GitHub Gist

# .env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 🐛 故障排除

### 常见问题

1. **Go编译失败**
   ```bash
   # 检查Go版本
   go version
   
   # 重新下载依赖
   go mod download
   
   # 重新编译
   go build -o build/subscheck main.go
   ```

2. **Python依赖安装失败**
   ```bash
   # 检查Python版本
   python --version
   
   # 重新安装依赖
   uv sync
   ```

3. **订阅链接无法获取**
   ```bash
   # 检查网络连接
   ping github.com
   
   # 使用代理
   export HTTP_PROXY=http://127.0.0.1:7890
   export HTTPS_PROXY=http://127.0.0.1:7890
   uv run main.py
   ```

4. **测试结果不准确**
   ```bash
   # 增加测试时间
   download-timeout: 20
   download-mb: 50
   
   # 降低并发数
   concurrent: 5
   ```

### 调试模式
启用调试模式获取详细日志：

```bash
DEBUG=1 uv run main.py
```






