"""注入到 ComfyUI PromptServer 的 HTTP 路由。

所有路径前缀：/anima_t8/*
"""
import json
import threading
from aiohttp import web

try:
    from core import prompt_manager, tag_manager
    from core.artist_manager import get_artist_manager
    from core.danbooru_manager import get_danbooru_manager
    from core.gelbooru_manager import get_gelbooru_manager
    from core.db import DEFAULT_NEGATIVE_PROMPT
    from api import civitai_client
except Exception:
    from ..core import prompt_manager, tag_manager
    from ..core.artist_manager import get_artist_manager
    from ..core.danbooru_manager import get_danbooru_manager
    from ..core.gelbooru_manager import get_gelbooru_manager
    from ..core.db import DEFAULT_NEGATIVE_PROMPT
    from ..api import civitai_client


def _ok(data=None):
    return web.json_response({"ok": True, "data": data})


def _err(msg, code=400):
    return web.json_response({"ok": False, "error": str(msg)}, status=code)


def register_routes():
    try:
        from server import PromptServer
    except Exception as e:
        print("[anima_t8] 无法导入 PromptServer，跳过路由注册:", e)
        return

    server = PromptServer.instance
    routes = server.routes

    # ---------- 提示词 ----------
    @routes.get("/anima_t8/prompts")
    async def list_prompts(request: web.Request):
        # 首次访问：确保默认标签 + 默认提示词已写入
        try:
            tag_manager.ensure_default_tags()
            prompt_manager.ensure_default_prompts()
        except Exception as e:
            print("[anima_t8] 初始化默认数据失败:", e)
        q = request.query
        items = prompt_manager.list_prompts(
            keyword=q.get("q"),
            tag_id=q.get("tag"),
            favorite_only=q.get("favorite") == "1",
            pinned_only=q.get("pinned") == "1",
        )
        return _ok(items)

    @routes.get("/anima_t8/prompts/{pid}")
    async def get_prompt(request: web.Request):
        pid = request.match_info["pid"]
        data = prompt_manager.get_prompt(pid)
        if not data:
            return _err("not found", 404)
        return _ok(data)

    @routes.post("/anima_t8/prompts")
    async def create_or_update(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        data = prompt_manager.upsert_prompt(body or {})
        return _ok(data)

    @routes.put("/anima_t8/prompts/{pid}")
    async def update_prompt(request: web.Request):
        pid = request.match_info["pid"]
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        body["id"] = pid
        data = prompt_manager.upsert_prompt(body)
        return _ok(data)

    @routes.delete("/anima_t8/prompts/{pid}")
    async def delete_prompt(request: web.Request):
        prompt_manager.delete_prompt(request.match_info["pid"])
        return _ok()

    @routes.post("/anima_t8/prompts/{pid}/favorite")
    async def fav_prompt(request: web.Request):
        data = prompt_manager.toggle_favorite(request.match_info["pid"])
        return _ok(data) if data else _err("not found", 404)

    @routes.post("/anima_t8/prompts/{pid}/pin")
    async def pin_prompt(request: web.Request):
        data = prompt_manager.toggle_pin(request.match_info["pid"])
        return _ok(data) if data else _err("not found", 404)

    @routes.post("/anima_t8/civitai/refresh")
    async def refresh_from_civitai(request: web.Request):
        """从 Civitai 拉取指定模型高赞图 meta，按 title 增量写入 prompts 表。

        body 参数：
            model_id (int, 必需)
            sort     (str, 默认 'Most Reactions')
            period   (str, 默认 'Month')
            nsfw     (str, 'None'/'Soft'/'Mature'/'X')
            limit    (int, 默认 100，最大 200)
            max_pages(int, 默认 1)
            top_n    (int, 默认 30，只取点赞最高的前 N 张写入)
            tag_names(list, 默认 ['风格']，给生成的模板打上的分类)
            title_prefix (str, 默认 'Civitai-{model_id}')
            token    (str, 选填，拉 NSFW=X 需要)
        """
        try:
            body = await request.json()
        except Exception:
            body = {}
        model_id = body.get("model_id") or body.get("modelId")
        if not model_id:
            return _err("model_id required")
        try:
            model_id = int(model_id)
        except Exception:
            return _err("model_id must be int")

        sort = body.get("sort") or "Most Reactions"
        period = body.get("period") or "Month"
        nsfw = body.get("nsfw") or "None"
        limit = int(body.get("limit") or 100)
        max_pages = int(body.get("max_pages") or 1)
        top_n = int(body.get("top_n") or 30)
        tag_names = body.get("tag_names") or ["风格"]
        title_prefix = body.get("title_prefix")
        token = body.get("token") or None

        loop = request.app.loop
        try:
            templates = await loop.run_in_executor(
                None,
                lambda: civitai_client.fetch_templates_from_model(
                    model_id,
                    sort=sort, period=period, nsfw=nsfw,
                    limit=limit, max_pages=max_pages,
                    title_prefix=title_prefix,
                    default_tag_names=tag_names,
                    token=token,
                ),
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            return _err("Civitai 拉取失败：" + str(e), 502)

        # 限 top_n + 依赖 prompt_manager 里同名 title 增量逻辑手工实现
        templates = templates[:max(0, top_n)]
        from core.db import get_db as _get_db
        try:
            db = _get_db()
        except Exception:
            from ..core.db import get_db as _get_db2  # type: ignore
            db = _get_db2()
        existing_titles = {r["title"] for r in db.fetchall("SELECT title FROM prompts")}
        tag_rows = db.fetchall("SELECT id, name FROM tags")
        tag_map = {r["name"]: r["id"] for r in tag_rows}

        added = 0
        for t in templates:
            title = t.get("title") or ""
            if not title or title in existing_titles:
                continue
            names = t.get("tag_names") or []
            tag_ids = [tag_map[n] for n in names if n in tag_map]
            prompt_manager.upsert_prompt({
                "title": title,
                "description": t.get("description", ""),
                "positive_prompt": t.get("positive_prompt", ""),
                "negative_prompt": t.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT,
                "artist_prompt": t.get("artist_prompt", ""),
                "is_pinned": False,
                "tag_ids": tag_ids,
            })
            existing_titles.add(title)
            added += 1
        return _ok({
            "model_id": model_id,
            "fetched": len(templates),
            "added": added,
            "sort": sort,
            "period": period,
        })

    # ---------- 标签 ----------
    @routes.get("/anima_t8/tags")
    async def list_tags(request: web.Request):
        # 首次访问时尝试种入默认标签
        try:
            tag_manager.ensure_default_tags()
        except Exception:
            pass
        return _ok(tag_manager.list_tags())

    @routes.post("/anima_t8/tags")
    async def upsert_tag(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        try:
            data = tag_manager.upsert_tag(
                body.get("name", ""),
                body.get("color", "#FF6B9D"),
                body.get("id"),
            )
            return _ok(data)
        except Exception as e:
            return _err(e)

    @routes.delete("/anima_t8/tags/{tid}")
    async def delete_tag(request: web.Request):
        tag_manager.delete_tag(request.match_info["tid"])
        return _ok()

    # ---------- 艺术家 ----------
    @routes.get("/anima_t8/artists")
    async def list_artists(request: web.Request):
        q = request.query
        loop = request.app.loop
        mgr = get_artist_manager()
        try:
            # 先试新签名，兼容旧 search() 不接受 letter / with_image_only 的情况
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: mgr.search(
                        keyword=q.get("q", ""),
                        page=int(q.get("page", "1") or 1),
                        page_size=int(q.get("page_size", "60") or 60),
                        pinned_only=q.get("pinned") == "1",
                        letter=q.get("letter", ""),
                        with_image_only=q.get("with_image") == "1",
                    ),
                )
            except TypeError:
                # 旧版 search() 没有这些参数，降级到最小调用
                result = await loop.run_in_executor(
                    None,
                    lambda: mgr.search(
                        keyword=q.get("q", ""),
                        page=int(q.get("page", "1") or 1),
                        page_size=int(q.get("page_size", "60") or 60),
                        pinned_only=q.get("pinned") == "1",
                    ),
                )
            return _ok(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("艺术家库读取失败：" + str(e), 500)

    @routes.post("/anima_t8/artists/refresh")
    async def refresh_artists(request: web.Request):
        loop = request.app.loop
        mgr = get_artist_manager()
        try:
            result = await loop.run_in_executor(None, lambda: mgr.fetch(force_refresh=True))
            return _ok({"count": len(result)})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("刷新失败：" + str(e), 500)

    @routes.post("/anima_t8/artists/{slug}/pin")
    async def pin_artist(request: web.Request):
        slug = request.match_info["slug"]
        try:
            body = await request.json()
        except Exception:
            body = {}
        get_artist_manager().pin(slug, bool(body.get("pinned", True)))
        return _ok()

    # ---------- Danbooru tags（artist / copyright / character） ----------
    # 后台补全 fetch 任务状态：category -> True 表示正在跑，避免重复启动
    _bg_fetch_running: dict = {}

    @routes.get("/anima_t8/dtags")
    async def list_dtags(request: web.Request):
        q = request.query
        loop = request.app.loop
        mgr = get_danbooru_manager()
        try:
            category = q.get("category", "artist")
            current_count = await loop.run_in_executor(None, lambda: mgr.count(category))
            if current_count == 0:
                # 首屏快速拉 2 页 (~2000 条) 让页面立即可用（约 2~5 秒）
                await loop.run_in_executor(
                    None, lambda: mgr.fetch(category, max_pages=2))
                # 后台异步补全剩下页面（不阻塞返回）
                if not _bg_fetch_running.get(category):
                    _bg_fetch_running[category] = True
                    def _bg_fill(cat=category):
                        try:
                            mgr.fetch(cat, force_refresh=True, max_pages=30)
                        except Exception as ex:
                            print(f"[anima_t8] bg fetch fail cat={cat}: {ex}")
                        finally:
                            _bg_fetch_running[cat] = False
                    loop.run_in_executor(None, _bg_fill)
            result = await loop.run_in_executor(
                None,
                lambda: mgr.search(
                    category=category,
                    keyword=q.get("q", ""),
                    page=int(q.get("page", "1") or 1),
                    page_size=int(q.get("page_size", "60") or 60),
                    pinned_only=q.get("pinned") == "1",
                    letter=q.get("letter", ""),
                ),
            )
            # 告诉前端是否还在后台补全，前端可以选择提示 / 定时重拉
            result["backfilling"] = bool(_bg_fetch_running.get(category))
            return _ok(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("Danbooru 标签读取失败：" + str(e), 500)

    @routes.post("/anima_t8/dtags/refresh")
    async def refresh_dtags(request: web.Request):
        loop = request.app.loop
        mgr = get_danbooru_manager()
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}
            category = body.get("category") or request.query.get("category", "artist")
            n = await loop.run_in_executor(
                None, lambda: mgr.fetch(category, force_refresh=True))
            return _ok({"count": n, "category": category})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("Danbooru 刷新失败：" + str(e), 500)

    @routes.post("/anima_t8/dtags/pin")
    async def pin_dtag(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        name = (body.get("name") or "").strip()
        category = body.get("category") or "artist"
        pinned = bool(body.get("pinned", True))
        if not name:
            return _err("name required")
        get_danbooru_manager().set_pinned(name, category, pinned)
        return _ok()

    @routes.get("/anima_t8/dtags/image")
    async def proxy_dtag_image(request: web.Request):
        """代理 Danbooru 图片，让浏览器从同源拿图，避开防盗链/CSP/网络拦截。"""
        u = request.query.get("u", "")
        if not u:
            return _err("u required")
        from urllib.parse import urlparse
        parsed = urlparse(u)
        allowed = ("cdn.donmai.us", "danbooru.donmai.us")
        if parsed.hostname not in allowed:
            return _err("hostname not allowed: " + str(parsed.hostname))
        def _fetch():
            import ssl as _ssl
            import urllib.request as _ur
            ctx = _ssl.create_default_context()
            req = _ur.Request(u, headers={
                "User-Agent": "AnimaForge/1.0",
                "Referer": "https://danbooru.donmai.us/",
            })
            with urlopen_with_route_retry(req, timeout=15, context=ctx) as r:
                return r.read(), r.headers.get("Content-Type", "image/jpeg")
        try:
            loop = request.app.loop
            body, ctype = await loop.run_in_executor(None, _fetch)
            return web.Response(body=body, content_type=ctype, headers={
                "Cache-Control": "public, max-age=86400",
            })
        except Exception as e:
            print(f"[anima_t8] image proxy failed url={u}: {e}")
            return _err("proxy failed: " + str(e), 502)

    @routes.get("/anima_t8/dtags/preview")
    async def preview_dtag(request: web.Request):
        """为 Danbooru 作品IP/角色IP/未命中moo的画师拉代表作首图。

        前端 IntersectionObserver 懒加载调用，后端走进程内存 LRU 缓存。
        """
        name = (request.query.get("name") or "").strip()
        if not name:
            return _err("name required")
        try:
            loop = request.app.loop
            data = await loop.run_in_executor(
                None, lambda: get_danbooru_manager().fetch_preview(name)
            )
            return _ok(data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("预览图获取失败：" + str(e), 500)

    # ---------- Gelbooru tags（artist / copyright / character / general） ----------
    _gel_bg_fetch_running: dict = {}

    @routes.get("/anima_t8/gtags")
    async def list_gtags(request: web.Request):
        q = request.query
        loop = request.app.loop
        mgr = get_gelbooru_manager()
        try:
            category = q.get("category", "artist")
            current_count = await loop.run_in_executor(None, lambda: mgr.count(category))
            if current_count == 0:
                await loop.run_in_executor(None, lambda: mgr.fetch(category, max_pages=2))
                if not _gel_bg_fetch_running.get(category):
                    _gel_bg_fetch_running[category] = True

                    def _bg_fill(cat=category):
                        try:
                            mgr.fetch(cat, force_refresh=True, max_pages=10)
                        except Exception as ex:
                            print(f"[anima_t8] gelbooru bg fetch fail cat={cat}: {ex}")
                        finally:
                            _gel_bg_fetch_running[cat] = False

                    loop.run_in_executor(None, _bg_fill)
            result = await loop.run_in_executor(
                None,
                lambda: mgr.search(
                    category=category,
                    keyword=q.get("q", ""),
                    page=int(q.get("page", "1") or 1),
                    page_size=int(q.get("page_size", "60") or 60),
                    pinned_only=q.get("pinned") == "1",
                    letter=q.get("letter", ""),
                ),
            )
            result["backfilling"] = bool(_gel_bg_fetch_running.get(category))
            return _ok(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("Gelbooru 标签读取失败：" + str(e), 500)

    @routes.post("/anima_t8/gtags/refresh")
    async def refresh_gtags(request: web.Request):
        loop = request.app.loop
        mgr = get_gelbooru_manager()
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}
            category = body.get("category") or request.query.get("category", "artist")
            n = await loop.run_in_executor(
                None, lambda: mgr.fetch(category, force_refresh=True))
            return _ok({"count": n, "category": category})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("Gelbooru 刷新失败：" + str(e), 500)

    @routes.post("/anima_t8/gtags/pin")
    async def pin_gtag(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        name = (body.get("name") or "").strip()
        category = body.get("category") or "artist"
        pinned = bool(body.get("pinned", True))
        if not name:
            return _err("name required")
        get_gelbooru_manager().set_pinned(name, category, pinned)
        return _ok()

    @routes.get("/anima_t8/gtags/image")
    async def proxy_gtag_image(request: web.Request):
        """代理 Gelbooru 图片，让浏览器从同源拿图。"""
        u = request.query.get("u", "")
        if not u:
            return _err("u required")
        from urllib.parse import urlparse
        parsed = urlparse(u)
        hostname = (parsed.hostname or "").lower()
        if hostname != "gelbooru.com" and not hostname.endswith(".gelbooru.com"):
            return _err("hostname not allowed: " + str(parsed.hostname))

        def _fetch():
            import ssl as _ssl
            import urllib.request as _ur
            ctx = _ssl.create_default_context()
            req = _ur.Request(u, headers={
                "User-Agent": "AnimaForge/1.0",
                "Referer": "https://gelbooru.com/",
            })
            with urlopen_with_route_retry(req, timeout=15, context=ctx) as r:
                return r.read(), r.headers.get("Content-Type", "image/jpeg")

        try:
            loop = request.app.loop
            body, ctype = await loop.run_in_executor(None, _fetch)
            return web.Response(body=body, content_type=ctype, headers={
                "Cache-Control": "public, max-age=86400",
            })
        except Exception as e:
            print(f"[anima_t8] gelbooru image proxy failed url={u}: {e}")
            return _err("proxy failed: " + str(e), 502)

    @routes.get("/anima_t8/gtags/preview")
    async def preview_gtag(request: web.Request):
        name = (request.query.get("name") or "").strip()
        if not name:
            return _err("name required")
        try:
            loop = request.app.loop
            data = await loop.run_in_executor(
                None, lambda: get_gelbooru_manager().fetch_preview(name)
            )
            return _ok(data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return _err("Gelbooru 预览图获取失败：" + str(e), 500)

    # ---------- 片段收藏 ----------
    @routes.get("/anima_t8/snippets")
    async def list_snippets(request: web.Request):
        return _ok(prompt_manager.list_snippets(request.query.get("type")))

    @routes.post("/anima_t8/snippets")
    async def add_snippet(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        return _ok(prompt_manager.add_snippet(
            body.get("content", ""), body.get("type", "positive")
        ))

    @routes.delete("/anima_t8/snippets/{sid}")
    async def del_snippet(request: web.Request):
        prompt_manager.delete_snippet(request.match_info["sid"])
        return _ok()

    # ---------- 元数据 / 默认 ----------
    @routes.get("/anima_t8/meta")
    async def meta(request: web.Request):
        return _ok({
            "default_negative": DEFAULT_NEGATIVE_PROMPT,
            "version": "1.1.0",
        })

    # ---------- 导入 / 导出 ----------
    @routes.get("/anima_t8/export")
    async def export_all(request: web.Request):
        return _ok(prompt_manager.export_all())

    @routes.post("/anima_t8/import")
    async def import_all(request: web.Request):
        try:
            body = await request.json()
        except Exception:
            return _err("invalid json")
        cnt = prompt_manager.import_all(body or {}, replace=bool(body.get("__replace")))
        return _ok(cnt)

    print("[anima_t8] 已注册 HTTP 路由（含 Danbooru/Gelbooru tags + Civitai 模板抓取）")
