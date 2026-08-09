"""
Danbooru Tags 客户端
====================
按 tag category 分页拉取 Danbooru 公开标签（不需要登录 / API key）。

category 取值：
    1 = artist     画师
    3 = copyright  作品 IP（动画/游戏/漫画作品名）
    4 = character  角色 IP
    5 = meta       元标签（画质/媒介/年代/镜头等响应风格的 token）

接口：
    https://danbooru.donmai.us/tags.json
        ?search[category]=1
        &search[order]=count
        &search[hide_empty]=yes
        &search[post_count_gteq]=50
        &limit=1000
        &page=N
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

try:
    from ..http_retry import read_response_limited, urlopen_with_route_retry
except Exception:
    from http_retry import read_response_limited, urlopen_with_route_retry

BASE_URL = "https://danbooru.donmai.us"
USER_AGENT = "comfyui-anima-t8/1.0 (https://github.com/mikuYongh/AnimaForge)"

CATEGORY_NAMES = {1: "artist", 3: "copyright", 4: "character", 5: "meta"}
CATEGORY_BY_NAME = {v: k for k, v in CATEGORY_NAMES.items()}


def _fetch_one_page(category: int, page: int, *, page_size: int, min_count: int,
                    timeout: float) -> Tuple[int, Optional[List[Dict]]]:
    """拉单页；超出范围 / 错误返回 None。"""
    url = (
        f"{BASE_URL}/tags.json"
        f"?search[category]={category}"
        f"&search[order]=count"
        f"&search[hide_empty]=yes"
        f"&search[post_count_gteq]={min_count}"
        f"&limit={page_size}"
        f"&page={page}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen_with_route_retry(req, timeout=timeout) as resp:
            payload = read_response_limited(resp, 5 * 1024 * 1024).decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return page, None
        print(f"[anima_t8] fetch_tags page={page} HTTP {e.code}")
        return page, None
    except Exception as e:
        print(f"[anima_t8] fetch_tags page={page} fail: {type(e).__name__}")
        return page, None
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError:
        return page, None
    if not isinstance(rows, list):
        return page, None
    return page, rows


def fetch_tags(
    category: int,
    *,
    max_pages: int = 30,
    min_count: int = 50,
    page_size: int = 1000,
    timeout: float = 30.0,
    max_workers: int = 4,
) -> List[Dict]:
    """并发拉取指定 category 的所有 tag（同时 4 页）。

    返回按 page 顺序展平后按 post_count 降序的列表。
    """
    if category not in CATEGORY_NAMES:
        raise ValueError(f"unsupported category: {category}")

    pages_data: Dict[int, List[Dict]] = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                _fetch_one_page, category, p,
                page_size=page_size, min_count=min_count, timeout=timeout,
            ): p for p in range(1, max_pages + 1)
        }
        for fut in as_completed(futures):
            page, rows = fut.result()
            if rows:
                pages_data[page] = rows

    out: List[Dict] = []
    for p in sorted(pages_data.keys()):
        for r in pages_data[p]:
            name = (r.get("name") or "").strip()
            if not name:
                continue
            out.append({
                "name": name,
                "category": int(r.get("category", category)),
                "post_count": int(r.get("post_count", 0)),
            })
    print(f"[anima_t8] fetch_tags category={category} pages={len(pages_data)} "
          f"items={len(out)} ({(time.time()-t0):.1f}s, {max_workers} workers)")
    return out


def fetch_all_three(
    *,
    max_pages: int = 30,
    min_count: int = 50,
) -> Dict[str, List[Dict]]:
    """便利函数：一次性拉三类。"""
    result = {}
    for cat in (1, 3, 4):
        result[CATEGORY_NAMES[cat]] = fetch_tags(
            cat, max_pages=max_pages, min_count=min_count,
        )
    return result
