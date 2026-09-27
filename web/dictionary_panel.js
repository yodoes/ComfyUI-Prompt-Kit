/**
 * Prompt-Kit 字典面板
 * - 在「字典选词 / 字典管理 / 字典面板」节点上挂「打开字典」按钮
 * - 弹层：左侧分类树 + 搜索 + 词条列表 + 已选区
 * - 「应用到节点」写入目标节点的 panel_text / text 类 widget
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/prompt-kit";
const NODE_TYPES = new Set([
  "PromptKitDictionaryPick",
  "PromptKitDictionaryManage",
  "PromptKitDictionaryPanel",
]);

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
};

async function apiGet(path) {
  const res = await api.fetchApi(BASE + path);
  return await res.json();
}

async function apiPost(path, body) {
  const res = await api.fetchApi(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return await res.json();
}

function el(tag, style, text) {
  const n = document.createElement(tag);
  if (style) n.style.cssText = style;
  if (text != null) n.textContent = text;
  return n;
}

/** @type {{ id:string, display:string }[]} */
let selected = [];

function selectedIds() {
  return new Set(selected.map((s) => s.id));
}

function openPanel(targetNode) {
  selected = [];

  const overlay = el(
    "div",
    "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"
  );
  const dialog = el(
    "div",
    "background:#1a1a1a;border:1px solid #555;border-radius:10px;width:960px;max-width:96vw;height:82vh;max-height:900px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.55);color:#eee;font:13px/1.4 system-ui,sans-serif;"
  );
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  // ---- header ----
  const header = el(
    "div",
    "display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #333;flex-shrink:0;"
  );
  header.appendChild(el("div", "font-weight:700;font-size:15px;", "PromptKit · 字典面板"));
  const status = el("span", "color:#8ab;font-size:12px;margin-left:auto;", "");
  header.appendChild(status);
  const btnClose = el("button", css.btnGhost, "关闭");
  btnClose.onclick = () => overlay.remove();
  header.appendChild(btnClose);
  dialog.appendChild(header);

  // ---- toolbar ----
  const toolbar = el(
    "div",
    "display:flex;gap:8px;padding:8px 14px;border-bottom:1px solid #333;flex-shrink:0;align-items:center;flex-wrap:wrap;"
  );
  const searchInput = el("input");
  searchInput.type = "text";
  searchInput.placeholder = "搜索关键词（中英）";
  searchInput.style.cssText = css.field + "flex:1;min-width:180px;";
  const langSelect = el("select");
  langSelect.style.cssText = css.field + "width:90px;";
  ["zh", "en", "both"].forEach((v) => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    langSelect.appendChild(o);
  });
  const btnSearch = el("button", css.btnBlue, "搜索");
  const btnFavView = el("button", css.btnGhost, "收藏夹");
  const btnClearSel = el("button", css.btnGhost, "清空已选");
  toolbar.append(searchInput, langSelect, btnSearch, btnFavView, btnClearSel);
  dialog.appendChild(toolbar);

  // ---- body: tree | list | selected ----
  const body = el("div", "display:flex;flex:1;min-height:0;");
  const treePane = el(
    "div",
    "width:220px;border-right:1px solid #333;overflow:auto;padding:8px;flex-shrink:0;"
  );
  const listPane = el("div", "flex:1;overflow:auto;padding:8px;min-width:0;");
  const selPane = el(
    "div",
    "width:240px;border-left:1px solid #333;display:flex;flex-direction:column;flex-shrink:0;"
  );
  body.append(treePane, listPane, selPane);
  dialog.appendChild(body);

  // selected area
  const selTitle = el(
    "div",
    "padding:8px 10px;border-bottom:1px solid #333;font-weight:600;flex-shrink:0;",
    "已选 (0)"
  );
  const selList = el("div", "flex:1;overflow:auto;padding:6px;");
  const selFooter = el(
    "div",
    "padding:8px;border-top:1px solid #333;display:flex;flex-direction:column;gap:6px;flex-shrink:0;"
  );
  const btnApply = el("button", css.btnBlue, "应用到节点");
  const btnCopy = el("button", css.btnGhost, "复制文本");
  selFooter.append(btnApply, btnCopy);
  selPane.append(selTitle, selList, selFooter);

  // ---- state ----
  let currentSub = null;
  let listOffset = 0;
  const PAGE = 50;

  function refreshSelUI() {
    selTitle.textContent = `已选 (${selected.length})`;
    selList.innerHTML = "";
    selected.forEach((item, idx) => {
      const row = el(
        "div",
        "display:flex;align-items:flex-start;gap:4px;padding:4px 2px;border-bottom:1px solid #2a2a2a;"
      );
      const t = el("div", "flex:1;word-break:break-all;", item.display);
      const rm = el("button", css.btnSmall, "×");
      rm.onclick = () => {
        selected.splice(idx, 1);
        refreshSelUI();
        // re-render list checkmarks cheaply
      };
      row.append(t, rm);
      selList.appendChild(row);
    });
  }

  function toggleSelect(entry) {
    const ids = selectedIds();
    if (ids.has(entry.id)) {
      selected = selected.filter((s) => s.id !== entry.id);
    } else {
      selected.push({ id: entry.id, display: entry.display });
    }
    refreshSelUI();
  }

  function renderEntries(entries, total, append) {
    if (!append) listPane.innerHTML = "";
    if (!entries.length && !append) {
      listPane.appendChild(el("div", "color:#888;padding:12px;", "无结果"));
      status.textContent = "0 条";
      return;
    }
    const ids = selectedIds();
    entries.forEach((e) => {
      const row = el(
        "div",
        "display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid #2a2a2a;cursor:pointer;"
      );
      row.onmouseenter = () => (row.style.background = "#252525");
      row.onmouseleave = () => (row.style.background = "transparent");
      const check = el("input");
      check.type = "checkbox";
      check.checked = ids.has(e.id);
      check.onclick = (ev) => {
        ev.stopPropagation();
        toggleSelect(e);
        check.checked = selectedIds().has(e.id);
      };
      const main = el("div", "flex:1;min-width:0;");
      main.appendChild(el("div", "word-break:break-all;", e.display));
      const meta = el(
        "div",
        "color:#777;font-size:11px;margin-top:2px;",
        `${e.subcategory || ""}  ${e.id || ""}`
      );
      main.appendChild(meta);
      const star = el("button", css.btnSmall, "★");
      star.title = "收藏/取消";
      star.onclick = async (ev) => {
        ev.stopPropagation();
        const r = await apiPost("/favorites", { action: "toggle", id: e.id });
        status.textContent = r.favorited ? "已收藏" : "已取消收藏";
      };
      row.onclick = () => {
        toggleSelect(e);
        check.checked = selectedIds().has(e.id);
      };
      row.append(check, main, star);
      listPane.appendChild(row);
    });
    status.textContent = total != null ? `显示 ${entries.length} / 约 ${total}` : `${entries.length} 条`;

    if (currentSub && total != null && listOffset + entries.length < total) {
      const more = el("button", css.btnGhost + "margin:8px;width:calc(100% - 16px);", "加载更多");
      more.onclick = async () => {
        listOffset += PAGE;
        more.remove();
        const data = await apiGet(
          `/entries?subcategory=${encodeURIComponent(currentSub)}&offset=${listOffset}&limit=${PAGE}&lang=${langSelect.value}`
        );
        if (data.ok) renderEntries(data.entries || [], data.total, true);
      };
      listPane.appendChild(more);
    }
  }

  async function loadTree() {
    treePane.innerHTML = el("div", "color:#888;", "加载分类…").outerHTML;
    const data = await apiGet("/tree?lang=zh");
    treePane.innerHTML = "";
    if (!data.ok) {
      treePane.appendChild(el("div", "color:#c66;", data.error || "加载失败"));
      return;
    }
    (data.tree || []).forEach((cat) => {
      const catEl = el("div", "margin-bottom:6px;");
      const title = el(
        "div",
        "font-weight:600;padding:4px 2px;cursor:default;color:#bcd;",
        cat.name || cat.id
      );
      catEl.appendChild(title);
      (cat.children || []).forEach((ch) => {
        const item = el(
          "div",
          "padding:4px 8px;cursor:pointer;border-radius:4px;color:#ddd;",
          ch.name || ch.id
        );
        item.onmouseenter = () => (item.style.background = "#2a2a2a");
        item.onmouseleave = () => {
          if (currentSub !== ch.id) item.style.background = "transparent";
        };
        item.onclick = async () => {
          currentSub = ch.id;
          listOffset = 0;
          [...treePane.querySelectorAll("[data-sub]")].forEach((n) => {
            n.style.background = "transparent";
            n.style.color = "#ddd";
          });
          item.dataset.sub = ch.id;
          item.style.background = "#2a3a5a";
          item.style.color = "#fff";
          status.textContent = "加载中…";
          const data2 = await apiGet(
            `/entries?subcategory=${encodeURIComponent(ch.id)}&offset=0&limit=${PAGE}&lang=${langSelect.value}`
          );
          if (data2.ok) renderEntries(data2.entries || [], data2.total, false);
          else listPane.innerHTML = `<div style="color:#c66;padding:12px">${data2.error || "失败"}</div>`;
        };
        catEl.appendChild(item);
      });
      treePane.appendChild(catEl);
    });
  }

  async function doSearch() {
    currentSub = null;
    listOffset = 0;
    const q = searchInput.value.trim();
    status.textContent = "搜索中…";
    const data = await apiGet(
      `/search?q=${encodeURIComponent(q)}&limit=80&lang=${langSelect.value}`
    );
    if (data.ok) renderEntries(data.entries || [], data.total, false);
    else listPane.innerHTML = `<div style="color:#c66;padding:12px">${data.error || "失败"}</div>`;
  }

  async function doFav() {
    currentSub = null;
    status.textContent = "加载收藏…";
    const data = await apiGet(`/favorites?lang=${langSelect.value}`);
    if (data.ok) renderEntries(data.entries || [], data.total, false);
  }

  btnSearch.onclick = doSearch;
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
  btnFavView.onclick = doFav;
  btnClearSel.onclick = () => {
    selected = [];
    refreshSelUI();
  };

  btnCopy.onclick = async () => {
    const text = selected.map((s) => s.display).join(", ");
    try {
      await navigator.clipboard.writeText(text);
      status.textContent = "已复制";
    } catch {
      status.textContent = "复制失败";
    }
  };

  btnApply.onclick = () => {
    const text = selected.map((s) => s.display).join(", ");
    if (!targetNode) {
      status.textContent = "无目标节点";
      return;
    }
    const widgets = targetNode.widgets || [];
    // 优先写入 panel_text，其次 text，再次 query
    const order = ["panel_text", "text", "query"];
    let w = null;
    for (const name of order) {
      w = widgets.find((x) => x.name === name);
      if (w) break;
    }
    if (!w) {
      // 任意 STRING
      w = widgets.find((x) => x.type === "text" || x.type === "customtext");
    }
    if (!w) {
      status.textContent = "节点上没有可写入的文本框";
      return;
    }
    w.value = text;
    if (w.callback) w.callback(text);
    targetNode.setDirtyCanvas?.(true, true);
    status.textContent = `已写入「${w.name}」`;
    // 不自动关，方便继续选
  };

  refreshSelUI();
  loadTree();
}

function addOpenButton(nodeType, nodeData) {
  if (!NODE_TYPES.has(nodeData.name)) return;

  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const r = onNodeCreated?.apply(this, arguments);
    // 避免重复加按钮
    if (this._pkDictBtn) return r;
    this._pkDictBtn = this.addWidget("button", "打开字典面板", null, () => {
      openPanel(this);
    });
    return r;
  };
}

app.registerExtension({
  name: "PromptKit.DictionaryPanel",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    addOpenButton(nodeType, nodeData);
  },
});
