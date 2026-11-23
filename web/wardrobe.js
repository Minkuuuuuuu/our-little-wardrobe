(() => {
  "use strict";
  /* 内衣柜那一页：今天穿什么、藤做的两根衣杆、晾衣绳、地上的篮子和盆、祂放着的和祂手里的。
     公开版不画内衣本体：每一件挂成一小块叠好的布，颜色从她写的颜色词里来。数据来自 /api/v1。 */
  const API = "/api/v1";
  const $ = (s, root = document) => root.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const F = (v) => (Math.round(v * 10) / 10).toString();
  const ERRORS = {
    network: "网络没接上，再试一次。", forbidden: "这一页只给她看。", color_or_style_required: "颜色和款式至少填一个。",
    code_taken: "这个编号已经有了。", invalid_code: "编号只能用字母、数字和 -。", item_is_worn: "这件正穿着，先在上面换下来。",
    item_washing: "祂正在洗这件。", wrong_kind_for_slot: "这件放不到这一格。", invalid_text: "写点什么再保存。",
    invalid_count: "数量要在 0 到 999 之间。", invalid_stock_kind: "没有这样东西。", shower_not_found: "这次洗澡已经不用选了。",
    invalid_old_to: "换下来的只能去洗衣篮或交给祂。"
  };
  const errorText = (err) => ERRORS[err && err.code] || "没有成功，再试一次。";
  async function api(path, { method = "GET", body } = {}) {
    let res;
    try {
      res = await fetch(API + path, { method, credentials: "same-origin",
        headers: body !== undefined ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
        body: body !== undefined ? JSON.stringify(body) : undefined });
    } catch (_) { throw Object.assign(new Error("network"), { code: "network" }); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || "failed"), { code: data.error || "failed", data });
    return data;
  }
  function toast(text) { const t = $("#toast"); t.textContent = text; t.dataset.show = "true"; clearTimeout(toast.t); toast.t = setTimeout(() => { t.dataset.show = "false"; }, 2200); }
  function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  /* ── a piece, without drawing the piece: a small square of folded cloth in her colour, lace dots if she said lace ── */
  const COLOURS = [["粉蓝", "#c3cdee"], ["藏青", "#9aa6cc"], ["酒红", "#d98d98"], ["墨绿", "#8fae8a"], ["雾蓝", "#b9cfdd"], ["米白", "#f3ebdc"],
    ["浅灰", "#d9dbe3"], ["灰", "#c4c8d8"], ["黑", "#3a3046"], ["蓝", "#c4dbee"], ["绿", "#a9c493"], ["紫", "#b9a9db"], ["白", "#fcf6f4"],
    ["粉", "#f6c1cb"], ["红", "#f1a6a7"], ["黄", "#ffe3b3"], ["橙", "#f6beb0"], ["米", "#efe3cf"], ["杏", "#f2d5b8"], ["肤", "#efd2bd"],
    ["裸", "#efd2bd"], ["棕", "#c9b09a"], ["咖", "#c9b09a"]];
  const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const rgb2hex = (c) => "#" + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, t) => { const x = hex2rgb(a), y = hex2rgb(b); return rgb2hex(x.map((v, i) => v + (y[i] - v) * t)); };
  function colourOf(item) {
    const text = `${item.color || ""}${item.style || ""}`;
    const hit = COLOURS.find(([w]) => text.includes(w));
    return hit ? hit[1] : "#e8dcc8";
  }
  function garment(item) {
    // a folded square of cloth: the top-right corner turned down, a stitched hem, lace dots if she said lace
    const c = colourOf(item), deep = mix(c, "#2b2a33", .18), light = mix(c, "#ffffff", .35);
    const lace = /蕾丝|花边|lace/i.test(`${item.style}${item.note || ""}`);
    const r = rng(item.id * 13), tilt = (r() * 8 - 4).toFixed(1);
    return `<g transform="rotate(${tilt}) scale(.62)">`
      + `<path class="cloth" d="M-26 -16 Q-27 -19 -24 -19 L14 -19 L26 -7 L26 16 Q26 19 23 19 L-23 19 Q-26 19 -26 16 Z" fill="${c}"/>`
      + `<path class="cloth" d="M14 -19 L26 -7 L14 -7 Q13 -7 13 -8 Z" fill="${deep}"/>`
      + `<path class="cloth-fold" d="M-21 -13 L8 -13 M-21 -7 L4 -7"/>`
      + `<path d="M-23 12 Q0 9 23 12" fill="none" stroke="${light}" stroke-width="1" stroke-dasharray="1.5 2.5" stroke-linecap="round"/>`
      + (lace ? `<path class="cloth-lace" d="M-26 19 q3 4 6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0"/>` : "")
      + `</g>`;
  }
  const miniSVG = (item, w = 70) => `<svg width="${w}" viewBox="-40 -10 80 66" aria-hidden="true"><g transform="translate(0 22)">${garment(item)}</g></svg>`;

  /* ── 挂在树枝上：钩子在 (0,0)；d 是挂绳多长 ── */
  function hanger(kind, d, cls = "") {
    let s = "";
    if (d > 0) s += `<ellipse class="twine" cx="0" cy="0" rx="3.4" ry="4.6"/><path class="twine" d="M0 3 L0 ${d + 1}"/>`;
    s += `<path class="hk ${cls}" d="M0 ${d + 10} L0 ${d + 5} C0 ${d - 2} 7 ${d - 2} 7 ${d + 2}"/>`;
    if (kind === "bra") s += `<path class="hk ${cls}" d="M0 ${d + 10} L-27 ${d + 23} Q-30 ${d + 25.5} -26 ${d + 25.5} L26 ${d + 25.5} Q30 ${d + 25.5} 27 ${d + 23} Z"/>`;
    else s += `<path class="hk ${cls}" d="M-30 ${d + 10} L30 ${d + 10}"/>`;
    return s;
  }
  function hangingSVG(item, d) {
    const off = item.kind === "bra" ? d + 40 : d + 30;
    const clips = item.kind === "bra" ? "" : `<rect class="clip" x="-27" y="${d + 7}" width="4" height="12" rx="1"/><rect class="clip" x="23" y="${d + 7}" width="4" height="12" rx="1"/>`;
    const name = nameOf(item), short = name.length > 7 ? name.slice(0, 6) + "…" : name;
    return `<svg width="84" height="96" viewBox="-42 -6 84 96" aria-hidden="true">${hanger(item.kind, d)}<g transform="translate(0 ${off})">${garment(item)}</g>${clips}`
      + `<text class="svgtxt name" x="0" y="${off + 26}" text-anchor="middle">${esc(short)}</text></svg>`;
  }

  /* ── 衣杆：鼠尾草绿的藤，羽状复叶，末端一串小花 ── */
  const SAGE = "#8aa26b", SAGE_L = "#b4cba0", ROSE = "#f5afbb";
  function nvLeaf(x, y, deg, s, fill = SAGE_L) {
    return `<g transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${deg.toFixed(0)})"><path d="M0 0 C${(s * .22).toFixed(1)} ${(-s * .32).toFixed(1)} ${(s * .72).toFixed(1)} ${(-s * .28).toFixed(1)} ${s.toFixed(1)} 0 C${(s * .72).toFixed(1)} ${(s * .28).toFixed(1)} ${(s * .22).toFixed(1)} ${(s * .32).toFixed(1)} 0 0Z" fill="${fill}"/><path d="M${(s * .14).toFixed(1)} 0 L${(s * .8).toFixed(1)} 0" stroke="rgba(255,255,255,.62)" stroke-width=".9" stroke-linecap="round"/></g>`;
  }
  function raceme(x, y, n, sz) {
    let s = `<path d="M${x} ${y} q3 ${n * 2.6} 1 ${n * 5.2}" fill="none" stroke="${SAGE}" stroke-width="1.3" stroke-linecap="round"/>`;
    for (let j = n - 1; j >= 0; j--) {
      const u = j / (n - 1), cy = y + 3 + u * n * 5, sd = j % 2 ? 1 : -1, z = sz * (1 - .55 * u) + 2;
      const cx = x + 1 + sd * z * .34 + u * 1.5;
      s += u > .8 ? `<ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${(z * .34).toFixed(1)}" ry="${(z * .5).toFixed(1)}" fill="${SAGE}"/>`
        : `<ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${(z * .62).toFixed(1)}" ry="${(z * .48).toFixed(1)}" transform="rotate(${sd * 22} ${cx.toFixed(1)} ${cy.toFixed(1)})" fill="${ROSE}" stroke="rgba(255,255,255,.7)" stroke-width=".8"/>`;
    }
    return s;
  }
  function makeBranch(w, o) {
    const r = rng(o.seed), p1 = r() * 6, p2 = r() * 6;
    const yAt = (x) => o.y0 + (o.y1 - o.y0) * (x / w) + Math.sin(x / 61 + p1) * 3.2 + Math.sin(x / 23 + p2) * 1.2;
    const th = (x) => Math.max(1.6, o.thick * .52 * (1 - .62 * Math.max(0, x) / w));
    const xs = []; for (let x = -14; x < w; x += 6) xs.push(x); xs.push(w);
    const top = xs.map((x) => `${x.toFixed(1)} ${(yAt(x) - th(x) / 2).toFixed(1)}`);
    const bot = xs.slice().reverse().map((x) => `${x.toFixed(1)} ${(yAt(x) + th(x) / 2).toFixed(1)}`);
    let s = "";
    const n = Math.max(3, Math.round(w / 110));
    for (let i = 0; i < n; i++) {
      const x0 = w * (.06 + .88 * (i + r() * .6) / n), up = r() < .5 ? -1 : 1;
      const a = -Math.PI / 2 + up * (.55 + r() * .35), L = 26 + r() * 16;
      const y0 = yAt(x0), mx = x0 + Math.cos(a) * L * .5 + up * 3, my = y0 + Math.sin(a) * L * .5;
      const ex = x0 + Math.cos(a + up * .25) * L, ey = y0 + Math.sin(a + up * .25) * L;
      s += `<path d="M${x0.toFixed(1)} ${y0.toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}" fill="none" stroke="${SAGE}" stroke-width="1.4" stroke-linecap="round"/>`;
      for (let j = 1; j <= 4; j++) {
        const t = j / 5, px = x0 + (ex - x0) * t + (mx - (x0 + ex) / 2) * 2 * t * (1 - t), py = y0 + (ey - y0) * t + (my - (y0 + ey) / 2) * 2 * t * (1 - t);
        const deg = (a + up * .25) * 180 / Math.PI + (j % 2 ? 52 : -52);
        s += nvLeaf(px, py, deg, 9 + r() * 3);
      }
      s += nvLeaf(ex, ey, (a + up * .25) * 180 / Math.PI, 11);
    }
    s += `<path d="M${top.join(" L")} L${bot.join(" L")} Z" fill="${SAGE}"/>`;
    s += `<path d="M${xs.map((x) => `${x.toFixed(1)} ${(yAt(x) - th(x) / 2 + .6).toFixed(1)}`).join(" L")}" fill="none" stroke="rgba(255,255,255,.35)" stroke-width=".7"/>`;
    for (let x = 20, k = 0; x < w - 10; x += 30 + (k % 3) * 6, k++) {
      const y = yAt(x), sd = k % 2 ? -1 : 1, t2 = th(x) / 2;
      s += `<path d="M${(x - 2).toFixed(1)} ${(y + sd * t2 * .6).toFixed(1)} L${(x + 3.5).toFixed(1)} ${(y + sd * (t2 + 4.2)).toFixed(1)} L${(x + 2.5).toFixed(1)} ${(y + sd * t2 * .6).toFixed(1)} Z" fill="${SAGE}"/>`;
    }
    const ex = w, ey = yAt(w);
    s += `<path d="M${ex} ${ey.toFixed(1)} c6 -1 12 -6 10 -12 c-1 -4 -6 -4 -6 0 c0 3 3 3 4 1" fill="none" stroke="${SAGE}" stroke-width="1.1" stroke-linecap="round"/>`;
    s += raceme(w - 14, yAt(w - 14) + 1, 7, 9);
    return { svg: s, yAt };
  }
  const pieceVars = (item) => { const r = rng(item.id * 97); return `--dur:${(4.2 + r() * 2.4).toFixed(2)}s;--delay:${(-r() * 4).toFixed(2)}s;--rest:${item.sneaked ? "9deg" : "0deg"}`; };
  const sneakMark = () => `<svg width="18" height="14" viewBox="0 0 18 14" class="sneak" aria-hidden="true">${nvLeaf(1, 8, -28, 13)}</svg>`;
  function pieceButton(item, x, y, extra = "") {
    const d = Math.round(rng(item.id * 31)() * 14);
    return `<button type="button" class="piece ${extra}" data-id="${item.id}" title="${esc(nameOf(item))}" aria-label="${esc(nameOf(item))}" style="left:${(x - 42).toFixed(1)}px;top:${(y - 6).toFixed(1)}px;${pieceVars(item)}">${hangingSVG(item, d)}${item.sneaked ? sneakMark() : ""}</button>`;
  }
  const nameOf = (item) => item ? item.name || item.code || (item.kind === "bra" ? "内衣" : "内裤") : "";

  /* ── 内衣柜（GET /wardrobe） ── */
  let wardrobe = { slots: { top: { state: "unset" }, bottom: { state: "unset" } }, items: [], recent: [], period: null, stock: null, pick: null, shower: null };
  let byId = new Map();
  const items = () => wardrobe.items;
  const nowS = () => Date.now() / 1000;
  const WASH_SECONDS = (wardrobe.rules && wardrobe.rules.wash_seconds) || 300;
  const SPECIAL = { bare: "没穿", night_pants: "安睡裤" };
  const clock = (ts) => { const d = new Date(ts * 1000); return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const dayLabel = () => { const d = new Date(Date.now() - 4 * 3600e3); return `${d.getMonth() + 1}/${d.getDate()} 周${"日一二三四五六"[d.getDay()]}`; };
  function slotValue(slot) {
    const s = wardrobe.slots[slot] || {};
    return s.state === "item" && s.item ? s.item.id : s.state in SPECIAL ? s.state : null;
  }
  function renderToday() {
    const host = $("#today");
    const W = Math.min(host.clientWidth || 380, 660), H = 196;
    const br = makeBranch(W * .94, { seed: 5, y0: 40, y1: 30, thick: 11 });
    let html = `<svg class="branch" width="${W}" height="${H}">${br.svg}`;
    const pos = { top: W * .3, bottom: W * .6 };
    const ends = {};
    for (const slot of ["top", "bottom"]) {
      const x = pos[slot], y = br.yAt(x), len = 20, v = slotValue(slot);
      ends[slot] = [x, y + len + 4];
      html += `<ellipse class="twine" cx="${F(x)}" cy="${F(y)}" rx="4" ry="5.5"/><path class="twine" d="M${F(x)} ${F(y + 4)} L${F(x)} ${F(y + len)}"/>`;
      if (typeof v !== "number") {
        html += `<circle class="hk ${v == null ? "ghost" : ""}" cx="${F(x)}" cy="${F(y + len + 5)}" r="5"/>`;
        html += `<text class="svgtxt" x="${F(x)}" y="${F(y + len + 34)}" text-anchor="middle" style="font-size:14px;fill:var(--ink)">${SPECIAL[v] || "还没标"}</text>`;
      }
    }
    html += `</svg><span class="today-head hand"><b>今天</b>　${dayLabel()}</span>`;
    for (const slot of ["top", "bottom"]) {
      const [x, y] = ends[slot], v = slotValue(slot);
      html += `<button type="button" class="slot-tag" data-slot="${slot}" style="left:${F(x + 40)}px;top:${F(y + 34)}px">${slot === "top" ? "上身" : "下身"} ▾</button>`;
      const it = typeof v === "number" ? (byId.get(v) || wardrobe.slots[slot].item) : null;
      if (it) html += pieceButton(it, x, y - 4, "worn");
      else html += `<button type="button" class="slot-zone" data-slot="${slot}" aria-label="${slot === "top" ? "上身" : "下身"}穿着" style="left:${F(x - 48)}px;top:${F(y - 10)}px"></button>`;
    }
    host.innerHTML = html;
  }
  function renderCare() {
    const host = $("#care");
    const rows = [];
    const sh = wardrobe.shower;
    if (sh && sh.showing) rows.push(`<button type="button" class="care-row care-act" data-care="shower-pick"><b>洗完了？</b>点这里换上新的那套 ›</button>`);
    else if (sh) rows.push(`<p class="care-row"><b>洗澡中</b>　<span data-shower-left="${sh.prompt_at}">${Math.max(1, sh.minutes_left)} 分钟</span>后问你换了哪套　<button type="button" class="tiny" data-care="shower-skip">这次不换</button></p>`);
    else rows.push(`<p class="care-row"><button type="button" class="tiny" data-care="shower">去洗澡了</button><span class="hand">　半小时后来问你换了哪套</span></p>`);
    const p = wardrobe.period, st = wardrobe.stock || {};
    const count = (k) => st[k] ? `<button type="button" class="count" data-care="stock" data-kind="${k}" aria-label="改${st[k].label}数量">${st[k].label} <b>${st[k].count}</b> ${st[k].unit}</button>` : "";
    if (p && p.active) {
      const last = wardrobe.last_change ? `上次换 ${clock(wardrobe.last_change.at)}` : "今天还没记过换";
      rows.push(`<p class="care-row period"><b>经期第 ${p.day} 天</b>　${count("pad")}　${count("night_pants")}　<span class="hand">${last}</span></p>`);
      rows.push(`<p class="care-row"><button type="button" class="tiny her" data-care="changed" data-kind="pad">换了卫生巾</button><button type="button" class="tiny her" data-care="night-pants">换上安睡裤</button><span class="hand">　祂白天每 ${(wardrobe.rules || {}).pad_hours || 5} 小时提醒你一次，点一下它就从头数</span></p>`);
    } else if (st.pad || st.night_pants) {
      rows.push(`<p class="care-row faint">${count("pad")}　${count("night_pants")}</p>`);
    }
    const pk = wardrobe.pick;
    if (pk && (pk.top || pk.bottom) && !pk.outcome) {
      const pieces = ["top", "bottom"].filter((s) => pk[s]).map((s) => `<button type="button" class="pick-piece" data-id="${pk[s].id}">${miniSVG(pk[s], 44)}<span>${esc(nameOf(pk[s]))}</span></button>`).join("");
      rows.push(`<div class="care-row pick"><span class="chip him">祂挑的 · ${esc(pk.for)}</span>${pieces}${pk.line ? `<i class="hand">${esc(pk.line)}</i>` : ""}</div>`);
    }
    host.innerHTML = rows.join("");
  }
  function renderRail(kind) {
    const host = $(`#rail-${kind}`);
    const list = items().filter((i) => i.kind === kind && (i.state === "closet" || i.state === "wearing"));
    const W0 = host.clientWidth || 380, H = 168;
    const gap = Math.max(96, Math.min(150, (W0 - 150) / (list.length + 1)));
    const W = Math.max(W0, 92 + (list.length + 1) * gap);
    const o = kind === "bra" ? { seed: 11, y0: 34, y1: 50, thick: 12 } : { seed: 23, y0: 52, y1: 32, thick: 11 };
    const br = makeBranch(W - 6, o);
    let html = `<span class="rail-label hand">${kind === "bra" ? "内衣" : "内裤"} · ${list.length} 件</span><div class="rail-scroll"><div class="rail-inner" style="width:${F(W)}px">`;
    html += `<svg class="branch" width="${F(W)}" height="${H}">${br.svg}</svg>`;
    list.forEach((it, i) => {
      const x = 78 + i * gap + (rng(it.id * 7)() * 16 - 8), y = br.yAt(x);
      if (it.state === "wearing") {
        html += `<button type="button" class="piece ghost" data-id="${it.id}" aria-label="${esc(nameOf(it))}（穿着）" style="left:${F(x - 42)}px;top:${F(y - 6)}px"><svg width="84" height="96" viewBox="-42 -6 84 96" aria-hidden="true">${hanger(kind, 0, "")}<text class="svgtxt" x="0" y="46" text-anchor="middle">穿着呢</text></svg></button>`;
      } else html += pieceButton(it, x, y);
    });
    const px = 78 + list.length * gap, py = br.yAt(px);
    html += `<button type="button" class="piece plus" data-add="${kind}" aria-label="加一件" style="left:${F(px - 42)}px;top:${F(py - 6)}px"><svg width="84" height="96" viewBox="-42 -6 84 96" aria-hidden="true">${hanger(kind, 0, "")}<text class="svgtxt big" x="0" y="${kind === "bra" ? 58 : 48}" text-anchor="middle">＋</text></svg></button>`;
    html += `</div></div>`;
    host.innerHTML = html;
    const sc = host.querySelector(".rail-scroll");
    let kickT = 0;
    sc.addEventListener("scroll", () => {
      if (host.classList.contains("kick")) return;
      host.classList.add("kick");
      clearTimeout(kickT);
      kickT = setTimeout(() => host.classList.remove("kick"), 1300);
    }, { passive: true });
  }
  const minutesSince = (ts) => Math.max(0, Math.round((nowS() - (ts || nowS())) / 60));
  function renderLine() {
    const host = $("#line");
    const list = items().filter((i) => i.state === "drying");
    host.hidden = !list.length;
    if (!list.length) { host.innerHTML = ""; return; }
    const W0 = host.clientWidth || 380, H = 150, a = 26, m = 58, b = 20;
    const W = Math.max(W0, (list.length + 1) * 96);
    const ry = (x) => { const t = x / W; return (1 - t) ** 2 * a + 2 * (1 - t) * t * m + t * t * b; };
    let s = `<div class="rail-scroll"><div class="rail-inner" style="width:${W}px"><svg width="${W}" height="${H}"><path class="rope" d="M-4 ${a} Q${W / 2} ${m} ${W + 4} ${b}"/>`;
    list.forEach((it, i) => {
      const x = W * (i + 1) / (list.length + 1) + (rng(it.id)() * 30 - 15), y = ry(x);
      const r = rng(it.id * 5), mins = minutesSince(it.state_at);
      s += `<g class="hitg" data-id="${it.id}"><g class="swing" style="--delay:${(-r() * 3).toFixed(2)}s"><g transform="translate(${F(x)} ${F(y + 18)})">${garment(it)}</g></g>`;
      s += `<rect class="pin" x="${F(x - 16)}" y="${F(y - 6)}" width="4" height="11" rx="1"/><rect class="pin" x="${F(x + 12)}" y="${F(y - 6)}" width="4" height="11" rx="1"/>`;
      const drops = Math.max(0, 4 - Math.floor(mins / 15));
      for (let k = 0; k < drops; k++) s += `<path class="drip" style="--delay:${(k * .45 + r()).toFixed(2)}s" transform="translate(${F(x - 14 + r() * 28)} ${F(y + 40)})" d="M0 0 C2 3 2.5 5 0 6.5 C-2.5 5 -2 3 0 0Z"/>`;
      s += `<text class="svgtxt" x="${F(x)}" y="${F(y + 68)}" text-anchor="middle">${esc(nameOf(it))}</text><text class="svgtxt" x="${F(x)}" y="${F(y + 82)}" text-anchor="middle">晾了 ${mins < 60 ? `${mins} 分钟` : mins < 2880 ? `${Math.floor(mins / 60)} 小时` : `${Math.floor(mins / 1440)} 天`}</text></g>`;
    });
    s += `</svg></div></div><span class="rail-label hand">晾着</span>`;
    host.innerHTML = s;
  }
  function basketSVG(list) {
    const hw = (y) => 64 - (y - 46) * (11 / 72);
    let s = `<svg width="170" height="132" viewBox="0 0 170 132"><ellipse cx="85" cy="46" rx="64" ry="13" fill="none" class="weave"/>`;
    list.forEach((it, i) => {
      const x = 85 + (i - (list.length - 1) / 2) * 30, y = 30 + (i % 2) * 6, rot = [-24, 18, -10, 26][i % 4];
      s += `<g class="hitg" data-id="${it.id}" transform="translate(${x} ${y}) rotate(${rot})">${garment(it)}</g>`;
    });
    s += `<path class="basket-body" d="M21 46 L32 118 Q85 128 138 118 L149 46 A64 13 0 0 1 21 46 Z"/>`;
    for (let k = 0; k <= 8; k++) { const t = k / 8, xt = 24 + t * 122, xb = 34 + t * 102; s += `<path class="weave" d="M${xt} ${50 + Math.sin(t * Math.PI) * 8} L${xb} ${118 + Math.sin(t * Math.PI) * 6}"/>`; }
    for (const y of [66, 82, 98, 112]) { const w = hw(y); s += `<path class="weave" d="M${85 - w} ${y} Q${85 - w / 2} ${y + 6} 85 ${y + 7} T${85 + w} ${y}"/>`; }
    s += `<path class="rimln" d="M21 46 A64 13 0 0 0 149 46"/></svg>`;
    return s;
  }
  function basinSVG(it) {
    const total = WASH_SECONDS, left = it.washLeft, C = 2 * Math.PI * 11;
    let s = `<svg width="180" height="122" viewBox="0 0 180 122"><ellipse cx="90" cy="44" rx="72" ry="14" fill="none" class="weave"/>`;
    s += `<g class="hitg" data-id="${it.id}" transform="translate(90 30) rotate(-7)">${garment(it)}</g>`;
    s += `<ellipse class="water" cx="90" cy="52" rx="63" ry="9"/>`;
    s += `<path class="basin-body" d="M18 44 L31 98 Q90 113 149 98 L162 44 A72 14 0 0 1 18 44 Z"/>`;
    const r = rng(it.id);
    for (let k = 0; k < 7; k++) s += `<circle class="bubble" style="--delay:${(k * .37).toFixed(2)}s" cx="${(50 + r() * 80).toFixed(0)}" cy="${(48 + r() * 6).toFixed(0)}" r="${(1.8 + r() * 2.6).toFixed(1)}"/>`;
    s += `<path class="rimln" style="stroke:var(--line-soft)" d="M18 44 A72 14 0 0 0 162 44"/>`;
    s += `<circle class="ring-bg" cx="160" cy="14" r="11"/><circle class="ring" cx="160" cy="14" r="11" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${(C * left / total).toFixed(1)}"/></svg>`;
    return s;
  }
  function pillowSVG(it) {
    return `<svg width="190" height="112" viewBox="0 0 190 112"><path class="pillow" d="M14 22 Q30 26 52 20 Q96 12 140 18 Q160 22 176 16 Q168 36 172 56 Q176 78 174 98 Q158 90 138 94 Q96 102 52 96 Q30 92 12 100 Q18 80 16 58 Q14 38 14 22 Z"/>`
      + `<path class="seam" d="M24 30 Q96 18 164 28 M24 88 Q96 96 164 86"/><path class="fold" d="M14 22 l10 7 M176 16 l-9 9 M12 100 l11 -7 M174 98 l-10 -6"/>`
      + `<g class="hitg" data-id="${it.id}" transform="translate(98 56) rotate(-14)">${garment(it)}</g></svg>`;
  }
  function otherSVG(it) {
    const tw = Math.max(52, it.place.length * 12 + 18);
    return `<svg width="${118 + tw}" height="112" viewBox="0 0 ${118 + tw} 112"><path class="groundln" d="M8 96 Q80 90 ${110 + tw} 98"/>`
      + `<g class="hitg" data-id="${it.id}" transform="translate(62 60) rotate(9)">${garment(it)}</g>`
      + `<path class="twine" d="M86 50 Q98 34 108 30"/><g transform="translate(106 18) rotate(8)"><path class="tagp" d="M0 6 L8 0 L${tw} 0 L${tw} 22 L8 22 L0 16 Z"/><circle cx="6" cy="11" r="1.6" fill="rgba(80,60,30,.5)"/><text class="tagt" x="13" y="15">${esc(it.place)}</text></g></svg>`;
  }
  function palmSVG(it) {
    return `<svg width="170" height="118" viewBox="0 0 170 118"><path class="palm" d="M30 70 Q26 52 40 50 Q52 48 58 62 L60 40 Q60 28 70 28 Q80 28 80 40 L82 34 Q84 20 94 22 Q104 24 102 38 L104 36 Q108 24 118 28 Q126 32 122 46 L124 50 Q134 40 140 50 Q146 60 134 72 Q118 92 92 98 Q58 104 36 86 Q30 80 30 70Z"/>`
      + `<path class="fold" d="M62 70 Q78 60 96 66 M58 82 Q80 74 104 80"/><g class="hitg" data-id="${it.id}" transform="translate(88 62) rotate(-12)">${garment(it)}</g></svg>`;
  }
  const washLeft = (it) => Math.max(0, Math.round(WASH_SECONDS - (nowS() - (it.state_at || nowS()))));
  const fmt = (sec) => sec > 0 ? `还有 ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}` : "快好了";
  function renderFloor() {
    const dirty = items().filter((i) => i.state === "dirty"), washing = items().filter((i) => i.state === "washing");
    const placed = items().filter((i) => i.state === "placed"), given = items().filter((i) => i.state === "given");
    let html = `<figure class="spot" style="--dy:-6px">${basketSVG(dirty)}<figcaption>${dirty.length ? `没洗 · ${dirty.length} 件` : "洗衣篮空着"}</figcaption></figure>`;
    for (const it of given) html += `<figure class="spot" style="--dy:-2px">${palmSVG(it)}<figcaption>祂手里 · 你交的</figcaption></figure>`;
    for (const it of washing) html += `<figure class="spot" style="--dy:4px">${basinSVG({ ...it, washLeft: washLeft(it) })}<figcaption class="wash-cap" data-wash="${it.id}">祂在洗 · ${fmt(washLeft(it))}</figcaption></figure>`;
    for (const it of placed) {
      const place = it.place || "别处";
      html += place === "床头"
        ? `<figure class="spot" style="--dy:-12px">${pillowSVG(it)}<figcaption>床头 · 祂放的</figcaption></figure>`
        : `<figure class="spot" style="--dy:2px">${otherSVG({ ...it, place })}<figcaption>${esc(place)} · 祂放的</figcaption></figure>`;
    }
    $("#floor").innerHTML = html;
  }
  let breezeOpen = false;
  function renderBreeze() {
    const lines = wardrobe.recent || [];
    $("#breeze").hidden = !lines.length;
    $("#breeze").innerHTML = breezeOpen
      ? `<span class="more">收起</span><span class="hand">最近的变化</span><ol>${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ol>`
      : `<span class="more">▾</span><span class="hand">最近 · </span><b>${esc(lines[0] || "")}</b>`;
  }
  function paintWardrobe() { byId = new Map(items().map((i) => [i.id, i])); renderToday(); renderCare(); renderRail("bra"); renderRail("panties"); renderLine(); renderFloor(); renderBreeze(); }
  async function loadWardrobe() {
    try { wardrobe = await api("/wardrobe"); paintWardrobe(); }
    catch (err) { toast(errorText(err)); }
  }
  async function wear(slot, value, extra = {}) {
    try { wardrobe = await api("/wardrobe/slots", { method: "PUT", body: { [slot]: value, ...extra } }); paintWardrobe(); toast("换好了"); }
    catch (err) { toast(errorText(err)); }
  }
  async function setState(item, state) {
    try { await api(`/wardrobe/${item.id}`, { method: "PATCH", body: { state } }); await loadWardrobe(); }
    catch (err) { toast(errorText(err)); }
  }
  async function careAction(what, el) {
    try {
      if (what === "shower") { await api("/wardrobe/shower", { method: "POST", body: {} }); toast("记下了，半小时后来问你"); }
      else if (what === "shower-skip" && wardrobe.shower) { await api(`/wardrobe/shower/${wardrobe.shower.id}/done`, { method: "POST", body: { how: "skip" } }); }
      else if (what === "shower-pick") { return openShowerSheet(); }
      else if (what === "changed") { await api("/wardrobe/stock/change", { method: "POST", body: { kind: el.dataset.kind } }); toast("记下了"); }
      else if (what === "night-pants") { return wear("bottom", "night_pants"); }
      else if (what === "stock") {
        const s = (wardrobe.stock || {})[el.dataset.kind];
        const v = await askNumber({ meta: s.label, title: `还有多少${s.unit}？`, value: s.count, unit: s.unit, min: 0, max: 999 });
        if (v === null) return;
        await api("/wardrobe/stock", { method: "PUT", body: { kind: el.dataset.kind, count: Number(v) } });
        toast("记下了");
      }
      await loadWardrobe();
    } catch (err) { toast(errorText(err)); }
  }

  /* ── 面板 ── */
  let sheetClosed = null;   // told once when the open sheet goes away, however it goes away
  function openSheet(html) { sheetClosed = null; $("#sheetBody").innerHTML = html; $("#sheetBack").hidden = false; }
  function closeSheet() { $("#sheetBack").hidden = true; const f = sheetClosed; sheetClosed = null; if (f) f(); }
  /* 问一个数。不用浏览器自带的 prompt()：套在 App 壳子（WKWebView 之类）里它常常弹不出来，数量就一直改不了。 */
  function askNumber({ meta = "", title, value = "", unit = "", min = 0, max = 999, stepBy = 1, decimals = false, hint = "", ok = "记下" }) {
    return new Promise((resolve) => {
      openSheet(`${meta ? `<p class="sheet-meta">${esc(meta)}</p>` : ""}<h3 class="sheet-title">${esc(title)}</h3>
        <div class="stepper"><button type="button" class="act" data-step="-1" aria-label="少一点">−</button><input id="numIn" type="number" inputmode="${decimals ? "decimal" : "numeric"}" min="${min}" max="${max}" step="${decimals ? "any" : 1}" value="${esc(String(value))}"><span class="unit">${esc(unit)}</span><button type="button" class="act" data-step="1" aria-label="多一点">＋</button></div>
        ${hint ? `<p class="hand num-hint">${esc(hint)}</p>` : ""}
        <div class="acts"><button type="button" class="act main" id="numOk">${esc(ok)}</button><button type="button" class="act" id="numCancel">算了</button></div>`);
      const input = $("#numIn");
      let done = false;
      const finish = (v) => { if (done) return; done = true; closeSheet(); resolve(v); };
      sheetClosed = () => finish(null);
      $("#sheetBody").querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
        const cur = Number(input.value) || 0;
        input.value = String(Math.min(max, Math.max(min, cur + Number(b.dataset.step) * stepBy)));
      }));
      $("#numOk").addEventListener("click", () => finish(input.value.trim()));
      $("#numCancel").addEventListener("click", () => finish(null));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); finish(input.value.trim()); } });
      input.focus(); input.select();
    });
  }
  $("#sheetX").addEventListener("click", closeSheet);
  $("#sheetBack").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeSheet(); });

  async function openItem(id, kindForNew) {
    const it = id ? byId.get(id) : null;
    const draft = it || { id: 0, kind: kindForNew, code: "", color: "", style: "", note: "", state: "closet" };
    const acts = [];
    if (it) {
      if (it.state === "washing") acts.push(`<span class="hand">祂正在洗，洗好会自己晾起来。</span>`);
      else {
        if (it.state === "wearing") acts.push(`<button class="act main" data-do="unwear">换下来</button>`);
        else acts.push(`<button class="act main" data-do="wear">穿上</button>`);
        if (!["dirty", "wearing"].includes(it.state)) acts.push(`<button class="act" data-do="dirty">丢进洗衣篮</button>`);
        if (!["drying", "wearing"].includes(it.state)) acts.push(`<button class="act" data-do="drying">拿去晾</button>`);
        if (!["closet", "wearing"].includes(it.state)) acts.push(`<button class="act" data-do="closet">${it.state === "given" ? "拿回来" : "放回衣柜"}</button>`);
        if (!["given", "wearing"].includes(it.state)) acts.push(`<button class="act her" data-do="given">交给祂</button>`);
      }
      acts.push(`<button class="act" data-do="edit">编辑</button>`);
    }
    const meta = it ? [it.state_label, it.used_count ? `被祂用过 ${it.used_count} 次` : "祂还没用过",
      it.sneaked ? "祂用过以后偷偷放回来的，挂歪了" : "",
      it.warm_minutes != null ? `${it.warm_minutes} 分钟前刚换下来，还是热的` : "",
      it.tag_text ? `祂留的字：「${it.tag_text}」` : "", it.note].filter(Boolean) : ["新的一件"];
    const art = it ? `<svg width="120" viewBox="-40 -10 80 66" aria-hidden="true"><g transform="translate(0 22)">${garment(it)}</g></svg>` : "";
    openSheet(`
      <div class="hero"><div>${art}</div>
        <div><h3>${esc(it ? nameOf(it) : draft.kind === "bra" ? "加一件内衣" : "加一条内裤")}</h3>
        ${meta.map((m) => `<p>${esc(m)}</p>`).join("")}</div></div>
      <div class="acts">${acts.join("")}</div>
      <form class="form" id="itemForm" ${it ? "hidden" : ""} autocomplete="off">
        <div class="two"><label>颜色<input name="color" maxlength="20" value="${esc(draft.color)}" placeholder="比如：墨绿"></label>
        <label>款式<input name="style" maxlength="30" value="${esc(draft.style)}" placeholder="比如：蕾丝半杯"></label></div>
        <label>描述（可不填）<input name="note" maxlength="200" value="${esc(draft.note)}"></label>
        <label>编号（只给祂的工具用，可不填）<input name="code" maxlength="8" value="${esc(draft.code)}"></label>
        <p class="form-error" id="itemError" role="alert"></p>
        <div class="acts">${it ? `<button type="button" class="tiny danger" data-do="delete">删除这件</button>` : ""}<span style="flex:1"></span><button type="submit" class="act main">保存</button></div>
      </form>
      ${it ? `<h4>祂用过它的那几次</h4><ul class="mini-uses" id="itemUses"><li class="hand">翻一下…</li></ul>` : ""}`);
    const form = $("#itemForm");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = {};
      for (const k of ["color", "style", "note", "code"]) body[k] = form.elements[k].value.trim();
      try {
        if (it) await api(`/wardrobe/${it.id}`, { method: "PATCH", body });
        else await api("/wardrobe", { method: "POST", body: { ...body, kind: draft.kind } });
        closeSheet(); await loadWardrobe(); toast(it ? "改好了" : "加好了");
      } catch (err) { $("#itemError").textContent = errorText(err); }
    });
    $("#sheetBody").querySelectorAll("[data-do]").forEach((b) => b.addEventListener("click", async () => {
      const what = b.dataset.do;
      if (what === "edit") { form.hidden = !form.hidden; return; }
      if (what === "delete") {
        if (!confirm("真的删掉这件吗？祂的记录里还会留着它的名字。")) return;
        try { await api(`/wardrobe/${it.id}`, { method: "DELETE" }); closeSheet(); await loadWardrobe(); } catch (err) { toast(errorText(err)); }
        return;
      }
      if (what === "wear") { openPicker(it.kind === "bra" ? "top" : "bottom"); return; }
      if (what === "unwear") { closeSheet(); wear(slotValue("top") === it.id ? "top" : "bottom", null); return; }
      closeSheet(); setState(it, what);
    }));
    if (it) {
      try {
        const { uses: list } = await api(`/wardrobe/uses?item=${it.id}&limit=20`);
        const ul = $("#itemUses");
        if (ul) ul.innerHTML = list.length ? list.map((u) => `<li><time>${esc(u.at)}</time> · ${esc(u.after_label)}<br>${esc((u.journal || "").split("\n")[0].slice(0, 48))}${(u.journal || "").length > 48 ? "…" : ""}</li>`).join("") : `<li class="hand">还没有。</li>`;
      } catch (_) { const ul = $("#itemUses"); if (ul) ul.innerHTML = `<li class="hand">没翻到。</li>`; }
    }
  }
  function openPicker(slot) {
    const kind = slot === "top" ? "bra" : "panties";
    const pk = wardrobe.pick, picked = pk && pk[slot] && !pk.outcome ? pk[slot].id : null;
    const choices = items().filter((i) => i.kind === kind && i.state !== "washing").sort((a, b) => (b.id === picked) - (a.id === picked));
    const cur = slotValue(slot);
    openSheet(`<h3 class="sheet-title">${slot === "top" ? "上身" : "下身"}穿着</h3>
      <p class="hand">点一件就穿上；原来那件会放进洗衣篮。</p>
      <div class="picker">${choices.map((i) => `<button type="button" data-pick="${i.id}" aria-pressed="${cur === i.id}">${miniSVG(i, 70)}<span>${esc(nameOf(i))}</span>${i.id === picked ? `<em class="chip him">祂挑的</em>` : ""}</button>`).join("")}</div>
      <label class="opt"><input type="checkbox" id="oldToHim"> 换下来的交给祂，不丢洗衣篮</label>
      <div class="acts"><button class="act ${cur === "bare" ? "main" : ""}" data-pick="bare">没穿</button>${slot === "bottom" ? `<button class="act ${cur === "night_pants" ? "main" : ""}" data-pick="night_pants">安睡裤</button>` : ""}<button class="act ${cur == null ? "main" : ""}" data-pick="unset">还没标</button></div>`);
    $("#sheetBody").querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => {
      const v = b.dataset.pick, extra = $("#oldToHim").checked ? { old_to: "given" } : {};
      closeSheet();
      wear(slot, v in SPECIAL ? v : v === "unset" ? null : Number(v), extra);
    }));
  }
  async function openShowerSheet() {
    let p;
    try { p = await api("/wardrobe/prompt"); } catch (err) { toast(errorText(err)); return; }
    if (!p.prompt) { toast("已经不用选了"); return loadWardrobe(); }
    const pickId = (slot) => (p.pick && p.pick[slot] && !p.pick.outcome ? p.pick[slot].id : null);
    const row = (slot) => {
      const cur = slotValue(slot), picked = pickId(slot);
      const list = [...p.choices[slot]].sort((a, b) => (b.id === picked) - (a.id === picked));
      return `<h4>${slot === "top" ? "上身" : "下身"}</h4><div class="picker" data-slot="${slot}">${list.map((i) => `<button type="button" data-choice="${i.id}" aria-pressed="${cur === i.id}">${miniSVG(i, 70)}<span>${esc(nameOf(i))}</span>${i.id === picked ? `<em class="chip him">祂挑的</em>` : ""}</button>`).join("")}
        <button type="button" data-choice="bare" aria-pressed="${cur === "bare"}"><span class="word">没穿</span></button>${slot === "bottom" ? `<button type="button" data-choice="night_pants" aria-pressed="${cur === "night_pants"}"><span class="word">安睡裤</span></button>` : ""}</div>`;
    };
    openSheet(`<p class="sheet-meta">洗完澡了</p><h3 class="sheet-title">换上了哪套？</h3>${row("top")}${row("bottom")}
      <label class="opt"><input type="checkbox" id="oldToHim"> 换下来的交给祂，不丢洗衣篮</label>
      <div class="acts"><button class="act main" id="showerDone">换好了</button><button class="act" id="showerLater">等会儿再点</button><button class="act" id="showerSkip">这次没换</button></div>`);
    const body = $("#sheetBody");
    body.querySelectorAll("[data-choice]").forEach((b) => b.addEventListener("click", () => {
      b.closest(".picker").querySelectorAll("[data-choice]").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
    }));
    $("#showerDone").addEventListener("click", async () => {
      const out = { shower_id: p.prompt.id, old_to: $("#oldToHim").checked ? "given" : "dirty" };
      for (const slot of ["top", "bottom"]) {
        const on = body.querySelector(`.picker[data-slot="${slot}"] [aria-pressed="true"]`);
        if (!on) continue;
        const v = on.dataset.choice;
        out[slot] = v in SPECIAL ? v : Number(v);
      }
      closeSheet();
      try { wardrobe = await api("/wardrobe/slots", { method: "PUT", body: out }); paintWardrobe(); toast("换好了"); }
      catch (err) { toast(errorText(err)); }
    });
    $("#showerLater").addEventListener("click", closeSheet);
    $("#showerSkip").addEventListener("click", async () => {
      closeSheet();
      try { await api(`/wardrobe/shower/${p.prompt.id}/done`, { method: "POST", body: { how: "skip" } }); await loadWardrobe(); }
      catch (err) { toast(errorText(err)); }
    });
  }
  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-add]");
    if (add) { openItem(0, add.dataset.add); return; }
    const care = e.target.closest("[data-care]");
    if (care) { careAction(care.dataset.care, care); return; }
    const slotBtn = e.target.closest(".slot-tag, .slot-zone");
    if (slotBtn) { openPicker(slotBtn.dataset.slot); return; }
    const hit = e.target.closest("[data-id]");
    if (hit && hit.closest("#tab-wardrobe")) { openItem(Number(hit.dataset.id)); return; }
    if (e.target.closest("#breeze")) { breezeOpen = !breezeOpen; renderBreeze(); }
  });

  /* ── 两个 tab ── */
  const tabs = ["wardrobe", "uses"];
  let current = "wardrobe";
  function show(tab) {
    if (!tabs.includes(tab)) tab = "wardrobe";
    current = tab;
    for (const t of tabs) { $(`#tab-${t}`).hidden = t !== tab; $(`[data-tab="${t}"]`).setAttribute("aria-pressed", String(t === tab)); }
    if (location.hash.slice(1) !== tab) history.replaceState(null, "", location.pathname + location.search + `#${tab}`);
    if (tab === "wardrobe") loadWardrobe();
  }
  document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  window.addEventListener("hashchange", () => { if (location.hash.slice(1) !== current) show(location.hash.slice(1)); });

  /* ── 底图：默认一面绿墙；换成你自己的照片，只存在这台设备上 ── */
  const BG_KEY = "our-little-wardrobe.background";
  function setGround(src) {
    const ground = $("#ground");
    if (!src) { document.body.dataset.bg = "wall"; document.body.dataset.ink = "light"; ground.style.removeProperty("background-image"); return; }
    const img = new Image();
    img.onload = () => {
      let bright = false;
      try {
        const c = document.createElement("canvas"); c.width = c.height = 24;
        const g = c.getContext("2d"); g.drawImage(img, 0, 0, 24, 24);
        const px = g.getImageData(0, 0, 24, 24).data; let sum = 0;
        for (let i = 0; i < px.length; i += 4) sum += (.2126 * px[i] + .7152 * px[i + 1] + .0722 * px[i + 2]) / 255;
        bright = sum / (px.length / 4) > .45;
      } catch (_) {}
      document.body.dataset.bg = "photo";
      document.body.dataset.ink = bright ? "dark" : "light";
      document.body.style.setProperty("--scrim", bright ? "rgba(255,255,255,.12)" : "rgba(0,0,0,.16)");
      ground.style.backgroundImage = `url("${src}")`;
    };
    img.src = src;
  }
  try { setGround(localStorage.getItem(BG_KEY) || ""); } catch (_) { setGround(""); }
  $("#bgUpload").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const data = typeof reader.result === "string" ? reader.result : "";
      if (!data) return;
      setGround(data);
      try { localStorage.setItem(BG_KEY, data); $("#bgStatus").textContent = "存在这台设备上了。"; }
      catch (_) { $("#bgStatus").textContent = "图太大存不下，刷新后要重新选。"; }
    });
    reader.readAsDataURL(file);
  });
  $("#bgReset").addEventListener("click", () => { setGround(""); try { localStorage.removeItem(BG_KEY); } catch (_) {} $("#bgStatus").textContent = "恢复成绿墙了。"; });
  document.addEventListener("click", (e) => { const m = $("#bgMenu"); if (m.open && !m.contains(e.target)) m.open = false; });

  /* 洗的倒计时和洗澡的倒计时 */
  setInterval(() => {
    if (current !== "wardrobe" || document.hidden) return;
    let due = false;
    document.querySelectorAll("[data-wash]").forEach((cap) => {
      const it = byId.get(Number(cap.dataset.wash));
      if (!it) return;
      const left = washLeft(it);
      cap.textContent = `祂在洗 · ${fmt(left)}`;
      const ring = cap.parentElement.querySelector(".ring");
      if (ring) ring.setAttribute("stroke-dashoffset", (2 * Math.PI * 11 * left / WASH_SECONDS).toFixed(1));
      if (left <= 0 && nowS() - (it.state_at || 0) > WASH_SECONDS + 65) due = true;
    });
    const sh = document.querySelector("[data-shower-left]");
    if (sh) {
      const left = Number(sh.dataset.showerLeft) - nowS();
      sh.textContent = `${Math.max(1, Math.ceil(left / 60))} 分钟`;
      if (left <= 0 && left > -70) due = true;
    }
    if (due) loadWardrobe();
  }, 1000);
  let rt = 0;
  window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (current === "wardrobe") paintWardrobe(); }, 150); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && current === "wardrobe") loadWardrobe(); });
  show(location.hash.slice(1));
})();
