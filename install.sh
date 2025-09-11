#!/bin/bash
# SubCheck Project - Definitive Installation Script for Ubuntu 24.04
# - Uses `pipx ensurepath` to permanently fix the user's PATH.
# - Downloads the Xray installer to a file before executing to ensure argument integrity.
# - Auto-detects root user, uses GitHub accelerator, and installs Xray locally.

set -e

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
fi

echo "--- [1/6] Updating system packages ---"
$SUDO_CMD apt update && $SUDO_CMD apt upgrade -y

echo "--- [2/6] Installing essential tools (git, curl, unzip, python3-pip) ---"
$SUDO_CMD apt install -y git curl unzip python3-pip

echo "--- [3/6] Installing and configuring pipx ---"
$SUDO_CMD apt install -y pipx
# This command permanently modifies your shell's startup file (e.g., .bashrc)
pipx ensurepath
# Add pipx's path to the current session so the rest of this script works
export PATH="$PATH:$HOME/.local/bin"

echo "--- [4/6] Installing uv using pipx ---"
# Use --force to ensure it overwrites any previous failed attempts
pipx install uv --force
echo "uv installed successfully via pipx."

echo "--- [5/6] Installing Xray-core (Robust Method) ---"
XRAY_INSTALL_URL="https://ghfast.top/https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh"
echo "Downloading Xray install script from: $XRAY_INSTALL_URL"
# --- [FINAL FIX] Download to file first, then execute ---
XRAY_INSTALL_SCRIPT="/tmp/xray_install.sh"
$SUDO_CMD curl -L $XRAY_INSTALL_URL -o $XRAY_INSTALL_SCRIPT
$SUDO_CMD chmod +x $XRAY_INSTALL_SCRIPT
$SUDO_CMD $XRAY_INSTALL_SCRIPT @ install --local
$SUDO_CMD rm $XRAY_INSTALL_SCRIPT

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
echo "IMPORTANT: To use 'uv' and other tools, you must reload your shell:"
echo "Run ONE of these commands:"
echo "  1. source ~/.bashrc"
echo "  2. Log out and log back in."
echo ""
echo "After that, you can run your project with: python3 main.py"