# SubCheck - 高性能代理订阅节点筛选工具

SubCheck 是一个专为中国大陆用户设计的高性能代理节点测试和筛选工具。它能够自动从多个订阅源获取节点，通过真实的HTTP延迟和下载速度测试，为您筛选出当前网络环境下最优质、最快速的代理节点。

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)


---

## ✨ 主要特性

- **多种订阅格式支持**: 智能识别并解析 `Clash (YAML)`、`Base64` 编码以及 `Vmess/Vless/Trojan` 纯文本链接格式的订阅源。
- **全面的节点测试**:
    - **HTTP 延迟测试**: 并发测试节点到多个国内外知名站点的连接延迟，综合评估节点的响应速度。
    - **真实下载测速**: 并发测试节点从多个国内外CDN下载文件的真实速度，准确反映节点的带宽性能。
- **高性能并发**: 利用 `asyncio` 实现高并发测试，能够在短时间内完成对大量节点的筛选。
- **高度可配置**: 所有关键参数，如并发数、超时时间、测试URL、筛选节点数量等，均可通过 `config.yaml` 文件进行灵活配置。
- **自动化运行**: 配备 `install.sh` 和 `run.sh` 脚本，可轻松在 Ubuntu 服务器上部署，并通过 `cron` 实现定时自动测试和更新结果。
- **清晰的结果展示**: 使用 `rich` 库在命令行生成美观的结果表格，直观展示最优节点的性能数据。
- **健壮的架构**: 依赖 `Xray-core` 作为测试核心，确保了对各种复杂代理协议的稳定支持。

---

##  快速开始

### 1. 克隆项目

登录到您的 vps，并克隆本仓库：

```bash
git clone https://github.com/twj0/subscheck-ubuntu.git
cd subscheck-ubuntu
```

### 2. 执行安装脚本

项目提供了一键安装脚本 `install.sh`，它将自动完成所有环境依赖的安装，包括 `git`, `curl`, `uv` (高速Python包安装器) 以及 `Xray-core`。

```bash
bash install.sh
```
> **注意**: `uv` 安装完成后，您可能需要执行 `source ~/.bashrc` 或重新登录终端才能使其生效。

### 3. 配置订阅链接

编辑 `subscription.txt` 文件，将您的所有代理订阅链接粘贴进去，每行一个。

```
# 这是注释，会被自动忽略
https://example.com/sub1.txt
https://example.com/sub2.yaml
```

### 4. 自定义配置 (可选)

打开 `config.yaml` 文件，您可以根据自己的需求调整测试参数。大部分情况下，默认配置已经足够优秀。

### 5. 手动执行测试

一切就绪后，运行主程序即可开始测试：

```bash
python3 main.py
```

测试完成后，性能最优的节点将会以表格形式展示在终端。

---

## ⚙️ 配置文件说明 (`config.yaml`)

这是项目的控制中心，所有行为都由它定义。

- `general_settings`:
    - `max_nodes_to_test`: 最多测试的节点数量 (`-1` 表示测试所有)。
    - `concurrency`: 并发测试的线程数，可根据服务器性能适当调整。
- `test_settings`:
    - `timeout`: 延迟测试的超时时间（秒）。
    - `speed_test_duration`: 每个测速URL的下载持续时间（秒）。
    - `latency_urls`: 用于测试HTTP延迟的目标URL列表。
    - `speed_urls`: 用于测试下载速度的大文件URL列表。
- `output_settings`:
    - `results_dir`: 测试结果日志的存放目录。
    - `top_n_results`: 在命令行表格中显示的最优节点数量。

---

## 🤖 自动化运行 (Cron)

您可以设置定时任务，让服务器在后台自动为您筛选节点。

### 1. 确保 `run.sh` 可执行

```bash
chmod +x run.sh
```

### 2. 编辑 Cron 任务

打开 `crontab` 编辑器：
```bash
crontab -e
```

在文件末尾添加一行，以下示例表示每6小时的0分执行一次测试：

```
# SubCheck Project - Automatic Node Testing
0 */6 * * * /path/to/your/project/run.sh
```


### 3. 查看日志

自动化任务的输出日志将保存在 `results/cron.log` 文件中，方便您随时查看运行状态或排查问题。

---

##  项目结构

```
.
├── main.py                 # 主程序入口
├── config.yaml             # 核心配置文件
├── subscription.txt        # 订阅链接文件
├── install.sh              # 一键安装脚本
├── run.sh                  # 自动化执行脚本
├── requirements.txt        # Python 依赖
├── core/                   # 与 Xray-core 交互的模块
│   └── xray_runner.py
├── parsers/                # 各类订阅格式的解析器
│   ├── base_parser.py
│   └── clash_parser.py
├── testers/                # 节点测试逻辑
│   └── node_tester.py
├── utils/                  # 工具函数 (如日志)
│   └── logger.py
└── results/                # 存放日志和结果
```
