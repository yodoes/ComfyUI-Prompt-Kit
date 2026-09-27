"""
字典节点（阶段 2 打磨版）

日常只需两个节点：
  1. PromptKit · 字典选词   — 搜索 / 分类浏览 / 收藏，一键取词
  2. PromptKit · 字典管理   — 添加词条、收藏、取消收藏

设计原则：
  - 不要求用户手填 entry_id 或行号
  - 大类 13 项下拉（不用 73 中类长列表）
  - 中类用「名称包含」过滤，可选
  - 取用方式明确：全部(限N) / 第一条 / 随机N条
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

try:
    from ...core.dictionary_service import dictionary_service
    from ...core.settings import settings
except ImportError:
    from core.dictionary_service import dictionary_service
    from core.settings import settings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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
    """从 '01_xxx|中文名' 或 '全部' 解析大类 id。"""
    label = (label or "").strip()
    if not label or label == "全部":
        return None
    return label.split("|")[0].strip()


def _cat_choices(include_misc: bool = False) -> List[str]:
    tree = dictionary_service.get_category_tree(include_misc=include_misc)
    return ["全部"] + [f"{c['id']}|{c['name']}" for c in tree]


def _resolve_sub_ids(
    category_label: str,
    subcategory_filter: str,
    include_misc: bool,
) -> Optional[List[str]]:
    """
    根据大类 + 中类名称过滤，得到要扫描的 subcategory id 列表。
    返回 None 表示「全部正式分类」。
    """
    tree = dictionary_service.get_category_tree(include_misc=include_misc)
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
) -> List[Dict[str, Any]]:
    """按模式收集候选词条（尚未做最终取用裁剪）。"""
    mode = (mode or "搜索").strip()
    query = (query or "").strip()

    if mode == "收藏":
        fav_ids = dictionary_service.list_favorites()
        entries: List[Dict[str, Any]] = []
        for eid in fav_ids:
            e = dictionary_service.get_entry_by_id(eid, include_misc=True)
            if not e:
                continue
            if query:
                blob = f"{e.get('text','')} {e.get('text_zh','')} {e.get('id','')}".lower()
                if query.lower() not in blob:
                    continue
            entries.append(e)
            if len(entries) >= limit_scan:
                break
        return entries

    sub_ids = _resolve_sub_ids(category, subcategory_filter, include_misc)

    if mode == "搜索":
        if not query and not subcategory_filter and _parse_cat_id(category) is None:
            # 无任何条件时不扫全库，避免卡顿
            return []
        return dictionary_service.search(
            query or "",  # 空 query 时仍可用 tags/范围；服务层空 query + 无 tags 会返回 []
            subcategory_ids=sub_ids,
            include_misc=include_misc,
            language="both",
            limit=limit_scan,
        )

    # 分类浏览：加载范围内全部，再按 query 本地过滤
    if sub_ids is None:
        sub_ids = dictionary_service.list_subcategory_ids(include_misc=include_misc)

    entries = []
    q = query.lower()
    for sid in sub_ids:
        for e in dictionary_service.load_subcategory(sid):
            if q:
                blob = f"{e.get('text','')} {e.get('text_zh','')}".lower()
                if q not in blob:
                    continue
            entries.append(e)
            if len(entries) >= limit_scan:
                return entries
    return entries


def _pick(
    entries: List[Dict[str, Any]],
    pick_mode: str,
    n: int,
    seed: int,
) -> List[Dict[str, Any]]:
    if not entries:
        return []
    pick_mode = (pick_mode or "前N条").strip()
    n = max(1, min(int(n), 200))

    if pick_mode == "仅第1条":
        return entries[:1]
    if pick_mode == "随机N条":
        rng = random.Random(seed)
        k = min(n, len(entries))
        return rng.sample(entries, k)
    # 前N条
    return entries[:n]


def _preview(entries: List[Dict[str, Any]], language: str, max_lines: int = 40) -> str:
    lines = []
    for i, e in enumerate(entries[:max_lines]):
        d = dictionary_service.display_text(e, language)
        src = e.get("subcategory") or e.get("category") or ""
        lines.append(f"{i+1}. {d}  · {src}")
    if len(entries) > max_lines:
        lines.append(f"… 共 {len(entries)} 条，仅预览前 {max_lines} 条")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 节点 1：字典选词（日常主节点）
# ---------------------------------------------------------------------------

class PromptKitDictionaryPick:
    """
    一站式选词：搜索 / 按大类浏览 / 从收藏取词。
    不需要手填 id 或行号。
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "mode": (["搜索", "分类浏览", "收藏"], {"default": "搜索"}),
                "query": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "搜索关键词；分类浏览时作二次过滤；收藏时过滤收藏夹",
                    },
                ),
                "category": (_cat_choices(False), {"default": "全部"}),
                "subcategory_filter": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "中类名称包含（如：景别、表情、连衣裙）。可空",
                    },
                ),
                "pick": (["前N条", "仅第1条", "随机N条"], {"default": "前N条"}),
                "n": ("INT", {"default": 8, "min": 1, "max": 100}),
                "language": (["zh", "en", "both"], {"default": "zh"}),
            },
            "optional": {
                "panel_text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "由「打开字典面板」写入；非空时优先作为输出 text",
                    },
                ),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "include_misc": ("BOOLEAN", {"default": False}),
                "scan_limit": ("INT", {"default": 300, "min": 20, "max": 2000}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("text", "preview", "hit_count")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/选词"
    SEARCH_ALIASES = ["pk", "PK", "promptkit", "字典", "选词", "字典选词"]
    DESCRIPTION = "字典选词：搜索 / 分类浏览 / 收藏。输出可直接接入提示词。节点上可点「打开字典面板」。"

    def run(
        self,
        mode: str,
        query: str,
        category: str,
        subcategory_filter: str,
        pick: str,
        n: int,
        language: str,
        panel_text: str = "",
        seed: int = 0,
        include_misc: bool = False,
        scan_limit: int = 300,
    ) -> Tuple[str, str, int]:
        # 面板写入优先
        panel_text = (panel_text or "").strip()
        if panel_text:
            lines = [ln.strip() for ln in panel_text.replace(",", "\n").splitlines() if ln.strip()]
            preview = "\n".join(f"{i+1}. {t}" for i, t in enumerate(lines[:40]))
            return (panel_text, preview or panel_text, len(lines) or 1)

        # 搜索模式下空 query 且无范围 → 友好提示
        if mode == "搜索" and not (query or "").strip():
            if _parse_cat_id(category) is None and not (subcategory_filter or "").strip():
                return (
                    "",
                    "请输入关键词，或先选大类 / 填写中类过滤后再搜索。",
                    0,
                )

        # 分类浏览无大类且无中类过滤时，要求至少限定范围
        if mode == "分类浏览":
            if _parse_cat_id(category) is None and not (subcategory_filter or "").strip():
                return (
                    "",
                    "分类浏览请先选择大类，或填写中类名称过滤（如：景别）。",
                    0,
                )

        candidates = _collect_entries(
            mode=mode,
            query=query,
            category=category,
            subcategory_filter=subcategory_filter,
            include_misc=include_misc,
            limit_scan=scan_limit,
        )
        chosen = _pick(candidates, pick, n, seed)
        text = _join([dictionary_service.display_text(e, language) for e in chosen])
        preview = _preview(candidates, language)
        if not candidates:
            preview = "无命中。可尝试更短关键词、换大类，或检查中类过滤写法。"
        return (text, preview, len(candidates))


# ---------------------------------------------------------------------------
# 节点 2：字典管理（添加 / 收藏）
# ---------------------------------------------------------------------------

class PromptKitDictionaryManage:
    """
    字典侧写操作：添加自定义词条、按关键词收藏/取消收藏、列出收藏。
    收藏不依赖手填 id：用「搜索第一条命中」来定位。
    """

    @classmethod
    def INPUT_TYPES(cls) -> Dict[str, Any]:
        return {
            "required": {
                "action": (
                    [
                        "列出收藏",
                        "收藏：搜索第一条",
                        "取消收藏：搜索第一条",
                        "添加词条",
                    ],
                    {"default": "列出收藏"},
                ),
                "query": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "收藏/取消时：用于定位词条的关键词；添加时作英文 text",
                    },
                ),
                "category": (_cat_choices(True), {"default": "全部"}),
                "text_zh": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "添加词条时的中文；收藏操作可忽略",
                    },
                ),
                "subcategory_filter": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "添加词条时必填中类线索（如：表情）；收藏时可选缩小范围",
                    },
                ),
                "language": (["zh", "en", "both"], {"default": "zh"}),
            },
            "optional": {
                "tags": ("STRING", {"default": "", "multiline": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("message", "detail")
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/管理"
    SEARCH_ALIASES = ["pk", "PK", "promptkit", "字典", "收藏", "添加词条", "字典管理"]
    DESCRIPTION = "添加词条 / 收藏管理。收藏用关键词定位，无需手填 id。节点上可点「打开字典面板」。"

    def run(
        self,
        action: str,
        query: str,
        category: str,
        text_zh: str,
        subcategory_filter: str,
        language: str,
        tags: str = "",
    ) -> Tuple[str, str]:
        action = (action or "").strip()
        query = (query or "").strip()
        text_zh = (text_zh or "").strip()
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

        if action == "列出收藏":
            fav_ids = dictionary_service.list_favorites()
            lines = []
            texts = []
            for eid in fav_ids:
                e = dictionary_service.get_entry_by_id(eid, include_misc=True)
                if not e:
                    lines.append(f"(缺失) {eid}")
                    continue
                d = dictionary_service.display_text(e, language)
                lines.append(f"• {d}  [{eid}]")
                texts.append(d)
            msg = f"收藏共 {len(fav_ids)} 条"
            detail = _join(texts) if texts else "（空）"
            if lines:
                detail = detail + "\n\n" + "\n".join(lines[:50])
            return (msg, detail)

        if action in ("收藏：搜索第一条", "取消收藏：搜索第一条"):
            if not query:
                return ("请填写 query 关键词以定位词条", "")
            sub_ids = _resolve_sub_ids(category, subcategory_filter, include_misc=True)
            hits = dictionary_service.search(
                query,
                subcategory_ids=sub_ids,
                include_misc=True,
                language="both",
                limit=5,
            )
            if not hits:
                return (f"未找到与「{query}」匹配的词条", "")
            target = hits[0]
            eid = target.get("id") or ""
            disp = dictionary_service.display_text(target, language)
            if action.startswith("收藏"):
                dictionary_service.add_favorite(eid)
                return (f"已收藏：{disp}", eid)
            dictionary_service.remove_favorite(eid)
            return (f"已取消收藏：{disp}", eid)

        if action == "添加词条":
            text_en = query  # 约定：query 字段复用为英文 text
            if not text_en and not text_zh:
                return ("添加失败：请至少填写 query（英文）或 text_zh（中文）", "")
            sub_ids = _resolve_sub_ids(category, subcategory_filter, include_misc=True)
            if not sub_ids:
                return (
                    "添加失败：请选择大类，并填写中类线索（subcategory_filter，如：景别、基础表情）",
                    "",
                )
            # 若过滤出多个中类，取第一个；更稳妥是要求用户写准中类名
            sid = sub_ids[0]
            if len(sub_ids) > 1:
                # 优先精确匹配中类名
                kw = (subcategory_filter or "").strip().lower()
                tree = dictionary_service.get_category_tree(include_misc=True)
                for c in tree:
                    for ch in c.get("children", []):
                        if (ch.get("name") or "").lower() == kw or (ch.get("id") or "").lower() == kw:
                            sid = ch["id"]
                            break
            entry = dictionary_service.add_user_entry(
                sid,
                text=(text_en or text_zh),
                text_zh=text_zh,
                tags=tag_list,
            )
            return (
                f"已添加至 {sid}：{dictionary_service.display_text(entry, language)}",
                entry.get("id", ""),
            )

        return (f"未知操作：{action}", "")



# ---------------------------------------------------------------------------
# 节点 3：字典面板锚点（主要靠前端弹层选词，输出 panel_text）
# ---------------------------------------------------------------------------

class PromptKitDictionaryPanel:
    """
    字典面板入口：画布上点「打开字典面板」勾选词条，结果写入本节点 text 并输出。
    可与「字典选词」并用；本节点更适合纯点选工作流。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "panel_text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "由「打开字典面板」写入选中词条",
                    },
                ),
            },
            "optional": {
                "separator": ("STRING", {"default": ", "}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "run"
    CATEGORY = "PromptKit/字典/选词"
    SEARCH_ALIASES = ["pk", "PK", "promptkit", "字典", "字典面板", "面板"]
    DESCRIPTION = "打开字典面板点选词条，输出拼接文本。"

    def run(self, panel_text: str, separator: str = ", ") -> tuple:
        text = (panel_text or "").strip()
        if not text:
            return ("",)
        # 若用户从面板写入已是逗号拼接，直接返回；否则按行合并
        if "\n" in text and separator not in text.split("\n")[0]:
            parts = [ln.strip().rstrip(",") for ln in text.splitlines() if ln.strip()]
            sep = separator if separator is not None else ", "
            return (sep.join(parts),)
        return (text,)


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 注册（只暴露打磨后的 2 个节点；旧 4 节点移除）
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "PromptKitDictionaryPick": PromptKitDictionaryPick,
    "PromptKitDictionaryManage": PromptKitDictionaryManage,
    "PromptKitDictionaryPanel": PromptKitDictionaryPanel,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptKitDictionaryPick": "PromptKit · 字典选词",
    "PromptKitDictionaryManage": "PromptKit · 字典管理",
    "PromptKitDictionaryPanel": "PromptKit · 字典面板",
}
