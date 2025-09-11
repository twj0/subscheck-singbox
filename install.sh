#!/bin/bash
# SubCheck Project - Installation Script for Ubuntu 24.04
# This script installs all necessary dependencies: git, uv, xray, and python packages.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- [1/5] Updating system packages ---"
sudo apt update && sudo apt upgrade -y

echo "--- [2/5] Installing essential tools (git, curl, unzip) ---"
sudo apt install -y git curl unzip

echo "--- [3/5] Installing uv (a fast Python package installer) ---"
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.cargo/env"
echo "uv installation complete. Run 'source ~/.bashrc' or restart your terminal to use it."

echo "--- [4/5] Installing Xray-core ---"
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
echo "Xray-core installation complete."

echo "--- [5/5] Creating project structure and installing Python dependencies ---"
# This part assumes you will clone your git repo. We'll create a placeholder requirements.txt
# In your actual project, this file will exist in the repo.
if [ ! -f "requirements.txt" ]; then
    echo "Creating a placeholder requirements.txt..."
    echo "aiohttp" > requirements.txt
    echo "PyYAML" >> requirements.txt
    echo "rich" >> requirements.txt
fi

echo "Installing Python packages using uv..."
uv pip install -r requirements.txt

# Create results directory
mkdir -p results

echo "--- Installation Finished ---"
echo "Next steps:"
echo "1. Clone your project from GitHub: git clone <your-repo-url>"
echo "2. Navigate into your project directory: cd <your-repo-name>"
echo "3. Customize your 'subscription.txt' and 'config.yaml'."
echo "4. Run the main script: python3 main.py"