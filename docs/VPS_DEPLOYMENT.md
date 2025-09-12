# 🚀 VPS部署指南

本指南专门针对**Ubuntu VPS无界面部署**场景，基于GUI项目的经验优化。

## 📋 部署概览

### 核心优势
- **无界面运行** - 专为VPS服务器环境设计
- **Web远程管理** - 替代桌面GUI界面
- **自动化调度** - cron定时任务自动执行
- **结果上传** - 支持多种云端存储方式
- **中国大陆优化** - 针对国内网络环境优化

## 🔧 快速部署

### 1. 连接到VPS
```bash
ssh user@your-vps-ip
```

### 2. 克隆项目
```bash
git clone https://github.com/your-repo/subscheck-ubuntu.git
cd subscheck-ubuntu
```

### 3. 一键部署
```bash
chmod +x setup_vps.sh
./setup_vps.sh
```

这个脚本会自动完成：
- ✅ 安装系统依赖
- ✅ 下载Sing-box
- ✅ 配置Python环境
- ✅ 设置定时任务
- ✅ 配置防火墙
- ✅ 创建系统服务

## 🌐 Web管理界面

### 启动Web界面
```bash
# 使用Gunicorn（推荐生产环境）
./run_web.sh

# 或手动启动
source .venv/bin/activate
gunicorn -w 2 -b 0.0.0.0:8080 web_manager:app
```

### 访问界面
在浏览器中访问：`http://your-vps-ip:8080`

### 功能特性
- 📊 **实时状态监控** - 查看测试进程状态
- ⚙️ **配置管理** - 在线修改测试参数
- 🚀 **手动启动** - 一键触发测试
- 📁 **结果查看** - 下载和查看测试结果

## ⏰ 自动化运行

### 定时任务配置
```bash
# 查看当前定时任务
crontab -l

# 编辑定时任务
crontab -e

# 示例：每6小时执行一次
0 */6 * * * cd /path/to/subscheck-ubuntu && .venv/bin/python main.py >> results/cron.log 2>&1
```

### 系统服务管理
```bash
# 启动服务
sudo systemctl start subscheck

# 停止服务
sudo systemctl stop subscheck

# 查看状态
sudo systemctl status subscheck

# 开机自启
sudo systemctl enable subscheck
```

## 📤 结果管理

### 本地保存（默认）
- 结果保存在 `results/` 目录
- 自动生成时间戳文件名
- 保留最新结果副本供Web界面使用

### GitHub Gist上传
在 `config.yaml` 中配置：
```yaml
vps_settings:
  upload_settings:
    enabled: true
    type: "gist"
    gist:
      token: "your_github_token"
      public: false
```

### Webhook上传
```yaml
vps_settings:
  upload_settings:
    enabled: true
    type: "webhook"
    webhook:
      url: "https://your-webhook-url.com/endpoint"
      headers:
        "Content-Type": "application/json"
        "Authorization": "Bearer your-token"
```

## 🔧 配置优化

### VPS网络优化
```yaml
vps_settings:
  network_optimization:
    dns_servers:
      - "223.5.5.5"      # 阿里DNS
      - "114.114.114.114" # 114DNS
    connect_timeout: 15
    read_timeout: 30
```

### 测试参数调优
```yaml
general_settings:
  max_nodes_to_test: 50  # 适合VPS资源
  concurrency: 5         # 避免过度并发

test_settings:
  timeout: 15            # 增加超时适应国内网络
  speed_test_duration: 10
```

## 📝 日志管理

### 查看日志
```bash
# 查看最新日志
tail -f results/cron.log

# 查看特定时间的日志
ls results/app_*.log

# 清理旧日志（保留最近7天）
find results/ -name "*.log" -mtime +7 -delete
```

### 日志轮转配置
```bash
# 创建logrotate配置
sudo tee /etc/logrotate.d/subscheck > /dev/null <<EOF
/path/to/subscheck-ubuntu/results/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
    create 644 user user
}
EOF
```

## 🔒 安全配置

### 防火墙设置
```bash
# Ubuntu UFW
sudo ufw allow 8080/tcp
sudo ufw enable

# CentOS FirewallD
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### Web界面访问控制
在 `config.yaml` 中设置访问令牌：
```yaml
vps_settings:
  web_interface:
    auth_token: "your-secure-token"
```

## 🚨 故障排除

### 常见问题

#### 1. Web界面无法访问
```bash
# 检查服务状态
sudo netstat -tlnp | grep 8080

# 检查防火墙
sudo ufw status
```

#### 2. 定时任务不执行
```bash
# 检查cron服务
sudo systemctl status cron

# 查看cron日志
sudo tail -f /var/log/cron
```

#### 3. Sing-box下载失败
```bash
# 手动下载
wget https://ghfast.top/https://github.com/SagerNet/sing-box/releases/download/v1.12.5/sing-box-1.12.5-linux-amd64.tar.gz
```

### 性能优化

#### 内存使用优化
```yaml
general_settings:
  max_nodes_to_test: 30  # 减少节点数
  concurrency: 3         # 降低并发数
```

#### 磁盘空间管理
```bash
# 自动清理脚本
cat > cleanup_results.sh <<'EOF'
#!/bin/bash
# 保留最近10个结果文件
cd /path/to/subscheck-ubuntu/results
ls -t *.json | tail -n +11 | xargs rm -f
EOF

chmod +x cleanup_results.sh

# 添加到crontab（每天凌晨清理）
0 0 * * * /path/to/subscheck-ubuntu/cleanup_results.sh
```

## 📊 监控和维护

### 系统监控
```bash
# 监控资源使用
htop

# 监控网络连接
sudo netstat -tulnp

# 监控磁盘使用
df -h
```

### 定期维护
- 每周检查日志文件大小
- 每月更新系统和依赖包
- 定期备份配置文件和重要结果

## 🔄 更新升级

### 更新项目代码
```bash
cd subscheck-ubuntu
git pull origin main

# 重新安装依赖（如有变化）
source .venv/bin/activate
uv pip install -r requirements.txt

# 重启服务
sudo systemctl restart subscheck
```

### 更新Sing-box
```bash
# 下载新版本
./setup_vps.sh  # 重新运行部署脚本

# 或手动更新
rm -rf sing-box-*
# 然后重新下载最新版本
```

---

## 📞 支持

如遇到问题，请检查：
1. [故障排除文档](TROUBLESHOOTING.md)
2. [调试指南](DEBUGGING_WINDOWS.md)
3. 项目Issues页面

**VPS部署完成后，您就可以享受全自动的代理节点测试服务了！** 🎉