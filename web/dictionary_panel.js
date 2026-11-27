/**
 * Prompt-Kit 字典面板
 * - 勾选同步 / 清空同步
 * - 详情编辑（系统/用户均写入 user 覆盖层）
 * - NSFW 可插拔（勾选后加载 NSFW 分类）
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/prompt-kit";
const NODE_TYPES = new Set([
  "PromptKitDictionaryPick",
  "PromptKitDictionaryPanel",
  "PromptKitDictionaryAdd",
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


/** @type {{ id:string, display:string, text?:string, text_zh?:string, subcategory?:string, tags?:string[] }[]} */
let selected = [];
/** @type {any|null} */
let previewEntry = null;
/** @type {any[]} */
let lastEntries = [];

function selectedIds() {
  return new Set(selected.map((s) => s.id));
}

function openPanel(targetNode) {
  selected = [];
  previewEntry = null;
  lastEntries = [];
  let currentSub = null;
  let listOffset = 0;
  let includeNsfw = false;
  /** @type {Set<string>} */
  let favSet = new Set();
  const PAGE = 50;

  async function refreshFavSet() {
    try {
      const data = await apiGet(`/favorites?lang=${langSelect.value}`);
      const ids = (data.entries || data.ids || []).map((x) => (typeof x === "string" ? x : x.id)).filter(Boolean);
      // list endpoint returns entries; also support raw ids
      if (data.ok && Array.isArray(data.entries)) {
        favSet = new Set(data.entries.map((e) => e.id).filter(Boolean));
      } else if (data.ok && Array.isArray(data.ids)) {
        favSet = new Set(data.ids);
      } else {
        // fallback: empty keep previous
      }
    } catch (_) {}
  }

  const overlay = el(
    "div",
    "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;"
  );
  const dialog = el(
    "div",
    "background:#1a1a1a;border:1px solid #555;border-radius:10px;width:1040px;max-width:96vw;height:84vh;max-height:920px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.55);color:#eee;font:13px/1.4 system-ui,sans-serif;"
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
  header.appendChild(el("div", "font-weight:700;font-size:15px;", "PromptKit · 字典面板"));
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
  const chkNsfw = el("label", "display:flex;align-items:center;gap:4px;font-size:12px;color:#aaa;");
  const chkNsfwInput = document.createElement("input");
  chkNsfwInput.type = "checkbox";
  chkNsfw.append(chkNsfwInput, document.createTextNode("显示 NSFW"));
  toolbar.append(searchInput, langSelect, btnSearch, btnFavView, btnClearSel, chkNsfw);
  dialog.appendChild(toolbar);

  const body = el("div", "display:flex;flex:1;min-height:0;");
  const treePane = el(
    "div",
    "width:200px;border-right:1px solid #333;overflow:auto;padding:8px;flex-shrink:0;"
  );
  const listPane = el("div", "flex:1;overflow:auto;padding:8px;min-width:0;");
  const rightPane = el(
    "div",
    "width:280px;border-left:1px solid #333;display:flex;flex-direction:column;flex-shrink:0;"
  );
  body.append(treePane, listPane, rightPane);
  dialog.appendChild(body);

  const selBox = el("div", "padding:8px;border-bottom:1px solid #333;max-height:35%;overflow:auto;flex-shrink:0;");
  const selTitle = el("div", "font-weight:600;margin-bottom:6px;", "已选 (0)");
  const selList = el("div", "");
  selBox.append(selTitle, selList);
  const detailBox = el("div", "flex:1;overflow:auto;padding:8px;min-height:0;");
  detailBox.appendChild(el("div", "font-weight:600;margin-bottom:6px;", "详情 / 编辑"));
  const detailBody = el("div", "");
  detailBox.appendChild(detailBody);
  rightPane.append(selBox, detailBox);

  const footer = el(
    "div",
    "display:flex;gap:8px;padding:10px 14px;border-top:1px solid #333;flex-shrink:0;align-items:center;"
  );
  const btnApply = el("button", css.btnBlue, "应用到节点");
  const btnCopy = el("button", css.btnGhost, "复制文本");
  footer.append(el("span", "flex:1;", ""), btnApply, btnCopy);
  dialog.appendChild(footer);

  function setStatus(msg) {
    status.textContent = msg || "";
  }

  function refreshSelUI() {
    selTitle.textContent = `已选 (${selected.length})`;
    selList.innerHTML = "";
    selected.forEach((item, idx) => {
      const row = el(
        "div",
        "display:flex;align-items:flex-start;gap:4px;padding:4px 2px;border-bottom:1px solid #2a2a2a;"
      );
      const t = el("div", "flex:1;word-break:break-all;font-size:12px;", item.display);
      const rm = el("button", css.btnSmall, "×");
      rm.onclick = () => {
        selected.splice(idx, 1);
        refreshSelUI();
        renderEntries(lastEntries, null, false, true);
      };
      row.append(t, rm);
      selList.appendChild(row);
    });
  }

  function showDetail(entry) {
    previewEntry = entry;
    detailBody.innerHTML = "";
    if (!entry) {
      detailBody.appendChild(el("div", "color:#666;", "未选择"));
      return;
    }
    const fZh = el("textarea");
    fZh.style.cssText = css.field + "width:100%;min-height:52px;margin-bottom:6px;";
    fZh.placeholder = "中文 text_zh";
    fZh.value = entry.text_zh || "";
    const fEn = el("textarea");
    fEn.style.cssText = css.field + "width:100%;min-height:52px;margin-bottom:6px;";
    fEn.placeholder = "英文 text";
    fEn.value = entry.text || "";
    const fTags = el("input");
    fTags.type = "text";
    fTags.style.cssText = css.field + "width:100%;margin-bottom:6px;";
    fTags.placeholder = "标签，逗号分隔";
    fTags.value = (entry.tags || []).join(", ");
    const btnSave = el("button", css.btnBlue + "width:100%;", "保存修改");
    btnSave.onclick = async () => {
      const tags = fTags.value
        .split(/[,，;；]/)
        .map((x) => x.trim())
        .filter(Boolean);
      const r = await apiPost("/entry/update", {
        id: entry.id,
        subcategory: entry.subcategory || currentSub || "",
        text: fEn.value,
        text_zh: fZh.value,
        tags,
      });
      if (!r.ok) {
        setStatus(r.error || "保存失败");
        return;
      }
      entry.text = fEn.value;
      entry.text_zh = fZh.value;
      entry.tags = tags;
      const lang = langSelect.value;
      entry.display =
        lang === "en"
          ? entry.text || entry.text_zh
          : lang === "both" && entry.text_zh && entry.text
            ? `${entry.text_zh} (${entry.text})`
            : entry.text_zh || entry.text;
      const sel = selected.find((s) => s.id === entry.id);
      if (sel) sel.display = entry.display;
      refreshSelUI();
      renderEntries(lastEntries, null, false, true);
      setStatus("已保存（用户覆盖层）");
    };
    detailBody.append(fZh, fEn, fTags, btnSave);
  }

  function toggleSelect(entry) {
    const ids = selectedIds();
    if (ids.has(entry.id)) {
      selected = selected.filter((s) => s.id !== entry.id);
    } else {
      selected.push({
        id: entry.id,
        display: entry.display,
        text: entry.text,
        text_zh: entry.text_zh,
        subcategory: entry.subcategory,
        tags: entry.tags,
      });
    }
    refreshSelUI();
  }

  function renderEntries(entries, total, append, keepOnly) {
    if (!keepOnly) {
      if (!append) {
        listPane.innerHTML = "";
        lastEntries = [];
      }
      if (!entries) entries = [];
      if (!append) lastEntries = entries.slice();
      else lastEntries = lastEntries.concat(entries);
    }
    const data = keepOnly ? lastEntries : append ? lastEntries : entries;
    if (!keepOnly) {
      if (!append) listPane.innerHTML = "";
    } else {
      listPane.innerHTML = "";
    }
    if (!data.length) {
      listPane.appendChild(el("div", "color:#888;padding:12px;", "无结果"));
      if (total != null) setStatus("0 条");
      return;
    }
    const ids = selectedIds();
    data.forEach((e) => {
      const row = el(
        "div",
        "display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid #2a2a2a;cursor:pointer;" +
          (ids.has(e.id) ? "background:#1e2a40;" : "")
      );
      const check = el("input");
      check.type = "checkbox";
      check.checked = ids.has(e.id);
      check.onclick = (ev) => {
        ev.stopPropagation();
        toggleSelect(e);
        renderEntries(null, null, false, true);
      };
      const main = el("div", "flex:1;min-width:0;");
      main.appendChild(el("div", "word-break:break-all;", e.display));
      const isFav = favSet.has(e.id);
      const btnStyle = "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;font-size:13px;line-height:1.2;min-width:28px;";
      const star = el(
        "button",
        btnStyle + (isFav ? "color:#f5c542;" : "color:#888;"),
        isFav ? "★" : "☆"
      );
      star.title = isFav ? "取消收藏" : "收藏";
      star.onclick = async (ev) => {
        ev.stopPropagation();
        const r = await apiPost("/favorites", { action: "toggle", id: e.id });
        if (r.favorited) favSet.add(e.id);
        else favSet.delete(e.id);
        setStatus(r.favorited ? "已收藏" : "已取消收藏");
        renderEntries(null, null, false, true);
      };
      const del = el("button", btnStyle + "color:#e88;", "删");
      del.title = "删除词条";
      del.onclick = (ev) => {
        ev.stopPropagation();
        const name = e.display || e.text_zh || e.id;
        openConfirmModal("确认删除字典词条「" + name + "」？此操作不可恢复。", async () => {
          const r = await apiPost("/entry/delete", { id: e.id, subcategory: e.subcategory || currentSub || "" });
          if (!r.ok) { setStatus(r.error || "删除失败"); return; }
          selected = selected.filter((s) => s.id !== e.id);
          favSet.delete(e.id);
          if (previewEntry && previewEntry.id === e.id) { previewEntry = null; showDetail(null); }
          lastEntries = lastEntries.filter((x) => x.id !== e.id);
          setStatus("已删除");
          refreshSelUI();
          renderEntries(null, null, false, true);
        });
      };
      row.onclick = () => {
        toggleSelect(e);
        showDetail(e);
        renderEntries(null, null, false, true);
      };
      row.append(check, main, star, del);
      listPane.appendChild(row);
    });
    if (total != null) setStatus(`显示 ${data.length} / 约 ${total}`);
    if (!keepOnly && currentSub && total != null && listOffset + (entries || []).length < total && !append) {
      // handled below for initial
    }
    if (!keepOnly && currentSub && total != null && listOffset + data.length < total) {
      const more = el("button", css.btnGhost + "margin:8px;width:calc(100% - 16px);", "加载更多");
      more.onclick = async () => {
        listOffset += PAGE;
        more.remove();
        const data2 = await apiGet(
          `/entries?subcategory=${encodeURIComponent(currentSub)}&offset=${listOffset}&limit=${PAGE}&lang=${langSelect.value}`
        );
        if (data2.ok) renderEntries(data2.entries || [], data2.total, true);
      };
      listPane.appendChild(more);
    }
  }

  async function loadTree() {
    treePane.innerHTML = "";
    treePane.appendChild(el("div", "color:#888;", "加载分类…"));
    const data = await apiGet(
      `/tree?lang=zh&include_nsfw=${includeNsfw ? "1" : "0"}`
    );
    treePane.innerHTML = "";
    if (!data.ok) {
      treePane.appendChild(el("div", "color:#c66;", data.error || "加载失败"));
      return;
    }
    (data.tree || []).forEach((cat) => {
      const catEl = el("div", "margin-bottom:6px;");
      catEl.appendChild(
        el("div", "font-weight:600;padding:4px 2px;color:#bcd;", cat.name || cat.id)
      );
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
          setStatus("加载中…");
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
    setStatus("搜索中…");
    const data = await apiGet(
      `/search?q=${encodeURIComponent(q)}&limit=80&lang=${langSelect.value}&include_nsfw=${includeNsfw ? "1" : "0"}`
    );
    if (data.ok) renderEntries(data.entries || [], data.total, false);
    else listPane.innerHTML = `<div style="color:#c66;padding:12px">${data.error || "失败"}</div>`;
  }

  async function doFav() {
    currentSub = null;
    setStatus("加载收藏…");
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
    previewEntry = null;
    showDetail(null);
    refreshSelUI();
    renderEntries(null, null, false, true);
  };
  chkNsfwInput.onchange = async () => {
    includeNsfw = chkNsfwInput.checked;
    await loadTree();
  };

  btnCopy.onclick = async () => {
    const text = selected.map((s) => s.display).join(", ");
    try {
      await navigator.clipboard.writeText(text);
      setStatus("已复制");
    } catch {
      setStatus("复制失败");
    }
  };

  btnApply.onclick = () => {
    const text = selected.map((s) => s.display).join(", ");
    if (!targetNode) {
      setStatus("无目标节点");
      return;
    }
    const widgets = targetNode.widgets || [];
    const order = ["面板文本", "panel_text", "文本", "text", "query", "关键词"];
    let w = null;
    for (const name of order) {
      w = widgets.find((x) => x.name === name);
      if (w) break;
    }
    if (!w) w = widgets.find((x) => x.type === "text" || x.type === "customtext");
    if (!w) {
      setStatus("节点上没有可写入的文本框");
      return;
    }
    w.value = text;
    if (w.callback) w.callback(text);
    targetNode.setDirtyCanvas?.(true, true);
    setStatus(`已写入「${w.name}」`);
  };

  refreshSelUI();
  showDetail(null);
  refreshFavSet().then(() => loadTree());
}

function addOpenButton(nodeType, nodeData) {
  if (!NODE_TYPES.has(nodeData.name)) return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    const r = onNodeCreated?.apply(this, arguments);
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
