#!/bin/bash
# SubCheck Project - Enhanced Installation Script for Ubuntu 24.04
# - Auto-detects root user to handle sudo correctly.
# - Uses a GitHub accelerator for better reliability in mainland China.
# - Fixes the incorrect path for the uv environment.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- [FIX 1] Auto-detect sudo requirement ---
# Check if the user is root. If so, SUDO_CMD is empty. Otherwise, it's "sudo".
SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO_CMD="sudo"
  echo "Running as non-root user. Using 'sudo' for administrative commands."
  # Check if sudo is installed
  if ! command -v sudo &> /dev/null; then
    echo "'sudo' could not be found. Please install it or run this script as root."
    exit 1
  fi
fi

echo "--- [1/5] Updating system packages ---"
$SUDO_CMD apt update && $SUDO_CMD apt upgrade -y

echo "--- [2/5] Installing essential tools (git, curl, unzip) ---"
$SUDO_CMD apt install -y git curl unzip

echo "--- [3/5] Installing uv (a fast Python package installer) ---"
curl -LsSf https://astral.sh/uv/install.sh | sh

# --- [FIX 2] Correctly source the uv environment path ---
# The uv installer explicitly tells us to use this path.
echo "Activating uv environment..."
source "$HOME/.local/bin/env"

echo "uv installation complete and activated for this session."

echo "--- [4/5] Installing Xray-core (using GitHub accelerator) ---"
# --- [FIX 3] Use ghfast.top to accelerate the download ---
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
# uv doesn't need sudo as it installs into the user's environment
uv pip install -r requirements.txt

# Create results directory if it doesn't exist
mkdir -p results

echo ""
echo " --- Installation Finished Successfully --- "
echo ""
echo "Next steps:"
echo "1. Your project is already cloned and dependencies are installed."
echo "2. Customize your 'subscription.txt' and 'config.yaml'."
echo "3. Run the main script: python3 main.py"