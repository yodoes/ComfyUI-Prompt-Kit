"""
字典数据服务：懒加载、搜索、收藏、用户自定义词条。

约定：
- 内置数据只读（data/dictionary/）
- 用户数据可写（user_data/dictionary/ + favorites.json）
- 默认不加载 14_misc_custom（素材池），可通过 include_misc=True 打开
- 词条字段：id, text, text_zh, category, subcategory, tags, nsfw, source
"""
from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .io_utils import read_json, read_jsonl, write_json, write_jsonl
from .paths import paths


# 默认排除的素材池大类
MISC_CATEGORY_ID = "14_misc_custom"


class DictionaryService:
    """按中类懒加载的字典服务（单例使用）。"""

    def __init__(self) -> None:
        self._index: Optional[Dict[str, Any]] = None
        # subcategory_id -> list[entry]
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        # subcategory_id -> mtime 用于简单失效（用户文件）
        self._cache_mtime: Dict[str, float] = {}
        self._favorites: Optional[Dict[str, Any]] = None
        self._user_overrides: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # Index / tree
    # ------------------------------------------------------------------

    def load_index(self, force: bool = False) -> Dict[str, Any]:
        if self._index is not None and not force:
            return self._index
        data = read_json(paths.dictionary_index, default={})
        if not isinstance(data, dict) or "categories" not in data:
            data = {"version": 1, "categories": []}
        self._index = data
        self._loaded_at = time.time()
        return self._index

    def get_category_tree(
        self,
        include_misc: bool = False,
        language: str = "zh",
    ) -> List[Dict[str, Any]]:
        """返回用于 UI 的分类树（仅元数据，不含词条）。"""
        index = self.load_index()
        tree: List[Dict[str, Any]] = []
        for cat in index.get("categories", []):
            cid = cat.get("id", "")
            if not include_misc and cid == MISC_CATEGORY_ID:
                continue
            name = cat.get("name_zh") if language == "zh" else cat.get("name_en")
            children = []
            for ch in cat.get("children", []):
                ch_name = ch.get("name_zh") if language == "zh" else ch.get("name_en")
                children.append(
                    {
                        "id": ch.get("id"),
                        "name": ch_name or ch.get("id"),
                        "file": ch.get("file"),
                    }
                )
            tree.append(
                {
                    "id": cid,
                    "name": name or cid,
                    "order": cat.get("order", 0),
                    "children": children,
                }
            )
        tree.sort(key=lambda x: x.get("order", 0))
        return tree

    def list_subcategory_ids(self, include_misc: bool = False) -> List[str]:
        ids: List[str] = []
        for cat in self.get_category_tree(include_misc=include_misc):
            for ch in cat.get("children", []):
                if ch.get("id"):
                    ids.append(ch["id"])
        return ids

    def _find_subcategory_meta(self, subcategory_id: str) -> Optional[Dict[str, Any]]:
        index = self.load_index()
        for cat in index.get("categories", []):
            for ch in cat.get("children", []):
                if ch.get("id") == subcategory_id:
                    meta = dict(ch)
                    meta["category_id"] = cat.get("id")
                    return meta
        return None

    # ------------------------------------------------------------------
    # Lazy load entries
    # ------------------------------------------------------------------

    def _builtin_path(self, subcategory_id: str) -> Optional[Any]:
        meta = self._find_subcategory_meta(subcategory_id)
        if not meta or not meta.get("file"):
            return None
        return paths.dictionary / meta["file"]

    def _user_path(self, subcategory_id: str) -> Any:
        # 用户自定义：user_data/dictionary/<subcategory_id>.jsonl
        return paths.user_dictionary / f"{subcategory_id}.jsonl"

    def load_subcategory(
        self,
        subcategory_id: str,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """加载单个中类：内置 + 用户覆盖合并（用户同 id 覆盖内置）。"""
        if not force and subcategory_id in self._cache:
            return self._cache[subcategory_id]

        builtin_path = self._builtin_path(subcategory_id)
        entries: List[Dict[str, Any]] = []
        if builtin_path is not None and builtin_path.is_file():
            entries = read_jsonl(builtin_path)

        user_path = self._user_path(subcategory_id)
        user_entries = read_jsonl(user_path) if user_path.is_file() else []

        # 合并：以 id 为键，用户优先
        by_id: Dict[str, Dict[str, Any]] = {}
        for e in entries:
            eid = e.get("id")
            if eid:
                by_id[eid] = e
        for e in user_entries:
            eid = e.get("id")
            if eid:
                by_id[eid] = e
            else:
                # 无 id 的用户条目直接追加
                by_id[f"user_{uuid.uuid4().hex[:8]}"] = e

        merged = list(by_id.values())
        self._cache[subcategory_id] = merged
        return merged

    def unload_subcategory(self, subcategory_id: str) -> None:
        self._cache.pop(subcategory_id, None)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_mtime.clear()
        self._favorites = None
        self._user_overrides = None
        self._index = None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        subcategory_ids: Optional[Iterable[str]] = None,
        tags: Optional[Iterable[str]] = None,
        include_misc: bool = False,
        language: str = "both",  # zh | en | both
        limit: int = 200,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        在指定中类（或全部正式分类）中搜索。
        query 匹配 text / text_zh / id / tags。
        """
        q = (query or "").strip()
        if not q and not tags:
            return []

        if not case_sensitive:
            q = q.lower()

        tag_set: Set[str] = set()
        if tags:
            for t in tags:
                t = (t or "").strip()
                if t:
                    tag_set.add(t.lower() if not case_sensitive else t)

        if subcategory_ids is None:
            sub_ids = self.list_subcategory_ids(include_misc=include_misc)
        else:
            sub_ids = list(subcategory_ids)

        results: List[Dict[str, Any]] = []
        for sid in sub_ids:
            for entry in self.load_subcategory(sid):
                if self._match_entry(entry, q, tag_set, language, case_sensitive):
                    results.append(entry)
                    if len(results) >= limit:
                        return results
        return results

    def _match_entry(
        self,
        entry: Dict[str, Any],
        q: str,
        tag_set: Set[str],
        language: str,
        case_sensitive: bool,
    ) -> bool:
        if tag_set:
            entry_tags = entry.get("tags") or []
            if not isinstance(entry_tags, list):
                entry_tags = []
            norm_tags = {
                (t.lower() if not case_sensitive else t)
                for t in entry_tags
                if isinstance(t, str)
            }
            if not tag_set.issubset(norm_tags):
                return False

        if not q:
            return True

        fields: List[str] = []
        if language in ("en", "both"):
            fields.append(str(entry.get("text") or ""))
        if language in ("zh", "both"):
            fields.append(str(entry.get("text_zh") or ""))
        fields.append(str(entry.get("id") or ""))
        # tags 也参与文本搜索
        for t in entry.get("tags") or []:
            if isinstance(t, str):
                fields.append(t)

        haystack = " ".join(fields)
        if not case_sensitive:
            haystack = haystack.lower()
        return q in haystack

    def get_entries_by_subcategory(
        self,
        subcategory_id: str,
        *,
        limit: int = 0,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        entries = self.load_subcategory(subcategory_id)
        if offset:
            entries = entries[offset:]
        if limit and limit > 0:
            entries = entries[:limit]
        return entries

    def get_entry_by_id(self, entry_id: str, include_misc: bool = False) -> Optional[Dict[str, Any]]:
        for sid in self.list_subcategory_ids(include_misc=include_misc):
            for e in self.load_subcategory(sid):
                if e.get("id") == entry_id:
                    return e
        return None

    # ------------------------------------------------------------------
    # Display text helper
    # ------------------------------------------------------------------

    @staticmethod
    def display_text(entry: Dict[str, Any], language: str = "zh") -> str:
        """按语言偏好取展示/输出文本。"""
        text = (entry.get("text") or "").strip()
        text_zh = (entry.get("text_zh") or "").strip()
        if language == "zh":
            return text_zh or text
        if language == "en":
            return text or text_zh
        # bilingual
        if text_zh and text and text_zh != text:
            return f"{text_zh} ({text})"
        return text_zh or text

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------

    def load_favorites(self, force: bool = False) -> Dict[str, Any]:
        if self._favorites is not None and not force:
            return self._favorites
        paths.ensure_user_dirs()
        data = read_json(paths.favorites_file, default=None)
        if not isinstance(data, dict):
            data = {"version": 1, "entries": [], "tags": {}}
        data.setdefault("version", 1)
        data.setdefault("entries", [])  # list of entry ids
        data.setdefault("tags", {})  # entry_id -> [tag, ...]
        self._favorites = data
        return self._favorites

    def save_favorites(self) -> bool:
        if self._favorites is None:
            self.load_favorites()
        paths.ensure_user_dirs()
        return write_json(paths.favorites_file, self._favorites)

    def list_favorites(self) -> List[str]:
        fav = self.load_favorites()
        return list(fav.get("entries") or [])

    def is_favorite(self, entry_id: str) -> bool:
        return entry_id in set(self.list_favorites())

    def add_favorite(self, entry_id: str) -> bool:
        fav = self.load_favorites()
        entries: List[str] = list(fav.get("entries") or [])
        if entry_id not in entries:
            entries.append(entry_id)
            fav["entries"] = entries
            return self.save_favorites()
        return True

    def remove_favorite(self, entry_id: str) -> bool:
        fav = self.load_favorites()
        entries: List[str] = list(fav.get("entries") or [])
        if entry_id in entries:
            entries = [e for e in entries if e != entry_id]
            fav["entries"] = entries
            return self.save_favorites()
        return True

    def toggle_favorite(self, entry_id: str) -> bool:
        """返回切换后是否处于收藏状态。"""
        if self.is_favorite(entry_id):
            self.remove_favorite(entry_id)
            return False
        self.add_favorite(entry_id)
        return True

    def set_entry_tags(self, entry_id: str, tags: List[str]) -> bool:
        fav = self.load_favorites()
        tags_map = fav.setdefault("tags", {})
        tags_map[entry_id] = [t for t in tags if t]
        return self.save_favorites()

    def get_entry_tags(self, entry_id: str) -> List[str]:
        fav = self.load_favorites()
        return list((fav.get("tags") or {}).get(entry_id) or [])

    # ------------------------------------------------------------------
    # User CRUD (写到 user_data/dictionary/<subcategory_id>.jsonl)
    # ------------------------------------------------------------------

    def add_user_entry(
        self,
        subcategory_id: str,
        *,
        text: str,
        text_zh: str = "",
        tags: Optional[List[str]] = None,
        nsfw: bool = False,
        note: str = "",
    ) -> Dict[str, Any]:
        """新增用户词条，返回完整 entry。"""
        meta = self._find_subcategory_meta(subcategory_id)
        category_id = (meta or {}).get("category_id") or subcategory_id.split("_")[0]

        entry_id = f"user_{subcategory_id}_{uuid.uuid4().hex[:10]}"
        entry: Dict[str, Any] = {
            "id": entry_id,
            "text": text.strip(),
            "text_zh": (text_zh or "").strip(),
            "category": category_id,
            "subcategory": subcategory_id,
            "tags": tags or [],
            "nsfw": bool(nsfw),
            "source": "user",
        }
        if note:
            entry["note"] = note

        user_path = self._user_path(subcategory_id)
        existing = read_jsonl(user_path) if user_path.is_file() else []
        existing.append(entry)
        write_jsonl(user_path, existing)
        self.unload_subcategory(subcategory_id)
        return entry

    def update_user_entry(
        self,
        subcategory_id: str,
        entry_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """仅更新用户文件中的词条（不能改内置）。"""
        user_path = self._user_path(subcategory_id)
        if not user_path.is_file():
            return None
        rows = read_jsonl(user_path)
        found = None
        for i, row in enumerate(rows):
            if row.get("id") == entry_id:
                for k, v in updates.items():
                    if k in ("id", "source", "category", "subcategory"):
                        continue
                    row[k] = v
                rows[i] = row
                found = row
                break
        if found is None:
            return None
        write_jsonl(user_path, rows)
        self.unload_subcategory(subcategory_id)
        return found

    def delete_user_entry(self, subcategory_id: str, entry_id: str) -> bool:
        user_path = self._user_path(subcategory_id)
        if not user_path.is_file():
            return False
        rows = read_jsonl(user_path)
        new_rows = [r for r in rows if r.get("id") != entry_id]
        if len(new_rows) == len(rows):
            return False
        write_jsonl(user_path, new_rows)
        self.unload_subcategory(subcategory_id)
        return True

    def count_subcategory(self, subcategory_id: str) -> int:
        return len(self.load_subcategory(subcategory_id))

    def stats(self, include_misc: bool = False) -> Dict[str, int]:
        """粗略统计（会触发懒加载，仅用于调试/后台）。"""
        total = 0
        by_cat: Dict[str, int] = {}
        for cat in self.get_category_tree(include_misc=include_misc):
            c = 0
            for ch in cat.get("children", []):
                n = self.count_subcategory(ch["id"])
                c += n
            by_cat[cat["id"]] = c
            total += c
        return {"total": total, **by_cat}


# 模块级单例
dictionary_service = DictionaryService()
