"""
ComfyUI-Prompt-Kit
专业级 Prompt 工作台与工具箱（第一阶段骨架）
"""
from __future__ import annotations

__version__ = "0.2.0-dev"

from .core.paths import paths
from .core.settings import settings

# 确保用户目录存在
paths.ensure_user_dirs()
# 预加载一次设置（首次会写出默认 settings.json）
settings.load()

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# 注册 HTTP API（ComfyUI 环境下）
try:
    from .core import api_routes  # noqa: F401
except Exception as e:
    print(f"[Prompt-Kit] API routes not loaded: {e}")

WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
    "__version__",
]

print(f"[Prompt-Kit] v{__version__} loaded | root={paths.root}")
