#!/bin/bash
# SubCheck Project - Final Installation Script for Ubuntu 24.04
# - Auto-detects root user to handle sudo correctly.
# - Uses a GitHub accelerator for both Xray and uv downloads.
# - Installs uv manually to avoid installer script conflicts.
# - Uses --local install for Xray in container environments.

set -e

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "--- [1/5] Updating system packages ---"
$SUDO_CMD apt update && $SUDO_CMD apt upgrade -y

echo "--- [2/5] Installing essential tools (git, curl, unzip) ---"
$SUDO_CMD apt install -y git curl unzip

echo "--- [3/5] Installing uv (a fast Python package installer) ---"
# --- [FIX 5] Manually install uv to bypass problematic installer script ---
# We determine the latest version and architecture, then download and place it manually.
UV_LATEST_INFO=$(curl -s https://api.github.com/repos/astral-sh/uv/releases/latest)
UV_VERSION=$(echo "$UV_LATEST_INFO" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
UV_ARCH="aarch64-unknown-linux-gnu" # Change to x86_64-unknown-linux-gnu if your VPS is Intel/AMD

# Construct the full, correct download URL
ACCELERATED_URL="https://ghfast.top/https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${UV_ARCH}.tar.gz"
echo "Manually downloading uv from: $ACCELERATED_URL"

# Download, extract, and install
curl -L "$ACCELERATED_URL" -o uv.tar.gz
tar -xzf uv.tar.gz
# Ensure the destination directory exists
mkdir -p "$HOME/.local/bin"
# Move the binary to a directory in the PATH
mv "${UV_ARCH}/uv" "$HOME/.local/bin/"
# Clean up
rm -rf uv.tar.gz "${UV_ARCH}"

echo "Activating uv environment..."
source "$HOME/.local/bin/env"
echo "uv installation complete and activated for this session."

echo "--- [4/5] Installing Xray-core (using GitHub accelerator & --local flag) ---"
XRAY_INSTALL_URL="https://ghfast.top/https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh"
echo "Downloading Xray install script from: $XRAY_INSTALL_URL"
bash -c "$($SUDO_CMD curl -L $XRAY_INSTALL_URL)" -- @ install --local

echo "Xray-core installation complete."

echo "--- [5/5] Installing Python dependencies ---"
if [ ! -f "requirements.txt" ]; then
    echo "Creating a placeholder requirements.txt..."
    echo "aiohttp" > requirements.txt
    echo "PyYAML" >> requirements.txt
    echo "rich" >> requirements.txt
fi

echo "Installing Python packages using uv..."
uv pip install -r requirements.txt
mkdir -p results

echo ""
echo "✅ --- Installation Finished Successfully --- ✅"
echo ""
echo "Next steps:"
echo "1. Your environment is now fully prepared."
echo "2. Customize your 'subscription.txt' and 'config.yaml'."
echo "3. Run the main script: python3 main.py"