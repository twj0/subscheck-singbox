#!/bin/bash
# SubCheck Project - Final Installation Script for Ubuntu 24.04
# - Auto-detects root user to handle sudo correctly.
# - Uses a GitHub accelerator for both Xray and uv downloads.
# - Installs uv manually in a temporary directory to handle flat archive structure.
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
# --- [FIX 6] Handle flat tarball structure by extracting in a temp directory ---
UV_LATEST_INFO=$(curl -s https://api.github.com/repos/astral-sh/uv/releases/latest)
UV_VERSION=$(echo "$UV_LATEST_INFO" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
UV_ARCH="aarch64-unknown-linux-gnu" # Change to x86_64-unknown-linux-gnu if your VPS is Intel/AMD

ACCELERATED_URL="https://ghfast.top/https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${UV_ARCH}.tar.gz"
echo "Manually downloading uv from: $ACCELERATED_URL"

# Create a temporary directory for clean extraction
mkdir -p /tmp/uv_install
curl -L "$ACCELERATED_URL" -o /tmp/uv_install/uv.tar.gz
# Extract the contents inside the temporary directory
tar -xzf /tmp/uv_install/uv.tar.gz -C /tmp/uv_install/

# Ensure the final destination directory exists
mkdir -p "$HOME/.local/bin"
# Move the uv executable from the temp dir to its final location
mv /tmp/uv_install/uv "$HOME/.local/bin/"
# Clean up the temporary directory
rm -rf /tmp/uv_install

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