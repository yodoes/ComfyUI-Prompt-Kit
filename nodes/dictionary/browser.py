"""
字典浏览 / 搜索 / 选择节点。

节点列表：
  - PromptKitDictionarySearch   搜索并返回匹配文本
  - PromptKitDictionaryBrowse   按中类浏览并选择
  - PromptKitDictionaryFavorite 收藏管理
  - PromptKitDictionaryAdd      添加用户词条
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from ...core.dictionary_service import dictionary_service
    from ...core.settings import settings
except ImportError:  # 直接脚本/测试时
    from core.dictionary_service import dictionary_service
    from core.settings import settings


def _lang() -> str:
    return settings.get("output_language", "zh") or "zh"


def _join(texts: List[str]) -> str:
    sep = settings.get("separator", ", ") or ", "
    # 去重保序
    seen = set()
    out = []
    for t in texts:
        t = (t or "").strip().rstrip(",")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return sep.join(out)


class PromptKitDictionarySearch:
    """按关键词搜索字典，返回拼接后的 prompt 片段与命中条数。"""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        tree = dictionary_service.get_category_tree(include_misc=False)
        cat_choices = ["全部"] + [f"{c['id']}|{c['name']}" for c in tree]
        return {
            "required": {
                "query": ("STRING", {"default": "", "multiline": False}),
                "category": (cat_choices, {"default": "全部"}),
                "limit": ("INT", {"default": 20, "min": 1, "max": 200}),
                "language": (["zh", "en", "both"], {"default": "zh"}),
            },
            "optional": {
                "tags": ("STRING", {"default": "", "multiline": False}),
                "include_misc": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt", "detail", "count")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典"

    def run(
        self,
        query: str,
        category: str,
        limit: int,
        language: str,
        tags: str = "",
        include_misc: bool = False,
    ) -> Tuple[str, str, int]:
        sub_ids = None
        if category and category != "全部":
            cid = category.split("|")[0].strip()
            tree = dictionary_service.get_category_tree(include_misc=include_misc)
            for c in tree:
                if c["id"] == cid:
                    sub_ids = [ch["id"] for ch in c.get("children", [])]
                    break

        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        hits = dictionary_service.search(
            query,
            subcategory_ids=sub_ids,
            tags=tag_list or None,
            include_misc=include_misc,
            language="both",
            limit=limit,
        )
        texts = [dictionary_service.display_text(e, language) for e in hits]
        prompt = _join(texts)
        detail_lines = []
        for e in hits[:50]:
            d = dictionary_service.display_text(e, language)
            detail_lines.append(f"{e.get('id', '')}: {d}")
        detail = "\n".join(detail_lines)
        return (prompt, detail, len(hits))


class PromptKitDictionaryBrowse:
    """按中类浏览词条，支持分页与多选输出。"""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        tree = dictionary_service.get_category_tree(include_misc=False)
        sub_choices = []
        for c in tree:
            for ch in c.get("children", []):
                sub_choices.append(f"{ch['id']}|{c['name']}/{ch['name']}")
        if not sub_choices:
            sub_choices = ["(无分类)"]
        return {
            "required": {
                "subcategory": (sub_choices, {"default": sub_choices[0]}),
                "offset": ("INT", {"default": 0, "min": 0, "max": 100000}),
                "limit": ("INT", {"default": 30, "min": 1, "max": 500}),
                "language": (["zh", "en", "both"], {"default": "zh"}),
                "select_indices": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "逗号分隔的序号（从 0 开始），空则输出本页全部",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt", "list_preview", "total_in_sub")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典"

    def run(
        self,
        subcategory: str,
        offset: int,
        limit: int,
        language: str,
        select_indices: str = "",
    ) -> Tuple[str, str, int]:
        sid = subcategory.split("|")[0].strip()
        if not sid or sid.startswith("("):
            return ("", "", 0)

        all_entries = dictionary_service.load_subcategory(sid)
        total = len(all_entries)
        page = all_entries[offset : offset + limit]

        preview_lines = []
        for i, e in enumerate(page):
            d = dictionary_service.display_text(e, language)
            preview_lines.append(f"[{i}] {d}")

        selected: List[Dict[str, Any]] = []
        indices_raw = [s.strip() for s in (select_indices or "").split(",") if s.strip()]
        if indices_raw:
            for s in indices_raw:
                try:
                    idx = int(s)
                    if 0 <= idx < len(page):
                        selected.append(page[idx])
                except ValueError:
                    continue
        else:
            selected = page

        texts = [dictionary_service.display_text(e, language) for e in selected]
        prompt = _join(texts)
        return (prompt, "\n".join(preview_lines), total)


class PromptKitDictionaryFavorite:
    """收藏：添加 / 移除 / 列出收藏词条。"""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "action": (["list", "add", "remove", "toggle"], {"default": "list"}),
                "entry_id": ("STRING", {"default": ""}),
                "language": (["zh", "en", "both"], {"default": "zh"}),
                "limit": ("INT", {"default": 50, "min": 1, "max": 500}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt", "detail", "count")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典"

    def run(
        self,
        action: str,
        entry_id: str,
        language: str,
        limit: int,
    ) -> Tuple[str, str, int]:
        entry_id = (entry_id or "").strip()
        if action == "add" and entry_id:
            dictionary_service.add_favorite(entry_id)
        elif action == "remove" and entry_id:
            dictionary_service.remove_favorite(entry_id)
        elif action == "toggle" and entry_id:
            dictionary_service.toggle_favorite(entry_id)

        fav_ids = dictionary_service.list_favorites()[:limit]
        entries = []
        for eid in fav_ids:
            e = dictionary_service.get_entry_by_id(eid, include_misc=True)
            if e:
                entries.append(e)

        texts = [dictionary_service.display_text(e, language) for e in entries]
        prompt = _join(texts)
        detail = "\n".join(
            f"{e.get('id')}: {dictionary_service.display_text(e, language)}" for e in entries
        )
        return (prompt, detail, len(fav_ids))


class PromptKitDictionaryAdd:
    """向指定中类添加用户自定义词条。"""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        tree = dictionary_service.get_category_tree(include_misc=True)
        sub_choices = []
        for c in tree:
            for ch in c.get("children", []):
                sub_choices.append(f"{ch['id']}|{c['name']}/{ch['name']}")
        if not sub_choices:
            sub_choices = ["(无分类)"]
        return {
            "required": {
                "subcategory": (sub_choices, {"default": sub_choices[0]}),
                "text": ("STRING", {"default": "", "multiline": False}),
                "text_zh": ("STRING", {"default": "", "multiline": False}),
                "tags": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("entry_id", "message")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典"

    def run(
        self,
        subcategory: str,
        text: str,
        text_zh: str = "",
        tags: str = "",
    ) -> Tuple[str, str]:
        sid = subcategory.split("|")[0].strip()
        if not sid or sid.startswith("("):
            return ("", "无效中类")
        if not (text or "").strip() and not (text_zh or "").strip():
            return ("", "text 与 text_zh 至少填一个")

        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        entry = dictionary_service.add_user_entry(
            sid,
            text=(text or text_zh).strip(),
            text_zh=(text_zh or "").strip(),
            tags=tag_list,
        )
        return (entry.get("id", ""), f"已添加: {entry.get('id')}")


NODE_CLASS_MAPPINGS = {
    "PromptKitDictionarySearch": PromptKitDictionarySearch,
    "PromptKitDictionaryBrowse": PromptKitDictionaryBrowse,
    "PromptKitDictionaryFavorite": PromptKitDictionaryFavorite,
    "PromptKitDictionaryAdd": PromptKitDictionaryAdd,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptKitDictionarySearch": "PromptKit · 字典搜索",
    "PromptKitDictionaryBrowse": "PromptKit · 字典浏览",
    "PromptKitDictionaryFavorite": "PromptKit · 收藏管理",
    "PromptKitDictionaryAdd": "PromptKit · 添加词条",
}
