"""
Civitai Images 客户端
=====================
拉取 Civitai 公开 image meta（prompt / negativePrompt），用来扩充 Anima 风格库。

公开 REST API 文档：https://github.com/civitai/civitai/wiki/REST-API-Reference
    GET https://civitai.com/api/v1/images
        ?modelId=...           # 指定 checkpoint / lora 的 modelId
        &modelVersionId=...    # 指定具体版本
        &sort=Most Reactions   # 排序：Most Reactions / Most Comments / Newest
        &period=Month          # 时间窗：AllTime / Year / Month / Week / Day
        &nsfw=None             # None / Soft / Mature / X（X 需登录 token）
        &limit=100             # 最多 200
        &page=1
    返回：{ "items": [...], "metadata": { "nextCursor": ..., "nextPage": ... } }

不需要 API key 即可访问公开数据。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from ..http_retry import urlopen_with_route_retry
except Exception:
    from http_retry import urlopen_with_route_retry

BASE_URL = "https://civitai.com/api/v1"
USER_AGENT = "comfyui-anima-t8/1.1 (https://github.com/T8mars/comfyui-anima-t8)"


def _build_url(path: str, params: Dict[str, Any]) -> str:
    q = {k: v for k, v in params.items() if v is not None and v != ""}
    return f"{BASE_URL}{path}?{urllib.parse.urlencode(q)}"


def _http_get_json(url: str, *, timeout: float = 30.0,
                   token: Optional[str] = None) -> Optional[Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urlopen_with_route_retry(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"[anima_t8] civitai HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"[anima_t8] civitai fetch failed: {e}")
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def fetch_images(
    *,
    model_id: Optional[int] = None,
    model_version_id: Optional[int] = None,
    sort: str = "Most Reactions",
    period: str = "Month",
    nsfw: str = "None",
    limit: int = 100,
    max_pages: int = 1,
    timeout: float = 30.0,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """拉取 Civitai images。返回原始 item 数组。

    至少需要传入 model_id 或 model_version_id 之一；都不传则按全站排序拉取。
    """
    items: List[Dict[str, Any]] = []
    next_page: Optional[int] = 1
    pages_done = 0
    t0 = time.time()
    while next_page and pages_done < max_pages:
        url = _build_url("/images", {
            "modelId": model_id,
            "modelVersionId": model_version_id,
            "sort": sort,
            "period": period,
            "nsfw": nsfw,
            "limit": min(max(int(limit or 100), 1), 200),
            "page": next_page,
        })
        data = _http_get_json(url, timeout=timeout, token=token)
        if not isinstance(data, dict):
            break
        page_items = data.get("items") or []
        if not isinstance(page_items, list):
            break
        items.extend(page_items)
        meta = data.get("metadata") or {}
        next_page = meta.get("nextPage") if isinstance(meta, dict) else None
        pages_done += 1
    print(f"[anima_t8] civitai fetched {len(items)} items "
          f"(model={model_id}, pages={pages_done}, {(time.time()-t0):.1f}s)")
    return items


def _clean_prompt(text: str) -> str:
    """把多行 prompt 折成一行，去重空白。"""
    if not text:
        return ""
    # 统一换行 / 去掉 BREAK 关键词 / 收敛多余空白
    s = text.replace("\r", "\n").replace("BREAK", ",").replace("\n", ", ")
    parts = [p.strip() for p in s.split(",")]
    parts = [p for p in parts if p]
    seen, out = set(), []
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return ", ".join(out)


# ----- 关键词 → 分类 表（用于自动给 Civitai 抓回的 prompt 打 tag）
# 顺序代表优先级。每张图最多保画 3 个 tag。
CLASSIFY_RULES = [
    ("画质",  ["score_9", "score_8", "score_7", "masterpiece", "best quality",
               "ultra detailed", "absurdres", "highres", "8k", "4k", "amazing quality",
               "very aesthetic"]),
    ("媒介",  ["oil painting", "watercolor", "pixel art", "lineart", "line art",
               "monochrome", "greyscale", "sketch", "pencil", "ukiyo-e", "sumi-e",
               "ink wash", "impasto", "flat color", "cel shading", "painterly",
               "woodblock"]),
    ("光影",  ["volumetric", "god rays", "golden hour", "neon", "moonlight",
               "backlight", "rim light", "backlit", "dramatic lighting",
               "chiaroscuro", "cinematic lighting", "sunlight", "bokeh"]),
    ("镜头",  ["close-up", "upper body", "full body", "from above", "from below",
               "dutch angle", "portrait", "face focus", "cowboy shot", "low angle"]),
    ("构图",  ["cinematic", "wide shot", "depth of field", "film grain", "anamorphic",
               "dynamic angle", "dramatic angle"]),
    ("服装",  ["dress", "kimono", "qipao", "cheongsam", "hanfu", "swimsuit",
               "bikini", "school uniform", "sailor uniform", "maid outfit",
               "victorian dress", "armor", "gothic dress", "sweater", "corset"]),
    ("表情",  ["smile", "blush", "crying", "angry", "surprised", "shy", "pout",
               "laughing", "smirk", "sad", "happy"]),
    ("季节",  ["cherry blossom", "sakura", "autumn", "maple leaves", "snow",
               "winter", "summer", "spring", "hanami"]),
    ("时代",  ["victorian", "medieval", "edo period", "1930s", "1900s", "shanghai",
               "futuristic", "retro", "vintage", "ancient chinese", "steampunk"]),
    ("场景",  ["classroom", "school", "cafe", "beach", "ocean", "forest", "city",
               "street", "cyberpunk city", "futuristic city", "castle",
               "space station", "ruined city", "post-apocalyptic", "courtyard",
               "indoors", "outdoors", "park", "library", "shrine"]),
    ("风格",  ["cyberpunk", "steampunk", "fantasy", "sci-fi", "ghibli", "miyazaki",
               "iyashikei", "chibi", "super deformed", "anime style", "manga style"]),
    ("情绪",  ["melancholic", "lonely", "cheerful", "mystical", "dreamy", "peaceful",
               "romantic", "ethereal", "epic", "mysterious", "calm"]),
    ("角色",  ["1girl", "1boy", "2girls", "2boys", "multiple girls", "multiple boys",
               "chibi", "loli", "shota"]),
    ("NSFW", ["nsfw", "explicit", "nude", "naked", "sex", "rating_explicit"]),
]


def _auto_classify(prompt_text: str, max_tags: int = 3) -> List[str]:
    """根据 prompt 内容自动匹配预设分类。

    返回按优先级取前 max_tags 个命中的中文分类名。
    全部未命中返回 ["风格"] 作为兑底。
    """
    if not prompt_text:
        return ["风格"]
    text = prompt_text.lower()
    hits: List[str] = []
    for tag, keywords in CLASSIFY_RULES:
        for kw in keywords:
            if kw in text:
                hits.append(tag)
                break
        if len(hits) >= max_tags:
            break
    return hits or ["风格"]


def _extract_from_comfy_workflow(comfy_str: str) -> Dict[str, str]:
    """从 ComfyUI workflow 字符串中提取 positive / negative prompt。

    Civitai 上新发布的图大部分是 ComfyUI 生成的，meta 里仅有
    `comfy` 字段 = 一串 JSON，里面 prompt 按 node_id 收纳。
    寻找 CLIPTextEncode 节点，根据 _meta.title 判断是 Positive 还是 Negative。
    inputs.text 可能是字符串 也可能是 ["node_id", index] 的引用，
    引用时追溯到被引用节点的 inputs.text / inputs.string。
    """
    out = {"positive": "", "negative": ""}
    if not comfy_str:
        return out
    try:
        data = json.loads(comfy_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    nodes = data.get("prompt") if isinstance(data.get("prompt"), dict) else data
    if not isinstance(nodes, dict):
        return out

    def _resolve_text(v: Any, depth: int = 0) -> str:
        """递归解析节点输入，取到字符串 prompt。限深度避免环。"""
        if depth > 4:
            return ""
        if isinstance(v, str):
            return v
        if isinstance(v, list) and len(v) >= 1:
            ref_id = str(v[0])
            ref = nodes.get(ref_id)
            if isinstance(ref, dict):
                ins = ref.get("inputs") or {}
                for k in ("text", "string", "value", "text_g", "text_l", "prompt"):
                    if k in ins:
                        return _resolve_text(ins[k], depth + 1)
        return ""

    for nid, node in nodes.items():
        if not isinstance(node, dict):
            continue
        ctype = (node.get("class_type") or "").lower()
        if "cliptextencode" not in ctype and "textencode" not in ctype \
                and "prompt" not in ctype:
            continue
        title = ""
        m = node.get("_meta")
        if isinstance(m, dict):
            title = (m.get("title") or "").lower()
        text = _resolve_text((node.get("inputs") or {}).get("text")) \
            or _resolve_text((node.get("inputs") or {}).get("string"))
        if not text:
            continue
        if "negative" in title or "负面" in title or "反向" in title:
            if not out["negative"]:
                out["negative"] = text
        else:
            # 默认当作正向 prompt（title 包含 positive / 正向 / 主提示 / 空）
            if not out["positive"]:
                out["positive"] = text
    return out


def _extract_meta(item: Dict[str, Any]) -> Dict[str, str]:
    """属 Civitai item 中抓取 prompt / negative，兼容 3 种结构。"""
    out = {"positive": "", "negative": "", "model": "", "sampler": ""}
    meta = item.get("meta") if isinstance(item, dict) else None
    if not isinstance(meta, dict):
        return out

    # 候选起点：meta 本身 、嵌套 meta.meta
    candidates: List[Dict[str, Any]] = [meta]
    inner = meta.get("meta")
    if isinstance(inner, dict):
        candidates.append(inner)

    for c in candidates:
        if not out["positive"]:
            out["positive"] = str(c.get("prompt") or "")
        if not out["negative"]:
            out["negative"] = str(c.get("negativePrompt") or c.get("negative_prompt") or "")
        if not out["model"]:
            out["model"] = str(c.get("Model") or c.get("model") or "")
        if not out["sampler"]:
            out["sampler"] = str(c.get("sampler") or c.get("Sampler") or "")

    # 还是拿不到 → 试试解 ComfyUI workflow字符串
    if not out["positive"]:
        for c in candidates:
            comfy = c.get("comfy")
            if isinstance(comfy, str) and comfy:
                got = _extract_from_comfy_workflow(comfy)
                if got["positive"] and not out["positive"]:
                    out["positive"] = got["positive"]
                if got["negative"] and not out["negative"]:
                    out["negative"] = got["negative"]
                if out["positive"]:
                    break
    return out


def _extract_score(item: Dict[str, Any]) -> int:
    """Civitai stats 里汇总 reaction 计数。优先 reactionCount，其次按各表情相加。"""
    stats = item.get("stats") if isinstance(item, dict) else None
    if not isinstance(stats, dict):
        return 0
    if stats.get("reactionCount") is not None:
        try:
            return int(stats.get("reactionCount") or 0)
        except (TypeError, ValueError):
            pass
    s = 0
    for k in ("heartCount", "likeCount", "laughCount", "cryCount", "commentCount"):
        try:
            s += int(stats.get(k) or 0)
        except (TypeError, ValueError):
            continue
    return s


def parse_image_to_template(
    item: Dict[str, Any],
    *,
    title_prefix: str = "Civitai",
    default_tag_names: Optional[List[str]] = None,
    auto_classify: bool = True,
) -> Optional[Dict[str, Any]]:
    """把单条 Civitai image item 转成 Anima 风格库需要的 dict。

    无 prompt 则返回 None。auto_classify=True 时根据 prompt 内容优先自动分类，
    否则使用 default_tag_names（兑底 ["风格"]）。
    """
    if not isinstance(item, dict):
        return None
    extracted = _extract_meta(item)
    prompt = _clean_prompt(extracted["positive"])
    if not prompt:
        return None
    neg = _clean_prompt(extracted["negative"])

    item_id = item.get("id")
    react = _extract_score(item)

    desc_bits = []
    if extracted["model"]:
        desc_bits.append(extracted["model"])
    if extracted["sampler"]:
        desc_bits.append(extracted["sampler"])
    if react:
        desc_bits.append(f"{react} reactions")

    if auto_classify:
        tag_names = _auto_classify(prompt)
        # 如果调用方传了 default_tag_names，作为补充添加（去重）
        if default_tag_names:
            for d in default_tag_names:
                if d not in tag_names:
                    tag_names.append(d)
    else:
        tag_names = list(default_tag_names or ["风格"])

    title = f"{title_prefix} #{item_id}" if item_id else title_prefix
    return {
        "title": title,
        "description": " · ".join(desc_bits) or "Civitai 抓取",
        "positive_prompt": prompt,
        "negative_prompt": neg,
        "artist_prompt": "",
        "is_pinned": False,
        "tag_names": tag_names,
        "_civitai_id": item_id,
        "_civitai_score": react,
    }


def fetch_templates_from_model(
    model_id: int,
    *,
    sort: str = "Most Reactions",
    period: str = "Month",
    nsfw: str = "None",
    limit: int = 100,
    max_pages: int = 1,
    title_prefix: Optional[str] = None,
    default_tag_names: Optional[List[str]] = None,
    token: Optional[str] = None,
    auto_classify: bool = True,
) -> List[Dict[str, Any]]:
    """便利函数：拉某个模型的高赞图，输出 prompt 模板列表。

    auto_classify=True 时每张图会根据 prompt 内容自动判入哪个分类。
    """
    items = fetch_images(
        model_id=model_id, sort=sort, period=period, nsfw=nsfw,
        limit=limit, max_pages=max_pages, token=token,
    )
    prefix = title_prefix or f"Civitai-{model_id}"
    templates = []
    for it in items:
        t = parse_image_to_template(it, title_prefix=prefix,
                                    default_tag_names=default_tag_names,
                                    auto_classify=auto_classify)
        if t:
            templates.append(t)
    templates.sort(key=lambda x: x.get("_civitai_score", 0), reverse=True)
    return templates
