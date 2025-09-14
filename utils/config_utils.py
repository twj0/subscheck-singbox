#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置工具模块
"""
import os
import re
from typing import Any, Dict, List

def parse_env_variables(config: Any) -> Any:
    """
    递归解析配置中的环境变量占位符 ${VAR_NAME}
    """
    if isinstance(config, dict):
        for key, value in config.items():
            config[key] = parse_env_variables(value)
    elif isinstance(config, list):
        for i, item in enumerate(config):
            config[i] = parse_env_variables(item)
    elif isinstance(config, str):
        # 正则匹配 ${VAR_NAME}
        match = re.match(r'^\$\{(.*)\}$', config)
        if match:
            var_name = match.group(1)
            return os.getenv(var_name, '') # 如果环境变量不存在，返回空字符串
    return config