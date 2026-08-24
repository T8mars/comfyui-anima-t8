# comfyui-anima-t8

[Chinese](README.md) | [English](README_EN.md)

> An Anima anime prompt workstation for ComfyUI custom nodes.
>
> Three-part prompt presets, artist libraries, Danbooru/Gelbooru tag galleries, Civitai prompt import, and live style preview images.

[![version](https://img.shields.io/badge/version-1.5.2-blue.svg)]()
[![ComfyUI](https://img.shields.io/badge/ComfyUI-custom_node-green.svg)](https://github.com/comfyanonymous/ComfyUI)
[![license](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

---

## Overview

**comfyui-anima-t8** is a ComfyUI prompt workstation designed for the [Anima anime text-to-image model](https://huggingface.co/circlestone-labs/Anima). It brings style presets, artist tags, copyright/character tags, Gelbooru tags, and Civitai prompt collection directly into the ComfyUI canvas.

## Features

- **52 Pony-compatible style presets across 15 categories**: quality, medium, camera, composition, lighting, outfit, expression, season, era, scene, style, mood, character, NSFW, and testing.
- **Civitai one-click prompt import**: fetch highly reacted image prompts by model ID and classify useful tokens automatically.
- **Multi-source artist and IP galleries**: mooshieblob artists plus Danbooru artist, copyright, character, and meta tags.
- **Gelbooru tag gallery**: separate artist, copyright, character, and general-tag panels with search, pinning, weights, and preview images.
- **Live preview images**: connect the preview output to `PreviewImage` to see representative artwork for selected tags.
- **Local SQLite cache and background backfill**: quick first-page results with asynchronous tag completion.
- **Non-destructive preset seeding**: upgrades add new built-in presets by name/title without overwriting user-edited presets.
- **Pin, pinned-only filter, A-Z filter, and keyword search** across galleries.
- **Same-origin image proxy** for Danbooru/Gelbooru previews to avoid browser hotlink/CSP issues.
- **External request retry hardening** for read-only Danbooru, Gelbooru, Civitai, and preview-image requests.

## Nodes

| Node | Purpose | Main Inputs | Outputs |
|---|---|---|---|
| **Anima Prompt T8** | Assemble positive, negative, and style prompt sections | `positive`, `negative`, `style` | `POSITIVE`, `NEGATIVE` |
| **Anima Artist Style T8** | Build artist-style prompts and preview selected tags | `artist_tags`, `default_weight`, `use_artist_prefix` | `STYLE_PROMPT`, `PREVIEW_IMAGES` |
| **Anima Gelbooru Style T8** | Build Gelbooru tag prompts and preview selected tags | `gelbooru_tags`, `default_weight`, `use_artist_prefix` | `STYLE_PROMPT`, `PREVIEW_IMAGES` |
| **Anima Prompt Combiner T8** | Combine two prompt fragments | `text_a`, `text_b`, `separator` | `COMBINED` |
| **Anima Saved Prompt Loader T8** | Load a saved prompt preset | `preset_id` | `POSITIVE`, `NEGATIVE`, `STYLE` |

## Installation

### Manual install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/T8mars/comfyui-anima-t8
cd comfyui-anima-t8
pip install -r requirements.txt
```

### ComfyUI Manager

Search for `comfyui-anima-t8` in ComfyUI Manager and install it from there.

### Requirements

- Python 3.10 or newer
- A recent ComfyUI checkout
- `Pillow`, `numpy`, and `torch` from the ComfyUI environment
- `requests` from `requirements.txt`

## Usage

1. In the ComfyUI canvas, right-click and add nodes from `Anima/T8`.
2. Use the buttons above Anima nodes to open the preset library, artist/IP gallery, or Gelbooru tag gallery.
3. Select tags or presets, then apply them to the current node or prompt widgets.
4. Connect `PREVIEW_IMAGES` from `Anima Artist Style T8` or `Anima Gelbooru Style T8` to a `PreviewImage` node to inspect representative images.

Gallery tabs include:

- Danbooru artists
- Danbooru copyright tags
- Danbooru character tags
- Danbooru style/meta tags
- mooshieblob curated artists
- Gelbooru artists
- Gelbooru copyright tags
- Gelbooru character tags
- Gelbooru general tags

## Gelbooru Authentication

Gelbooru's DAPI may return `401 Unauthorized` without credentials. The node supports credentials from:

- Environment variables: `GELBOORU_USER_ID` and `GELBOORU_API_KEY`
- Local file: `data/gelbooru_auth.json`

Use `data/gelbooru_auth.example.json` as the shape reference. The real auth file is ignored by Git.

When credentials are not configured, the implementation falls back to public `autocomplete2` for tag search and public HTML scraping for preview thumbnails. This fallback is useful, but it is not a complete full-database pagination mode.

## Data Sources

| Source | Usage |
|---|---|
| [Danbooru](https://danbooru.donmai.us) | Artist, copyright, character, and meta tags plus representative preview images |
| [Gelbooru](https://gelbooru.com) | Artist, copyright, character, and general tags plus representative preview images |
| [mooshieblob Anima Artist Gallery](https://anima.mooshieblob.com) | Curated artist list with high-quality preview images |
| [Civitai](https://civitai.com) | Public image API for model prompt collection |

Data is cached locally in SQLite under `comfyui-anima-t8/data/`.

## HTTP Routes

The extension registers these routes on the ComfyUI server:

| Route | Description |
|---|---|
| `GET /anima_t8/prompts` | List saved prompt presets |
| `GET /anima_t8/artists` | List mooshieblob artists |
| `GET /anima_t8/dtags?category=artist\|copyright\|character\|meta` | List Danbooru tags |
| `GET /anima_t8/dtags/preview?name=xxx` | Fetch a Danbooru representative preview URL |
| `GET /anima_t8/dtags/image?u=xxx` | Same-origin Danbooru image proxy |
| `POST /anima_t8/dtags/refresh` | Force-refresh a Danbooru category |
| `GET /anima_t8/gtags?category=artist\|copyright\|character\|general` | List Gelbooru tags |
| `GET /anima_t8/gtags/preview?name=xxx` | Fetch a Gelbooru representative preview URL |
| `GET /anima_t8/gtags/image?u=xxx` | Same-origin Gelbooru image proxy |
| `POST /anima_t8/gtags/refresh` | Force-refresh a Gelbooru category |
| `POST /anima_t8/artists/pin` | Pin or unpin an artist/tag |
| `POST /anima_t8/civitai/refresh` | Fetch and import Civitai prompts by model ID |

## Project Layout

```text
comfyui-anima-t8/
├── __init__.py
├── pyproject.toml
├── requirements.txt
├── api/
│   ├── artist_client.py
│   ├── civitai_client.py
│   ├── danbooru_client.py
│   └── gelbooru_client.py
├── core/
│   ├── artist_manager.py
│   ├── danbooru_manager.py
│   ├── db.py
│   ├── gelbooru_manager.py
│   ├── prompt_manager.py
│   └── tag_manager.py
├── nodes/
│   ├── anima_artist_node.py
│   ├── anima_combiner_node.py
│   ├── anima_loader_node.py
│   ├── anima_prompt_node.py
│   └── gelbooru_style_node.py
├── server/
│   └── routes.py
└── web/
    ├── anima_t8.js
    ├── api.js
    ├── components/
    └── styles/
```

## Design Notes

### Fast First Page And Background Backfill

For large Danbooru/Gelbooru tabs, the backend returns an immediately useful initial page, then continues filling the local cache in the background. The frontend shows a background-fill state and refreshes after a short delay.

### Browser-Friendly Image Proxy

Preview images are proxied through same-origin ComfyUI routes with host allow-lists and cache headers. This avoids common browser issues with hotlink protection, local blockers, or CSP restrictions.

### Last Picked Semantics

Artist/tag text areas are cumulative, but preview images should reflect the latest explicit selection. Hidden `last_picked` widgets preserve that distinction.

## Changelog

### v1.5.2 (2026-08)

- Added this English README while keeping the Chinese `README.md` as the default GitHub entry point.
- Added language switch links to both README files.

### v1.5.1 (2026-08)

- Added retry hardening for read-only external Danbooru, Gelbooru, Civitai, and preview-image requests.

### v1.5.0 (2026-08)

- Added the independent `Anima Gelbooru Style T8` node and Gelbooru tag gallery.
- Added `/anima_t8/gtags*` routes.
- Added Gelbooru DAPI 401 fallbacks through autocomplete and HTML preview scraping.
- Prepared Comfy Registry publishing metadata and workflow.

## Credits

- Data: [Danbooru](https://danbooru.donmai.us), [Gelbooru](https://gelbooru.com), [mooshieblob Anima Artist Gallery](https://anima.mooshieblob.com), and [Civitai](https://civitai.com)
- Model: [circlestone-labs/Anima](https://huggingface.co/circlestone-labs/Anima)
- Platform: [ComfyUI](https://github.com/comfyanonymous/ComfyUI)

## License

MIT © 2026 T8mars
