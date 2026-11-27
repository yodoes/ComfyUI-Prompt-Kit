---
name: demo-prompt-polish
description: Polish and expand image-generation prompts while preserving the user's intent. Use when the user asks to improve, expand, or clean up a prompt. 提示词润色、扩写、整理时使用。
tags: demo, prompt, polish
---

# 提示词润色（示例）

## 何时使用

- 用户已有一段提示词，希望更清晰、更完整
- 需要扩写细节但不改变主题与风格
- 需要统一中文输出结构

## 步骤

1. 识别主体、场景、风格、镜头与必须保留的关键词。
2. 补全缺失但合理的细节（光影、材质、构图），不引入用户未要求的新主题。
3. 按「主体 → 外观 → 动作/表情 → 服装 → 场景 → 光影 → 风格」组织中文短句。
4. 去除重复与冲突描述，保持可直接用于生图。

## 输出要求

- 默认纯中文，专有模型词可保留英文
- 使用逗号或顿号分隔的短语/短句
- 不输出解释过程，只输出最终提示词（除非用户要求说明）

## 禁止

- 不要删除用户明确要求保留的元素
- 不要加入 NSFW 内容，除非用户明确要求
- 不要写成故事段落（除非用户指定叙事体）
