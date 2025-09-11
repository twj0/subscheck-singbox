#!/bin/bash
# SubCheck Project - Final, Robust Installation Script for Ubuntu
# - Idempotent: Checks for existing installations.
# - Robust: Uses 'jq' for reliable API parsing.
# - Best Practices: Creates and uses a Python virtual environment (.venv).

# --- Configuration & Setup ---
set -e
set -o pipefail
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then SUDO_CMD="sudo"; fi

# --- Functions ---
configure_apt_mirror() {
    echo -e "${GREEN}--- [1/7] Configuring APT to use Aliyun mirrors ---${NC}"
    if grep -q "mirrors.aliyun.com" /etc/apt/sources.list; then
        echo -e "${YELLOW}Aliyun APT mirror already configured. Skipping.${NC}"
    else
        echo "Backing up original sources.list..."
        $SUDO_CMD cp /etc/apt/sources.list /etc/apt/sources.list.bak
        echo "Replacing APT sources with Aliyun mirrors..."
        $SUDO_CMD sed -i 's/http:\/\/ports.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
        $SUDO_CMD sed -i 's/http:\/\/archive.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
    fi
    echo "Updating package lists..."; $SUDO_CMD apt update
}

# --- Main Execution ---
configure_apt_mirror

echo -e "${GREEN}--- [2/7] Installing essential system packages ---${NC}"
$SUDO_CMD apt install -y git curl unzip python3-pip pipx jq

echo -e "${GREEN}--- [3/7] Installing 'uv' via pipx ---${NC}"
if command -v uv &> /dev/null; then
    echo -e "${YELLOW}'uv' is already installed. Skipping.${NC}"
else
    export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
    pipx ensurepath
    export PATH="$PATH:$HOME/.local/bin" # Add to current session
    pipx install uv --force
    echo -e "${GREEN}✅ 'uv' installed successfully.${NC}"
fi

echo -e "${GREEN}--- [4/7] Installing Sing-box ---${NC}"
if command -v sing-box &> /dev/null; then
    echo -e "${YELLOW}'sing-box' is already installed. Skipping. Current version: $(sing-box version | head -n 1)${NC}"
else
    ARCH=$(uname -m); case "$ARCH" in x86_64) SINGBOX_ARCH="amd64" ;; aarch64|arm64) SINGBOX_ARCH="arm64" ;; *) echo -e "${RED}ERR: Unsupported arch: $ARCH.${NC}"; exit 1 ;; esac
    echo "Arch: $ARCH, Sing-box arch: $SINGBOX_ARCH"
    SINGBOX_LATEST_TAG=$(curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | jq -r '.tag_name')
    if [ -z "$SINGBOX_LATEST_TAG" ] || [ "$SINGBOX_LATEST_TAG" = "null" ]; then echo -e "${RED}ERR: Could not fetch Sing-box tag.${NC}"; exit 1; fi
    echo "Latest Sing-box version is $SINGBOX_LATEST_TAG"
    SINGBOX_FILENAME="sing-box-${SINGBOX_LATEST_TAG#v}-linux-${SINGBOX_ARCH}.tar.gz"
    ACCELERATORS=("https://ghfast.top" "https://ghproxy.com" "https://github.com"); DOWNLOAD_SUCCESS=false
    for acc in "${ACCELERATORS[@]}"; do
        DOWNLOAD_URL="${acc}/https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_LATEST_TAG}/${SINGBOX_FILENAME}"
        echo -e "Trying: ${YELLOW}${DOWNLOAD_URL}${NC}"
        TMP_DIR="/tmp/singbox_$$"; mkdir -p "$TMP_DIR"
        if curl -L --fail -o "$TMP_DIR/$SINGBOX_FILENAME" "$DOWNLOAD_URL"; then
            echo -e "${GREEN}Download successful!${NC}"; DOWNLOAD_SUCCESS=true; break
        else echo -e "${YELLOW}Download failed. Trying next...${NC}"; rm -rf "$TMP_DIR"; fi
    done
    if [ "$DOWNLOAD_SUCCESS" = false ]; then echo -e "${RED}ERR: Failed to download Sing-box.${NC}"; exit 1; fi
    tar -xzf "$TMP_DIR/$SINGBOX_FILENAME" -C "$TMP_DIR"
    $SUDO_CMD mv "$TMP_DIR"/sing-box-*/sing-box /usr/local/bin/
    rm -rf "$TMP_DIR"; echo -e "${GREEN}✅ Sing-box installed successfully.${NC}"
fi

echo -e "${GREEN}--- [5/7] Setting up Python virtual environment (.venv) ---${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment '.venv' already exists. Skipping creation.${NC}"
else
    # Create venv using the system's python3
    python3 -m venv .venv
    echo -e "${GREEN}✅ Virtual environment created successfully.${NC}"
fi

echo -e "${GREEN}--- [6/7] Installing project Python dependencies into .venv ---${NC}"
if [ ! -f "requirements.txt" ]; then
    echo -e "${YELLOW}requirements.txt not found. Creating placeholder...${NC}"
    echo -e "aiohttp\nPyYAML\nrich" > requirements.txt
fi
# Activate the venv and install dependencies with uv
source .venv/bin/activate
echo "Using Python from: $(which python)"
uv pip install -r requirements.txt
echo -e "${GREEN}✅ Python dependencies installed successfully.${NC}"

echo -e "${GREEN}--- [7/7] Finalizing ---${NC}"
mkdir -p results
echo ""
echo -e "${GREEN}✅ --- Installation/Verification Finished Successfully --- ✅${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: A Python virtual environment '.venv' has been set up.${NC}"
echo "To run the script manually, you now have two options:"
echo -e "  1. (Recommended) Activate the environment first:"
echo -e "     ${GREEN}source .venv/bin/activate${NC}"
echo -e "     ${GREEN}python3 main.py${NC}"
echo -e "  2. (Directly) Use the venv's python interpreter:"
echo -e "     ${GREEN}./.venv/bin/python3 main.py${NC}"
echo ""
echo "The 'run.sh' script has been configured to handle this automatically for cron jobs."