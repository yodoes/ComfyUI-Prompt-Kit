"""
Skill 资产服务（0.5.0-dev）。

约定：
- 系统：data/skills/<name>/SKILL.md（只读）
- 用户：user_data/skills/<name>/SKILL.md（可写）
- 同名时用户覆盖系统（source=user-override）
- 收藏：user_data/skill_favorites.json
- 格式：开放 SKILL.md（YAML frontmatter name+description + Markdown 正文）
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .io_utils import read_json, write_json
from .paths import paths

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
SKILL_FILENAMES = ("SKILL.md", "SKILL.cn.md", "skill.md")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig") as f:
        return f.read()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")
    tmp.replace(path)


def parse_skill_md(text: str) -> Tuple[Dict[str, str], str]:
    """解析 SKILL.md → (frontmatter dict, body)。无 frontmatter 时 meta 为空。"""
    text = text or ""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    meta: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key:
            meta[key] = val
    body = (m.group(2) or "").strip()
    return meta, body


def dump_skill_md(meta: Dict[str, Any], body: str) -> str:
    """序列化为 SKILL.md 文本。"""
    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    lines = ["---", f"name: {name}", f"description: {description}"]
    tags = meta.get("tags")
    if tags:
        if isinstance(tags, list):
            tag_str = ", ".join(str(t).strip() for t in tags if str(t).strip())
        else:
            tag_str = str(tags).strip()
        if tag_str:
            lines.append(f"tags: {tag_str}")
    for k, v in meta.items():
        if k in ("name", "description", "tags"):
            continue
        if v is None or v == "":
            continue
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append((body or "").strip())
    lines.append("")
    return "\n".join(lines)


def validate_name(name: str) -> str:
    """规范化并校验 skill name；非法则抛 ValueError。"""
    raw = (name or "").strip().lower().replace("_", "-").replace(" ", "-")
    raw = re.sub(r"-+", "-", raw).strip("-")
    if not raw or not NAME_RE.match(raw):
        raise ValueError(
            f"无效 Skill 名称: {name!r}（需小写字母/数字/连字符，如 my-skill）"
        )
    if len(raw) > 64:
        raise ValueError("Skill 名称不能超过 64 字符")
    return raw


def _find_skill_file(skill_dir: Path) -> Optional[Path]:
    for fn in SKILL_FILENAMES:
        p = skill_dir / fn
        if p.is_file():
            return p
    # 目录内唯一 md/txt
    candidates = sorted(
        p
        for p in skill_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".md", ".txt")
    )
    if len(candidates) == 1:
        return candidates[0]
    return None


def _list_references(skill_dir: Path) -> List[str]:
    ref = skill_dir / "references"
    if not ref.is_dir():
        return []
    out: List[str] = []
    for p in sorted(ref.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".md", ".txt", ".yaml", ".yml", ".json"):
            out.append(p.relative_to(skill_dir).as_posix())
    return out


def _read_meta_yaml(skill_dir: Path) -> Dict[str, str]:
    path = skill_dir / "meta.yaml"
    if not path.is_file():
        return {}
    data: Dict[str, str] = {}
    for line in _read_text(path).splitlines():
        m = re.match(r"^([\w-]+):\s*(.+?)\s*$", line)
        if m:
            data[m.group(1)] = m.group(2).strip().strip("\"'")
    return data


class SkillService:
    def __init__(self) -> None:
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._favorites: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # favorites
    # ------------------------------------------------------------------

    def _load_favorites(self, force: bool = False) -> Dict[str, Any]:
        if self._favorites is not None and not force:
            return self._favorites
        data = read_json(paths.skill_favorites_file, default=None)
        if not isinstance(data, dict):
            data = {"version": 1, "favorites": []}
        data.setdefault("version", 1)
        data.setdefault("favorites", [])
        self._favorites = data
        return data

    def _save_favorites(self) -> bool:
        return write_json(paths.skill_favorites_file, self._load_favorites())

    def list_favorite_names(self) -> Set[str]:
        data = self._load_favorites()
        return {str(x).strip() for x in (data.get("favorites") or []) if str(x).strip()}

    def is_favorite(self, name: str) -> bool:
        try:
            name = validate_name(name)
        except ValueError:
            return False
        return name in self.list_favorite_names()

    def toggle_favorite(self, name: str) -> bool:
        name = validate_name(name)
        data = self._load_favorites()
        favs: List[str] = [str(x) for x in (data.get("favorites") or [])]
        if name in favs:
            favs = [x for x in favs if x != name]
            data["favorites"] = favs
            self._save_favorites()
            return False
        favs.append(name)
        data["favorites"] = favs
        self._save_favorites()
        return True

    # ------------------------------------------------------------------
    # discovery
    # ------------------------------------------------------------------

    def reload(self) -> None:
        self._cache = None
        self._favorites = None

    def _scan_root(self, root: Path, source: str) -> Dict[str, Dict[str, Any]]:
        """扫描一个 skills 根目录，返回 name -> entry。"""
        result: Dict[str, Dict[str, Any]] = {}
        if not root.is_dir():
            return result
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                # 单文件落在根上：自动视为 name=stem
                if child.is_file() and child.suffix.lower() in (".md", ".txt"):
                    try:
                        entry = self._entry_from_file(child, source=source, forced_name=None)
                        if entry:
                            result[entry["name"]] = entry
                    except Exception as e:
                        print(f"[Prompt-Kit] Skill 单文件跳过 {child}: {e}")
                continue
            if child.name.startswith(".") or child.name == "references":
                continue
            skill_file = _find_skill_file(child)
            if not skill_file:
                continue
            try:
                entry = self._entry_from_file(
                    skill_file, source=source, forced_name=child.name, skill_dir=child
                )
                if entry:
                    result[entry["name"]] = entry
            except Exception as e:
                print(f"[Prompt-Kit] Skill 目录跳过 {child}: {e}")
        return result

    def _entry_from_file(
        self,
        skill_file: Path,
        *,
        source: str,
        forced_name: Optional[str] = None,
        skill_dir: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        skill_dir = skill_dir or skill_file.parent
        text = _read_text(skill_file)
        meta, body = parse_skill_md(text)
        yaml_meta = _read_meta_yaml(skill_dir)
        name_raw = forced_name or meta.get("name") or skill_file.stem
        try:
            name = validate_name(name_raw)
        except ValueError:
            # 目录名不合法时尝试从 meta
            name = validate_name(meta.get("name") or skill_file.stem)

        description = (meta.get("description") or "").strip()
        display_zh = (
            yaml_meta.get("display-name-zh")
            or yaml_meta.get("display_name_zh")
            or meta.get("display_name_zh")
            or ""
        ).strip()
        tags_raw = meta.get("tags") or yaml_meta.get("tags") or ""
        if isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags = [t.strip() for t in re.split(r"[,，;；|]", str(tags_raw)) if t.strip()]

        mtime = skill_file.stat().st_mtime
        updated = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        refs = _list_references(skill_dir)
        return {
            "name": name,
            "display_name_zh": display_zh,
            "description": description,
            "tags": tags,
            "source": source,
            "has_references": bool(refs),
            "references": refs,
            "skill_file": skill_file.name,
            "path": str(skill_dir),
            "updated_at": updated,
            "_skill_file": str(skill_file),
            "_body_preview": body[:400],
        }

    def _merged(self) -> List[Dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        paths.ensure_user_dirs()
        system = self._scan_root(paths.skills, "system")
        user = self._scan_root(paths.user_skills, "user")
        merged: Dict[str, Dict[str, Any]] = dict(system)
        for name, entry in user.items():
            if name in merged:
                entry = dict(entry)
                entry["source"] = "user-override"
            merged[name] = entry
        favs = self.list_favorite_names()
        rows = []
        for name in sorted(merged.keys()):
            e = dict(merged[name])
            e["favorite"] = name in favs
            e.pop("_skill_file", None)
            rows.append(e)
        self._cache = rows
        return rows

    def list_skills(
        self,
        q: str = "",
        tags: Optional[List[str]] = None,
        source: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._merged()
        q = (q or "").strip().lower()
        tag_set = {t.strip().lower() for t in (tags or []) if t and str(t).strip()}
        source = (source or "").strip().lower()
        out: List[Dict[str, Any]] = []
        for e in rows:
            if source and e.get("source") != source:
                if not (source == "user" and e.get("source") == "user-override"):
                    continue
            if tag_set:
                et = {str(t).lower() for t in (e.get("tags") or [])}
                if not tag_set.issubset(et):
                    continue
            if q:
                blob = " ".join(
                    [
                        e.get("name") or "",
                        e.get("display_name_zh") or "",
                        e.get("description") or "",
                        " ".join(e.get("tags") or []),
                        e.get("_body_preview") or "",
                    ]
                ).lower()
                if q not in blob:
                    continue
            out.append({k: v for k, v in e.items() if not k.startswith("_")})
        return out

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        name = validate_name(name)
        # 优先用户
        for root, source in (
            (paths.user_skills, "user"),
            (paths.skills, "system"),
        ):
            skill_dir = root / name
            skill_file = _find_skill_file(skill_dir) if skill_dir.is_dir() else None
            if not skill_file and root == paths.user_skills:
                # 单文件
                for ext in (".md", ".txt"):
                    p = root / f"{name}{ext}"
                    if p.is_file():
                        skill_file = p
                        skill_dir = root
                        break
            if not skill_file:
                continue
            text = _read_text(skill_file)
            meta, body = parse_skill_md(text)
            entry = self._entry_from_file(
                skill_file,
                source=source,
                forced_name=name,
                skill_dir=skill_dir if skill_dir.is_dir() else skill_file.parent,
            )
            if not entry:
                continue
            if source == "user" and (paths.skills / name).is_dir():
                entry["source"] = "user-override"
            entry["favorite"] = self.is_favorite(name)
            entry["meta"] = meta
            entry["body"] = body
            entry["raw"] = text
            entry.pop("_skill_file", None)
            entry.pop("_body_preview", None)
            return entry
        return None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_skill(
        self,
        name: str,
        description: str,
        body: str,
        *,
        tags: Optional[List[str]] = None,
        display_name_zh: str = "",
        overwrite: bool = False,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        name = validate_name(name)
        paths.ensure_user_dirs()
        skill_dir = paths.user_skills / name
        skill_file = skill_dir / "SKILL.md"
        if skill_dir.exists() and not overwrite:
            raise ValueError(f"Skill 已存在: {name}（可传 overwrite=true 覆盖）")
        if (paths.skills / name).exists() and not overwrite:
            # 允许用户写覆盖层
            pass
        meta: Dict[str, Any] = {
            "name": name,
            "description": (description or "").strip(),
        }
        if tags:
            meta["tags"] = tags
        if extra_meta:
            for k, v in extra_meta.items():
                if k not in meta and v is not None:
                    meta[k] = v
        text = dump_skill_md(meta, body or "")
        skill_dir.mkdir(parents=True, exist_ok=True)
        _write_text(skill_file, text)
        if display_name_zh:
            _write_text(
                skill_dir / "meta.yaml",
                f"display-name-zh: {display_name_zh.strip()}\n",
            )
        self.reload()
        got = self.get_skill(name)
        if not got:
            raise RuntimeError("写入后无法读取 Skill")
        return got

    def update_skill(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        body: Optional[str] = None,
        tags: Optional[List[str]] = None,
        display_name_zh: Optional[str] = None,
    ) -> Dict[str, Any]:
        name = validate_name(name)
        existing = self.get_skill(name)
        if not existing:
            raise ValueError(f"Skill 不存在: {name}")
        # 系统只读 → COW 到用户目录
        src = existing.get("source")
        meta = dict(existing.get("meta") or {})
        meta["name"] = name
        if description is not None:
            meta["description"] = description.strip()
        elif "description" not in meta:
            meta["description"] = existing.get("description") or ""
        if tags is not None:
            meta["tags"] = tags
        new_body = body if body is not None else (existing.get("body") or "")
        text = dump_skill_md(meta, new_body)
        paths.ensure_user_dirs()
        skill_dir = paths.user_skills / name
        if src == "system" and not skill_dir.exists():
            # COW：复制 references 等
            sys_dir = paths.skills / name
            if sys_dir.is_dir():
                shutil.copytree(sys_dir, skill_dir, dirs_exist_ok=True)
        skill_dir.mkdir(parents=True, exist_ok=True)
        _write_text(skill_dir / "SKILL.md", text)
        if display_name_zh is not None:
            _write_text(
                skill_dir / "meta.yaml",
                f"display-name-zh: {display_name_zh.strip()}\n",
            )
        self.reload()
        got = self.get_skill(name)
        if not got:
            raise RuntimeError("更新后无法读取 Skill")
        return got

    def delete_skill(self, name: str) -> bool:
        name = validate_name(name)
        skill_dir = paths.user_skills / name
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir)
            # 清理收藏
            data = self._load_favorites()
            data["favorites"] = [x for x in (data.get("favorites") or []) if x != name]
            self._save_favorites()
            self.reload()
            return True
        # 单文件
        for ext in (".md", ".txt"):
            p = paths.user_skills / f"{name}{ext}"
            if p.is_file():
                p.unlink()
                self.reload()
                return True
        raise ValueError(f"只能删除用户 Skill，或不存在: {name}")

    # ------------------------------------------------------------------
    # import / export
    # ------------------------------------------------------------------

    def import_path(self, src: str | Path, *, overwrite: bool = False) -> Dict[str, Any]:
        src = Path(src).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"路径不存在: {src}")
        paths.ensure_user_dirs()
        if src.is_file() and src.suffix.lower() in (".md", ".txt"):
            text = _read_text(src)
            meta, body = parse_skill_md(text)
            name = validate_name(meta.get("name") or src.stem)
            return self.create_skill(
                name,
                description=meta.get("description") or body[:200],
                body=body or text,
                tags=None,
                overwrite=overwrite,
                extra_meta={k: v for k, v in meta.items() if k not in ("name", "description")},
            )
        if src.is_dir():
            skill_file = _find_skill_file(src)
            if not skill_file:
                raise ValueError(f"目录中未找到 SKILL.md: {src}")
            text = _read_text(skill_file)
            meta, body = parse_skill_md(text)
            name = validate_name(meta.get("name") or src.name)
            dest = paths.user_skills / name
            if dest.exists() and not overwrite:
                raise ValueError(f"Skill 已存在: {name}")
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            # 确保 name 一致
            meta["name"] = name
            if not meta.get("description"):
                meta["description"] = body[:200] if body else name
            _write_text(dest / "SKILL.md", dump_skill_md(meta, body))
            self.reload()
            got = self.get_skill(name)
            if not got:
                raise RuntimeError("导入后无法读取")
            return got
        raise ValueError(f"不支持的导入路径类型: {src}")

    def export_skill(self, name: str, dest_dir: str | Path) -> Path:
        name = validate_name(name)
        existing = self.get_skill(name)
        if not existing:
            raise ValueError(f"Skill 不存在: {name}")
        dest_dir = Path(dest_dir).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        src = Path(existing["path"])
        if dest.exists():
            shutil.rmtree(dest)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.mkdir(parents=True)
            _write_text(dest / "SKILL.md", existing.get("raw") or dump_skill_md(
                {"name": name, "description": existing.get("description") or ""},
                existing.get("body") or "",
            ))
        return dest

    # ------------------------------------------------------------------
    # template generation (no LLM)
    # ------------------------------------------------------------------

    def render_template(
        self,
        kind: str,
        fields: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        """
        规则模板生成 (meta, body)。
        kind: from_prompt | from_library | from_builder
        fields 常用键：name, description, title_zh, when, steps, output, forbid, source_text
        """
        kind = (kind or "from_prompt").strip()
        title_zh = str(fields.get("title_zh") or fields.get("name") or "未命名 Skill").strip()
        name_raw = str(fields.get("name") or "").strip()
        if not name_raw:
            slug = re.sub(r"[^a-z0-9]+", "-", title_zh.lower()).strip("-")
            name_raw = slug if NAME_RE.match(slug or "") else f"skill-{int(datetime.now(timezone.utc).timestamp())}"
        try:
            name = validate_name(name_raw)
        except ValueError:
            name = validate_name(f"skill-{int(datetime.now(timezone.utc).timestamp())}")
        when = fields.get("when") or fields.get("when_bullets") or []
        if isinstance(when, str):
            when = [w.strip() for w in when.splitlines() if w.strip()]
        steps = fields.get("steps") or []
        if isinstance(steps, str):
            steps = [s.strip() for s in steps.splitlines() if s.strip()]
        output = fields.get("output") or fields.get("output_rules") or []
        if isinstance(output, str):
            output = [o.strip() for o in output.splitlines() if o.strip()]
        forbid = fields.get("forbid") or []
        if isinstance(forbid, str):
            forbid = [f.strip() for f in forbid.splitlines() if f.strip()]
        source_text = str(fields.get("source_text") or fields.get("prompt") or "").strip()

        if not when:
            when = ["当用户需要执行与本 Skill 描述相符的任务时使用。"]
        if not steps:
            if source_text:
                steps = [
                    "阅读并理解用户提供的素材与约束。",
                    "按下列参考内容的风格、结构与要点组织输出。",
                    "必要时向用户确认缺失信息后再给出最终结果。",
                ]
            else:
                steps = [
                    "确认用户目标与约束。",
                    "按本 Skill 规则组织内容。",
                    "输出符合「输出要求」的结果。",
                ]
        if not output:
            output = ["使用清晰结构", "默认中文，专有名词可保留英文"]
        if not forbid:
            forbid = ["不要忽略用户明确给出的约束", "不要编造未提供的关键事实"]

        desc = str(fields.get("description") or "").strip()
        if not desc:
            desc = (
                f"Help with {title_zh}. Use when the user needs this workflow. "
                f"{title_zh}相关任务时使用。"
            )

        body_lines = [
            f"# {title_zh}",
            "",
            "## 何时使用",
        ]
        for w in when:
            body_lines.append(f"- {w}")
        body_lines += ["", "## 步骤"]
        for i, s in enumerate(steps, 1):
            body_lines.append(f"{i}. {s}")
        body_lines += ["", "## 输出要求"]
        for o in output:
            body_lines.append(f"- {o}")
        body_lines += ["", "## 禁止"]
        for f in forbid:
            body_lines.append(f"- {f}")
        if source_text:
            body_lines += ["", "## 参考成品 / 原始素材", "", "```", source_text[:8000], "```"]
            if kind in ("from_library", "from_builder"):
                body_lines += [
                    "",
                    "## 复现说明",
                    "- 保持参考成品的风格、节奏与关键词密度。",
                    "- 用户要求变化时，在不变核心设定的前提下调整细节。",
                ]

        meta: Dict[str, Any] = {
            "name": name,
            "description": desc,
        }
        tags = fields.get("tags")
        if tags:
            meta["tags"] = tags
        return meta, "\n".join(body_lines) + "\n"

    # ------------------------------------------------------------------
    # optional Ollama polish
    # ------------------------------------------------------------------

    def polish_with_ollama(
        self,
        meta: Dict[str, Any],
        body: str,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """
        用本地 Ollama 润色 description 与步骤措辞，尽量保持 Markdown 结构。
        返回 (meta, body, warning)。失败时返回原文 + warning，不抛致命异常。
        """
        from .settings import settings

        cfg = settings.load()
        if not cfg.get("skill_ollama_enabled", False) and model is None and base_url is None:
            # 显式调用时仍允许；若全无配置则直接跳过
            pass

        base_url = (base_url or cfg.get("skill_ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
        model = (model or cfg.get("skill_ollama_model") or "").strip()
        try:
            timeout_sec = float(timeout_sec if timeout_sec is not None else cfg.get("skill_ollama_timeout_sec") or 60)
        except (TypeError, ValueError):
            timeout_sec = 60.0

        if not model:
            return meta, body, "未配置 skill_ollama_model，已跳过润色"

        system = (
            "You refine Agent Skill documents. "
            "Improve the English description (for skill triggering) and the Chinese step wording. "
            "Keep the same Markdown structure and section headings. "
            "Do not add new major sections. Do not remove the reference block if present. "
            "Return ONLY a JSON object with keys description (string) and body (string). No markdown fences."
        )
        user = (
            f"Current name: {meta.get('name') or ''}\n"
            f"Current description:\n{meta.get('description') or ''}\n\n"
            f"Current body:\n{body or ''}\n"
        )
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.3},
        }
        import json
        import urllib.error
        import urllib.request

        req = urllib.request.Request(
            f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            content = (
                (data.get("message") or {}).get("content")
                or data.get("response")
                or ""
            )
            content = str(content).strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            new_meta = dict(meta)
            if isinstance(parsed.get("description"), str) and parsed["description"].strip():
                new_meta["description"] = parsed["description"].strip()
            new_body = body
            if isinstance(parsed.get("body"), str) and parsed["body"].strip():
                new_body = parsed["body"].strip() + ("\n" if not parsed["body"].endswith("\n") else "")
            return new_meta, new_body, None
        except urllib.error.URLError as e:
            return meta, body, f"Ollama 连接失败: {e}"
        except TimeoutError:
            return meta, body, f"Ollama 超时（{timeout_sec}s），已保留模板版"
        except Exception as e:
            return meta, body, f"Ollama 润色失败: {e}"


# 模块级单例
skill_service = SkillService()
