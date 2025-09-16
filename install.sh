#!/bin/bash

# SubsCheck-Singbox v3.0 自動安裝腳本
# 支持 Ubuntu/Debian/CentOS 系統

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 顯示橫幅
show_banner() {
    echo -e "${CYAN}"
    echo "████████████████████████████████████████████████████████"
    echo "█                                                      █"
    echo "█            🚀 SubsCheck-Singbox v3.0                █"
    echo "█            Python+Go混合架構安裝腳本                █"
    echo "█                                                      █"
    echo "████████████████████████████████████████████████████████"
    echo -e "${NC}"
    echo -e "${BLUE}🔍 系統檢測中...${NC}"
    echo ""
}

# 檢查系統
check_system() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/debian_version ]; then
            DISTRO="debian"
            PACKAGE_MANAGER="apt"
        elif [ -f /etc/redhat-release ]; then
            DISTRO="redhat"
            PACKAGE_MANAGER="yum"
        elif [ -f /etc/centos-release ]; then
            DISTRO="centos"
            PACKAGE_MANAGER="yum"
        else
            echo -e "${RED}❌ 不支持的 Linux 發行版${NC}"
            exit 1
        fi
        echo -e "${GREEN}✅ 檢測到系統: $DISTRO (包管理器: $PACKAGE_MANAGER)${NC}"
    else
        echo -e "${RED}❌ 此腳本僅支持 Linux 系統${NC}"
        exit 1
    fi
}

# 更新系統包
update_system() {
    echo -e "${YELLOW}📦 更新系統包...${NC}"
    if [ "$PACKAGE_MANAGER" = "apt" ]; then
        sudo apt update && sudo apt upgrade -y
    elif [ "$PACKAGE_MANAGER" = "yum" ]; then
        sudo yum update -y
    fi
    echo -e "${GREEN}✅ 系統包更新完成${NC}"
}

# 安裝必要依賴
install_dependencies() {
    echo -e "${YELLOW}📦 安裝系統依賴...${NC}"
    if [ "$PACKAGE_MANAGER" = "apt" ]; then
        sudo apt install -y curl wget git build-essential python3 python3-pip python3-venv
    elif [ "$PACKAGE_MANAGER" = "yum" ]; then
        sudo yum groupinstall -y "Development Tools"
        sudo yum install -y curl wget git python3 python3-pip
    fi
    echo -e "${GREEN}✅ 系統依賴安裝完成${NC}"
}

# 安裝 Go
install_go() {
    if ! command -v go &> /dev/null; then
        echo -e "${YELLOW}📦 安裝 Go 語言...${NC}"
        GO_VERSION="1.21.5"
        
        # 檢測系統架構
        ARCH=$(uname -m)
        if [ "$ARCH" = "x86_64" ]; then
            GO_ARCH="amd64"
        elif [ "$ARCH" = "aarch64" ]; then
            GO_ARCH="arm64"
        else
            echo -e "${RED}❌ 不支持的系統架構: $ARCH${NC}"
            exit 1
        fi
        
        wget -q "https://golang.org/dl/go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
        sudo tar -C /usr/local -xzf "go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
        rm "go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
        
        # 添加到 PATH
        echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
        echo 'export GOPATH=$HOME/go' >> ~/.bashrc
        export PATH=$PATH:/usr/local/go/bin
        export GOPATH=$HOME/go
        
        echo -e "${GREEN}✅ Go 安裝完成: $(go version)${NC}"
    else
        echo -e "${GREEN}✅ Go 已安裝: $(go version)${NC}"
    fi
}

# 安裝 uv
install_uv() {
    if ! command -v uv &> /dev/null; then
        echo -e "${YELLOW}📦 安裝 uv Python 包管理器...${NC}"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source $HOME/.cargo/env
        echo -e "${GREEN}✅ uv 安裝完成${NC}"
    else
        echo -e "${GREEN}✅ uv 已安裝: $(uv --version)${NC}"
    fi
}

# 安裝 Python 依賴
install_python_deps() {
    echo -e "${YELLOW}📦 安裝 Python 依賴...${NC}"
    uv sync
    echo -e "${GREEN}✅ Python 依賴安裝完成${NC}"
}

# 編譯 Go 程序
compile_go() {
    echo -e "${YELLOW}🔨 編譯 Go 核心程序...${NC}"
    go mod download
    go build -o build/subscheck -ldflags="-s -w" main.go
    echo -e "${GREEN}✅ Go 程序編譯完成${NC}"
}

# 創建配置文件
setup_config() {
    if [ ! -f "config.yaml" ]; then
        echo -e "${YELLOW}📝 創建配置文件...${NC}"
        cp config.example.yaml config.yaml
        echo -e "${GREEN}✅ 配置文件已創建: config.yaml${NC}"
    else
        echo -e "${BLUE}ℹ️  配置文件已存在: config.yaml${NC}"
    fi
    
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}📝 創建環境變量模板...${NC}"
        cp env.example .env
        echo -e "${GREEN}✅ 環境變量模板已創建: .env${NC}"
    else
        echo -e "${BLUE}ℹ️  環境變量文件已存在: .env${NC}"
    fi
}

# 顯示完成信息
show_completion() {
    echo ""
    echo -e "${GREEN}"
    echo "🎉 安裝完成！"
    echo "████████████████████████████████████████████████████████"
    echo -e "${NC}"
    echo -e "${BLUE}🚀 使用方法:${NC}"
    echo -e "   ${GREEN}uv run main.py${NC} - 運行測速"
    echo ""
    echo -e "${BLUE}📝 配置說明:${NC}"
    echo -e "   ${YELLOW}1. 編輯 config.yaml 添加您的訂閱鏈接${NC}"
    echo -e "   ${YELLOW}2. 可選: 編輯 .env 配置 GitHub Gist 或 WebDAV${NC}"
    echo ""
    echo -e "${BLUE}🔧 其他選項:${NC}"
    echo -e "   ${GREEN}uv run main.py --help${NC} - 查看幫助"
    echo -e "   ${GREEN}uv run main.py --compile-only${NC} - 僅編譯 Go 程序"
    echo ""
    echo -e "${PURPLE}💡 提示: 如果您想將結果保存到 GitHub Gist 或 WebDAV，${NC}"
    echo -e "${PURPLE}    請編輯 .env 文件填入相應的配置信息${NC}"
    echo ""
    echo -e "${CYAN}████████████████████████████████████████████████████████${NC}"
}

# 主函數
main() {
    show_banner
    check_system
    update_system
    install_dependencies
    install_go
    install_uv
    install_python_deps
    compile_go
    setup_config
    show_completion
}

# 運行主函數
main "$@"