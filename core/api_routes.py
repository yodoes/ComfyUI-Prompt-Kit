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

    BASE = "/prompt-kit"

    def _json_ok(**kwargs: Any) -> web.Response:
        return web.json_response({"ok": True, **kwargs})

    def _json_err(msg: str, status: int = 400) -> web.Response:
        return web.json_response({"ok": False, "error": msg}, status=status)

    @PromptServer.instance.routes.get(f"{BASE}/tree")
    async def pk_tree(request: web.Request) -> web.Response:
        include_misc = request.query.get("include_misc", "0") in ("1", "true", "True")
        language = request.query.get("lang", "zh")
        tree = dictionary_service.get_category_tree(
            include_misc=include_misc, language=language
        )
        # 附上每个中类的条数（轻量：只读缓存或文件行数会慢；此处不强制全量 count）
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
        language = request.query.get("lang", "zh")
        try:
            limit = min(200, max(1, int(request.query.get("limit") or 50)))
        except ValueError:
            limit = 50

        sub_ids = None
        if category or sub_filter:
            tree = dictionary_service.get_category_tree(include_misc=include_misc)
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

    print("[Prompt-Kit] API routes registered: /prompt-kit/*")

except ImportError:
    # 非 ComfyUI 环境
    pass
