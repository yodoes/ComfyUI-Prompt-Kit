"""
路径管理：统一插件根目录、内置数据目录、用户数据目录。
"""
from __future__ import annotations

from pathlib import Path


class Paths:
    """插件内所有路径的单一入口。"""

    def __init__(self) -> None:
        # 插件根目录（本文件位于 core/ 下，上一级为包根）
        self.root: Path = Path(__file__).resolve().parent.parent
        self.data: Path = self.root / "data"
        self.dictionary: Path = self.data / "dictionary"
        self.dictionary_nsfw: Path = self.data / "dictionary_nsfw"
        self.library: Path = self.data / "library"
        # 阶段 4 结构化生成（独立于字典）
        self.builder: Path = self.data / "builder"
        self.builder_nsfw: Path = self.data / "builder_nsfw"

        self.user_data: Path = self.root / "user_data"
        self.user_dictionary: Path = self.user_data / "dictionary"
        self.user_library: Path = self.user_data / "library"
        self.user_builder: Path = self.user_data / "builder"
        self.user_builder_nsfw: Path = self.user_data / "builder_nsfw"

        self.settings_file: Path = self.user_data / "settings.json"
        self.favorites_file: Path = self.user_data / "favorites.json"
        self.library_favorites_file: Path = self.user_data / "library_favorites.json"

        self.dictionary_index: Path = self.dictionary / "index.json"
        self.dictionary_nsfw_index: Path = self.dictionary_nsfw / "index.json"
        self.library_index: Path = self.library / "index.json"
        self.library_manifest: Path = self.user_library / "_extract_manifest.json"
        self.builder_index: Path = self.builder / "index.json"
        self.builder_nsfw_index: Path = self.builder_nsfw / "index.json"

        self.web: Path = self.root / "web"

    def ensure_user_dirs(self) -> None:
        """确保用户数据目录存在（首次运行或被删除时自动创建）。"""
        self.user_dictionary.mkdir(parents=True, exist_ok=True)
        self.user_library.mkdir(parents=True, exist_ok=True)
        self.user_builder.mkdir(parents=True, exist_ok=True)
        self.user_builder_nsfw.mkdir(parents=True, exist_ok=True)

    def builder_slot_file(self, slot_id: str, nsfw: bool = False) -> Path:
        """系统精选：某槽位 jsonl 路径。"""
        base = self.builder_nsfw if nsfw else self.builder
        return base / f"{slot_id}.jsonl"

    def user_builder_slot_file(self, slot_id: str, nsfw: bool = False) -> Path:
        """用户覆盖层：某槽位 jsonl 路径。"""
        base = self.user_builder_nsfw if nsfw else self.user_builder
        return base / f"{slot_id}.jsonl"

    def resolve(self, *parts: str) -> Path:
        """相对插件根目录解析路径。"""
        return self.root.joinpath(*parts)


# 模块级单例，方便各处直接 import
paths = Paths()
