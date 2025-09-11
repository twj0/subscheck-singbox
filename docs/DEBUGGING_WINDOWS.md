# Windows 11 调试指南 for SubsCheck

本指南旨在帮助您在 Windows 11 本地环境中设置、运行和调试 `subscheck-ubuntu` 项目。

## 1. 先决条件

在开始之前，请确保您的系统已安装以下软件：

- **Python 3.12+**:
  - 从 [Python 官网](https://www.python.org/downloads/) 下载并安装。
  - **重要**: 在安装过程中，请务必勾选 "Add Python to PATH" 选项。
- **Git**:
  - 从 [Git 官网](https://git-scm.com/download/win) 下载并安装。

您可以在 PowerShell 或 CMD 中运行 `python --version` 和 `git --version` 来验证安装是否成功。

## 2. 项目设置

### 克隆代码库

打开 PowerShell 或 CMD，进入您希望存放项目的目录，然后运行以下命令：

```bash
git clone <your-repository-url>
cd subscheck-ubuntu
```

### 安装 uv

`uv` 是一个极速的 Python 包安装和解析器。我们将使用 `pipx` 来安装它，以避免污染全局 Python 环境。

```powershell
# 安装 pipx
py -m pip install --user pipx
py -m pipx ensurepath

# 关闭并重新打开 PowerShell/CMD 终端
# 使用 pipx 安装 uv
pipx install uv
```

运行 `uv --version` 验证安装。

## 3. 安装 Xray-core for Windows

项目依赖 Xray-core 来测试节点。`install.sh` 脚本无法在 Windows 上运行，需要手动下载。

1.  **下载 Xray-core**:
    - 前往 [Xray-core 的 GitHub Releases 页面](https://github.com/XTLS/Xray-core/releases)。
    - 找到最新的版本，下载适用于 Windows 的 `64-bit` `zip` 压缩包（例如 `Xray-windows-64.zip`）。

2.  **解压和放置**:
    - 解压下载的 `zip` 文件。
    - 将解压出来的 `xray.exe` 文件复制到 `subscheck-ubuntu` 项目的根目录下。这是为了让 `core/xray_runner.py` 脚本能够找到它。

## 4. 配置 Python 虚拟环境

使用虚拟环境是 Python 项目的最佳实践，可以隔离项目依赖。

```powershell
# 1. 在项目根目录创建虚拟环境
uv venv

# 2. 激活虚拟环境
#    激活后，你的终端提示符前会出现 (.venv)
.venv\Scripts\activate

# 3. 安装项目依赖
#    确保你在激活了虚拟环境的终端中运行此命令
uv pip install -r requirements.txt
```

## 5. 运行与调试

### 正常运行

确保您已经激活了虚拟环境 (`.venv\Scripts\activate`)，然后在项目根目录运行：

```powershell
python main.py
```

### 调试指南

根据您在 Ubuntu VPS 上遇到的错误，以下是一些针对性的调试步骤：

#### A. 调试网络错误 (`Failed to fetch...`)

这类错误通常是 DNS 解析失败或网络无法访问目标 URL 导致的。

1.  **验证链接**: 随意从日志中挑选一个失败的 URL，尝试用浏览器或者 `curl` (Windows 11 自带) 访问，看是否能获取内容。
    ```powershell
    curl -L "https://raw.githubusercontent.com/Leon406/SubCrawler/refs/heads/main/sub/share/vless"
    ```
2.  **网络环境**: 很多订阅链接在国内可能无法直接访问。您可能需要在系统上配置代理，并让 Python 脚本通过该代理发出请求。这需要修改代码，在 `aiohttp` 请求中加入 `proxy` 参数。

#### B. 调试解析错误 (`Failed to parse...`)

这类错误说明从 URL 获取到的内容格式不正确，或者解析逻辑有 bug。

1.  **检查内容**: 修改 `main.py` 中 `fetch_subscription_content` 函数，在解析前打印出从 URL 获取到的原始文本 `text`。
    ```python
    # in main.py, around line 50
    async def fetch_subscription_content(session, url):
        # ...
        try:
            text = await response.text()
            print(f"--- Content from {url} ---")
            print(text) # <--- 添加这行来打印原始内容
            print("--- End of Content ---")
            # ...
    ```
2.  **分析格式**: 查看打印出的内容，判断它是否是预期的 Base64、Clash YAML 或纯文本链接格式。很多时候，返回的可能是一个 HTML 错误页面，或者格式已经变化。
3.  **单步调试**: 针对特定格式的解析失败（如 VMess），可以修改 `parsers/base_parser.py`，在对应的 `parse_vmess` 等函数中加入日志或 `print` 语句，查看是哪个字段解析出了问题。

#### C. 调试 Xray 错误 (`Xray failed to start. Return code: 23`)

这是最关键的错误之一，意味着 `xray.exe` 进程启动失败。

1.  **确认路径**: 检查 `core/xray_runner.py` 脚本，确认它寻找 `xray.exe` 的路径是否正确。默认情况下，它应该是在项目根目录。
2.  **查看 Xray 配置**: 修改 `core/xray_runner.py` 中的 `run_test` 方法，在启动 `xray.exe` 进程前，将生成的 `config` 打印出来或保存到临时文件。
    ```python
    # in core/xray_runner.py
    async def run_test(self, node_config):
        # ...
        config_json = self._generate_config(node_config)
        
        # 打印生成的配置用于调试
        print("--- Xray Config ---")
        print(config_json)
        print("--- End of Config ---")

        # ... a few lines later
        # proc = await asyncio.create_subprocess_exec(...)
    ```
3.  **手动运行 Xray**: 将打印出的 JSON 配置保存到一个临时的 `config.json` 文件中。然后在终端里手动运行 `xray.exe`，查看它输出的详细错误信息。
    ```powershell
    .\xray.exe -c config.json
    ```
    Xray 会明确指出是哪个配置项有问题，这通常是定位问题的最快方法。`Return code: 23` 往往与配置文件的格式或内容错误有关。

#### D. 调试配置错误 (`Test failed with exception: 'latency_urls'`)

这个错误表明 `config.yaml` 文件中缺少 `latency_urls` 这个键。

1.  **检查 `config.yaml`**: 打开 `config.yaml` 文件。
2.  **确保结构正确**: 确认文件中有如下结构，并且至少有一个有效的测速 URL。
    ```yaml
    # config.yaml
    settings:
      test_nodes_limit: 100
      # ...
    
    latency_urls:
      - http://www.google.com/generate_204
      - http://www.apple.com/library/test/success.html