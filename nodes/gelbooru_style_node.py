"""Anima Gelbooru Style T8 节点：Gelbooru 标签输出 + 预览图。"""

import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

try:
    from api.gelbooru_client import fetch_preview_post
except Exception:
    from ..api.gelbooru_client import fetch_preview_post

_USER_AGENT = "comfyui-anima-t8/1.4"
_PREVIEW_W, _PREVIEW_H = 512, 768


def _strip_name_for_query(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
    if t.startswith("@"):
        t = t[1:]
    if t.startswith("artist:"):
        t = t[len("artist:"):]
    if ":" in t:
        head, _, tail = t.rpartition(":")
        try:
            float(tail)
            t = head
        except ValueError:
            pass
    return t.strip()


def _fetch_preview_pil(name: str, timeout: float = 8.0):
    """从 Gelbooru 拉一个 tag 的代表作首图，返回 PIL.Image 或 None。"""
    try:
        from PIL import Image
    except ImportError:
        print("[anima_t8] Pillow 未安装，无法生成 Gelbooru 预览图")
        return None
    try:
        data = fetch_preview_post(name, timeout=timeout)
        img_url = data.get("sample_url") or data.get("file_url") or data.get("image_url") or ""
        if not img_url:
            return None
        req = urllib.request.Request(img_url, headers={
            "User-Agent": _USER_AGENT,
            "Referer": "https://gelbooru.com/",
        })
        with urlopen_with_route_retry(req, timeout=timeout * 2) as resp:
            buf = resp.read()
        return Image.open(io.BytesIO(buf)).convert("RGB")
    except Exception as e:
        print(f"[anima_t8] gelbooru preview fetch fail name={name}: {e}")
        return None


class AnimaGelbooruStyleT8:
    """Gelbooru 标签输出节点。

    画师类 token 由前端写入为 `@name`，其他 Gelbooru tag 保持裸名。
    """

    CATEGORY = "Anima/T8"
    FUNCTION = "build"
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("STYLE_PROMPT", "PREVIEW_IMAGES")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "gelbooru_tags": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "逗号或换行分隔 Gelbooru 标签。例：@wlop, 1girl, long_hair。",
                }),
                "default_weight": ("FLOAT", {
                    "default": 1.0, "min": 0.1, "max": 2.0, "step": 0.05,
                }),
                "use_artist_prefix": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "last_picked": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "本次选中的 Gelbooru 标签（点击添加时自动填充，为空则预览 gelbooru_tags 全部）",
                }),
            },
        }

    def build(self, gelbooru_tags: str, default_weight: float = 1.0,
              use_artist_prefix: bool = True, last_picked: str = ""):
        out: List[str] = []
        names: List[str] = []
        raw_tokens = []
        for ln in (gelbooru_tags or "").splitlines():
            for piece in ln.split(","):
                raw_tokens.append(piece)

        for raw in raw_tokens:
            line = raw.strip().strip(",")
            if not line:
                continue
            if line.startswith("(") and line.endswith(")"):
                out.append(line)
                inner = _strip_name_for_query(line)
                if inner:
                    names.append(inner)
                continue

            is_artist = line.startswith("@")
            if is_artist:
                line = line[1:].strip()
            if ":" in line:
                parts = line.rsplit(":", 1)
                name = parts[0].strip()
                try:
                    weight = float(parts[1])
                except ValueError:
                    name = line
                    weight = default_weight
            else:
                name = line
                weight = default_weight

            name = name.replace("(artist:", "").strip()
            while name.endswith(")") and name.count("(") < name.count(")"):
                name = name[:-1]
            if name.startswith("@"):
                name = name[1:].strip()
            if name.startswith("artist:"):
                name = name[len("artist:"):].strip()
            if not name:
                continue
            names.append(name)

            tag = f"@{name}" if (is_artist and use_artist_prefix) else name
            if abs(weight - 1.0) < 1e-3:
                out.append(tag)
            else:
                out.append(f"({tag}:{weight:.2f})")

        prompt = ", ".join(out)
        existing_lower = {n.lower() for n in names}
        extras: List[str] = []
        seen_extra = set()
        for t in self._parse_names(last_picked):
            tl = t.lower()
            if not t or tl in existing_lower or tl in seen_extra:
                continue
            seen_extra.add(tl)
            extras.append(t)
        if extras:
            prompt = (prompt + ", " + ", ".join(extras)) if prompt else ", ".join(extras)

        preview_names = self._parse_names(last_picked) if (last_picked or "").strip() else names
        preview = self._build_preview_tensor(preview_names)
        return (prompt, preview)

    @staticmethod
    def _parse_names(text: str) -> List[str]:
        out: List[str] = []
        for ln in (text or "").splitlines():
            for piece in ln.split(","):
                t = _strip_name_for_query(piece.strip().strip(","))
                if t:
                    out.append(t)
        return out

    def _build_preview_tensor(self, names: List[str]):
        try:
            import numpy as np
            import torch
            from PIL import Image
        except ImportError as e:
            print(f"[anima_t8] gelbooru preview 依赖缺失: {e}")
            import torch
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        if not names:
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        seen = set()
        uniq_names = []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq_names.append(n)
        if len(uniq_names) > 16:
            print(f"[anima_t8] gelbooru preview limit 16/{len(uniq_names)}")
            uniq_names = uniq_names[:16]

        results: List[Optional[Image.Image]] = [None] * len(uniq_names)
        with ThreadPoolExecutor(max_workers=min(6, len(uniq_names))) as ex:
            fut_map = {ex.submit(_fetch_preview_pil, n): i for i, n in enumerate(uniq_names)}
            for fut in as_completed(fut_map):
                idx = fut_map[fut]
                try:
                    results[idx] = fut.result()
                except Exception as e:
                    print(f"[anima_t8] gelbooru preview thread fail: {e}")

        valid = [im for im in results if im is not None]
        if not valid:
            print("[anima_t8] no Gelbooru preview images fetched")
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

        arr_list = []
        for im in valid:
            try:
                src_w, src_h = im.size
                if src_w <= 0 or src_h <= 0:
                    continue
                scale = min(_PREVIEW_W / src_w, _PREVIEW_H / src_h)
                new_w = max(1, int(round(src_w * scale)))
                new_h = max(1, int(round(src_h * scale)))
                im_resized = im.resize((new_w, new_h), Image.LANCZOS)
                canvas = Image.new("RGB", (_PREVIEW_W, _PREVIEW_H), (0, 0, 0))
                canvas.paste(im_resized, ((_PREVIEW_W - new_w) // 2, (_PREVIEW_H - new_h) // 2))
                arr = np.array(canvas, dtype=np.float32) / 255.0
                if arr.ndim == 2:
                    arr = np.stack([arr, arr, arr], axis=-1)
                if arr.shape[-1] == 4:
                    arr = arr[..., :3]
                arr_list.append(arr)
            except Exception as e:
                print(f"[anima_t8] gelbooru preview convert fail: {e}")
        if not arr_list:
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        tensor = torch.from_numpy(np.stack(arr_list, axis=0))
        print(f"[anima_t8] gelbooru preview built {tensor.shape}")
        return tensor


NODE_CLASS_MAPPINGS = {"AnimaGelbooruStyleT8": AnimaGelbooruStyleT8}
NODE_DISPLAY_NAME_MAPPINGS = {"AnimaGelbooruStyleT8": "Anima Gelbooru Style T8"}
