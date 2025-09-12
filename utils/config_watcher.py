#!/usr/bin/env python3
"""
配置文件热重载模块
学习Go版本的配置监控机制
"""
import asyncio
import yaml
from pathlib import Path
from typing import Callable, Any, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils.logger import log

class ConfigHandler(FileSystemEventHandler):
    """配置文件变化处理器"""
    
    def __init__(self, config_path: Path, callback: Callable[[Dict[str, Any]], None]):
        self.config_path = config_path
        self.callback = callback
        self.last_modified = 0
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # 检查是否是我们关心的配置文件
        if Path(event.src_path).resolve() == self.config_path.resolve():
            # 防止重复触发
            import time
            current_time = time.time()
            if current_time - self.last_modified < 1.0:  # 1秒内只触发一次
                return
            self.last_modified = current_time
            
            try:
                log.info(f"检测到配置文件变化: {event.src_path}")
                self.reload_config()
            except Exception as e:
                log.error(f"重载配置文件失败: {e}")
    
    def reload_config(self):
        """重新加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            # 验证配置有效性
            if self.validate_config(new_config):
                self.callback(new_config)
                log.info("配置文件重载成功")
            else:
                log.error("配置文件格式无效，忽略此次变更")
                
        except Exception as e:
            log.error(f"读取配置文件失败: {e}")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """验证配置文件有效性"""
        try:
            required_sections = ['general_settings', 'test_settings', 'output_settings']
            for section in required_sections:
                if section not in config:
                    log.error(f"配置文件缺少必需部分: {section}")
                    return False
            
            # 验证关键参数
            general = config['general_settings']
            if 'max_nodes_to_test' not in general or 'concurrency' not in general:
                log.error("general_settings缺少必需参数")
                return False
                
            return True
            
        except Exception as e:
            log.error(f"配置验证失败: {e}")
            return False

class ConfigWatcher:
    """配置文件监控器"""
    
    def __init__(self, config_path: str, callback: Callable[[Dict[str, Any]], None]):
        self.config_path = Path(config_path)
        self.callback = callback
        self.observer = Observer()
        self.handler = ConfigHandler(self.config_path, callback)
        
    def start(self):
        """开始监控"""
        if not self.config_path.exists():
            log.error(f"配置文件不存在: {self.config_path}")
            return False
            
        # 监控配置文件所在目录
        watch_dir = self.config_path.parent
        self.observer.schedule(self.handler, str(watch_dir), recursive=False)
        self.observer.start()
        
        log.info(f"开始监控配置文件: {self.config_path}")
        return True
    
    def stop(self):
        """停止监控"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            log.info("配置文件监控已停止")

# 全局配置管理器
class GlobalConfigManager:
    """全局配置管理器"""
    
    def __init__(self):
        self.config = {}
        self.watcher = None
        self.update_callbacks = []
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        return self.config
    
    def start_watching(self, config_path: str):
        """开始监控配置文件"""
        def on_config_changed(new_config):
            old_config = self.config.copy()
            self.config = new_config
            
            # 通知所有回调函数
            for callback in self.update_callbacks:
                try:
                    callback(old_config, new_config)
                except Exception as e:
                    log.error(f"配置更新回调失败: {e}")
        
        self.watcher = ConfigWatcher(config_path, on_config_changed)
        return self.watcher.start()
    
    def stop_watching(self):
        """停止监控"""
        if self.watcher:
            self.watcher.stop()
    
    def add_update_callback(self, callback: Callable[[Dict, Dict], None]):
        """添加配置更新回调"""
        self.update_callbacks.append(callback)
    
    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self.config

# 全局实例
config_manager = GlobalConfigManager()