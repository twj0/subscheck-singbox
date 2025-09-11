#!/bin/bash
# SubCheck Project - Final Installation Script for Ubuntu 24.04
# - Uses python3-pip and a Tsinghua mirror to reliably install uv.
# - Auto-detects root user to handle sudo correctly.
# - Uses a GitHub accelerator for Xray and --local install for containers.

set -e

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "--- [1/6] Updating system packages ---"
$SUDO_CMD apt update && $SUDO_CMD apt upgrade -y

echo "--- [2/6] Installing essential tools (git, curl, unzip) ---"
$SUDO_CMD apt install -y git curl unzip

echo "--- [3/6] Installing Python and Pip ---"
$SUDO_CMD apt install -y python3-pip

echo "--- [4/6] Configuring Pip and Installing uv ---"
echo "Configuring pip to use Tsinghua University mirror..."
pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

echo "Installing uv using pip..."
pip3 install uv

# Add the local bin directory to PATH for the current session to find uv
export PATH="$HOME/.local/bin:$PATH"
echo "uv installed successfully."

echo "--- [5/6] Installing Xray-core (using GitHub accelerator & --local flag) ---"
XRAY_INSTALL_URL="https://ghfast.top/https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh"
echo "Downloading Xray install script from: $XRAY_INSTALL_URL"
bash -c "$($SUDO_CMD curl -L $XRAY_INSTALL_URL)" -- @ install --local

echo "Xray-core installation complete."

echo "--- [6/6] Installing Project Python dependencies using uv ---"
if [ ! -f "requirements.txt" ]; then
    echo "Creating a placeholder requirements.txt..."
    echo "aiohttp" > requirements.txt
    echo "PyYAML" >> requirements.txt
    echo "rich" >> requirements.txt
fi

echo "Installing Python packages with uv (from Tsinghua mirror)..."
uv pip install -r requirements.txt
mkdir -p results

echo ""
echo "✅ --- Installation Finished Successfully --- ✅"
echo ""
echo "Next steps:"
echo "1. Your environment is now fully prepared."
echo "2. Customize your 'subscription.txt' and 'config.yaml'."
echo "3. Run the main script: python3 main.py"