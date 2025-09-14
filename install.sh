#!/bin/bash
# SubsCheck-Ubuntu - 完整安装脚本
# 作者: subscheck-ubuntu team
# 专为Linux环境和中国大陆网络环境优化

# --- 配置和初始化 ---
set -e
set -o pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
SUDO_CMD=""

# 检测环境
detect_environment() {
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}    SubsCheck-Ubuntu v1.0 安装程序${NC}"
    echo -e "${GREEN}    专为Linux环境和中国大陆网络优化${NC}"
    echo -e "${GREEN}===============================================${NC}"
    
    # 检测操作系统
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        echo -e "${RED}错误: 此脚本仅支持Linux环境${NC}"
        echo -e "${YELLOW}如果您在Windows环境，请使用 install_windows.bat${NC}"
        exit 1
    fi
    
    # 检测架构
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) SING_ARCH="amd64" ;;
        aarch64|arm64) SING_ARCH="arm64" ;;
        armv7l) SING_ARCH="armv7" ;;
        *) echo -e "${RED}错误: 不支持的架构: $ARCH${NC}"; exit 1 ;;
    esac
    
    # 检测是否为root用户
    if [ "$(id -u)" -eq 0 ]; then
        echo -e "${YELLOW}检测到root用户，将直接执行系统级操作${NC}"
        SUDO_CMD=""
    else
        echo -e "${GREEN}检测到普通用户，将使用sudo执行系统操作${NC}"
        SUDO_CMD="sudo"
        # 检查sudo权限
        if ! $SUDO_CMD -n true 2>/dev/null; then
            echo -e "${YELLOW}需要sudo权限来安装系统包，请输入密码${NC}"
        fi
    fi
    
    # 检测网络环境（中国大陆优化）
    echo "检测网络环境..."
    if curl -m 5 -s www.baidu.com >/dev/null 2>&1; then
        echo -e "${GREEN}✅ 网络连接正常，启用中国大陆镜像加速${NC}"
        USE_CN_MIRROR=true
    else
        echo -e "${YELLOW}网络连接较慢，将使用国际镜像${NC}"
        USE_CN_MIRROR=false
    fi
    
    echo -e "检测结果:"
    echo -e "  - 操作系统: ${GREEN}Linux${NC}"
    echo -e "  - 架构: ${GREEN}$ARCH ($SING_ARCH)${NC}"
    echo -e "  - 用户权限: ${GREEN}$(if [ "$SUDO_CMD" = "" ]; then echo "root"; else echo "普通用户(sudo)"; fi)${NC}"
    echo -e "  - 网络环境: ${GREEN}$(if [ "$USE_CN_MIRROR" = true ]; then echo "中国大陆(镜像加速)"; else echo "国际网络"; fi)${NC}"
}

# --- 函数定义 ---
configure_apt_mirror() {
    echo -e "${GREEN}--- [1/8] 配置APT镜像源 ---${NC}"
    
    if [ "$USE_CN_MIRROR" = true ]; then
        echo "中国大陆环境，配置国内镜像源..."
        
        # 备份原始 sources.list
        if [ ! -f "/etc/apt/sources.list.bak" ]; then
            $SUDO_CMD cp /etc/apt/sources.list /etc/apt/sources.list.bak 2>/dev/null || true
            echo "已备份原始 sources.list"
        fi
        
        # 检测 Ubuntu 版本
        UBUNTU_CODENAME=$(lsb_release -cs 2>/dev/null || echo "focal")
        echo "检测到 Ubuntu 版本: $UBUNTU_CODENAME"
        
        # 优先使用阿里云镜像，备用清华镜像
        echo "更新APT源为阿里云镜像..."
        $SUDO_CMD tee /etc/apt/sources.list >/dev/null <<EOF
# 阿里云 Ubuntu 镜像源 - 由 SubsCheck-Ubuntu 自动配置
deb http://mirrors.aliyun.com/ubuntu/ $UBUNTU_CODENAME main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $UBUNTU_CODENAME-updates main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $UBUNTU_CODENAME-backports main restricted universe multiverse
deb http://mirrors.aliyun.com/ubuntu/ $UBUNTU_CODENAME-security main restricted universe multiverse
EOF
        echo -e "${GREEN}✅ APT源已更新为阿里云镜像${NC}"
    else
        echo "使用默认APT源..."
    fi
    
    echo "更新软件包列表..."
    $SUDO_CMD apt update -qq
    echo -e "${GREEN}✅ APT更新完成${NC}"
}

install_system_packages() {
    echo -e "${GREEN}--- [2/8] 安装系统基础软件包 ---${NC}"
    
    # 必需的系统包
    PACKAGES="git curl unzip python3 python3-pip python3-venv jq wget build-essential"
    
    if [ "$USE_CN_MIRROR" = true ]; then
        echo "使用中国镜像加速安装系统包..."
    fi
    
    $SUDO_CMD apt install -y $PACKAGES
    echo -e "${GREEN}✅ 系统软件包安装完成${NC}"
}

install_uv() {
    echo -e "${GREEN}--- [3/8] 安装uv包管理器 ---${NC}"
    if command -v uv &> /dev/null; then
        echo -e "${YELLOW}uv已存在，版本: $(uv --version)${NC}"
        return
    fi
    
    echo "安装uv包管理器..."
    
    if [ "$USE_CN_MIRROR" = true ]; then
        echo "使用中国镜像加速下载..."
        # 使用国内镜像
        export RUSTUP_DIST_SERVER="https://rsproxy.cn"
        export RUSTUP_UPDATE_ROOT="https://rsproxy.cn/rustup"
    fi
    
    # 优先尝试官方安装器
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.cargo/bin:$PATH"
        echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
        
        if command -v uv &> /dev/null; then
            echo -e "${GREEN}✅ uv安装成功，版本: $(uv --version)${NC}"
            return
        fi
    fi
    
    # 备用方案：使用pip安装
    echo -e "${YELLOW}官方安装器失败，尝试使用pip安装...${NC}"
    python3 -m pip install --user uv
    export PATH="$PATH:$HOME/.local/bin"
    echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc
    
    if command -v uv &> /dev/null; then
        echo -e "${GREEN}✅ uv安装成功（pip方式）${NC}"
    else
        echo -e "${RED}错误: 无法安装uv包管理器${NC}"
        exit 1
    fi
}

install_singbox() {
    echo -e "${GREEN}--- [4/8] 安装Sing-box ---${NC}"
    
    # 检查项目目录中是否已有sing-box
    if [ -f "./sing-box" ]; then
        echo -e "${YELLOW}项目目录中已存在sing-box，验证版本...${NC}"
        if ./sing-box version &> /dev/null; then
            echo -e "${GREEN}✅ 使用项目目录中的sing-box${NC}"
            echo -e "版本: $(./sing-box version | head -n 1)"
            return
        else
            echo -e "${YELLOW}项目目录中的sing-box无法运行，重新下载...${NC}"
            rm -f ./sing-box
        fi
    fi
    
    # 检查系统中是否已安装
    if command -v sing-box &> /dev/null; then
        echo -e "${YELLOW}系统中已安装Sing-box，版本: $(sing-box version | head -n 1)${NC}"
        # 创建符号链接到项目目录
        if [ ! -f "./sing-box" ]; then
            ln -sf $(which sing-box) ./sing-box
            echo "创建项目目录的sing-box符号链接"
        fi
        return
    fi
    
    # 使用内置的下载脚本自动下载
    echo "使用内置下载脚本获取sing-box..."
    if [ -f "./download_binaries.sh" ]; then
        chmod +x ./download_binaries.sh
        if ./download_binaries.sh; then
            echo -e "${GREEN}✅ Sing-box下载成功${NC}"
            return
        else
            echo -e "${YELLOW}内置下载脚本失败，尝试手动下载...${NC}"
        fi
    fi
    
    # 需要下载安装
    echo "系统架构: $ARCH, Sing-box架构: $SING_ARCH"
    
    # 获取最新版本（使用多镜像）
    GITHUB_MIRRORS=(
        "https://api.github.com"
        "https://ghfast.top/https://api.github.com"
        "https://ghproxy.com/https://api.github.com"
    )
    
    SINGBOX_LATEST_TAG=""
    for mirror in "${GITHUB_MIRRORS[@]}"; do
        echo "尝试获取版本信息: $mirror"
        if SINGBOX_LATEST_TAG=$(curl -m 10 -s "$mirror/repos/SagerNet/sing-box/releases/latest" | jq -r '.tag_name' 2>/dev/null); then
            if [ -n "$SINGBOX_LATEST_TAG" ] && [ "$SINGBOX_LATEST_TAG" != "null" ]; then
                echo -e "${GREEN}获取成功！${NC}"
                break
            fi
        fi
        echo "失败，尝试下一个镜像..."
    done
    
    if [ -z "$SINGBOX_LATEST_TAG" ] || [ "$SINGBOX_LATEST_TAG" = "null" ]; then
        echo -e "${RED}错误: 无法获取Sing-box版本信息${NC}"
        exit 1
    fi
    
    echo "最新Sing-box版本: $SINGBOX_LATEST_TAG"
    SINGBOX_FILENAME="sing-box-${SINGBOX_LATEST_TAG#v}-linux-${SING_ARCH}.tar.gz"
    
    # 使用多个下载加速器
    if [ "$USE_CN_MIRROR" = true ]; then
        DOWNLOAD_MIRRORS=(
            "https://ghfast.top"
            "https://ghproxy.com" 
            "https://mirror.ghproxy.com"
            "https://gh.con.sh"
            "https://github.com"
        )
    else
        DOWNLOAD_MIRRORS=(
            "https://github.com"
            "https://ghfast.top"
            "https://ghproxy.com"
        )
    fi
    
    DOWNLOAD_SUCCESS=false
    
    for mirror in "${DOWNLOAD_MIRRORS[@]}"; do
        DOWNLOAD_URL="${mirror}/https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_LATEST_TAG}/${SINGBOX_FILENAME}"
        echo -e "尝试下载: ${YELLOW}${mirror}${NC}"
        
        TMP_DIR="/tmp/singbox_$$"
        mkdir -p "$TMP_DIR"
        
        if curl -L --fail --progress-bar --connect-timeout 10 --max-time 300 -o "$TMP_DIR/$SINGBOX_FILENAME" "$DOWNLOAD_URL"; then
            echo -e "${GREEN}下载成功！${NC}"
            DOWNLOAD_SUCCESS=true
            break
        else
            echo -e "${YELLOW}下载失败，尝试下一个...${NC}"
            rm -rf "$TMP_DIR"
        fi
    done
    
    if [ "$DOWNLOAD_SUCCESS" = false ]; then
        echo -e "${RED}错误: 无法下载Sing-box${NC}"
        exit 1
    fi
    
    # 解压和安装
    echo "解压和安装Sing-box..."
    tar -xzf "$TMP_DIR/$SINGBOX_FILENAME" -C "$TMP_DIR"
    
    # 查找解压后的文件
    EXTRACTED_DIR=$(find "$TMP_DIR" -name "sing-box-*" -type d | head -n 1)
    if [ -z "$EXTRACTED_DIR" ]; then
        echo -e "${RED}错误: 找不到解压目录${NC}"
        exit 1
    fi
    
    # 安装到系统目录
    if [ -f "$EXTRACTED_DIR/sing-box" ]; then
        $SUDO_CMD mv "$EXTRACTED_DIR/sing-box" /usr/local/bin/
        $SUDO_CMD chmod +x /usr/local/bin/sing-box
        echo -e "${GREEN}✅ Sing-box已安装到 /usr/local/bin/${NC}"
    else
        echo -e "${RED}错误: 找不到sing-box可执行文件${NC}"
        exit 1
    fi
    
    # 创建项目目录的符号链接
    if [ ! -f "./sing-box" ]; then
        ln -sf /usr/local/bin/sing-box ./sing-box
        echo "创建项目目录的sing-box符号链接"
    fi
    
    rm -rf "$TMP_DIR"
    echo -e "${GREEN}✅ Sing-box安装成功${NC}"
}

setup_python_env() {
    echo -e "${GREEN}--- [5/8] 设置Python虚拟环境 ---${NC}"
    if [ -d ".venv" ]; then
        echo -e "${YELLOW}虚拟环境'.venv'已存在，跳过创建${NC}"
    else
        # 使用系统的python3创建venv
        python3 -m venv .venv
        echo -e "${GREEN}✅ 虚拟环境创建成功${NC}"
    fi
}

install_dependencies() {
    echo -e "${GREEN}--- [6/8] 安装Python依赖 ---${NC}"
    if [ ! -f "requirements.txt" ]; then
        echo -e "${YELLOW}requirements.txt不存在，创建完整依赖文件...${NC}"
        cat > requirements.txt << 'EOF'
# SubsCheck-Ubuntu 核心依赖

# 网络请求和代理支持
aiohttp>=3.8.0
PySocks>=1.7.1
requests>=2.28.0

# 配置文件解析
PyYAML>=6.0

# 美化终端输出和日志
rich>=13.0.0
colorama>=0.4.6

# 文件监控（配置热重载）
watchdog>=3.0.0

# 定时任务支持
croniter>=1.3.0
schedule>=1.2.0
pytz>=2023.3

# 系统工具
psutil>=5.9.0

# 加密和安全
cryptography>=41.0.0

# 数据处理
numpy>=1.24.0
EOF
    fi
    
    # 激活venv并安装依赖
    source .venv/bin/activate
    echo "使用Python: $(which python)"
    
    # 配置pip镜像（中国大陆加速）
    if [ "$USE_CN_MIRROR" = true ]; then
        echo "配置pip使用中国镜像源..."
        mkdir -p ~/.pip
        cat > ~/.pip/pip.conf << 'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
EOF
    fi
    
    # 使用uv安装依赖（更快）
    if command -v uv &> /dev/null; then
        echo "使用uv安装Python依赖..."
        uv pip install -r requirements.txt
    else
        # 如果uv不可用，使用普通pip
        echo "使用pip安装Python依赖..."
        pip install -r requirements.txt
    fi
    
    echo -e "${GREEN}✅ Python依赖安装成功${NC}"
}

setup_project_structure() {
    echo -e "${GREEN}--- [7/8] 设置项目结构 ---${NC}"
    
    # 创建必要的目录
    mkdir -p results logs debug
    
    # 检查配置文件
    if [ ! -f "config.yaml" ]; then
        echo -e "${YELLOW}config.yaml不存在，请确保配置文件正确${NC}"
    fi
    
    # 检查订阅文件
    if [ ! -f "subscription.txt" ]; then
        echo -e "${YELLOW}subscription.txt不存在，创建示例文件${NC}"
        cat > subscription.txt << 'EOF'
# 请在此文件中添加您的订阅链接
# 一行一个链接
# 
# 示例:
# https://example.com/subscription
EOF
    fi
    
    # 创建运行脚本
    cat > run.sh << 'EOF'
#!/bin/bash
# SubsCheck-Ubuntu 运行脚本
# 作者: subscheck-ubuntu team

set -e
cd "$(dirname "$0")"

# 激活虚拟环境并运行
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    python main.py "$@"
else
    echo "错误: 虚拟环境不存在，请先运行 install.sh"
    exit 1
fi
EOF
    chmod +x run.sh
    
    echo -e "${GREEN}✅ 项目结构设置完成${NC}"
}

setup_cron_scheduler() {
    echo -e "${GREEN}--- [8/9] 设置定时任务 (可选) ---${NC}"
    
    # 询问用户是否设置定时任务
    echo -e "${YELLOW}是否设置定时任务自动测速？[y/N]${NC}"
    read -r -t 10 setup_cron || setup_cron="n"
    
    if [[ "$setup_cron" =~ ^[Yy]$ ]]; then
        echo "设置定时任务..."
        
        # 获取当前脚本的绝对路径
        SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
        
        # 创建定时任务脚本
        cat > "${SCRIPT_DIR}/cron_speedtest.sh" << EOF
#!/bin/bash
# SubsCheck-Ubuntu 定时任务脚本
# 自动生成于 $(date)

cd "${SCRIPT_DIR}"
source .venv/bin/activate
python main.py --max-nodes 50 >> logs/cron.log 2>&1
EOF
        chmod +x "${SCRIPT_DIR}/cron_speedtest.sh"
        
        # 添加到crontab (每6小时执行一次)
        echo "# SubsCheck-Ubuntu 自动测速 - 每6小时执行一次" > /tmp/subscheck_cron
        echo "0 */6 * * * ${SCRIPT_DIR}/cron_speedtest.sh" >> /tmp/subscheck_cron
        
        # 检查现有crontab
        if crontab -l &> /dev/null; then
            # 合并现有crontab
            (crontab -l; cat /tmp/subscheck_cron) | crontab -
        else
            # 直接设置新crontab
            crontab /tmp/subscheck_cron
        fi
        
        rm -f /tmp/subscheck_cron
        
        echo -e "${GREEN}✅ 定时任务设置成功！每6小时自动测速一次${NC}"
        echo -e "日志文件: ${YELLOW}${SCRIPT_DIR}/logs/cron.log${NC}"
        echo -e "查看定时任务: ${GREEN}crontab -l${NC}"
        echo -e "停用定时任务: ${GREEN}crontab -e${NC} (删除对应行)"
    else
        echo -e "${YELLOW}跳过定时任务设置${NC}"
        echo -e "您可以稍后使用以下命令手动设置："
        echo -e "  ${GREEN}./run.sh --scheduler${NC} (程序内定时器)"
        echo -e "  ${GREEN}crontab -e${NC} (系统定时任务)"
    fi
}

finalize_installation() {
    echo -e "${GREEN}--- [9/9] 完成安装 ---${NC}"
    
    # 显示版本信息
    echo ""
    echo -e "${GREEN}✅ --- 安装完成 --- ✅${NC}"
    echo ""
    echo -e "${YELLOW}环境信息:${NC}"
    if command -v sing-box &> /dev/null; then
        echo -e "  Sing-box: ${GREEN}$(sing-box version | head -n 1)${NC}"
    fi
    if command -v uv &> /dev/null; then
        echo -e "  UV: ${GREEN}$(uv --version)${NC}"
    fi
    echo -e "  Python: ${GREEN}$(python3 --version)${NC}"
    echo -e "  系统架构: ${GREEN}$ARCH${NC}"
    
    echo ""
    echo -e "${YELLOW}快速开始:${NC}"
    echo -e "  1. 配置订阅链接: ${GREEN}nano subscription.txt${NC}"
    echo -e "  2. 立即测试: ${GREEN}./run.sh -n 10${NC}"
    echo -e "  3. 查看结果: ${GREEN}ls -la results/${NC}"
    
    echo ""
    echo -e "${YELLOW}常用命令:${NC}"
    echo -e "  完整测试: ${GREEN}./run.sh${NC}"
    echo -e "  调试模式: ${GREEN}./run.sh --debug${NC}"
    echo -e "  定时任务: ${GREEN}./run.sh --scheduler${NC}"
    echo -e "  查看帮助: ${GREEN}./run.sh --help${NC}"
    
    if [ -f "./cron_speedtest.sh" ]; then
        echo ""
        echo -e "${GREEN}🕒 定时任务已设置，每6小时自动执行${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}🚀 安装完成！开始测速吧！${NC}"
}

# --- 主执行流程 ---
main() {
    detect_environment
    configure_apt_mirror
    install_system_packages
    install_uv
    install_singbox
    setup_python_env
    install_dependencies
    setup_project_structure
    setup_cron_scheduler
    finalize_installation
}

# 执行安装
main "$@"