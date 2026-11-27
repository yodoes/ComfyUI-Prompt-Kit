/**
 * Prompt-Kit 词库面板 v0.3.1
 * - 分类区限高滚动；标签/收藏常显；标签筛选 AND/OR 可切换（默认 AND）
 * - 收藏在标题行右侧；选中用 ☑
 * - 详情与已选分离；清空已选清空详情
 * - 预设可编辑
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/prompt-kit";
const NODE_TYPES = new Set([
  "PromptKitLibraryPick",
  "PromptKitLibraryPanel",
  "PromptKitLibraryQuickSave",
]);

const css = {
  field: "padding:6px 8px;border:1px solid #555;border-radius:4px;background:#2a2a2a;color:#eee;outline:none;font:inherit;box-sizing:border-box;",
  btnBlue: "padding:6px 14px;cursor:pointer;background:#4a7dff;border:1px solid #4a7dff;border-radius:4px;color:#fff;font:inherit;",
  btnGhost: "padding:6px 14px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:4px;color:#eee;font:inherit;",
  btnSmall: "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;color:#ccc;font-size:12px;",
  btnActive: "padding:2px 8px;cursor:pointer;background:#3a5a9a;border:1px solid #4a7dff;border-radius:3px;color:#fff;font-size:12px;",
  tag: "display:inline-flex;align-items:center;gap:4px;padding:1px 8px;margin:2px;border-radius:10px;background:#333;border:1px solid #555;font-size:12px;cursor:pointer;",
  tagOn: "display:inline-flex;align-items:center;gap:4px;padding:1px 8px;margin:2px;border-radius:10px;background:#3a5a9a;border:1px solid #4a7dff;font-size:12px;cursor:pointer;",
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

function openFormModal(title, fields, buttons) {
  const ov = el("div", "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;");
  const box = el("div", "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:440px;max-width:92vw;color:#eee;font:13px system-ui,sans-serif;");
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
    } else {
      inp = el("input");
      inp.type = "text";
      inp.value = f.value || "";
      inp.placeholder = f.placeholder || "";
      inp.style.cssText = css.field + "width:100%;margin-bottom:10px;";
    }
    inputs[f.key] = inp;
    box.appendChild(inp);
  });
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;");
  const close = () => ov.remove();
  (buttons || []).forEach((b) => {
    const btn = el("button", b.primary ? css.btnBlue : css.btnGhost, b.label);
    btn.onclick = async () => {
      const values = {};
      Object.keys(inputs).forEach((k) => { values[k] = inputs[k].value; });
      await b.onClick(values, close, inputs);
    };
    row.appendChild(btn);
  });
  box.appendChild(row);
  ov.appendChild(box);
  // 表单弹窗不点遮罩关闭，仅取消/保存关闭

  document.body.appendChild(ov);
  const first = Object.values(inputs)[0];
  if (first) first.focus();
}

function openConfirmModal(message, onYes) {
  const ov = el("div", "position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.45);display:flex;align-items:center;justify-content:center;");
  const box = el("div", "background:#1e1e1e;border:1px solid #555;border-radius:8px;padding:16px;width:400px;max-width:92vw;color:#eee;font:13px system-ui,sans-serif;");
  box.appendChild(el("div", "font-weight:700;margin-bottom:10px;", "确认"));
  box.appendChild(el("div", "margin-bottom:14px;line-height:1.5;color:#ddd;", message));
  const row = el("div", "display:flex;gap:8px;justify-content:flex-end;");
  const btnCancel = el("button", css.btnGhost, "取消");
  const btnOk = el("button", css.btnBlue, "确认");
  const close = () => ov.remove();
  btnCancel.onclick = close;
  btnOk.onclick = async () => { close(); await onYes(); };
  row.append(btnCancel, btnOk);
  box.appendChild(row);
  ov.appendChild(box);
  document.body.appendChild(ov);
}


let selected = [];
let previewRow = null;

function openPanel(targetNode) {
  selected = [];
  previewRow = null;
  let libraries = [];
  let currentLibId = "";
  let categories = [];
  let allTags = [];
  let activeTags = new Set();
  let tagMode = "and"; // and | or
  let activeCategory = "";
  let favOnly = false;
  let offset = 0;
  const limit = 50;
  let total = 0;
  let showNsfw = false;
  let lastRows = [];

  const overlay = el("div", "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;");
  const dialog = el("div", "background:#1a1a1a;border:1px solid #555;border-radius:10px;width:1100px;max-width:96vw;height:86vh;max-height:940px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.55);color:#eee;font:13px/1.4 system-ui,sans-serif;");
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

  const header = el("div", "display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid #333;flex-shrink:0;");
  header.appendChild(el("div", "font-weight:700;font-size:15px;", "PromptKit · 词库面板"));
  const status = el("span", "color:#8ab;font-size:12px;margin-left:auto;", "");
  header.appendChild(status);
  const btnClose = el("button", css.btnGhost, "关闭");
  btnClose.onclick = () => overlay.remove();
  header.appendChild(btnClose);
  dialog.appendChild(header);

  const toolbar = el("div", "display:flex;gap:8px;padding:8px 14px;border-bottom:1px solid #333;flex-shrink:0;align-items:center;flex-wrap:wrap;");
  const libSelect = el("select");
  libSelect.style.cssText = css.field + "min-width:220px;max-width:320px;";
  const searchInput = el("input");
  searchInput.type = "text";
  searchInput.placeholder = "搜索标题 / 正文 / 标签";
  searchInput.style.cssText = css.field + "flex:1;min-width:160px;";
  const langSelect = el("select");
  langSelect.style.cssText = css.field + "width:80px;";
  ["zh", "en", "both"].forEach((v) => { const o = document.createElement("option"); o.value = v; o.textContent = v; langSelect.appendChild(o); });
  const btnSearch = el("button", css.btnBlue, "搜索");
  const btnFavView = el("button", css.btnGhost, "收藏夹");
  const btnReload = el("button", css.btnGhost, "刷新");
  const btnClearSel = el("button", css.btnGhost, "清空已选");
  const btnNewLib = el("button", css.btnGhost, "新建词库");
  const btnNewPreset = el("button", css.btnGhost, "新建预设");
  const chkNsfw = el("label", "display:flex;align-items:center;gap:4px;font-size:12px;color:#aaa;");
  const chkNsfwInput = document.createElement("input");
  chkNsfwInput.type = "checkbox";
  chkNsfw.append(chkNsfwInput, document.createTextNode("显示 NSFW 库"));
  toolbar.append(libSelect, searchInput, langSelect, btnSearch, btnFavView, btnReload, btnClearSel, btnNewLib, btnNewPreset, chkNsfw);
  dialog.appendChild(toolbar);

  const body = el("div", "display:flex;flex:1;min-height:0;");
  const leftPane = el("div", "width:210px;border-right:1px solid #333;display:flex;flex-direction:column;flex-shrink:0;min-height:0;");
  const listPane = el("div", "flex:1;overflow:auto;padding:8px;min-width:0;");
  const rightPane = el("div", "width:300px;border-left:1px solid #333;display:flex;flex-direction:column;flex-shrink:0;min-height:0;");
  body.append(leftPane, listPane, rightPane);
  dialog.appendChild(body);

  const footer = el("div", "display:flex;gap:8px;padding:10px 14px;border-top:1px solid #333;flex-shrink:0;align-items:center;");
  const selCount = el("span", "color:#8ab;font-size:12px;", "已选 0");
  const btnApply = el("button", css.btnBlue, "应用到节点");
  const btnCopy = el("button", css.btnGhost, "复制文本");
  const btnToSkill = el("button", css.btnGhost, "沉淀为 Skill");
  footer.append(selCount, el("span", "flex:1;", ""), btnToSkill, btnApply, btnCopy);
  dialog.appendChild(footer);

  const selBox = el("div", "padding:8px;border-bottom:1px solid #333;max-height:30%;overflow:auto;flex-shrink:0;");
  selBox.appendChild(el("div", "font-weight:600;margin-bottom:6px;", "已选"));
  const selList = el("div", "");
  selBox.appendChild(selList);
  const detailBox = el("div", "flex:1;overflow:auto;padding:8px;min-height:0;");
  detailBox.appendChild(el("div", "font-weight:600;margin-bottom:6px;", "详情 / 编辑"));
  const detailBody = el("div", "font-size:12px;color:#ccc;");
  detailBox.appendChild(detailBody);
  rightPane.append(selBox, detailBox);

  function setStatus(msg) { status.textContent = msg || ""; }

  function renderSelected() {
    selList.innerHTML = "";
    selCount.textContent = "已选 " + selected.length;
    selected.forEach((s, idx) => {
      const row = el("div", "display:flex;gap:4px;align-items:flex-start;padding:4px 0;border-bottom:1px solid #2a2a2a;");
      const t = el("div", "flex:1;font-size:12px;", s.title || (s.text || "").slice(0, 40));
      const rm = el("button", css.btnSmall, "×");
      rm.onclick = () => { selected.splice(idx, 1); renderSelected(); renderList(lastRows); };
      row.append(t, rm);
      selList.appendChild(row);
    });
  }

  function fillLibSelect() {
    libSelect.innerHTML = "";
    const groups = { system: [], plugin: [], user: [], bulk: [], nsfw: [] };
    libraries.forEach((m) => { const g = m.group || "user"; if (!groups[g]) groups[g] = []; groups[g].push(m); });
    const labels = { system: "系统示例", plugin: "精库", user: "用户", bulk: "粗分 SFW", nsfw: "NSFW" };
    ["system", "plugin", "user", "bulk", "nsfw"].forEach((g) => {
      const items = (groups[g] || []).filter((m) => showNsfw || !m.nsfw);
      if (!items.length) {
        if (g === "nsfw" && !showNsfw && (groups.nsfw || []).length) {
          const o = document.createElement("option");
          o.disabled = true;
          o.textContent = "── NSFW（" + groups.nsfw.length + " 个库，勾选上方显示）──";
          libSelect.appendChild(o);
        }
        return;
      }
      const og = document.createElement("optgroup");
      og.label = labels[g] + " (" + items.length + ")";
      items.forEach((m) => {
        const o = document.createElement("option");
        o.value = m.id;
        o.textContent = (m.name_zh || m.id) + " (" + (m.preset_count || 0) + ")";
        og.appendChild(o);
      });
      libSelect.appendChild(og);
    });
    if (currentLibId) libSelect.value = currentLibId;
    if (!libSelect.value) {
      for (const o of libSelect.options) { if (!o.disabled && o.value) { libSelect.value = o.value; break; } }
    }
    currentLibId = libSelect.value || "";
  }

  async function loadLibraries() {
    setStatus("加载词库列表…");
    const all = await apiGet("/library/list?include_nsfw=1");
    if (!all.ok) { setStatus("列表失败: " + (all.error || "")); return; }
    libraries = all.libraries || [];
    fillLibSelect();
    setStatus("词库 " + libraries.filter((x) => showNsfw || !x.nsfw).length + " 个");
    if (currentLibId) await loadLibMetaAndSearch();
  }

  async function loadLibMetaAndSearch() {
    if (!currentLibId) return;
    setStatus("加载分类/标签…");
    const meta = await apiGet("/library/get?id=" + encodeURIComponent(currentLibId));
    categories = meta.ok ? (meta.categories || []) : [];
    allTags = meta.ok ? (meta.tags || []) : [];
    activeCategory = "";
    activeTags = new Set();
    favOnly = false;
    offset = 0;
    renderLeft();
    await doSearch();
  }

  function renderLeft() {
    leftPane.innerHTML = "";
    const catHeader = el("div", "font-weight:600;padding:8px 8px 4px;flex-shrink:0;", "分类");
    const catScroll = el("div", "max-height:38%;overflow:auto;padding:0 8px 8px;border-bottom:1px solid #333;flex-shrink:0;");
    const catAll = el("div", "padding:4px 6px;cursor:pointer;border-radius:4px;" + (!activeCategory ? "background:#2a3a5a;" : ""), "全部");
    catAll.onclick = () => { activeCategory = ""; offset = 0; renderLeft(); doSearch(); };
    catScroll.appendChild(catAll);
    categories.forEach((c) => {
      const id = c.id || "";
      const name = c.name_zh || c.name_en || id;
      const row = el("div", "padding:4px 6px;cursor:pointer;border-radius:4px;font-size:12px;" + (activeCategory === id ? "background:#2a3a5a;" : ""), name);
      row.onclick = () => { activeCategory = id; offset = 0; renderLeft(); doSearch(); };
      catScroll.appendChild(row);
    });
    leftPane.append(catHeader, catScroll);

    const tagHeader = el("div", "display:flex;align-items:center;gap:6px;padding:8px 8px 4px;flex-shrink:0;");
    tagHeader.appendChild(el("span", "font-weight:600;", "标签"));
    const modeWrap = el("span", "display:inline-flex;gap:2px;margin-left:auto;");
    const btnAnd = el("button", tagMode === "and" ? css.btnActive : css.btnSmall, "AND");
    btnAnd.title = "多标签需同时满足";
    btnAnd.onclick = (e) => {
      e.stopPropagation();
      if (tagMode === "and") return;
      tagMode = "and";
      offset = 0;
      renderLeft();
      doSearch();
    };
    const btnOr = el("button", tagMode === "or" ? css.btnActive : css.btnSmall, "OR");
    btnOr.title = "多标签满足其一即可";
    btnOr.onclick = (e) => {
      e.stopPropagation();
      if (tagMode === "or") return;
      tagMode = "or";
      offset = 0;
      renderLeft();
      doSearch();
    };
    modeWrap.append(btnAnd, btnOr);
    tagHeader.appendChild(modeWrap);
    const tagScroll = el("div", "flex:1;overflow:auto;padding:0 8px;min-height:60px;");
    if (!allTags.length) tagScroll.appendChild(el("div", "color:#666;font-size:12px;", "暂无标签"));
    else {
      const tagWrap = el("div", "display:flex;flex-wrap:wrap;");
      allTags.slice(0, 120).forEach((t) => {
        const on = activeTags.has(t);
        const chip = el("span", on ? css.tagOn : css.tag, t);
        chip.onclick = () => { if (activeTags.has(t)) activeTags.delete(t); else activeTags.add(t); offset = 0; renderLeft(); doSearch(); };
        tagWrap.appendChild(chip);
      });
      tagScroll.appendChild(tagWrap);
      if (activeTags.size) {
        const clr = el("button", css.btnSmall + "margin-top:6px;", "清除标签筛选");
        clr.onclick = () => { activeTags.clear(); offset = 0; renderLeft(); doSearch(); };
        tagScroll.appendChild(clr);
      }
    }
    leftPane.append(tagHeader, tagScroll);

    const favBtn = el("button", (favOnly ? css.btnActive : css.btnSmall) + "margin:8px;width:calc(100% - 16px);flex-shrink:0;", favOnly ? "★ 收藏中" : "☆ 仅收藏");
    favBtn.onclick = () => { favOnly = !favOnly; offset = 0; renderLeft(); doSearch(); };
    leftPane.appendChild(favBtn);
  }

  function renderList(rows) {
    lastRows = rows || [];
    listPane.innerHTML = "";
    listPane.appendChild(el("div", "color:#8ab;font-size:12px;margin-bottom:6px;", "共 " + total + " 条 · 显示 " + lastRows.length));
    if (!lastRows.length) { listPane.appendChild(el("div", "color:#666;", "无结果")); return; }
    const selSet = new Set(selected.map((s) => s.library_id + "::" + s.id));
    lastRows.forEach((r) => {
      const lid = r.library_id || currentLibId;
      const key = lid + "::" + r.id;
      const checked = selSet.has(key);
      const row = el("div", "padding:8px;border:1px solid #333;border-radius:6px;margin-bottom:6px;cursor:pointer;" + (checked ? "background:#1e2a40;border-color:#4a7dff;" : "background:#222;"));
      const titleRow = el("div", "display:flex;align-items:center;gap:6px;");
      const title = el("div", "font-weight:600;flex:1;min-width:0;", r.title || "(无标题)");
      const mark = el(
        "button",
        checked
          ? "padding:2px 8px;cursor:pointer;background:#2a3d5c;border:1px solid #4a7dff;border-radius:3px;color:#9cf;font-size:12px;"
          : "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;color:#aaa;font-size:12px;",
        checked ? "已选" : "选择"
      );
      mark.title = checked ? "取消选中" : "选中";
      mark.onclick = (e) => {
        e.stopPropagation();
        const lid0 = r.library_id || currentLibId;
        if (checked) selected = selected.filter((x) => !(x.id === r.id && (x.library_id || lid0) === lid0));
        else selected.push({ library_id: lid0, id: r.id, title: r.title || "", text: r.text || r.prompt || "" });
        renderSelected();
        renderList(lastRows);
      };
      const fav = el(
        "button",
        "padding:2px 8px;cursor:pointer;background:transparent;border:1px solid #555;border-radius:3px;font-size:13px;" +
          (r.favorite ? "color:#f5c542;" : "color:#888;"),
        r.favorite ? "★" : "☆"
      );
      fav.title = r.favorite ? "取消收藏" : "收藏";
      fav.onclick = async (e) => {
        e.stopPropagation();
        const res = await apiPost("/library/favorite", { library_id: lid, preset_id: r.id });
        if (res.ok) { r.favorite = res.favorited; renderList(lastRows); setStatus(res.favorited ? "已收藏" : "已取消收藏"); }
        else setStatus(res.error || "收藏失败");
      };
      const del = el("button", css.btnSmall + "color:#e88;", "删");
      del.title = "删除预设";
      del.onclick = async (e) => {
        e.stopPropagation();
        const name = r.title || r.id;
        openConfirmModal("确认删除预设「" + name + "」？此操作不可恢复。", async () => {
          const res = await apiPost("/library/preset", { action: "delete", library_id: lid, preset_id: r.id });
          if (!res.ok) { setStatus(res.error || "删除失败"); return; }
          selected = selected.filter((x) => x.id !== r.id);
          if (previewRow && previewRow.id === r.id) { previewRow = null; showDetail(null); }
          setStatus("已删除");
          await doSearch(false);
          renderSelected();
        });
      };
      titleRow.append(title, mark, fav, del);
      const tags = el("div", "margin-top:4px;");
      (r.tags || []).slice(0, 8).forEach((t) => tags.appendChild(el("span", css.tag, t)));
      const snip = el("div", "margin-top:4px;color:#999;font-size:12px;max-height:2.8em;overflow:hidden;", (r.text || "").slice(0, 160));
      row.append(titleRow, tags, snip);
      row.onclick = () => {
        if (checked) selected = selected.filter((s) => !(s.library_id === lid && s.id === r.id));
        else selected.push({ library_id: lid, id: r.id, title: r.title || "", text: r.text || r.prompt || "" });
        showDetail(r);
        renderSelected();
        renderList(lastRows);
      };
      listPane.appendChild(row);
    });
    if (offset + lastRows.length < total) {
      const more = el("button", css.btnGhost + "width:100%;margin-top:8px;", "加载更多");
      more.onclick = async () => { offset += limit; await doSearch(true); };
      listPane.appendChild(more);
    }
  }

  function showDetail(r) {
    previewRow = r;
    detailBody.innerHTML = "";
    if (!r) { detailBody.appendChild(el("div", "color:#666;", "未选择（点击中间列表预览/编辑）")); return; }
    const tTitle = el("input"); tTitle.type = "text"; tTitle.style.cssText = css.field + "width:100%;margin-bottom:6px;"; tTitle.placeholder = "标题"; tTitle.value = r.title_zh || r.title || "";
    const tPrompt = el("textarea"); tPrompt.style.cssText = css.field + "width:100%;min-height:100px;margin-bottom:6px;"; tPrompt.placeholder = "prompt（中文）"; tPrompt.value = r.prompt || r.text || "";
    const tPromptEn = el("textarea"); tPromptEn.style.cssText = css.field + "width:100%;min-height:60px;margin-bottom:6px;"; tPromptEn.placeholder = "prompt_en"; tPromptEn.value = r.prompt_en || "";
    const tTags = el("input"); tTags.type = "text"; tTags.style.cssText = css.field + "width:100%;margin-bottom:6px;"; tTags.placeholder = "标签，逗号分隔"; tTags.value = (r.tags || []).join(", ");
    const btnSave = el("button", css.btnBlue + "width:100%;margin-bottom:6px;", "保存修改");
    btnSave.onclick = async () => {
      const tags = tTags.value.split(/[,，;；]/).map((x) => x.trim()).filter(Boolean);
      const res = await apiPost("/library/preset", { action: "update", library_id: r.library_id || currentLibId, preset_id: r.id, title_zh: tTitle.value, prompt: tPrompt.value, prompt_en: tPromptEn.value, tags: tags });
      if (!res.ok) { setStatus(res.error || "保存失败"); return; }
      r.title = tTitle.value; r.title_zh = tTitle.value; r.prompt = tPrompt.value; r.prompt_en = tPromptEn.value; r.text = tPrompt.value || tPromptEn.value; r.tags = tags;
      const s = selected.find((x) => x.id === r.id); if (s) { s.title = r.title; s.text = r.text; }
      renderSelected(); renderList(lastRows); setStatus("已保存");
    };
    detailBody.append(tTitle, tPrompt, tPromptEn, tTags, btnSave);
  }

  async function doSearch(append) {
    if (!currentLibId && !favOnly) { renderList([]); return; }
    setStatus("搜索中…");
    if (!append) offset = 0;
    const params = new URLSearchParams();
    params.set("id", currentLibId);
    params.set("q", searchInput.value || "");
    params.set("lang", langSelect.value || "zh");
    params.set("offset", String(offset));
    params.set("limit", String(limit));
    params.set("tag_mode", tagMode || "and");
    if (activeCategory) params.set("category_id", activeCategory);
    if (activeTags.size) params.set("tags", Array.from(activeTags).join(","));
    if (favOnly) params.set("favorites", "1");
    params.set("include_nsfw", showNsfw ? "1" : "0");
    const data = await apiGet("/library/search?" + params.toString());
    if (!data.ok) { setStatus(data.error || "搜索失败"); return; }
    total = data.total || 0;
    const rows = data.presets || [];
    if (append) renderList(lastRows.concat(rows)); else renderList(rows);
    setStatus("命中 " + total);
  }

  libSelect.onchange = async () => { currentLibId = libSelect.value; previewRow = null; showDetail(null); await loadLibMetaAndSearch(); };
  btnSearch.onclick = () => doSearch(false);
  searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(false); });
  btnFavView.onclick = () => { favOnly = true; offset = 0; renderLeft(); doSearch(false); };
  btnReload.onclick = async () => { await apiPost("/library/reload", {}); await loadLibraries(); };
  btnClearSel.onclick = () => { selected = []; previewRow = null; showDetail(null); renderSelected(); renderList(lastRows); };
  chkNsfwInput.onchange = async () => { showNsfw = chkNsfwInput.checked; await loadLibraries(); };

  btnApply.onclick = () => {
    if (!selected.length) { setStatus("请先选择预设"); return; }
    const text = selected.map((s) => s.text).filter(Boolean).join("\n");
    applyToNode(targetNode, text);
    setStatus("已应用到节点（" + selected.length + " 条，换行拼接）");
  };
  btnCopy.onclick = async () => {
    const text = selected.map((s) => s.text).filter(Boolean).join("\n");
    if (!text) { setStatus("无内容可复制"); return; }
    try { await navigator.clipboard.writeText(text); setStatus("已复制"); } catch (e) { setStatus("复制失败"); }
  };
  btnToSkill.onclick = () => {
    const fromSel = selected.map((s) => s.text).filter(Boolean);
    let text = fromSel.join("\n\n");
    let title = selected.length === 1 ? (selected[0].title || "") : (selected.length ? "词库组合" : "");
    if (!text && previewRow) {
      text = previewRow.text || previewRow.prompt || "";
      title = previewRow.title || title;
    }
    if (!text) { setStatus("请先选择或点开一条预设"); return; }
    if (!window.PromptKitSkill || !window.PromptKitSkill.openGenerateWizard) {
      setStatus("Skill 面板脚本未加载，请完整重启 ComfyUI");
      return;
    }
    window.PromptKitSkill.openGenerateWizard({
      kind: "from_library",
      title_zh: title || "词库沉淀",
      name: window.PromptKitSkill.suggestSkillName(title || text.slice(0, 24)),
      source_text: text,
      tags: ["词库", "沉淀"],
      description: "Reusable prompt style distilled from library presets. Use when recreating this look. 来自词库预设的风格复用。",
      onSaved: (skill) => setStatus("已沉淀为 Skill：" + ((skill && skill.name) || "")),
    });
  };


  btnNewLib.onclick = () => {
    openFormModal("新建词库", [
      { key: "name_zh", label: "词库中文名", type: "text", placeholder: "例如：我的角色库" },
    ], [
      { label: "取消", primary: false, onClick: async (_v, close) => close() },
      { label: "保存", primary: true, onClick: async (v, close) => {
          if (!(v.name_zh || "").trim()) { setStatus("名称不能为空"); return; }
          const res = await apiPost("/library/create", { name_zh: v.name_zh.trim() });
          if (!res.ok) { setStatus(res.error || "新建失败"); return; }
          close(); setStatus("已新建词库"); await loadLibraries();
        }},
    ]);
  };
  btnNewPreset.onclick = () => {
    if (!currentLibId) { setStatus("请先选择词库"); return; }
    const openAgain = () => btnNewPreset.onclick();
    openFormModal("新建预设", [
      { key: "title", label: "标题", type: "text", value: "新预设", placeholder: "预设标题" },
      { key: "prompt", label: "提示词正文", type: "textarea", rows: 6, placeholder: "中文提示词" },
      { key: "tags", label: "标签（可空，逗号分隔）", type: "text", placeholder: "如：人像, 室内" },
    ], [
      { label: "取消", primary: false, onClick: async (_v, close) => close() },
      { label: "保存", primary: true, onClick: async (v, close) => {
          const tags = (v.tags || "").split(/[,，;；]/).map((x) => x.trim()).filter(Boolean);
          const res = await apiPost("/library/preset", {
            action: "add", library_id: currentLibId,
            title_zh: (v.title || "").trim() || "新预设",
            prompt: (v.prompt || "").trim(),
            tags,
          });
          if (!res.ok) { setStatus(res.error || "新建预设失败"); return; }
          close(); setStatus("已新建预设"); await doSearch(false);
        }},
      { label: "继续添加", primary: false, onClick: async (v, close) => {
          const tags = (v.tags || "").split(/[,，;；]/).map((x) => x.trim()).filter(Boolean);
          const res = await apiPost("/library/preset", {
            action: "add", library_id: currentLibId,
            title_zh: (v.title || "").trim() || "新预设",
            prompt: (v.prompt || "").trim(),
            tags,
          });
          if (!res.ok) { setStatus(res.error || "新建预设失败"); return; }
          setStatus("已保存，可继续添加");
          await doSearch(false);
          close();
          openAgain();
        }},
    ]);
  };

  renderSelected();
  showDetail(null);
  loadLibraries();
}

function applyToNode(node, text) {
  if (!node) return;
  const names = ["面板文本", "panel_text", "提示词", "text", "prompt", "query"];
  for (const w of node.widgets || []) {
    if (names.includes(w.name)) {
      w.value = text;
      if (w.callback) w.callback(text);
      if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
      return;
    }
  }
}

function addOpenButton(node) {
  if (node._pkLibBtn) return;
  node._pkLibBtn = true;
  const btn = node.addWidget("button", "打开词库面板", null, () => openPanel(node));
  btn.serialize = false;
}

app.registerExtension({
  name: "PromptKit.LibraryPanel",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_TYPES.has(nodeData.name)) return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
      addOpenButton(this);
      return r;
    };
  },
});
