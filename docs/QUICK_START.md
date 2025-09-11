# SubCheck 快速运行指南

## 🚀 开始调试

### 1. 网络连接测试（推荐首先运行）
```powershell
python network_test.py
```
这会测试你的网络连接和DNS解析是否正常。

### 2. 调试模式运行
```powershell
python run_debug.py
```
这会使用简化设置运行程序，便于调试。

### 3. 正常运行
```powershell
python main.py
```

## 📁 重要文件说明

- `subscription_debug.txt` - 简化的订阅列表，用于调试
- `TROUBLESHOOTING.md` - 详细的问题诊断指南
- `debug/` - 包含详细的运行日志

## 💡 快速修复建议

如果遇到网络连接问题：

1. **检查网络**：确保能正常访问 GitHub 和 Google
2. **更换DNS**：尝试使用 8.8.8.8 或 1.1.1.1
3. **使用代理**：在网络受限环境下可能需要代理

## 🎯 预期结果

成功运行后，你应该看到：
- 节点解析统计
- 测试进度显示
- 最终的速度和延迟排行榜
- 结果保存在 `results/` 目录