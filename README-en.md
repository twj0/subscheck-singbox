# SubsCheck-Ubuntu User Guide

## 🚀 Project Overview

SubsCheck-Ubuntu is a high-performance proxy node speed testing tool based on Sing-box, optimized for Ubuntu VPS environments and also supporting local development.

### ✨ Core Features

- **Multi-Protocol Support**: Parses major protocols like VLESS, VMess, Trojan, and Shadowsocks.
- **High-Performance Speed Testing**: Based on the `sing-box` core, providing accurate HTTP latency and real download speed tests.
- **Automation of Results**:
    - **Upload Test Results**: Upload detailed test results in JSON format to Gist, WebDAV, or send via Webhook.
    - **Backup Available Nodes**: Generate a new subscription file from all successful nodes and upload it to Gist or WebDAV for direct use in clients.
- **Scheduled Tasks**: Supports daily automatic speed tests and uploads via `cron` or the built-in scheduler.
- **Environment Security**: Manages sensitive information through a `.env` file to avoid hardcoding credentials in configuration files.

## 🛠️ How to Use

### Local Development (uv Recommended)

```bash
# 1. Install dependencies (uv will automatically create a virtual environment)
uv pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit the .env file to add your credentials for Gist, WebDAV, etc.

# 3. Configure config.yaml
# Enable and configure upload_settings and subscription_backup according to your needs

# 4. Run the program
uv run python main.py

# 5. Run with specific parameters
uv run python main.py -s my_subscription.txt -n 20

# 6. Enable debug mode
uv run python main.py -d
```

### Remote VPS Deployment

```bash
# 1. One-click installation and configuration
chmod +x install.sh
./install.sh

# 2. Configure environment variables
cp .env.example .env
# Edit the .env file

# 3. Run the program
./run.sh

# Or run manually
source .venv/bin/activate
python main.py
```

## ⚙️ Configuration Files

### `.env` (Environment Variables)

Used to store all sensitive information, such as API tokens and passwords.

```env
# Gist Configuration
GIST_TOKEN="your_github_token"
GIST_ID="your_gist_id"

# WebDAV Configuration for Result Uploads
WEBDAV_HOSTNAME="https://your.webdav.host/dav/"
WEBDAV_USERNAME="your_username"
WEBDAV_PASSWORD="your_password"

# WebDAV Configuration for Subscription Backup
WEBDAV_BACKUP_HOSTNAME="https://your.webdav.host/dav/"
WEBDAV_BACKUP_USERNAME="your_username"
WEBDAV_BACKUP_PASSWORD="your_password"
```

### `config.yaml` (Main Configuration)

Configure the program's behavior in this file, such as speed test parameters and upload destinations. All sensitive information should be referenced from the `.env` file using the `${VAR_NAME}` format.

```yaml
# Result Upload Settings
upload_settings:
  enabled: false
  type: "webdav"  # Options: local, gist, webhook, webdav, r2
  
  webdav:
    enabled: true
    hostname: "${WEBDAV_HOSTNAME}"
    username: "${WEBDAV_USERNAME}"
    password: "${WEBDAV_PASSWORD}"
    remote_path: "subscheck_results.json"

# Subscription Backup Settings
subscription_backup:
  enabled: false
  
  gist:
    enabled: false
    token: "${GIST_TOKEN}"
    gist_id: "${GIST_ID}"
    filename: "subscheck_backup.txt"
```

### `subscription.txt` (Subscription Sources)

Add your subscription links to this file, one per line.

```
https://example.com/subscription1
https://example.com/subscription2
```

## 📦 Project Structure

```
subscheck-ubuntu/
├── core/
│   └── singbox_runner.py       # sing-box core interface
├── parsers/
│   └── ...                     # Protocol parsers
├── testers/
│   └── node_tester.py          # Node testing logic
├── utils/
│   ├── config_utils.py         # Environment variable parser
│   ├── uploader.py             # Result upload module
│   └── subscription_backup.py  # Subscription backup module
├── .env                        # Environment variables (private)
├── .env.example                # Environment variable example
├── config.yaml                 # Core configuration
├── main.py                     # Main program entry point
├── requirements.txt            # Dependency list
└── install.sh                  # VPS auto-install script
```
