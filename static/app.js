/* Fiscus 前端主逻辑（原生 JS 单文件，与 SubDeck 同架构） */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtMoney = (n) => (n ?? 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const PALETTE = ["#ef5350", "#ab63f6", "#5c9dff", "#26a69a", "#66bb6a",
  "#ffa726", "#ff7043", "#ec407a", "#8d6e63", "#78909c"];

const state = {
  me: null, settings: null, overview: null,
  tab: "cards", cardView: localStorage.getItem("fiscus-view") || "list",
  walletOpenId: null,
  detailId: null, editId: null, editImageFile: null, editImageCleared: false,
};

/* ---------------------------------------------------------------- API */
async function api(path, opts = {}) {
  const cfg = { headers: {}, ...opts };
  if (cfg.body && !(cfg.body instanceof FormData)) {
    cfg.headers["Content-Type"] = "application/json";
    cfg.body = JSON.stringify(cfg.body);
  }
  const resp = await fetch(path, cfg);
  if (resp.status === 401 && state.me?.auth_required) { showLogin(); throw new Error("未登录"); }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `请求失败（${resp.status}）`);
  return data;
}

/* ---------------------------------------------------------------- Toast */
let toastTimer = null;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2400);
}

/* ---------------------------------------------------------------- 主题与品牌 */
function applyAccent(color) {
  const rootStyle = document.documentElement.style;
  if (!color) { rootStyle.removeProperty("--accent"); return; }
  rootStyle.setProperty("--accent", color);
}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("fiscus-theme", theme);
  const meta = $('meta[name="theme-color"]');
  meta?.setAttribute("content", theme === "dark" ? "#14161C" : (state.settings?.theme_color || "#4F6EF7"));
}
function applyBrand() {
  const s = state.settings || {};
  document.body.dataset.skin = s.skin || "glass";
  $("#brand-name").textContent = s.app_name || "Fiscus";
  document.title = s.app_name || "Fiscus";
  applyAccent(s.theme_color);
  const mark = $("#brand-mark");
  mark.innerHTML = s.brand_icon ? `<img src="/api/brand/icon?v=${Date.now() % 1e7}">` : "F";
  const bg = $("#app-bg");
  if (s.bg_image) {
    const url = s.bg_image.startsWith("preset:")
      ? `/assets/bg/${s.bg_image.split(":")[1]}.jpg` : `/api/brand/background`;
    bg.style.backgroundImage = `url("${url}")`;
    bg.classList.remove("hidden");
  } else { bg.classList.add("hidden"); }
  bg.style.setProperty("--app-mask", `${(s.bg_mask ?? 35) / 100}`);
}

/* ---------------------------------------------------------------- 登录 */
function showLogin() {
  $("#view-app").classList.add("hidden");
  $("#view-login").classList.remove("hidden");
  api("/api/brand/login-page").then((b) => {
    $("#login-title").textContent = b.app_name || "Fiscus";
    $("#login-welcome").textContent = b.login_welcome || b.login_title || "你的信用卡卡包工作台";
    if (b.theme_color) applyAccent(b.theme_color);
    const logo = $("#login-logo");
    logo.innerHTML = b.icon_ver ? `<img src="/api/brand/login-icon?v=${Date.now() % 1e7}">` : (b.app_name || "F").charAt(0).toUpperCase();
    if (b.login_bg && b.login_bg !== "none") {
      const wrap = $(".login-wrap");
      const layer = document.createElement("div");
      layer.className = "login-bg";
      const url = b.login_bg.startsWith("preset:") ? `/assets/bg/${b.login_bg.split(":")[1]}.jpg` : "/api/brand/login-background";
      layer.style.backgroundImage = `url("${url}")`;
      layer.style.setProperty("--login-mask", `${(b.login_bg_mask ?? 45) / 100}`);
      wrap.prepend(layer);
    }
  }).catch(() => {});
}
$("#login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#login-error");
  err.classList.add("hidden");
  try {
    await api("/api/login", { method: "POST", body: { password: $("#login-password").value } });
    location.reload();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

/* ---------------------------------------------------------------- 数据装载 */
async function loadAll() {
  state.me = await api("/api/me");
  if (state.me.auth_required && !state.me.logged_in) { showLogin(); return false; }
  [state.settings, state.overview] = await Promise.all([api("/api/settings"), api("/api/overview")]);
  return true;
}
async function refreshOverview() {
  state.overview = await api("/api/overview");
  renderSummary(); renderCards(); renderTodo();
}

/* ---------------------------------------------------------------- 概览条 */
function renderSummary() {
  const s = state.overview?.summary;
  if (!s) return;
  $("#sum-total").textContent = s.has_unpaid ? `¥${fmtMoney(s.total_due)}` : "已还清";
  $("#sum-nearest").textContent = s.nearest ? `最近：${s.nearest.text}` : "本期没有待办";
  const n = state.overview.cards.length;
  const totalLimit = state.overview.cards.reduce((a, c) => a + (c.limit_amount || 0), 0);
  $("#sum-cards").textContent = `${n} 张卡` + (totalLimit > 0 ? ` · 总额度 ¥${fmtMoney(totalLimit)}` : "");
}

/* ---------------------------------------------------------------- 徽章工具 */
function dueBadge(days, paid, urgentDays) {
  if (paid) return `<span class="badge badge-ok">已还</span>`;
  if (days < 0) return `<span class="badge badge-danger">已过期 ${-days} 天</span>`;
  if (days === 0) return `<span class="badge badge-danger">今天到期</span>`;
  if (days <= urgentDays) return `<span class="badge badge-warn">${days} 天后</span>`;
  if (days <= 7) return `<span class="badge badge-deep">${days} 天后</span>`;
  return `<span class="badge badge-blue">${days} 天后</span>`;
}
function amountText(c) {
  return c.bill_amount === null ? "¥ --" : `¥${fmtMoney(c.bill_amount)}`;
}

/* ---------------------------------------------------------------- 卡包页 */
function renderCards() {
  /* 临期优先：未还的按天数升序，已还的沉底（列表与卡包一致） */
  const cards = [...(state.overview?.cards || [])].sort((a, b) =>
    (a.bill_paid - b.bill_paid) || (a.next_due_days - b.next_due_days));
  const urgent = state.settings?.urgent_days || 3;
  renderCardList(cards, urgent);
  renderCardWallet(cards, urgent);
}
function renderCardList(cards, urgent) {
  const box = $("#card-list");
  if (!cards.length) {
    box.innerHTML = `<div class="empty-tip">还没有卡片。点右上「+ 添加卡片」开始。</div>`;
    return;
  }
  box.innerHTML = cards.map((c) => `
    <div class="card-row" data-id="${c.id}">
      <div class="card-avatar" style="background:${esc(c.color)}">
        ${c.image_url ? `<img src="${esc(c.image_url)}" alt="">` : esc(c.name.charAt(0))}
      </div>
      <div class="card-row-main">
        <div class="card-row-name">${esc(c.name)}${c.bank ? ` · ${esc(bankDisplay(c.bank))}` : ""}</div>
        <div class="card-row-sub">每月 ${c.repay_day} 号 · ${amountText(c)}</div>
      </div>
      ${dueBadge(c.next_due_days, c.bill_paid, urgent)}
    </div>`).join("");
  $$(".card-row", box).forEach((el) =>
    el.addEventListener("click", () => openDetail(+el.dataset.id)));
}
function walletFaceHTML(c, urgent, plain = false) {
  const head = plain
    ? `<div class="wallet-top"><div></div><div class="wallet-badge-row">${dueBadge(c.next_due_days, c.bill_paid, urgent)}</div></div>`
    : `<div class="wallet-top">
        <div>
          <div class="wallet-bank">${esc(bankDisplay(c.bank) || c.name)}</div>
          <div class="wallet-sub">${esc(c.name)}${c.notes ? ` · ${esc(c.notes)}` : ""}</div>
        </div>
        <div class="wallet-badge-row">${dueBadge(c.next_due_days, c.bill_paid, urgent)}</div>
      </div>`;
  return `
    <div class="wallet-face" style="background-color:${esc(c.color)};${c.image_url ? `background-image:url('${esc(c.image_url)}')` : ""}">
      ${head}
      <div class="wallet-top">
        <div>
          <div class="wallet-due">${c.bill_paid ? "已还清" : amountText(c)}</div>
          <div class="wallet-sub">每月 ${c.repay_day} 号还款${c.limit_amount ? ` · 额度 ¥${fmtMoney(c.limit_amount)}` : ""}</div>
        </div>
        ${c.image_url ? "" : '<div class="wallet-chip"></div>'}
      </div>
    </div>`;
}

function renderCardWallet(cards, urgent) {
  const box = $("#card-wallet");
  if (!cards.length) { box.innerHTML = ""; return; }
  const openCard = cards.find((c) => c.id === state.walletOpenId);

  /* 展开态：被点的卡置顶完整展示 + 基本信息块（含编辑入口），其余卡收到底部露边 */
  if (openCard) {
    const rest = cards.filter((c) => c.id !== openCard.id);
    box.innerHTML = `
      <div class="wallet-open">
        ${walletFaceHTML(openCard, urgent, true)}
        <div class="wallet-info-panel">
          <div class="wip-bill" style="--bill-c:${esc(openCard.color)}">
            <span class="wip-bill-label">本期账单</span>
            <span class="wip-bill-amount ${openCard.bill_amount === null ? "empty" : openCard.bill_paid ? "paid" : ""}">${
              openCard.bill_paid ? "已还清"
              : openCard.bill_amount === null ? "--"
              : `¥${fmtMoney(openCard.bill_amount)}`
            }</span>
          </div>
          <div class="wip-grid">
            <div class="wip-item"><span class="wip-k">卡名</span><span class="wip-v">${esc(openCard.name)}</span></div>
            <div class="wip-item"><span class="wip-k">银行</span><span class="wip-v">${esc(bankDisplay(openCard.bank) || "—")}</span></div>
            <div class="wip-item"><span class="wip-k">还款日</span><span class="wip-v">每月 ${openCard.repay_day} 号 · ${openCard.bill_paid ? "已还" : `${openCard.next_due_days} 天后`}</span></div>
            <div class="wip-item"><span class="wip-k">账单日</span><span class="wip-v">${openCard.bill_day ? `每月 ${openCard.bill_day} 号` : "未填"}</span></div>
            <div class="wip-item"><span class="wip-k">额度</span><span class="wip-v">${openCard.limit_amount ? `¥${fmtMoney(openCard.limit_amount)}` : "—"}</span></div>
            <div class="wip-item"><span class="wip-k">备注</span><span class="wip-v">${esc(openCard.notes || "—")}</span></div>
          </div>
          <div class="wip-actions">
            <button class="btn btn-primary btn-sm" id="btn-wallet-edit">编辑</button>
            <button class="btn btn-ghost btn-sm" id="btn-wallet-collapse">收起</button>
          </div>
        </div>
      </div>
      ${rest.map((c) => `
        <div class="wallet-card wallet-card-mini" data-id="${c.id}">
          ${walletFaceHTML(c, urgent, true)}
        </div>`).join("")}
      <div class="wallet-hint">点折叠卡面或空白处恢复完整视图</div>`;
    $("#btn-wallet-edit", box)?.addEventListener("click", () => openCardModal(openCard.id));
    const collapse = () => {
      /* 先播收起过渡再回层叠（时长对齐 CSS .25s ease） */
      const open = $(".wallet-open", box);
      if (open && !open.classList.contains("closing")) {
        open.classList.add("closing");
        setTimeout(() => {
          state.walletOpenId = null;
          renderCardWallet(cards, urgent);
        }, 250);
        box.onclick = null;
      } else {
        state.walletOpenId = null;
        renderCardWallet(cards, urgent);
      }
    };
    $("#btn-wallet-collapse", box)?.addEventListener("click", collapse);
    /* 点本卡卡面同样收起 */
    $(".wallet-open .wallet-face", box)?.addEventListener("click", collapse);
    /* 点底部折叠卡面或空白处 → 恢复完整层叠视图 */
    $$(".wallet-card-mini", box).forEach((el) => el.addEventListener("click", collapse));
    box.onclick = (e) => {
      if (e.target.closest(".wallet-open") || e.target.closest(".wallet-card-mini")) return;
      collapse();
    };
    return;
  }

  /* 层叠态 */
  box.onclick = null;              /* 清掉展开态遗留的空白收起监听，防冒泡误触 */
  box.innerHTML = cards.map((c) => `
    <div class="wallet-card" data-id="${c.id}">
      ${walletFaceHTML(c, urgent, true)}
    </div>`).join("") + `<div class="wallet-hint">点卡片展开详情 · 临期的卡完整置顶</div>`;
  $$(".wallet-card", box).forEach((el) =>
    el.addEventListener("click", (ev) => {
      ev.stopPropagation();        /* 阻断冒泡，防同一次点击被容器收起逻辑吃掉 */
      state.walletOpenId = +el.dataset.id;
      renderCardWallet(cards, urgent);
    }));
}
$("#card-view-seg")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn");
  if (!btn) return;
  state.cardView = btn.dataset.view;
  localStorage.setItem("fiscus-view", state.cardView);
  $$("#card-view-seg .seg-btn").forEach((b) => b.classList.toggle("active", b === btn));
  $("#card-list").classList.toggle("hidden", state.cardView !== "list");
  $("#card-wallet").classList.toggle("hidden", state.cardView !== "wallet");
});

/* ---------------------------------------------------------------- 聚焦详情 */
async function openDetail(cardId) {
  state.detailId = cardId;
  await renderDetail();
  $("#card-detail").classList.remove("hidden");
  $("#detail-mask").classList.remove("hidden");
}
function closeDetail() {
  state.detailId = null;
  $("#card-detail").classList.add("hidden");
  $("#detail-mask").classList.add("hidden");
}
$("#btn-detail-close")?.addEventListener("click", closeDetail);
$("#detail-mask")?.addEventListener("click", closeDetail);

async function renderDetail() {
  const c = await api(`/api/cards/${state.detailId}`);
  const urgent = state.settings?.urgent_days || 3;
  $("#detail-title").textContent = c.name;
  $("#detail-body").innerHTML = detailHtml(c, urgent);
  bindDetail(c);
}

function faceBlock(c) {
  return `
  <div class="detail-face">
    <div class="detail-face-inner" style="background-color:${esc(c.color)};${c.image_url ? `background-image:url('${esc(c.image_url)}')` : ""}">
      <div class="wallet-top">
        <div>
          <div class="wallet-bank">${esc(c.bank || c.name)}</div>
          <div class="wallet-sub">${esc(c.name)}${c.notes ? ` · ${esc(c.notes)}` : ""}</div>
        </div>
        ${c.image_url ? "" : '<div class="wallet-chip"></div>'}
      </div>
      <div class="wallet-top">
        <div class="wallet-due">${c.bill_paid ? "已还清" : amountText(c)}</div>
        <div class="wallet-badge-row">${dueBadge(c.next_due_days, c.bill_paid, state.settings?.urgent_days || 3)}</div>
      </div>
    </div>
  </div>`;
}

function detailHtml(c, urgent) {
  const f = c.fee;
  return `
  ${faceBlock(c)}

  <div class="quick-actions">
    <button class="quick-btn ${c.bill_paid ? "undone" : ""}" id="q-toggle-paid">${c.bill_paid ? "撤销已还" : "标记已还"}</button>
    <button class="quick-btn" id="q-amount">记金额</button>
  </div>

  <div class="section-label">账单与还款</div>
  <div class="info-card">
    <div class="info-row"><span class="info-label">本期账单（${esc(c.next_period)}）</span>
      <span class="info-value big" id="bill-amount">${c.bill_amount === null ? "未录" : `¥${fmtMoney(c.bill_amount)}`}</span></div>
    <div class="info-row"><span class="info-label">还款日</span>
      <span class="info-value">${esc(c.next_due)} · ${c.next_due_days < 0 ? `已过期 ${-c.next_due_days} 天` : `${c.next_due_days} 天后`}</span></div>
    <div class="info-row"><span class="info-label">账单日</span>
      <span class="info-value">${c.bill_day ? `每月 ${c.bill_day} 号` : "未设置"}</span></div>
    <div class="info-row"><span class="info-label">备注</span>
      <span class="info-value">${esc(c.notes || "--")}</span></div>
    ${(c.network || c.level) ? `<div class="info-row"><span class="info-label">卡片</span>
      <span class="info-value">${c.network ? `<span class="badge badge-blue tag">${esc(c.network)}</span>` : ""}${c.level ? ` <span class="badge badge-deep tag">${esc(c.level)}</span>` : ""}</span></div>` : ""}
    <div class="mini-form" style="margin-top:8px">
      <input type="number" class="input" id="bill-input" min="0" step="0.01" placeholder="录入本期应还金额">
      <button class="btn btn-primary btn-sm" id="bill-save">保存金额</button>
    </div>
    ${c.bills.length ? `<div class="info-row" style="margin-top:8px"><span class="info-label">最近账单</span>
      <span class="info-value">${c.bills.slice(0, 4).map((b) =>
        `${esc(b.period)} ${b.paid ? "已还" : "未还"}`).join(" · ")}</span></div>` : ""}
  </div>

  <div class="section-label">年费</div>
  <div class="info-card" id="fee-card">
    ${f && (f.amount > 0 || f.target_count > 0) ? `
      <div class="info-row"><span class="info-label">年费</span><span class="info-value">¥${fmtMoney(f.amount)}</span></div>
      <div class="info-row"><span class="info-label">下次年费日</span><span class="info-value">${esc(f.next_date)} · ${f.days} 天后</span></div>
      ${f.rule_note ? `<div class="info-row"><span class="info-label">政策</span><span class="info-value">${esc(f.rule_note)}</span></div>` : ""}
      ${f.target_count > 0 ? `
      <div class="info-row"><span class="info-label">免年费进度</span>
        <span class="info-value">已刷 <b>${f.done_count}</b> / ${f.target_count}${f.remaining > 0 ? ` · 还差 ${f.remaining} 笔` : " · 已达标"}</span></div>` : ""}
      <div class="btn-row" style="margin-top:8px">
        <button class="btn btn-ghost btn-sm" id="fee-plus">已刷 +1</button>
        <button class="btn btn-ghost btn-sm" id="fee-minus">撤销一笔</button>
        <button class="btn btn-ghost btn-sm" id="fee-edit">编辑年费</button>
      </div>` : `
      <div class="about-line sub">未配置年费。可记录金额、免年费条件和已刷笔数。</div>
      <button class="btn btn-ghost btn-sm" id="fee-edit" style="margin-top:8px">配置年费</button>`}
  </div>

  <div class="section-label">权益</div>
  <div id="benefit-list">
    ${c.benefits.length ? c.benefits.map((b) => `
      <div class="info-card" data-bid="${b.id}">
        <div class="info-row"><span class="info-label">${esc(b.name)}</span>
          <span class="info-value">剩 <b>${b.remaining}</b> / ${b.total}${b.days !== null ? ` · ${b.expire_date.slice(5)} ${b.alert ? "将清零" : "失效"}` : ""}</span></div>
        <div class="btn-row">
          <button class="btn btn-ghost btn-sm b-use">用一次</button>
          <button class="btn btn-ghost btn-sm b-restore">退回一次</button>
          <button class="btn btn-ghost btn-sm b-del">删除</button>
        </div>
      </div>`).join("") : `<div class="info-card about-line sub">暂无权益记录。</div>`}
  </div>
  <button class="btn btn-ghost btn-sm" id="benefit-add" style="margin-top:8px">+ 添加权益</button>

  <div class="other-cards">
    <div class="section-label">其他卡片</div>
    ${(state.overview?.cards || []).filter((x) => x.id !== c.id).map((x) => `
      <button class="other-card" data-id="${x.id}">
        <span>${esc(x.name)}</span>
        <span>${x.bill_paid ? "已还" : `${x.next_due_days} 天后`}</span>
      </button>`).join("") || ""}
  </div>`;
}

function bindDetail(c) {
  const urgent = state.settings?.urgent_days || 3;
  const reload = async () => { await refreshOverview(); await renderDetail(); };

  $("#q-toggle-paid").addEventListener("click", async () => {
    await api(`/api/cards/${c.id}/bill`, { method: "POST",
      body: { period: c.next_period, paid: !c.bill_paid, due_date: c.next_due,
              ...(c.bill_amount === null && !c.bill_paid ? {} : { amount: c.bill_amount ?? 0 }) } });
    toast(c.bill_paid ? "已撤销还款标记" : "已标记还清，本期停止提醒");
    await reload();
  });
  $("#q-amount").addEventListener("click", () => $("#bill-input").focus());
  $("#bill-save").addEventListener("click", async () => {
    const v = $("#bill-input").value;
    if (v === "") { toast("请输入金额"); return; }
    await api(`/api/cards/${c.id}/bill`, { method: "POST",
      body: { period: c.next_period, amount: +v, due_date: c.next_due, paid: c.bill_paid } });
    toast("金额已保存");
    await reload();
  });
  $("#fee-plus")?.addEventListener("click", async () => {
    await api(`/api/cards/${c.id}/fee/bump`, { method: "POST", body: { delta: 1 } });
    await reload();
  });
  $("#fee-minus")?.addEventListener("click", async () => {
    await api(`/api/cards/${c.id}/fee/bump`, { method: "POST", body: { delta: -1 } });
    await reload();
  });
  $("#fee-edit")?.addEventListener("click", () => feeForm(c));
  $("#benefit-add")?.addEventListener("click", () => benefitForm(c));
  $$("#benefit-list .info-card").forEach((el) => {
    const bid = +el.dataset.bid;
    const b = c.benefits.find((x) => x.id === bid);
    $(".b-use", el)?.addEventListener("click", async () => {
      await api(`/api/benefits/${bid}`, { method: "PUT",
        body: { name: b.name, total: b.total, used: Math.min(b.total, b.used + 1),
                expire_type: b.expire_type, expire_date: b.expire_date,
                cycle: b.cycle, next_reset: b.expire_date } });
      await reload();
    });
    $(".b-restore", el)?.addEventListener("click", async () => {
      await api(`/api/benefits/${bid}`, { method: "PUT",
        body: { name: b.name, total: b.total, used: Math.max(0, b.used - 1),
                expire_type: b.expire_type, expire_date: b.expire_date,
                cycle: b.cycle, next_reset: b.expire_date } });
      await reload();
    });
    $(".b-del", el)?.addEventListener("click", async () => {
      if (!confirm(`删除权益「${b.name}」？`)) return;
      await api(`/api/benefits/${bid}`, { method: "DELETE" });
      await reload();
    });
  });
  $$(".other-card").forEach((el) =>
    el.addEventListener("click", () => openDetail(+el.dataset.id)));
}

/* ---------------------------------------------------------------- 年费 / 权益内联表单 */
function feeForm(c) {
  const f = c.fee;
  const html = `
    <div class="mini-form" style="margin-top:8px; flex-wrap:wrap;">
      <input type="number" class="input" id="fee-amount" placeholder="年费金额（元）" value="${f?.amount || ""}" style="max-width:130px">
      <input type="date" class="input" id="fee-date" value="${f?.next_date || ""}" style="max-width:160px">
    </div>
    <div class="mini-form" style="margin-top:8px">
      <input class="input" id="fee-note" maxlength="100" placeholder="免年费政策，如：刷 6 次免" value="${esc(f?.rule_note || "")}">
    </div>
    <div class="mini-form" style="margin-top:8px">
      <input type="number" class="input" id="fee-target" min="0" placeholder="目标笔数" value="${f?.target_count || ""}" style="max-width:110px">
      <input type="number" class="input" id="fee-done" min="0" placeholder="已刷" value="${f?.done_count || ""}" style="max-width:90px">
      <button class="btn btn-primary btn-sm" id="fee-save">保存</button>
    </div>`;
  const card = $("#fee-card");
  card.insertAdjacentHTML("beforeend", html);
  $("#fee-edit")?.classList.add("hidden");
  $("#fee-save").addEventListener("click", async () => {
    await api(`/api/cards/${c.id}/fee`, { method: "PUT", body: {
      amount: +($("#fee-amount").value || 0),
      next_date: $("#fee-date").value,
      rule_note: $("#fee-note").value,
      target_count: +($("#fee-target").value || 0),
      done_count: +($("#fee-done").value || 0),
    } });
    toast("年费配置已保存");
    await refreshOverview(); await renderDetail();
  }, { once: true });
}

function benefitForm(c) {
  if ($("#benefit-form")) return;   /* 表单已打开，防重复 */
  const html = `
    <div class="info-card" id="benefit-form">
      <div class="mini-form"><input class="input" id="b-name" maxlength="30" placeholder="权益名，如：贵宾厅"></div>
      <div class="mini-form" style="margin-top:8px">
        <input type="number" class="input sm" id="b-total" min="0" placeholder="总量"><span class="unit">次</span>
        <select class="input" id="b-type" style="max-width:130px">
          <option value="date">固定日期失效</option>
          <option value="cycle">周期刷新</option>
        </select>
      </div>
      <div class="mini-form" style="margin-top:8px">
        <input type="date" class="input" id="b-date">
        <select class="input hidden" id="b-cycle">
          <option value="daily">每天</option><option value="weekly">每周</option>
          <option value="monthly">每月</option><option value="quarterly">每季</option>
          <option value="yearly">每年</option>
        </select>
        <button class="btn btn-primary btn-sm" id="b-save">保存</button>
      </div>
    </div>`;
  $("#benefit-list").insertAdjacentHTML("beforeend", html);
  $("#b-type").addEventListener("change", () => {
    const cyc = $("#b-type").value === "cycle";
    $("#b-date").classList.toggle("hidden", cyc);
    $("#b-cycle").classList.toggle("hidden", !cyc);
  });
  $("#b-save").addEventListener("click", async () => {
    const type = $("#b-type").value;
    const cyc = $("#b-cycle").value;
    const d = $("#b-date").value;
    if (type === "date" && !d) { toast("请选择失效日期"); return; }
    if (type === "cycle") {
      if (!d) { toast("周期型首次也需选一个刷新日"); return; }
    }
    try {
      await api(`/api/cards/${c.id}/benefits`, { method: "POST", body: {
        name: $("#b-name").value, total: +($("#b-total").value || 0), used: 0,
        expire_type: type, expire_date: type === "date" ? d : "",
        cycle: cyc, next_reset: type === "cycle" ? d : "",
      } });
      toast("权益已添加");
      await refreshOverview(); await renderDetail();
    } catch (ex) { toast(ex.message); }
  });
}

/* ---------------------------------------------------------------- 待办页 */
function todoItemHTML(c, urgent, extraBadge) {
  return `
    <div class="swipe-wrap">
      <div class="todo-actions">
        <button class="ta-btn ta-paid" data-id="${c.id}">${c.bill_paid ? "撤销" : "已还"}</button>
        <button class="ta-btn ta-amount" data-id="${c.id}">金额</button>
        <button class="ta-btn ta-edit" data-id="${c.id}">编辑</button>
      </div>
      <div class="todo-item ${c.bill_paid ? "done" : ""}" data-id="${c.id}">
        <button class="todo-check" title="${c.bill_paid ? "撤销已还" : "标记已还"}">✓</button>
        <div class="todo-main">
          <div class="todo-name">${esc(c.name)}</div>
          <div class="todo-sub">${esc(c.next_due)} · ${amountText(c)}</div>
        </div>
        ${extraBadge || dueBadge(c.next_due_days, c.bill_paid, urgent)}
        <div class="todo-hover-actions">
          <button class="th-btn th-amount" data-id="${c.id}" title="记金额">¥</button>
          <button class="th-btn th-edit" data-id="${c.id}" title="编辑账单">✎</button>
        </div>
      </div>
    </div>`;
}
function renderTodo() {
  const o = state.overview;
  if (!o) return;
  const urgent = state.settings?.urgent_days || 3;

  /* 待办角标 */
  const repayPending = o.cards.filter((c) => !c.bill_paid && c.next_due_days <= 7).length;
  const feePending = o.cards.filter((c) => c.fee?.alert).length;
  const benPending = o.cards.reduce((a, c) => a + c.benefits.filter((b) => b.alert).length, 0);
  const total = repayPending + feePending + benPending;
  const badge = $("#todo-badge");
  badge.classList.toggle("hidden", !total);
  badge.textContent = total;

  /* 横向日期条：未来 14 天 */
  const strip = $("#date-strip");
  const byDate = {};
  o.events.forEach((e) => {
    if (e.days < -3 || e.days > 14) return;
    (byDate[e.date] ||= []).push(e);
  });
  const cells = [];
  const base = new Date(o.today + "T00:00:00");
  for (let i = -1; i <= 14; i++) {
    const d = new Date(base.getTime() + i * 864e5);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const evs = byDate[iso] || [];
    const urgentToday = evs.some((e) => e.days <= urgent);
    cells.push(`<div class="date-cell${evs.length ? " has-event" : ""}${urgentToday ? " is-urgent" : ""}">
      <span class="d1">${i === 0 ? "今天" : `${d.getMonth() + 1}/${d.getDate()}`}</span>
      <span class="d2">${evs.length || "·"}</span></div>`);
  }
  strip.innerHTML = cells.join("");

  /* 三区块：还款置顶 */
  const sections = [];
  const repay = o.cards.filter((c) => !c.bill_paid || c.next_due_days <= 7)
    .sort((a, b) => a.next_due_days - b.next_due_days);
  const repayDone = o.cards.filter((c) => c.bill_paid && c.next_due_days <= 7).length;
  sections.push(`
    <div class="todo-section">
      <div class="todo-title"><span>还款（7 天内）</span>
        <span class="todo-count">待完成 ${repay.filter((c) => !c.bill_paid).length} · 已完成 <b class="ok">${repayDone}</b></span></div>
      ${repay.length ? repay.map((c) => todoItemHTML(c, urgent)).join("") : `<div class="empty-tip">7 天内没有需要还款的卡。</div>`}
    </div>`);

  /* 本期已还：可撤销（勾选后本周期静默，撤销后恢复提醒） */
  const doneCards = o.cards.filter((c) => c.bill_paid);
  sections.push(`
    <div class="todo-section">
      <div class="todo-title"><span>本期已还</span>
        <span class="todo-count">${doneCards.length} 张 · 右滑可撤销</span></div>
      ${doneCards.length ? doneCards.map((c) => todoItemHTML(c, urgent, '<span class="badge badge-ok">已还</span>')).join("") : `<div class="empty-tip">本期暂无已还的卡。</div>`}
    </div>`);

  const fees = o.cards.filter((c) => c.fee?.alert);
  sections.push(`
    <div class="todo-section">
      <div class="todo-title"><span>年费达标（30 天内）</span>
        <span class="todo-count">${fees.length} 项</span></div>
      ${fees.length ? fees.map((c) => `
        <div class="todo-item" data-id="${c.id}">
          <div class="todo-main">
            <div class="todo-name">${esc(c.name)}</div>
            <div class="todo-sub">年费 ¥${fmtMoney(c.fee.amount)} · ${esc(c.fee.rule_note || "收取中")}${c.fee.target_count ? ` · 还差 ${c.fee.remaining} 笔` : ""}</div>
          </div>
          <span class="badge ${c.fee.days <= urgent ? "badge-warn" : "badge-blue"}">${c.fee.days} 天后</span>
        </div>`).join("") : `<div class="empty-tip">30 天内没有年费事项。</div>`}
    </div>`);

  const bens = [];
  o.cards.forEach((c) => c.benefits.forEach((b) => { if (b.alert) bens.push({ c, b }); }));
  sections.push(`
    <div class="todo-section">
      <div class="todo-title"><span>权益临期（30 天内）</span>
        <span class="todo-count">${bens.length} 项</span></div>
      ${bens.length ? bens.map(({ c, b }) => `
        <div class="todo-item" data-id="${c.id}">
          <div class="todo-main">
            <div class="todo-name">${esc(c.name)} · ${esc(b.name)}</div>
            <div class="todo-sub">剩 ${b.remaining} 次 · ${esc(b.expire_date)} 清零</div>
          </div>
          <span class="badge ${b.days <= urgent ? "badge-warn" : "badge-blue"}">${b.days} 天后</span>
        </div>`).join("") : `<div class="empty-tip">30 天内没有权益清零。</div>`}
    </div>`);

  $("#todo-sections").innerHTML = sections.join("");

  const togglePaid = async (id) => {
    const c = o.cards.find((x) => x.id === id);
    if (!c) return;
    await api(`/api/cards/${id}/bill`, { method: "POST",
      body: { period: c.next_period, paid: !c.bill_paid, due_date: c.next_due,
              ...(c.bill_amount !== null ? { amount: c.bill_amount } : {}) } });
    toast(c.bill_paid ? `${c.name} 已撤销，提醒恢复` : `${c.name} 已标记还清`);
    await refreshOverview();
  };
  const openAmountEditor = async (id) => {
    await openDetail(id);
    $("#bill-input")?.focus();
  };
  /* 勾选打卡 = 标记已还 / 撤销已还 */
  $$("#todo-sections .todo-check").forEach((el) =>
    el.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      await togglePaid(+el.closest(".todo-item").dataset.id);
    }));
  /* 滑动操作层与桌面悬浮按钮（委托到区块容器，重渲染后自动生效） */
  $("#todo-sections").addEventListener("click", async (e) => {
    const btn = e.target.closest(".ta-paid, .th-amount, .ta-amount, .th-edit, .ta-edit");
    if (!btn) return;
    e.stopPropagation();
    const id = +btn.dataset.id;
    const wrap = btn.closest(".swipe-wrap");
    wrap?.classList.remove("open");
    if (btn.classList.contains("ta-paid")) await togglePaid(id);
    else if (btn.classList.contains("ta-amount") || btn.classList.contains("th-amount")) await openAmountEditor(id);
    else openDetail(id);
  });
  /* 点条目开详情（已展开滑层的条目先收起） */
  $$("#todo-sections .todo-item").forEach((el) =>
    el.addEventListener("click", (e) => {
      if (e.target.closest(".todo-check") || e.target.closest(".todo-hover-actions")) return;
      if (el.closest(".swipe-wrap")?.classList.contains("open")) {
        el.closest(".swipe-wrap").classList.remove("open");
        return;
      }
      openDetail(+el.dataset.id);
    }));
  initTodoSwipe();
}

/* 待办条目右滑操作（SubDeck 左滑骨架改向）：方向锁防误滚、半程吸附、单条互斥、点空白收回 */
const TODO_SWIPE_W = 200;
function closeTodoSwipe(except) {
  $$("#todo-sections .swipe-wrap.open").forEach((w) => {
    if (w !== except) w.classList.remove("open");
  });
}
function initTodoSwipe() {
  let sx = 0, sy = 0, dx = 0, wrapEl = null, cardEl = null, horizontal = null, startOpen = false, active = false;
  const sections = $("#todo-sections");
  if (!sections || sections.dataset.swipeInit) return;
  sections.dataset.swipeInit = "1";
  sections.addEventListener("touchstart", (e) => {
    const w = e.target.closest(".swipe-wrap");
    if (!w) return;
    wrapEl = w; cardEl = w.querySelector(".todo-item");
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
    dx = 0; horizontal = null; active = true;
    startOpen = w.classList.contains("open");
    cardEl.style.transition = "none";
  }, { passive: true });
  sections.addEventListener("touchmove", (e) => {
    if (!active || !wrapEl) return;
    dx = e.touches[0].clientX - sx;
    const dy = e.touches[0].clientY - sy;
    if (horizontal === null) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;   // 起步阈值，等方向明确
      horizontal = Math.abs(dx) > Math.abs(dy);
      if (horizontal) { closeTodoSwipe(wrapEl); wrapEl.classList.add("dragging"); }
    }
    if (!horizontal) return;                              // 纵向手势交还浏览器滚动
    if (e.cancelable) e.preventDefault();
    const base = startOpen ? TODO_SWIPE_W : 0;
    const x = Math.min(TODO_SWIPE_W, Math.max(0, base + dx));
    cardEl.style.transform = `translateX(${x}px)`;
  }, { passive: false });
  sections.addEventListener("touchend", () => {
    if (!active || !wrapEl) return;
    active = false;
    cardEl.style.transition = "";
    wrapEl.classList.remove("dragging");
    if (horizontal === null) return;                      // 纯点击，无位移
    const base = startOpen ? TODO_SWIPE_W : 0;
    wrapEl.classList.toggle("open", base + dx > TODO_SWIPE_W / 2);
    cardEl.style.transform = "";
    horizontal = null;
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".swipe-wrap")) closeTodoSwipe();
  }, true);
}

/* ---------------------------------------------------------------- 卡片编辑弹窗 */
function openCardModal(id = null) {
  state.editId = id;
  state.editImageFile = null;
  state.editImageCleared = false;
  state.editBankLogoFile = null;
  state.editBankLogoCleared = false;
  const c = id ? state.overview.cards.find((x) => x.id === id) : null;
  $("#card-modal-title").textContent = id ? "编辑卡片" : "添加卡片";
  $("#f-name").value = c?.name || "";
  $("#f-bank").value = c?.bank || "";
  $("#f-repay").value = c?.repay_day || 5;
  $("#f-bill").value = c?.bill_day || 0;
  $("#f-limit").value = c?.limit_amount || "";
  $("#f-network").value = c?.network || "";
  $("#f-level").value = c?.level || "";
  $("#f-notes").value = c?.notes || "";
  $("#f-color-hex").value = (c?.color || PALETTE[2]).toUpperCase();
  renderPalette($("#f-palette"), $("#f-color-hex").value);
  bindColorHex($("#f-color-hex"), $("#f-palette"));
  const pv = $("#f-image-preview");
  pv.innerHTML = c?.image_url ? `<img src="${esc(c.image_url)}">` : "";
  $("#btn-f-image-clear").classList.toggle("hidden", !c?.image_url);
  const bpv = $("#f-bank-logo-preview");
  bpv.innerHTML = c?.bank_logo_url ? `<img src="${esc(c.bank_logo_url)}">` : "";
  $("#btn-f-bank-logo-clear").classList.toggle("hidden", !c?.bank_logo_url);
  $("#btn-card-delete").classList.toggle("hidden", !id);
  $("#modal-mask").classList.remove("hidden");
  $("#card-modal").classList.remove("hidden");
}
function closeCardModal() {
  $("#modal-mask").classList.add("hidden");
  $("#card-modal").classList.add("hidden");
}
$("#btn-card-modal-close")?.addEventListener("click", closeCardModal);
$("#modal-mask")?.addEventListener("click", closeCardModal);
$("#btn-add-card")?.addEventListener("click", () => openCardModal());
$("#btn-detail-edit")?.addEventListener("click", () => {
  const id = state.detailId;      /* closeDetail 会清空 detailId，先取值 */
  closeDetail();
  openCardModal(id);
});
$("#btn-card-delete")?.addEventListener("click", async () => {
  if (!state.editId || !confirm("删除后该卡的账单、年费、权益记录全部清除，确定？")) return;
  await api(`/api/cards/${state.editId}`, { method: "DELETE" });
  toast("卡片已删除");
  closeCardModal();
  await refreshOverview();
});
$("#f-image")?.addEventListener("change", () => {
  const file = $("#f-image").files[0];
  if (!file) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { toast("仅支持 PNG / JPG / WebP"); return; }
  if (file.size > 4 * 1024 * 1024) { toast("图片不能超过 4MB"); return; }
  state.editImageFile = file;
  state.editImageCleared = false;
  $("#f-image-name").textContent = file.name;
  const reader = new FileReader();
  reader.onload = () => { $("#f-image-preview").innerHTML = `<img src="${reader.result}">`; };
  reader.readAsDataURL(file);
});
$("#btn-f-image-clear")?.addEventListener("click", () => {
  state.editImageFile = null;
  state.editImageCleared = true;
  $("#f-image-preview").innerHTML = "";
  $("#f-image-name").textContent = "未选择";
  $("#btn-f-image-clear").classList.add("hidden");
});
$("#f-bank-logo")?.addEventListener("change", () => {
  const file = $("#f-bank-logo").files[0];
  if (!file) return;
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) { toast("仅支持 PNG / JPG / WebP"); return; }
  if (file.size > 2 * 1024 * 1024) { toast("图片不能超过 2MB"); return; }
  state.editBankLogoFile = file;
  state.editBankLogoCleared = false;
  $("#f-bank-logo-name").textContent = file.name;
  const reader = new FileReader();
  reader.onload = () => { $("#f-bank-logo-preview").innerHTML = `<img src="${reader.result}">`; };
  reader.readAsDataURL(file);
});
$("#btn-f-bank-logo-clear")?.addEventListener("click", () => {
  state.editBankLogoFile = null;
  state.editBankLogoCleared = true;
  $("#f-bank-logo-preview").innerHTML = "";
  $("#f-bank-logo-name").textContent = "未选择";
  $("#btn-f-bank-logo-clear").classList.add("hidden");
});
$("#btn-card-save")?.addEventListener("click", async () => {
  const name = $("#f-name").value.trim();
  if (!name) { toast("请填写卡名"); return; }
  const body = {
    name, bank: $("#f-bank").value.trim(),
    repay_day: +($("#f-repay").value || 5), bill_day: +($("#f-bill").value || 0),
    limit: +($("#f-limit").value || 0), notes: $("#f-notes").value.trim(),
    network: $("#f-network").value.trim(), level: $("#f-level").value.trim(),
    color: readHex($("#f-color-hex"), PALETTE[2]),
  };
  let cardId = state.editId;
  try {
    if (cardId) {
      await api(`/api/cards/${cardId}`, { method: "PUT", body });
    } else {
      const created = await api("/api/cards", { method: "POST", body });
      cardId = created.id;
    }
    if (state.editImageFile) {
      const fd = new FormData();
      fd.append("file", state.editImageFile);
      await api(`/api/cards/${cardId}/image`, { method: "POST", body: fd });
    } else if (state.editImageCleared) {
      await api(`/api/cards/${cardId}/image`, { method: "DELETE" });
    }
    if (state.editBankLogoFile) {
      const fd = new FormData();
      fd.append("file", state.editBankLogoFile);
      await api(`/api/cards/${cardId}/bank-logo`, { method: "POST", body: fd });
    } else if (state.editBankLogoCleared) {
      await api(`/api/cards/${cardId}/bank-logo`, { method: "DELETE" });
    }
    toast("已保存");
    closeCardModal();
    await refreshOverview();
  } catch (ex) { toast(ex.message); }
});
function renderPalette(box, active) {
  box.innerHTML = PALETTE.map((c) =>
    `<button class="swatch ${c === active ? "on" : ""}" data-c="${c}" style="background:${c}"></button>`).join("");
}
/* 色号输入框为唯一真值源（SubDeck 同款）：色块点击回填输入框，输入合法时刷新高亮 */
const HEX_RE = /^#[0-9a-fA-F]{6}$/;
function bindColorHex(hexEl, paletteBox) {
  if (!hexEl || !paletteBox) return;
  hexEl.addEventListener("input", () => {
    const v = hexEl.value.trim().toUpperCase();
    if (HEX_RE.test(v)) renderPalette(paletteBox, v);
  });
  $$(".swatch", paletteBox).forEach((el) => el.addEventListener("click", () => {
    hexEl.value = el.dataset.c.toUpperCase();
    renderPalette(paletteBox, el.dataset.c);
  }));
}
function readHex(hexEl, fallback = "") {
  const v = (hexEl?.value || "").trim().toUpperCase();
  return HEX_RE.test(v) ? v : fallback;
}
/* 恢复默认主题色（照 SubDeck btn-theme-reset：直接保存空值回默认色） */
$("#btn-set-color-reset")?.addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "PUT", body: { theme_color: "" } });
    state.settings = await api("/api/settings");
    applyBrand(); fillSettings();
    toast("已恢复默认主题色");
  } catch (ex) { toast(ex.message); }
});

/* ---------------------------------------------------------------- 银行显示名 */
function bankNameMap() {
  try { return JSON.parse(state.settings?.bank_names || "{}") || {}; }
  catch { return {}; }
}
function bankDisplay(bank) {
  if (!bank) return bank;
  return bankNameMap()[bank.trim()] || bank;
}

/* 银行显示名折叠（照 SubDeck 回收记录手风琴骨架）：超过阈值折叠为汇总条，展开状态跨重渲染记忆 */
const BANK_FOLD_MAX = 5;
let bankFoldOpen = false;
const bankRowHTML = (from = "", to = "") => `
    <div class="bank-name-row">
      <input class="input bn-from" placeholder="完整银行名" maxlength="30" value="${esc(from)}">
      <span class="bn-arrow">→</span>
      <input class="input bn-to" placeholder="显示名" maxlength="30" value="${esc(to)}">
      <button class="icon-btn bn-del" title="删除">×</button>
    </div>`;

function renderBankNameRows(map) {
  const box = $("#bank-name-rows");
  if (!box) return;
  const entries = Object.entries(map || {});
  const rows = entries.map(([from, to]) => bankRowHTML(from, to)).join("");
  box.innerHTML = entries.length > BANK_FOLD_MAX
    ? `<details class="bank-fold"${bankFoldOpen ? " open" : ""}>
        <summary>银行显示名 ${entries.length} 条 · 点开编辑<span class="fold-arrow" aria-hidden="true"></span></summary>
        ${rows}
      </details>`
    : rows;
  $$(".bank-name-row .bn-del", box).forEach((el) =>
    el.addEventListener("click", () => el.closest(".bank-name-row").remove()));
}
/* toggle 不冒泡，用捕获监听把展开状态带到下一次重渲染 */
$("#bank-name-rows")?.addEventListener("toggle", (e) => {
  const fold = e.target.closest?.(".bank-fold");
  if (fold) bankFoldOpen = fold.open;
}, true);
function collectBankNameRows() {
  const map = {};
  $$("#bank-name-rows .bank-name-row").forEach((row) => {
    const from = $(".bn-from", row).value.trim();
    const to = $(".bn-to", row).value.trim();
    if (from) map[from] = to;
  });
  return map;
}
$("#btn-bank-name-add")?.addEventListener("click", () => {
  const box = $("#bank-name-rows");
  const fold = box.querySelector(".bank-fold");
  if (fold) {                        // 折叠态加行：先展开容器，行插到 details 内
    bankFoldOpen = true;
    fold.open = true;
    fold.insertAdjacentHTML("beforeend", bankRowHTML());
    $(".bn-del", fold.lastElementChild).addEventListener("click", () => fold.lastElementChild.remove());
    return;
  }
  const div = document.createElement("div");
  div.className = "bank-name-row";
  div.innerHTML = bankRowHTML();
  box.appendChild(div);
  $(".bn-del", div).addEventListener("click", () => div.remove());
});
$("#btn-bank-name-save")?.addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "PUT", body: { bank_names: collectBankNameRows() } });
    await loadSettings();
    toast("银行显示名已保存");
  } catch (ex) { toast(ex.message); }
});

/* ---------------------------------------------------------------- 设置页 */
function fillSettings() {
  const s = state.settings || {};
  $("#set-app-name").value = s.app_name || "";
  $("#set-color-hex").value = (s.theme_color || "").toUpperCase();
  renderPalette($("#set-palette"), s.theme_color || "");
  bindColorHex($("#set-color-hex"), $("#set-palette"));
  $("#icon-preview").innerHTML = s.brand_icon ? `<img src="/api/brand/icon?v=${Date.now() % 1e7}">` : "F";
  $("#set-bg-select").value = s.bg_image?.startsWith("preset:") ? s.bg_image : (s.bg_image ? "upload:" : "");
  $("#set-bg-mask").value = s.bg_mask ?? 35;
  document.querySelectorAll('input[name="set-skin"]').forEach((r) => r.checked = r.value === (s.skin || "glass"));
  if (state.me?.logged_in) updateBackupRollback();
  renderBankNameRows(bankNameMap());
  $("#set-notify-on").setAttribute("aria-pressed", s.notify_enabled ? "true" : "false");
  $("#set-notify-emails").value = s.notify_emails || "";
  $("#set-lead").value = s.notify_lead_days ?? 3;
  $("#set-hour").value = s.notify_hour ?? 8;
  $("#set-smtp-host").value = s.smtp_host || "";
  $("#set-smtp-port").value = s.smtp_port ?? 465;
  $("#set-smtp-ssl").checked = !!s.smtp_ssl;
  $("#set-smtp-user").value = s.smtp_user || "";
  $("#set-smtp-pass").value = s.smtp_pass || "";
  $("#about-version").textContent = `v${state.me?.version || ""}`;
}
$("#set-bg-select")?.addEventListener("change", () => {
  $("#set-bg-file-btn").classList.toggle("hidden", $("#set-bg-select").value !== "upload:");
});
$("#set-icon")?.addEventListener("change", () => {
  const f = $("#set-icon").files[0];
  $("#set-icon-name").textContent = f ? f.name : "未选择";
});
$("#btn-save-brand")?.addEventListener("click", async () => {
  try {
    const body = {
      app_name: $("#set-app-name").value.trim(),
      theme_color: readHex($("#set-color-hex"), ""),
      bg_mask: +$("#set-bg-mask").value,
      skin: document.querySelector('input[name="set-skin"]:checked')?.value || "glass",
    };
    const sel = $("#set-bg-select").value;
    if (sel !== "upload:") body.bg_image = sel;
    await api("/api/settings", { method: "PUT", body });
    if ($("#set-icon").files[0]) {
      const fd = new FormData();
      fd.append("file", $("#set-icon").files[0]);
      await api("/api/brand/icon", { method: "POST", body: fd });
    }
    if ($("#set-bg-file").files[0] && sel === "upload:") {
      const fd = new FormData();
      fd.append("file", $("#set-bg-file").files[0]);
      await api("/api/brand/background", { method: "POST", body: fd });
    }
    state.settings = await api("/api/settings");
    applyBrand();
    fillSettings();
    toast("界面设置已保存");
  } catch (ex) { toast(ex.message); }
});
$("#btn-clear-icon")?.addEventListener("click", async () => {
  await api("/api/brand/icon", { method: "DELETE" });
  state.settings = await api("/api/settings");
  applyBrand(); fillSettings();
  toast("已恢复默认图标");
});
$("#set-notify-on")?.addEventListener("click", () => {
  const el = $("#set-notify-on");
  el.setAttribute("aria-pressed", el.getAttribute("aria-pressed") === "true" ? "false" : "true");
});
$("#btn-save-notify")?.addEventListener("click", async () => {
  try {
    await api("/api/settings", { method: "PUT", body: {
      notify_enabled: $("#set-notify-on").getAttribute("aria-pressed") === "true",
      notify_emails: $("#set-notify-emails").value,
      notify_lead_days: +$("#set-lead").value,
      notify_hour: +$("#set-hour").value,
      smtp_host: $("#set-smtp-host").value.trim(),
      smtp_port: +$("#set-smtp-port").value,
      smtp_ssl: $("#set-smtp-ssl").checked,
      smtp_user: $("#set-smtp-user").value.trim(),
      smtp_pass: $("#set-smtp-pass").value,
    } });
    state.settings = await api("/api/settings");
    fillSettings();
    toast("邮箱提醒已保存");
  } catch (ex) { toast(ex.message); }
});
$("#btn-test-notify")?.addEventListener("click", async () => {
  try {
    const r = await api("/api/notify/test", { method: "POST", body: {
      notify_emails: $("#set-notify-emails").value,
      notify_lead_days: +$("#set-lead").value,
      smtp_host: $("#set-smtp-host").value.trim(),
      smtp_port: +$("#set-smtp-port").value,
      smtp_ssl: $("#set-smtp-ssl").checked,
      smtp_user: $("#set-smtp-user").value.trim(),
      smtp_pass: $("#set-smtp-pass").value,
    } });
    toast(r.info || "已发送");
  } catch (ex) { toast(ex.message); }
});
$("#btn-theme")?.addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("#btn-logout")?.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.reload();
});

/* ---------------------------------------------------------------- Tab 切换 */
$$(".tab-item").forEach((el) =>
  el.addEventListener("click", async () => {
    const tab = el.dataset.tab;
    state.tab = tab;
    state.walletOpenId = null;      // 离开卡包即收起展开态
    $$(".tab-item").forEach((b) => b.classList.toggle("active", b === el));
    ["cards", "todo", "settings"].forEach((t) =>
      $(`#tab-${t}`).classList.toggle("hidden", t !== tab));
    if (tab === "todo") await refreshOverview();
  }));

/* ---------------------------------------------------------------- 启动 */
(async function init() {
  applyTheme(localStorage.getItem("fiscus-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  $$("#card-view-seg .seg-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === state.cardView));
  $("#card-list").classList.toggle("hidden", state.cardView !== "list");
  $("#card-wallet").classList.toggle("hidden", state.cardView !== "wallet");
  try {
    if (!(await loadAll())) return;
  } catch (ex) { console.error(ex); return; }
  $("#view-login").classList.add("hidden");
  $("#view-app").classList.remove("hidden");
  $("#btn-logout").classList.toggle("hidden", !state.me.auth_required);
  applyBrand();
  fillSettings();
  renderSummary();
  renderCards();
  renderTodo();
})();

/* ---------------------------------------------------------------- 数据备份：导出 / 导入 / 回滚（照抄 SubDeck v1.6.11 逻辑） */
function updateBackupRollback() {
  api("/api/import-status").then((r) => {
    $("#btn-rollback")?.classList.toggle("hidden", !r.has_rollback);
  }).catch(() => {});
}
(function () {
  const mask = $("#export-mask");
  const btnExport = $("#btn-export");
  if (!btnExport || !mask) return;
  const btnRollback = $("#btn-rollback");
  const note = $("#backup-note");

  /* 导出：弹选项 → 下载 → 按是否含敏感给出对应提醒 */
  btnExport.addEventListener("click", () => mask.classList.remove("hidden"));
  const closeMask = () => mask.classList.add("hidden");
  $("#btn-export-cancel")?.addEventListener("click", closeMask);
  $("#btn-export-cancel2")?.addEventListener("click", closeMask);
  mask.addEventListener("click", (e) => { if (e.target === mask) closeMask(); });
  $("#btn-export-go").addEventListener("click", async () => {
    const sensitive = $("#export-sensitive").checked ? 1 : 0;
    closeMask();
    try {
      const resp = await fetch(`/api/export?sensitive=${sensitive}`, { credentials: "same-origin" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      const blob = await resp.blob();
      const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `fiscus-backup-${stamp}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast(sensitive
        ? "导出成功：文件含授权码等隐私敏感信息，请妥善保管"
        : "导出成功：已剔除敏感信息");
    } catch { toast("导出失败，请重试"); }
  });

  /* 导入：选文件 → 确认覆盖 → 上传 → 全量刷新 */
  const fileInput = $("#import-file");
  $("#btn-import")?.addEventListener("click", () => fileInput.click());
  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files[0];
    fileInput.value = "";
    if (!file) return;
    if (!confirm("导入将覆盖当前全部卡片、账单与设置（图片以备份包为准）。\n导入前会自动留档，可一键回滚到导入前。\n\n确定导入 " + file.name + " ？")) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch("/api/import", { method: "POST", body: fd, credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "HTTP " + r.status);
      toast(j.sensitive
        ? "导入成功（备份包含敏感信息）"
        : "导入成功（备份包不含敏感信息，相关设置保留本地现状）");
      state.settings = await api("/api/settings");
      await refreshOverview();
      applyBrand(); fillSettings();
      btnRollback.classList.remove("hidden");
      note.textContent = "上次导入：" + (j.exported_at || "").slice(0, 10) + " 的备份包 · 卡片 " + (j.cards || 0) + " 张 · 图片 " + j.assets + " 张";
    } catch (e) { toast("导入失败：" + e.message); }
  });

  /* 回滚：恢复到最近一次导入前 */
  btnRollback?.addEventListener("click", async () => {
    if (!confirm("回滚将恢复到最近一次导入前的状态（回滚后存档作废）。确定？")) return;
    try {
      const r = await fetch("/api/import/rollback", { method: "POST", credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "HTTP " + r.status);
      toast("已回滚到导入前");
      state.settings = await api("/api/settings");
      await refreshOverview();
      applyBrand(); fillSettings();
      btnRollback.classList.add("hidden");
      note.textContent = "";
    } catch (e) { toast("回滚失败：" + e.message); }
  });
})();

/* ---------------------------------------------------------------- 设置页左导航：点击平滑滚动 + 滚动高亮联动（照抄 SubDeck v1.6.9，仅 ≥1024 显示） */
(function () {
  const nav = $("#settings-nav");
  if (!nav) return;
  nav.addEventListener("click", (e) => {
    const a = e.target.closest("a");
    if (!a) return;
    e.preventDefault();
    history.replaceState(null, "", a.getAttribute("href"));
    const target = document.querySelector(a.getAttribute("href"));
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  const links = [...nav.querySelectorAll("a")];
  const groups = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  let ticking = false;
  function highlight() {
    ticking = false;
    let cur = -1;
    const ref = 96;   /* sticky 顶栏高度余量 */
    groups.forEach((g, i) => { if (g.getBoundingClientRect().top <= ref + 8) cur = i; });
    links.forEach((a, i) => a.classList.toggle("on", i === cur));
  }
  document.addEventListener("scroll", () => {
    if (!ticking) { ticking = true; requestAnimationFrame(highlight); }
  }, { passive: true });
  highlight();
})();
