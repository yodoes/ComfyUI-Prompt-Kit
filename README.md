# ComfyUI-Prompt-Kit

专业级 Prompt 工作台与工具箱。第一阶段聚焦：**字典管理**、**词库/预设管理**、**结构化生成**。

当前版本：`0.2.0-dev`（阶段 2 已收口；下一步阶段 3 词库/预设）

## 安装

放入 ComfyUI `custom_nodes` 后重启。无额外 Python 依赖。  
前端面板依赖 `web/dictionary_panel.js`，**需重启 ComfyUI** 才会加载。

## 阶段 2 节点

搜索关键词：`pk` / `PK` / `promptkit` / `字典`

分类路径：

```text
PromptKit
└── 字典
    ├── 选词    → 字典选词、字典面板
    └── 管理    → 字典管理
```

| 显示名 | 说明 |
|--------|------|
| **PromptKit · 字典选词** | 搜索 / 分类浏览 / 收藏；支持 `panel_text`（面板写入优先） |
| **PromptKit · 字典管理** | 列出/收藏/取消收藏/添加词条 |
| **PromptKit · 字典面板** | 点选工作流入口，输出面板勾选结果 |

三个节点上都有 **「打开字典面板」** 按钮。

### 字典 Web 面板

- 左侧：14 大类分类树（默认不含素材池）
- 中部：分页词条列表 + 搜索 + 收藏夹
- 右侧：已选列表 → **应用到节点** / 复制
- 后端 API：`/prompt-kit/tree|entries|search|favorites|entry`

## 用户数据

- `user_data/dictionary/` 自定义词条  
- `user_data/favorites.json` 收藏  
- `user_data/settings.json` 设置  

## 路线

| 阶段 | 状态 |
|------|------|
| 0 骨架 | ✅ |
| 1 字典数据 | ✅ 收口 |
| 2 字典管理 + 面板 | ✅ |
| 3 词库/预设（含 V2 式管理面板） | ⏳ |
| 4 结构化生成 | ⏳ |

## 许可

待定。
