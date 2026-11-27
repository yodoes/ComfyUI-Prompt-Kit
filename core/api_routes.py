"""
ComfyUI HTTP 路由：字典树 / 搜索 / 分页 / 收藏。

仅在 ComfyUI 环境（存在 PromptServer）时注册；本地脚本导入会跳过。
前缀：/prompt-kit/
"""
from __future__ import annotations

from typing import Any, Dict, List

try:
    from aiohttp import web
    from server import PromptServer

    from .dictionary_service import dictionary_service
    from .library_service import library_service
    from .builder_service import builder_service

    BASE = "/prompt-kit"

    def _json_ok(**kwargs: Any) -> web.Response:
        return web.json_response({"ok": True, **kwargs})

    def _json_err(msg: str, status: int = 400) -> web.Response:
        return web.json_response({"ok": False, "error": msg}, status=status)

    @PromptServer.instance.routes.get(f"{BASE}/tree")
    async def pk_tree(request: web.Request) -> web.Response:
        include_misc = request.query.get("include_misc", "0") in ("1", "true", "True")
        include_nsfw = request.query.get("include_nsfw", "0") in ("1", "true", "True")
        language = request.query.get("lang", "zh")
        tree = dictionary_service.get_category_tree(
            include_misc=include_misc,
            include_nsfw=include_nsfw,
            language=language,
        )
        return _json_ok(tree=tree)

    @PromptServer.instance.routes.get(f"{BASE}/entries")
    async def pk_entries(request: web.Request) -> web.Response:
        sid = (request.query.get("subcategory") or "").strip()
        if not sid:
            return _json_err("缺少 subcategory")
        try:
            offset = max(0, int(request.query.get("offset") or 0))
            limit = min(200, max(1, int(request.query.get("limit") or 50)))
        except ValueError:
            return _json_err("offset/limit 无效")
        language = request.query.get("lang", "zh")
        entries = dictionary_service.load_subcategory(sid)
        total = len(entries)
        page = entries[offset : offset + limit]
        rows = [
            {
                "id": e.get("id"),
                "text": e.get("text") or "",
                "text_zh": e.get("text_zh") or "",
                "display": dictionary_service.display_text(e, language),
                "tags": e.get("tags") or [],
                "subcategory": e.get("subcategory"),
                "source": e.get("source"),
            }
            for e in page
        ]
        return _json_ok(entries=rows, total=total, offset=offset, limit=limit)

    @PromptServer.instance.routes.get(f"{BASE}/search")
    async def pk_search(request: web.Request) -> web.Response:
        q = (request.query.get("q") or "").strip()
        category = (request.query.get("category") or "").strip()
        sub_filter = (request.query.get("subcategory") or "").strip()
        include_misc = request.query.get("include_misc", "0") in ("1", "true", "True")
        include_nsfw = request.query.get("include_nsfw", "0") in ("1", "true", "True")
        language = request.query.get("lang", "zh")
        try:
            limit = min(200, max(1, int(request.query.get("limit") or 50)))
        except ValueError:
            limit = 50

        sub_ids = None
        if category or sub_filter:
            tree = dictionary_service.get_category_tree(
                include_misc=include_misc, include_nsfw=include_nsfw
            )
            sub_ids = []
            kw = sub_filter.lower()
            for c in tree:
                if category and c["id"] != category:
                    continue
                for ch in c.get("children", []):
                    if kw:
                        name = (ch.get("name") or "").lower()
                        sid = (ch.get("id") or "").lower()
                        if kw not in name and kw not in sid:
                            continue
                    sub_ids.append(ch["id"])
            if not sub_ids:
                return _json_ok(entries=[], total=0)

        if not q and not sub_ids:
            return _json_ok(entries=[], total=0, hint="请输入关键词或选择分类")

        if q:
            hits = dictionary_service.search(
                q,
                subcategory_ids=sub_ids,
                include_misc=include_misc,
                include_nsfw=include_nsfw,
                language="both",
                limit=limit,
            )
        else:
            hits = []
            for sid in sub_ids or []:
                for e in dictionary_service.load_subcategory(sid):
                    hits.append(e)
                    if len(hits) >= limit:
                        break
                if len(hits) >= limit:
                    break

        rows = [
            {
                "id": e.get("id"),
                "text": e.get("text") or "",
                "text_zh": e.get("text_zh") or "",
                "display": dictionary_service.display_text(e, language),
                "tags": e.get("tags") or [],
                "subcategory": e.get("subcategory"),
                "source": e.get("source"),
            }
            for e in hits
        ]
        return _json_ok(entries=rows, total=len(rows))

    @PromptServer.instance.routes.get(f"{BASE}/favorites")
    async def pk_fav_list(request: web.Request) -> web.Response:
        language = request.query.get("lang", "zh")
        ids = dictionary_service.list_favorites()
        rows = []
        for eid in ids:
            e = dictionary_service.get_entry_by_id(eid, include_misc=True)
            if not e:
                continue
            rows.append(
                {
                    "id": e.get("id"),
                    "display": dictionary_service.display_text(e, language),
                    "text": e.get("text") or "",
                    "text_zh": e.get("text_zh") or "",
                    "subcategory": e.get("subcategory"),
                }
            )
        return _json_ok(entries=rows, total=len(rows))

    @PromptServer.instance.routes.post(f"{BASE}/favorites")
    async def pk_fav_mutate(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        action = (data.get("action") or "add").strip()
        entry_id = (data.get("id") or "").strip()
        if not entry_id:
            return _json_err("缺少 id")
        if action == "remove":
            dictionary_service.remove_favorite(entry_id)
            return _json_ok(favorited=False, id=entry_id)
        if action == "toggle":
            now = dictionary_service.toggle_favorite(entry_id)
            return _json_ok(favorited=now, id=entry_id)
        dictionary_service.add_favorite(entry_id)
        return _json_ok(favorited=True, id=entry_id)

    @PromptServer.instance.routes.post(f"{BASE}/entry")
    async def pk_add_entry(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        sid = (data.get("subcategory") or "").strip()
        text = (data.get("text") or "").strip()
        text_zh = (data.get("text_zh") or "").strip()
        tags = data.get("tags") or []
        if not sid:
            return _json_err("缺少 subcategory")
        if not text and not text_zh:
            return _json_err("text / text_zh 至少填一个")
        entry = dictionary_service.add_user_entry(
            sid,
            text=text or text_zh,
            text_zh=text_zh,
            tags=tags if isinstance(tags, list) else [],
        )
        return _json_ok(entry=entry)


    # ------------------------------------------------------------------
    # 词库 / 预设 API
    # ------------------------------------------------------------------

    @PromptServer.instance.routes.get(f"{BASE}/library/list")
    async def pk_lib_list(request: web.Request) -> web.Response:
        include_nsfw = request.query.get("include_nsfw", "0") in ("1", "true", "True")
        libs = library_service.list_libraries(include_nsfw=include_nsfw)
        # 不把绝对 path 暴露给前端也可；保留 id/file/name 即可
        rows = [
            {
                "id": m.get("id"),
                "name_zh": m.get("name_zh"),
                "name_en": m.get("name_en"),
                "description": m.get("description") or "",
                "preset_count": m.get("preset_count") or 0,
                "nsfw": bool(m.get("nsfw")),
                "readonly": bool(m.get("readonly")),
                "group": m.get("group") or "user",
                "system": bool(m.get("system")),
            }
            for m in libs
        ]
        return _json_ok(libraries=rows)

    @PromptServer.instance.routes.get(f"{BASE}/library/get")
    async def pk_lib_get(request: web.Request) -> web.Response:
        lid = (request.query.get("id") or "").strip()
        if not lid:
            return _json_err("缺少 id")
        language = request.query.get("lang", "zh")
        lib = library_service.load_library(lid)
        if not lib:
            return _json_err("词库不存在", 404)
        # 默认不返回全部 presets（可能 5000 条）；仅元数据 + categories
        return _json_ok(
            library={
                "id": lib.get("id"),
                "name_zh": lib.get("name_zh"),
                "name_en": lib.get("name_en"),
                "description": lib.get("description") or "",
                "categories": lib.get("categories") or [],
                "preset_count": len(lib.get("presets") or []),
                "readonly": bool(lib.get("_readonly")),
                "nsfw": bool(lib.get("_nsfw")),
            },
            tags=library_service.collect_tags(lid),
            categories=library_service.collect_categories(lid),
        )

    @PromptServer.instance.routes.get(f"{BASE}/library/search")
    async def pk_lib_search(request: web.Request) -> web.Response:
        lid = (request.query.get("id") or request.query.get("library_id") or "").strip()
        if not lid:
            return _json_err("缺少词库 id")
        q = (request.query.get("q") or "").strip()
        category_id = (request.query.get("category_id") or "").strip()
        tags_raw = (request.query.get("tags") or "").strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        tag_mode = (request.query.get("tag_mode") or "and").strip().lower()
        favorites_only = request.query.get("favorites", "0") in ("1", "true", "True")
        include_nsfw = request.query.get("include_nsfw", "1") in ("1", "true", "True")
        language = request.query.get("lang", "zh")
        try:
            offset = max(0, int(request.query.get("offset") or 0))
            limit = min(200, max(1, int(request.query.get("limit") or 50)))
        except ValueError:
            return _json_err("offset/limit 无效")
        result = library_service.search_presets(
            lid,
            query=q,
            category_id=category_id,
            tags=tags,
            tag_mode=tag_mode,
            favorites_only=favorites_only,
            include_nsfw_presets=include_nsfw,
            language=language,
            offset=offset,
            limit=limit,
        )
        return _json_ok(**result)

    @PromptServer.instance.routes.get(f"{BASE}/library/favorites")
    async def pk_lib_fav_list(request: web.Request) -> web.Response:
        language = request.query.get("lang", "zh")
        rows = library_service.list_favorites_entries(language=language)
        return _json_ok(presets=rows, total=len(rows))

    @PromptServer.instance.routes.post(f"{BASE}/library/favorite")
    async def pk_lib_fav_mutate(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        lid = (data.get("library_id") or "").strip()
        pid = (data.get("preset_id") or data.get("id") or "").strip()
        if not lid or not pid:
            return _json_err("缺少 library_id / preset_id")
        now = library_service.toggle_favorite(lid, pid)
        return _json_ok(favorited=now, library_id=lid, preset_id=pid)

    @PromptServer.instance.routes.post(f"{BASE}/library/create")
    async def pk_lib_create(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        try:
            meta = library_service.create_library(
                data.get("name_zh") or data.get("name") or "",
                library_id=data.get("id") or "",
                name_en=data.get("name_en") or "",
                description=data.get("description") or "",
            )
            return _json_ok(library=meta)
        except Exception as e:
            return _json_err(str(e))

    @PromptServer.instance.routes.post(f"{BASE}/library/delete")
    async def pk_lib_delete(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        lid = (data.get("id") or data.get("library_id") or "").strip()
        if not lid:
            return _json_err("缺少 id")
        try:
            library_service.delete_library(lid)
            return _json_ok(deleted=lid)
        except Exception as e:
            return _json_err(str(e))

    @PromptServer.instance.routes.post(f"{BASE}/library/preset")
    async def pk_lib_preset(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        action = (data.get("action") or "add").strip().lower()
        lid = (data.get("library_id") or "").strip()
        if not lid:
            return _json_err("缺少 library_id")
        try:
            if action == "add":
                preset = library_service.add_preset(
                    lid,
                    title_zh=data.get("title_zh") or data.get("title") or "",
                    title_en=data.get("title_en") or "",
                    prompt=data.get("prompt") or "",
                    prompt_en=data.get("prompt_en") or "",
                    category_id=data.get("category_id") or "",
                    tags=data.get("tags") or [],
                    nsfw=bool(data.get("nsfw")),
                    note=data.get("note") or "",
                )
                return _json_ok(preset=preset)
            if action == "update":
                pid = (data.get("preset_id") or data.get("id") or "").strip()
                if not pid:
                    return _json_err("缺少 preset_id")
                fields = {
                    k: data[k]
                    for k in (
                        "title_zh",
                        "title_en",
                        "prompt",
                        "prompt_en",
                        "category_id",
                        "tags",
                        "nsfw",
                        "note",
                    )
                    if k in data
                }
                preset = library_service.update_preset(lid, pid, fields)
                return _json_ok(preset=preset)
            if action == "delete":
                pid = (data.get("preset_id") or data.get("id") or "").strip()
                if not pid:
                    return _json_err("缺少 preset_id")
                library_service.delete_preset(lid, pid)
                return _json_ok(deleted=pid)
            return _json_err(f"未知 action: {action}")
        except Exception as e:
            return _json_err(str(e))

    @PromptServer.instance.routes.post(f"{BASE}/library/tags")
    async def pk_lib_tags(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        lid = (data.get("library_id") or "").strip()
        pid = (data.get("preset_id") or "").strip()
        if not lid or not pid:
            return _json_err("缺少 library_id / preset_id")
        action = (data.get("action") or "set").strip().lower()
        tags = data.get("tags") or []
        try:
            new_tags = library_service.set_preset_tags(lid, pid, tags, action=action)
            return _json_ok(tags=new_tags)
        except Exception as e:
            return _json_err(str(e))

    @PromptServer.instance.routes.post(f"{BASE}/library/reload")
    async def pk_lib_reload(request: web.Request) -> web.Response:
        library_service.reload()
        n = len(library_service.list_libraries(include_nsfw=True))
        return _json_ok(count=n)


    @PromptServer.instance.routes.post(f"{BASE}/entry/delete")
    async def pk_delete_entry(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        entry_id = (data.get("id") or "").strip()
        if not entry_id:
            return _json_err("缺少 id")
        ok = dictionary_service.delete_entry(
            entry_id,
            subcategory_id=(data.get("subcategory") or "").strip(),
        )
        if not ok:
            return _json_err("删除失败或词条不存在", 404)
        return _json_ok(deleted=entry_id)

    @PromptServer.instance.routes.post(f"{BASE}/entry/update")
    async def pk_update_entry(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        entry_id = (data.get("id") or "").strip()
        if not entry_id:
            return _json_err("缺少 id")
        updates = {}
        for k in ("text", "text_zh", "tags", "nsfw", "note"):
            if k in data:
                updates[k] = data[k]
        if not updates:
            return _json_err("无更新字段")
        entry = dictionary_service.update_entry(
            entry_id,
            updates,
            subcategory_id=(data.get("subcategory") or "").strip(),
        )
        if not entry:
            return _json_err("词条不存在或更新失败", 404)
        return _json_ok(entry=entry)

    # ------------------------------------------------------------------
    # 结构化生成 builder
    # ------------------------------------------------------------------

    def _query_bool(request: web.Request, key: str, default: bool = False) -> bool:
        v = request.query.get(key)
        if v is None:
            return default
        return str(v).lower() in ("1", "true", "yes", "on")

    @PromptServer.instance.routes.get(f"{BASE}/builder/slots")
    async def pk_builder_slots(request: web.Request) -> web.Response:
        nsfw = _query_bool(request, "nsfw", False)
        slots = builder_service.list_slots(nsfw=nsfw)
        order = builder_service.compose_order(nsfw=nsfw)
        return _json_ok(slots=slots, compose_order=order, nsfw=nsfw)

    @PromptServer.instance.routes.get(f"{BASE}/builder/slot/{{slot_id}}")
    async def pk_builder_slot(request: web.Request) -> web.Response:
        slot_id = (request.match_info.get("slot_id") or "").strip()
        if not slot_id:
            return _json_err("缺少 slot_id")
        nsfw = _query_bool(request, "nsfw", False)
        q = (request.query.get("q") or "").strip()
        group = (request.query.get("group") or "").strip()
        try:
            limit = int(request.query.get("limit") or 500)
        except ValueError:
            limit = 500
        terms = builder_service.search_slot(
            slot_id, q=q, group=group, nsfw=nsfw, limit=max(1, min(limit, 2000))
        )
        return _json_ok(slot_id=slot_id, terms=terms, count=len(terms), nsfw=nsfw)

    @PromptServer.instance.routes.post(f"{BASE}/builder/compose")
    async def pk_builder_compose(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        selected = data.get("selected") or {}
        if not isinstance(selected, dict):
            return _json_err("selected 须为对象")
        # 规范为 str -> list[str]
        norm: Dict[str, List[str]] = {}
        for k, v in selected.items():
            if v is None:
                continue
            if isinstance(v, list):
                norm[str(k)] = [str(x) for x in v if x is not None and str(x).strip()]
            else:
                norm[str(k)] = [str(v)]
        enabled = data.get("enabled")
        if enabled is not None and not isinstance(enabled, dict):
            return _json_err("enabled 须为对象")
        nsfw = bool(data.get("nsfw", False))
        separator = data.get("separator")
        if separator is not None:
            separator = str(separator)
        dedupe = bool(data.get("dedupe", True))
        enable_weight = bool(data.get("enable_weight", False))
        prefix = str(data.get("prefix") or "")
        suffix = str(data.get("suffix") or "")
        try:
            result = builder_service.compose(
                norm,
                nsfw=nsfw,
                separator=separator,
                dedupe=dedupe,
                enable_weight=enable_weight,
                prefix=prefix,
                suffix=suffix,
                enabled=enabled,
            )
            return _json_ok(**result)
        except Exception as e:
            return _json_err(str(e))

    
    @PromptServer.instance.routes.get(f"{BASE}/builder/presets")
    async def pk_builder_presets(_request: web.Request) -> web.Response:
        """官方组词预设列表。"""
        items = [
            {"id": "portrait_general", "name_zh": "通用人像", "era": "关闭"},
            {"id": "guofeng", "name_zh": "国风中式", "era": "古风中式"},
            {"id": "xianxia", "name_zh": "仙侠", "era": "仙侠玄幻"},
        ]
        return _json_ok(presets=items)

    @PromptServer.instance.routes.post(f"{BASE}/builder/preset/apply")
    async def pk_builder_preset_apply(request: web.Request) -> web.Response:
        """按预设抽取词条 id，供面板填充已选。"""
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        pid = str(data.get("id") or data.get("preset") or "").strip()
        seed = int(data.get("seed") or 0)
        if seed == 0:
            import time as _time
            seed = int(_time.time_ns() % (2**31))

        # 预设定义：slot -> [(group, n)]
        table = {
            "portrait_general": {
                "era": "关闭",
                "picks": [
                    ("subject", "性别", 1),
                    ("subject", "年龄段", 1),
                    ("subject", "气质", 1),
                    ("expression", "表情", 1),
                    ("pose", "站姿", 1),
                    ("clothing", "套装", 1),
                    ("scene", "地点", 1),
                    ("lighting", "氛围", 1),
                ],
            },
            "guofeng": {
                "era": "古风中式",
                "picks": [
                    ("style", "时代世界观", 1),
                    ("style", "文化地域", 1),
                    ("subject", "性别", 1),
                    ("subject", "年龄段", 1),
                    ("subject", "职业身份", 1),
                    ("hair", "盘发冠髻", 1),
                    ("clothing", "服饰形制", 1),
                    ("accessories", "头饰", 1),
                    ("pose", "站姿", 1),
                    ("scene", "地点", 1),
                    ("lighting", "氛围", 1),
                ],
            },
            "xianxia": {
                "era": "仙侠玄幻",
                "picks": [
                    ("style", "时代世界观", 1),
                    ("subject", "性别", 1),
                    ("subject", "气质", 1),
                    ("subject", "职业身份", 1),
                    ("hair", "发质动态", 1),
                    ("clothing", "服饰形制", 1),
                    ("accessories", "手持", 1),
                    ("pose", "站姿", 1),
                    ("scene", "地点", 1),
                    ("lighting", "主光", 1),
                ],
            },
        }
        conf = table.get(pid)
        if not conf:
            return _json_err(f"未知预设: {pid}")
        era = conf["era"]
        selected: Dict[str, List[str]] = {}
        terms_out: Dict[str, List[Dict[str, Any]]] = {}
        for i, (sid, group, n) in enumerate(conf["picks"]):
            ids = builder_service.random_ids(
                sid,
                n=n,
                nsfw=False,
                seed=(seed + i * 97) & 0xFFFFFFFF,
                group=group,
                era="" if era in ("关闭", "") else era,
            )
            if not ids:
                # 无时代命中则放宽
                ids = builder_service.random_ids(
                    sid, n=n, nsfw=False, seed=(seed + i * 97 + 3) & 0xFFFFFFFF, group=group, era=""
                )
            if not ids:
                continue
            selected.setdefault(sid, []).extend(ids)
            for term in builder_service.get_terms_by_ids(sid, ids, nsfw=False):
                terms_out.setdefault(sid, []).append(term)
        return _json_ok(id=pid, era=era, selected=selected, terms=terms_out)

    
    @PromptServer.instance.routes.post(f"{BASE}/builder/reload")
    async def pk_builder_reload(request: web.Request) -> web.Response:
        builder_service.reload()
        n = len(builder_service.list_slots(nsfw=True))
        # 各组词量摘要（便于前端提示）
        counts = {}
        for s in builder_service.list_slots(nsfw=True):
            sid = s["id"]
            rows = builder_service.load_slot(sid, nsfw=bool(s.get("nsfw")))
            counts[sid] = len(rows)
        return _json_ok(slots=n, term_counts=counts, message="词表缓存已刷新；节点下拉需重建节点或重启后更新")

    @PromptServer.instance.routes.get(f"{BASE}/builder/validate")
    async def pk_builder_validate(_request: web.Request) -> web.Response:
        try:
            report = builder_service.validate_catalog()
            return _json_ok(**report)
        except Exception as e:
            return _json_err(str(e))

    @PromptServer.instance.routes.post(f"{BASE}/builder/term")
    async def pk_builder_term(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception as e:
            return _json_err(f"JSON 无效: {e}")
        action = (data.get("action") or "upsert").strip().lower()
        slot_id = (data.get("slot") or data.get("slot_id") or "").strip()
        if not slot_id:
            return _json_err("缺少 slot")
        try:
            if action in ("upsert", "add", "update"):
                entry = builder_service.upsert_term(
                    slot_id,
                    text_zh=str(data.get("text_zh") or data.get("text") or ""),
                    term_id=str(data.get("id") or data.get("term_id") or ""),
                    group=str(data.get("group") or ""),
                    nsfw=bool(data.get("nsfw")),
                    tags=data.get("tags"),
                )
                return _json_ok(term=entry)
            if action == "delete":
                tid = str(data.get("id") or data.get("term_id") or "").strip()
                if not tid:
                    return _json_err("缺少 id")
                ok = builder_service.delete_term(slot_id, tid)
                if not ok:
                    return _json_err("未找到词条或删除失败", 404)
                return _json_ok(deleted=tid, slot=slot_id)
            return _json_err(f"未知 action: {action}")
        except Exception as e:
            return _json_err(str(e))

    print("[Prompt-Kit] API routes registered: /prompt-kit/* (+ library + builder)")

except ImportError:
    # 非 ComfyUI 环境
    pass
