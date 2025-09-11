#!/bin/bash
# SubCheck Project - Enhanced Installation Script for Ubuntu
# Optimized for Mainland China network environments and improved stability.

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
  echo -e "${YELLOW}Sudo privileges will be required for system-wide installations.${NC}"
fi

# --- Function Definitions ---

# Function to configure APT mirrors to Aliyun
configure_apt_mirror() {
    echo -e "${GREEN}--- [1/5] Configuring APT to use Aliyun mirrors ---${NC}"
    if grep -q "mirrors.aliyun.com" /etc/apt/sources.list; then
        echo -e "${YELLOW}Aliyun APT mirror already configured. Skipping.${NC}"
    else
        echo "Backing up original sources.list to /etc/apt/sources.list.bak..."
        $SUDO_CMD cp /etc/apt/sources.list /etc/apt/sources.list.bak
        echo "Replacing APT sources with Aliyun mirrors..."
        $SUDO_CMD sed -i 's/http:\/\/ports.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
        $SUDO_CMD sed -i 's/http:\/\/archive.ubuntu.com/http:\/\/mirrors.aliyun.com/g' /etc/apt/sources.list
        echo "APT mirror configured."
    fi
    echo "Updating package lists..."
    $SUDO_CMD apt update
}

# --- Main Execution ---

# Step 1: Configure Mirrors and Install System Dependencies
configure_apt_mirror
echo -e "${GREEN}--- [2/5] Installing essential system packages ---${NC}"
$SUDO_CMD apt install -y git curl unzip python3-pip pipx

# Step 2: Configure Python Environment using Domestic Mirrors
echo -e "${GREEN}--- [3/5] Configuring and Installing 'uv' via pipx ---${NC}"
# Set environment variables for pip to use Tsinghua mirror. This affects pipx and uv.
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
pipx ensurepath
export PATH="$PATH:$HOME/.local/bin"
pipx install uv --force
echo -e "${GREEN}✅ 'uv' installed successfully via Tsinghua mirror.${NC}"

# Step 3: Install Xray-core with Architecture Detection and Resilient Download
echo -e "${GREEN}--- [4/5] Installing Xray-core with smart download ---${NC}"
# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ZIP_FILENAME="Xray-linux-64.zip" ;;
    aarch64|arm64) ZIP_FILENAME="Xray-linux-arm64-v8a.zip" ;;
    *)
        echo -e "${RED}ERROR: Unsupported architecture: $ARCH. Exiting.${NC}"
        exit 1
        ;;
esac
echo "Detected architecture: $ARCH. Target file: $ZIP_FILENAME"

# Get latest version tag from GitHub API
XRAY_LATEST_TAG=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [ -z "$XRAY_LATEST_TAG" ]; then
    echo -e "${RED}ERROR: Could not fetch latest Xray version tag. Check network or API rate limits.${NC}"
    exit 1
fi
echo "Latest Xray version is $XRAY_LATEST_TAG"

# Array of GitHub accelerators to try in order
ACCELERATORS=(
    "https://ghfast.top"
    "https://gh-proxy.com"
    "https://gh.api.99988866.xyz"
    "https://github.com" # Direct download as a last resort
)
DOWNLOAD_SUCCESS=false

for acc in "${ACCELERATORS[@]}"; do
    DOWNLOAD_URL="${acc}/https://github.com/XTLS/Xray-core/releases/download/${XRAY_LATEST_TAG}/${ZIP_FILENAME}"
    echo -e "Attempting to download from: ${YELLOW}${DOWNLOAD_URL}${NC}"
    
    TMP_DIR="/tmp/xray_install_$$"
    mkdir -p "$TMP_DIR"
    
    # Use curl with --fail to error out on 404s, and a timeout to prevent getting stuck
    if curl -L --fail --speed-limit 10240 --speed-time 10 "$DOWNLOAD_URL" -o "$TMP_DIR/$ZIP_FILENAME"; then
        echo -e "${GREEN}Download successful!${NC}"
        DOWNLOAD_SUCCESS=true
        break
    else
        echo -e "${YELLOW}Download failed from $acc. Trying next accelerator...${NC}"
        rm -rf "$TMP_DIR" # Clean up failed attempt
    fi
done

if [ "$DOWNLOAD_SUCCESS" = false ]; then
    echo -e "${RED}ERROR: Failed to download Xray from all available accelerators. Please check your network.${NC}"
    exit 1
fi

echo "Installing Xray..."
unzip -o "$TMP_DIR/$ZIP_FILENAME" -d "$TMP_DIR"
$SUDO_CMD mv "$TMP_DIR/xray" /usr/local/bin/
$SUDO_CMD mkdir -p /usr/local/share/xray/
$SUDO_CMD mv "$TMP_DIR/geoip.dat" /usr/local/share/xray/
$SUDO_CMD mv "$TMP_DIR/geosite.dat" /usr/local/share/xray/
rm -rf "$TMP_DIR"
echo -e "${GREEN}✅ Xray-core installed successfully.${NC}"

# Step 4: Install Python Project Dependencies
echo -e "${GREEN}--- [5/5] Installing project Python dependencies ---${NC}"
if [ ! -f "requirements.txt" ]; then
    echo -e "${YELLOW}requirements.txt not found. Creating a placeholder...${NC}"
    echo -e "aiohttp\nPyYAML\nrich" > requirements.txt
fi
echo "Installing Python packages with uv (using Tsinghua mirror)..."
uv pip install -r requirements.txt --system
mkdir -p results

# --- Final Instructions ---
echo ""
echo -e "${GREEN}✅ --- Installation Finished Successfully --- ✅${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: To use the newly installed commands ('uv', 'xray'), you must reload your shell.${NC}"
echo "Run ONE of the following commands:"
echo -e "  1. ${GREEN}source ~/.bashrc${NC} (or ~/.zshrc if you use zsh)"
echo -e "  2. ${GREEN}Log out and log back into your VPS.${NC}"
echo ""
echo "After reloading, you can verify the installations with 'uv --version' and 'xray version'."
echo "Then, run your project using: ${GREEN}python3 main.py${NC}"