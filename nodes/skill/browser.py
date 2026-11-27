"""
Skill 节点：面板入口 + 选 Skill + 快速生成。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, List, Tuple

try:
    from ...core.skill_service import dump_skill_md, skill_service
except ImportError:
    from core.skill_service import dump_skill_md, skill_service


def _skill_choices() -> List[str]:
    try:
        rows = skill_service.list_skills()
    except Exception:
        rows = []
    names = [r.get("name") or "" for r in rows if r.get("name")]
    if not names:
        return ["(无 Skill)"]
    return names


def _ollama_model_choices() -> List[str]:
    """启动时尝试拉一次 Ollama 模型；失败则占位，前端可再刷新。"""
    try:
        from ...core.settings import settings
    except ImportError:
        try:
            from core.settings import settings
        except Exception:
            settings = None
    base = "http://127.0.0.1:11434"
    if settings is not None:
        try:
            base = str(settings.get("skill_ollama_base_url") or base).rstrip("/")
        except Exception:
            pass
    try:
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = []
        for m in data.get("models") or []:
            name = (m.get("name") or m.get("model") or "").strip()
            if name and name not in models:
                models.append(name)
        models.sort(key=str.casefold)
        if models:
            return models
    except Exception:
        pass
    return ["(未检测到模型-可手改或开润色后刷新)"]


_KIND_MAP = {
    "从说明/提示词": "from_prompt",
    "从词库素材": "from_library",
    "从结构化素材": "from_builder",
    "from_prompt": "from_prompt",
    "from_library": "from_library",
    "from_builder": "from_builder",
}


class PromptKitSkillPanel:
    """打开 Skill 面板：管理 / 预览 / 生成 Skill；可将正文写入本节点。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "面板文本": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "由「打开 Skill 面板」写入：Skill 正文或导出用名称",
                    },
                ),
            },
            "optional": {
                "Skill名称": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "当前选中的 Skill name（面板写入）",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("文本", "Skill名称")
    FUNCTION = "run"
    CATEGORY = "PromptKit/Skill"
    SEARCH_ALIASES = ["pk", "promptkit", "skill", "技能", "Skill面板"]
    DESCRIPTION = "Skill 面板入口：管理与生成 SKILL.md，输出正文或名称。"

    def run(self, **kwargs: Any) -> Tuple[str, str]:
        panel_text = kwargs.get("面板文本")
        if panel_text is None:
            panel_text = kwargs.get("panel_text", "")
        skill_name = kwargs.get("Skill名称")
        if skill_name is None:
            skill_name = kwargs.get("skill_name", "")
        return ((panel_text or "").strip(), (skill_name or "").strip())


class PromptKitSkillPick:
    """从已安装 Skill 中选取并输出正文 / 全文件 / 名称 / 路径。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Skill": (
                    _skill_choices(),
                    {"tooltip": "选择 Skill；新增后可用「刷新 Skill 列表」热更新"},
                ),
                "输出内容": (
                    ["正文", "完整SKILL.md", "名称", "路径"],
                    {
                        "default": "正文",
                        "tooltip": "正文=Markdown body；完整=含 frontmatter；名称/路径便于对接其它节点",
                    },
                ),
            },
            "optional": {
                "面板文本": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "由 Skill 面板写入时优先使用（非空则覆盖下拉选择的正文输出）",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("文本", "Skill名称", "路径")
    FUNCTION = "run"
    CATEGORY = "PromptKit/Skill"
    SEARCH_ALIASES = ["pk", "promptkit", "skill", "选skill", "技能"]
    DESCRIPTION = "选取已有 Skill，输出正文、完整 SKILL.md、名称或路径字符串。"

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> float:
        return 0

    def run(self, **kwargs: Any) -> Tuple[str, str, str]:
        name = kwargs.get("Skill") if "Skill" in kwargs else kwargs.get("skill", "")
        mode = kwargs.get("输出内容") if "输出内容" in kwargs else kwargs.get("output_mode", "正文")
        panel_text = kwargs.get("面板文本")
        if panel_text is None:
            panel_text = kwargs.get("panel_text", "")
        panel_text = (panel_text or "").strip()

        name = (name or "").strip()
        if not name or name.startswith("("):
            return (panel_text, "", "")

        try:
            skill = skill_service.get_skill(name)
        except Exception as e:
            return (f"[Skill 读取失败] {e}", name, "")

        if not skill:
            return (f"[未找到 Skill] {name}", name, "")

        path = str(skill.get("path") or "")
        body = (skill.get("body") or "").strip()
        raw = (skill.get("raw") or "").strip()

        if panel_text:
            return (panel_text, name, path)

        if mode in ("名称", "name"):
            text = name
        elif mode in ("路径", "path"):
            text = path
        elif mode in ("完整SKILL.md", "完整", "raw"):
            text = raw or body
        else:
            text = body or raw

        return (text, name, path)


class PromptKitSkillQuickGenerate:
    """
    快速生成 Skill：素材 → 规则模板（可选 Ollama 润色）→ 可选写盘。
    润色开关独立，默认关；开时使用节点上的模型下拉。
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "素材正文": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "提示词 / 预设 / 组词结果；可接上游",
                    },
                ),
                "中文标题": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "正文一级标题；空则截取素材前 20 字",
                    },
                ),
                "类型": (
                    ["从说明/提示词", "从词库素材", "从结构化素材"],
                    {
                        "default": "从说明/提示词",
                        "tooltip": "对应模板：from_prompt / from_library / from_builder",
                    },
                ),
                "输出模式": (
                    ["完整SKILL.md", "仅正文", "仅名称"],
                    {
                        "default": "完整SKILL.md",
                        "tooltip": "决定「文本」输出端口内容",
                    },
                ),
                "Ollama润色": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "默认关；开启后使用下方模型做润色（失败仍返回模板版）",
                    },
                ),
                "写入磁盘": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "是否保存到 user_data/skills/",
                    },
                ),
            },
            "optional": {
                "名称name": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "kebab-case；空则自动生成",
                    },
                ),
                "description": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "空则模板自动补英文触发语",
                    },
                ),
                "标签": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "逗号分隔",
                    },
                ),
                "Ollama模型": (
                    _ollama_model_choices(),
                    {
                        "tooltip": "仅当「Ollama润色」开启时使用；列表来自本机 Ollama",
                    },
                ),
                "覆盖已存在": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "写入磁盘且同名已存在时是否覆盖",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("文本", "Skill名称", "结果", "路径")
    FUNCTION = "run"
    CATEGORY = "PromptKit/Skill"
    SEARCH_ALIASES = [
        "pk",
        "promptkit",
        "skill",
        "生成skill",
        "快速生成",
        "技能",
    ]
    DESCRIPTION = "从素材快速生成 Skill（规则模板 + 可选 Ollama 润色），可写入磁盘。"

    def run(self, **kwargs: Any) -> Tuple[str, str, str, str]:
        source = kwargs.get("素材正文")
        if source is None:
            source = kwargs.get("source_text", "")
        source = (source or "").strip()

        title_zh = kwargs.get("中文标题")
        if title_zh is None:
            title_zh = kwargs.get("title_zh", "")
        title_zh = (title_zh or "").strip()
        if not title_zh and source:
            title_zh = source[:20] + ("…" if len(source) > 20 else "")
        if not title_zh:
            title_zh = "未命名 Skill"

        kind_label = kwargs.get("类型") if "类型" in kwargs else kwargs.get("kind", "从说明/提示词")
        kind = _KIND_MAP.get(str(kind_label or "").strip(), "from_prompt")

        out_mode = kwargs.get("输出模式") if "输出模式" in kwargs else kwargs.get("output_mode", "完整SKILL.md")
        polish = bool(kwargs.get("Ollama润色") if "Ollama润色" in kwargs else kwargs.get("polish", False))
        save = bool(kwargs.get("写入磁盘") if "写入磁盘" in kwargs else kwargs.get("save", False))
        overwrite = bool(kwargs.get("覆盖已存在") if "覆盖已存在" in kwargs else kwargs.get("overwrite", False))

        name = kwargs.get("名称name")
        if name is None:
            name = kwargs.get("name", "")
        name = (name or "").strip()

        description = kwargs.get("description")
        if description is None:
            description = ""
        description = (description or "").strip()

        tags_raw = kwargs.get("标签")
        if tags_raw is None:
            tags_raw = kwargs.get("tags", "")
        tags = [t.strip() for t in str(tags_raw or "").replace("，", ",").split(",") if t.strip()]

        model = kwargs.get("Ollama模型")
        if model is None:
            model = kwargs.get("ollama_model", "")
        model = str(model or "").strip()
        if model.startswith("("):
            model = ""

        if not source and not description:
            return ("", "", "素材正文为空，未生成", "")

        fields = {
            "name": name,
            "title_zh": title_zh,
            "description": description,
            "source_text": source,
            "tags": tags,
        }

        try:
            meta, body = skill_service.render_template(kind, fields)
        except Exception as e:
            return ("", name or "", f"模板生成失败：{e}", "")

        result_bits: List[str] = ["已生成模板"]
        if polish:
            if not model:
                result_bits.append("润色跳过（未选有效模型）")
            else:
                meta, body, warn = skill_service.polish_with_ollama(
                    meta, body, model=model
                )
                if warn:
                    result_bits.append(f"润色未成功：{warn}")
                else:
                    result_bits.append(f"已润色（{model}）")

        skill_name = str(meta.get("name") or name or "").strip()
        raw = dump_skill_md(meta, body)

        path = ""
        if save:
            try:
                skill = skill_service.create_skill(
                    skill_name,
                    meta.get("description") or "",
                    body,
                    tags=tags or meta.get("tags"),
                    display_name_zh=title_zh,
                    overwrite=overwrite,
                )
                skill_name = skill.get("name") or skill_name
                path = str(skill.get("path") or "")
                raw = skill.get("raw") or dump_skill_md(
                    {
                        "name": skill_name,
                        "description": skill.get("description") or meta.get("description") or "",
                        "tags": skill.get("tags") or tags,
                    },
                    skill.get("body") or body,
                )
                result_bits.append(f"已写入 {skill_name}")
            except Exception as e:
                result_bits.append(f"写入失败：{e}")

        if out_mode in ("仅名称", "名称", "name"):
            text = skill_name
        elif out_mode in ("仅正文", "正文", "body"):
            text = (body or "").strip()
        else:
            text = raw

        return (text, skill_name, "；".join(result_bits), path)


NODE_CLASS_MAPPINGS = {
    "PromptKitSkillPanel": PromptKitSkillPanel,
    "PromptKitSkillPick": PromptKitSkillPick,
    "PromptKitSkillQuickGenerate": PromptKitSkillQuickGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PromptKitSkillPanel": "PromptKit · Skill 面板",
    "PromptKitSkillPick": "PromptKit · 选 Skill",
    "PromptKitSkillQuickGenerate": "PromptKit · 快速生成 Skill",
}
