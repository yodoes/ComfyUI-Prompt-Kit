"""
结构化分槽小节点：按分组「不选 / 随机 / 指定」，多组合并输出。
SFW 分槽「含 NSFW」仅合并薄 overlay（组名 N· 前缀）；完整成人服饰请用「着装服饰」节点。
新增分组需重启后才出现新下拉；「其它/未归组」兜底。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Set, Tuple, Type

try:
    from ...core.builder_service import builder_service
    from ...core.settings import settings
except ImportError:
    from core.builder_service import builder_service
    from core.settings import settings

NONE = "(不选)"
RANDOM = "(随机)"
OTHER = "其它/未归组"
OTHER_PREFIX_SEP = " · "


def _effective_seed(seed: int) -> int:
    s = int(seed) & 0xFFFFFFFF
    if s == 0:
        s = (time.time_ns() ^ id(object())) & 0xFFFFFFFF
        if s == 0:
            s = 1
    return s


def _slot_meta(slot_id: str, *, nsfw_slot: bool) -> Dict[str, Any]:
    try:
        for s in builder_service.list_slots(nsfw=bool(nsfw_slot)):
            if s.get("id") == slot_id:
                return s
    except Exception:
        pass
    return {"id": slot_id, "groups": []}


def _merge_groups(slot_id: str, *, nsfw: bool, is_nsfw_slot: bool) -> List[str]:
    """index 声明顺序 ∪ 数据中出现的 group（不含空）。
    薄 overlay 的 N· 组始终排在正式组之后，便于 SFW 节点扫读。
    """
    meta = _slot_meta(slot_id, nsfw_slot=is_nsfw_slot)
    ordered: List[str] = []
    seen: Set[str] = set()
    for g in meta.get("groups") or []:
        g = (g or "").strip()
        if g and g not in seen:
            seen.add(g)
            ordered.append(g)
    try:
        rows = builder_service.load_slot(slot_id, nsfw=nsfw)
    except Exception:
        rows = []
    for r in rows:
        g = (r.get("group") or "").strip()
        if g and g not in seen:
            seen.add(g)
            ordered.append(g)
    # 正式组在前，N· 薄 overlay 组在后
    primary = [g for g in ordered if not str(g).startswith("N·")]
    thin = [g for g in ordered if str(g).startswith("N·")]
    return primary + thin


def _group_combo(
    slot_id: str,
    group: str,
    *,
    nsfw: bool,
    known_groups: Set[str],
    limit: int = 500,
) -> List[str]:
    """某分组的下拉：不选 / 随机 / 词条…；其它组可带「组名 · 词」前缀。"""
    opts = [NONE, RANDOM]
    try:
        rows = builder_service.load_slot(slot_id, nsfw=nsfw)
    except Exception:
        rows = []
    seen: Set[str] = set()
    count = 0
    for r in rows:
        g = (r.get("group") or "").strip()
        t = (r.get("text_zh") or "").strip()
        if not t or t in (NONE, RANDOM) or t in seen:
            continue
        if group == OTHER:
            if g and g in known_groups:
                continue
            label = f"{g}{OTHER_PREFIX_SEP}{t}" if g else t
        else:
            if g != group:
                continue
            label = t
        seen.add(t)
        opts.append(label)
        count += 1
        if count >= limit:
            break
    return opts


def _strip_other_prefix(label: str) -> str:
    s = (label or "").strip()
    if OTHER_PREFIX_SEP in s:
        return s.split(OTHER_PREFIX_SEP, 1)[-1].strip()
    return s


def _make_slot_node(*, slot_id: str, name_zh: str, is_nsfw_slot: bool, class_key: str) -> Type:
    category = "PromptKit/结构化/NSFW" if is_nsfw_slot else "PromptKit/结构化/分模块"
    # 下拉构建时尽量带上 NSFW 包词，运行时再按「含NSFW」过滤
    load_nsfw = True

    groups = _merge_groups(slot_id, nsfw=load_nsfw or is_nsfw_slot, is_nsfw_slot=is_nsfw_slot)
    known = set(groups)
    group_widgets = list(groups) + [OTHER]

    class SlotNode:
        SLOT_ID = slot_id
        IS_NSFW_SLOT = is_nsfw_slot
        CLASS_KEY = class_key
        GROUP_WIDGETS = group_widgets
        KNOWN_GROUPS = known

        @classmethod
        def INPUT_TYPES(cls):
            sep_default = settings.get("separator", ", ") or ", "
            required: Dict[str, Any] = {
                "选词方式": (
                    ["节点组词", "面板文本"],
                    {
                        "default": "节点组词",
                        "tooltip": "节点组词：按分组不选/随机/指定；面板文本：用面板写入",
                    },
                ),
            }
            for g in group_widgets:
                combo = _group_combo(
                    slot_id,
                    g,
                    nsfw=load_nsfw or is_nsfw_slot,
                    known_groups=known,
                )
                if g == OTHER:
                    tip = "不在固定分组中的词（含空组、面板新建组未重启前）；显示为「组名 · 词条」"
                elif str(g).startswith("N·"):
                    tip = f"薄 overlay 分组「{g}」：需开启「含NSFW」才参与组词；完整成人服饰请用着装服饰节点"
                else:
                    tip = f"分组「{g}」：不选 / 随机 / 指定；新分组需重启后出现下拉"
                required[g] = (combo, {"default": NONE, "tooltip": tip})

            required["分隔符"] = (
                "STRING",
                {"default": sep_default, "multiline": False, "tooltip": "多词条分隔符"},
            )
            required["去重"] = ("BOOLEAN", {"default": True, "tooltip": "去重"})
            required["启用权重"] = ("BOOLEAN", {"default": False, "tooltip": "输出权重语法"})
            required["随机种子"] = (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFF,
                    "control_after_generate": True,
                    "tooltip": "各「随机」组共用；0=每次自动变化；组间用种子偏移保证可复现差异",
                },
            )
            required["随机条数"] = (
                "INT",
                {
                    "default": 1,
                    "min": 1,
                    "max": 5,
                    "tooltip": "每个设为「随机」的分组各抽几条",
                },
            )
            optional: Dict[str, Any] = {
                "面板文本": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "面板写入；选词方式=面板文本时输出此项",
                    },
                ),
            }
            if not is_nsfw_slot:
                optional["含NSFW"] = (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "仅合并本槽薄 overlay（组名以 N· 开头）。完整成人服饰请用「着装服饰」专用节点，勿依赖本开关。",
                    },
                )
            return {"required": required, "optional": optional}

        RETURN_TYPES = ("STRING", "INT")
        RETURN_NAMES = ("文本", "数量")
        FUNCTION = "run"
        CATEGORY = category
        SEARCH_ALIASES = ["pk", "promptkit", "结构化", name_zh, slot_id, "着装"] if is_nsfw_slot else ["pk", "promptkit", "结构化", name_zh, slot_id]
        DESCRIPTION = (
            f"结构化分槽「{name_zh}」：按分组不选/随机/指定，多组合并；含「{OTHER}」兜底。"
            + (
                "（NSFW 专用槽，数据来自 builder_nsfw。）"
                if is_nsfw_slot
                else " SFW 默认干净；「含NSFW」仅薄 overlay（N·组），完整成人服饰见「着装服饰」。"
            )
        )

        def run(self, **kwargs):
            pick_mode = kwargs.get("选词方式") or kwargs.get("pick_mode") or "节点组词"
            separator = kwargs.get("分隔符") if "分隔符" in kwargs else kwargs.get("separator", ", ")
            dedupe = bool(kwargs.get("去重") if "去重" in kwargs else kwargs.get("dedupe", True))
            enable_weight = bool(
                kwargs.get("启用权重") if "启用权重" in kwargs else kwargs.get("enable_weight", False)
            )
            seed = int(kwargs.get("随机种子") if "随机种子" in kwargs else kwargs.get("seed", 0))
            random_n = int(
                kwargs.get("随机条数") if "随机条数" in kwargs else kwargs.get("random_n", 1)
            )
            panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
            include_nsfw = bool(
                kwargs.get("含NSFW") if "含NSFW" in kwargs else kwargs.get("include_nsfw", False)
            )

            panel = (panel_text or "").strip()
            nsfw = True if is_nsfw_slot else bool(include_nsfw)
            mode = (pick_mode or "节点组词").strip()

            if mode == "面板文本":
                return (panel, 1 if panel else 0)

            base_seed = _effective_seed(seed)
            ids: List[str] = []
            seen_id: Set[str] = set()

            def _add(id_list: List[str]) -> None:
                for i in id_list:
                    i = str(i)
                    if i and i not in seen_id:
                        seen_id.add(i)
                        ids.append(i)

            # 兼容旧工作流里残留的「词条」单字段
            legacy = kwargs.get("词条") if "词条" in kwargs else None
            if legacy and str(legacy).strip() and str(legacy).strip() not in (NONE, RANDOM):
                _add(builder_service.resolve_texts_to_ids(slot_id, [str(legacy).strip()], nsfw=nsfw))
            elif legacy and str(legacy).strip() == RANDOM:
                _add(
                    builder_service.random_ids(
                        slot_id, n=random_n, nsfw=nsfw, seed=base_seed
                    )
                )

            for gi, g in enumerate(group_widgets):
                # SFW：未开含NSFW 时跳过 N· 薄 overlay 分组
                if (not is_nsfw_slot) and (not include_nsfw) and str(g).startswith("N·"):
                    continue
                val = kwargs.get(g)
                if val is None:
                    continue
                val = str(val).strip()
                if not val or val == NONE:
                    continue
                if val == RANDOM:
                    if g == OTHER:
                        try:
                            rows = builder_service.load_slot(slot_id, nsfw=nsfw)
                        except Exception:
                            rows = []
                        pool = [
                            r
                            for r in rows
                            if not (r.get("group") or "").strip()
                            or (r.get("group") or "").strip() not in known
                        ]
                        if pool:
                            import random as _random

                            rng = _random.Random((base_seed + gi * 10007) & 0xFFFFFFFF)
                            n = max(1, min(int(random_n), len(pool)))
                            picked = rng.sample(pool, n)
                            _add([str(r.get("id")) for r in picked if r.get("id")])
                    else:
                        _add(
                            builder_service.random_ids(
                                slot_id,
                                n=random_n,
                                nsfw=nsfw,
                                seed=(base_seed + gi * 10007) & 0xFFFFFFFF,
                                group=g,
                            )
                        )
                else:
                    text = _strip_other_prefix(val) if g == OTHER else val
                    _add(builder_service.resolve_texts_to_ids(slot_id, [text], nsfw=nsfw))

            selected = {slot_id: ids} if ids else {}
            result = builder_service.compose(
                selected,
                nsfw=nsfw,
                separator=separator if separator is not None else ", ",
                dedupe=bool(dedupe),
                enable_weight=bool(enable_weight),
                prefix="",
                suffix="",
                enabled={slot_id: True},
            )
            text = result.get("text") or ""
            count = int((result.get("counts") or {}).get(slot_id) or 0)
            return (text, count)

    SlotNode.__name__ = class_key
    SlotNode.__qualname__ = class_key
    return SlotNode


def build_slot_mappings():
    class_map = {}
    display_map = {}
    builder_service.load_sfw_index()
    builder_service.load_nsfw_index()
    for s in builder_service.list_slots(nsfw=False):
        sid = s["id"]
        key = "PromptKitSlot_" + "".join(p.capitalize() for p in sid.split("_"))
        cls = _make_slot_node(
            slot_id=sid, name_zh=s.get("name_zh") or sid, is_nsfw_slot=False, class_key=key
        )
        class_map[key] = cls
        display_map[key] = f"PromptKit · {s.get('name_zh') or sid}"
    for s in builder_service.list_slots(nsfw=True):
        if not s.get("nsfw"):
            continue
        sid = s["id"]
        key = "PromptKitSlot_" + "".join(p.capitalize() for p in sid.split("_"))
        cls = _make_slot_node(
            slot_id=sid, name_zh=s.get("name_zh") or sid, is_nsfw_slot=True, class_key=key
        )
        class_map[key] = cls
        display_map[key] = f"PromptKit · {s.get('name_zh') or sid}"
    return class_map, display_map


_SLOT_CLASS_MAPPINGS, _SLOT_DISPLAY_MAPPINGS = build_slot_mappings()
NODE_CLASS_MAPPINGS = dict(_SLOT_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS = dict(_SLOT_DISPLAY_MAPPINGS)
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "build_slot_mappings"]
