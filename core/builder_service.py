"""
结构化生成服务（阶段 4）。

约定：
- SFW：data/builder/{slot}.jsonl + user_data/builder/ 覆盖（同 id 覆盖）
- NSFW B：打开 nsfw 时合并 data/builder_nsfw/{同名槽}.jsonl
- NSFW C：额外槽 nsfw_* 仅存在于 builder_nsfw
- 不读取字典；dictionary_sources 预留
- compose 只输出中文 text_zh
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

import uuid

from .io_utils import read_json, read_jsonl, write_jsonl
from .paths import paths

DEFAULT_SEPARATOR = ", "
SFW_FALLBACK_ORDER = [
    "style",
    "camera",
    "subject",
    "face",
    "hair",
    "expression",
    "pose",
    "clothing",
    "accessories",
    "scene",
    "lighting",
]
EXTRA_FALLBACK_ORDER = [
    "nsfw_clothing",
    "nsfw_body",
    "nsfw_pose",
    "nsfw_act",
    "nsfw_props",
    "nsfw_fluids",
]


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        s = (x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _term_text(term: Dict[str, Any], enable_weight: bool = False) -> str:
    text = (term.get("text_zh") or "").strip()
    if not text:
        return ""
    if enable_weight and term.get("weight") is not None:
        try:
            w = float(term["weight"])
            if abs(w - 1.0) > 1e-6:
                return f"({text}:{w:g})"
        except (TypeError, ValueError):
            pass
    return text


class BuilderService:
    def __init__(self) -> None:
        self._sfw_index: Optional[Dict[str, Any]] = None
        self._nsfw_index: Optional[Dict[str, Any]] = None
        self._slot_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # index
    # ------------------------------------------------------------------

    def load_sfw_index(self, force: bool = False) -> Dict[str, Any]:
        if self._sfw_index is not None and not force:
            return self._sfw_index
        data = read_json(paths.builder_index, default={})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("version", 1)
        data.setdefault("slots", [])
        data.setdefault("compose_order", list(SFW_FALLBACK_ORDER))
        self._sfw_index = data
        self._loaded_at = time.time()
        return self._sfw_index

    def load_nsfw_index(self, force: bool = False) -> Dict[str, Any]:
        if self._nsfw_index is not None and not force:
            return self._nsfw_index
        data = read_json(paths.builder_nsfw_index, default={})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("version", 1)
        data.setdefault("overlays", [])
        data.setdefault("extras", [])
        data.setdefault("compose_insert_after", "accessories")
        data.setdefault("compose_extra_order", list(EXTRA_FALLBACK_ORDER))
        self._nsfw_index = data
        return self._nsfw_index

    def reload(self) -> None:
        self._sfw_index = None
        self._nsfw_index = None
        self._slot_cache.clear()
        self.load_sfw_index(force=True)
        self.load_nsfw_index(force=True)

    def _overlay_slots(self) -> Set[str]:
        idx = self.load_nsfw_index()
        return {str(o.get("slot") or "") for o in idx.get("overlays", []) if o.get("slot")}

    def _extra_meta(self) -> Dict[str, Dict[str, Any]]:
        idx = self.load_nsfw_index()
        out: Dict[str, Dict[str, Any]] = {}
        for ex in idx.get("extras", []):
            eid = ex.get("id")
            if eid:
                out[str(eid)] = ex
        return out

    def is_extra_slot(self, slot_id: str) -> bool:
        return slot_id in self._extra_meta()

    def validate_catalog(self) -> Dict[str, Any]:
        """校验分组覆盖、空组、标签覆盖率（维护用）。"""
        self.reload()
        issues: List[Dict[str, Any]] = []
        summary: List[Dict[str, Any]] = []
        slots = self.list_slots(nsfw=True)
        for s in slots:
            sid = s["id"]
            nsfw = bool(s.get("nsfw"))
            declared = [str(g).strip() for g in (s.get("groups") or []) if str(g).strip()]
            rows = self.load_slot(sid, nsfw=True if nsfw else False)
            # SFW 槽在 nsfw=False 下统计主库；额外扫 nsfw 仅报告
            if not nsfw:
                rows = self.load_slot(sid, nsfw=False)
            by_g: Dict[str, int] = {}
            tagged = 0
            for r in rows:
                g = (r.get("group") or "").strip() or "(空)"
                by_g[g] = by_g.get(g, 0) + 1
                if r.get("tags"):
                    tagged += 1
            for g in declared:
                c = by_g.get(g, 0)
                if c == 0:
                    issues.append({"level": "error", "slot": sid, "group": g, "msg": "声明组无词条"})
                elif c < 10:
                    issues.append({"level": "warn", "slot": sid, "group": g, "msg": f"词条偏少({c})"})
            empty_group = by_g.get("(空)", 0)
            if empty_group:
                issues.append({"level": "warn", "slot": sid, "group": "(空)", "msg": f"无分组词条 {empty_group}"})
            total = len(rows)
            summary.append({
                "id": sid,
                "name_zh": s.get("name_zh"),
                "nsfw": nsfw,
                "total": total,
                "groups": {g: by_g.get(g, 0) for g in declared},
                "tag_ratio": round(tagged / total, 3) if total else 0,
            })
        return {
            "slots": summary,
            "issues": issues,
            "issue_count": len(issues),
            "error_count": sum(1 for x in issues if x.get("level") == "error"),
            "warn_count": sum(1 for x in issues if x.get("level") == "warn"),
        }


    # ------------------------------------------------------------------
    # slots list
    # ------------------------------------------------------------------

    def list_slots(self, nsfw: bool = False) -> List[Dict[str, Any]]:
        """返回槽位元数据列表（面板左侧）。nsfw=True 时追加 extra 槽。"""
        sfw = self.load_sfw_index()
        result: List[Dict[str, Any]] = []
        for s in sfw.get("slots", []):
            sid = s.get("id")
            if not sid:
                continue
            result.append(
                {
                    "id": sid,
                    "name_zh": s.get("name_zh") or sid,
                    "order": s.get("order", 0),
                    "selection_mode": s.get("selection_mode") or "multi",
                    "groups": list(s.get("groups") or []),
                    "nsfw": False,
                    "default_collapsed": False,
                }
            )
        if nsfw:
            base_order = len(result)
            for ex in self.load_nsfw_index().get("extras", []):
                eid = ex.get("id")
                if not eid:
                    continue
                result.append(
                    {
                        "id": eid,
                        "name_zh": ex.get("name_zh") or eid,
                        "order": base_order + int(ex.get("order") or 0),
                        "selection_mode": ex.get("selection_mode") or "multi",
                        "groups": list(ex.get("groups") or []),
                        "nsfw": True,
                        "default_collapsed": bool(ex.get("default_collapsed")),
                    }
                )
        return result

    def compose_order(self, nsfw: bool = False) -> List[str]:
        sfw = self.load_sfw_index()
        order = list(sfw.get("compose_order") or SFW_FALLBACK_ORDER)
        if not nsfw:
            return order
        nidx = self.load_nsfw_index()
        extras = list(nidx.get("compose_extra_order") or EXTRA_FALLBACK_ORDER)
        insert_after = nidx.get("compose_insert_after") or "accessories"
        if insert_after in order:
            i = order.index(insert_after) + 1
            return order[:i] + extras + order[i:]
        return order + extras

    # ------------------------------------------------------------------
    # load / search terms
    # ------------------------------------------------------------------

    def _cache_key(self, slot_id: str, nsfw: bool) -> str:
        return f"{slot_id}|{1 if nsfw else 0}"

    def _merge_rows(
        self, base: List[Dict[str, Any]], overlay: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """后写覆盖同 id；保持先 base 后 overlay 的稳定顺序（新 id 追加）。"""
        by_id: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for row in base + overlay:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            if not rid:
                continue
            rid = str(rid)
            if rid not in by_id:
                order.append(rid)
            by_id[rid] = row
        return [by_id[i] for i in order]

    def load_slot(self, slot_id: str, nsfw: bool = False) -> List[Dict[str, Any]]:
        """
        加载槽位词条。
        - 普通槽：系统 SFW + 用户 SFW；nsfw 时再合并 NSFW overlay + 用户 NSFW overlay
        - extra 槽（nsfw_*）：仅 nsfw=True 时从 builder_nsfw 加载
        """
        slot_id = (slot_id or "").strip()
        if not slot_id:
            return []

        is_extra = self.is_extra_slot(slot_id)
        if is_extra and not nsfw:
            return []

        key = self._cache_key(slot_id, nsfw)
        cached = self._slot_cache.get(key)
        if cached is not None:
            return cached[1]

        rows: List[Dict[str, Any]] = []
        if is_extra:
            rows = self._merge_rows(
                read_jsonl(paths.builder_slot_file(slot_id, nsfw=True)),
                read_jsonl(paths.user_builder_slot_file(slot_id, nsfw=True)),
            )
        else:
            rows = self._merge_rows(
                read_jsonl(paths.builder_slot_file(slot_id, nsfw=False)),
                read_jsonl(paths.user_builder_slot_file(slot_id, nsfw=False)),
            )
            if nsfw and slot_id in self._overlay_slots():
                rows = self._merge_rows(
                    rows,
                    self._merge_rows(
                        read_jsonl(paths.builder_slot_file(slot_id, nsfw=True)),
                        read_jsonl(paths.user_builder_slot_file(slot_id, nsfw=True)),
                    ),
                )

        # 规范化
        cleaned: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["id"] = str(item.get("id") or "")
            item["text_zh"] = (item.get("text_zh") or "").strip()
            item["slot"] = slot_id
            if "nsfw" not in item:
                item["nsfw"] = is_extra or slot_id.startswith("nsfw_")
            cleaned.append(item)

        self._slot_cache[key] = (time.time(), cleaned)
        return cleaned

    def search_slot(
        self,
        slot_id: str,
        q: str = "",
        group: str = "",
        nsfw: bool = False,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        rows = self.load_slot(slot_id, nsfw=nsfw)
        g = (group or "").strip()
        query = (q or "").strip().lower()
        out: List[Dict[str, Any]] = []
        for r in rows:
            if g and (r.get("group") or "") != g:
                continue
            if query:
                blob = " ".join(
                    [
                        str(r.get("text_zh") or ""),
                        str(r.get("id") or ""),
                        " ".join(r.get("tags") or []),
                        str(r.get("group") or ""),
                    ]
                ).lower()
                if query not in blob:
                    continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def get_terms_by_ids(
        self, slot_id: str, ids: List[str], nsfw: bool = False
    ) -> List[Dict[str, Any]]:
        """按 id 列表取词条，保持 ids 顺序；缺失跳过。"""
        if not ids:
            return []
        by_id = {r["id"]: r for r in self.load_slot(slot_id, nsfw=nsfw) if r.get("id")}
        out: List[Dict[str, Any]] = []
        for i in ids:
            term = by_id.get(str(i))
            if term:
                out.append(term)
        return out

    # ------------------------------------------------------------------
    # compose
    # ------------------------------------------------------------------

    def compose(
        self,
        selected: Optional[Dict[str, List[str]]] = None,
        *,
        nsfw: bool = False,
        separator: Optional[str] = None,
        dedupe: bool = True,
        enable_weight: bool = False,
        prefix: str = "",
        suffix: str = "",
        enabled: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """
        根据各槽已选 id 拼接中文 prompt。

        selected: { slot_id: [term_id, ...] }
        enabled: 槽是否参与；缺省为 True
        """
        selected = selected or {}
        sep = DEFAULT_SEPARATOR if separator is None else separator
        order = self.compose_order(nsfw=nsfw)
        enabled = enabled or {}

        parts: List[str] = []
        preview_lines: List[str] = []
        counts: Dict[str, int] = {}
        all_texts: List[str] = []

        for slot_id in order:
            if enabled.get(slot_id) is False:
                counts[slot_id] = 0
                continue
            # NSFW 关闭时跳过 extra
            if self.is_extra_slot(slot_id) and not nsfw:
                counts[slot_id] = 0
                continue
            ids = selected.get(slot_id) or []
            if not ids:
                counts[slot_id] = 0
                continue
            terms = self.get_terms_by_ids(slot_id, [str(x) for x in ids], nsfw=nsfw)
            texts = [_term_text(t, enable_weight=enable_weight) for t in terms]
            texts = [t for t in texts if t]
            if dedupe:
                texts = _dedupe_preserve(texts)
            counts[slot_id] = len(texts)
            if not texts:
                continue
            chunk = sep.join(texts)
            parts.append(chunk)
            all_texts.extend(texts)
            # 预览用槽名
            name = slot_id
            for s in self.list_slots(nsfw=nsfw):
                if s["id"] == slot_id:
                    name = s.get("name_zh") or slot_id
                    break
            preview_lines.append(f"{name}: {chunk}")

        if dedupe:
            # 跨槽全局去重：按首次出现保留，再按 order 重组较复杂；
            # 简化：对已拼 parts 拆开再去重后用 sep 连接
            flat = _dedupe_preserve(all_texts)
            text = sep.join(flat)
        else:
            text = sep.join(parts)

        # 前缀 / 正文 / 后缀之间用同一分隔符连接，避免粘成一团
        segments = []
        pre = (prefix or "").strip()
        body = (text or "").strip()
        suf = (suffix or "").strip()
        if pre:
            segments.append(pre)
        if body:
            segments.append(body)
        if suf:
            segments.append(suf)
        text = sep.join(segments)

        if pre:
            preview_lines.insert(0, f"前缀: {pre}")
        if suf:
            preview_lines.append(f"后缀: {suf}")
        preview = "\n".join(preview_lines)

        return {
            "text": text,
            "preview": preview,
            "counts": counts,
            "order": order,
        }

    # ------------------------------------------------------------------
    # term CRUD（允许改写系统精选）
    # ------------------------------------------------------------------

    def _term_file(self, slot_id: str, *, nsfw_pack: bool) -> Any:
        is_extra = self.is_extra_slot(slot_id)
        return paths.builder_slot_file(slot_id, nsfw=(nsfw_pack or is_extra))

    def find_term_file(self, slot_id: str, term_id: str) -> Optional[Any]:
        """定位词条所在系统文件（SFW 或 NSFW 包）。"""
        for nsfw_pack in (False, True):
            if self.is_extra_slot(slot_id) and not nsfw_pack:
                continue
            path = self._term_file(slot_id, nsfw_pack=nsfw_pack)
            for row in read_jsonl(path):
                if str(row.get("id")) == str(term_id):
                    return path
        return None

    def upsert_term(
        self,
        slot_id: str,
        *,
        text_zh: str,
        term_id: str = "",
        group: str = "",
        nsfw: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        slot_id = (slot_id or "").strip()
        text_zh = (text_zh or "").strip()
        if not slot_id or not text_zh:
            raise ValueError("slot_id / text_zh 不能为空")
        is_extra = self.is_extra_slot(slot_id)
        nsfw_pack = bool(nsfw) or is_extra
        path = self._term_file(slot_id, nsfw_pack=nsfw_pack)
        rows = read_jsonl(path)
        tid = (term_id or "").strip()
        if not tid:
            tid = f"{slot_id}_{uuid.uuid4().hex[:8]}"
        found = False
        for r in rows:
            if str(r.get("id")) == tid:
                r["text_zh"] = text_zh
                r["slot"] = slot_id
                if group:
                    r["group"] = group
                r["nsfw"] = bool(nsfw) or is_extra
                if tags is not None:
                    r["tags"] = tags
                found = True
                entry = r
                break
        if not found:
            # 若 id 在另一文件，先从那边删掉再写入目标包
            other = self.find_term_file(slot_id, tid)
            if other is not None and other.resolve() != path.resolve():
                other_rows = [x for x in read_jsonl(other) if str(x.get("id")) != tid]
                write_jsonl(other, other_rows)
            entry = {
                "id": tid,
                "text_zh": text_zh,
                "slot": slot_id,
                "group": group or "",
                "tags": tags if tags is not None else (["nsfw"] if nsfw_pack else []),
                "nsfw": bool(nsfw) or is_extra,
            }
            rows.append(entry)
        if not write_jsonl(path, rows):
            raise OSError(f"写入失败: {path}")
        self._slot_cache.clear()
        return dict(entry)

    def delete_term(self, slot_id: str, term_id: str) -> bool:
        slot_id = (slot_id or "").strip()
        term_id = (term_id or "").strip()
        if not slot_id or not term_id:
            return False
        path = self.find_term_file(slot_id, term_id)
        if path is None:
            return False
        rows = read_jsonl(path)
        new_rows = [r for r in rows if str(r.get("id")) != term_id]
        if len(new_rows) == len(rows):
            return False
        write_jsonl(path, new_rows)
        self._slot_cache.clear()
        return True

    def resolve_texts_to_ids(
        self, slot_id: str, texts: List[str], nsfw: bool = False
    ) -> List[str]:
        """按 text_zh 反查 id（节点下拉用）。"""
        by_text = {}
        for r in self.load_slot(slot_id, nsfw=nsfw):
            t = (r.get("text_zh") or "").strip()
            if t and t not in by_text:
                by_text[t] = str(r.get("id"))
        out = []
        for t in texts:
            t = (t or "").strip()
            if not t or t in ("(不选)", "(随机)"):
                continue
            if t in by_text:
                out.append(by_text[t])
        return out

    def random_ids(
        self,
        slot_id: str,
        n: int = 1,
        nsfw: bool = False,
        seed: int = 0,
        group: str = "",
        era: str = "",
    ) -> List[str]:
        """随机抽取 term id；group 非空时仅在该分组内抽；era 非空时按 tags 过滤（时代∪通用）。"""
        import random as _random

        rows = self.load_slot(slot_id, nsfw=nsfw)
        g = (group or "").strip()
        if g:
            rows = [r for r in rows if (r.get("group") or "").strip() == g]
        era = (era or "").strip()
        if era and era not in ("关闭", "off", "none"):
            occ_map = {
                "现代": {"职业-现代", "职业-通用"},
                "古风中式": {"职业-古风", "职业-通用"},
                "仙侠玄幻": {"职业-仙侠", "职业-通用"},
                "民国年代": {"职业-民国", "职业-通用"},
                "西幻欧式": {"职业-西幻", "职业-通用"},
                "科幻未来": {"职业-科幻", "职业-通用"},
            }
            filtered = []
            for r in rows:
                tags = [str(x) for x in (r.get("tags") or [])]
                if g == "职业身份":
                    allowed = occ_map.get(era) or {"职业-通用"}
                    occ = [x for x in tags if x.startswith("职业-")]
                    if not tags or not occ or any(x in allowed for x in occ):
                        filtered.append(r)
                else:
                    if not tags or "通用" in tags or era in tags:
                        filtered.append(r)
            rows = filtered
        if not rows:
            return []
        rng = _random.Random(int(seed) & 0xFFFFFFFF)
        n = max(1, min(int(n), len(rows)))
        picked = rng.sample(rows, n)
        return [str(r.get("id")) for r in picked if r.get("id")]


# 模块级单例
builder_service = BuilderService()
