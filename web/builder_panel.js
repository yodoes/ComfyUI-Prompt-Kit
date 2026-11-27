/**
 * Prompt-Kit 结构化生成面板（阶段 4 / P4）
 * - 左：槽位列表（SFW 11；NSFW 开时 +5，fluids 默认折叠）
 * - 中：分组 + 搜索 + 词条
 * - 右：已选（按槽）+ 实时 compose 预览
 * - 顶栏：分隔符 / 权重 / 去重 / NSFW / 时代锁定 / 预设 / 应用到节点
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/prompt-kit";
/** 大节点 + 工厂小节点（PromptKitSlot_*）均可打开面板 */
function isBuilderNodeType(name) {
  return name === "PromptKitStructuredBuilder" || (name && String(name).startsWith("PromptKitSlot_"));
}

const css = {
  field:
    "padding:6px 8px;border:1px solid #555;border-radius:4px;background:#2a2a2a;color:#eee;outline:none;font:inherit;box-sizing:border-box;",
  btnBlue:
    "padding:6px 14px;cursor:pointer;background:#4a7dff;border:1px solid #4a7dff;border-radius:4px;color:#fff;font:inherit;",
  btnGhost:
    "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:4px;color:#eee;font:inherit;",
  btnSmall:
    "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;color:#ccc;font-size:12px;",
  btnActive:
    "padding:2px 8px;cursor:pointer;background:#3a5a9a;border:1px solid #4a7dff;border-radius:3px;color:#fff;font-size:12px;",
  slotBtn:
    "display:flex;align-items:center;gap:6px;width:100%;text-align:left;padding:6px 8px;margin:0 0 4px;border-radius:4px;border:1px solid transparent;background:transparent;color:#ddd;cursor:pointer;font:inherit;",
  slotOn:
    "display:flex;align-items:center;gap:6px;width:100%;text-align:left;padding:6px 8px;margin:0 0 4px;border-radius:4px;border:1px solid #4a7dff;background:#243656;color:#fff;cursor:pointer;font:inherit;",
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
function el(tag, style, text) {
  const n = document.createElement(tag);
  if (style) n.style.cssText = style;
  if (text != null) n.textContent = text;
  return n;
}

/** 通用表单弹窗：fields=[{key,label,type,value,placeholder,rows}], buttons=[{label,primary,onClick(values, close)}] */
function openFormModal(title, fields, buttons) {
  const ov = el("div", "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;");
  const box = el("div", "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:440px;max-width:92vw;color:#eee;font:13px system-ui,sans-serif;");
  box.appendChild(el("div", "font-weight:700;margin-bottom:12px;font-size:14px;", title));
  const inputs = {};
  fields.forEach((f) => {
    box.appendChild(el("div", "font-size:12px;color:#aaa;margin-bottom:4px;", f.label || f.key));
    let inp;
    if (f.type === "textarea") {
      inp = el("textarea");
      inp.rows = f.rows || 4;
      inp.value = f.value || "";
      inp.placeholder = f.placeholder || "";
      inp.style.cssText = "padding:6px 8px;border:1px solid #555;border-radius:4px;background:#2a2a2a;color:#eee;outline:none;font:inherit;box-sizing:border-box;width:100%;margin-bottom:10px;";
    } else {
      inp = el("input");
      inp.type = "text";
      inp.value = f.value || "";
      inp.placeholder = f.placeholder || "";
      inp.style.cssText = "padding:6px 8px;border:1px solid #555;border-radius:4px;background:#2a2a2a;color:#eee;outline:none;font:inherit;box-sizing:border-box;width:100%;margin-bottom:10px;";
    }
    inputs[f.key] = inp;
    box.appendChild(inp);
  });
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;margin-top:4px;");
  const close = () => ov.remove();
  (buttons || []).forEach((b) => {
    const btn = el("button", b.primary
      ? "padding:6px 14px;cursor:pointer;background:#4a7dff;border:1px solid #4a7dff;border-radius:4px;color:#fff;font:inherit;"
      : "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:4px;color:#eee;font:inherit;", b.label);
    btn.onclick = async () => {
      const values = {};
      Object.keys(inputs).forEach((k) => { values[k] = inputs[k].value; });
      await b.onClick(values, close);
    };
    row.appendChild(btn);
  });
  box.appendChild(row);
  ov.appendChild(box);
  // 表单弹窗不点遮罩关闭，仅取消/保存关闭

  document.body.appendChild(ov);
  const first = Object.values(inputs)[0];
  if (first) first.focus();
  return ov;
}

function openConfirmModal(message, onYes) {
  const ov = el("div", "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;");
  const box = el("div", "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:400px;max-width:92vw;color:#eee;font:13px system-ui,sans-serif;");
  box.appendChild(el("div", "font-weight:700;margin-bottom:10px;", "确认"));
  box.appendChild(el("div", "margin-bottom:14px;line-height:1.5;color:#ddd;", message));
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;");
  const btnCancel = el("button", "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:4px;color:#eee;font:inherit;", "取消");
  const btnOk = el("button", "padding:6px 14px;cursor:pointer;background:#4a7dff;border:1px solid #4a7dff;border-radius:4px;color:#fff;font:inherit;", "确认");
  const close = () => ov.remove();
  btnCancel.onclick = close;
  btnOk.onclick = async () => { close(); await onYes(); };
  row.append(btnCancel, btnOk);
  box.appendChild(row);
  ov.appendChild(box);
  document.body.appendChild(ov);
}

const WIDGET_ALIASES = {
  modules_state: ["模块状态", "modules_state"],
  panel_text: ["面板文本", "panel_text"],
  separator: ["分隔符", "separator"],
  dedupe: ["去重", "dedupe"],
  enable_weight: ["启用权重", "enable_weight"],
  include_nsfw: ["含NSFW", "include_nsfw"],
  term_ids: ["词条ID列表", "term_ids"],
  era_lock: ["时代锁定", "era_lock"],
  slot_states: ["组词状态", "slot_states"],
};
function setWidget(node, name, value) {
  if (!node || !node.widgets) return false;
  const names = WIDGET_ALIASES[name] || [name];
  for (const n of names) {
    const w = node.widgets.find((x) => x.name === n);
    if (!w) continue;
    w.value = value;
    if (w.callback) w.callback(value);
    node.setDirtyCanvas?.(true, true);
    return true;
  }
  return false;
}
function getWidget(node, name, fallback) {
  const names = WIDGET_ALIASES[name] || [name];
  for (const n of names) {
    const w = node?.widgets?.find((x) => x.name === n);
    if (w != null) return w.value;
  }
  return fallback;
}

function openPanel(targetNode) {
  /** @type {Record<string, Array<{id:string,text_zh:string,slot:string,nsfw?:boolean}>>} */
  let selected = {};
  /** @type {Record<string, boolean>} */
  let enabled = {};
  /** @type {Array<object>} */
  let slots = [];
  let currentSlot = "";
  let showNsfw = !!getWidget(targetNode, "include_nsfw", false);
  let activeGroup = "";
  let lastTerms = [];
  let activeTerm = null;
  let composeTimer = null;
  let fluidsExpanded = false;

  // restore from node modules_state if any
  try {
    const raw = getWidget(targetNode, "modules_state", "{}") || "{}";
    const data = typeof raw === "string" ? JSON.parse(raw || "{}") : raw;
    if (data && typeof data === "object") {
      if (data.selected && typeof data.selected === "object") {
        for (const [k, v] of Object.entries(data.selected)) {
          if (Array.isArray(v)) selected[k] = v.map((id) => ({ id: String(id), text_zh: String(id), slot: k }));
        }
      }
      if (data.enabled && typeof data.enabled === "object") {
        for (const [k, v] of Object.entries(data.enabled)) enabled[k] = !!v;
      }
    }
  } catch (_) {}

  const overlay = el(
    "div",
    "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"
  );
  const dialog = el(
    "div",
    "background:#1a1a1a;border:1px solid #555;border-radius:10px;width:1140px;max-width:96vw;height:88vh;max-height:960px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.55);color:#eee;font:13px/1.4 system-ui,sans-serif;"
  );
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  // header
  const header = el(
    "div",
    "display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #333;flex-shrink:0;"
  );
  header.appendChild(el("div", "font-weight:700;font-size:15px;", "PromptKit · 结构化面板"));
  const status = el("span", "color:#8ab;font-size:12px;margin-left:auto;", "");
  header.appendChild(status);
  const btnClose = el("button", css.btnGhost, "关闭");
  btnClose.onclick = () => overlay.remove();
  header.appendChild(btnClose);
  dialog.appendChild(header);

  // toolbar
  const toolbar = el(
    "div",
    "display:flex;gap:8px;padding:8px 14px;border-bottom:1px solid #333;flex-shrink:0;align-items:center;flex-wrap:wrap;"
  );
  const sepInput = el("input");
  sepInput.type = "text";
  sepInput.placeholder = "分隔符";
  sepInput.value = getWidget(targetNode, "separator", ", ") || ", ";
  sepInput.style.cssText = css.field + "width:88px;";
  sepInput.title = "分隔符";

  const chkDedupe = document.createElement("input");
  chkDedupe.type = "checkbox";
  chkDedupe.checked = getWidget(targetNode, "dedupe", true) !== false;
  const labDedupe = el("label", "display:flex;align-items:center;gap:4px;font-size:12px;color:#aaa;");
  labDedupe.append(chkDedupe, document.createTextNode("去重"));

  const chkWeight = document.createElement("input");
  chkWeight.type = "checkbox";
  chkWeight.checked = !!getWidget(targetNode, "enable_weight", false);
  const labWeight = el("label", "display:flex;align-items:center;gap:4px;font-size:12px;color:#aaa;");
  labWeight.append(chkWeight, document.createTextNode("权重"));

  const chkNsfw = document.createElement("input");
  chkNsfw.type = "checkbox";
  chkNsfw.checked = showNsfw;
  const labNsfw = el("label", "display:flex;align-items:center;gap:4px;font-size:12px;color:#c9a;",);
  labNsfw.append(chkNsfw, document.createTextNode("显示 NSFW（含着装服饰等附加槽）"));

  const eraSelect = el("select");
  eraSelect.style.cssText = css.field + "min-width:110px;";
  eraSelect.title = "时代锁定：随机与预设会参考；指定词不强制";
  const ERA_OPTS = ["关闭", "现代", "古风中式", "仙侠玄幻", "民国年代", "西幻欧式", "科幻未来"];
  for (const e of ERA_OPTS) {
    const o = document.createElement("option");
    o.value = e;
    o.textContent = e === "关闭" ? "时代锁定：关闭" : "时代：" + e;
    eraSelect.appendChild(o);
  }
  const nodeEra = getWidget(targetNode, "era_lock", "关闭") || "关闭";
  eraSelect.value = ERA_OPTS.indexOf(nodeEra) >= 0 ? nodeEra : "关闭";

  const presetSelect = el("select");
  presetSelect.style.cssText = css.field + "min-width:120px;";
  presetSelect.title = "官方组词预设：一键填充已选（可再改）";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = "预设…";
  presetSelect.appendChild(opt0);
  const btnPreset = el("button", css.btnGhost, "应用预设");

  const btnReload = el("button", css.btnGhost, "刷新词表");
  btnReload.title = "重新加载服务端词表缓存并刷新本面板列表（节点下拉需重建节点或重启）";
  const btnValidate = el("button", css.btnGhost, "校验数据");
  btnValidate.title = "检查空组、偏少组等";
  const btnClear = el("button", css.btnGhost, "清空已选");
  const btnApply = el("button", css.btnBlue, "应用到节点");
  const btnCopy = el("button", css.btnGhost, "复制预览");
  const btnToSkill = el("button", css.btnGhost, "沉淀为 Skill");
  toolbar.append(sepInput, labDedupe, labWeight, labNsfw, eraSelect, presetSelect, btnPreset, btnReload, btnValidate, btnClear, btnToSkill, btnApply, btnCopy);
  dialog.appendChild(toolbar);

  // 加载预设列表
  (async () => {
    try {
      const res = await apiGet("/builder/presets");
      if (res.ok && res.presets) {
        for (const pr of res.presets) {
          const o = document.createElement("option");
          o.value = pr.id;
          o.textContent = pr.name_zh || pr.id;
          presetSelect.appendChild(o);
        }
      }
    } catch (_e) {}
  })();

  // live preview bar
  const previewBar = el(
    "div",
    "padding:8px 14px;border-bottom:1px solid #333;flex-shrink:0;background:#141414;"
  );
  previewBar.appendChild(el("div", "color:#888;font-size:11px;margin-bottom:4px;", "实时预览"));
  const previewText = el(
    "div",
    "color:#ddd;font-size:13px;line-height:1.45;max-height:72px;overflow:auto;white-space:pre-wrap;word-break:break-word;",
    "（尚未选择）"
  );
  previewBar.appendChild(previewText);
  dialog.appendChild(previewBar);

  // body 3 columns
  const body = el("div", "display:flex;flex:1;min-height:0;");
  const leftPane = el(
    "div",
    "width:200px;border-right:1px solid #333;display:flex;flex-direction:column;flex-shrink:0;min-height:0;padding:8px;"
  );
  leftPane.appendChild(el("div", "font-size:12px;color:#888;margin-bottom:6px;", "槽位"));
  const slotList = el("div", "flex:1;overflow:auto;");
  leftPane.appendChild(slotList);

  const midPane = el("div", "flex:1;display:flex;flex-direction:column;min-width:0;min-height:0;border-right:1px solid #333;");
  const midToolbar = el(
    "div",
    "display:flex;gap:6px;padding:8px;border-bottom:1px solid #333;flex-shrink:0;flex-wrap:wrap;align-items:center;"
  );
  const groupSelect = el("select");
  groupSelect.style.cssText = css.field + "min-width:100px;";
  const searchInput = el("input");
  searchInput.type = "text";
  searchInput.placeholder = "搜索当前槽…";
  searchInput.style.cssText = css.field + "flex:1;min-width:120px;";
  const btnSearch = el("button", css.btnBlue, "搜索");
  const btnAddTerm = el("button", css.btnGhost, "新增词条");
  const btnEditTerm = el("button", css.btnGhost, "编辑词条");
  const btnDelTerm = el("button", css.btnGhost, "删除词条");
  const modeHint = el("span", "font-size:11px;color:#888;", "");
  midToolbar.append(groupSelect, searchInput, btnSearch, btnAddTerm, btnEditTerm, btnDelTerm, modeHint);
  const termList = el("div", "flex:1;overflow:auto;padding:8px;");
  midPane.append(midToolbar, termList);

  const rightPane = el(
    "div",
    "width:260px;display:flex;flex-direction:column;flex-shrink:0;min-height:0;padding:8px;"
  );
  rightPane.appendChild(el("div", "font-size:12px;color:#888;margin-bottom:6px;", "已选"));
  const selectedBox = el("div", "flex:1;overflow:auto;");
  rightPane.appendChild(selectedBox);

  body.append(leftPane, midPane, rightPane);
  dialog.appendChild(body);

  function setStatus(t) {
    status.textContent = t || "";
  }

  function slotMeta(id) {
    return slots.find((s) => s.id === id) || { id, name_zh: id, selection_mode: "multi" };
  }

  function countSelected(slotId) {
    return (selected[slotId] || []).length;
  }

  function buildSelectedPayload() {
    const out = {};
    for (const [k, arr] of Object.entries(selected)) {
      if (arr && arr.length) out[k] = arr.map((x) => x.id);
    }
    return out;
  }

  function scheduleCompose() {
    if (composeTimer) clearTimeout(composeTimer);
    composeTimer = setTimeout(runCompose, 180);
  }

  async function runCompose() {
    const body = {
      selected: buildSelectedPayload(),
      enabled,
      nsfw: showNsfw,
      separator: sepInput.value,
      dedupe: chkDedupe.checked,
      enable_weight: chkWeight.checked,
      prefix: "",
      suffix: "",
    };
    try {
      const res = await apiPost("/builder/compose", body);
      if (!res.ok) {
        previewText.textContent = res.error || "compose 失败";
        return;
      }
      previewText.textContent = res.text || "（空）";
    } catch (e) {
      previewText.textContent = "compose 请求失败";
    }
  }

  function renderSlots() {
    slotList.innerHTML = "";
    for (const s of slots) {
      if (s.id === "nsfw_fluids" && s.default_collapsed && !fluidsExpanded && showNsfw) {
        // show a toggle row once
        if (!slotList.querySelector("[data-fluids-toggle]")) {
          const tog = el("button", css.btnSmall + "width:100%;margin-bottom:6px;", "▶ 展开 痕迹与体液");
          tog.dataset.fluidsToggle = "1";
          tog.onclick = () => {
            fluidsExpanded = true;
            renderSlots();
          };
          slotList.appendChild(tog);
        }
        continue;
      }
      const n = countSelected(s.id);
      const isOn = s.id === currentSlot;
      const btn = el("button", isOn ? css.slotOn : css.slotBtn, "");
      const en = enabled[s.id] !== false;
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.checked = en;
      chk.title = "启用该槽";
      chk.onclick = (e) => {
        e.stopPropagation();
        enabled[s.id] = chk.checked;
        scheduleCompose();
      };
      const label = el(
        "span",
        "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;",
        (s.nsfw ? "[N] " : "") + (s.name_zh || s.id)
      );
      const badge = el(
        "span",
        "font-size:11px;color:#8ab;min-width:16px;text-align:right;",
        n ? String(n) : ""
      );
      btn.append(chk, label, badge);
      btn.onclick = () => {
        currentSlot = s.id;
        activeGroup = "";
        searchInput.value = "";
        renderSlots();
        loadTerms();
      };
      slotList.appendChild(btn);
    }
  }

  function renderGroups(groups) {
    groupSelect.innerHTML = "";
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "全部分组";
    groupSelect.appendChild(all);
    for (const g of groups || []) {
      const o = document.createElement("option");
      o.value = g;
      o.textContent = g;
      if (g === activeGroup) o.selected = true;
      groupSelect.appendChild(o);
    }
  }

  function isSelected(slotId, id) {
    return (selected[slotId] || []).some((x) => x.id === id);
  }

  function toggleTerm(term, softSingle) {
    const sid = term.slot || currentSlot;
    if (!selected[sid]) selected[sid] = [];
    const idx = selected[sid].findIndex((x) => x.id === term.id);
    if (idx >= 0) {
      selected[sid].splice(idx, 1);
    } else if (softSingle) {
      selected[sid] = [
        {
          id: term.id,
          text_zh: term.text_zh || term.id,
          slot: sid,
          nsfw: !!term.nsfw,
        },
      ];
    } else {
      selected[sid].push({
        id: term.id,
        text_zh: term.text_zh || term.id,
        slot: sid,
        nsfw: !!term.nsfw,
      });
    }
    renderTerms(lastTerms);
    renderSelected();
    renderSlots();
    scheduleCompose();
  }

  function renderTerms(terms) {
    lastTerms = terms || [];
    termList.innerHTML = "";
    const meta = slotMeta(currentSlot);
    const softSingle = (meta.selection_mode || "") === "single_soft";
    modeHint.textContent = softSingle ? "建议 1～2 个（单击替换，Ctrl 追加）" : "多选";
    if (!lastTerms.length) {
      termList.appendChild(el("div", "color:#666;padding:12px;", "无词条"));
      return;
    }
    for (const t of lastTerms) {
      const on = isSelected(currentSlot, t.id);
      const row = el(
        "div",
        "display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;border-radius:4px;border:1px solid " +
          (on ? "#4a7dff" : "#333") +
          ";background:" +
          (on ? "#1e2a40" : "#222") +
          ";cursor:pointer;"
      );
      row.appendChild(el("span", "color:#8ab;width:18px;", on ? "☑" : "☐"));
      const title = el("span", "flex:1;", t.text_zh || t.id);
      if (t.nsfw) {
        title.appendChild(el("span", "margin-left:6px;color:#c9a;font-size:11px;", "[NSFW]"));
      }
      row.appendChild(title);
      if (t.group) row.appendChild(el("span", "color:#666;font-size:11px;", t.group));
      row.onclick = (e) => {
        activeTerm = t;
        const forceMulti = e.ctrlKey || e.metaKey;
        toggleTerm(t, softSingle && !forceMulti);
      };
      termList.appendChild(row);
    }
  }

  function renderSelected() {
    selectedBox.innerHTML = "";
    const order = slots.map((s) => s.id);
    let any = false;
    for (const sid of order) {
      const arr = selected[sid] || [];
      if (!arr.length) continue;
      any = true;
      const meta = slotMeta(sid);
      selectedBox.appendChild(
        el("div", "font-size:11px;color:#8ab;margin:8px 0 4px;", meta.name_zh || sid)
      );
      arr.forEach((item, i) => {
        const row = el(
          "div",
          "display:flex;align-items:center;gap:4px;padding:4px 6px;margin-bottom:3px;background:#222;border-radius:3px;border:1px solid #333;"
        );
        row.appendChild(el("span", "flex:1;font-size:12px;", item.text_zh || item.id));
        const up = el("button", css.btnSmall, "↑");
        up.onclick = () => {
          if (i <= 0) return;
          const a = selected[sid];
          [a[i - 1], a[i]] = [a[i], a[i - 1]];
          renderSelected();
          scheduleCompose();
        };
        const down = el("button", css.btnSmall, "↓");
        down.onclick = () => {
          const a = selected[sid];
          if (i >= a.length - 1) return;
          [a[i], a[i + 1]] = [a[i + 1], a[i]];
          renderSelected();
          scheduleCompose();
        };
        const del = el("button", css.btnSmall, "×");
        del.onclick = () => {
          selected[sid] = (selected[sid] || []).filter((x) => x.id !== item.id);
          renderSelected();
          renderTerms(lastTerms);
          renderSlots();
          scheduleCompose();
        };
        row.append(up, down, del);
        selectedBox.appendChild(row);
      });
    }
    if (!any) selectedBox.appendChild(el("div", "color:#666;", "尚未选择"));
  }

  async function loadSlots() {
    setStatus("加载槽位…");
    const res = await apiGet("/builder/slots?nsfw=" + (showNsfw ? "1" : "0"));
    if (!res.ok) {
      setStatus(res.error || "加载失败");
      return;
    }
    slots = res.slots || [];
    for (const s of slots) {
      if (enabled[s.id] === undefined) enabled[s.id] = true;
    }
    // drop nsfw selections when toggled off
    if (!showNsfw) {
      for (const k of Object.keys(selected)) {
        if (k.startsWith("nsfw_")) delete selected[k];
      }
    }
    if (!currentSlot || !slots.find((s) => s.id === currentSlot)) {
      currentSlot = slots[0]?.id || "";
    }
    renderSlots();
    renderSelected();
    if (currentSlot) await loadTerms();
    scheduleCompose();
    setStatus("槽位 " + slots.length);
  }

  async function loadTerms() {
    if (!currentSlot) {
      renderTerms([]);
      return;
    }
    const meta = slotMeta(currentSlot);
    renderGroups(meta.groups || []);
    const params = new URLSearchParams();
    params.set("nsfw", showNsfw ? "1" : "0");
    if (searchInput.value) params.set("q", searchInput.value);
    if (activeGroup) params.set("group", activeGroup);
    setStatus("加载词条…");
    const res = await apiGet("/builder/slot/" + encodeURIComponent(currentSlot) + "?" + params.toString());
    if (!res.ok) {
      setStatus(res.error || "加载失败");
      renderTerms([]);
      return;
    }
    // enrich selected text_zh from loaded terms
    const byId = {};
    for (const t of res.terms || []) byId[t.id] = t;
    if (selected[currentSlot]) {
      selected[currentSlot] = selected[currentSlot].map((x) => {
        const full = byId[x.id];
        return full
          ? { id: full.id, text_zh: full.text_zh, slot: currentSlot, nsfw: !!full.nsfw }
          : x;
      });
    }
    renderTerms(res.terms || []);
    renderSelected();
    setStatus((meta.name_zh || currentSlot) + " · " + (res.count || 0) + " 条");
  }

  function applyToNode() {
    if (!targetNode) {
      setStatus("无目标节点");
      return;
    }
    const typeName = targetNode.comfyClass || targetNode.type || "";
    const isSlotNode = String(typeName).startsWith("PromptKitSlot_");
    setWidget(targetNode, "separator", sepInput.value);
    setWidget(targetNode, "dedupe", !!chkDedupe.checked);
    setWidget(targetNode, "enable_weight", !!chkWeight.checked);
    setWidget(targetNode, "era_lock", eraSelect.value || "关闭");

    if (isSlotNode) {
      // 小节点：只写入当前槽（若无当前槽则取第一个有选择的槽）
      let sid = currentSlot;
      const payload = buildSelectedPayload();
      if (!payload[sid] || !payload[sid].length) {
        sid = Object.keys(payload).find((k) => payload[k] && payload[k].length) || sid;
      }
      const ids = payload[sid] || [];
      setWidget(targetNode, "term_ids", ids.join(", "));
      if (Object.prototype.hasOwnProperty.call(
        Object.fromEntries((targetNode.widgets || []).map((w) => [w.name, true])),
        "include_nsfw"
      )) {
        setWidget(targetNode, "include_nsfw", !!showNsfw);
      }
      // 仅本槽文案
      const terms = (selected[sid] || []).map((x) => x.text_zh || x.id).filter(Boolean);
      const sep = sepInput.value != null ? sepInput.value : ", ";
      const chunk = terms.join(sep);
      if (chunk) setWidget(targetNode, "panel_text", chunk);
      setStatus("已应用到分槽节点（" + (sid || "?") + " · " + ids.length + "）");
      return;
    }

    const state = {
      selected: buildSelectedPayload(),
      enabled,
    };
    setWidget(targetNode, "modules_state", JSON.stringify(state, null, 0));
    setWidget(targetNode, "include_nsfw", !!showNsfw);
    setWidget(targetNode, "era_lock", eraSelect.value || "关闭");
    const text = previewText.textContent || "";
    if (text && text !== "（尚未选择）" && text !== "（空）") {
      setWidget(targetNode, "panel_text", text);
    }
    setStatus("已应用到节点（含时代锁定：" + (eraSelect.value || "关闭") + "）");
  }

  // events
  chkNsfw.onchange = async () => {
    showNsfw = chkNsfw.checked;
    fluidsExpanded = false;
    await loadSlots();
  };
  eraSelect.onchange = () => {
    setStatus("时代锁定：" + (eraSelect.value || "关闭") + "（应用到节点后写入大节点）");
  };
  btnPreset.onclick = async () => {
    const pid = presetSelect.value;
    if (!pid) {
      setStatus("请先选择预设");
      return;
    }
    try {
      const res = await apiPost("/builder/preset/apply", { id: pid, seed: 0 });
      if (!res.ok) {
        setStatus(res.error || "预设失败");
        return;
      }
      if (res.era && ERA_OPTS.indexOf(res.era) >= 0) {
        eraSelect.value = res.era;
      }
      selected = {};
      const termsMap = res.terms || {};
      for (const [sid, arr] of Object.entries(termsMap)) {
        selected[sid] = (arr || []).map((x) => ({
          id: x.id,
          text_zh: x.text_zh || x.id,
          slot: sid,
          group: x.group || "",
          nsfw: !!x.nsfw,
        }));
      }
      // 启用有选择的槽
      for (const sid of Object.keys(selected)) {
        enabled[sid] = true;
      }
      renderSelected();
      renderSlots();
      await loadTerms();
      scheduleCompose();
      setStatus("已应用预设「" + (presetSelect.selectedOptions[0]?.textContent || pid) + "」");
    } catch (_e) {
      setStatus("预设请求失败");
    }
  };
  btnReload.onclick = async () => {
    try {
      const res = await apiPost("/builder/reload", {});
      if (!res.ok) {
        setStatus(res.error || "刷新失败");
        return;
      }
      await loadSlots();
      await loadTerms();
      scheduleCompose();
      setStatus("词表已刷新（槽 " + (res.slots || "?") + "）；节点下拉若过期请重建节点或重启");
    } catch (_e) {
      setStatus("刷新请求失败");
    }
  };
  btnValidate.onclick = async () => {
    try {
      const res = await apiGet("/builder/validate");
      if (!res.ok) {
        setStatus(res.error || "校验失败");
        return;
      }
      const err = res.error_count || 0;
      const warn = res.warn_count || 0;
      const issues = res.issues || [];
      const top = issues.slice(0, 5).map((x) => (x.slot || "") + "/" + (x.group || "") + ":" + (x.msg || "")).join("；");
      setStatus("校验：错误 " + err + " / 警告 " + warn + (top ? " · " + top : " · 无严重问题"));
    } catch (_e) {
      setStatus("校验请求失败");
    }
  };
  sepInput.onchange = scheduleCompose;
  sepInput.oninput = scheduleCompose;
  chkDedupe.onchange = scheduleCompose;
  chkWeight.onchange = scheduleCompose;
  groupSelect.onchange = () => {
    activeGroup = groupSelect.value || "";
    loadTerms();
  };
  btnSearch.onclick = () => loadTerms();
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadTerms();
  });
  btnClear.onclick = () => {
    selected = {};
    renderSelected();
    renderTerms(lastTerms);
    renderSlots();
    scheduleCompose();
    setStatus("已清空");
  };
  btnApply.onclick = applyToNode;
  btnCopy.onclick = async () => {
    const text = previewText.textContent || "";
    try {
      await navigator.clipboard.writeText(text);
      setStatus("已复制");
    } catch {
      setStatus("复制失败");
    }
  };
  btnToSkill.onclick = () => {
    const text = (previewText.textContent || "").trim();
    if (!text || text === "（空）" || text.indexOf("compose") >= 0) {
      setStatus("请先组词，待预览有内容后再沉淀");
      return;
    }
    if (!window.PromptKitSkill || !window.PromptKitSkill.openGenerateWizard) {
      setStatus("Skill 面板脚本未加载，请完整重启 ComfyUI");
      return;
    }
    const title = "结构化组词沉淀";
    window.PromptKitSkill.openGenerateWizard({
      kind: "from_builder",
      title_zh: title,
      name: window.PromptKitSkill.suggestSkillName(title + "-" + text.slice(0, 16)),
      source_text: text,
      tags: ["结构化", "沉淀"],
      description:
        "Recreate structured prompt composition. Use when rebuilding this modular look. 复现该结构化组词结果。",
      onSaved: (skill) => setStatus("已沉淀为 Skill：" + ((skill && skill.name) || "")),
    });
  };

  btnAddTerm.onclick = () => {
    if (!currentSlot) { setStatus("请先选择槽位"); return; }
    openFormModal("新增词条", [
      { key: "text_zh", label: "中文词条", type: "textarea", rows: 3, placeholder: "输入中文描述" },
      { key: "group", label: "分组（可空）", type: "text", value: activeGroup || "", placeholder: "如：发色" },
    ], [
      { label: "取消", primary: false, onClick: async (_v, close) => close() },
      { label: "保存", primary: true, onClick: async (v, close) => {
          if (!(v.text_zh || "").trim()) { setStatus("词条不能为空"); return; }
          const res = await apiPost("/builder/term", {
            action: "upsert", slot: currentSlot, text_zh: v.text_zh.trim(),
            group: (v.group || "").trim(),
            nsfw: showNsfw && (currentSlot.startsWith("nsfw_") || false),
          });
          if (!res.ok) { setStatus(res.error || "新增失败"); return; }
          close(); setStatus("已新增词条"); await loadTerms(); scheduleCompose();
        }},
      { label: "继续添加", primary: false, onClick: async (v, close) => {
          if (!(v.text_zh || "").trim()) { setStatus("词条不能为空"); return; }
          const res = await apiPost("/builder/term", {
            action: "upsert", slot: currentSlot, text_zh: v.text_zh.trim(),
            group: (v.group || "").trim(),
            nsfw: showNsfw && (currentSlot.startsWith("nsfw_") || false),
          });
          if (!res.ok) { setStatus(res.error || "新增失败"); return; }
          setStatus("已新增，可继续填写");
          await loadTerms(); scheduleCompose();
          close();
          btnAddTerm.onclick();
        }},
    ]);
  };
  btnEditTerm.onclick = () => {
    if (!activeTerm) { setStatus("请先点击一条词条"); return; }
    openFormModal("编辑词条", [
      { key: "text_zh", label: "中文词条", type: "textarea", rows: 3, value: activeTerm.text_zh || "" },
      { key: "group", label: "分组（可空）", type: "text", value: activeTerm.group || "" },
    ], [
      { label: "取消", primary: false, onClick: async (_v, close) => close() },
      { label: "保存", primary: true, onClick: async (v, close) => {
          if (!(v.text_zh || "").trim()) { setStatus("不能为空"); return; }
          const res = await apiPost("/builder/term", {
            action: "upsert", slot: activeTerm.slot || currentSlot, id: activeTerm.id,
            text_zh: v.text_zh.trim(), group: (v.group || "").trim(), nsfw: !!activeTerm.nsfw,
          });
          if (!res.ok) { setStatus(res.error || "保存失败"); return; }
          close(); activeTerm = null; setStatus("已保存词条"); await loadTerms(); scheduleCompose();
        }},
    ]);
  };
  btnDelTerm.onclick = () => {
    if (!activeTerm) { setStatus("请先点击一条词条"); return; }
    const name = activeTerm.text_zh || activeTerm.id;
    openConfirmModal("确认删除词条「" + name + "」？系统精选也可删除，请谨慎。", async () => {
      const res = await apiPost("/builder/term", {
        action: "delete", slot: activeTerm.slot || currentSlot, id: activeTerm.id,
      });
      if (!res.ok) { setStatus(res.error || "删除失败"); return; }
      const sid = activeTerm.slot || currentSlot;
      if (selected[sid]) selected[sid] = selected[sid].filter((x) => x.id !== activeTerm.id);
      activeTerm = null;
      setStatus("已删除");
      await loadTerms(); renderSelected(); renderSlots(); scheduleCompose();
    });
  };

  loadSlots();
}

/** NSFW 附加槽行（方案B：槽名·模式） */
const NSFW_SLOT_PREFIXES = [
  "着装服饰",
  "身体与暴露",
  "体位",
  "行为与互动",
  "道具与束缚",
  "痕迹与体液",
];
function _pkIsNsfwSlotWidget(name) {
  if (!name) return false;
  for (const p of NSFW_SLOT_PREFIXES) {
    if (name === p || name.startsWith(p + "·")) return true;
  }
  return false;
}

function _pkGetNsfwToggleValue(node) {
  const w = node?.widgets?.find((x) => x.name === "含NSFW" || x.name === "include_nsfw");
  if (!w) return false;
  const v = w.value;
  return v === true || v === 1 || v === "true" || v === "True";
}

function _pkSetWidgetVisible(widget, visible) {
  if (!widget) return;
  if (visible) {
    widget.hidden = false;
    // 去掉隐藏时挂上的零高度，恢复默认测量
    if (widget._pkSizeHidden) {
      delete widget.computeSize;
      widget._pkSizeHidden = false;
    }
  } else {
    widget.hidden = true;
    // 不改 type，避免 combo 恢复失败；仅压高度让 computeSize 不算进去
    widget.computeSize = function () {
      return [0, -4];
    };
    widget._pkSizeHidden = true;
  }
}

function _pkRefreshNodeSize(node) {
  if (!node) return;
  try {
    let visible = 0;
    for (const w of node.widgets || []) {
      if (w && !w.hidden) visible += 1;
    }
    // 标题区 + 每控件约 26px + 底边，保证打开 NSFW 后高度够用
    const minH = 50 + visible * 26 + 24;
    const computed = typeof node.computeSize === "function" ? node.computeSize() : null;
    const w = Math.max(
      (node.size && node.size[0]) || 0,
      (computed && computed[0]) || 0,
      280
    );
    // 不与旧高度取 max，否则关闭 NSFW 后高度收不回去、打开时也可能被错误缓存卡住
    const h = Math.max((computed && computed[1]) || 0, minH);
    if (typeof node.setSize === "function") {
      node.setSize([w, h]);
    }
    if (node.size) {
      node.size[0] = w;
      node.size[1] = h;
    }
  } catch (_e) {
    /* ignore */
  }
  node.setDirtyCanvas?.(true, true);
  try {
    app.graph?.setDirtyCanvas?.(true, true);
  } catch (_e2) {
    /* ignore */
  }
}


/** 方案B3：槽组小浮窗 —— 仅编辑当前槽的 groups，写入「组词状态」 */
const SLOT_LABEL_TO_ID = {
  风格媒介: "style",
  镜头构图: "camera",
  人物主体: "subject",
  面部妆容: "face",
  发型发色: "hair",
  表情神态: "expression",
  姿态动作: "pose",
  服装穿搭: "clothing",
  配饰道具: "accessories",
  场景环境: "scene",
  光影氛围: "lighting",
  着装服饰: "nsfw_clothing",
  身体与暴露: "nsfw_body",
  体位: "nsfw_pose",
  行为与互动: "nsfw_act",
  道具与束缚: "nsfw_props",
  痕迹与体液: "nsfw_fluids",
};

function _pkParseSlotStates(raw) {
  if (!raw) return {};
  if (typeof raw === "object") return raw;
  try {
    const o = JSON.parse(String(raw));
    return o && typeof o === "object" ? o : {};
  } catch (_e) {
    return {};
  }
}

function _pkGetSlotModeWidget(node, slotId) {
  const label = Object.keys(SLOT_LABEL_TO_ID).find((k) => SLOT_LABEL_TO_ID[k] === slotId);
  if (!label || !node?.widgets) return null;
  const name = label + "·模式";
  return node.widgets.find((w) => w.name === name) || null;
}

function openSlotGroupFloat(node, slotId, slotNameZh) {
  if (!node || !slotId) return;
  const isNsfwSlot = String(slotId).startsWith("nsfw_");
  const nsfwOn = _pkGetNsfwToggleValue(node);
  if (isNsfwSlot && !nsfwOn) {
    alert("请先开启「含 NSFW」再编辑此槽");
    return;
  }

  const ov = el(
    "div",
    "position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;"
  );
  const box = el(
    "div",
    "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:14px 16px;width:400px;max-width:94vw;max-height:86vh;display:flex;flex-direction:column;color:#eee;font:13px system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,0.5);"
  );
  const title = el("div", "font-weight:700;font-size:14px;margin-bottom:8px;", "编辑槽 · " + (slotNameZh || slotId));
  const hint = el(
    "div",
    "font-size:11px;color:#888;margin-bottom:10px;line-height:1.4;",
    "各组：不选 / 随机 / 指定。确定后写入「组词状态」并设为「自定义」。已是自定义时，可选模式「编辑组…」再次打开本浮窗。"
  );
  const list = el("div", "flex:1;overflow:auto;min-height:120px;max-height:52vh;border:1px solid #333;border-radius:6px;padding:8px;background:#181818;");
  const status = el("div", "font-size:11px;color:#9ab;margin:8px 0 0;", "加载中…");
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;margin-top:12px;");
  const btnCancel = el("button", css.btnGhost, "取消");
  const btnReset = el("button", css.btnGhost, "重置不选");
  const btnOk = el("button", css.btnBlue, "确定");
  row.append(btnReset, btnCancel, btnOk);
  box.append(title, hint, list, status, row);
  ov.appendChild(box);
  document.body.appendChild(ov);

  const close = () => ov.remove();
  const normalizeModeAfterClose = (saved) => {
    const mw = _pkGetSlotModeWidget(node, slotId);
    if (!mw) return;
    node._pkSkipGroupFloat = true;
    try {
      if (saved) {
        mw.value = "自定义";
      } else if (mw.value === "编辑组…") {
        // 取消时：已有组状态则回到自定义，否则不选
        const st = _pkParseSlotStates(getWidget(node, "slot_states", "{}"));
        const has = st[slotId] && st[slotId].groups;
        mw.value = has ? "自定义" : "不选";
      }
      if (mw.callback) mw.callback(mw.value);
    } finally {
      queueMicrotask(() => {
        node._pkSkipGroupFloat = false;
      });
    }
  };
  btnCancel.onclick = () => {
    normalizeModeAfterClose(false);
    close();
  };
  ov.addEventListener("mousedown", (e) => {
    if (e.target === ov) {
      normalizeModeAfterClose(false);
      close();
    }
  });

  /** @type {Record<string, HTMLSelectElement>} */
  const selects = {};
  const OPS = ["(不选)", "(随机)"];

  function currentStates() {
    return _pkParseSlotStates(getWidget(node, "slot_states", "{}"));
  }

  function fillFromState(groups) {
    const st = currentStates();
    const slotSt = st[slotId] || {};
    const gcfg = slotSt.groups || slotSt;
    for (const g of groups) {
      const sel = selects[g];
      if (!sel) continue;
      const cfg = gcfg && gcfg[g];
      if (!cfg || typeof cfg !== "object") {
        sel.value = "(不选)";
        continue;
      }
      const op = String(cfg.op || "none").toLowerCase();
      if (op === "random" || op === "随机") {
        sel.value = "(随机)";
      } else if (op === "pick" || op === "指定") {
        const text = (cfg.text || "").trim();
        // 若选项中无该词则临时追加
        if (text && ![...sel.options].some((o) => o.value === text)) {
          const o = document.createElement("option");
          o.value = text;
          o.textContent = text;
          sel.appendChild(o);
        }
        sel.value = text || "(不选)";
      } else {
        sel.value = "(不选)";
      }
    }
  }

  btnReset.onclick = () => {
    for (const g of Object.keys(selects)) {
      selects[g].value = "(不选)";
    }
  };

  btnOk.onclick = () => {
    const groups = {};
    for (const [g, sel] of Object.entries(selects)) {
      const v = (sel.value || "").trim();
      if (!v || v === "(不选)") {
        groups[g] = { op: "none" };
      } else if (v === "(随机)") {
        groups[g] = { op: "random" };
      } else {
        groups[g] = { op: "pick", text: v };
      }
    }
    // 去掉全 none 可压缩；保留也可
    const st = currentStates();
    st[slotId] = { mode: "custom", groups };
    setWidget(node, "slot_states", JSON.stringify(st, null, 0));
    const mw = _pkGetSlotModeWidget(node, slotId);
    if (mw) {
      node._pkSkipGroupFloat = true;
      try {
        mw.value = "自定义";
        if (mw.callback) mw.callback("自定义");
      } finally {
        queueMicrotask(() => {
          node._pkSkipGroupFloat = false;
        });
      }
    }
    node.setDirtyCanvas?.(true, true);
    close();
  };

  (async () => {
    try {
      // 槽元数据 + 词条
      const metaRes = await apiGet("/builder/slots?nsfw=1");
      const slots = metaRes.slots || metaRes.items || [];
      let meta = slots.find((s) => s.id === slotId);
      if (!meta) {
        // 兼容不同返回
        const all = Array.isArray(metaRes) ? metaRes : slots;
        meta = (all || []).find((s) => s.id === slotId);
      }
      let groupNames = (meta && meta.groups) || [];
      const termRes = await apiGet(
        "/builder/slot/" + encodeURIComponent(slotId) + "?nsfw=" + (isNsfwSlot || nsfwOn ? "1" : "0") + "&limit=2000"
      );
      const terms = termRes.terms || [];
      const byG = {};
      for (const r of terms) {
        const g = (r.group || "").trim() || "其它/未归组";
        if (g.startsWith("N·")) continue; // 大节点浮窗不编薄 overlay
        if (!byG[g]) byG[g] = [];
        const t = (r.text_zh || "").trim();
        if (t) byG[g].push(t);
      }
      if (!groupNames.length) groupNames = Object.keys(byG);
      // 补数据里有但 index 未声明的组
      for (const g of Object.keys(byG)) {
        if (!groupNames.includes(g)) groupNames.push(g);
      }
      list.innerHTML = "";
      if (!groupNames.length) {
        status.textContent = "该槽暂无分组";
        return;
      }
      for (const g of groupNames) {
        const line = el("div", "display:flex;align-items:center;gap:8px;margin-bottom:8px;");
        const lab = el("div", "width:96px;flex-shrink:0;color:#bbb;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;", g);
        lab.title = g;
        const sel = document.createElement("select");
        sel.style.cssText = css.field + "flex:1;min-width:0;";
        const words = byG[g] || [];
        for (const opt of ["(不选)", "(随机)", ...words.slice(0, 400)]) {
          const o = document.createElement("option");
          o.value = opt;
          o.textContent = opt.length > 36 ? opt.slice(0, 34) + "…" : opt;
          sel.appendChild(o);
        }
        selects[g] = sel;
        line.append(lab, sel);
        list.appendChild(line);
      }
      fillFromState(groupNames);
      status.textContent = "共 " + groupNames.length + " 组 · " + terms.length + " 条词";
    } catch (e) {
      status.textContent = "加载失败";
    }
  })();
}

function bindStructuredSlotEditors(node) {
  if (!node?.widgets || node._pkSlotEditBound) return;
  node._pkSlotEditBound = true;

  // 模式切到「自定义」时打开浮窗
  for (const w of node.widgets) {
    if (!w.name || !String(w.name).endsWith("·模式")) continue;
    const label = String(w.name).replace(/·模式$/, "");
    const slotId = SLOT_LABEL_TO_ID[label];
    if (!slotId) continue;
    const prev = w.callback;
    w.callback = function (value) {
      const r = prev?.apply(this, arguments);
      if (node._pkSkipGroupFloat) return r;
      const v = value != null ? value : w.value;
      // 自定义 / 编辑组… 都打开浮窗；「编辑组…」可在已是自定义时再次点选打开
      if (v === "自定义" || v === "编辑组…") {
        queueMicrotask(() => openSlotGroupFloat(node, slotId, label));
      }
      return r;
    };
  }

  // 按钮：选择槽后编辑
  if (!node._pkEditSlotBtn) {
    node._pkEditSlotBtn = node.addWidget("button", "编辑槽组（浮窗）", null, () => {
      // 弹出简单选槽
      const ov = el(
        "div",
        "position:fixed;inset:0;z-index:100001;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;"
      );
      const box = el(
        "div",
        "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:14px;width:320px;color:#eee;font:13px system-ui,sans-serif;"
      );
      box.appendChild(el("div", "font-weight:700;margin-bottom:10px;", "选择要编辑的槽"));
      const sel = document.createElement("select");
      sel.style.cssText = css.field + "width:100%;margin-bottom:12px;";
      const nsfwOn = _pkGetNsfwToggleValue(node);
      for (const [lab, id] of Object.entries(SLOT_LABEL_TO_ID)) {
        if (String(id).startsWith("nsfw_") && !nsfwOn) continue;
        const o = document.createElement("option");
        o.value = id;
        o.textContent = lab;
        sel.appendChild(o);
      }
      box.appendChild(sel);
      const row = el("div", "display:flex;gap:8px;justify-content:flex-end;");
      const b1 = el("button", css.btnGhost, "取消");
      const b2 = el("button", css.btnBlue, "编辑");
      b1.onclick = () => ov.remove();
      b2.onclick = () => {
        const id = sel.value;
        const lab = Object.keys(SLOT_LABEL_TO_ID).find((k) => SLOT_LABEL_TO_ID[k] === id) || id;
        ov.remove();
        openSlotGroupFloat(node, id, lab);
      };
      row.append(b1, b2);
      box.appendChild(row);
      ov.appendChild(box);
      document.body.appendChild(ov);
    });
    if (node._pkEditSlotBtn) node._pkEditSlotBtn.serialize = false;
  }
}


/**
 * 按「含NSFW」开关显隐大节点上的 NSFW 附加槽。
 * 控件始终注册（工作流可序列化）；关闭时仅隐藏，后端本就不参与组词。
 * @param {object} node
 * @param {boolean} [forceShow] 开关 callback 里传入的新值，避免读到旧 value
 */
function applyStructuredNsfwVisibility(node, forceShow) {
  if (!node || !node.widgets) return;
  const isBig =
    node.comfyClass === "PromptKitStructuredBuilder" ||
    node.type === "PromptKitStructuredBuilder" ||
    (node.title && String(node.title).includes("结构化生成"));
  if (!isBig) return;

  const show = typeof forceShow === "boolean" ? forceShow : _pkGetNsfwToggleValue(node);
  for (const w of node.widgets) {
    if (!_pkIsNsfwSlotWidget(w.name)) continue;
    _pkSetWidgetVisible(w, show);
  }
  _pkRefreshNodeSize(node);
  // 再刷一帧，等 LiteGraph 布局稳定
  requestAnimationFrame(() => {
    _pkRefreshNodeSize(node);
  });
}

function bindStructuredNsfwToggle(node) {
  if (!node?.widgets) return;
  const toggle = node.widgets.find((x) => x.name === "含NSFW" || x.name === "include_nsfw");
  if (!toggle) return;
  if (!node._pkNsfwVisBound) {
    node._pkNsfwVisBound = true;
    const prev = toggle.callback;
    toggle.callback = function (value) {
      const r = prev?.apply(this, arguments);
      // ComfyUI 布尔控件常把新值作为第一参数传入
      let show;
      if (typeof value === "boolean") show = value;
      else if (value === 0 || value === 1) show = !!value;
      else show = _pkGetNsfwToggleValue(node);
      applyStructuredNsfwVisibility(node, show);
      return r;
    };
  }
  applyStructuredNsfwVisibility(node);
}

function addOpenButton(nodeType, nodeData) {
  if (!isBuilderNodeType(nodeData.name)) return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const r = onNodeCreated?.apply(this, arguments);
    if (!this._pkBuilderBtn) {
      this._pkBuilderBtn = this.addWidget("button", "打开结构化面板", null, () => {
        openPanel(this);
      });
      if (this._pkBuilderBtn) this._pkBuilderBtn.serialize = false;
    }
    // 大节点：NSFW 槽随开关显隐
    if (nodeData.name === "PromptKitStructuredBuilder") {
      const self = this;
      // widgets 可能稍后才齐，微任务 + 下一帧各刷一次
      queueMicrotask(() => {
        bindStructuredNsfwToggle(self);
        applyStructuredNsfwVisibility(self);
        bindStructuredSlotEditors(self);
      });
      requestAnimationFrame?.(() => {
        bindStructuredNsfwToggle(self);
        applyStructuredNsfwVisibility(self);
        bindStructuredSlotEditors(self);
      });
    }
    return r;
  };

  if (nodeData.name === "PromptKitStructuredBuilder") {
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      const r = onConfigure?.apply(this, arguments);
      const self = this;
      queueMicrotask(() => {
        bindStructuredNsfwToggle(self);
        applyStructuredNsfwVisibility(self);
        bindStructuredSlotEditors(self);
      });
      return r;
    };
  }
}

app.registerExtension({
  name: "PromptKit.BuilderPanel",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    addOpenButton(nodeType, nodeData);
  },
  async nodeCreated(node) {
    // 双保险：图加载后也按开关收敛一次
    if (
      node?.comfyClass === "PromptKitStructuredBuilder" ||
      node?.type === "PromptKitStructuredBuilder"
    ) {
      queueMicrotask(() => {
        bindStructuredNsfwToggle(node);
        applyStructuredNsfwVisibility(node);
        bindStructuredSlotEditors(node);
      });
    }
  },
});
