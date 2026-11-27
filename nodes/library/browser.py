"""
词库节点
  1. PromptKit · 词库选词
  2. PromptKit · 词库面板
  3. PromptKit · 快速保存到词库
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Tuple

try:
    from ...core.library_service import library_service, _preset_text, _preset_title
    from ...core.settings import settings
except ImportError:
    from core.library_service import library_service, _preset_text, _preset_title
    from core.settings import settings



def _effective_seed(seed: int) -> int:
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
        t = (t or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return sep.join(out)


def _parse_tags(s: str) -> List[str]:
    if not s:
        return []
    import re
    return [x.strip() for x in re.split(r"[,，;；|/]", s) if x.strip()]


def _lib_choices(include_nsfw: bool = True) -> List[str]:
    choices = library_service.library_choices(include_nsfw=include_nsfw)
    return choices if choices else ["(无词库)"]


class PromptKitLibraryPick:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "词库": (
                    _lib_choices(True),
                    {"tooltip": "选择词库；名称带 [NSFW] 的为成人库，需打开 含NSFW"},
                ),
                "模式": (
                    ["全部", "搜索", "收藏"],
                    {"default": "全部", "tooltip": "浏览模式"},
                ),
                "关键词": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "搜索标题 / 正文 / 标签"},
                ),
                "标签": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "标签筛选，逗号分隔；多标签默认 AND"},
                ),
                "取用方式": (["前N条", "仅第1条", "随机N条"], {"default": "仅第1条", "tooltip": "结果取用规则"}),
                "数量": ("INT", {"default": 1, "min": 1, "max": 50, "tooltip": "取用条数"}),
                "语言": (["zh", "en", "both"], {"default": "zh", "tooltip": "输出语言"}),
                "拼接方式": (
                    ["换行", "逗号", "分号"],
                    {"default": "换行", "tooltip": "多条预设如何拼接"},
                ),
            },
            "optional": {
                "面板文本": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "由词库面板写入；非空时优先输出"},
                ),
                "随机种子": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF, "control_after_generate": True, "tooltip": "随机取用种子；0=每次自动变化；非0可复现"}),
                "含NSFW": ("BOOLEAN", {"default": False, "tooltip": "是否允许 NSFW 词库/预设"}),
                "扫描上限": ("INT", {"default": 200, "min": 10, "max": 2000, "tooltip": "最多扫描条数"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("文本", "预览", "命中数", "标题")
    FUNCTION = "run"
    CATEGORY = "PromptKit/词库/选词"
    SEARCH_ALIASES = ["pk", "promptkit", "词库", "预设", "词库选词", "library"]
    DESCRIPTION = "从词库选取完整提示词。可打开词库面板点选。"

    def run(self, **kwargs):
        library = kwargs.get("词库") if "词库" in kwargs else kwargs.get("library", "")
        mode = kwargs.get("模式") if "模式" in kwargs else kwargs.get("mode", "全部")
        query = kwargs.get("关键词") if "关键词" in kwargs else kwargs.get("query", "")
        tags = kwargs.get("标签") if "标签" in kwargs else kwargs.get("tags", "")
        pick = kwargs.get("取用方式") if "取用方式" in kwargs else kwargs.get("pick", "仅第1条")
        n = int(kwargs.get("数量") if "数量" in kwargs else kwargs.get("n", 1))
        language = kwargs.get("语言") if "语言" in kwargs else kwargs.get("language", "zh")
        join_mode = kwargs.get("拼接方式") if "拼接方式" in kwargs else kwargs.get("join_mode", "换行")
        panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
        seed = int(kwargs.get("随机种子") if "随机种子" in kwargs else kwargs.get("seed", 0))
        include_nsfw = bool(kwargs.get("含NSFW") if "含NSFW" in kwargs else kwargs.get("include_nsfw", False))
        limit = int(kwargs.get("扫描上限") if "扫描上限" in kwargs else kwargs.get("limit", 200))

        panel = (panel_text or "").strip()
        if panel:
            return (panel, panel, 1, "")

        lid = library_service.parse_library_choice(library)
        if not lid or lid.startswith("("):
            return ("", "请选择词库", 0, "")

        tag_list = _parse_tags(tags or "")
        favorites_only = mode == "收藏"
        use_query = query if mode in ("搜索", "全部", "收藏") else ""
        if mode == "搜索" and not (query or "").strip() and not tag_list:
            return ("", "搜索模式请填写关键词或标签。", 0, "")

        result = library_service.search_presets(
            lid,
            query=use_query if mode == "搜索" else (query or ""),
            category_id="",
            tags=tag_list,
            tag_mode="and",
            favorites_only=favorites_only,
            include_nsfw_presets=include_nsfw,
            language=language,
            offset=0,
            limit=max(limit, n),
        )
        presets = result.get("presets") or []
        total = int(result.get("total") or 0)
        if not presets:
            return ("", f"无匹配预设（库={lid}，命中 0）", 0, "")

        if pick == "仅第1条":
            chosen = presets[:1]
        elif pick == "随机N条":
            rng = random.Random(_effective_seed(seed))
            k = min(n, len(presets))
            chosen = rng.sample(presets, k)
        else:
            chosen = presets[:n]

        texts = [p.get("text") or "" for p in chosen if p.get("text")]
        titles = [p.get("title") or "" for p in chosen]
        if join_mode == "逗号":
            text = _join(texts)
        elif join_mode == "分号":
            seen = set()
            out = []
            for x in texts:
                x = (x or "").strip()
                if x and x not in seen:
                    seen.add(x)
                    out.append(x)
            text = "; ".join(out)
        else:
            text = "\n".join(x for x in texts if x)
        preview = "\n".join(
            f"{i+1}. [{t}] {(p.get('text') or '')[:100]}"
            for i, (t, p) in enumerate(zip(titles, chosen))
        )
        title_out = titles[0] if len(titles) == 1 else _join(titles)
        return (text, preview, total, title_out)


class PromptKitLibraryPanel:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "面板文本": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "由「打开词库面板」写入选中预设正文"},
                ),
            },
            "optional": {
                "分隔符": ("STRING", {"default": ", ", "tooltip": "多段拼接分隔符（默认多段用换行）"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文本",)
    FUNCTION = "run"
    CATEGORY = "PromptKit/词库/选词"
    SEARCH_ALIASES = ["pk", "promptkit", "词库", "词库面板"]
    DESCRIPTION = "词库面板入口：点选预设后输出完整提示词。"

    def run(self, **kwargs) -> tuple:
        panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
        separator = kwargs.get("分隔符") if "分隔符" in kwargs else kwargs.get("separator", ", ")
        text = (panel_text or "").strip()
        if not text:
            return ("",)
        if "\n" in text:
            parts = [ln.strip() for ln in text.splitlines() if ln.strip()]
            sep = separator if separator is not None else "\n"
            if sep == ", ":
                return ("\n".join(parts),)
            return (sep.join(parts),)
        return (text,)


class PromptKitLibraryQuickSave:
    """将上游文本快速保存为词库预设。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "词库": (_lib_choices(True), {"tooltip": "保存到哪个词库（用户库可写）"}),
                "标题": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "预设标题；可空则截取正文前 20 字"},
                ),
                "提示词": (
                    "STRING",
                    {"default": "", "multiline": True, "tooltip": "要保存的提示词正文（可接上游）"},
                ),
                "标签": (
                    "STRING",
                    {"default": "", "multiline": False, "tooltip": "标签，逗号分隔"},
                ),
            },
            "optional": {
                "标记NSFW": ("BOOLEAN", {"default": False, "tooltip": "是否标记为 NSFW 预设"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("结果", "预设ID", "提示词")
    FUNCTION = "run"
    CATEGORY = "PromptKit/词库/管理"
    SEARCH_ALIASES = ["pk", "promptkit", "词库", "保存", "快速保存"]
    DESCRIPTION = "将提示词快速保存到指定词库（新建一条预设）。"

    def run(self, **kwargs):
        library = kwargs.get("词库") if "词库" in kwargs else kwargs.get("library", "")
        title = kwargs.get("标题") if "标题" in kwargs else kwargs.get("title", "")
        prompt = kwargs.get("提示词") if "提示词" in kwargs else kwargs.get("prompt", "")
        tags = kwargs.get("标签") if "标签" in kwargs else kwargs.get("tags", "")
        nsfw = bool(kwargs.get("标记NSFW") if "标记NSFW" in kwargs else kwargs.get("nsfw", False))

        lid = library_service.parse_library_choice(library)
        prompt = (prompt or "").strip()
        if not lid or lid.startswith("("):
            return ("请选择词库", "", prompt)
        if not prompt:
            return ("提示词为空，未保存", "", "")
        title = (title or "").strip() or (prompt[:20] + ("…" if len(prompt) > 20 else ""))
        tag_list = _parse_tags(tags or "")
        try:
            preset = library_service.add_preset(
                lid,
                title_zh=title,
                prompt=prompt,
                tags=tag_list,
                nsfw=nsfw,
            )
            pid = preset.get("id") or ""
            return (f"已保存到词库：{title}", pid, prompt)
        except Exception as e:
            return (f"保存失败：{e}", "", prompt)


NODE_CLASS_MAPPINGS = {
    "PromptKitLibraryPick": PromptKitLibraryPick,
    "PromptKitLibraryPanel": PromptKitLibraryPanel,
    "PromptKitLibraryQuickSave": PromptKitLibraryQuickSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptKitLibraryPick": "PromptKit · 词库选词",
    "PromptKitLibraryPanel": "PromptKit · 词库面板",
    "PromptKitLibraryQuickSave": "PromptKit · 快速保存到词库",
}
