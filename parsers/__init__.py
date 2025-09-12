# parsers模块初始化
# 作者: subscheck-ubuntu team

from .base_parser import parse_node_url
from .clash_parser import parse_clash_config

__all__ = ['parse_node_url', 'parse_clash_config']