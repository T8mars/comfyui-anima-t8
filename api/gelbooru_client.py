"""
Gelbooru DAPI 客户端
====================
按 tag type 分页拉取 Gelbooru 公开标签，并按 tag 拉取代表作预览。

Gelbooru 使用旧式 DAPI：
    https://gelbooru.com/index.php?page=dapi&s=tag&q=index&json=1
    https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1

tag type 兼容 Danbooru 数字约定：
    0 = general
    1 = artist
    3 = copyright
    4 = character
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..http_retry import urlopen_with_route_retry
except Exception:
    from http_retry import urlopen_with_route_retry

BASE_URL = "https://gelbooru.com"
USER_AGENT = "comfyui-anima-t8/1.4 (https://github.com/T8mars/comfyui-anima-t8)"

CATEGORY_NAMES = {0: "general", 1: "artist", 3: "copyright", 4: "character"}
CATEGORY_BY_NAME = {v: k for k, v in CATEGORY_NAMES.items()}
_AUTH_CACHE: Optional[Dict[str, str]] = None

_AUTOCOMPLETE_CATEGORY = {
    "tag": 0,
    "metadata": 0,
    "artist": 1,
    "copyright": 3,
    "character": 4,
}

_FALLBACK_TERMS = {
    0: ["1girl", "solo", "long_hair", "blue_eyes", "blush", "smile", "absurdres", "highres"],
    1: ["wlop", "hiten", "kantoku", "ask", "as109", "ciloranko", "redjuice", "tony"],
    3: ["genshin", "naruto", "pokemon", "fate", "azur_lane", "touhou", "blue_archive", "kantai"],
    4: ["hatsune", "miku", "saber", "rem", "lumine", "raiden", "asuna", "frieren"],
}


class GelbooruAuthError(RuntimeError):
    """Gelbooru DAPI requires user_id/api_key for this request."""


def _load_auth_file() -> Dict[str, str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "gelbooru_auth.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    api_key = str(data.get("api_key") or "").strip()
    user_id = str(data.get("user_id") or "").strip()
    return {"api_key": api_key, "user_id": user_id}


def _resolve_auth(api_key: Optional[str], user_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """认证优先级：显式参数 > 环境变量 > data/gelbooru_auth.json。"""
    if api_key and user_id:
        return api_key, user_id
    env_key = (os.environ.get("GELBOORU_API_KEY") or "").strip()
    env_uid = (os.environ.get("GELBOORU_USER_ID") or "").strip()
    if not api_key and env_key:
        api_key = env_key
    if not user_id and env_uid:
        user_id = env_uid
    if api_key and user_id:
        return api_key, user_id

    global _AUTH_CACHE
    if _AUTH_CACHE is None:
        _AUTH_CACHE = _load_auth_file()
    if not api_key:
        api_key = _AUTH_CACHE.get("api_key") or None
    if not user_id:
        user_id = _AUTH_CACHE.get("user_id") or None
    return api_key, user_id


def normalize_category(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value if value in CATEGORY_NAMES else 0
    s = str(value).strip().lower()
    if s in CATEGORY_BY_NAME:
        return CATEGORY_BY_NAME[s]
    try:
        n = int(s)
        return n if n in CATEGORY_NAMES else 0
    except ValueError:
        return 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_url(params: Dict[str, Any]) -> str:
    q = {k: v for k, v in params.items() if v is not None and v != ""}
    return f"{BASE_URL}/index.php?{urllib.parse.urlencode(q)}"


def _http_get_json(url: str, *, timeout: float = 30.0) -> Optional[Any]:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urlopen_with_route_retry(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise GelbooruAuthError(
                "Gelbooru API 返回 401，需要配置 user_id/api_key "
                "（环境变量 GELBOORU_USER_ID/GELBOORU_API_KEY 或 data/gelbooru_auth.json）"
            )
        print(f"[anima_t8] gelbooru HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"[anima_t8] gelbooru fetch failed: {e}")
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _http_get_text(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen_with_route_retry(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[anima_t8] gelbooru html fetch failed: {e}")
        return ""


def _extract_records(data: Any, key: str) -> List[Dict[str, Any]]:
    """兼容 Gelbooru DAPI 常见 JSON 形态。

    有的返回是 `{"post": [...]}` / `{"tag": [...]}`，有的在空结果时返回
    空数组或带 `@attributes` 的对象。
    """
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []

    direct = data.get(key)
    if isinstance(direct, list):
        return [x for x in direct if isinstance(x, dict)]
    if isinstance(direct, dict):
        return [direct]

    plural = data.get(key + "s")
    if isinstance(plural, list):
        return [x for x in plural if isinstance(x, dict)]
    if isinstance(plural, dict):
        inner = plural.get(key)
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        if isinstance(inner, dict):
            return [inner]

    if key == "tag" and ("name" in data or "count" in data):
        return [data]
    if key == "post" and ("file_url" in data or "preview_url" in data):
        return [data]
    return []


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE_URL + u
    return u


def autocomplete_tags(
    term: str,
    category: int,
    *,
    limit: int = 20,
    timeout: float = 15.0,
) -> List[Dict[str, Any]]:
    """使用公开 autocomplete2 端点获取标签。

    Gelbooru 当前对正式 DAPI 可能返回 401，但 autocomplete2 对未登录用户可用。
    """
    category = normalize_category(category)
    q = (term or "").strip()
    if not q:
        return []
    url = _build_url({
        "page": "autocomplete2",
        "term": q,
        "type": "tag_query",
        "limit": max(1, min(int(limit or 20), 50)),
    })
    data = _http_get_json(url, timeout=timeout)
    rows = data if isinstance(data, list) else []
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        row_cat = _AUTOCOMPLETE_CATEGORY.get(str(r.get("category") or "").lower(), 0)
        if row_cat != category:
            continue
        name = (r.get("value") or r.get("label") or "").strip().replace(" ", "_")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({
            "name": name,
            "category": row_cat,
            "post_count": _safe_int(r.get("post_count"), 0),
        })
    return out


def _fallback_fetch_tags(category: int, *, page_size: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for term in _FALLBACK_TERMS.get(category, []):
        for r in autocomplete_tags(term, category, limit=min(50, max(10, page_size))):
            key = (r["name"], r["category"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda x: (-int(x.get("post_count") or 0), x.get("name") or ""))
    return rows


def _fetch_one_tag_page(
    category: int,
    page: int,
    *,
    page_size: int,
    timeout: float,
    api_key: Optional[str],
    user_id: Optional[str],
) -> Tuple[int, Optional[List[Dict[str, Any]]]]:
    api_key, user_id = _resolve_auth(api_key, user_id)
    params = {
        "page": "dapi",
        "s": "tag",
        "q": "index",
        "json": 1,
        "limit": page_size,
        "pid": page - 1,
        "orderby": "count",
        "order": "desc",
        # Gelbooru accepts this on current deployments even though older docs
        # mainly list generic tag query params. If ignored, local filtering still
        # keeps the returned rows in the requested category.
        "type": category,
        "api_key": api_key,
        "user_id": user_id,
    }
    data = _http_get_json(_build_url(params), timeout=timeout)
    if data is None:
        return page, None
    rows = _extract_records(data, "tag")
    return page, rows


def fetch_tags(
    category: int,
    *,
    max_pages: int = 10,
    page_size: int = 100,
    timeout: float = 30.0,
    max_workers: int = 4,
    api_key: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """并发拉取 Gelbooru 标签，并归一化为 name/category/post_count。"""
    category = normalize_category(category)
    pages_data: Dict[int, List[Dict[str, Any]]] = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                _fetch_one_tag_page,
                category,
                p,
                page_size=page_size,
                timeout=timeout,
                api_key=api_key,
                user_id=user_id,
            ): p
            for p in range(1, max_pages + 1)
        }
        for fut in as_completed(futures):
            try:
                page, rows = fut.result()
            except GelbooruAuthError as e:
                print(f"[anima_t8] gelbooru DAPI unauthorized; using autocomplete fallback: {e}")
                return _fallback_fetch_tags(category, page_size=page_size)
            if rows:
                pages_data[page] = rows

    out: List[Dict[str, Any]] = []
    seen = set()
    for p in sorted(pages_data.keys()):
        for r in pages_data[p]:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            row_cat = normalize_category(r.get("type", r.get("category", category)))
            if row_cat != category:
                continue
            key = (name, row_cat)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": name,
                "category": row_cat,
                "post_count": _safe_int(r.get("count", r.get("post_count")), 0),
            })
    out.sort(key=lambda x: (-int(x.get("post_count") or 0), x.get("name") or ""))
    print(f"[anima_t8] gelbooru fetch_tags category={category} pages={len(pages_data)} "
          f"items={len(out)} ({(time.time()-t0):.1f}s)")
    return out


def fetch_preview_post(
    name: str,
    *,
    timeout: float = 10.0,
    api_key: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, str]:
    """按 tag 拉一张 Gelbooru 代表图。返回原始 URL，由上层决定是否代理。"""
    tag = (name or "").strip()
    if not tag:
        return {"image_url": "", "sample_url": "", "file_url": "", "source_url": ""}
    api_key, user_id = _resolve_auth(api_key, user_id)
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": 1,
        "limit": 1,
        "pid": 0,
        "tags": tag,
        "api_key": api_key,
        "user_id": user_id,
    }
    try:
        data = _http_get_json(_build_url(params), timeout=timeout)
    except GelbooruAuthError as e:
        print(f"[anima_t8] gelbooru post DAPI unauthorized; using html fallback: {e}")
        return fetch_preview_from_html(tag, timeout=timeout)
    rows = _extract_records(data, "post")
    if not rows:
        return {"image_url": "", "sample_url": "", "file_url": "", "source_url": ""}
    p = rows[0]
    post_id = p.get("id") or ""
    preview = _normalize_url(str(p.get("preview_url") or ""))
    sample = _normalize_url(str(p.get("sample_url") or ""))
    file_url = _normalize_url(str(p.get("file_url") or ""))
    return {
        "image_url": preview or sample or file_url,
        "sample_url": sample or file_url or preview,
        "file_url": file_url or sample or preview,
        "source_url": f"{BASE_URL}/index.php?page=post&s=view&id={post_id}" if post_id else "",
    }


def fetch_preview_from_html(name: str, *, timeout: float = 10.0) -> Dict[str, str]:
    tag = (name or "").strip()
    if not tag:
        return {"image_url": "", "sample_url": "", "file_url": "", "source_url": ""}
    url = _build_url({
        "page": "post",
        "s": "list",
        "tags": tag,
    })
    html = _http_get_text(url, timeout=timeout)
    if not html:
        return {"image_url": "", "sample_url": "", "file_url": "", "source_url": ""}
    m = re.search(r"https?://[^\"']+?(?:thumbnail|samples|images)[^\"']+?\.(?:jpg|jpeg|png|webp)", html)
    img = _normalize_url(m.group(0)) if m else ""
    post = re.search(r"index\.php\?page=post&amp;s=view&amp;id=(\d+)", html)
    post_id = post.group(1) if post else ""
    return {
        "image_url": img,
        "sample_url": img,
        "file_url": img,
        "source_url": f"{BASE_URL}/index.php?page=post&s=view&id={post_id}" if post_id else url,
    }
