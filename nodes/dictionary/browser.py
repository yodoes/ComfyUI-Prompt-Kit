"""
字典节点
  1. PromptKit · 字典选词
  2. PromptKit · 字典面板
  3. PromptKit · 新增字典词条
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from ...core.dictionary_service import dictionary_service
    from ...core.settings import settings
except ImportError:
    from core.dictionary_service import dictionary_service
    from core.settings import settings



def _effective_seed(seed: int) -> int:
    """seed==0 时每次变化；非 0 可复现。"""
    s = int(seed) & 0xFFFFFFFF
    if s == 0:
        s = (time.time_ns() ^ id(object())) & 0xFFFFFFFF
        if s == 0:
            s = 1
    return s


def _join(texts: List[str]) -> str:
    sep = settings.get("separator", ", ") or ", "
    seen = set()
    out: List[str] = []
    for t in texts:
        t = (t or "").strip().rstrip(",")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return sep.join(out)


def _parse_cat_id(label: str) -> Optional[str]:
    """从中文名、id、或旧格式 id|中文名 解析大类 id。"""
    label = (label or "").strip()
    if not label or label == "全部":
        return None
    if "|" in label:
        return label.split("|")[0].strip()
    tree = dictionary_service.get_category_tree(include_misc=True, include_nsfw=True)
    for c in tree:
        if c.get("id") == label or (c.get("name") or "").strip() == label:
            return c.get("id")
    return label


def _cat_choices(include_misc: bool = False, include_nsfw: bool = False) -> List[str]:
    tree = dictionary_service.get_category_tree(include_misc=include_misc, include_nsfw=include_nsfw)
    return ["全部"] + [(c.get("name") or c.get("id") or "") for c in tree]


def _resolve_sub_ids(
    category_label: str,
    subcategory_filter: str,
    include_misc: bool,
    include_nsfw: bool = False,
) -> Optional[List[str]]:
    tree = dictionary_service.get_category_tree(include_misc=include_misc, include_nsfw=include_nsfw)
    cid = _parse_cat_id(category_label)
    kw = (subcategory_filter or "").strip().lower()
    candidates = []
    for c in tree:
        if cid and c["id"] != cid:
            continue
        for ch in c.get("children", []):
            if kw:
                name = (ch.get("name") or "").lower()
                sid = (ch.get("id") or "").lower()
                if kw not in name and kw not in sid:
                    continue
            candidates.append(ch["id"])
    return candidates if (cid or kw) else None


def _collect_entries(
    *,
    mode: str,
    query: str,
    category: str,
    subcategory_filter: str,
    include_misc: bool,
    limit_scan: int,
    include_nsfw: bool = False,
) -> List[Dict[str, Any]]:
    mode = (mode or "搜索").strip()
    query = (query or "").strip()

    if mode == "收藏":
        fav_ids = dictionary_service.list_favorites()
        rows = []
        for eid in fav_ids:
            e = dictionary_service.get_entry_by_id(eid, include_misc=True, include_nsfw=True)
            if e:
                if query:
                    blob = " ".join(
                        [
                            str(e.get("text_zh") or ""),
                            str(e.get("text") or ""),
                            " ".join(e.get("tags") or []),
                        ]
                    ).lower()
                    if query.lower() not in blob:
                        continue
                rows.append(e)
            if len(rows) >= limit_scan:
                break
        return rows

    sub_ids = _resolve_sub_ids(category, subcategory_filter, include_misc, include_nsfw)
    if mode == "搜索":
        if not query and not subcategory_filter and _parse_cat_id(category) is None:
            return []
        return dictionary_service.search(
            query or "",
            subcategory_ids=sub_ids,
            include_misc=include_misc,
            include_nsfw=include_nsfw,
            language="both",
            limit=limit_scan,
        )

    # 分类浏览
    if sub_ids is None:
        sub_ids = dictionary_service.list_subcategory_ids(
            include_misc=include_misc, include_nsfw=include_nsfw
        )
    rows: List[Dict[str, Any]] = []
    for sid in sub_ids:
        for e in dictionary_service.load_subcategory(sid):
            if query:
                blob = " ".join(
                    [
                        str(e.get("text_zh") or ""),
                        str(e.get("text") or ""),
                        " ".join(e.get("tags") or []),
                    ]
                ).lower()
                if query.lower() not in blob:
                    continue
            rows.append(e)
            if len(rows) >= limit_scan:
                return rows
    return rows


def _display(e: Dict[str, Any], language: str) -> str:
    return dictionary_service.display_text(e, language)


class PromptKitDictionaryPick:
    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "模式": (["搜索", "分类浏览", "收藏"], {"default": "搜索", "tooltip": "选词模式"}),
                "关键词": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "搜索关键词；分类浏览时可作二次过滤"},
                ),
                "大类": (_cat_choices(False), {"default": "全部", "tooltip": "字典大类（仅中文名）"}),
                "中类过滤": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "中类名称包含（如：景别、表情）。可空"},
                ),
                "取用方式": (["前N条", "仅第1条", "随机N条"], {"default": "前N条", "tooltip": "从结果中取用规则"}),
                "数量": ("INT", {"default": 8, "min": 1, "max": 100, "tooltip": "取用条数"}),
                "语言": (["zh", "en", "both"], {"default": "zh", "tooltip": "输出语言"}),
            },
            "optional": {
                "面板文本": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "由字典面板写入；非空时优先作为输出"},
                ),
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF, "control_after_generate": True, "tooltip": "随机取用种子；0=每次自动变化；非0可复现"}),
                "含素材池": ("BOOLEAN", {"default": False, "tooltip": "是否包含「素材池」大类"}),
                "含NSFW": ("BOOLEAN", {"default": False, "tooltip": "是否包含 NSFW 分类"}),
                "扫描上限": ("INT", {"default": 300, "min": 20, "max": 2000, "tooltip": "最多扫描条数"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("文本", "预览", "命中数")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/选词"
    SEARCH_ALIASES = ["pk", "promptkit", "字典", "选词", "字典选词"]
    DESCRIPTION = "字典选词：搜索 / 分类浏览 / 收藏。可打开字典面板点选。"

    def run(
        self,
        **kwargs,
    ) -> Tuple[str, str, int]:
        mode = kwargs.get("模式") or kwargs.get("mode") or "搜索"
        query = kwargs.get("关键词") if "关键词" in kwargs else kwargs.get("query", "")
        category = kwargs.get("大类") if "大类" in kwargs else kwargs.get("category", "全部")
        subcategory_filter = kwargs.get("中类过滤") if "中类过滤" in kwargs else kwargs.get("subcategory_filter", "")
        pick = kwargs.get("取用方式") if "取用方式" in kwargs else kwargs.get("pick", "前N条")
        n = int(kwargs.get("数量") if "数量" in kwargs else kwargs.get("n", 8))
        language = kwargs.get("语言") if "语言" in kwargs else kwargs.get("language", "zh")
        panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
        seed = int(kwargs.get("随机种子") if "随机种子" in kwargs else kwargs.get("seed", 0))
        include_misc = bool(kwargs.get("含素材池") if "含素材池" in kwargs else kwargs.get("include_misc", False))
        include_nsfw = bool(kwargs.get("含NSFW") if "含NSFW" in kwargs else kwargs.get("include_nsfw", False))
        scan_limit = int(kwargs.get("扫描上限") if "扫描上限" in kwargs else kwargs.get("scan_limit", 300))

        panel = (panel_text or "").strip()
        if panel:
            return (panel, panel, panel.count(",") + 1 if panel else 0)

        rows = _collect_entries(
            mode=mode,
            query=query or "",
            category=category or "全部",
            subcategory_filter=subcategory_filter or "",
            include_misc=include_misc,
            limit_scan=scan_limit,
            include_nsfw=include_nsfw,
        )
        total = len(rows)
        if not rows:
            return ("", "无匹配词条", 0)

        if pick == "仅第1条":
            chosen = rows[:1]
        elif pick == "随机N条":
            rng = random.Random(_effective_seed(seed))
            k = min(n, len(rows))
            chosen = rng.sample(rows, k)
        else:
            chosen = rows[:n]

        texts = [_display(e, language) for e in chosen]
        text = _join(texts)
        preview = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
        return (text, preview, total)


class PromptKitDictionaryPanel:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "面板文本": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "由「打开字典面板」写入选中词条"},
                ),
            },
            "optional": {
                "分隔符": ("STRING", {"default": ", ", "tooltip": "多词条拼接分隔符"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文本",)
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/选词"
    SEARCH_ALIASES = ["pk", "promptkit", "字典", "字典面板"]
    DESCRIPTION = "打开字典面板点选词条，输出拼接文本。"

    def run(self, **kwargs) -> tuple:
        panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
        separator = kwargs.get("分隔符") if "分隔符" in kwargs else kwargs.get("separator", ", ")
        text = (panel_text or "").strip()
        if not text:
            return ("",)
        if "\n" in text and separator not in text.split("\n")[0]:
            parts = [ln.strip().rstrip(",") for ln in text.splitlines() if ln.strip()]
            sep = separator if separator is not None else ", "
            return (sep.join(parts),)
        return (text,)


class PromptKitDictionaryAdd:
    """独立新增字典词条节点。"""

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        # 中类下拉：扁平 name（带大类前缀便于识别）
        tree = dictionary_service.get_category_tree(include_misc=True, include_nsfw=True)
        sub_labels = []
        for c in tree:
            cname = c.get("name") or c.get("id")
            for ch in c.get("children", []):
                n = ch.get("name") or ch.get("id")
                sub_labels.append(f"{cname} / {n}")
        if not sub_labels:
            sub_labels = ["(无分类)"]
        return {
            "required": {
                "中类": (sub_labels, {"default": sub_labels[0], "tooltip": "词条所属中类"}),
                "中文词条": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "中文 text_zh（必填其一）"},
                ),
                "英文词条": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "英文 text（可空）"},
                ),
                "标签": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "标签，逗号分隔"},
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("结果", "词条ID")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/管理"
    SEARCH_ALIASES = ["pk", "promptkit", "字典", "新增", "添加词条"]
    DESCRIPTION = "向指定中类新增一条字典词条（写入用户覆盖层）。"

    def run(self, **kwargs) -> Tuple[str, str]:
        sub_label = kwargs.get("中类") if "中类" in kwargs else kwargs.get("subcategory", "")
        text_zh = (kwargs.get("中文词条") if "中文词条" in kwargs else kwargs.get("text_zh", "")) or ""
        text_en = (kwargs.get("英文词条") if "英文词条" in kwargs else kwargs.get("text", "")) or ""
        tags_s = (kwargs.get("标签") if "标签" in kwargs else kwargs.get("tags", "")) or ""
        text_zh = text_zh.strip()
        text_en = text_en.strip()
        if not text_zh and not text_en:
            return ("请填写中文或英文词条", "")
        # resolve subcategory id from "大类 / 中类"
        sid = ""
        tree = dictionary_service.get_category_tree(include_misc=True, include_nsfw=True)
        target = (sub_label or "").split("/")[-1].strip()
        for c in tree:
            for ch in c.get("children", []):
                n = (ch.get("name") or "").strip()
                if n == target or f"{c.get('name')} / {n}" == (sub_label or "").strip():
                    sid = ch.get("id") or ""
                    break
            if sid:
                break
        if not sid:
            return (f"未找到中类：{sub_label}", "")
        tags = [x.strip() for x in tags_s.replace("，", ",").split(",") if x.strip()]
        entry = dictionary_service.add_user_entry(
            sid,
            text=text_en or text_zh,
            text_zh=text_zh,
            tags=tags,
        )
        disp = dictionary_service.display_text(entry, "zh")
        return (f"已添加：{disp}", entry.get("id") or "")


NODE_CLASS_MAPPINGS = {
    "PromptKitDictionaryPick": PromptKitDictionaryPick,
    "PromptKitDictionaryPanel": PromptKitDictionaryPanel,
    "PromptKitDictionaryAdd": PromptKitDictionaryAdd,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptKitDictionaryPick": "PromptKit · 字典选词",
    "PromptKitDictionaryPanel": "PromptKit · 字典面板",
    "PromptKitDictionaryAdd": "PromptKit · 新增字典词条",
}
