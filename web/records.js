(() => {
  "use strict";
  /* 祂的记录：一条一页，十二种排法轮着来；她在每一页下面吐槽，祂醒来会看到、会回。
     数据来自 /api/v1（同一台机器上的 wardrobe 服务）。留白处原来是她的照片，这里换成几块画出来的水彩纸。 */
  const API = "/api/v1";
  const $ = (s, root = document) => root.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const ERRORS = { network: "网络没接上，再试一次。", forbidden: "这一页只给她看。", invalid_comment: "吐槽写点什么呀（500 字以内）。", use_not_found: "这条记录已经不在了。" };
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

  /* ── the ground: a plain green wall (her own photo goes here at home) ── */
  $("#shade").remove();

  /* ── watercolour paper swatches instead of her photos: a few soft washes on cream, seeded per record ── */
  const WASHES = [["#a9b8a0", "#5f7a5a"], ["#cfe0c2", "#7f9f6e"], ["#b7d1b0", "#5e8a63"], ["#dfe9d2", "#8ea06f"], ["#c3d8c6", "#6f9478"], ["#d4e3c7", "#9ab77f"]];
  const swatches = new Map();
  function swatch(seed, wide = false) {
    const key = `${seed}|${wide}`;
    if (swatches.has(key)) return swatches.get(key);
    const r = rng(seed * 2654435761), W = wide ? 400 : 240, H = wide ? 160 : 240;
    const [soft, deep] = WASHES[seed % WASHES.length];
    let s = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" fill="#eef2e6"/>`;
    for (let i = 0; i < 4; i++) {
      const cx = r() * W, cy = r() * H, rx = W * (.16 + r() * .22), ry = H * (.16 + r() * .22), rot = r() * 180;
      s += `<ellipse cx="${cx.toFixed(0)}" cy="${cy.toFixed(0)}" rx="${rx.toFixed(0)}" ry="${ry.toFixed(0)}" transform="rotate(${rot.toFixed(0)} ${cx.toFixed(0)} ${cy.toFixed(0)})" fill="${i % 2 ? deep : soft}" fill-opacity="${(.22 + r() * .22).toFixed(2)}"/>`;
    }
    for (let i = 0; i < 5; i++) {
      const x = r() * W, y = r() * H, L = 30 + r() * 70, a = r() * 360;
      s += `<path transform="translate(${x.toFixed(0)} ${y.toFixed(0)}) rotate(${a.toFixed(0)})" d="M0 0 Q${L / 2} ${-L * .3} ${L} 0 Q${L / 2} ${L * .3} 0 0Z" fill="${deep}" fill-opacity=".5"/>`;
    }
    const url = `url('data:image/svg+xml,${encodeURIComponent(s + "</svg>")}')`;   // single quotes: it lands inside style="…"
    swatches.set(key, url);
    return url;
  }

  /* ── the 吐槽 thread ── */
  const isHim = (c) => (c.author || "her") === "him";
  function threadHTML(comments) {
    let html = comments.map((c) => isHim(c)
      ? `<li class="t him"><span class="who">祂</span><p>${esc(c.text)}</p><time>${esc(c.at)}</time><button type="button" class="leaf-x" data-del-comment="${c.id}" data-del-him="1" aria-label="删掉祂这句回复">×</button></li>`
      : `<li class="t her"><p>${esc(c.text)}</p><time>${esc(c.at)}</time><button type="button" class="leaf-x" data-del-comment="${c.id}" aria-label="删掉这句吐槽">×</button></li>`).join("");
    const last = comments[comments.length - 1];
    if (last && !isHim(last)) html += `<li class="t wait">祂下次醒来会看到</li>`;
    return `<section class="talk"><p class="talk-head"><span>吐槽</span><i>ツッコミ</i></p><ol class="thread-list">${html || `<li class="t empty">还没有吐槽</li>`}</ol></section>`;
  }
  const sproutHTML = (post) => `<form class="sprout" data-post="${post}"><input maxlength="500" placeholder="吐槽一句…" aria-label="吐槽"><button type="submit" class="tiny her">吐槽</button></form>`;
  function wireLeaves(root, reload) {
    root.querySelectorAll(".sprout").forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = f.querySelector("input"), text = input.value.trim();
      if (!text) return;
      f.querySelector("button").disabled = true;
      try { await api(f.dataset.post, { method: "POST", body: { text } }); toast("祂下次醒来会看到"); await reload(); }
      catch (err) { toast(errorText(err)); f.querySelector("button").disabled = false; }
    }));
    root.querySelectorAll("[data-del-comment]").forEach((b) => b.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm(b.dataset.delHim ? "删掉祂这句回复？" : "删掉这句吐槽？")) return;
      try { await api(`/comments/${b.dataset.delComment}`, { method: "DELETE" }); await reload(); } catch (err) { toast(errorText(err)); }
    }));
  }

  /* ── the pad: one record per leaf, flipping up ── */
  const NP_HOLES = `<span class="holes" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></span>`;
  const NP_WD = "日一二三四五六";
  const npWd = (day) => { const [y, m, d] = String(day || "").split("-").map(Number); return y ? new Date(y, m - 1, d).getDay() : -1; };
  function makePad(root) {
    const stack = $(".np-stack", root), prev = $("[data-np-prev]", root), next = $("[data-np-next]", root), dots = $(".dots", root);
    const pad = { at: 0, n: 0 };
    pad.layout = () => {
      const leaves = [...stack.children];
      leaves.forEach((l, i) => { l.classList.toggle("gone", i < pad.at); l.classList.toggle("rest", i === pad.at); l.classList.toggle("under", i === pad.at + 1); l.classList.toggle("deep", i > pad.at + 1); l.style.zIndex = i < pad.at ? 1 + i : pad.n - i + 10; });
      prev.disabled = pad.at === 0; next.disabled = pad.at >= pad.n - 1;
      dots.innerHTML = pad.n > 1 ? Array.from({ length: pad.n }, (_, i) => `<i class="${i === pad.at ? "on" : ""}"></i>`).join("") : "";
    };
    pad.render = (pages, keepAt) => {
      pad.n = pages.length; pad.at = Math.max(0, Math.min(keepAt ?? pad.at, pages.length - 1));
      stack.innerHTML = pages.map((p, i) => `<div class="np-leaf" data-i="${i}">${p}</div>`).join("");
      pad.layout();
    };
    pad.flip = (d) => { const n = pad.at + d; if (n < 0 || n >= pad.n) return; pad.at = n; pad.layout(); };
    prev.addEventListener("click", () => pad.flip(-1)); next.addEventListener("click", () => pad.flip(1));
    let y0 = null, x0 = null;
    root.addEventListener("touchstart", (e) => { if (e.target.closest("input, textarea, button")) return; y0 = e.touches[0].clientY; x0 = e.touches[0].clientX; }, { passive: true });
    root.addEventListener("touchend", (e) => { if (y0 == null) return; const dy = e.changedTouches[0].clientY - y0, dx = e.changedTouches[0].clientX - x0; y0 = null; if (Math.abs(dx) > Math.abs(dy)) return; if (dy < -70) pad.flip(1); else if (dy > 70) pad.flip(-1); });
    return pad;
  }
  const pad = makePad($("#tab-uses .np-book"));

  /* ── twelve layouts ── */
  const npName = (u) => esc(u.items.map((x) => x.name).join("、"));
  const npFirst = (u) => esc((u.journal || "").split("\n")[0]);
  const npJ = (u) => `<p class="journal ruled">${esc(u.journal)}</p>`;
  const npM = (u) => `<p class="meta">${esc(u.at)} · 祂的记录</p>`;
  const npTalk = (u) => threadHTML(u.comments) + sproutHTML(`/wardrobe/uses/${u.id}/comments`);
  const npFoot = (u, n) => `<div class="np-foot"><span>第 ${n} 条 · ${u.items.length} 件</span><button type="button" data-use-del="${u.id}">删掉这条</button></div>`;
  const npDay = (u) => (u.day || "");
  const NP_LAYOUTS = [
    (u, n, t, b) => `<article class="np-pg rec L1">${NP_HOLES}<div class="top"><span class="np-piece" style="background-image:${b}"></span><span class="cap">paper · not a photo</span></div>${npM(u)}<h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="jn">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec L2">${NP_HOLES}<div class="bg" style="background-image:${t}"></div><span class="num np-hand">${esc(u.at)}</span><div class="inner">${npM(u)}<h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="jn">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</div></article>`,
    (u, n, t, b) => `<article class="np-pg rec L3">${NP_HOLES}<figure class="np-piece win thumb" style="background-image:${t}"></figure><p class="spaced">s l o w · d o w n</p><p class="meta">${esc(u.at)}</p><h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="gridp"></div><span class="dot d1"></span><span class="dot d2"></span><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec dark L4">${NP_HOLES}<p class="sub">MARKS OF HER DAY</p><h2>${npName(u)}</h2><svg class="leaf-svg" viewBox="0 0 100 120" fill="none" stroke="currentColor" stroke-width="1" aria-hidden="true"><path d="M50 4 C 20 30, 14 70, 50 116 C 86 70, 80 30, 50 4 Z"/><path d="M50 10 V 110"/><path d="M50 30 L 28 46 M50 30 L 72 46 M50 48 L 24 66 M50 48 L 76 66 M50 66 L 28 84 M50 66 L 72 84"/></svg><table><tr><td>DATE</td><td class="v">${esc(u.at)}</td></tr><tr><td>PIECE</td><td class="v">${npName(u)}</td></tr><tr><td>AFTER</td><td class="v">${esc(u.after_label)}</td></tr></table>${npJ(u)}${npTalk(u)}${npFoot(u, n)}<div class="bottom" style="background-image:${b}"></div></article>`,
    (u, n, t, b) => `<article class="np-pg rec L5">${NP_HOLES}<div class="bg" style="background-image:${b}"></div><div class="rel">${npM(u)}<div class="week">${[...NP_WD].map((c, i) => i === npWd(npDay(u)) ? `<b>${c}</b>` : `<span>${c}</span>`).join("")}</div><figure class="np-piece circle" style="background-image:${t}"></figure><span class="dotbig"></span><h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</div></article>`,
    (u, n, t, b) => `<article class="np-pg rec L6">${NP_HOLES}<div class="block"><figure class="np-piece" style="background-image:${t}"></figure></div>${npM(u)}<h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="np-bar"></div><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}<div class="gridp"></div></article>`,
    (u, n, t, b) => `<article class="np-pg rec L7">${NP_HOLES}<svg class="lines" viewBox="0 0 100 100" preserveAspectRatio="none" fill="none" stroke="#2b3a2e" stroke-width=".4" aria-hidden="true"><path d="M18 12 L 30 20"/><path d="M27 17 L 30 20 L 26.5 20.5"/><path d="M58 20 C 50 34, 40 38, 32 30" stroke-dasharray="1 1.5"/></svg><span class="np-ring r1">苔</span><span class="np-ring r2">时</span><figure class="np-piece oval" style="background-image:${t}"></figure><p class="meta">${esc(u.at)}</p><h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><p class="quote">「${npFirst(u)}」</p><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec L8">${NP_HOLES}<figure class="np-piece strip" style="background-image:${b}"></figure><p class="vert">${npName(u)}</p><div class="body">${npM(u)}<p class="where">${esc(u.after_label)}</p><div class="jn">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</div></article>`,
    (u, n, t, b) => `<article class="np-pg rec L9">${NP_HOLES}${npM(u)}<figure class="np-piece t1" style="background-image:${b}"></figure><p class="big">${npName(u)}</p><p class="where">${esc(u.after_label)}</p><div class="sw"><i></i><i></i><i></i><i></i><i></i></div><figure class="np-piece t2" style="background-image:${t}"></figure><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec L10">${NP_HOLES}${npM(u)}<figure class="np-piece sq" style="background-image:${t}"></figure><span class="np-bar"></span><p class="vtext">${esc(u.after_label)} · ${esc(u.at)}</p><p class="script">晴 · 有风</p><h2>${npName(u)}</h2><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec L11">${NP_HOLES}${npM(u)}<span class="label l1">叶尖 ↘</span><div class="shape" style="background-image:${t}"></div><span class="label l2">↖ ${esc(u.after_label)}</span><p class="all"><small>ALL ABOUT</small><b>${npName(u)}</b></p>${npJ(u)}${npTalk(u)}${npFoot(u, n)}</article>`,
    (u, n, t, b) => `<article class="np-pg rec L12">${NP_HOLES}${npM(u)}<div class="panes">${`<i style="background-image:${t}"></i>`.repeat(6)}</div><h2>${npName(u)}</h2><p class="where">${esc(u.after_label)}</p><div class="body">${npJ(u)}</div>${npTalk(u)}${npFoot(u, n)}</article>`,
  ];

  async function loadUses(keepAt) {
    let list;
    try { list = (await api("/wardrobe/uses?limit=100")).uses; } catch (err) { toast(errorText(err)); return; }
    $("#uses-count").innerHTML = list.length ? `共 <em>${list.length}</em> 条，一条一页，页页不同` : "";
    const pages = list.length ? list.map((u, i) => NP_LAYOUTS[i % NP_LAYOUTS.length](u, list.length - i, swatch(u.id), swatch(u.id + 7, true)))
      : [`<article class="np-pg np-empty">${NP_HOLES}<span>还没有记录。</span></article>`];
    pad.render(pages, keepAt);
    const stack = $("#tab-uses .np-stack");
    wireLeaves(stack, () => loadUses(pad.at));
    stack.querySelectorAll("[data-use-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("删掉这条记录？聊天里那一句也会一起消失。")) return;
      try { await api(`/wardrobe/uses/${b.dataset.useDel}`, { method: "DELETE" }); await loadUses(pad.at); } catch (err) { toast(errorText(err)); }
    }));
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadUses(pad.at); });
  loadUses(0);
})();
