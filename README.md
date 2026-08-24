# 贞贞网站：[https://ai.t8star.org](https://ai.t8star.org/register?aff=dP7j)
# 致谢企鹅的云端画布：[https://art.pebbling.cn](https://art.pebbling.cn/?invite=T8STAR)
# Online workflow overseas：
https://www.runninghub.ai/?inviteCode=rh-v1121
# 在线工作流国内版：
https://www.runninghub.cn/?inviteCode=rh-v1121
# 👋🏻 Welcome to Zhenzhen

<img src="https://github.com/T8mars/Comfyui-zhenzhen/blob/main/pic/1.png" width="30%" alt="My favorite girl">
My favorite girl Go YounJung

# comfyui-anima-t8

[中文](README.md) | [English](README_EN.md)

> Anima 动漫提示词生成器 · ComfyUI 自定义节点
>
> 风格库三段式（52 条预设 / 15 分类）+ 1000+ 画师库 + Danbooru/Gelbooru 标签库 + Civitai 一键抓取 + 实时风格预览图

[![version](https://img.shields.io/badge/version-1.5.2-blue.svg)]()
[![ComfyUI](https://img.shields.io/badge/ComfyUI-custom_node-green.svg)](https://github.com/comfyanonymous/ComfyUI)
[![license](https://img.shields.io/badge/license-MIT-lightgrey.svg)]()

---

## ✨ 简介

**comfyui-anima-t8** 是为 [Anima 动漫文生图模型](https://huggingface.co/circlestone-labs/Anima) 设计的 ComfyUI 提示词工作站，把"风格库 + 画师库 + IP 库"完整搬进 ComfyUI 主面板，让你无需离开画布就能完成提示词组装。

**核心特色**：

- 📚 **风格库 52 条 Pony 兼容预设 × 15 分类**：画质 / 媒介 / 镜头 / 构图 / 光影 / 服装 / 表情 / 季节 / 时代 / 场景 / 风格 / 情绪 / 角色 / NSFW / 测试，开箱即用
- 🌐 **一键 Civitai 抓取**：输入模型 ID 自动拉高赞图 prompt，按 14 组关键词自动归类（兼容 Civitai 直 prompt / 嵌套 / ComfyUI workflow 三种 meta 结构）
- 🎨 **5 个素材库 Tab 一键切换**：mooshieblob 画师 + Danbooru 画师 / 作品 IP / 角色 IP / 风格·meta
- 🌐 **Gelbooru 标签库**：独立画师 / 作品 IP / 角色 IP / 通用标签面板，支持搜索、收藏、权重和预览图
- 🖼️ **实时风格预览图**：选画师后运行节点即可在 PreviewImage 看到代表作首图
- 🚀 **本地缓存 + 并发拉取**：首次切 Tab 仅 2~5 秒可用，后台异步补全 30000+ 标签
- 🧬 **增量种子机制**：升级版本会按 name / title 增量补入新预设，**不覆盖**用户已编辑的内容
- 📌 **Pin 收藏 / 仅固定 / A-Z 字母筛选 / 关键字搜索** 一应俱全
- 🛡️ **图片代理**：所有 Danbooru CDN 图片走后端同源代理，绕开浏览器防盗链/CSP

---

## 📦 节点清单

| 节点 | 说明 | 主要输入 | 输出 |
|---|---|---|---|
| **Anima Prompt T8** | 三段式提示词组装（正向 / 负向 / 风格） | positive / negative / style | POSITIVE / NEGATIVE |
| **Anima Artist Style T8** | 画师风格输出 + 实时预览 | artist_tags（多选）/ default_weight / use_artist_prefix | STYLE_PROMPT / **PREVIEW_IMAGES** |
| **Anima Gelbooru Style T8** | Gelbooru 标签输出 + 实时预览 | gelbooru_tags（多选）/ default_weight / use_artist_prefix | STYLE_PROMPT / **PREVIEW_IMAGES** |
| **Anima Prompt Combiner T8** | 把多段提示词合并为单段 | text_a / text_b / separator | COMBINED |
| **Anima Saved Prompt Loader T8** | 从风格库一键加载已保存提示词 | preset_id | POSITIVE / NEGATIVE / STYLE |

---

## 🚀 安装

### 方式 1：手动 clone

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/T8mars/comfyui-anima-t8
cd comfyui-anima-t8
pip install -r requirements.txt
```

### 方式 2：通过 ComfyUI Manager

在 ComfyUI Manager 搜索 `comfyui-anima-t8` 后一键安装。

### 依赖

- Python ≥ 3.10
- ComfyUI 主分支（任意近期版本）
- `Pillow` / `numpy` / `torch`（ComfyUI 自带，无需额外）
- `requests`（已写入 `requirements.txt`）

---

## 🎯 使用流程

### 1. 拖入节点

在 ComfyUI 画布右键 → `Add Node` → `Anima/T8` → 选择需要的节点。

### 2. 打开素材库

每个 Anima 节点上方都有按钮：

- **📚 风格库**：浏览/搜索/收藏已保存的三段式提示词，支持 📥 导入 / 📤 导出 / 🌐 Civitai 抓取
- **🎨 艺术家 / IP 库**：5 个 Tab 切换
  - 👤 **Danbooru 画师** —— 30000+ Danbooru 真实标注画师标签
  - 📚 **作品 IP** —— 5000+ 动画/游戏/漫画作品名
  - 🧑‍🎤 **角色 IP** —— 30000+ 角色名
  - 🎭 **风格·meta** —— Danbooru meta tag（画风 / 媒介 / 题材描述）
  - 🎨 **画师库·mooshieblob** —— 1000+ 精选画师 + 高质量预览图
- **🌐 Gelbooru 标签库**：4 个 Tab 切换
  - 👤 **Gelbooru 画师**
  - 📚 **Gelbooru 作品 IP**
  - 🧑‍🎤 **Gelbooru 角色 IP**
  - 🏷 **Gelbooru 通用标签**

### 3. 选择 → 添加

- 在卡片上点击 → 进入选中状态
- 点击右上角"➜ 添加 N 个" → 自动写入对应节点的 widget
  - 画师类 → 写入 `artist_tags` widget（[Anima Artist Style T8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py)）或 `style` widget（Anima Prompt T8）
  - 作品 / 角色 IP → 写入 `positive` widget

### 4. 运行查看预览

把 [Anima Artist Style T8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py) 的 `PREVIEW_IMAGES` 端口连到 `PreviewImage` 节点，运行后会自动从 Danbooru 拉每个画师的代表作首图（≤16 张，6 路并发，约 2~5 秒）。

> **小提示**：`PREVIEW_IMAGES` 仅展示"本次选中"的画师；`STYLE_PROMPT` 始终拼接 textarea 全部画师。如需预览全部，清空 `last_picked` widget 即可。

### 5. 一键 Civitai 抓取（v1.2 新增）

在风格库面板点 **🌐 Civitai** 按钮 → 输入目标模型 ID（例如 `2458426`）→ 系统会：

1. 调 Civitai images API 拉该模型 Most Reactions × Month 的高赞图（默认 100 张，1 页）
2. 自动从每张图的 meta 中提取 prompt（兼容直 prompt / 嵌套 meta / ComfyUI workflow 三种结构）
3. 按 prompt 内容自动归类到 14 个分类（每条最多 3 个 tag）
4. 按 reactions 倒序，取 top 30 增量写入风格库（标题 `Civitai-{modelId} #{imageId}`，按 title 去重）

---

## ⚙️ 数据来源

| 来源 | 用途 |
|---|---|
| [Danbooru](https://danbooru.donmai.us) | 画师 / 作品 IP / 角色 IP / 风格·meta 标签库 + 预览图首图 |
| [Gelbooru](https://gelbooru.com) | 画师 / 作品 IP / 角色 IP / 通用标签库 + 预览图首图 |
| [mooshieblob Anima Artist Gallery](https://anima.mooshieblob.com) | 1000+ 精选画师 + 高质量风格预览图 |
| [Civitai](https://civitai.com) | 按模型 ID 抓取高赞图 prompt（公开 API，免 token） |

所有数据按需缓存到本地 SQLite (`comfyui-anima-t8/data/anima_t8.sqlite`)，首次拉取后即离线可用。

---

## 🔌 HTTP 路由

节点会自动注册以下路由到 ComfyUI 服务器：

| 路径 | 说明 |
|---|---|
| `GET /anima_t8/prompts` | 列出已保存的提示词预设 |
| `GET /anima_t8/artists` | mooshieblob 画师列表 |
| `GET /anima_t8/dtags?category=artist\|copyright\|character\|meta` | Danbooru 四类标签（v1.2 加 meta） |
| `GET /anima_t8/dtags/preview?name=xxx` | 拉取某 tag 的代表作首图 URL（带本地 LRU 4096 缓存） |
| `GET /anima_t8/dtags/image?u=xxx` | **同源图片代理**（白名单 cdn.donmai.us / danbooru.donmai.us） |
| `POST /anima_t8/dtags/refresh` | 强制刷新某 category 的标签库 |
| `GET /anima_t8/gtags?category=artist\|copyright\|character\|general` | Gelbooru 四类标签 |
| `GET /anima_t8/gtags/preview?name=xxx` | 拉取 Gelbooru tag 的代表作首图 URL |
| `GET /anima_t8/gtags/image?u=xxx` | Gelbooru 同源图片代理 |
| `POST /anima_t8/gtags/refresh` | 强制刷新某 Gelbooru category 的标签库 |
| `POST /anima_t8/artists/pin` | Pin / 取消 Pin 一个画师 |
| `POST /anima_t8/civitai/refresh` | **v1.2** 按 model_id 抓取 Civitai 高赞图 prompt 并写入风格库 |

---

## 🗂️ 项目结构

```
comfyui-anima-t8/
├── __init__.py              # ComfyUI 节点注册入口
├── pyproject.toml           # 包元数据（v1.0.0）
├── requirements.txt         # Python 依赖
├── api/
│   ├── danbooru_client.py   # Danbooru 标签拉取（4 路并发, 4 类: artist/copyright/character/meta）
│   ├── gelbooru_client.py   # Gelbooru 标签 / 预览图拉取（含 autocomplete / HTML fallback）
│   └── civitai_client.py    # v1.2 Civitai images API 客户端 + ComfyUI workflow 解析 + 自动归类
├── core/
│   ├── db.py                # SQLite 自愈连接
│   ├── artist_manager.py    # mooshieblob 画师管理
│   ├── danbooru_manager.py  # Danbooru 标签管理 + 预览图代理
│   ├── gelbooru_manager.py  # Gelbooru 标签管理 + 预览图代理
│   ├── tag_manager.py       # 风格库分类标签（增量种子）
│   └── prompt_manager.py    # 风格库 prompt 预设（增量种子，按 title 去重）
├── nodes/
│   ├── anima_prompt_node.py
│   ├── anima_artist_node.py # Anima Artist Style T8（含 PREVIEW_IMAGES 输出）
│   ├── gelbooru_style_node.py # Anima Gelbooru Style T8（含 PREVIEW_IMAGES 输出）
│   ├── anima_combiner_node.py
│   └── anima_loader_node.py
├── server/
│   └── routes.py            # aiohttp 路由（含图片代理 + 后台补全）
└── web/                     # 前端注入到 ComfyUI 主面板
    ├── anima_t8.js          # 入口扩展
    ├── api.js               # 前端 API 封装
    ├── components/
    │   ├── prompt_panel.js  # 风格库面板
    │   ├── artist_gallery.js # 4 Tab 画师 / IP 画廊
    │   ├── gelbooru_gallery.js # Gelbooru 标签库面板
    │   └── tag_chip.js
    └── styles/
        └── anima_t8.css
```

---

## 🧠 设计要点

### 首屏快速 + 后台补全

切到 Danbooru 任一 Tab 时：

1. 后端先拉前 2 页（~2000 条）立即返回，前端 2~5 秒可用
2. 同时启动后台 `fetch(force_refresh=True, max_pages=30)` 4 路并发补全
3. 响应附带 `backfilling: true` 标记 → 前端显示"· 后台补全中…"，并在 8s 后自动重拉
4. 第二次进入相同 Tab → 直接从 SQLite 秒开

### 浏览器兼容的图片代理

直连 `cdn.donmai.us` 在某些网络/扩展环境下会被拦截（防盗链 / CSP / 本地拦截器），所有 Danbooru 图片统一走 `/anima_t8/dtags/image?u=...` 后端同源代理：

- SSRF 防护：仅允许 `cdn.donmai.us` / `danbooru.donmai.us`
- Referer 头：`https://danbooru.donmai.us/` 绕过防盗链
- HTTP 缓存：`Cache-Control: public, max-age=86400`

### "本次选中"语义

[Anima Artist Style T8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py) 的 `artist_tags` 是累积式 textarea（保留历史选择），但 `PREVIEW_IMAGES` 应该只反映本次操作。解决方案：

- 新增隐藏 `last_picked` widget，每次"添加选中"前端覆盖式写入
- 节点 `build()` 优先用 `last_picked`，为空才退回 `artist_tags` 全部

---

## 📝 版本历史

### v1.5.2 (2026-08)
- 📚 **新增英文 README**：保留中文 `README.md` 作为默认入口，新增 `README_EN.md`，并在两个文档顶部加入语言切换链接。

### v1.5.1 (2026-08)
- 🛡️ **外部请求重试增强**：Danbooru / Gelbooru / Civitai / 预览图代理等只读网络请求增加 direct / proxy 多路线重试，缓解临时 429、502、503、504、TLS EOF 和不完整响应导致的失败。

### v1.5.0 (2026-08)
- ✨ **新增 Gelbooru 独立节点与标签库**：`Anima Gelbooru Style T8` + Gelbooru 画师 / 作品 IP / 角色 IP / 通用标签面板
- 🔌 **新增 Gelbooru 路由**：`/anima_t8/gtags*` 独立于现有 Danbooru `/dtags*`
- 🛡 **Gelbooru 401 fallback**：正式 DAPI 无 key 返回 401 时，标签搜索走公开 autocomplete2，预览图走公开 HTML 缩略图兜底
- 📦 **Comfy Registry 发布准备**：补齐 PublisherId、GitHub Action 和 `.comfyignore`

### v1.4.3 (2026-05)
- 🎨 **STYLE_PROMPT 合并 `last_picked` 额外 token**：`last_picked` 里不在 `artist_tags` 中的裸 token（作品 IP / 角色 IP / 风格·meta 等）以裸名追加输出，以 `, ` 连接。例：`artist_tags=@dairi, @ebifurya` + `last_picked=dairi, ebifurya, original` → `@dairi, @ebifurya, original`（画师去重，额外 meta 追加）

### v1.4.2 (2026-05)
- 🎨 **STYLE_PROMPT 输出格式修正**：原不论画师还是 IP/角色/meta 全部输出为 `(artist:xxx)`；改为按 `@` 标记区分：画师输出 `@name` / `(@name:weight)`，其他裸 `name` / `(name:weight)`。`use_artist_prefix` 语义重定义为“是否保留画师 `@` 前缀”
- 🐛 **修复名字里右括号被误删**：原 `name.rstrip(")")` 会把合法名字中的尾部 `)` 吃掉（如 `kouji_(campus_life)` 变 `kouji_(campus_life`）；改为仅在左右括号不平衡时才逐个剔除

### v1.4.1 (2026-05)
- 🐛 **修复 `last_picked` widget 被覆盖问题**：原 `appendArtistsToWidget` / `setLastPickedRaw` 是覆盖式写入，每次选新 token 都会清空之前的列表；改为累加去重（`a, b` + `b, c` → `a, b, c`），与上面 `artist_tags` widget 行为保持一致
- ♻️ **抽出 helper `_stripToRawName` / `_appendLastPicked`**：去重复的 token 归一化逻辑（括号 / `@` / `artist:` / `:weight` 剥离）集中到一处，避免两处维护不同步

### v1.4.0 (2026-05)
- 🐛 **修复预览图黑屏（last_picked 带 `@` 前缀）**：前端 `appendArtistsToWidget` 写 `last_picked` 时剥离 `@` / 括号 / `artist:` / `:weight`；后端新增 `_strip_name_for_query` 工具，`_parse_names` + `build()` 同步剥离 `@` 作双保险，避免 Danbooru 查询返回 0 结果触发 64×64 黑图兜底
- 🐛 **修复 [AnimaArtistStyleT8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py) 节点上 IP/角色/风格·meta 运行无反应**：原逻辑遇到非画师类直接 toast 拒绝；改为写入 `last_picked`（用于 PREVIEW_IMAGES 拉 Danbooru 代表作首图，不污染 `STYLE_PROMPT`）+ 同步追加到画布 [AnimaPromptT8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_prompt_node.py) 的 `positive` widget；新增 helper `setLastPickedRaw`
- 🎨 **预览图改为等比缩放 + 居中黑边填充（letterbox）**：替换原 `im.resize((512, 768))` 强制拉伸；用 `min(512/w, 768/h)` 算缩放比例后 `Image.LANCZOS` 缩放，再 paste 到 (512, 768) 黑底画布居中位置；保持 ComfyUI batch tensor 形状一致，画面不再变形
- 🛠 **Civitai 拉取 0 条修复**：兼容 2026 年新 meta 结构变体（直 `meta.prompt` / 嵌套 `meta.meta` / ComfyUI workflow JSON）；新增 `_extract_from_comfy_workflow`（按 `_meta.title` 区分 Positive/Negative，支持 `["nodeId", 0]` 引用追溯最深 4 层）；新增 `_extract_score`（reactionCount fallback heart+like+laugh+cry+comment）
- ✨ **Civitai 自动归类**：新增 `_auto_classify` + 14 组优先级关键词（画质 / 媒介 / 光影 / 镜头 / 构图 / 服装 / 表情 / 季节 / 时代 / 场景 / 风格 / 情绪 / 角色 / NSFW），每条模板按 prompt 内容自动打 ≤3 个分类 tag

### v1.3.0 (2026-05)
- 🔧 **风格库"应用"按字段映射 + 空字段保护**：模板某字段为空则不覆盖对应 widget，保护用户已选画师 / 已调节词；想强制清空可在模板里填一个空格
- 🔧 **艺术家库统一写入 STYLE widget**：画师 / 作品 IP / 角色 IP / 风格·meta 全部去重追加到 [Anima Prompt T8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_prompt_node.py) 的 `style` 字段（不再污染 `positive` 主体词框）；新增公用工具 `appendTokensToStyle`
- 🐛 **修复 PREVIEW_IMAGES 黑图**：v1.1 起 `last_picked` widget 写入了带 `@` 前缀的 token，后端 `_fetch_preview_pil` 拿 `@xxx` 查 Danbooru 永远 0 结果。前端写入时剥离 `@` / 括号 / `artist:` / `:weight`；后端 `_parse_names` + `build()` 同步剥离 `@` 作双保险
- 🐛 **修复风格库"应用"按钮无反应**：兼容新版 ComfyUI Frontend `selected_nodes` 三态（Object / Array / Map），加 try/catch + 明确 toast；为 [AnimaSavedPromptLoaderT8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_loader_node.py) 节点补 `onApply` fallback（自动写到画布上的 [AnimaPromptT8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_prompt_node.py)）
- 🧹 保留 `STYLE_PROMPT` 仍带 `@` 前缀（v1.1 行为不变）；保留 [AnimaArtistStyleT8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py) 节点的 `artist_tags` widget 专用路径

### v1.2.0 (2026-05)
- ✨ **风格库扩充 12 → 52 条预设**，全部 Pony 兼容（开头 `score_9, score_8_up, score_7_up`）
- ✨ **15 个分类**（新增：媒介 / 镜头 / 情绪 / 季节 / 时代）
- ✨ **🌐 Civitai 一键抓取**：按 model_id 拉高赞图 prompt，自动按关键词归类
  - 兼容 Civitai 三种 meta 结构（直 prompt / 嵌套 meta.meta / ComfyUI workflow）
  - 14 组关键词自动分类（画质 / 媒介 / 光影 / 镜头 / 构图 / 服装 / 表情 / 季节 / 时代 / 场景 / 风格 / 情绪 / 角色 / NSFW），每条最多 3 个 tag
- ✨ **🎭 风格·meta Tab**：新增 Danbooru meta category 拉取（CATEGORY_NAMES 加 5: meta）
- 🧬 **增量种子机制**：`ensure_default_tags` / `ensure_default_prompts` 改按 name / title 去重，升级版本不覆盖用户已编辑的预设
- 🔌 新路由 `POST /anima_t8/civitai/refresh`

### v1.1.0 (2026-05)
- 🔧 Anima Prompt T8 节点默认正向词追加 `score_9, score_8_up, score_7_up`
- 🔧 艺术家库写入画师统一加 `@` 前缀，避免与作品 / 角色 IP 混淆

### v1.0.0 (2026-05)
- ✨ 完整 4 Tab 素材库（mooshieblob + Danbooru 三类）
- ✨ [Anima Artist Style T8](file:///f:/AnimaForge/comfyui-anima-t8/nodes/anima_artist_node.py) 新增 `PREVIEW_IMAGES` 输出，运行节点即出风格图
- ✨ 后端图片代理 + 4 路并发标签拉取 + 首屏 2 页快速返回
- ✨ Pin 收藏 / A-Z 字母筛选 / 关键字搜索 / 仅固定模式
- 🛡️ SQLite 自愈机制（损坏自动重建）
- 🛡️ SSRF 白名单 + Referer 头绕开防盗链

---

## 🙏 致谢

- 数据来源：**[Danbooru](https://danbooru.donmai.us)** / **[mooshieblob Anima Artist Gallery](https://anima.mooshieblob.com)** / **[Civitai](https://civitai.com)**
- 模型：**[circlestone-labs/Anima](https://huggingface.co/circlestone-labs/Anima)**
- 平台：**[ComfyUI](https://github.com/comfyanonymous/ComfyUI)**

---

## 📜 License

MIT © 2026 T8mars
