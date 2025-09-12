# utils/logger.py
# 作者: subscheck-ubuntu team
import logging
import os
import sys
import subprocess
import datetime
from pathlib import Path
from typing import Optional, Union
from rich.logging import RichHandler
from rich.console import Console

class DebugLogger:
    """
    增强的调试日志器
    支持debug模式、PowerShell输出捕获和文件日志
    """
    
    def __init__(self, debug_mode: bool = False, debug_dir: str = "debug"):
        self.debug_mode = debug_mode
        self.debug_dir = Path(debug_dir)
        self.console = Console()
        
        # 创建debug目录
        if self.debug_mode:
            self.debug_dir.mkdir(exist_ok=True)
            
        # 设置日志级别
        log_level = logging.DEBUG if debug_mode else logging.INFO
        
        # 创建日志格式
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 创建handlers列表
        handlers = []
        
        # Rich控制台handler
        rich_handler = RichHandler(
            console=self.console,
            rich_tracebacks=True,
            show_time=True,
            show_path=debug_mode
        )
        rich_handler.setLevel(log_level)
        handlers.append(rich_handler)
        
        # 如果是debug模式，添加文件handler
        if self.debug_mode:
            # 主日志文件
            main_log_file = self.debug_dir / f"subscheck_debug_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(main_log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
            
            # PowerShell专用日志文件
            self.pwsh_log_file = self.debug_dir / f"pwsh_output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self.pwsh_handler = logging.FileHandler(self.pwsh_log_file, encoding='utf-8')
            self.pwsh_handler.setLevel(logging.DEBUG)
            self.pwsh_handler.setFormatter(formatter)
        
        # 配置根日志器
        logging.basicConfig(
            level=log_level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=handlers,
            force=True
        )
        
        # 获取logger实例
        self.logger = logging.getLogger("subscheck")
        self.pwsh_logger = logging.getLogger("pwsh_output") if debug_mode else None
        
        if self.pwsh_logger and debug_mode:
            self.pwsh_logger.addHandler(self.pwsh_handler)
            self.pwsh_logger.setLevel(logging.DEBUG)
        
        if debug_mode:
            self.logger.debug(f"🐛 Debug模式已启用 - 日志保存至: {self.debug_dir}")
            self.logger.debug(f"📁 主日志文件: {main_log_file}")
            self.logger.debug(f"💻 PowerShell日志文件: {self.pwsh_log_file}")
    
    def log_pwsh_command(self, command: str, capture_output: bool = True) -> Optional[subprocess.CompletedProcess]:
        """
        执行PowerShell命令并记录输出
        
        Args:
            command: PowerShell命令
            capture_output: 是否捕获输出
        
        Returns:
            命令执行结果
        """
        if not self.debug_mode:
            self.logger.warning("PowerShell命令记录功能需要开启debug模式")
            return None
        
        self.logger.debug(f"🔧 执行PowerShell命令: {command}")
        self.pwsh_logger.info(f"COMMAND: {command}")
        
        try:
            # 执行PowerShell命令
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell.exe", "-Command", command],
                    capture_output=capture_output,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            else:
                # Linux环境下使用pwsh（如果可用）
                result = subprocess.run(
                    ["pwsh", "-Command", command],
                    capture_output=capture_output,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
            
            # 记录输出
            self.pwsh_logger.info(f"EXIT_CODE: {result.returncode}")
            
            if result.stdout:
                self.pwsh_logger.info(f"STDOUT:\n{result.stdout}")
                if self.debug_mode:
                    self.logger.debug(f"📤 PowerShell标准输出: {result.stdout.strip()}")
            
            if result.stderr:
                self.pwsh_logger.error(f"STDERR:\n{result.stderr}")
                self.logger.warning(f"⚠️ PowerShell错误输出: {result.stderr.strip()}")
            
            self.pwsh_logger.info("-" * 50)
            
            return result
            
        except FileNotFoundError:
            error_msg = "PowerShell未找到，请确保已安装PowerShell"
            self.logger.error(f"❌ {error_msg}")
            self.pwsh_logger.error(f"ERROR: {error_msg}")
            return None
        except Exception as e:
            error_msg = f"执行PowerShell命令时发生错误: {e}"
            self.logger.error(f"❌ {error_msg}")
            self.pwsh_logger.error(f"EXCEPTION: {error_msg}")
            return None
    
    def save_debug_info(self, info: dict, filename: str = None):
        """
        保存调试信息到文件
        
        Args:
            info: 要保存的调试信息字典
            filename: 文件名（可选）
        """
        if not self.debug_mode:
            return
        
        if filename is None:
            filename = f"debug_info_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        debug_file = self.debug_dir / filename
        
        try:
            import json
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump(info, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.debug(f"💾 调试信息已保存: {debug_file}")
        except Exception as e:
            self.logger.error(f"❌ 保存调试信息失败: {e}")
    
    def get_logger(self) -> logging.Logger:
        """获取主日志器"""
        return self.logger
    
    def get_pwsh_logger(self) -> Optional[logging.Logger]:
        """获取PowerShell日志器"""
        return self.pwsh_logger

# 全局日志器实例
_debug_logger = None

def setup_logger(debug_mode: bool = False, debug_dir: str = "debug") -> DebugLogger:
    """
    配置日志器
    
    Args:
        debug_mode: 是否启用debug模式
        debug_dir: debug文件夹路径
    
    Returns:
        DebugLogger实例
    """
    global _debug_logger
    
    # 检查环境变量
    if not debug_mode:
        debug_mode = os.getenv('SUBSCHECK_DEBUG', '').lower() in ('true', '1', 'yes')
    
    _debug_logger = DebugLogger(debug_mode=debug_mode, debug_dir=debug_dir)
    return _debug_logger

def get_logger() -> logging.Logger:
    """
    获取主日志器实例
    
    Returns:
        logging.Logger实例
    """
    global _debug_logger
    if _debug_logger is None:
        _debug_logger = setup_logger()
    return _debug_logger.get_logger()

def get_debug_logger() -> Optional[DebugLogger]:
    """
    获取调试日志器实例
    
    Returns:
        DebugLogger实例或None
    """
    global _debug_logger
    return _debug_logger

def log_pwsh_command(command: str) -> Optional[subprocess.CompletedProcess]:
    """
    便捷函数：执行并记录PowerShell命令
    
    Args:
        command: PowerShell命令
    
    Returns:
        命令执行结果
    """
    debug_logger = get_debug_logger()
    if debug_logger:
        return debug_logger.log_pwsh_command(command)
    else:
        logger = get_logger()
        logger.warning("PowerShell命令记录需要开启debug模式")
        return None

# 默认日志器（向后兼容）
log = get_logger()
