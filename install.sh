#!/bin/bash
# SubCheck Project - Definitive, Simplified Installation Script
# - Installs uv using the robust pipx method.
# - Bypasses the Xray installer script entirely by downloading the pre-compiled binary.
# - Uses GitHub accelerator for all downloads, making it China-friendly.

set -e

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "--- [1/5] Updating system packages & Installing Dependencies ---"
$SUDO_CMD apt update
$SUDO_CMD apt install -y git curl unzip python3-pip pipx

echo "--- [2/5] Configuring and Installing uv ---"
# This command permanently modifies your shell's startup file (e.g., .bashrc)
pipx ensurepath
# Add pipx's path to the current session so the rest of this script works
export PATH="$PATH:$HOME/.local/bin"
# Use --force to ensure it overwrites any previous failed attempts
pipx install uv --force
echo "✅ uv installed successfully."

echo "--- [3/5] Installing Xray-core Manually (Most Robust Method) ---"
# Get the latest version tag (e.g., v1.8.10) from the GitHub API
XRAY_LATEST_TAG=$(curl -s https://api.github.com/repos/XTLS/Xray-core/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [ -z "$XRAY_LATEST_TAG" ]; then
    echo "❌ ERROR: Could not fetch latest Xray version tag. Check network or API rate limits."
    exit 1
fi
echo "Latest Xray version is $XRAY_LATEST_TAG"

# Construct the download URL for the ARM64 binary
ZIP_FILENAME="Xray-linux-arm64-v8a.zip"
ACCELERATED_URL="https://ghfast.top/https://github.com/XTLS/Xray-core/releases/download/${XRAY_LATEST_TAG}/${ZIP_FILENAME}"
echo "Downloading from: $ACCELERATED_URL"

# Create a temporary directory for a clean installation
TMP_DIR="/tmp/xray_install_$$"
mkdir -p "$TMP_DIR"
curl -L "$ACCELERATED_URL" -o "$TMP_DIR/$ZIP_FILENAME"
unzip -o "$TMP_DIR/$ZIP_FILENAME" -d "$TMP_DIR"

echo "Placing xray binary and data files in system directories..."
# Move the main executable
$SUDO_CMD mv "$TMP_DIR/xray" /usr/local/bin/
# Move the data files to the conventional location
$SUDO_CMD mkdir -p /usr/local/share/xray/
$SUDO_CMD mv "$TMP_DIR/geoip.dat" /usr/local/share/xray/
$SUDO_CMD mv "$TMP_DIR/geosite.dat" /usr/local/share/xray/
# Clean up
rm -rf "$TMP_DIR"
echo "✅ Xray-core installed successfully."

echo "--- [4/5] Installing Project Python dependencies ---"
if [ ! -f "requirements.txt" ]; then
    echo "Creating a placeholder requirements.txt..."
    echo "aiohttp" > requirements.txt
    echo "PyYAML" >> requirements.txt
    echo "rich" >> requirements.txt
fi
echo "Installing Python packages with uv..."
uv pip install -r requirements.txt
mkdir -p results

echo "--- [5/5] Finalizing ---"
echo ""
echo "✅ --- Installation Finished Successfully --- ✅"
echo ""
echo "IMPORTANT: To use 'uv' and 'xray', you must reload your shell:"
echo "Run ONE of these commands:"
echo "  1. source ~/.bashrc"
echo "  2. Log out and log back in."
echo ""
echo "After that, verify with 'uv --version' and 'xray --version'."
echo "Then you can run your project with: python3 main.py"