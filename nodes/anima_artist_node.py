"""Anima Artist Style T8 节点：选择艺术家并按权重格式化输出。

额外输出：PREVIEW_IMAGES (IMAGE)
    并发从 Danbooru posts.json 拉每个 tag 的代表作首图，拼成 batch tensor。
    可接到 PreviewImage 节点查看当前选中画师 / IP 的风格预览。
"""

import io
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

try:
    from ..http_retry import read_response_limited, urlopen_with_route_retry
except Exception:
    from http_retry import read_response_limited, urlopen_with_route_retry

DANBOORU_BASE = "https://danbooru.donmai.us"
_USER_AGENT = "comfyui-anima-t8/1.0"
_PREVIEW_W, _PREVIEW_H = 512, 768  # 输出画布尺寸（实际图片等比缩放后居中填充到该画布，保持原比例）


def _fetch_preview_pil(name: str, timeout: float = 8.0):
    """从 Danbooru 拉一个 tag 的代表作首图，返回 PIL.Image 或 None。"""
    try:
        from PIL import Image  # 延迟导入，避免节点加载时依赖错误
    except ImportError:
        print("[anima_t8] Pillow 未安装，无法生成预览图")
        return None
    tag_q = urllib.parse.quote(name, safe=":/_")
    api = f"{DANBOORU_BASE}/posts.json?tags={tag_q}&limit=1"
    try:
        req = urllib.request.Request(api, headers={"User-Agent": _USER_AGENT})
        with urlopen_with_route_retry(req, timeout=timeout) as resp:
            data = json.loads(read_response_limited(resp, 5 * 1024 * 1024).decode("utf-8", errors="ignore"))
        if not isinstance(data, list) or not data:
            return None
        p = data[0]
        img_url = (p.get("large_file_url") or p.get("preview_file_url")
                   or p.get("file_url") or "")
        if not img_url:
            return None
        req2 = urllib.request.Request(img_url, headers={
            "User-Agent": _USER_AGENT,
            "Referer": "https://danbooru.donmai.us/",
        })
        with urlopen_with_route_retry(req2, timeout=timeout * 2) as resp:
            buf = read_response_limited(resp)
        return Image.open(io.BytesIO(buf)).convert("RGB")
    except Exception as e:
        print(f"[anima_t8] preview fetch failed: {type(e).__name__}")
        return None


def _strip_name_for_query(s: str) -> str:
    """把任意形态的画师 token 化为纯 tag name（供 Danbooru 查询）。

    接受：`wlop` / `@wlop` / `wlop:1.1` / `(@wlop:1.1)` / `(artist:wlop:1.1)`
    返回：`wlop`
    """
    t = (s or "").strip()
    if not t:
        return ""
    # 拆括号：(@wlop:1.1) → @wlop:1.1
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
    # 去 @ / artist: 前缀
    if t.startswith("@"):
        t = t[1:]
    if t.startswith("artist:"):
        t = t[len("artist:"):]
    # 去尾部 :weight（仅当尾是纯数字时）
    if ":" in t:
        head, _, tail = t.rpartition(":")
        try:
            float(tail)
            t = head
        except ValueError:
            pass
    return t.strip()


class AnimaArtistStyleT8:
    """艺术家风格输出节点。

    输入多个 artist_tags，可用 **逗号** 或 **换行** 分隔（两者可混用），
    每个项为一个 slug 或 tag，可附 `:weight`。
    例如：
        wlop:1.1, hiten, (artist:somebody:0.9)
    输出按 ComfyUI 权重格式 `(artist:slug:weight)` 拼接。
    """

    CATEGORY = "Anima/T8"
    FUNCTION = "build"
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("STYLE_PROMPT", "PREVIEW_IMAGES")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "artist_tags": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "逗号或换行分隔多个画师。例：wlop:1.1, hiten。也可点击节点上方按钮打开艺术家库选择。",
                }),
                "default_weight": ("FLOAT", {
                    "default": 1.0, "min": 0.1, "max": 2.0, "step": 0.05,
                }),
                "use_artist_prefix": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                # 本次从艺术家库“添加选中”的画师名列表（逗号或换行分隔）。
                # 运行时 PREVIEW_IMAGES 仅对该列表拉预览图；为空时退回到 artist_tags 全部。
                "last_picked": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "本次选中的画师（点击“添加选中”时自动填充，为空则预览 artist_tags 全部）",
                }),
            },
        }

    def build(self, artist_tags: str, default_weight: float = 1.0,
              use_artist_prefix: bool = True, last_picked: str = ""):
        out: List[str] = []
        names: List[str] = []  # 去权重去括号后的纯 name，用于拉预览图
        # 允许逗号与换行混用：先切行，再按逗号拆分
        raw_tokens = []
        for ln in (artist_tags or "").splitlines():
            for piece in ln.split(","):
                raw_tokens.append(piece)
        for raw in raw_tokens:
            line = raw.strip().strip(",")
            if not line:
                continue
            # 已带括号的整体直接保留（例如用户手输的 (artist:xxx:0.9)、(@wlop:1.1) 等）
            if line.startswith("(") and line.endswith(")"):
                out.append(line)
                # 从括号里提取 name（用于预览图）
                inner = line.strip("()").strip()
                if inner.startswith("@"):
                    inner = inner[1:].strip()
                if inner.startswith("artist:"):
                    inner = inner[len("artist:"):]
                if ":" in inner:
                    inner = inner.rsplit(":", 1)[0].strip()
                if inner:
                    names.append(inner)
                continue
            # 检测原始是否打了画师标记 @：决定输出用 @ 还是裸输出
            is_artist = line.startswith("@")
            if is_artist:
                line = line[1:].strip()
            # 拆 weight
            if ":" in line:
                parts = line.rsplit(":", 1)
                name = parts[0].strip()
                try:
                    w = float(parts[1])
                except ValueError:
                    name = line
                    w = default_weight
            else:
                name = line
                w = default_weight

            # 入口安全重为纯 name（去双重括号、artist: 残留、多余 @）
            name = name.replace("(artist:", "").strip()
            # 仅在括号不平衡（被外层包裹丢了左括号）时才 rstrip，
            # 避免误删合法名字里的右括号，例如 kouji_(campus_life)
            while name.endswith(")") and name.count("(") < name.count(")"):
                name = name[:-1]
            if name.startswith("@"):
                name = name[1:].strip()
            if name.startswith("artist:"):
                name = name[len("artist:"):].strip()
            if not name:
                continue
            names.append(name)

            # 输出格式：
            #   - 画师 (is_artist=True) 且 use_artist_prefix=True → @name / (@name:weight)
            #   - 其他 → 裸 name / (name:weight)
            tag = f"@{name}" if (is_artist and use_artist_prefix) else name
            if abs(w - 1.0) < 1e-3:
                out.append(tag)
            else:
                out.append(f"({tag}:{w:.2f})")

        prompt = ", ".join(out)
        # 合并 last_picked 中不在 artist_tags 里的额外 token（作品 IP / 角色 IP / 风格·meta 等）。
        # last_picked 是裸 name（前端 strip 过 @）——追加输出也用裸名，以 ", " 连接。
        existing_lower = {n.lower() for n in names}
        extras: List[str] = []
        seen_extra = set()
        for t in self._parse_names(last_picked):
            if not t:
                continue
            tl = t.lower()
            if tl in existing_lower or tl in seen_extra:
                continue
            seen_extra.add(tl)
            extras.append(t)
        if extras:
            extra_str = ", ".join(extras)
            prompt = (prompt + ", " + extra_str) if prompt else extra_str
        # 预览图：优先拉 last_picked（含额外项）；为空才退回到 artist_tags 全部
        preview_names = self._parse_names(last_picked) if (last_picked or "").strip() else names
        preview = self._build_preview_tensor(preview_names)
        return (prompt, preview)

    @staticmethod
    def _parse_names(text: str) -> List[str]:
        """从逗号 / 换行分隔的文本里提取纯 name 列表（去权重去括号去 @ 前缀）。"""
        out: List[str] = []
        for ln in (text or "").splitlines():
            for piece in ln.split(","):
                t = _strip_name_for_query(piece.strip().strip(","))
                if t:
                    out.append(t)
        return out

    # ------------------------------------------------------------------
    # 预览图拼装
    # ------------------------------------------------------------------
    def _build_preview_tensor(self, names: List[str]):
        """并发拉取所有 name 的首图并拼成 [B,H,W,3] tensor。"""
        try:
            import numpy as np
            import torch
            from PIL import Image
        except ImportError as e:
            print(f"[anima_t8] preview 依赖缺失: {e}")
            import torch
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        if not names:
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        # 去重（保持输入顺序）
        seen = set()
        uniq_names = []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq_names.append(n)

        # 限制最多 16 张，避免选太多时超时
        if len(uniq_names) > 16:
            print(f"[anima_t8] preview limit 16/{len(uniq_names)}")
            uniq_names = uniq_names[:16]

        results: List[Optional[Image.Image]] = [None] * len(uniq_names)
        with ThreadPoolExecutor(max_workers=min(6, len(uniq_names))) as ex:
            fut_map = {ex.submit(_fetch_preview_pil, n): i
                       for i, n in enumerate(uniq_names)}
            for fut in as_completed(fut_map):
                idx = fut_map[fut]
                try:
                    results[idx] = fut.result()
                except Exception as e:
                    print(f"[anima_t8] preview thread fail: {e}")

        valid = [im for im in results if im is not None]
        if not valid:
            print("[anima_t8] no preview images fetched")
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        arr_list = []
        for im in valid:
            try:
                # 等比缩放：以画布为上限，取 min(scale_w, scale_h) 使长边贴合画布边
                src_w, src_h = im.size
                if src_w <= 0 or src_h <= 0:
                    continue
                scale = min(_PREVIEW_W / src_w, _PREVIEW_H / src_h)
                new_w = max(1, int(round(src_w * scale)))
                new_h = max(1, int(round(src_h * scale)))
                im_resized = im.resize((new_w, new_h), Image.LANCZOS)
                # 居中贴到 (_PREVIEW_W, _PREVIEW_H) 黑底画布上 → 保持原比例、多余部分补黑边
                canvas = Image.new("RGB", (_PREVIEW_W, _PREVIEW_H), (0, 0, 0))
                ox = (_PREVIEW_W - new_w) // 2
                oy = (_PREVIEW_H - new_h) // 2
                canvas.paste(im_resized, (ox, oy))
                arr = np.array(canvas, dtype=np.float32) / 255.0
                if arr.ndim == 2:  # 灰度补3通道
                    arr = np.stack([arr, arr, arr], axis=-1)
                if arr.shape[-1] == 4:  # 丢掉 alpha
                    arr = arr[..., :3]
                arr_list.append(arr)
            except Exception as e:
                print(f"[anima_t8] preview convert fail: {e}")
        if not arr_list:
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        tensor = torch.from_numpy(np.stack(arr_list, axis=0))
        print(f"[anima_t8] preview built {tensor.shape}")
        return tensor


NODE_CLASS_MAPPINGS = {"AnimaArtistStyleT8": AnimaArtistStyleT8}
NODE_DISPLAY_NAME_MAPPINGS = {"AnimaArtistStyleT8": "Anima Artist Style T8"}
