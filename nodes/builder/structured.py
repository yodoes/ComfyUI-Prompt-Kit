"""
结构化生成大节点（方案 B / B1）
- 每槽：不选 | 整槽随机 | 自定义
- 自定义组状态存「组词状态」JSON（浮窗 B3 写入；B1 可手改 JSON 测）
- 不再注册 70+ 组下拉
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from ...core.builder_service import builder_service
    from ...core.settings import settings
except ImportError:
    from core.builder_service import builder_service
    from core.settings import settings

NONE = "(不选)"
RANDOM = "(随机)"
ERA_OFF = "关闭"

MODE_NONE = "不选"
MODE_SLOT_RANDOM = "整槽随机"
MODE_CUSTOM = "自定义"
MODE_EDIT = "编辑组…"
SLOT_MODES = [MODE_NONE, MODE_SLOT_RANDOM, MODE_CUSTOM, MODE_EDIT]

SLOT_LABELS = {
    "style": "风格媒介",
    "camera": "镜头构图",
    "subject": "人物主体",
    "face": "面部妆容",
    "hair": "发型发色",
    "expression": "表情神态",
    "pose": "姿态动作",
    "clothing": "服装穿搭",
    "accessories": "配饰道具",
    "scene": "场景环境",
    "lighting": "光影氛围",
    "nsfw_clothing": "着装服饰",
    "nsfw_body": "身体与暴露",
    "nsfw_pose": "体位",
    "nsfw_act": "行为与互动",
    "nsfw_props": "道具与束缚",
    "nsfw_fluids": "痕迹与体液",
}
SFW_SLOTS = [
    "style", "camera", "subject", "face", "hair", "expression",
    "pose", "clothing", "accessories", "scene", "lighting",
]
EXTRA_SLOTS = [
    "nsfw_clothing", "nsfw_body", "nsfw_pose", "nsfw_act", "nsfw_props", "nsfw_fluids",
]

# 整槽随机时参与的组（方案 B §5）
SLOT_RANDOM_GROUPS: Dict[str, List[str]] = {
    "style": ["媒介", "风格"],
    "camera": ["景别"],
    "subject": ["性别", "年龄段"],
    "face": ["妆容"],
    "hair": ["发色", "长度造型"],
    "expression": ["表情"],
    "pose": ["站姿"],
    "clothing": ["套装"],
    "accessories": ["首饰"],
    "scene": ["地点"],
    "lighting": ["氛围"],
    "nsfw_clothing": ["外衣暴露"],
    "nsfw_body": ["暴露程度"],
    "nsfw_pose": ["基础体位"],
    "nsfw_act": ["行为"],
    "nsfw_props": ["道具"],
    "nsfw_fluids": ["痕迹"],
}

# 新建节点默认模式
SLOT_MODE_DEFAULTS: Dict[str, str] = {
    "style": MODE_SLOT_RANDOM,
    "camera": MODE_SLOT_RANDOM,
    "subject": MODE_SLOT_RANDOM,
    "face": MODE_NONE,
    "hair": MODE_NONE,
    "expression": MODE_SLOT_RANDOM,
    "pose": MODE_SLOT_RANDOM,
    "clothing": MODE_NONE,
    "accessories": MODE_NONE,
    "scene": MODE_SLOT_RANDOM,
    "lighting": MODE_SLOT_RANDOM,
    "nsfw_clothing": MODE_NONE,
    "nsfw_body": MODE_NONE,
    "nsfw_pose": MODE_NONE,
    "nsfw_act": MODE_NONE,
    "nsfw_props": MODE_NONE,
    "nsfw_fluids": MODE_NONE,
}


def _era_choices() -> List[str]:
    try:
        reg = (builder_service.load_sfw_index().get("tag_registry") or {}).get("era") or []
        eras = [str(x) for x in reg if x and str(x) != "通用"]
    except Exception:
        eras = ["现代", "古风中式", "仙侠玄幻", "民国年代", "西幻欧式", "科幻未来"]
    return [ERA_OFF] + eras


def _mode_widget_name(slot_id: str) -> str:
    return f"{SLOT_LABELS[slot_id]}·模式"


def _parse_states(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s:
        return {}
    try:
        data = json.loads(s)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _summary_from_slot_state(slot_id: str, mode: str, states: Dict[str, Any]) -> str:
    if mode == MODE_NONE:
        return "—"
    if mode == MODE_SLOT_RANDOM:
        groups = SLOT_RANDOM_GROUPS.get(slot_id) or []
        return "随机（" + "、".join(groups[:3]) + ("…" if len(groups) > 3 else "") + "）" if groups else "随机"
    st = states.get(slot_id) or {}
    groups = (st.get("groups") or {}) if isinstance(st, dict) else {}
    if not groups:
        return "自定义（空）"
    parts = []
    for g, cfg in groups.items():
        if not isinstance(cfg, dict):
            continue
        op = (cfg.get("op") or "none").lower()
        if op in ("none", "不选", ""):
            continue
        if op in ("random", "随机"):
            parts.append(f"{g}=随机")
        elif op in ("pick", "指定"):
            t = (cfg.get("text") or "").strip()
            parts.append(f"{g}={t or '指定'}")
    return " · ".join(parts[:6]) + ("…" if len(parts) > 6 else "") if parts else "自定义（均不选）"


def _effective_seed(seed: int) -> int:
    s = int(seed) & 0xFFFFFFFF
    if s == 0:
        s = (time.time_ns() ^ id(object())) & 0xFFFFFFFF
        if s == 0:
            s = 1
    return s


def _counts_json(counts: Dict[str, int]) -> str:
    try:
        return json.dumps(counts, ensure_ascii=False)
    except Exception:
        return "{}"


def _resolve_group_ops(
    slot_id: str,
    groups_cfg: Dict[str, Any],
    *,
    nsfw: bool,
    base_seed: int,
    seed_i: int,
    random_n: int,
    era: str,
) -> List[str]:
    """按组配置收集 term ids。"""
    ids: List[str] = []
    seen: Set[str] = set()
    gi = 0
    for g, cfg in (groups_cfg or {}).items():
        if not isinstance(cfg, dict):
            continue
        op = str(cfg.get("op") or "none").lower()
        g = str(g).strip()
        if not g:
            continue
        if op in ("none", "不选", ""):
            continue
        use_nsfw = nsfw or slot_id.startswith("nsfw_")
        if op in ("random", "随机"):
            got = builder_service.random_ids(
                slot_id,
                n=max(random_n * 4, 4) if (slot_id == "subject" and g == "性别") else random_n,
                nsfw=use_nsfw,
                seed=(base_seed + seed_i * 10007 + gi * 97) & 0xFFFFFFFF,
                group=g,
                era=era if era and era != ERA_OFF else "",
            )
            # 性别组：优先短词、避免年龄/族裔复合串进随机
            if slot_id == "subject" and g == "性别" and got:
                terms = builder_service.get_terms_by_ids(slot_id, got, nsfw=use_nsfw)
                pure = []
                for term in terms:
                    tx = (term.get("text_zh") or "").strip()
                    if not tx:
                        continue
                    if re.search(r"\d|岁|东亚|南亚|面孔|短发|长发|西装|裙装", tx):
                        continue
                    if len(tx) > 12:
                        continue
                    pure.append(str(term.get("id")))
                if pure:
                    got = pure[:random_n]
                else:
                    got = got[:random_n]
            for i in got:
                if i not in seen:
                    seen.add(i)
                    ids.append(i)
        elif op in ("pick", "指定"):
            text = (cfg.get("text") or "").strip()
            if text and text not in (NONE, RANDOM):
                got = builder_service.resolve_texts_to_ids(slot_id, [text], nsfw=use_nsfw)
                for i in got:
                    if i not in seen:
                        seen.add(i)
                        ids.append(i)
        gi += 1
    return ids


def _age_compatible(gender_text: str, age_text: str) -> bool:
    """粗过滤：避免「成熟男性+5岁」「女孩+40岁」类组合。"""
    g = gender_text or ""
    a = age_text or ""
    nums = [int(x) for x in re.findall(r"(\d{1,2})\s*岁", a)]
    num = nums[0] if nums else None
    child_g = bool(re.search(r"女孩|男孩|儿童|少女外形|少男外形|孩童", g))
    elder_g = bool(re.search(r"老太太|老大爷|老年", g))
    mature_g = bool(re.search(r"成熟|中年", g))
    young_g = bool(re.search(r"少女|少年|年轻|小伙|姑娘", g)) and not mature_g
    child_a = bool(re.search(r"儿童|孩童|幼|约五六岁|约十岁|十三|十四|十五|十六", a)) or (
        num is not None and num <= 14
    )
    elder_a = bool(re.search(r"老|古稀|银发|退休|知天命", a)) or (num is not None and num >= 60)
    adult_mid = bool(re.search(r"中年|而立|不惑|熟龄", a)) or (num is not None and 35 <= num <= 55)
    if child_g and (elder_a or adult_mid or (num is not None and num >= 25)):
        return False
    if elder_g and (child_a or (num is not None and num < 50) or re.search(r"少年感|少女感|青春|大学", a)):
        return False
    if mature_g and (child_a or (num is not None and num < 28)):
        return False
    if young_g and (elder_a or adult_mid or (num is not None and num >= 45)):
        return False
    if mature_g and elder_a:
        return False
    if not child_g and child_a:
        return False
    # 年龄文案里若残留性别且与主体性别字面冲突
    if re.search(r"女", a) and re.search(r"男", g) and not re.search(r"女", g):
        return False
    if re.search(r"男", a) and re.search(r"女", g) and not re.search(r"男", g):
        return False
    return True


def _slot_random_ids(
    slot_id: str,
    *,
    nsfw: bool,
    base_seed: int,
    seed_i: int,
    random_n: int,
    era: str,
) -> List[str]:
    groups = SLOT_RANDOM_GROUPS.get(slot_id) or []
    if not groups:
        return builder_service.random_ids(
            slot_id,
            n=random_n,
            nsfw=nsfw or slot_id.startswith("nsfw_"),
            seed=(base_seed + seed_i * 10007) & 0xFFFFFFFF,
            era=era if era and era != ERA_OFF else "",
        )
    # 主体：先性别后年龄，做兼容过滤
    if slot_id == "subject" and "性别" in groups and "年龄段" in groups:
        use_nsfw = nsfw or slot_id.startswith("nsfw_")
        era_arg = era if era and era != ERA_OFF else ""
        g_ids = _resolve_group_ops(
            slot_id,
            {"性别": {"op": "random"}},
            nsfw=use_nsfw,
            base_seed=base_seed,
            seed_i=seed_i,
            random_n=random_n,
            era=era_arg,
        )
        gender_text = ""
        if g_ids:
            terms = builder_service.get_terms_by_ids(slot_id, g_ids[:1], nsfw=use_nsfw)
            if terms:
                gender_text = (terms[0].get("text_zh") or "").strip()
        # 年龄：多抽再滤
        pool = builder_service.random_ids(
            slot_id,
            n=min(24, max(8, random_n * 8)),
            nsfw=use_nsfw,
            seed=(base_seed + seed_i * 10007 + 3) & 0xFFFFFFFF,
            group="年龄段",
            era=era_arg,
        )
        age_ids: List[str] = []
        if pool:
            terms = builder_service.get_terms_by_ids(slot_id, pool, nsfw=use_nsfw)
            for term in terms:
                tid = str(term.get("id") or "")
                tx = (term.get("text_zh") or "").strip()
                if tid and _age_compatible(gender_text, tx):
                    age_ids.append(tid)
                if len(age_ids) >= random_n:
                    break
        if not age_ids and pool:
            age_ids = pool[:random_n]
        out = []
        seen: Set[str] = set()
        for i in list(g_ids) + list(age_ids):
            if i and i not in seen:
                seen.add(i)
                out.append(i)
        # 其余默认组（若有）
        rest = [g for g in groups if g not in ("性别", "年龄段")]
        if rest:
            cfg = {g: {"op": "random"} for g in rest}
            for i in _resolve_group_ops(
                slot_id, cfg, nsfw=use_nsfw, base_seed=base_seed, seed_i=seed_i + 1,
                random_n=random_n, era=era_arg,
            ):
                if i not in seen:
                    seen.add(i)
                    out.append(i)
        return out

    cfg = {g: {"op": "random"} for g in groups}
    return _resolve_group_ops(
        slot_id,
        cfg,
        nsfw=nsfw,
        base_seed=base_seed,
        seed_i=seed_i,
        random_n=random_n,
        era=era,
    )


class PromptKitStructuredBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        sep_default = settings.get("separator", ", ") or ", "
        required: Dict[str, Any] = {
            "选词方式": (
                ["节点组词", "面板优先"],
                {
                    "default": "节点组词",
                    "tooltip": "节点组词：按各槽模式组词；面板优先：只用面板文本",
                },
            ),
            "时代锁定": (
                _era_choices(),
                {
                    "default": ERA_OFF,
                    "tooltip": "关闭=不过滤；开启后随机仅从对应时代或「通用」标签中抽；指定词不清除",
                },
            ),
            "分隔符": ("STRING", {"default": sep_default, "multiline": False, "tooltip": "词条分隔符"}),
            "去重": ("BOOLEAN", {"default": True, "tooltip": "跨槽去重"}),
            "启用权重": ("BOOLEAN", {"default": False, "tooltip": "输出权重语法"}),
            "含NSFW": (
                "BOOLEAN",
                {
                    "default": False,
                    "tooltip": "开启后显示 NSFW 槽行并参与组词（着装服饰等）",
                },
            ),
            "随机种子": (
                "INT",
                {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFF,
                    "control_after_generate": True,
                    "tooltip": "0=每次变化；整槽随机与自定义内组随机共用",
                },
            ),
            "每组随机条数": (
                "INT",
                {"default": 1, "min": 1, "max": 5, "tooltip": "每个随机组抽取条数"},
            ),
        }
        optional: Dict[str, Any] = {
            "前缀": ("STRING", {"default": "", "multiline": False, "tooltip": "整段前缀"}),
            "后缀": ("STRING", {"default": "", "multiline": False, "tooltip": "整段后缀"}),
            "面板文本": (
                "STRING",
                {"default": "", "multiline": True, "tooltip": "面板写入；选词方式=面板优先时输出"},
            ),
            "组词状态": (
                "STRING",
                {
                    "default": "{}",
                    "multiline": True,
                    "tooltip": "自定义模式的组状态 JSON。B1 可手改测试；B3 由小浮窗写入。"
                    '示例：{"subject":{"groups":{"性别":{"op":"pick","text":"年轻女性"},"气质":{"op":"random"}}}}',
                },
            ),
        }
        for sid in SFW_SLOTS + EXTRA_SLOTS:
            label = SLOT_LABELS[sid]
            default_mode = SLOT_MODE_DEFAULTS.get(sid, MODE_NONE)
            tip = f"{label}：不选 / 整槽随机 / 自定义（自定义读组词状态 JSON）"
            if sid.startswith("nsfw_"):
                tip += "；需开启含NSFW"
            optional[_mode_widget_name(sid)] = (
                SLOT_MODES,
                {"default": default_mode, "tooltip": tip},
            )
        return {"required": required, "optional": optional}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("文本", "预览", "槽计数JSON")
    FUNCTION = "run"
    CATEGORY = "PromptKit/结构化"
    SEARCH_ALIASES = ["pk", "promptkit", "结构化", "组词", "时代锁定"]
    DESCRIPTION = (
        "方案B：每槽不选/整槽随机/自定义。自定义组状态见「组词状态」JSON；"
        "切换槽模式到「自定义」或点「编辑槽组（浮窗）」可按组编辑。含NSFW 展开附加槽行。"
    )

    def run(self, **kwargs):
        pick_mode = kwargs.get("选词方式") or kwargs.get("pick_mode") or "节点组词"
        era = str(kwargs.get("时代锁定") or kwargs.get("era_lock") or ERA_OFF).strip()
        separator = kwargs.get("分隔符") if "分隔符" in kwargs else kwargs.get("separator", ", ")
        dedupe = bool(kwargs.get("去重") if "去重" in kwargs else kwargs.get("dedupe", True))
        enable_weight = bool(
            kwargs.get("启用权重") if "启用权重" in kwargs else kwargs.get("enable_weight", False)
        )
        include_nsfw = bool(kwargs.get("含NSFW") if "含NSFW" in kwargs else kwargs.get("include_nsfw", False))
        seed = int(kwargs.get("随机种子") if "随机种子" in kwargs else kwargs.get("seed", 0))
        random_n = int(
            kwargs.get("每组随机条数")
            if "每组随机条数" in kwargs
            else kwargs.get("每槽随机条数")
            if "每槽随机条数" in kwargs
            else kwargs.get("random_per_slot", 1)
        )
        prefix = kwargs.get("前缀") if "前缀" in kwargs else kwargs.get("prefix", "")
        suffix = kwargs.get("后缀") if "后缀" in kwargs else kwargs.get("suffix", "")
        panel_text = kwargs.get("面板文本") if "面板文本" in kwargs else kwargs.get("panel_text", "")
        states = _parse_states(kwargs.get("组词状态") if "组词状态" in kwargs else kwargs.get("slot_states", "{}"))

        nsfw = bool(include_nsfw)
        mode = (pick_mode or "节点组词").strip()

        if mode == "面板优先":
            panel = (panel_text or "").strip()
            return (panel, panel, "{}")

        base = _effective_seed(seed)
        selected: Dict[str, List[str]] = {}
        slots = list(SFW_SLOTS) + (list(EXTRA_SLOTS) if nsfw else [])
        era_arg = "" if not era or era == ERA_OFF else era

        for si, sid in enumerate(slots):
            if sid.startswith("nsfw_") and not nsfw:
                continue
            wname = _mode_widget_name(sid)
            slot_mode = kwargs.get(wname)
            if slot_mode is None:
                slot_mode = SLOT_MODE_DEFAULTS.get(sid, MODE_NONE)
            slot_mode = str(slot_mode).strip()

            if slot_mode == MODE_NONE or slot_mode == NONE:
                continue

            use_nsfw = nsfw or sid.startswith("nsfw_")
            if slot_mode == MODE_SLOT_RANDOM:
                ids = _slot_random_ids(
                    sid,
                    nsfw=use_nsfw,
                    base_seed=base,
                    seed_i=si,
                    random_n=random_n,
                    era=era_arg,
                )
                if ids:
                    selected[sid] = ids
                continue

            if slot_mode in (MODE_CUSTOM, MODE_EDIT):
                st = states.get(sid) or {}
                groups_cfg = st.get("groups") if isinstance(st, dict) else {}
                if not groups_cfg and isinstance(st, dict) and st.get("mode") == "custom":
                    groups_cfg = st.get("groups") or {}
                # 兼容直接 {groups:{...}} 或 {性别:{op:...}}
                if not groups_cfg and isinstance(st, dict):
                    maybe = {k: v for k, v in st.items() if isinstance(v, dict) and "op" in v}
                    if maybe:
                        groups_cfg = maybe
                ids = _resolve_group_ops(
                    sid,
                    groups_cfg or {},
                    nsfw=use_nsfw,
                    base_seed=base,
                    seed_i=si,
                    random_n=random_n,
                    era=era_arg,
                )
                if ids:
                    selected[sid] = ids
                continue

            # 未知模式当不选
            continue

        result = builder_service.compose(
            selected,
            nsfw=nsfw,
            separator=separator if separator is not None else ", ",
            dedupe=bool(dedupe),
            enable_weight=bool(enable_weight),
            prefix=prefix or "",
            suffix=suffix or "",
            enabled=None,
        )
        return (
            result.get("text") or "",
            result.get("preview") or "",
            _counts_json(result.get("counts") or {}),
        )


NODE_CLASS_MAPPINGS = {"PromptKitStructuredBuilder": PromptKitStructuredBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptKitStructuredBuilder": "PromptKit · 结构化生成"}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
