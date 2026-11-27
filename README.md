# ComfyUI-Prompt-Kit

专业级 Prompt 工作台与工具箱。第一阶段聚焦：**字典管理**、**词库/预设管理**、**结构化生成**。

当前版本：`0.6.0-dev`（Skill 资产/生成可试用；结构化 0.4 基线可用）

## 安装

放入 ComfyUI `custom_nodes` 后**完整重启**。无额外 Python 依赖。  
前端面板依赖 `web/*.js`，仅 F5 不够。

## 节点总览

搜索：`pk` / `promptkit` / `字典` / `词库` / `结构化` / `skill`

```text
PromptKit
├── 字典
│   ├── 选词    → 字典选词、字典面板
│   └── 管理    → 字典管理
├── 词库
│   ├── 选词    → 词库选词、词库面板
│   └── 管理    → 词库管理
├── 结构化
│   ├── 结构化生成     → 大节点（11 槽 + 可选 NSFW）
│   ├── 分模块/*       → 11 个 SFW 小节点
│   └── NSFW/*         → 5 个 NSFW 附加槽小节点
└── Skill
    ├── Skill 面板       → 管理 / 生成 / 导入导出 SKILL.md
    ├── 选 Skill         → 下拉输出正文 / 全文件 / 名称 / 路径
    └── 快速生成 Skill   → 素材模板生成（可选润色/写盘）
```

### 字典（阶段 2）

| 显示名 | 说明 |
|--------|------|
| **PromptKit · 字典选词** | 搜索 / 分类浏览 / 收藏 |
| **PromptKit · 字典管理** | 列出/收藏/添加词条 |
| **PromptKit · 字典面板** | 点选工作流入口 |

### 词库（阶段 3）

| 显示名 | 说明 |
|--------|------|
| **PromptKit · 词库选词** | 按库 / 分类 / 标签(AND) / 搜索 / 收藏取完整 prompt |
| **PromptKit · 词库管理** | 新建库、增删预设、收藏、设置标签 |
| **PromptKit · 词库面板** | Web 面板：库切换、标签筛选、多选应用 |

### Skill（0.6.0-dev）

| 显示名 | 说明 |
|--------|------|
| **PromptKit · Skill 面板** | 列表/搜索/收藏/编辑/导入导出/规则模板生成/Ollama 润色设置；输出正文或 name |
| **PromptKit · 选 Skill** | 下拉选取已有 Skill，输出正文 / 完整 SKILL.md / 名称 / 路径；支持下拉热更新 |
| **PromptKit · 快速生成 Skill** | 素材→模板（可选润色）→可选写盘；输出完整 SKILL.md / 正文 / 名称 |

数据：`data/skills/`（系统）+ `user_data/skills/`（用户）；格式为目录 + `SKILL.md`。  
兼容 Claude / Cursor / comfyUI-llama-TE 的开放 Skill 格式。词库与结构化面板支持「沉淀为 Skill」。

Skill API：

- `GET/POST /prompt-kit/skill/list|get|save|delete|favorite|generate|import|export|reload|settings`

### 结构化生成（阶段 4）

| 显示名 | 说明 |
|--------|------|
| **PromptKit · 结构化生成** | 大节点：多槽选词 → 中文 prompt；可开 NSFW |
| **PromptKit · {槽名}** | 分槽小节点：按分组「不选/随机/指定」多选合并；含「其它/未归组」兜底 |

要点：

- **独立精选词表**（`data/builder/`），不绑字典 14 类；预留挂字典口子
- **11 个 SFW 槽**：style / camera / subject / face / hair / expression / pose / clothing / accessories / scene / lighting
- **NSFW**：面板独立「显示 NSFW」；B 并入原槽 + C 五个附加槽（body / pose / act / props / fluids）
- **纯中文**输出；全局去重默认开；软单选（单击替换，Ctrl 追加）
- **实时预览**：面板调用 `POST /prompt-kit/builder/compose`
- 节点按钮「打开结构化面板」→ 选词 →「应用到节点」

API：

- `GET  /prompt-kit/builder/slots?nsfw=0|1`
- `GET  /prompt-kit/builder/slot/{id}?q=&group=&nsfw=`
- `POST /prompt-kit/builder/compose`
- `POST /prompt-kit/builder/reload`

## 数据目录

```text
data/dictionary/          系统字典（SFW）
data/dictionary_nsfw/     NSFW 字典（可插拔）
data/library/             系统词库 demo
data/builder/             结构化 SFW 精选（index + 11×jsonl）
data/builder_nsfw/        结构化 NSFW（overlay + 5 附加槽）
user_data/library/         用户/全量词库
user_data/builder/        用户覆盖结构化 SFW
user_data/builder_nsfw/   用户覆盖结构化 NSFW
user_data/favorites.json / library_favorites.json / skill_favorites.json / settings.json
data/skills/              系统 Skill 示例
user_data/skills/         用户 Skill
```

## 路线

| 阶段 | 状态 |
|------|------|
| 0 骨架 | ✅ |
| 1 字典数据 | ✅ |
| 2 字典管理 + 面板 | ✅ |
| 3 词库/预设 | ✅ 0.3.x |
| 4 结构化生成 | ✅ 0.4.x 可试用 |
| 5 Skill 资产/生成 | ✅ 0.6.0-dev 可试用 |

## 许可

待定。
