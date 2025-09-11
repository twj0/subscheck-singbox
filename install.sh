#!/bin/bash
# SubCheck Project - Final, Robust Installation Script for Ubuntu
# - Idempotent: Checks for existing installations before proceeding.
# - Robust: Uses 'jq' for reliable JSON parsing from GitHub API.
# - Optimized: Tailored for Mainland China network environments.

# --- Configuration & Setup ---
set -e
set -o pipefail

# Color codes for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Automatically detect if sudo is needed
SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

# --- Function Definitions ---

configure_apt_mirror() {
    echo -e "${GREEN}--- [1/6] Configuring APT to use Aliyun mirrors ---${NC}"
    if grep -q "mirrors.aliyun.com" /etc/apt/sources.list; then
        echo -e "${YELLOW}Aliyun APT mirror already configured. Skipping.${NC}"
    else
        echo "Backing up original sources.list to /etc/apt/sources.list.bak..."
        $SUDO_CMD cp /etc/apt/sources.list /etc/apt/sources.list.bak
        echo "Replacing APT sources with Aliyun mirrors..."
        $SUDO_CMD sed -i 's/http:\/\/ports.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
        $SUDO_CMD sed -i 's/http:\/\/archive.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
    fi
    echo "Updating package lists..."
    $SUDO_CMD apt update
}

# --- Main Execution ---

# Step 1: Configure Mirrors
configure_apt_mirror

# Step 2: Install System Dependencies (including jq)
echo -e "${GREEN}--- [2/6] Installing essential system packages ---${NC}"
$SUDO_CMD apt install -y git curl unzip python3-pip pipx jq

# Step 3: Configure and Install 'uv'
echo -e "${GREEN}--- [3/6] Configuring and Installing 'uv' via pipx ---${NC}"
if command -v uv &> /dev/null; then
    echo -e "${YELLOW}'uv' is already installed. Skipping installation.${NC}"
else
    export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
    pipx ensurepath
    export PATH="$PATH:$HOME/.local/bin"
    pipx install uv --force
    echo -e "${GREEN}✅ 'uv' installed successfully via Tsinghua mirror.${NC}"
fi

# Step 4: Install Xray-core
echo -e "${GREEN}--- [4/6] Installing Xray-core with smart download ---${NC}"
if command -v xray &> /dev/null; then
    echo -e "${YELLOW}'xray' is already installed. Skipping installation. Current version: $(xray version | head -n 1)${NC}"
else
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) ZIP_FILENAME="Xray-linux-64.zip" ;;
        aarch64|arm64) ZIP_FILENAME="Xray-linux-arm64-v8a.zip" ;;
        *) echo -e "${RED}ERROR: Unsupported architecture: $ARCH.${NC}"; exit 1 ;;
    esac
    echo "Detected architecture: $ARCH. Target file: $ZIP_FILENAME"

    XRAY_LATEST_TAG=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | jq -r '.tag_name')
    if [ -z "$XRAY_LATEST_TAG" ] || [ "$XRAY_LATEST_TAG" = "null" ]; then
        echo -e "${RED}ERROR: Could not fetch latest Xray version tag using 'jq'.${NC}"; exit 1
    fi
    echo "Latest Xray version is $XRAY_LATEST_TAG"

    ACCELERATORS=("https://ghfast.top" "https://ghproxy.com" "https://gh.api.99988866.xyz" "https://github.com")
    DOWNLOAD_SUCCESS=false

    for acc in "${ACCELERATORS[@]}"; do
        DOWNLOAD_URL="${acc}/https://github.com/XTLS/Xray-core/releases/download/${XRAY_LATEST_TAG}/${ZIP_FILENAME}"
        echo -e "Attempting to download from: ${YELLOW}${DOWNLOAD_URL}${NC}"
        TMP_DIR="/tmp/xray_install_$$"
        mkdir -p "$TMP_DIR"
        
        if curl -L --fail --speed-limit 10240 --speed-time 10 "$DOWNLOAD_URL" -o "$TMP_DIR/$ZIP_FILENAME"; then
            echo -e "${GREEN}Download successful!${NC}"; DOWNLOAD_SUCCESS=true; break
        else
            echo -e "${YELLOW}Download failed from $acc. Trying next...${NC}"; rm -rf "$TMP_DIR"
        fi
    done

    if [ "$DOWNLOAD_SUCCESS" = false ]; then
        echo -e "${RED}ERROR: Failed to download Xray from all accelerators.${NC}"; exit 1
    fi

    echo "Installing Xray..."
    unzip -o "$TMP_DIR/$ZIP_FILENAME" -d "$TMP_DIR"
    $SUDO_CMD mv "$TMP_DIR/xray" /usr/local/bin/
    $SUDO_CMD mkdir -p /usr/local/share/xray/
    $SUDO_CMD mv "$TMP_DIR/geoip.dat" /usr/local/share/xray/
    $SUDO_CMD mv "$TMP_DIR/geosite.dat" /usr/local/share/xray/
    rm -rf "$TMP_DIR"
    echo -e "${GREEN}✅ Xray-core installed successfully.${NC}"
fi

# Step 5: Install Python Project Dependencies
echo -e "${GREEN}--- [5/6] Installing project Python dependencies ---${NC}"
if [ ! -f "requirements.txt" ]; then
    echo -e "${YELLOW}requirements.txt not found. Creating a placeholder...${NC}"
    echo -e "aiohttp\nPyYAML\nrich" > requirements.txt
fi
echo "Installing/updating Python packages with uv (to system environment)..."
# Use --system flag to install into the global python env, suitable for server scripts.
uv pip install -r requirements.txt --system

# Step 6: Finalizing
mkdir -p results
echo ""
echo -e "${GREEN}✅ --- Installation/Verification Finished Successfully --- ✅${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: If this is the first time you've run the script, you must reload your shell.${NC}"
echo "Run ONE of the following commands:"
echo -e "  1. ${GREEN}source ~/.bashrc${NC} (or ~/.zshrc if you use zsh)"
echo -e "  2. ${GREEN}Log out and log back into your VPS.${NC}"
echo ""
echo "You can verify the installations with 'uv --version' and 'xray version'."
echo "Then, run your project using: ${GREEN}python3 main.py${NC}"