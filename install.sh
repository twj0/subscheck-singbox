#!/bin/bash
# SubsCheck-Ubuntu - 安装脚本
# 作者: subscheck-ubuntu team
# 适配新的项目架构和Ubuntu环境

# --- 配置和初始化 ---
set -e
set -o pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then SUDO_CMD="sudo"; fi

echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN}    SubsCheck-Ubuntu v1.0 安装程序${NC}"
echo -e "${GREEN}===============================================${NC}"

# --- 函数定义 ---
configure_apt_mirror() {
    echo -e "${GREEN}--- [1/8] 配置APT镜像源 ---${NC}"
    if grep -q "mirrors.aliyun.com" /etc/apt/sources.list 2>/dev/null; then
        echo -e "${YELLOW}阿里APT镜像已配置，跳过。${NC}"
    else
        echo "备份原始 sources.list..."
        $SUDO_CMD cp /etc/apt/sources.list /etc/apt/sources.list.bak 2>/dev/null || true
        echo "替换APT源为阿里镜像..."
        $SUDO_CMD sed -i 's|http://ports.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true
        $SUDO_CMD sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true
    fi
    echo "更新软件包列表..."
    $SUDO_CMD apt update
}

}

install_system_packages() {
    echo -e "${GREEN}--- [2/8] 安装系统基础软件包 ---${NC}"
    $SUDO_CMD apt install -y git curl unzip python3 python3-pip python3-venv jq wget
    echo -e "${GREEN}✅ 系统软件包安装完成${NC}"
}

install_uv() {
    echo -e "${GREEN}--- [3/8] 安装uv包管理器 ---${NC}"
    if command -v uv &> /dev/null; then
        echo -e "${YELLOW}uv已存在，版本: $(uv --version)${NC}"
    else
        echo "使用官方安装器安装uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        
        # 检查安装是否成功
        if command -v uv &> /dev/null; then
            echo -e "${GREEN}✅ uv安装成功，版本: $(uv --version)${NC}"
        else
            echo -e "${RED}官方安装器失败，尝试使用pip安装...${NC}"
            python3 -m pip install --user uv
            export PATH="$PATH:$HOME/.local/bin"
            
            if command -v uv &> /dev/null; then
                echo -e "${GREEN}✅ uv安装成功（pip方式）${NC}"
            else
                echo -e "${RED}错误: 无法安装uv包管理器${NC}"
                exit 1
            fi
        fi
    fi
}

install_singbox() {
    echo -e "${GREEN}--- [4/8] 安装Sing-box ---${NC}"
    if command -v sing-box &> /dev/null; then
        echo -e "${YELLOW}Sing-box已存在，版本: $(sing-box version | head -n 1)${NC}"
    else
        # 检测架构
        ARCH=$(uname -m)
        case "$ARCH" in
            x86_64) SINGBOX_ARCH="amd64" ;;
            aarch64|arm64) SINGBOX_ARCH="arm64" ;;
            *) echo -e "${RED}错误: 不支持的架构: $ARCH${NC}"; exit 1 ;;
        esac
        
        echo "系统架构: $ARCH, Sing-box架构: $SINGBOX_ARCH"
        
        # 获取最新版本
        SINGBOX_LATEST_TAG=$(curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | jq -r '.tag_name')
        if [ -z "$SINGBOX_LATEST_TAG" ] || [ "$SINGBOX_LATEST_TAG" = "null" ]; then
            echo -e "${RED}错误: 无法获取Sing-box版本信息${NC}"
            exit 1
        fi
        
        echo "最新Sing-box版本: $SINGBOX_LATEST_TAG"
        SINGBOX_FILENAME="sing-box-${SINGBOX_LATEST_TAG#v}-linux-${SINGBOX_ARCH}.tar.gz"
        
        # 使用加速器下载
        ACCELERATORS=("https://ghfast.top" "https://ghproxy.com" "https://github.com")
        DOWNLOAD_SUCCESS=false
        
        for acc in "${ACCELERATORS[@]}"; do
            DOWNLOAD_URL="${acc}/https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_LATEST_TAG}/${SINGBOX_FILENAME}"
            echo -e "尝试下载: ${YELLOW}${DOWNLOAD_URL}${NC}"
            
            TMP_DIR="/tmp/singbox_$$"
            mkdir -p "$TMP_DIR"
            
            if curl -L --fail -o "$TMP_DIR/$SINGBOX_FILENAME" "$DOWNLOAD_URL"; then
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
        tar -xzf "$TMP_DIR/$SINGBOX_FILENAME" -C "$TMP_DIR"
        $SUDO_CMD mv "$TMP_DIR"/sing-box-*/sing-box /usr/local/bin/
        $SUDO_CMD chmod +x /usr/local/bin/sing-box
        rm -rf "$TMP_DIR"
        
        echo -e "${GREEN}✅ Sing-box安装成功${NC}"
        
        # 创建符号链接到项目目录（适配代码中的路径查找）
        if [ ! -f "./sing-box" ]; then
            ln -sf /usr/local/bin/sing-box ./sing-box
            echo "创建项目目录的sing-box符号链接"
        fi
    fi
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
        echo -e "${YELLOW}requirements.txt不存在，创建默认文件...${NC}"
        cat > requirements.txt << 'EOF'
# SubsCheck-Ubuntu 核心依赖
aiohttp>=3.8.0
PyYAML>=6.0
rich>=13.0.0
watchdog>=3.0.0
croniter>=1.3.0
EOF
    fi
    
    # 激活venv并安装依赖
    source .venv/bin/activate
    echo "使用Python: $(which python)"
    
    # 使用uv安装依赖（更快）
    if command -v uv &> /dev/null; then
        uv pip install -r requirements.txt
    else
        # 如果uv不可用，使用普通pip
        pip install -r requirements.txt
    fi
    
    echo -e "${GREEN}✅ Python依赖安装成功${NC}"
}

setup_project_structure() {
    echo -e "${GREEN}--- [7/8] 设置项目结构 ---${NC}"
    
    # 创建必要的目录
    mkdir -p results logs
    
    # 检查配置文件
    if [ ! -f "config.yaml" ]; then
        echo -e "${YELLOW}config.yaml不存在，使用默认配置${NC}"
    fi
    
    # 检查订阅文件
    if [ ! -f "subscription.txt" ]; then
        echo -e "${YELLOW}subscription.txt不存在，创建示例文件${NC}"
        echo -e "# 请在此文件中添加您的订阅链接\n# 一行一个链接" > subscription.txt
    fi
    
    # 创建运行脚本
    cat > run.sh << 'EOF'
#!/bin/bash
# SubsCheck-Ubuntu 运行脚本
# 作者: subscheck-ubuntu team

set -e
cd "$(dirname "$0")"

# 激活虚拟环境并运行
source .venv/bin/activate
python main.py "$@"
EOF
    chmod +x run.sh
    
    echo -e "${GREEN}✅ 项目结构设置完成${NC}"
}

finalize_installation() {
    echo -e "${GREEN}--- [8/8] 完成安装 ---${NC}"
    
    # 显示版本信息
    echo ""
    echo -e "${GREEN}✅ --- 安装完成 --- ✅${NC}"
    echo ""
    echo -e "${YELLOW}重要提示: 已创建Python虚拟环境'.venv'${NC}"
    echo "运行程序有以下方式:"
    echo -e "  1. (推荐) 使用运行脚本:"
    echo -e "     ${GREEN}./run.sh${NC}"
    echo -e "  2. 手动激活环境:"
    echo -e "     ${GREEN}source .venv/bin/activate${NC}"
    echo -e "     ${GREEN}python main.py${NC}"
    echo -e "  3. 直接使用venv的Python:"
    echo -e "     ${GREEN}./.venv/bin/python main.py${NC}"
    echo ""
    echo -e "更多使用说明请查看: ${GREEN}python main.py --help${NC}"
    echo ""
    
    # 显示环境信息
    if command -v sing-box &> /dev/null; then
        echo -e "Sing-box版本: ${GREEN}$(sing-box version | head -n 1)${NC}"
    fi
    if command -v uv &> /dev/null; then
        echo -e "UV版本: ${GREEN}$(uv --version)${NC}"
    fi
    echo -e "Python版本: ${GREEN}$(python3 --version)${NC}"
}

# --- 主执行流程 ---
configure_apt_mirror
install_system_packages
install_uv
install_singbox
setup_python_env
install_dependencies
setup_project_structure
finalize_installation

echo -e "${GREEN}安装完成！可以使用 './run.sh' 或 'python main.py' 开始测试${NC}"