"""Anima 艺术家数据远程客户端。

数据源：https://cdn.mooshieblob.com/20260325_anima_all_artists/indices/search.json
图片：  https://cdn.mooshieblob.com/20260325_anima_all_artists/images/<image_id>.webp
"""
import json
import urllib.request
import urllib.error
from typing import List, Dict, Any

try:
    from ..http_retry import read_response_limited, urlopen_with_route_retry
except Exception:
    from http_retry import read_response_limited, urlopen_with_route_retry


class ArtistClient:
    BASE_URL = "https://cdn.mooshieblob.com/20260325_anima_all_artists"
    SEARCH_URL = BASE_URL + "/indices/search.json"
    TIMEOUT = 30

    def fetch_all(self) -> List[Dict[str, Any]]:
        try:
            req = urllib.request.Request(
                self.SEARCH_URL,
                headers={"User-Agent": "comfyui-anima-t8/1.0"},
            )
            with urlopen_with_route_retry(req, timeout=self.TIMEOUT) as resp:
                if resp.status != 200:
                    print("[anima_t8] 远程返回非 200:", resp.status)
                    return []
                raw = read_response_limited(resp, 5 * 1024 * 1024).decode("utf-8")
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "artists" in data:
                    return data.get("artists") or []
                return []
        except Exception as e:
            print("[anima_t8] 获取艺术家列表失败:", type(e).__name__)
            return []

    def image_url(self, image_id: str) -> str:
        if not image_id:
            return ""
        return f"{self.BASE_URL}/images/{image_id}.webp"
