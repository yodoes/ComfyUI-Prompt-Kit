"""
用户设置：读写 user_data/settings.json。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .io_utils import read_json, write_json
from .paths import paths

# 默认设置（第一阶段最小集，后续可扩展）
DEFAULT_SETTINGS: Dict[str, Any] = {
    "version": 1,
    "output_language": "zh",          # zh | en | bilingual
    "separator": ", ",
    "enable_weight": False,
    "default_weight": 1.0,
    "prefix": "",
    "suffix": "",
    "reload_on_change": True,
    "include_nsfw": False,
    "library_join_mode": "newline",
}


class Settings:
    """懒加载 + 缓存的用户设置。"""

    def __init__(self) -> None:
        self._data: Dict[str, Any] | None = None

    def load(self, force: bool = False) -> Dict[str, Any]:
        if self._data is not None and not force:
            return self._data
        paths.ensure_user_dirs()
        raw = read_json(paths.settings_file, default=None)
        if not isinstance(raw, dict):
            self._data = deepcopy(DEFAULT_SETTINGS)
            self.save()
        else:
            merged = deepcopy(DEFAULT_SETTINGS)
            merged.update(raw)
            self._data = merged
        return self._data

    def save(self) -> bool:
        if self._data is None:
            self._data = deepcopy(DEFAULT_SETTINGS)
        paths.ensure_user_dirs()
        return write_json(paths.settings_file, self._data)

    def get(self, key: str, default: Any = None) -> Any:
        data = self.load()
        return data.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        data = self.load()
        data[key] = value
        if auto_save:
            self.save()

    def reset(self) -> None:
        self._data = deepcopy(DEFAULT_SETTINGS)
        self.save()


# 模块级单例
settings = Settings()
