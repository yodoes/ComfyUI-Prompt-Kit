# ComfyUI-Prompt-Kit

专业级 Prompt 工作台与工具箱。第一阶段聚焦：**字典管理**、**词库/预设管理**、**结构化生成**。

当前版本：`0.2.0-dev`（阶段 2：字典管理功能可用）

## 目录结构

```text
ComfyUI-Prompt-Kit/
├── __init__.py                 # 插件入口
├── core/                       # 核心工具（路径、IO、设置、字典服务）
├── nodes/                      # ComfyUI 节点（按大功能域分子目录）
│   ├── dictionary/             # 字典管理域 ✅
│   ├── library/                # 词库 / 预设管理域
│   └── builder/                # 结构化生成域
├── web/                        # 前端资源（预留）
├── data/                       # 插件自带基础数据（只读）
│   ├── dictionary/             # 字典：按分类树拆分的 jsonl + index.json
│   └── library/                # 系统示例词库
├── user_data/                  # 用户数据（不入库，可手动编辑）
│   ├── dictionary/             # 用户自定义词条（按中类 jsonl）
│   ├── library/
│   ├── settings.json
│   └── favorites.json
├── docs/                       # 方案与设计文档
└── 原始未整理数据/              # 原始语料（已 gitignore）
```

## 安装

将本仓库放入 ComfyUI 的 `custom_nodes` 目录，重启 ComfyUI 即可。

```bash
cd ComfyUI/custom_nodes
git clone <本仓库地址> ComfyUI-Prompt-Kit
```

无需额外 Python 依赖（纯标准库）。

## 已实现节点（阶段 2）

分类：`PromptKit/字典`

| 节点显示名 | 类名 | 说明 |
|-----------|------|------|
| PromptKit · 字典搜索 | PromptKitDictionarySearch | 关键词 + 大类 + 标签搜索，输出拼接 prompt |
| PromptKit · 字典浏览 | PromptKitDictionaryBrowse | 按中类分页浏览，支持序号多选输出 |
| PromptKit · 收藏管理 | PromptKitDictionaryFavorite | list / add / remove / toggle 收藏 |
| PromptKit · 添加词条 | PromptKitDictionaryAdd | 向指定中类写入用户词条 |

核心服务：`core.dictionary_service`（按中类懒加载、合并 user_data、默认不加载 14 待分类素材池）。

## 用户数据

- 路径：`ComfyUI-Prompt-Kit/user_data/`
- 自定义词条：写入 `user_data/dictionary/<subcategory_id>.jsonl`（也可通过「添加词条」节点）
- 收藏：`user_data/favorites.json`
- 设置：`user_data/settings.json`（首次运行自动生成）
- 该目录已加入 `.gitignore`，升级插件不会覆盖你的数据

## 功能路线

| 功能域 | 节点目录 | 状态 |
|--------|----------|------|
| 字典管理 | `nodes/dictionary/` | ✅ 阶段 2：浏览 / 搜索 / 收藏 / 添加 |
| 词库/预设管理 | `nodes/library/` | ⏳ 阶段 3 |
| 结构化生成 | `nodes/builder/` | ⏳ 阶段 4 |

详细方案见：`docs/第一阶段方案与开发计划_v1.0.docx`  
阶段 1 收口：`docs/阶段1收口记录与后续计划_v1.0.docx`

## 开发说明

- 路径统一通过 `core.paths.paths` 获取
- JSON/JSONL 读写使用 `core.io_utils`
- 用户设置使用 `core.settings.settings`
- 字典服务使用 `core.dictionary_service.dictionary_service`
- 字典分类树定义在 `data/dictionary/index.json`
- 节点按大功能域放在 `nodes/<domain>/`，在各自 `__init__.py` 中填充 `NODE_CLASS_MAPPINGS`，由 `nodes/__init__.py` 汇总
- 节点显示名统一前缀：`PromptKit · …`

## 许可

待定。
