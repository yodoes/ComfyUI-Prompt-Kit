/**
 * Prompt-Kit Skill 面板 v0.5.0-dev (S1)
 * 列表 / 搜索 / 来源筛选 / 收藏 / 预览 / 编辑 / 删除 / 导入导出 / 规则模板生成
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/prompt-kit";
const NODE_TYPES = new Set([
  "PromptKitSkillPanel",
  "PromptKitSkillPick",
  "PromptKitSkillQuickGenerate",
]);
const QUICK_GEN_TYPE = "PromptKitSkillQuickGenerate";

const css = {
  field:
    "padding:6px 8px;border:1px solid #555;border-radius:4px;background:#2a2a2a;color:#eee;outline:none;font:inherit;box-sizing:border-box;",
  btnBlue:
    "padding:6px 14px;cursor:pointer;background:#4a7dff;border:1px solid #4a7dff;border-radius:4px;color:#fff;font:inherit;",
  btnGhost:
    "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:4px;color:#eee;font:inherit;",
  btnSmall:
    "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;color:#ccc;font-size:12px;",
  btnDanger:
    "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #a44;border-radius:4px;color:#f88;font:inherit;",
  btnActive:
    "padding:2px 8px;cursor:pointer;background:#3a5a9a;border:1px solid #4a7dff;border-radius:3px;color:#fff;font-size:12px;",
};

async function apiGet(path) {
  const res = await api.fetchApi(BASE + path);
  return await res.json();
}
async function apiPost(path, body) {
  const res = await api.fetchApi(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return await res.json();
}

/** 拉取最新 Skill 名称列表（供下拉热更新） */
async function fetchSkillNameList() {
  try {
    const res = await apiGet("/skill/list");
    if (!res.ok) return ["(无 Skill)"];
    const names = (res.skills || []).map((s) => s.name).filter(Boolean);
    return names.length ? names : ["(无 Skill)"];
  } catch (e) {
    return ["(无 Skill)"];
  }
}

function setComboValues(widget, values) {
  if (!widget || !values || !values.length) return;
  if (widget.options) {
    widget.options.values = values;
  }
  // 部分 ComfyUI 版本把可选值挂在 widget 自身
  if ("values" in widget) {
    try {
      widget.values = values;
    } catch (e) {}
  }
  const cur = widget.value;
  if (cur == null || !values.includes(cur)) {
    widget.value = values[0];
    if (typeof widget.callback === "function") {
      try {
        widget.callback(widget.value);
      } catch (e) {}
    }
  }
}

/**
 * 热更新画布上所有「选 Skill」节点的下拉列表。
 * 面板增删改 / 导入后调用，无需重启 ComfyUI。
 */
async function refreshSkillPickDropdowns() {
  const values = await fetchSkillNameList();
  const graph = app.graph;
  if (!graph || !graph._nodes) return values;
  let n = 0;
  for (const node of graph._nodes) {
    if (!node || node.type !== "PromptKitSkillPick") continue;
    if (!node.widgets) continue;
    for (const w of node.widgets) {
      if (w.name === "Skill" || w.name === "skill") {
        setComboValues(w, values);
        n++;
      }
    }
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
  }
  return { values, updated: n };
}
function el(tag, style, text) {
  const n = document.createElement(tag);
  if (style) n.style.cssText = style;
  if (text != null) n.textContent = text;
  return n;
}

function openFormModal(title, fields, buttons) {
  const ov = el(
    "div",
    "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;"
  );
  const box = el(
    "div",
    "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:520px;max-width:94vw;max-height:90vh;overflow:auto;color:#eee;font:13px system-ui,sans-serif;"
  );
  box.appendChild(el("div", "font-weight:700;margin-bottom:12px;font-size:14px;", title));
  const inputs = {};
  (fields || []).forEach((f) => {
    box.appendChild(el("div", "font-size:12px;color:#aaa;margin-bottom:4px;", f.label || f.key));
    let inp;
    if (f.type === "textarea") {
      inp = el("textarea");
      inp.rows = f.rows || 4;
      inp.value = f.value || "";
      inp.placeholder = f.placeholder || "";
      inp.style.cssText = css.field + "width:100%;margin-bottom:10px;";
    } else if (f.type === "select") {
      inp = el("select");
      inp.style.cssText = css.field + "width:100%;margin-bottom:10px;";
      (f.options || []).forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        if (String(opt.value) === String(f.value)) o.selected = true;
        inp.appendChild(o);
      });
    } else {
      inp = el("input");
      inp.type = f.type || "text";
      inp.value = f.value || "";
      inp.placeholder = f.placeholder || "";
      if (f.readonly) inp.readOnly = true;
      inp.style.cssText = css.field + "width:100%;margin-bottom:10px;";
    }
    inputs[f.key] = inp;
    box.appendChild(inp);
  });
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;margin-top:8px;");
  (buttons || []).forEach((b) => {
    const btn = el("button", b.primary ? css.btnBlue : css.btnGhost, b.label);
    btn.onclick = async () => {
      const values = {};
      Object.keys(inputs).forEach((k) => {
        values[k] = inputs[k].value;
      });
      await b.onClick(values, () => ov.remove());
    };
    row.appendChild(btn);
  });
  box.appendChild(row);
  ov.appendChild(box);
  // 表单弹窗：禁止点遮罩关闭，避免误触丢失已填内容；仅「取消」/成功回调关闭
  document.body.appendChild(ov);
  return ov;
}

function openConfirm(message, onYes) {
  const ov = el(
    "div",
    "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;"
  );
  const box = el(
    "div",
    "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:360px;max-width:90vw;color:#eee;font:13px system-ui,sans-serif;"
  );
  box.appendChild(el("div", "margin-bottom:14px;line-height:1.5;", message));
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;");
  const btnCancel = el("button", css.btnGhost, "取消");
  const btnOk = el("button", css.btnBlue, "确定");
  btnCancel.onclick = () => ov.remove();
  btnOk.onclick = async () => {
    ov.remove();
    await onYes();
  };
  row.append(btnCancel, btnOk);
  box.appendChild(row);
  ov.appendChild(box);
  document.body.appendChild(ov);
}

function applyToNode(node, text, skillName) {
  if (!node || !node.widgets) return;
  const textKeys = new Set(["面板文本", "panel_text", "文本"]);
  const nameKeys = new Set(["Skill名称", "skill_name", "名称"]);
  for (const w of node.widgets) {
    if (textKeys.has(w.name) && text != null) {
      w.value = text;
      if (w.callback) w.callback(text);
    }
    if (nameKeys.has(w.name) && skillName != null) {
      w.value = skillName;
      if (w.callback) w.callback(skillName);
    }
  }
  if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
}

function sourceLabel(src) {
  if (src === "system") return "系统";
  if (src === "user-override") return "用户覆盖";
  if (src === "user") return "用户";
  return src || "";
}

/** ISO 时间展示为 2026-10-05 06:42:51 */
function formatUpdatedAt(s) {
  if (!s) return "—";
  let t = String(s).trim();
  t = t.replace("T", " ");
  t = t.replace(/\.\d+/, "");
  t = t.replace(/Z$/i, "");
  t = t.replace(/([+-]\d{2}):(\d{2})$/, "");
  t = t.replace(/([+-]\d{4})$/, "");
  return t.trim() || "—";
}

function suggestSkillName(title) {
  let s = String(title || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (!s || s.length < 2) s = "skill-" + Date.now().toString(36);
  return s.slice(0, 48);
}

/**
 * 两步生成向导：填表 → 预览 → 保存（支持重名覆盖/改名）
 * opts: { kind, name, title_zh, description, source_text, tags, onSaved }
 */
function openGenerateWizard(opts) {
  opts = opts || {};
  const kind0 = opts.kind || "from_prompt";
  const title0 = opts.title_zh || "";
  const name0 = opts.name || suggestSkillName(title0 || opts.source_text || "");
  const desc0 = opts.description || "";
  const src0 = opts.source_text || "";
  const tags0 = Array.isArray(opts.tags) ? opts.tags.join(", ") : opts.tags || "";

  (async () => {
    let polishDefault = "false";
    try {
      const sres = await apiGet("/skill/settings");
      if (sres.ok && sres.settings && sres.settings.skill_ollama_enabled) {
        polishDefault = "true";
      }
    } catch (e) {}

    openFormModal(
      "生成 Skill · 步骤 1/2",
      [
        {
          key: "kind",
          label: "类型",
          type: "select",
          value: kind0,
          options: [
            { value: "from_prompt", label: "从说明/提示词" },
            { value: "from_library", label: "从词库预设素材" },
            { value: "from_builder", label: "从结构化组词素材" },
          ],
        },
        { key: "name", label: "名称 name（小写连字符）", value: name0, placeholder: "my-skill" },
        { key: "title_zh", label: "中文标题", value: title0 },
        {
          key: "description",
          label: "description（可空，模板自动补英文触发语）",
          type: "textarea",
          rows: 2,
          value: desc0,
        },
        {
          key: "source_text",
          label: "素材正文",
          type: "textarea",
          rows: 7,
          value: src0,
        },
        { key: "tags", label: "标签（逗号分隔）", value: tags0 },
        {
          key: "polish",
          label: "Ollama 润色（需在「Skill 设置」配置模型）",
          type: "select",
          value: polishDefault,
          options: [
            { value: "false", label: "否" },
            { value: "true", label: "是" },
          ],
        },
      ],
      [
        { label: "取消", primary: false, onClick: async (_v, close) => close() },
        {
          label: "生成预览",
          primary: true,
          onClick: async (v, close) => {
            const fields = {
              name: (v.name || "").trim() || suggestSkillName(v.title_zh || v.source_text),
              title_zh: v.title_zh,
              description: v.description,
              source_text: v.source_text,
              tags: (v.tags || "")
                .split(/[,，]/)
                .map((x) => x.trim())
                .filter(Boolean),
              kind: v.kind || "from_prompt",
            };
            const polish = String(v.polish || "").toLowerCase() === "true";
            const res = await apiPost("/skill/generate", {
              kind: fields.kind,
              fields,
              save: false,
              polish,
            });
            if (!res.ok) {
              alert(res.error || "生成失败");
              return;
            }
            close();
            if (res.warning) console.warn("[PromptKit Skill]", res.warning);
            openPreviewAndSave(res.meta || {}, res.body || "", fields, opts.onSaved, res.warning);
          },
        },
      ]
    );
  })();
}

function openPreviewAndSave(meta, body, fields, onSaved, warning) {
  openFormModal(
    "生成 Skill · 步骤 2/2 预览确认" + (warning ? "（润色未成功，已用模板版）" : ""),
    [
      {
        key: "name",
        label: "名称 name",
        value: (meta && meta.name) || fields.name || "",
      },
      {
        key: "display_name_zh",
        label: "中文显示名",
        value: fields.title_zh || "",
      },
      {
        key: "description",
        label: "description",
        type: "textarea",
        rows: 3,
        value: (meta && meta.description) || "",
      },
      {
        key: "body",
        label: "正文预览（可改）",
        type: "textarea",
        rows: 14,
        value: body || "",
      },
    ],
    [
      { label: "返回修改", primary: false, onClick: async (_v, close) => {
          close();
          openGenerateWizard({
            kind: fields.kind,
            name: fields.name,
            title_zh: fields.title_zh,
            description: fields.description,
            source_text: fields.source_text,
            tags: fields.tags,
            onSaved,
          });
        }},
      {
        label: "保存",
        primary: true,
        onClick: async (v, close) => {
          const name = (v.name || "").trim();
          if (!name) {
            alert("名称不能为空");
            return;
          }
          let res = await apiPost("/skill/save", {
            name,
            description: v.description || "",
            body: v.body || "",
            display_name_zh: v.display_name_zh || "",
            tags: fields.tags || [],
            overwrite: false,
          });
          if (!res.ok && /已存在/.test(res.error || "")) {
            const choice = await conflictChoice(name);
            if (choice === "cancel") return;
            if (choice === "overwrite") {
              res = await apiPost("/skill/save", {
                name,
                description: v.description || "",
                body: v.body || "",
                display_name_zh: v.display_name_zh || "",
                tags: fields.tags || [],
                overwrite: true,
              });
            } else if (choice === "rename") {
              const newName = suggestSkillName(name + "-2");
              res = await apiPost("/skill/save", {
                name: newName,
                description: v.description || "",
                body: v.body || "",
                display_name_zh: v.display_name_zh || "",
                tags: fields.tags || [],
                overwrite: false,
              });
            }
          }
          if (!res.ok) {
            alert(res.error || "保存失败");
            return;
          }
          close();
          try {
            await refreshSkillPickDropdowns();
          } catch (e) {}
          if (typeof onSaved === "function") {
            try {
              await onSaved(res.skill);
            } catch (e) {}
          } else {
            alert("已保存 Skill：" + ((res.skill && res.skill.name) || name));
          }
        },
      },
    ]
  );
}

function conflictChoice(name) {
  return new Promise((resolve) => {
    const ov = el(
      "div",
      "position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"
    );
    const box = el(
      "div",
      "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:400px;max-width:92vw;color:#eee;font:13px system-ui,sans-serif;"
    );
    box.appendChild(
      el("div", "margin-bottom:12px;line-height:1.5;", "Skill「" + name + "」已存在，请选择：")
    );
    const row = el("div", "display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;");
    const mk = (label, val, primary) => {
      const b = el("button", primary ? css.btnBlue : css.btnGhost, label);
      b.onclick = () => {
        ov.remove();
        resolve(val);
      };
      return b;
    };
    row.append(
      mk("取消", "cancel", false),
      mk("自动改名", "rename", false),
      mk("覆盖", "overwrite", true)
    );
    box.appendChild(row);
    ov.appendChild(box);
    document.body.appendChild(ov);
  });
}

function openPanel(targetNode) {
  let rows = [];
  let current = null;
  let favOnly = false;
  let sourceFilter = "";

  const overlay = el(
    "div",
    "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"
  );
  const dialog = el(
    "div",
    "background:#1a1a1a;border:1px solid #555;border-radius:10px;width:1080px;max-width:96vw;height:86vh;max-height:920px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.55);color:#eee;font:13px/1.4 system-ui,sans-serif;"
  );
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  const header = el(
    "div",
    "display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #333;flex-shrink:0;"
  );
  header.appendChild(el("div", "font-weight:700;font-size:15px;", "PromptKit · Skill 面板"));
  const status = el("span", "color:#8ab;font-size:12px;margin-left:auto;", "");
  header.appendChild(status);
  const btnClose = el("button", css.btnGhost, "关闭");
  btnClose.onclick = () => overlay.remove();
  header.appendChild(btnClose);
  dialog.appendChild(header);

  const toolbar = el(
    "div",
    "display:flex;gap:8px;padding:8px 14px;border-bottom:1px solid #333;flex-shrink:0;align-items:center;flex-wrap:wrap;"
  );
  const searchInput = el("input");
  searchInput.type = "text";
  searchInput.placeholder = "搜索名称 / 描述 / 标签";
  searchInput.style.cssText = css.field + "flex:1;min-width:180px;";
  const sourceSelect = el("select");
  sourceSelect.style.cssText = css.field + "width:110px;";
  [
    { v: "", t: "全部来源" },
    { v: "system", t: "仅系统" },
    { v: "user", t: "仅用户" },
  ].forEach((o) => {
    const opt = document.createElement("option");
    opt.value = o.v;
    opt.textContent = o.t;
    sourceSelect.appendChild(opt);
  });
  const btnSearch = el("button", css.btnBlue, "搜索");
  const btnFav = el("button", css.btnGhost, "收藏夹");
  const btnReload = el("button", css.btnGhost, "刷新");
  const btnNew = el("button", css.btnGhost, "新建");
  const btnGen = el("button", css.btnGhost, "生成");
  const btnImport = el("button", css.btnGhost, "导入路径");
  const btnSettings = el("button", css.btnGhost, "Skill 设置");
  toolbar.append(
    searchInput,
    sourceSelect,
    btnSearch,
    btnFav,
    btnReload,
    btnNew,
    btnGen,
    btnImport,
    btnSettings
  );
  dialog.appendChild(toolbar);

  const body = el("div", "display:flex;flex:1;min-height:0;");
  const listPane = el("div", "width:340px;border-right:1px solid #333;overflow:auto;flex-shrink:0;");
  const detailPane = el("div", "flex:1;display:flex;flex-direction:column;min-width:0;min-height:0;");
  body.append(listPane, detailPane);
  dialog.appendChild(body);

  const detailHead = el(
    "div",
    "padding:10px 14px;border-bottom:1px solid #333;flex-shrink:0;display:flex;gap:8px;align-items:center;flex-wrap:wrap;"
  );
  const detailTitle = el("div", "font-weight:600;flex:1;min-width:120px;", "选择左侧 Skill 查看");
  const btnEdit = el("button", css.btnSmall, "编辑");
  const btnDelete = el("button", css.btnSmall, "删除");
  const btnExport = el("button", css.btnSmall, "导出");
  const btnApplyBody = el("button", css.btnSmall, "正文→节点");
  const btnApplyName = el("button", css.btnSmall, "名称→节点");
  const btnCopy = el("button", css.btnSmall, "复制正文");
  detailHead.append(detailTitle, btnEdit, btnDelete, btnExport, btnApplyBody, btnApplyName, btnCopy);
  detailPane.appendChild(detailHead);

  const detailMeta = el(
    "div",
    "padding:8px 14px;border-bottom:1px solid #333;font-size:12px;color:#aaa;flex-shrink:0;"
  );
  detailPane.appendChild(detailMeta);

  const detailBody = el(
    "pre",
    "flex:1;overflow:auto;padding:12px 14px;margin:0;white-space:pre-wrap;word-break:break-word;font:12px/1.5 Consolas,monospace;color:#ddd;background:#141414;"
  );
  detailPane.appendChild(detailBody);

  function setStatus(msg) {
    status.textContent = msg || "";
  }

  function renderList() {
    listPane.innerHTML = "";
    if (!rows.length) {
      listPane.appendChild(el("div", "padding:16px;color:#888;", "无 Skill"));
      return;
    }
    rows.forEach((r) => {
      const active = current && current.name === r.name;
      const row = el(
        "div",
        "padding:10px 12px;border-bottom:1px solid #2a2a2a;cursor:pointer;" +
          (active ? "background:#243044;" : "")
      );
      const top = el("div", "display:flex;align-items:center;gap:6px;");
      const star = el(
        "span",
        "cursor:pointer;font-size:14px;color:" + (r.favorite ? "#f5c542" : "#666") + ";",
        r.favorite ? "★" : "☆"
      );
      star.onclick = async (e) => {
        e.stopPropagation();
        const res = await apiPost("/skill/favorite", { name: r.name });
        if (!res.ok) {
          setStatus(res.error || "收藏失败");
          return;
        }
        r.favorite = res.favorite;
        if (current && current.name === r.name) current.favorite = res.favorite;
        renderList();
        setStatus(res.favorite ? "已收藏" : "已取消收藏");
      };
      const title =
        (r.display_name_zh || r.name) + (r.has_references ? " · 含资料" : "");
      top.append(star, el("span", "font-weight:600;flex:1;", title));
      row.appendChild(top);
      row.appendChild(
        el(
          "div",
          "margin-top:4px;font-size:11px;color:#888;",
          sourceLabel(r.source) + " · " + (r.name || "")
        )
      );
      const desc = (r.description || "").slice(0, 90);
      if (desc) row.appendChild(el("div", "margin-top:4px;font-size:12px;color:#aaa;", desc));
      row.onclick = () => loadDetail(r.name);
      listPane.appendChild(row);
    });
  }

  async function loadDetail(name) {
    setStatus("加载中…");
    const res = await apiGet("/skill/get?name=" + encodeURIComponent(name));
    if (!res.ok) {
      setStatus(res.error || "加载失败");
      return;
    }
    current = res.skill;
    detailTitle.textContent =
      (current.display_name_zh || current.name) + "  [" + current.name + "]";
    const tags = (current.tags || []).join(", ") || "—";
    detailMeta.textContent =
      "来源: " +
      sourceLabel(current.source) +
      "  |  标签: " +
      tags +
      "  |  更新: " +
      formatUpdatedAt(current.updated_at) +
      (current.has_references
        ? "  |  参考: " + (current.references || []).join(", ")
        : "");
    detailBody.textContent = current.raw || current.body || "";
    renderList();
    setStatus("已加载 " + current.name);
  }

  async function refreshList() {
    const q = (searchInput.value || "").trim();
    sourceFilter = sourceSelect.value || "";
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (sourceFilter) params.set("source", sourceFilter);
    const res = await apiGet("/skill/list?" + params.toString());
    if (!res.ok) {
      setStatus(res.error || "列表失败");
      return;
    }
    rows = res.skills || [];
    if (favOnly) rows = rows.filter((r) => r.favorite);
    renderList();
    setStatus("共 " + rows.length + " 个 Skill");
  }

  btnSearch.onclick = () => {
    favOnly = false;
    refreshList();
  };
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      favOnly = false;
      refreshList();
    }
  });
  sourceSelect.onchange = () => {
    favOnly = false;
    refreshList();
  };
  btnFav.onclick = () => {
    favOnly = true;
    refreshList();
  };
  btnReload.onclick = async () => {
    await apiPost("/skill/reload", {});
    favOnly = false;
    await refreshList();
    try {
      const r = await refreshSkillPickDropdowns();
      setStatus("已刷新列表" + (r && r.updated != null ? "（已同步 " + r.updated + " 个选 Skill 节点）" : ""));
    } catch (e) {}
  };

  function openEditor(mode, skill) {
    const isNew = mode === "new";
    openFormModal(
      isNew ? "新建 Skill" : "编辑 Skill",
      [
        {
          key: "name",
          label: "名称 (name，小写连字符)",
          value: skill ? skill.name : "",
          readonly: !isNew,
          placeholder: "my-skill-name",
        },
        {
          key: "display_name_zh",
          label: "中文显示名",
          value: skill ? skill.display_name_zh || "" : "",
        },
        {
          key: "description",
          label: "description（英文触发 + 可附中文）",
          type: "textarea",
          rows: 3,
          value: skill ? skill.description || "" : "",
        },
        {
          key: "tags",
          label: "标签（逗号分隔）",
          value: skill ? (skill.tags || []).join(", ") : "",
        },
        {
          key: "body",
          label: "正文（Markdown）",
          type: "textarea",
          rows: 12,
          value: skill ? skill.body || "" : "# 标题\n\n## 何时使用\n- \n\n## 步骤\n1. \n\n## 输出要求\n- \n\n## 禁止\n- \n",
        },
      ],
      [
        {
          label: "取消",
          primary: false,
          onClick: async (_v, close) => close(),
        },
        {
          label: "保存",
          primary: true,
          onClick: async (v, close) => {
            if (!(v.name || "").trim()) {
              setStatus("名称不能为空");
              return;
            }
            const payload = {
              name: v.name.trim(),
              description: v.description || "",
              body: v.body || "",
              tags: v.tags || "",
              display_name_zh: v.display_name_zh || "",
              overwrite: !isNew,
            };
            const res = await apiPost("/skill/save", payload);
            if (!res.ok) {
              setStatus(res.error || "保存失败");
              return;
            }
            close();
            setStatus("已保存 " + payload.name);
            await refreshList();
            try {
              await refreshSkillPickDropdowns();
            } catch (e) {}
            await loadDetail(payload.name);
          },
        },
      ]
    );
  }

  btnNew.onclick = () => openEditor("new", null);
  btnEdit.onclick = () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    openEditor("edit", current);
  };
  btnDelete.onclick = () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    if (current.source === "system") {
      setStatus("系统 Skill 不能删除（可编辑后保存为用户覆盖）");
      return;
    }
    openConfirm("确定删除用户 Skill「" + current.name + "」？", async () => {
      const res = await apiPost("/skill/delete", { name: current.name });
      if (!res.ok) {
        setStatus(res.error || "删除失败");
        return;
      }
      current = null;
      detailTitle.textContent = "选择左侧 Skill 查看";
      detailMeta.textContent = "";
      detailBody.textContent = "";
      await refreshList();
      try {
        await refreshSkillPickDropdowns();
      } catch (e) {}
      setStatus("已删除");
    });
  };
  btnExport.onclick = async () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    let defaultDest = "";
    try {
      const sres = await apiGet("/skill/settings");
      if (sres.ok && sres.settings) defaultDest = sres.settings.skill_export_dir || "";
    } catch (e) {}
    openFormModal(
      "导出 Skill",
      [
        {
          key: "dest_dir",
          label: "目标目录（默认来自 Skill 设置；可填 comfyUI-llama-TE/skills）",
          placeholder: "/path/to/skills",
          value: defaultDest,
        },
      ],
      [
        { label: "取消", primary: false, onClick: async (_v, close) => close() },
        {
          label: "导出",
          primary: true,
          onClick: async (v, close) => {
            const res = await apiPost("/skill/export", {
              name: current.name,
              dest_dir: (v.dest_dir || "").trim(),
            });
            if (!res.ok) {
              setStatus(res.error || "导出失败");
              return;
            }
            close();
            setStatus("已导出到 " + res.path);
          },
        },
      ]
    );
  };

  btnSettings.onclick = async () => {
    let cur = {
      skill_ollama_enabled: false,
      skill_ollama_base_url: "http://127.0.0.1:11434",
      skill_ollama_model: "",
      skill_ollama_timeout_sec: 60,
      skill_export_dir: "",
    };
    try {
      const sres = await apiGet("/skill/settings");
      if (sres.ok && sres.settings) cur = Object.assign(cur, sres.settings);
    } catch (e) {}

    const ov = el(
      "div",
      "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;"
    );
    const box = el(
      "div",
      "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:520px;max-width:94vw;max-height:90vh;overflow:auto;color:#eee;font:13px system-ui,sans-serif;"
    );
    box.appendChild(el("div", "font-weight:700;margin-bottom:12px;font-size:14px;", "Skill 设置"));

    const lab = (t) => el("div", "font-size:12px;color:#aaa;margin-bottom:4px;", t);
    const fieldStyle = css.field + "width:100%;margin-bottom:10px;";

    box.appendChild(lab("启用 Ollama 润色"));
    const selEnabled = el("select");
    selEnabled.style.cssText = fieldStyle;
    [
      { v: "false", t: "否" },
      { v: "true", t: "是" },
    ].forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.v;
      opt.textContent = o.t;
      if ((cur.skill_ollama_enabled ? "true" : "false") === o.v) opt.selected = true;
      selEnabled.appendChild(opt);
    });
    box.appendChild(selEnabled);

    box.appendChild(lab("Ollama 地址"));
    const inpUrl = el("input");
    inpUrl.type = "text";
    inpUrl.value = cur.skill_ollama_base_url || "http://127.0.0.1:11434";
    inpUrl.style.cssText = fieldStyle;
    box.appendChild(inpUrl);

    box.appendChild(lab("模型（从本地 Ollama 列表选择；也可在下方自定义）"));
    const modelRow = el("div", "display:flex;gap:8px;margin-bottom:6px;align-items:center;");
    const selModel = el("select");
    selModel.style.cssText = css.field + "flex:1;min-width:0;";
    const btnRefreshModels = el("button", css.btnGhost, "刷新列表");
    btnRefreshModels.style.flexShrink = "0";
    modelRow.append(selModel, btnRefreshModels);
    box.appendChild(modelRow);
    const modelHint = el("div", "font-size:11px;color:#888;margin-bottom:8px;", "正在加载模型列表…");
    box.appendChild(modelHint);

    box.appendChild(lab("自定义模型名（可选；非空时优先于上方下拉）"));
    const inpCustomModel = el("input");
    inpCustomModel.type = "text";
    inpCustomModel.placeholder = "例如 qwen2.5:14b（列表没有时手填）";
    inpCustomModel.value = "";
    inpCustomModel.style.cssText = fieldStyle;
    box.appendChild(inpCustomModel);

    function fillModelSelect(models, preferred) {
      selModel.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = models.length ? "（请选择模型）" : "（无可用模型，请手填自定义）";
      selModel.appendChild(empty);
      (models || []).forEach((name) => {
        const o = document.createElement("option");
        o.value = name;
        o.textContent = name;
        if (preferred && preferred === name) o.selected = true;
        selModel.appendChild(o);
      });
      if (preferred && models.indexOf(preferred) < 0 && preferred) {
        // 已保存的模型不在列表中：放进自定义框并保留下拉空选
        inpCustomModel.value = preferred;
        selModel.value = "";
      } else if (preferred && models.indexOf(preferred) >= 0) {
        selModel.value = preferred;
        inpCustomModel.value = "";
      }
    }

    async function loadModels() {
      modelHint.textContent = "正在加载模型列表…";
      modelHint.style.color = "#888";
      const base = (inpUrl.value || "").trim();
      try {
        const q = base ? "?base_url=" + encodeURIComponent(base) : "";
        const res = await apiGet("/skill/ollama/models" + q);
        if (!res.ok) {
          fillModelSelect([], cur.skill_ollama_model || "");
          modelHint.textContent = res.error || "无法获取模型列表，请手填自定义模型名";
          modelHint.style.color = "#c96";
          return;
        }
        const models = res.models || [];
        fillModelSelect(models, cur.skill_ollama_model || selModel.value || "");
        modelHint.textContent = models.length
          ? "已加载 " + models.length + " 个模型"
          : "列表为空，请确认 Ollama 已安装模型或手填名称";
        modelHint.style.color = models.length ? "#8a8" : "#c96";
      } catch (e) {
        fillModelSelect([], cur.skill_ollama_model || "");
        modelHint.textContent = "请求失败，请手填自定义模型名";
        modelHint.style.color = "#c96";
      }
    }
    btnRefreshModels.onclick = () => loadModels();
    // 初始加载
    loadModels();

    box.appendChild(lab("超时秒数"));
    const inpTimeout = el("input");
    inpTimeout.type = "text";
    inpTimeout.value = String(cur.skill_ollama_timeout_sec || 60);
    inpTimeout.style.cssText = fieldStyle;
    box.appendChild(inpTimeout);

    box.appendChild(lab("默认导出目录"));
    const inpExport = el("input");
    inpExport.type = "text";
    inpExport.value = cur.skill_export_dir || "";
    inpExport.placeholder = "/path/to/comfyUI-llama-TE/skills";
    inpExport.style.cssText = fieldStyle;
    box.appendChild(inpExport);

    const row = el("div", "display:flex;gap:8px;justify-content:flex-end;margin-top:8px;");
    const btnCancel = el("button", css.btnGhost, "取消");
    const btnSave = el("button", css.btnBlue, "保存");
    btnCancel.onclick = () => ov.remove();
    btnSave.onclick = async () => {
      const custom = (inpCustomModel.value || "").trim();
      const fromList = (selModel.value || "").trim();
      const model = custom || fromList;
      const payload = {
        skill_ollama_enabled: selEnabled.value === "true",
        skill_ollama_base_url: (inpUrl.value || "").trim(),
        skill_ollama_model: model,
        skill_ollama_timeout_sec: parseInt(inpTimeout.value || "60", 10) || 60,
        skill_export_dir: (inpExport.value || "").trim(),
      };
      const res = await apiPost("/skill/settings", payload);
      if (!res.ok) {
        setStatus(res.error || "保存设置失败");
        return;
      }
      ov.remove();
      setStatus(
        "Skill 设置已保存" +
          (payload.skill_ollama_enabled
            ? "（润色开 · " + (payload.skill_ollama_model || "未选模型") + "）"
            : "（润色关）")
      );
    };
    row.append(btnCancel, btnSave);
    box.appendChild(row);
    ov.appendChild(box);
    // 设置弹窗：仅取消/保存关闭，避免误触遮罩丢配置
    document.body.appendChild(ov);
  };

  btnImport.onclick = () => {
    openFormModal(
      "从路径导入 Skill",
      [
        {
          key: "path",
          label: "本机目录或 .md/.txt 绝对路径",
          placeholder: "/path/to/my-skill 或 /path/to/SKILL.md",
        },
        {
          key: "overwrite",
          label: "覆盖已存在",
          type: "select",
          value: "false",
          options: [
            { value: "false", label: "否（不覆盖）" },
            { value: "true", label: "是（覆盖）" },
          ],
        },
      ],
      [
        { label: "取消", primary: false, onClick: async (_v, close) => close() },
        {
          label: "导入",
          primary: true,
          onClick: async (v, close) => {
            const path = (v.path || "").trim();
            if (!path) {
              setStatus("路径不能为空");
              return;
            }
            const res = await apiPost("/skill/import", {
              path,
              overwrite: String(v.overwrite || "").toLowerCase() === "true",
            });
            if (!res.ok) {
              setStatus(res.error || "导入失败");
              return;
            }
            close();
            await refreshList();
            try {
              await refreshSkillPickDropdowns();
            } catch (e) {}
            if (res.skill && res.skill.name) await loadDetail(res.skill.name);
            setStatus("已导入 " + (res.skill && res.skill.name));
          },
        },
      ]
    );
  };

  btnGen.onclick = () => {
    openGenerateWizard({
      kind: "from_prompt",
      onSaved: async (skill) => {
        setStatus("已保存 " + (skill && skill.name));
        await refreshList();
        try {
          await refreshSkillPickDropdowns();
        } catch (e) {}
        if (skill && skill.name) await loadDetail(skill.name);
      },
    });
  };

  btnApplyBody.onclick = () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    applyToNode(targetNode, current.body || current.raw || "", current.name);
    setStatus("已将正文写入节点");
  };
  btnApplyName.onclick = () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    applyToNode(targetNode, current.name, current.name);
    setStatus("已将名称写入节点");
  };
  btnCopy.onclick = async () => {
    if (!current) {
      setStatus("请先选择 Skill");
      return;
    }
    const text = current.raw || current.body || "";
    try {
      await navigator.clipboard.writeText(text);
      setStatus("已复制正文");
    } catch (e) {
      setStatus("复制失败");
    }
  };

  refreshList();
}

function addOpenButton(node) {
  // 快速生成节点不挂面板按钮
  if (!node || node.type === QUICK_GEN_TYPE) return;
  if (node._pkSkillBtn) return;
  node._pkSkillBtn = true;
  const btn = node.addWidget("button", "打开 Skill 面板", null, () => openPanel(node));
  btn.serialize = false;
}

function addPickRefreshButton(node) {
  if (node._pkSkillRefreshBtn) return;
  node._pkSkillRefreshBtn = true;
  const btn = node.addWidget("button", "刷新 Skill 列表", null, async () => {
    const r = await refreshSkillPickDropdowns();
    const names = (r && r.values) || [];
    if (node.widgets) {
      for (const w of node.widgets) {
        if (w.name === "Skill" || w.name === "skill") setComboValues(w, names);
      }
    }
    if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
  });
  btn.serialize = false;
}

async function syncPickNodeOnCreate(node) {
  if (!node || node.type !== "PromptKitSkillPick") return;
  const values = await fetchSkillNameList();
  if (!node.widgets) return;
  for (const w of node.widgets) {
    if (w.name === "Skill" || w.name === "skill") setComboValues(w, values);
  }
}

function findWidget(node, names) {
  if (!node || !node.widgets) return null;
  const set = new Set(names);
  for (const w of node.widgets) {
    if (set.has(w.name)) return w;
  }
  return null;
}

function setWidgetVisible(widget, visible) {
  if (!widget) return;
  if (visible) {
    widget.hidden = false;
    if (widget._pkSizeHidden) {
      delete widget.computeSize;
      widget._pkSizeHidden = false;
    }
    if (widget.element) widget.element.style.display = "";
  } else {
    widget.hidden = true;
    // 零高度，避免隐藏控件仍占布局，且不把节点宽度算小
    widget.computeSize = function () {
      return [0, -4];
    };
    widget._pkSizeHidden = true;
    if (widget.element) widget.element.style.display = "none";
  }
}

/** 刷新节点高度，保留用户拖过的宽度，并保证最小宽度 */
function refreshNodeSizeKeepWidth(node, minW) {
  if (!node) return;
  minW = minW || 420;
  try {
    let visible = 0;
    for (const w of node.widgets || []) {
      if (w && !w.hidden) visible += 1;
    }
    const minH = 50 + visible * 26 + 24;
    const computed = typeof node.computeSize === "function" ? node.computeSize() : null;
    const curW = (node.size && node.size[0]) || 0;
    const w = Math.max(curW, (computed && computed[0]) || 0, minW);
    const h = Math.max((computed && computed[1]) || 0, minH);
    if (typeof node.setSize === "function") node.setSize([w, h]);
    if (node.size) {
      node.size[0] = w;
      node.size[1] = h;
    }
  } catch (e) {}
  if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
}

async function refreshOllamaModelWidget(node) {
  const modelW = findWidget(node, ["Ollama模型", "ollama_model"]);
  if (!modelW) return;
  try {
    const res = await apiGet("/skill/ollama/models");
    const models = res.ok && res.models && res.models.length ? res.models : null;
    if (models) {
      setComboValues(modelW, models);
    }
  } catch (e) {}
}

function wireQuickGenerateVisibility(node) {
  if (!node || node.type !== QUICK_GEN_TYPE || node._pkQuickGenWired) return;
  node._pkQuickGenWired = true;

  const polishW = findWidget(node, ["Ollama润色", "polish"]);
  const modelW = findWidget(node, ["Ollama模型", "ollama_model"]);
  if (!polishW || !modelW) return;

  // 初始拉宽，避免多行文本控件挤在过窄节点里
  try {
    const curW = (node.size && node.size[0]) || 0;
    const curH = (node.size && node.size[1]) || 0;
    if (typeof node.setSize === "function") {
      node.setSize([Math.max(curW, 420), Math.max(curH, 280)]);
    } else if (node.size) {
      node.size[0] = Math.max(curW, 420);
      node.size[1] = Math.max(curH, 280);
    }
  } catch (e) {}

  let refreshBtn = null;
  if (!node._pkOllamaRefreshBtn) {
    node._pkOllamaRefreshBtn = true;
    refreshBtn = node.addWidget("button", "刷新 Ollama 模型", null, async () => {
      await refreshOllamaModelWidget(node);
      if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
    });
    refreshBtn.serialize = false;
  }

  const applyAll = () => {
    const on = !!polishW.value;
    setWidgetVisible(modelW, on);
    if (refreshBtn) setWidgetVisible(refreshBtn, on);
    if (on) refreshOllamaModelWidget(node);
    // 只调高度、保留当前宽度（含用户拖宽后的值）
    refreshNodeSizeKeepWidth(node, 420);
  };

  const prev = polishW.callback;
  polishW.callback = function () {
    if (typeof prev === "function") prev.apply(this, arguments);
    applyAll();
  };
  applyAll();
}

app.registerExtension({
  name: "PromptKit.SkillPanel",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_TYPES.has(nodeData.name)) return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
      addOpenButton(this);
      if (nodeData.name === "PromptKitSkillPick") {
        addPickRefreshButton(this);
        syncPickNodeOnCreate(this);
      }
      if (nodeData.name === QUICK_GEN_TYPE) {
        wireQuickGenerateVisibility(this);
      }
      return r;
    };
  },
  async setup() {
    try {
      await refreshSkillPickDropdowns();
    } catch (e) {}
    // 已加载工作流中的快速生成节点补绑显隐
    try {
      const graph = app.graph;
      if (graph && graph._nodes) {
        for (const n of graph._nodes) {
          if (n && n.type === QUICK_GEN_TYPE) wireQuickGenerateVisibility(n);
        }
      }
    } catch (e) {}
  },
});

// 供词库 / 结构化面板调用「沉淀为 Skill」；并暴露下拉热更新
window.PromptKitSkill = {
  openGenerateWizard,
  openPanel,
  suggestSkillName,
  refreshSkillPickDropdowns,
  fetchSkillNameList,
};
