"""
JSON / JSONL 读写工具。
所有读写统一 UTF-8，失败时返回 None 或空列表，并打印简要日志，不抛致命异常。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, List, Optional, Union


def read_json(path: Union[str, Path], default: Any = None) -> Any:
    """读取 JSON 文件。失败返回 default（默认 None）。"""
    path = Path(path)
    if not path.is_file():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[Prompt-Kit] 读取 JSON 失败: {path} -> {e}")
        return default


def write_json(path: Union[str, Path], data: Any, indent: int = 2) -> bool:
    """写入 JSON 文件（原子替换）。成功返回 True。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f"[Prompt-Kit] 写入 JSON 失败: {path} -> {e}")
        return False


def read_jsonl(path: Union[str, Path]) -> List[dict]:
    """逐行读取 JSONL，跳过空行与坏行。"""
    path = Path(path)
    if not path.is_file():
        return []
    rows: List[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except json.JSONDecodeError as e:
                    print(f"[Prompt-Kit] JSONL 第 {i} 行解析失败: {path} -> {e}")
    except OSError as e:
        print(f"[Prompt-Kit] 读取 JSONL 失败: {path} -> {e}")
    return rows


def append_jsonl(path: Union[str, Path], items: Iterable[dict]) -> bool:
    """向 JSONL 追加若干条记录。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True
    except OSError as e:
        print(f"[Prompt-Kit] 追加 JSONL 失败: {path} -> {e}")
        return False


def write_jsonl(path: Union[str, Path], items: Iterable[dict]) -> bool:
    """整文件覆盖写入 JSONL。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f"[Prompt-Kit] 写入 JSONL 失败: {path} -> {e}")
        return False
