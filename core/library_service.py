"""
词库 / 预设数据服务（阶段 3）。

约定：
- 系统库：data/library/*.json（只读）
- 用户库：user_data/library/*.json（可写；含全量 bulk / plugin）
- 收藏：user_data/library_favorites.json（独立索引，不改写大 JSON）
- 按文件懒加载；列表优先读 _extract_manifest.json
- NSFW：文件名/id 含 nsfw，或 nsfw_lib / 库级 nsfw，或预设 nsfw=true
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .io_utils import read_json, write_json
from .paths import paths

MANIFEST_SKIP_NAMES = {"_extract_manifest.json", "index.json"}
NSFW_NAME_RE = re.compile(r"nsfw", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _is_nsfw_name(name: str) -> bool:
    return bool(NSFW_NAME_RE.search(name or ""))


def _norm_tags(tags: Any) -> List[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        parts = re.split(r"[,，;；|/]", tags)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(tags, list):
        out: List[str] = []
        seen: Set[str] = set()
        for t in tags:
            s = str(t).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return []


def _preset_text(preset: Dict[str, Any], language: str = "zh") -> str:
    """按语言取预设正文：zh 优先 prompt，空则 prompt_en；en 相反；both 拼接。"""
    zh = (preset.get("prompt") or "").strip()
    en = (preset.get("prompt_en") or "").strip()
    if language == "en":
        return en or zh
    if language == "both":
        if zh and en and zh != en:
            return f"{zh}, {en}"
        return zh or en
    return zh or en


def _preset_title(preset: Dict[str, Any], language: str = "zh") -> str:
    zh = (preset.get("title_zh") or "").strip()
    en = (preset.get("title_en") or "").strip()
    if language == "en":
        return en or zh or preset.get("id") or ""
    return zh or en or preset.get("id") or ""


class LibraryService:
    def __init__(self) -> None:
        self._list_cache: Optional[List[Dict[str, Any]]] = None
        self._list_cached_at: float = 0.0
        self._lib_cache: Dict[str, Dict[str, Any]] = {}
        self._favorites: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # favorites file
    # ------------------------------------------------------------------

    def _load_favorites(self, force: bool = False) -> Dict[str, Any]:
        if self._favorites is not None and not force:
            return self._favorites
        data = read_json(paths.library_favorites_file, default=None)
        if not isinstance(data, dict):
            data = {"version": 1, "favorites": [], "liked": []}
        data.setdefault("version", 1)
        data.setdefault("favorites", [])
        data.setdefault("liked", [])
        self._favorites = data
        return data

    def _save_favorites(self) -> bool:
        data = self._load_favorites()
        return write_json(paths.library_favorites_file, data)

    def _fav_key(self, library_id: str, preset_id: str) -> str:
        return f"{library_id}::{preset_id}"

    def list_favorite_keys(self) -> Set[str]:
        data = self._load_favorites()
        return {
            self._fav_key(x.get("library_id", ""), x.get("preset_id", ""))
            for x in data.get("favorites") or []
            if x.get("library_id") and x.get("preset_id")
        }

    def is_favorite(self, library_id: str, preset_id: str) -> bool:
        return self._fav_key(library_id, preset_id) in self.list_favorite_keys()

    def toggle_favorite(self, library_id: str, preset_id: str) -> bool:
        data = self._load_favorites()
        favs: List[Dict[str, str]] = list(data.get("favorites") or [])
        key = self._fav_key(library_id, preset_id)
        existing = [
            i
            for i, x in enumerate(favs)
            if self._fav_key(x.get("library_id", ""), x.get("preset_id", "")) == key
        ]
        if existing:
            for i in reversed(existing):
                favs.pop(i)
            data["favorites"] = favs
            self._save_favorites()
            return False
        favs.append({"library_id": library_id, "preset_id": preset_id})
        data["favorites"] = favs
        self._save_favorites()
        return True

    def list_favorites_entries(self, language: str = "zh") -> List[Dict[str, Any]]:
        """展开收藏为可读行（跳过已删除的库/预设）。"""
        data = self._load_favorites()
        rows: List[Dict[str, Any]] = []
        for item in data.get("favorites") or []:
            lid = item.get("library_id") or ""
            pid = item.get("preset_id") or ""
            if not lid or not pid:
                continue
            lib = self.load_library(lid)
            if not lib:
                continue
            preset = self._find_preset(lib, pid)
            if not preset:
                continue
            rows.append(self._preset_row(lid, preset, language, favorited=True))
        return rows

    # ------------------------------------------------------------------
    # library list (lightweight)
    # ------------------------------------------------------------------

    def invalidate_list_cache(self) -> None:
        self._list_cache = None
        self._list_cached_at = 0.0

    def invalidate_library_cache(self, library_id: Optional[str] = None) -> None:
        if library_id is None:
            self._lib_cache.clear()
        else:
            self._lib_cache.pop(library_id, None)

    def reload(self) -> None:
        self.invalidate_list_cache()
        self.invalidate_library_cache()
        self._load_favorites(force=True)

    def _meta_from_path(
        self,
        path: Path,
        *,
        readonly: bool,
        group: str,
        preset_count: Optional[int] = None,
        nsfw_lib: Optional[bool] = None,
        name_zh: Optional[str] = None,
        name_en: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        lid = path.stem
        nsfw = bool(nsfw_lib) if nsfw_lib is not None else _is_nsfw_name(lid)
        return {
            "id": lid,
            "file": path.name,
            "path": str(path),
            "name_zh": name_zh or lid,
            "name_en": name_en or lid,
            "description": description or "",
            "preset_count": int(preset_count or 0),
            "nsfw": nsfw,
            "readonly": readonly,
            "group": group,
            "system": readonly,
        }

    def _group_for(self, lid: str, readonly: bool, nsfw: bool) -> str:
        if readonly:
            return "system"
        if nsfw or _is_nsfw_name(lid):
            return "nsfw"
        if lid.startswith("plugin_"):
            return "plugin"
        if lid.startswith("bulk_sfw") or lid.startswith("bulk_"):
            return "bulk"
        return "user"

    def list_libraries(self, include_nsfw: bool = True) -> List[Dict[str, Any]]:
        if self._list_cache is not None:
            libs = self._list_cache
        else:
            libs = self._scan_libraries()
            self._list_cache = libs
            self._list_cached_at = time.time()

        if include_nsfw:
            return list(libs)
        return [x for x in libs if not x.get("nsfw")]

    def _scan_libraries(self) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}

        # 1) system demos from data/library
        if paths.library.is_dir():
            for path in sorted(paths.library.glob("*.json")):
                if path.name in MANIFEST_SKIP_NAMES:
                    continue
                data = read_json(path, default=None)
                if not isinstance(data, dict):
                    continue
                lid = str(data.get("id") or path.stem)
                nsfw = bool(data.get("nsfw")) or _is_nsfw_name(lid)
                meta = self._meta_from_path(
                    path,
                    readonly=True,
                    group="system",
                    preset_count=len(data.get("presets") or []),
                    nsfw_lib=nsfw,
                    name_zh=data.get("name_zh") or lid,
                    name_en=data.get("name_en") or lid,
                    description=data.get("description") or "",
                )
                meta["id"] = lid
                by_id[lid] = meta

        # 2) manifest for user_data bulk (fast path)
        manifest = read_json(paths.library_manifest, default=None)
        manifest_ids: Set[str] = set()
        if isinstance(manifest, dict):
            for item in manifest.get("libraries") or []:
                if not isinstance(item, dict):
                    continue
                fn = item.get("file") or ""
                lid = str(item.get("id") or Path(fn).stem)
                if not lid or lid.startswith("_"):
                    continue
                path = paths.user_library / (fn or f"{lid}.json")
                nsfw = bool(item.get("nsfw_lib")) or _is_nsfw_name(lid)
                meta = self._meta_from_path(
                    path,
                    readonly=False,
                    group=self._group_for(lid, False, nsfw),
                    preset_count=item.get("preset_count") or 0,
                    nsfw_lib=nsfw,
                    name_zh=item.get("name_zh") or lid,
                    name_en=item.get("name_en") or "",
                    description=item.get("description") or "",
                )
                meta["id"] = lid
                by_id[lid] = meta
                manifest_ids.add(lid)

        # 3) scan user_data for files not in manifest (user-created)
        if paths.user_library.is_dir():
            for path in sorted(paths.user_library.glob("*.json")):
                if path.name in MANIFEST_SKIP_NAMES:
                    continue
                lid = path.stem
                if lid in by_id:
                    # refresh path existence
                    by_id[lid]["path"] = str(path)
                    by_id[lid]["file"] = path.name
                    continue
                # lightweight: avoid loading huge files; use stem as name
                # only peek small files (< 2MB) for name_zh
                name_zh = lid
                name_en = ""
                desc = ""
                count = 0
                nsfw = _is_nsfw_name(lid)
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                if size and size < 2_000_000:
                    data = read_json(path, default=None)
                    if isinstance(data, dict) and "presets" in data:
                        lid = str(data.get("id") or lid)
                        name_zh = data.get("name_zh") or lid
                        name_en = data.get("name_en") or ""
                        desc = data.get("description") or ""
                        count = len(data.get("presets") or [])
                        nsfw = bool(data.get("nsfw")) or nsfw
                meta = self._meta_from_path(
                    path,
                    readonly=False,
                    group=self._group_for(lid, False, nsfw),
                    preset_count=count,
                    nsfw_lib=nsfw,
                    name_zh=name_zh,
                    name_en=name_en,
                    description=desc,
                )
                meta["id"] = lid
                by_id[lid] = meta

        # sort: system → plugin → user → bulk → nsfw
        group_order = {"system": 0, "plugin": 1, "user": 2, "bulk": 3, "nsfw": 4}

        def sort_key(x: Dict[str, Any]) -> Tuple[int, str]:
            return (group_order.get(x.get("group") or "", 9), x.get("name_zh") or x.get("id") or "")

        return sorted(by_id.values(), key=sort_key)

    def get_library_meta(self, library_id: str) -> Optional[Dict[str, Any]]:
        for m in self.list_libraries(include_nsfw=True):
            if m.get("id") == library_id:
                return m
        return None

    # ------------------------------------------------------------------
    # load full library
    # ------------------------------------------------------------------

    def load_library(self, library_id: str, force: bool = False) -> Optional[Dict[str, Any]]:
        if not library_id:
            return None
        if not force and library_id in self._lib_cache:
            return self._lib_cache[library_id]

        meta = self.get_library_meta(library_id)
        path: Optional[Path] = None
        if meta and meta.get("path"):
            path = Path(meta["path"])
        if path is None or not path.is_file():
            # fallback search
            for base in (paths.library, paths.user_library):
                cand = base / f"{library_id}.json"
                if cand.is_file():
                    path = cand
                    break
        if path is None or not path.is_file():
            return None

        data = read_json(path, default=None)
        if not isinstance(data, dict):
            return None
        # normalize
        data.setdefault("id", library_id)
        data.setdefault("name_zh", library_id)
        data.setdefault("name_en", "")
        data.setdefault("description", "")
        data.setdefault("version", 1)
        data.setdefault("categories", [])
        data.setdefault("presets", [])
        if not isinstance(data["presets"], list):
            data["presets"] = []
        data["_path"] = str(path)
        try:
            data["_readonly"] = bool(meta.get("readonly")) if meta else path.resolve().is_relative_to(paths.library.resolve())
        except (AttributeError, ValueError, TypeError):
            data["_readonly"] = bool(meta.get("readonly")) if meta else str(path).startswith(str(paths.library))
        data["_nsfw"] = bool(meta.get("nsfw")) if meta else _is_nsfw_name(library_id)

        self._lib_cache[library_id] = data
        return data

    def _find_preset(self, lib: Dict[str, Any], preset_id: str) -> Optional[Dict[str, Any]]:
        for p in lib.get("presets") or []:
            if p.get("id") == preset_id:
                return p
        return None

    def _preset_row(
        self,
        library_id: str,
        preset: Dict[str, Any],
        language: str = "zh",
        favorited: Optional[bool] = None,
    ) -> Dict[str, Any]:
        pid = preset.get("id") or ""
        if favorited is None:
            favorited = self.is_favorite(library_id, pid)
        return {
            "id": pid,
            "library_id": library_id,
            "title": _preset_title(preset, language),
            "title_zh": preset.get("title_zh") or "",
            "title_en": preset.get("title_en") or "",
            "prompt": preset.get("prompt") or "",
            "prompt_en": preset.get("prompt_en") or "",
            "text": _preset_text(preset, language),
            "category_id": preset.get("category_id") or "",
            "tags": list(preset.get("tags") or []),
            "nsfw": bool(preset.get("nsfw")),
            "favorite": favorited,
            "note": preset.get("note") or "",
            "source": preset.get("source") or "",
        }

    # ------------------------------------------------------------------
    # search / filter
    # ------------------------------------------------------------------

    def search_presets(
        self,
        library_id: str,
        *,
        query: str = "",
        category_id: str = "",
        tags: Optional[List[str]] = None,
        tag_mode: str = "and",
        favorites_only: bool = False,
        include_nsfw_presets: bool = True,
        language: str = "zh",
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        lib = self.load_library(library_id)
        if not lib:
            return {"presets": [], "total": 0, "offset": offset, "limit": limit}

        q = (query or "").strip().lower()
        tags = [t.strip() for t in (tags or []) if t and str(t).strip()]
        tag_mode = (tag_mode or "and").lower()
        fav_keys = self.list_favorite_keys() if favorites_only else None

        matched: List[Dict[str, Any]] = []
        for p in lib.get("presets") or []:
            if not include_nsfw_presets and p.get("nsfw"):
                continue
            pid = p.get("id") or ""
            if favorites_only and fav_keys is not None:
                if self._fav_key(library_id, pid) not in fav_keys:
                    continue
            if category_id and (p.get("category_id") or "") != category_id:
                continue
            ptags = [str(t).strip() for t in (p.get("tags") or []) if t]
            if tags:
                ptags_l = {t.lower() for t in ptags}
                want = [t.lower() for t in tags]
                if tag_mode == "or":
                    if not any(t in ptags_l for t in want):
                        continue
                else:  # and
                    if not all(t in ptags_l for t in want):
                        continue
            if q:
                blob = " ".join(
                    [
                        str(p.get("title_zh") or ""),
                        str(p.get("title_en") or ""),
                        str(p.get("prompt") or ""),
                        str(p.get("prompt_en") or ""),
                        " ".join(ptags),
                        str(p.get("note") or ""),
                    ]
                ).lower()
                if q not in blob:
                    continue
            matched.append(p)

        total = len(matched)
        page = matched[offset : offset + limit]
        rows = [
            self._preset_row(library_id, p, language)
            for p in page
        ]
        return {
            "presets": rows,
            "total": total,
            "offset": offset,
            "limit": limit,
            "library_id": library_id,
        }

    def collect_tags(self, library_id: str) -> List[str]:
        lib = self.load_library(library_id)
        if not lib:
            return []
        seen: Set[str] = set()
        out: List[str] = []
        for p in lib.get("presets") or []:
            for t in p.get("tags") or []:
                s = str(t).strip()
                if s and s not in seen:
                    seen.add(s)
                    out.append(s)
        out.sort()
        return out

    def collect_categories(self, library_id: str) -> List[Dict[str, Any]]:
        lib = self.load_library(library_id)
        if not lib:
            return []
        cats = list(lib.get("categories") or [])
        # also discover from presets
        known = {c.get("id") for c in cats if c.get("id")}
        for p in lib.get("presets") or []:
            cid = p.get("category_id") or ""
            if cid and cid not in known:
                cats.append({"id": cid, "name_zh": cid, "name_en": cid})
                known.add(cid)
        return cats

    # ------------------------------------------------------------------
    # write helpers
    # ------------------------------------------------------------------

    def _assert_writable(self, lib: Dict[str, Any]) -> None:
        # 系统/用户库均允许编辑（系统库写回 data/library）
        return

    def save_library(self, library_id: str, data: Optional[Dict[str, Any]] = None) -> bool:
        lib = data or self.load_library(library_id)
        if not lib:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        self._assert_writable(lib)
        path = Path(lib.get("_path") or (paths.user_library / f"{library_id}.json"))
        out = {
            "id": lib.get("id") or library_id,
            "name_zh": lib.get("name_zh") or library_id,
            "name_en": lib.get("name_en") or "",
            "description": lib.get("description") or "",
            "version": lib.get("version") or 1,
            "categories": lib.get("categories") or [],
            "presets": lib.get("presets") or [],
        }
        if "nsfw" in lib:
            out["nsfw"] = bool(lib.get("nsfw"))
        ok = write_json(path, out)
        if ok:
            self.invalidate_library_cache(library_id)
            self.invalidate_list_cache()
        return ok

    def create_library(
        self,
        name_zh: str,
        *,
        library_id: str = "",
        name_en: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        name_zh = (name_zh or "").strip()
        if not name_zh:
            raise ValueError("词库名称不能为空")
        lid = (library_id or "").strip()
        if not lid:
            # slug from name
            lid = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name_zh).strip("_").lower() or "lib"
            lid = f"user_{lid}"[:60]
        # ensure unique
        base = lid
        n = 1
        while self.get_library_meta(lid) is not None or (paths.user_library / f"{lid}.json").exists():
            n += 1
            lid = f"{base}_{n}"

        paths.ensure_user_dirs()
        path = paths.user_library / f"{lid}.json"
        data = {
            "id": lid,
            "name_zh": name_zh,
            "name_en": name_en or name_zh,
            "description": description or "",
            "version": 1,
            "categories": [],
            "presets": [],
            "nsfw": False,
        }
        write_json(path, data)
        self.invalidate_list_cache()
        return self._meta_from_path(
            path,
            readonly=False,
            group="user",
            preset_count=0,
            nsfw_lib=False,
            name_zh=name_zh,
            name_en=name_en or name_zh,
            description=description,
        )

    def delete_library(self, library_id: str) -> bool:
        meta = self.get_library_meta(library_id)
        if not meta:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        if meta.get("readonly") or meta.get("system"):
            raise PermissionError("系统词库不可删除")
        path = Path(meta["path"])
        if path.is_file():
            path.unlink()
        self.invalidate_library_cache(library_id)
        self.invalidate_list_cache()
        # clean favorites pointing to this lib
        data = self._load_favorites()
        data["favorites"] = [
            x for x in (data.get("favorites") or []) if x.get("library_id") != library_id
        ]
        data["liked"] = [
            x for x in (data.get("liked") or []) if x.get("library_id") != library_id
        ]
        self._save_favorites()
        return True

    def add_preset(
        self,
        library_id: str,
        *,
        title_zh: str = "",
        title_en: str = "",
        prompt: str = "",
        prompt_en: str = "",
        category_id: str = "",
        tags: Optional[List[str]] = None,
        nsfw: bool = False,
        note: str = "",
    ) -> Dict[str, Any]:
        lib = self.load_library(library_id, force=True)
        if not lib:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        self._assert_writable(lib)
        prompt = (prompt or "").strip()
        prompt_en = (prompt_en or "").strip()
        if not prompt and not prompt_en:
            raise ValueError("prompt / prompt_en 至少填一个")
        title_zh = (title_zh or "").strip()
        if not title_zh:
            base = prompt or prompt_en
            title_zh = (base[:24].rstrip("，。、；：,.!?;: ") or "未命名")
        pid = f"p_{uuid.uuid4().hex[:10]}"
        now = _now_iso()
        preset = {
            "id": pid,
            "title_zh": title_zh,
            "title_en": (title_en or "").strip(),
            "prompt": prompt,
            "prompt_en": prompt_en,
            "category_id": (category_id or "").strip(),
            "tags": _norm_tags(tags),
            "favorite": False,
            "liked": False,
            "nsfw": bool(nsfw),
            "source": "user",
            "note": note or "",
            "created_at": now,
            "updated_at": now,
        }
        lib.setdefault("presets", []).append(preset)
        self.save_library(library_id, lib)
        return preset

    def update_preset(
        self,
        library_id: str,
        preset_id: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        lib = self.load_library(library_id, force=True)
        if not lib:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        self._assert_writable(lib)
        preset = self._find_preset(lib, preset_id)
        if not preset:
            raise FileNotFoundError(f"预设不存在: {preset_id}")
        allowed = {
            "title_zh",
            "title_en",
            "prompt",
            "prompt_en",
            "category_id",
            "tags",
            "nsfw",
            "note",
        }
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "tags":
                preset["tags"] = _norm_tags(v)
            elif k == "nsfw":
                preset["nsfw"] = bool(v)
            else:
                preset[k] = v if v is not None else ""
        preset["updated_at"] = _now_iso()
        self.save_library(library_id, lib)
        return preset

    def delete_preset(self, library_id: str, preset_id: str) -> bool:
        lib = self.load_library(library_id, force=True)
        if not lib:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        self._assert_writable(lib)
        presets = lib.get("presets") or []
        new_list = [p for p in presets if p.get("id") != preset_id]
        if len(new_list) == len(presets):
            raise FileNotFoundError(f"预设不存在: {preset_id}")
        lib["presets"] = new_list
        self.save_library(library_id, lib)
        # remove from favorites
        data = self._load_favorites()
        data["favorites"] = [
            x
            for x in (data.get("favorites") or [])
            if not (x.get("library_id") == library_id and x.get("preset_id") == preset_id)
        ]
        self._save_favorites()
        return True

    def set_preset_tags(
        self,
        library_id: str,
        preset_id: str,
        tags: List[str],
        *,
        action: str = "set",
    ) -> List[str]:
        """action: set | add | remove"""
        lib = self.load_library(library_id, force=True)
        if not lib:
            raise FileNotFoundError(f"词库不存在: {library_id}")
        self._assert_writable(lib)
        preset = self._find_preset(lib, preset_id)
        if not preset:
            raise FileNotFoundError(f"预设不存在: {preset_id}")
        current = _norm_tags(preset.get("tags"))
        incoming = _norm_tags(tags)
        action = (action or "set").lower()
        if action == "add":
            for t in incoming:
                if t not in current:
                    current.append(t)
        elif action == "remove":
            remove_set = set(incoming)
            current = [t for t in current if t not in remove_set]
        else:
            current = incoming
        preset["tags"] = current
        preset["updated_at"] = _now_iso()
        self.save_library(library_id, lib)
        return current

    # ------------------------------------------------------------------
    # pick helpers for nodes
    # ------------------------------------------------------------------

    def library_choices(self, include_nsfw: bool = True) -> List[str]:
        """下拉选项：仅中文显示名（NSFW 加前缀）。用 parse_library_choice 还原 id。"""
        libs = self.list_libraries(include_nsfw=True)
        out = []
        for m in libs:
            name = (m.get("name_zh") or m["id"] or "").strip()
            if m.get("nsfw"):
                name = f"[NSFW] {name}"
            if not include_nsfw and m.get("nsfw"):
                continue
            out.append(name)
        return out

    def parse_library_choice(self, label: str) -> str:
        """支持纯中文名、id、或旧格式 id|中文名。"""
        label = (label or "").strip()
        if not label or label.startswith("("):
            return ""
        if "|" in label:
            return label.split("|")[0].strip()
        libs = self.list_libraries(include_nsfw=True)
        for m in libs:
            if m.get("id") == label:
                return str(m["id"])
        bare = label[7:].strip() if label.startswith("[NSFW]") else label
        for m in libs:
            nz = (m.get("name_zh") or "").strip()
            if nz == bare or nz == label:
                return str(m["id"])
        return label


# 模块级单例
library_service = LibraryService()
