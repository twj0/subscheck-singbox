#!/bin/bash
# SubCheck Project - Final Installation Script for Ubuntu 24.04
# - Correctly handles PEP 668 by using pipx to install uv.
# - Uses a robust `bash -s` pipe for Xray installation.
# - Uses a GitHub accelerator for Xray and --local install for containers.

set -e

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "--- [1/6] Updating system packages ---"
$SUDO_CMD apt update && $SUDO_CMD apt upgrade -y

echo "--- [2/6] Installing essential tools (git, curl, unzip, python3-pip) ---"
$SUDO_CMD apt install -y git curl unzip python3-pip

echo "--- [3/6] Installing pipx ---"
$SUDO_CMD apt install -y pipx
# Add pipx's path to the current session
export PATH="$PATH:$HOME/.local/bin"

echo "--- [4/6] Installing uv using pipx ---"
pipx install uv
echo "uv installed successfully via pipx."

echo "--- [5/6] Installing Xray-core (using GitHub accelerator & --local flag) ---"
XRAY_INSTALL_URL="https://ghfast.top/https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh"
echo "Downloading Xray install script from: $XRAY_INSTALL_URL"
# --- [FINAL FIX] Use a more robust bash pipe for execution ---
$SUDO_CMD curl -L $XRAY_INSTALL_URL | $SUDO_CMD bash -s -- @ install --local

echo "Xray-core installation complete."

echo "--- [6/6] Installing Project Python dependencies using uv ---"
if [ ! -f "requirements.txt" ]; then
    echo "Creating a placeholder requirements.txt..."
    echo "aiohttp" > requirements.txt
    echo "PyYAML" >> requirements.txt
    echo "rich" >> requirements.txt
fi

echo "Installing Python packages with uv..."
uv pip install -r requirements.txt
mkdir -p results

echo ""
echo "✅ --- Installation Finished Successfully --- ✅"
echo ""
echo "Next steps:"
echo "1. Your environment is now fully prepared."
echo "2. Customize your 'subscription.txt' and 'config.yaml'."
echo "3. Run the main script: python3 main.py"