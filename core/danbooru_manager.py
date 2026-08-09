"""
Danbooru Tags 管理器
====================
负责：
- 在 anima_t8.db 内维护 danbooru_tags 表
- 按 category 拉取 / 搜索 / 翻页 / 字母过滤 / 收藏置顶
- 兼容前端 artist_gallery 的统一接口（items + total）

category 取值：1=artist  3=copyright  4=character
"""

from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from .db import get_db
    from ..api.danbooru_client import BASE_URL as DANBOORU_BASE, fetch_tags, CATEGORY_NAMES, CATEGORY_BY_NAME
    from ..http_retry import read_response_limited, urlopen_with_route_retry
except Exception:
    from core.db import get_db
    from api.danbooru_client import BASE_URL as DANBOORU_BASE, fetch_tags, CATEGORY_NAMES, CATEGORY_BY_NAME
    from http_retry import read_response_limited, urlopen_with_route_retry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS danbooru_tags (
    name        TEXT NOT NULL,
    category    INTEGER NOT NULL,
    post_count  INTEGER NOT NULL DEFAULT 0,
    pinned      INTEGER NOT NULL DEFAULT 0,
    pinned_at   REAL    NOT NULL DEFAULT 0,
    updated_at  REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (name, category)
);
CREATE INDEX IF NOT EXISTS idx_dbt_category   ON danbooru_tags(category);
CREATE INDEX IF NOT EXISTS idx_dbt_post_count ON danbooru_tags(post_count DESC);
CREATE INDEX IF NOT EXISTS idx_dbt_pinned     ON danbooru_tags(pinned DESC);
"""


def _normalize_category(value) -> int:
    """支持传 1/3/4 整数或 artist/copyright/character 字符串。"""
    if value is None:
        return 1
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s in CATEGORY_BY_NAME:
        return CATEGORY_BY_NAME[s]
    try:
        return int(s)
    except ValueError:
        return 1


class DanbooruManager:
    _instance: Optional["DanbooruManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.db = get_db()
        self.db.conn().executescript(_SCHEMA)

    # ---------- 拉取 ----------
    def count(self, category: int) -> int:
        category = _normalize_category(category)
        row = self.db.fetchone(
            "SELECT COUNT(*) AS c FROM danbooru_tags WHERE category=?",
            (category,),
        )
        return int(row["c"]) if row else 0

    def fetch(self, category, force_refresh: bool = False,
              min_count: int = 50, max_pages: int = 30) -> int:
        """按 category 拉取并写库；返回当前类总条数。"""
        category = _normalize_category(category)
        if not force_refresh and self.count(category) > 0:
            return self.count(category)

        rows = fetch_tags(category, max_pages=max_pages, min_count=min_count)
        now = time.time()
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM danbooru_tags WHERE category=? AND pinned=0",
                         (category,))
            for r in rows:
                # 已 pinned 的保留 pinned 状态，仅刷新 post_count
                conn.execute(
                    "INSERT INTO danbooru_tags(name, category, post_count, pinned, pinned_at, updated_at) "
                    "VALUES (?,?,?,0,0,?) "
                    "ON CONFLICT(name, category) DO UPDATE SET "
                    "  post_count=excluded.post_count, updated_at=excluded.updated_at",
                    (r["name"], r["category"], r["post_count"], now),
                )
        return self.count(category)

    # ---------- 搜索 ----------
    def search(self, category, keyword: str = "", page: int = 1,
               page_size: int = 60, pinned_only: bool = False,
               letter: str = "") -> Dict[str, Any]:
        """查询 danbooru_tags。数据源始终是 Danbooru API拉取的 tag。

        预览图不在此拼接：返回的 image_url 永远为空，前端通过
        IntersectionObserver 懒加载 /anima_t8/dtags/preview，后端代理调
        Danbooru posts.json 拿代表作首图。
        """
        category = _normalize_category(category)
        kw = (keyword or "").strip().lower()
        lt = (letter or "").strip().lower()

        wh = ["category=?"]
        params: List[Any] = [category]
        if kw:
            wh.append("LOWER(name) LIKE ?")
            params.append(f"%{kw}%")
        if pinned_only:
            wh.append("pinned=1")
        if lt:
            if lt == "#":
                wh.append("(LOWER(SUBSTR(name,1,1)) NOT BETWEEN 'a' AND 'z')")
            elif len(lt) == 1 and lt.isalpha():
                wh.append("LOWER(SUBSTR(name,1,1))=?")
                params.append(lt)
        where_sql = " WHERE " + " AND ".join(wh)

        total_row = self.db.fetchone(
            f"SELECT COUNT(*) AS c FROM danbooru_tags{where_sql}",
            tuple(params),
        )
        total = int(total_row["c"]) if total_row else 0

        offset = max(0, (page - 1) * page_size)
        rows = self.db.fetchall(
            f"SELECT name, category, post_count, pinned "
            f"FROM danbooru_tags{where_sql} "
            f"ORDER BY pinned DESC, post_count DESC, name ASC "
            f"LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )

        items = []
        for r in rows:
            items.append({
                "slug": r["name"],
                "tag": r["name"],
                "category": r["category"],
                "category_name": CATEGORY_NAMES.get(r["category"], "unknown"),
                "post_count": r["post_count"],
                "pinned": bool(r["pinned"]),
                "has_image": False,
                "image_url": "",
            })
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ---------- 单张预览图 ----------
    def fetch_preview(self, name: str) -> Dict[str, Any]:
        """调 Danbooru posts.json 拿代表作首图。用于作品IP/角色IP/未命中moo的画师。

        返回 {"image_url": str, "sample_url": str, "source_url": str}。
        失败时返回空 URL，由上层决定是否 fallback 到 placeholder。
        结果进入进程内存 LRU 缓存避免重复调用。
        """
        if not name:
            return {"image_url": "", "sample_url": "", "source_url": ""}
        cached = _PREVIEW_CACHE.get(name)
        if cached is not None:
            return cached

        # tag 中可能含括号等字符，urlencode 仅会处理路径中不安全的字符
        tag_q = urllib.parse.quote(name, safe=":/_")
        url = (f"{DANBOORU_BASE}/posts.json"
               f"?tags={tag_q}&limit=1")
        result = {"image_url": "", "sample_url": "", "source_url": ""}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AnimaForge/1.0"})
            ctx = ssl.create_default_context()
            t0 = time.time()
            raw = urlopen_with_route_retry(
                req,
                timeout=4,
                context=ctx,
                consume=lambda resp: read_response_limited(
                    resp, 5 * 1024 * 1024
                ).decode("utf-8", errors="ignore"),
            )
            data = json.loads(raw) if raw else []
            if isinstance(data, list) and data:
                p = data[0]
                # 原始 URL（可能在 cdn.donmai.us）
                preview_raw = (p.get("preview_file_url") or
                               p.get("large_file_url") or
                               p.get("file_url") or "")
                sample_raw = p.get("large_file_url") or p.get("file_url") or ""
                # 转成同源代理 URL，避免浏览器直连 donmai 被防盗链/CSP/网络拦截
                if preview_raw:
                    result["image_url"] = "/anima_t8/dtags/image?u=" + urllib.parse.quote(preview_raw, safe="")
                if sample_raw:
                    result["sample_url"] = "/anima_t8/dtags/image?u=" + urllib.parse.quote(sample_raw, safe="")
                result["source_url"] = f"{DANBOORU_BASE}/posts/{p.get('id')}" if p.get("id") else ""
            print(f"[anima_t8] preview {name} -> {'OK' if result['image_url'] else 'EMPTY'} ({(time.time()-t0)*1000:.0f}ms)")
        except Exception as e:
            print(f"[anima_t8] danbooru preview fetch failed name={name}: {e}")

        # 仅缓存成功结果；失败不缓存以便下次重试
        if result["image_url"]:
            _PREVIEW_CACHE[name] = result
            # 简易 LRU：超过 4096 条清理一半
            if len(_PREVIEW_CACHE) > 4096:
                for k in list(_PREVIEW_CACHE.keys())[:2048]:
                    _PREVIEW_CACHE.pop(k, None)
        return result

    # ---------- Pin ----------
    def set_pinned(self, name: str, category, pinned: bool) -> bool:
        category = _normalize_category(category)
        now = time.time() if pinned else 0
        cur = self.db.execute(
            "UPDATE danbooru_tags SET pinned=?, pinned_at=? WHERE name=? AND category=?",
            (1 if pinned else 0, now, name, category),
        )
        return cur.rowcount > 0


# 预览图进程内缓存（name -> {image_url,sample_url,source_url}）
_PREVIEW_CACHE: Dict[str, Dict[str, str]] = {}

_MGR: Optional[DanbooruManager] = None


def get_danbooru_manager() -> DanbooruManager:
    global _MGR
    if _MGR is None:
        with DanbooruManager._lock:
            if _MGR is None:
                _MGR = DanbooruManager()
    return _MGR
