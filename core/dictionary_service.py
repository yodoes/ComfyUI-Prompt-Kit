"""
字典数据服务：懒加载、搜索、收藏、用户自定义词条、NSFW 可插拔。

约定：
- 内置 SFW：data/dictionary/
- 内置 NSFW：data/dictionary_nsfw/（include_nsfw=True 时合并进分类树）
- 用户覆盖：user_data/dictionary/<subcategory_id>.jsonl（同 id 覆盖内置，系统词条也可“编辑”）
- 默认不加载 14_misc_custom；默认不加载 NSFW
- 词条字段：id, text, text_zh, category, subcategory, tags, nsfw, source
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set

from .io_utils import read_json, read_jsonl, write_json, write_jsonl
from .paths import paths


MISC_CATEGORY_ID = "14_misc_custom"


class DictionaryService:
    def __init__(self) -> None:
        self._index: Optional[Dict[str, Any]] = None
        self._nsfw_index: Optional[Dict[str, Any]] = None
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_mtime: Dict[str, float] = {}
        self._favorites: Optional[Dict[str, Any]] = None
        self._loaded_at: float = 0.0

    def load_index(self, force: bool = False) -> Dict[str, Any]:
        if self._index is not None and not force:
            return self._index
        data = read_json(paths.dictionary_index, default={})
        if not isinstance(data, dict) or "categories" not in data:
            data = {"version": 1, "categories": []}
        self._index = data
        self._loaded_at = time.time()
        return self._index

    def load_nsfw_index(self, force: bool = False) -> Dict[str, Any]:
        if self._nsfw_index is not None and not force:
            return self._nsfw_index
        data = read_json(paths.dictionary_nsfw_index, default={})
        if not isinstance(data, dict) or "categories" not in data:
            data = {"version": 1, "categories": [], "nsfw": True}
        self._nsfw_index = data
        return self._nsfw_index

    def get_category_tree(
        self,
        include_misc: bool = False,
        include_nsfw: bool = False,
        language: str = "zh",
    ) -> List[Dict[str, Any]]:
        tree: List[Dict[str, Any]] = []
        for index, is_nsfw in (
            (self.load_index(), False),
            (self.load_nsfw_index() if include_nsfw else {"categories": []}, True),
        ):
            for cat in index.get("categories", []):
                cid = cat.get("id", "")
                if not include_misc and cid == MISC_CATEGORY_ID:
                    continue
                name = cat.get("name_zh") if language == "zh" else cat.get("name_en")
                if is_nsfw and language == "zh":
                    name = f"[NSFW] {name or cid}"
                elif is_nsfw:
                    name = f"[NSFW] {name or cid}"
                children = []
                for ch in cat.get("children", []):
                    ch_name = ch.get("name_zh") if language == "zh" else ch.get("name_en")
                    children.append(
                        {
                            "id": ch.get("id"),
                            "name": ch_name or ch.get("id"),
                            "file": ch.get("file"),
                            "nsfw": is_nsfw,
                        }
                    )
                tree.append(
                    {
                        "id": cid,
                        "name": name or cid,
                        "order": cat.get("order", 0) + (1000 if is_nsfw else 0),
                        "children": children,
                        "nsfw": is_nsfw,
                    }
                )
        tree.sort(key=lambda x: x.get("order", 0))
        return tree

    def list_subcategory_ids(
        self, include_misc: bool = False, include_nsfw: bool = False
    ) -> List[str]:
        ids: List[str] = []
        for cat in self.get_category_tree(
            include_misc=include_misc, include_nsfw=include_nsfw
        ):
            for ch in cat.get("children", []):
                if ch.get("id"):
                    ids.append(ch["id"])
        return ids

    def _find_subcategory_meta(self, subcategory_id: str) -> Optional[Dict[str, Any]]:
        for index, is_nsfw, base in (
            (self.load_index(), False, paths.dictionary),
            (self.load_nsfw_index(), True, paths.dictionary_nsfw),
        ):
            for cat in index.get("categories", []):
                for ch in cat.get("children", []):
                    if ch.get("id") == subcategory_id:
                        meta = dict(ch)
                        meta["category_id"] = cat.get("id")
                        meta["nsfw"] = is_nsfw
                        meta["_base"] = base
                        return meta
        return None

    def _builtin_path(self, subcategory_id: str) -> Optional[Any]:
        meta = self._find_subcategory_meta(subcategory_id)
        if not meta or not meta.get("file"):
            return None
        base = meta.get("_base") or paths.dictionary
        return base / meta["file"]

    def _user_path(self, subcategory_id: str) -> Any:
        return paths.user_dictionary / f"{subcategory_id}.jsonl"

    def load_subcategory(
        self, subcategory_id: str, force: bool = False
    ) -> List[Dict[str, Any]]:
        if not force and subcategory_id in self._cache:
            return self._cache[subcategory_id]

        builtin_path = self._builtin_path(subcategory_id)
        entries: List[Dict[str, Any]] = []
        if builtin_path is not None and builtin_path.is_file():
            entries = read_jsonl(builtin_path)

        user_path = self._user_path(subcategory_id)
        user_entries = read_jsonl(user_path) if user_path.is_file() else []

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
                by_id[f"user_{uuid.uuid4().hex[:8]}"] = e

        merged = [e for e in by_id.values() if not e.get("deleted")]
        self._cache[subcategory_id] = merged
        return merged

    def unload_subcategory(self, subcategory_id: str) -> None:
        self._cache.pop(subcategory_id, None)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_mtime.clear()
        self._favorites = None
        self._index = None
        self._nsfw_index = None

    def search(
        self,
        query: str,
        *,
        subcategory_ids: Optional[Iterable[str]] = None,
        tags: Optional[Iterable[str]] = None,
        include_misc: bool = False,
        include_nsfw: bool = False,
        language: str = "both",
        limit: int = 200,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
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
            sub_ids = self.list_subcategory_ids(
                include_misc=include_misc, include_nsfw=include_nsfw
            )
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

    def _match_entry(self, entry, q, tag_set, language, case_sensitive) -> bool:
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
        for t in entry.get("tags") or []:
            if isinstance(t, str):
                fields.append(t)
        haystack = " ".join(fields)
        if not case_sensitive:
            haystack = haystack.lower()
        return q in haystack

    def get_entries_by_subcategory(
        self, subcategory_id: str, *, limit: int = 0, offset: int = 0
    ) -> List[Dict[str, Any]]:
        entries = self.load_subcategory(subcategory_id)
        if offset:
            entries = entries[offset:]
        if limit and limit > 0:
            entries = entries[:limit]
        return entries

    def get_entry_by_id(
        self, entry_id: str, include_misc: bool = False, include_nsfw: bool = True
    ) -> Optional[Dict[str, Any]]:
        for sid in self.list_subcategory_ids(
            include_misc=include_misc, include_nsfw=include_nsfw
        ):
            for e in self.load_subcategory(sid):
                if e.get("id") == entry_id:
                    return e
        return None

    @staticmethod
    def display_text(entry: Dict[str, Any], language: str = "zh") -> str:
        text = (entry.get("text") or "").strip()
        text_zh = (entry.get("text_zh") or "").strip()
        if language == "zh":
            return text_zh or text
        if language == "en":
            return text or text_zh
        if text_zh and text and text_zh != text:
            return f"{text_zh} ({text})"
        return text_zh or text

    def load_favorites(self, force: bool = False) -> Dict[str, Any]:
        if self._favorites is not None and not force:
            return self._favorites
        paths.ensure_user_dirs()
        data = read_json(paths.favorites_file, default=None)
        if not isinstance(data, dict):
            data = {"version": 1, "entries": [], "tags": {}}
        data.setdefault("version", 1)
        data.setdefault("entries", [])
        data.setdefault("tags", {})
        self._favorites = data
        return self._favorites

    def save_favorites(self) -> bool:
        if self._favorites is None:
            self.load_favorites()
        paths.ensure_user_dirs()
        return write_json(paths.favorites_file, self._favorites)

    def list_favorites(self) -> List[str]:
        return list(self.load_favorites().get("entries") or [])

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
        entries = [e for e in (fav.get("entries") or []) if e != entry_id]
        fav["entries"] = entries
        return self.save_favorites()

    def toggle_favorite(self, entry_id: str) -> bool:
        if self.is_favorite(entry_id):
            self.remove_favorite(entry_id)
            return False
        self.add_favorite(entry_id)
        return True

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
            "nsfw": bool(nsfw) or bool((meta or {}).get("nsfw")),
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

    def update_entry(
        self,
        entry_id: str,
        updates: Dict[str, Any],
        *,
        subcategory_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        更新词条（系统/用户均可）。
        实现：写入 user_data 覆盖层（同 id），加载时用户优先，不直接改安装包内 jsonl。
        """
        entry = None
        sid = subcategory_id
        if sid:
            for e in self.load_subcategory(sid):
                if e.get("id") == entry_id:
                    entry = dict(e)
                    break
        if entry is None:
            entry = self.get_entry_by_id(entry_id, include_misc=True, include_nsfw=True)
            if entry:
                sid = entry.get("subcategory") or ""
        if not entry or not sid:
            return None
        allowed = ("text", "text_zh", "tags", "nsfw", "note")
        for k, v in updates.items():
            if k in allowed:
                entry[k] = v
        entry["id"] = entry_id
        entry["subcategory"] = sid
        entry["source"] = entry.get("source") or "override"
        user_path = self._user_path(sid)
        rows = read_jsonl(user_path) if user_path.is_file() else []
        found = False
        for i, row in enumerate(rows):
            if row.get("id") == entry_id:
                rows[i] = entry
                found = True
                break
        if not found:
            rows.append(entry)
        write_jsonl(user_path, rows)
        self.unload_subcategory(sid)
        return entry

    def update_user_entry(
        self, subcategory_id: str, entry_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        return self.update_entry(entry_id, updates, subcategory_id=subcategory_id)

    def delete_user_entry(self, subcategory_id: str, entry_id: str) -> bool:
        return self.delete_entry(entry_id, subcategory_id=subcategory_id)

    def delete_entry(self, entry_id: str, *, subcategory_id: str = "") -> bool:
        """删除词条：用户层直接移除；系统词写入 deleted 墓碑覆盖。"""
        entry_id = (entry_id or "").strip()
        if not entry_id:
            return False
        sid = (subcategory_id or "").strip()
        entry = None
        if sid:
            for e in self.load_subcategory(sid):
                if e.get("id") == entry_id:
                    entry = dict(e)
                    break
        if entry is None:
            entry = self.get_entry_by_id(entry_id, include_misc=True, include_nsfw=True)
            if entry:
                sid = entry.get("subcategory") or ""
        if not sid:
            # still try remove from any user file if only id known
            user_path = self._user_path(sid) if sid else None
            if user_path and user_path.is_file():
                rows = read_jsonl(user_path)
                new_rows = [r for r in rows if r.get("id") != entry_id]
                if len(new_rows) != len(rows):
                    write_jsonl(user_path, new_rows)
                    self.unload_subcategory(sid)
                    return True
            return False
        user_path = self._user_path(sid)
        rows = read_jsonl(user_path) if user_path.is_file() else []
        # remove existing user row
        rows = [r for r in rows if r.get("id") != entry_id]
        # system entry still exists in builtin → write tombstone
        builtin = self._builtin_path(sid)
        has_builtin = False
        if builtin and builtin.is_file():
            for r in read_jsonl(builtin):
                if r.get("id") == entry_id:
                    has_builtin = True
                    break
        if has_builtin:
            tomb = dict(entry or {"id": entry_id, "subcategory": sid})
            tomb["id"] = entry_id
            tomb["subcategory"] = sid
            tomb["deleted"] = True
            tomb["source"] = "deleted"
            rows.append(tomb)
        write_jsonl(user_path, rows)
        self.unload_subcategory(sid)
        return True

    def count_subcategory(self, subcategory_id: str) -> int:
        return len(self.load_subcategory(subcategory_id))


dictionary_service = DictionaryService()
