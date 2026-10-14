/* Attention Span: a static site over open JSON. No framework, no build step. */
(() => {
  "use strict";

  const D = { meta: null, timeline: [], concepts: [], people: [], index: { editions: [] }, editions: {}, stories: [],
    heads: { people: [], posts: [], groups: [], window_days: 7 } };
  const by = { concept: {}, person: {}, lab: {}, layer: {}, era: {}, type: {}, entry: {}, topic: {}, head: {}, group: {}, story: {} };
  const view = document.getElementById("view");
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // ------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const fmtDate = (d) => {
    if (!d) return "";
    const [y, m, day] = d.split("-");
    if (day) return `${+day} ${MONTHS[+m - 1]} ${y}`;
    if (m) return `${MONTHS[+m - 1]} ${y}`;
    return y;
  };
  const longDate = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-GB",
    { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  // Opened straight from disk (file://), browsers block fetch, so read the offline copy instead.
  const OFFLINE = location.protocol === "file:";
  const offlineReady = !OFFLINE ? Promise.resolve() : new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "data/offline.js";
    s.onload = resolve;
    s.onerror = () => reject(new Error("data/offline.js is missing; run python tools/bundle_data.py"));
    document.head.appendChild(s);
  });
  const getJSON = async (path) => {
    if (OFFLINE) {
      await offlineReady;
      if (window.AS_DATA && window.AS_DATA[path]) return window.AS_DATA[path];
      throw new Error(`${path} is not in the offline copy`);
    }
    const r = await fetch(path, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  };
  const plural = (n, word) => `${n} ${n === 1 ? word : /[^aeiou]y$/.test(word) ? word.slice(0, -1) + "ies" : word + "s"}`;

  const CHECK = {
    verified: ["Date checked", "The date was matched against arXiv, Crossref or the source page."],
    "link-ok": ["Link checked", "The source link works; the date is not printed on the page, so it was not machine-matched."],
    warning: ["Partly checked", "The year matches the source; the month or day could not be matched exactly."],
    unverifiable: ["Not machine-checked", "The source is on X, which cannot be read without the paid API."],
    failed: ["Check failed", "The last automated check did not pass."],
    unchecked: ["Not yet checked", "Run tools/verify_seed.py to check this entry."],
  };
  const checkBadge = (c) => {
    const [label, title] = CHECK[(c && c.status) || "unchecked"] || CHECK.unchecked;
    return `<span class="check ${esc(c && c.status)}" title="${esc(title)}">${icon("check")}${label}</span>`;
  };

  const labName = (id) => (by.lab[id] ? by.lab[id].name : id);
  const layerName = (id) => (by.layer[id] ? by.layer[id].name : id);
  const topicName = (id) => (by.topic[id] ? by.topic[id].name : id);
  const typeName = (id) => (by.type[id] ? by.type[id].name : id);
  const chipsLabs = (ids) => (ids || []).map((id) => `<a class="chip" href="#/labs/${esc(id)}">${esc(labName(id))}</a>`).join("");
  const chipsPeople = (ids) => (ids || []).filter((id) => by.person[id])
    .map((id) => `<a class="chip" href="#/people/${esc(id)}">${esc(by.person[id].name)}</a>`).join("");
  const chipsConcepts = (ids) => (ids || []).filter((id) => by.concept[id])
    .map((id) => `<a class="chip concept" href="#/concepts/${esc(id)}">${esc(by.concept[id].term)}</a>`).join("");

  // ------------------------------------------------------------ data
  async function load() {
    const [meta, timeline, concepts, people] = await Promise.all([
      getJSON("data/meta.json"), getJSON("data/timeline.json"), getJSON("data/concepts.json"), getJSON("data/people.json"),
    ]);
    Object.assign(D, { meta, timeline, concepts, people });
    try { D.index = await getJSON("data/editions/index.json"); } catch (e) { D.index = { editions: [] }; }
    const files = [...new Set(D.index.editions.map((e) => e.file))];
    const months = await Promise.all(files.map((f) => getJSON(`data/editions/${f}`).catch(() => null)));
    for (const m of months) {
      if (!m) continue;
      for (const [date, ed] of Object.entries(m.editions)) D.editions[date] = ed;
    }
    D.stories = Object.values(D.editions).flatMap((ed) => ed.stories);
    try { D.heads = await getJSON("data/heads.json"); } catch (e) { /* no Attention Heads data yet */ }
    D.heads.people = D.heads.people || []; D.heads.posts = D.heads.posts || []; D.heads.groups = D.heads.groups || [];
    D.heads.people.forEach((h) => (by.head[h.id] = h));
    D.heads.groups.forEach((g) => (by.group[g.id] = g));
    D.stories.forEach((s) => (by.story[s.id] = s));
    meta.labs.forEach((l) => (by.lab[l.id] = l));
    meta.layers.forEach((l, i) => (by.layer[l.id] = { ...l, level: i + 1 }));
    meta.eras.forEach((e) => (by.era[e.id] = e));
    meta.types.forEach((t) => (by.type[t.id] = t));
    meta.topics.forEach((t) => (by.topic[t.id] = t));
    concepts.forEach((c) => (by.concept[c.id] = c));
    people.forEach((p) => (by.person[p.id] = p));
    timeline.forEach((e) => (by.entry[e.id] = e));
  }

  // ------------------------------------------------------------ story rendering
  function storyDetail(s) {
    const sources = (s.sources || []).map((src) => {
      const kind = src.kind === "original" ? "original" : src.kind === "discussion" ? "discussion" : "coverage";
      return `<li><a href="${esc(src.url)}" rel="noopener" target="_blank">${esc(src.name)}</a>
        <span class="kind">${kind}</span></li>`;
    }).join("");
    const tags = chipsLabs(s.labs) + chipsPeople(s.people) + chipsConcepts(s.concepts);
    return `<div class="detail">
      <p>${esc(s.summary)}</p>
      ${s.eli5 ? `<div class="eli5"><h4>${icon("eli5")} Like I'm 5</h4><p>${esc(s.eli5)}</p></div>` : ""}
      ${s.why_it_matters ? `<div class="why"><h4>Why it matters</h4><p>${esc(s.why_it_matters)}</p></div>` : ""}
      ${s.spotlight_reason ? `<div class="why"><h4>${icon("spot")} Why it is in the spotlight</h4><p>${esc(s.spotlight_reason)}</p></div>` : ""}
      <div class="sources"><h4>Sources, original first</h4><ol>${sources}</ol></div>
      ${tags ? `<div class="tags">${tags}</div>` : ""}
    </div>`;
  }

  function kicker(s) {
    return `<div class="kicker"><span class="rank">${String(s.rank).padStart(2, "0")}</span>
      <span>${esc(topicName(s.topic))}</span>
      <span>${plural(s.buzz || 1, "source")}</span>
      ${s.spotlight ? `<span class="spot">Spotlight</span>` : ""}</div>`;
  }

  function storyCard(s) {
    return `<article class="story" id="s-${esc(s.id)}">
      ${kicker(s)}
      <h3>${esc(s.title)}</h3>
      <p class="one-liner">${esc(s.one_liner)}</p>
      <button class="more" type="button" aria-expanded="false" data-story="${esc(s.id)}">${icon("plus")}<span>Read the story</span></button>
      <div class="slot"></div>
    </article>`;
  }

  function bindStoryToggles(root, stories) {
    const map = Object.fromEntries(stories.map((s) => [s.id, s]));
    root.querySelectorAll("button.more[data-story]").forEach((btn) => {
      btn.addEventListener("click", () => toggleStory(btn, map[btn.dataset.story]));
    });
  }

  function toggleStory(btn, s, force) {
    const card = btn.closest(".story");
    const open = force ?? btn.getAttribute("aria-expanded") !== "true";
    btn.setAttribute("aria-expanded", String(open));
    btn.innerHTML = `${icon(open ? "minus" : "plus")}<span>${open ? "Close" : "Read the story"}</span>`;
    card.classList.toggle("open", open);
    card.querySelector(".slot").innerHTML = open ? storyDetail(s) : "";
  }

  // ------------------------------------------------------------ the 24-hour span
  function spanStrip(ed) {
    const end = new Date(ed.generated_at).getTime();
    const start = end - 24 * 3600 * 1000;
    const offsetMin = 330; // labels in India time, where the edition is made
    let hours = "";
    const first = Math.ceil(start / 3600000) * 3600000;
    for (let t = first; t <= end; t += 3600000) {
      const local = new Date(t + offsetMin * 60000);
      const h = local.getUTCHours();
      const pct = ((t - start) / (end - start)) * 100;
      const label = h % 3 === 0;
      hours += `<div class="span-hour ${h % 6 === 0 ? "label" : ""}" style="left:${pct.toFixed(2)}%">${label ? `<span>${String(h).padStart(2, "0")}:00</span>` : ""}</div>`;
    }
    let ticks = "", earlier = 0;
    for (const s of ed.stories) {
      const t = new Date(s.published).getTime();
      if (!(t >= start && t <= end)) { earlier++; continue; }
      const pct = ((t - start) / (end - start)) * 100;
      const when = new Date(t + offsetMin * 60000).toISOString().slice(11, 16);
      ticks += `<button class="span-tick ${s.rank === 1 ? "lead" : ""}" style="left:${pct.toFixed(2)}%" data-goto="${esc(s.id)}"
        aria-label="${esc(s.title)}, first seen ${when} IST"><span class="tip"><span class="mono">${when}</span> ${esc(s.title)}</span></button>`;
    }
    return `<section class="span" aria-label="When today's stories broke">
      <div class="span-head"><span>When each story first appeared, over the 24 hours before this edition (India time)</span>
      <span>${earlier ? `${earlier} from earlier days` : ""}</span></div>
      <div class="span-track">${hours}${ticks}</div><div class="span-foot"></div></section>`;
  }

  // ------------------------------------------------------------ pages
  function pageToday(date) {
    const dates = D.index.editions.map((e) => e.date);
    if (!dates.length) {
      view.innerHTML = `<div class="page-head"><h2>Today</h2></div>
        <p class="notice">No edition yet. Run <code>python run_daily.py</code> to collect the last 24 hours, then reload.</p>`;
      return;
    }
    const day = date && D.editions[date] ? date : D.index.latest || dates[0];
    const ed = D.editions[day];
    const [lead, ...rest] = ed.stories;
    const st = ed.stats || {};
    const spot = ed.stories.filter((s) => s.spotlight);
    view.innerHTML = `
      <div class="page-head"><h2>${day === dates[0] ? "Today" : "Edition"}: ${esc(longDate(day))}</h2>
        <p>${plural(ed.stories.length, "story")} chosen from ${st.items || "?"} items across ${st.sources_ok || "?"} sources.</p></div>
      ${spanStrip(ed)}
      <div class="today-grid">
        <div>
          <article class="story lead-story open" id="s-${esc(lead.id)}">
            ${kicker(lead)}
            <h3>${esc(lead.title)}</h3>
            <p class="one-liner">${esc(lead.one_liner)}</p>
            ${storyDetail(lead)}
          </article>
          <div class="stories">${rest.map(storyCard).join("")}</div>
        </div>
        <aside class="rail-box" aria-label="This edition">
          <h4>In this edition</h4>
          <ol class="contents">${ed.stories.map((s) => `<li><span class="n">${String(s.rank).padStart(2, "0")}</span>
            <a href="#/today/${day}/${esc(s.id)}">${esc(s.title)}</a></li>`).join("")}</ol>
          ${spot.length ? `<h4>${icon("spot")} Spotlight</h4>${spot.map((s) => `<p class="stat-line"><a href="#/today/${day}/${esc(s.id)}">${esc(s.title)}</a></p>`).join("")}<br>` : ""}
          <h4>How this edition was made</h4>
          <p class="stat-line"><b>${st.items ?? "?"}</b> items collected, grouped into <b>${st.stories ?? "?"}</b> stories.</p>
          <p class="stat-line"><b>${ed.stories.length}</b> published after a separate fact-check.</p>
          <p class="stat-line"><b>${st.dropped ?? 0}</b> dropped because a claim was not in the sources.</p>
          <br><h4>Past editions</h4>
          <ul class="archive">${D.index.editions.slice(0, 7).map((e) => `<li><a href="#/today/${e.date}" ${e.date === day ? 'aria-current="true"' : ""}>
            <time>${esc(fmtDate(e.date))}</time>${esc(e.lead)}</a></li>`).join("")}</ul>
          <p class="stat-line"><a href="#/archive">The full archive</a></p>
          <br><h4>Also here</h4>
          <p class="stat-line"><a href="#/week">The week in review</a></p>
          <p class="stat-line"><a href="#/context-window">Context Window</a>: posts worth reading, picked each evening</p>
        </aside>
      </div>`;
    bindStoryToggles(view, rest);
    view.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => openStory(b.dataset.goto)));
  }

  function openStory(id) {
    const card = document.getElementById(`s-${id}`);
    if (!card) return;
    const btn = card.querySelector("button.more");
    if (btn && btn.getAttribute("aria-expanded") !== "true") btn.click();
    card.scrollIntoView({ block: "start" });
    window.scrollBy(0, -60);
  }

  function pageArchive() {
    const eds = D.index.editions;
    if (!eds.length) {
      view.innerHTML = `<div class="page-head"><h2>Archive</h2></div><p class="notice">No editions yet.</p>`;
      return;
    }
    const months = {};
    eds.forEach((e) => (months[e.date.slice(0, 7)] = months[e.date.slice(0, 7)] || []).push(e));
    const total = eds.reduce((n, e) => n + e.count, 0);
    const monthName = (m) => new Date(m + "-15T12:00:00Z").toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
    view.innerHTML = `
      <div class="page-head"><h2>Archive</h2><p>${plural(eds.length, "edition")} and ${plural(total, "story")} so far. Nothing is ever removed.
        <a href="#/week">Read it week by week</a>.</p></div>
      ${Object.entries(months).map(([m, list]) => `
        <section class="arch-month"><h3>${esc(monthName(m))}</h3>
        ${list.map((e) => {
          const ed = D.editions[e.date];
          const titles = ed ? ed.stories.map((s) => `<li><a href="#/today/${e.date}/${esc(s.id)}">${esc(s.title)}</a>
            <span class="asof">${esc(topicName(s.topic))}</span></li>`).join("") : "";
          return `<article class="arch-day">
            <a class="arch-date" href="#/today/${e.date}"><time datetime="${e.date}">${esc(longDate(e.date))}</time></a>
            <div><a class="arch-lead" href="#/today/${e.date}">${esc(e.lead)}</a>
              <p class="asof">${plural(e.count, "story")}${e.spotlight ? `, ${e.spotlight} in the spotlight` : ""}</p>
              <details><summary>All stories in this edition</summary><ol>${titles}</ol></details></div>
          </article>`;
        }).join("")}</section>`).join("")}`;
  }

  function entryRow(e) {
    return `<article class="entry" id="e-${esc(e.id)}">
      <time datetime="${esc(e.date)}">${esc(fmtDate(e.date))}</time>
      <div>
        <h4><button type="button" aria-expanded="false" data-entry="${esc(e.id)}">${esc(e.title)}</button></h4>
        <p class="one-liner">${esc(e.one_liner)}</p>
        <div class="meta">${esc(typeName(e.type))}, ${esc(e.labs.map(labName).join(", "))}, ${esc(layerName(e.layer))}</div>
        <div class="slot"></div>
      </div></article>`;
  }

  function entryDetail(e) {
    const src = e.sources.map((s) => `<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>
      <span class="kind">${s.kind === "paper" ? "paper" : s.kind === "press" ? "press" : "original"}</span></li>`).join("");
    return `<div class="detail"><p>${esc(e.summary)}</p>
      <div class="sources"><h4>Sources</h4><ol>${src}</ol></div>
      <p style="margin-top:10px">${checkBadge(e.check)}${e.check && e.check.checked_on ? ` <span class="asof">on ${esc(fmtDate(e.check.checked_on))}</span>` : ""}</p>
      <div class="tags">${chipsConcepts(e.concepts)}${chipsPeople(e.people)}${chipsLabs(e.labs)}</div></div>`;
  }

  function bindEntryToggles(root) {
    root.querySelectorAll("button[data-entry]").forEach((b) => b.addEventListener("click", () => {
      const open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", String(open));
      b.closest(".entry").querySelector(".slot").innerHTML = open ? entryDetail(by.entry[b.dataset.entry]) : "";
    }));
  }

  function pageTimeline(params) {
    const types = D.meta.types.filter((t) => t.id !== "concept");
    const usedLabs = D.meta.labs.filter((l) => D.timeline.some((e) => e.labs.includes(l.id)));
    const counts = D.timeline.reduce((a, e) => ((a[e.check.status] = (a[e.check.status] || 0) + 1), a), {});
    view.innerHTML = `
      <div class="page-head"><h2>Timeline</h2>
        <p>${D.timeline.length} moments from 1943 to today. ${counts.verified || 0} have their date machine-checked against the source.</p></div>
      <div class="with-rail">
        <ol class="era-ruler" id="era-ruler">${D.meta.eras.map((er) => `<li><a href="#/timeline/${er.id}" data-era="${er.id}">${esc(er.name)}
          <span>${er.from}${er.to > 3000 ? " to now" : ` to ${er.to}`}</span></a></li>`).join("")}</ol>
        <div>
          <div class="filters">
            <label>Type <select id="f-type"><option value="">All</option>${types.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select></label>
            <label>Lab <select id="f-lab"><option value="">All</option>${usedLabs.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join("")}</select></label>
            <label>Layer <select id="f-layer"><option value="">All</option>${D.meta.layers.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join("")}</select></label>
          </div>
          <div id="eras"></div>
        </div>
      </div>`;
    const draw = () => {
      const ft = $("#f-type").value, fl = $("#f-lab").value, fy = $("#f-layer").value;
      const list = D.timeline.filter((e) => (!ft || e.type === ft) && (!fl || e.labs.includes(fl)) && (!fy || e.layer === fy));
      $("#eras").innerHTML = D.meta.eras.map((er) => {
        const items = list.filter((e) => e.era === er.id);
        return `<section class="era" id="era-${er.id}"><header><h3>${esc(er.name)}</h3><p>${esc(er.blurb)}</p></header>
          ${items.length ? items.map(entryRow).join("") : `<p class="empty">Nothing here for this filter.</p>`}</section>`;
      }).join("");
      bindEntryToggles(view);
      watchEras();
    };
    ["#f-type", "#f-lab", "#f-layer"].forEach((s) => $(s).addEventListener("change", draw));
    draw();
    view.querySelectorAll("[data-era]").forEach((a) => a.addEventListener("click", (ev) => {
      ev.preventDefault();
      document.getElementById(`era-${a.dataset.era}`).scrollIntoView();
    }));
    if (params[0]) setTimeout(() => {
      const t = document.getElementById(`era-${params[0]}`) || document.getElementById(`e-${params[0]}`);
      if (t) t.scrollIntoView();
      const b = t && t.querySelector && t.querySelector("button[data-entry]");
      if (b && t.classList.contains("entry")) b.click();
    }, 0);
  }

  let eraObserver;
  function watchEras() {
    if (eraObserver) eraObserver.disconnect();
    const links = [...document.querySelectorAll("#era-ruler a")];
    eraObserver = new IntersectionObserver((entries) => {
      for (const en of entries) {
        if (!en.isIntersecting) continue;
        const id = en.target.id.replace("era-", "");
        links.forEach((l) => l.classList.toggle("here", l.dataset.era === id));
      }
    }, { rootMargin: "-20% 0px -70% 0px" });
    document.querySelectorAll(".era").forEach((s) => eraObserver.observe(s));
  }

  function pageConcepts() {
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
    const groups = {};
    D.concepts.forEach((c) => (groups[c.letter] = groups[c.letter] || []).push(c));
    view.innerHTML = `
      <div class="page-head"><h2>Concepts</h2><p>${D.concepts.length} terms, each with its layer in the AI stack, a plain definition and its lineage.</p></div>
      <nav class="letters" aria-label="Jump to letter">${letters.map((L) => groups[L] ? `<a href="#/concepts" data-letter="${L}">${L}</a>` : `<span aria-hidden="true">${L}</span>`).join("")}</nav>
      <div class="filters"><label>Layer <select id="f-layer"><option value="">All layers</option>
        ${D.meta.layers.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join("")}</select></label></div>
      <div id="index"></div>`;
    const draw = () => {
      const fl = $("#f-layer").value;
      $("#index").innerHTML = letters.filter((L) => groups[L]).map((L) => {
        const items = groups[L].filter((c) => !fl || c.layer === fl);
        if (!items.length) return "";
        return `<section class="letter-group" id="L-${L}"><h3>${L}</h3><div class="index-cols">${items.map((c) => `
          <div class="term"><a class="name" href="#/concepts/${esc(c.id)}">${esc(c.term)}</a><span class="layer">${esc(layerName(c.layer))}</span>
          <p>${esc(c.definition)}</p></div>`).join("")}</div></section>`;
      }).join("");
    };
    $("#f-layer").addEventListener("change", draw);
    draw();
    view.querySelectorAll("[data-letter]").forEach((a) => a.addEventListener("click", (ev) => {
      ev.preventDefault();
      const t = document.getElementById(`L-${a.dataset.letter}`);
      if (t) t.scrollIntoView();
      view.querySelectorAll("[data-letter]").forEach((x) => x.classList.toggle("here", x === a));
    }));
  }

  function lineageDiagram(c) {
    const from = c.evolved_from.filter((id) => by.concept[id]);
    const to = c.led_to.filter((id) => by.concept[id]);
    const col = (ids, side) => ids.length ? ids.map((id) => `<a class="chip concept" href="#/concepts/${id}">${esc(by.concept[id].term)}</a>`).join("")
      : `<span class="none">${side === "from" ? "A starting point in this glossary" : "Nothing in this glossary builds on it yet"}</span>`;
    const arrow = `<svg width="46" height="16" viewBox="0 0 46 16" aria-hidden="true"><path d="M0 8h42M36 3l6 5-6 5" fill="none" stroke="#77746D" stroke-width="1.5"/></svg>`;
    return `<section class="lineage"><h4>Lineage</h4>
      <div class="lineage-row" style="grid-template-columns:1fr 46px auto 46px 1fr">
        <div class="lineage-col from">${col(from, "from")}</div>${arrow}
        <div class="lineage-self">${esc(c.term)}</div>${arrow}
        <div class="lineage-col">${col(to, "to")}</div></div></section>`;
  }

  function miniEntries(list) {
    return list.length ? `<ul class="mini-list">${list.map((e) => `<li><time>${esc(fmtDate(e.date))}</time>
      <div><a href="#/timeline/${esc(e.id)}">${esc(e.title)}</a><div class="src">${esc(e.one_liner)}</div></div></li>`).join("")}</ul>`
      : `<p class="empty">No history entries yet.</p>`;
  }

  function miniStories(list) {
    return list.length ? `<ul class="mini-list">${list.map((s) => `<li><time>${esc(fmtDate(s.date))}</time>
      <div><a href="#/today/${esc(s.date)}/${esc(s.id)}">${esc(s.title)}</a><div class="src">${esc(s.one_liner)}</div></div></li>`).join("")}</ul>`
      : `<p class="empty">No news mentions yet. They appear here as nightly editions mention it.</p>`;
  }

  function pageConcept(id) {
    const c = by.concept[id];
    if (!c) return notFound();
    const entries = c.entries.map((e) => by.entry[e]).filter(Boolean);
    const news = D.stories.filter((s) => (s.concepts || []).includes(id)).sort((a, b) => b.date.localeCompare(a.date));
    const people = D.people.filter((p) => p.concepts.includes(id));
    view.innerHTML = `<div class="concept-page">
      <p><a href="#/concepts">Concepts</a>, <a href="#/stack">${esc(layerName(c.layer))}</a></p>
      <h2>${esc(c.term)}</h2>
      ${c.aka && c.aka.length ? `<p class="aka">Also called ${c.aka.map(esc).join(", ")}</p>` : ""}
      <p class="def">${esc(c.definition)}</p>
      <div class="eli5"><h4>${icon("eli5")} Like I'm 5</h4><p>${esc(c.eli5)}</p></div>
      ${lineageDiagram(c)}
      <h3 class="section-title">In history</h3>${miniEntries(entries)}
      <h3 class="section-title">In the news</h3>${miniStories(news)}
      ${people.length ? `<h3 class="section-title">People</h3><div class="tags">${chipsPeople(people.map((p) => p.id))}</div>` : ""}
    </div>`;
  }

  function pageLabs() {
    const rows = D.meta.labs.map((l) => {
      const ent = D.timeline.filter((e) => e.labs.includes(l.id));
      const news = D.stories.filter((s) => (s.labs || []).includes(l.id));
      const latest = [...ent.map((e) => e.date), ...news.map((s) => s.date)].sort().pop();
      return { l, ent: ent.length, news: news.length, latest };
    }).filter((r) => r.ent || r.news);
    view.innerHTML = `<div class="page-head"><h2>Labs</h2><p>Who made what, and when. Each lab's page combines its history with the news.</p></div>
      <table class="ledger"><thead><tr><th>Lab</th><th class="hide-sm">Founded</th><th>History</th><th>News</th><th>Latest</th></tr></thead>
      <tbody>${rows.map((r) => `<tr><td><a href="#/labs/${r.l.id}">${esc(r.l.name)}</a><span class="blurb">${esc(r.l.blurb)}</span></td>
        <td class="num hide-sm">${r.l.founded || ""}</td><td class="num">${r.ent}</td><td class="num">${r.news}</td>
        <td class="num">${esc(fmtDate(r.latest))}</td></tr>`).join("")}</tbody></table>`;
  }

  function pageLab(id) {
    const l = by.lab[id];
    if (!l) return notFound();
    const items = [
      ...D.timeline.filter((e) => e.labs.includes(id)).map((e) => ({ date: e.date, title: e.title, text: e.one_liner, href: `#/timeline/${e.id}`, kind: typeName(e.type) })),
      ...D.stories.filter((s) => (s.labs || []).includes(id)).map((s) => ({ date: s.date, title: s.title, text: s.one_liner, href: `#/today/${s.date}/${s.id}`, kind: "News" })),
    ].sort((a, b) => b.date.localeCompare(a.date));
    view.innerHTML = `<div class="concept-page"><p><a href="#/labs">Labs</a></p><h2>${esc(l.name)}</h2>
      <p class="def">${esc(l.blurb)}</p>
      <h3 class="section-title">Dated releases and news</h3>
      <ul class="mini-list">${items.map((i) => `<li><time>${esc(fmtDate(i.date))}</time><div><a href="${i.href}">${esc(i.title)}</a>
        <div class="src">${esc(i.kind)}. ${esc(i.text)}</div></div></li>`).join("")}</ul></div>`;
  }

  const monogram = (name) => name.split(" ").map((w) => w[0]).slice(0, 2).join("");

  function pagePeople() {
    view.innerHTML = `<div class="page-head"><h2>People</h2><p>Ten people whose work and moves shape the field. Roles change, so each role links the source it comes from.</p></div>
      <div class="people-grid">${D.people.map((p) => `<article class="person"><div class="monogram" aria-hidden="true">${esc(monogram(p.name))}</div>
        <div><h3><a href="#/people/${p.id}">${esc(p.name)}</a></h3><p class="role">${esc(p.role)}</p>
        <p class="known">${esc(p.known_for)}</p></div></article>`).join("")}</div>`;
  }

  function pagePerson(id) {
    const p = by.person[id];
    if (!p) return notFound();
    const entries = p.entries.map((e) => by.entry[e]).filter(Boolean).sort((a, b) => b.date.localeCompare(a.date));
    const news = D.stories.filter((s) => (s.people || []).includes(id)).sort((a, b) => b.date.localeCompare(a.date));
    const posted = livePosts().filter((x) => x.person === id);
    view.innerHTML = `<div class="concept-page"><p><a href="#/people">People</a></p><h2>${esc(p.name)}</h2>
      <p class="def">${esc(p.role)}. <span class="asof">Source for this role:
        <a href="${esc(p.role_source.url)}" target="_blank" rel="noopener">${esc(p.role_source.title)}</a></span></p>
      <p>${esc(p.known_for)}</p>
      <div class="tags">${chipsConcepts(p.concepts)}${chipsLabs(p.labs)}</div>
      ${p.links.length ? `<p style="margin-top:14px">${p.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a>`).join(", ")}</p>` : ""}
      <h3 class="section-title">In the news</h3>${miniStories(news)}
      ${by.head[id] ? `<h3 class="section-title">What they posted</h3>${posted.length ? posted.slice(0, 5).map((x) => postCard(x, { noName: true })).join("")
        + (posted.length > 5 ? `<p><a href="#/heads/${esc(id)}">All ${posted.length} posts</a></p>` : "") : `<p class="empty">No AI posts collected yet.</p>`}` : ""}
      <h3 class="section-title">In history</h3>${miniEntries(entries)}</div>`;
    activateEmbeds(view);
  }


  // ------------------------------------------------------------ Attention Heads
  const IST = 330 * 60000;
  const istDay = (iso) => new Date(new Date(iso).getTime() + IST).toISOString().slice(0, 10);
  const istTime = (iso) => new Date(new Date(iso).getTime() + IST).toISOString().slice(11, 16);
  const platformName = (p) => (p === "x" ? "X" : "Bluesky");
  const isAccount = (h) => !!h && (by.group[h.group] || {}).kind === "account";
  const peopleOnly = () => D.heads.people.filter((h) => !isAccount(h));
  const accountsOnly = () => D.heads.people.filter(isAccount);
  const livePosts = () => D.heads.posts.filter((p) => !p.removed);
  const weekPosts = () => {
    const days = D.heads.window_days || 7;
    const since = Date.now() - days * 86400000;
    return livePosts().filter((p) => new Date(p.posted_at).getTime() >= since);
  };
  const isClassic = (p) => /^classic:/i.test(p.note || "");
  const pickedPosts = () => livePosts().filter((p) => p.via === "inbox");
  const headLink = (h) => `<a href="#/heads/${esc(h.id)}">${esc(h.name)}</a>`;
  const REPO = "https://github.com/shashikantdev3/attention-span";

  // X posts are shown only through X's own embedded-post widget, loaded when a post scrolls into view.
  let xScript = null, xObserver = null;
  function loadX() {
    if (!xScript) xScript = new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = "https://platform.twitter.com/widgets.js";
      s.async = true;
      s.charset = "utf-8";
      s.onload = () => resolve(window.twttr || null);
      s.onerror = () => resolve(null);
      document.head.appendChild(s);
    });
    return xScript;
  }
  function xEmbed(p) {
    const night = document.documentElement.getAttribute("data-theme") === "night";
    let h = p.embed_html || "";
    const extra = `${/data-dnt=/.test(h) ? "" : ' data-dnt="true"'}${night ? ' data-theme="dark"' : ""} data-conversation="none"`;
    h = h.replace(/^<blockquote/, `<blockquote${extra}`);
    return `<div class="x-embed" data-x>${h}</div>`;
  }
  function activateEmbeds(root) {
    const boxes = [...root.querySelectorAll("[data-x]:not([data-done])")];
    if (!boxes.length) return;
    if (xObserver) xObserver.disconnect();
    xObserver = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        const el = en.target;
        xObserver.unobserve(el);
        el.dataset.done = "1";
        loadX().then((tw) => { if (tw && tw.widgets) tw.widgets.load(el); });
      });
    }, { rootMargin: "500px 0px" });
    boxes.forEach((b) => xObserver.observe(b));
  }
  const noteLine = (p) => {
    if (!p.note) return "";
    if (isClassic(p)) return `<p class="asof">In the Hall of fame: ${esc(p.note.replace(/^classic:\s*/i, ""))}</p>`;
    if (/^via\b/i.test(p.note)) return "";
    return `<p class="asof">Editor's note: ${esc(p.note)}</p>`;
  };

  // the post text with its links made clickable; everything else is escaped
  function richText(text, links) {
    let out = "", rest = text;
    for (const l of links || []) {
      const i = rest.indexOf(l.text);
      if (i < 0 || !/^https?:\/\//.test(l.url)) continue;
      out += esc(rest.slice(0, i)) + `<a href="${esc(l.url)}" target="_blank" rel="noopener nofollow">${esc(l.text)}</a>`;
      rest = rest.slice(i + l.text.length);
    }
    return out + esc(rest);
  }

  function postCard(p, opts = {}) {
    const h = by.head[p.person] || { id: p.person, name: p.person, group: "" };
    const ctx = p.context;
    const story = p.story && by.story[p.story];
    const when = p.date_only ? fmtDate(istDay(p.posted_at)) : `${fmtDate(istDay(p.posted_at))}, ${istTime(p.posted_at)} IST`;
    return `<article class="dispatch" data-group="${esc(h.group)}">
      <header>
        ${opts.noName ? "" : `<span class="monogram sm" aria-hidden="true">${esc(monogram(h.name))}</span>`}
        <div class="who">${opts.noName ? "" : `<b>${headLink(h)}</b>`}
          <span class="asof">${opts.noName ? "" : `${esc((by.group[h.group] || {}).label || "")}, `}on ${platformName(p.platform)}${p.platform === "x" && p.embed_html ? "" : `, <time datetime="${esc(p.posted_at)}">${esc(when)}</time>`}</span></div>
      </header>
      ${p.platform === "x" && p.embed_html ? xEmbed(p) : `<blockquote cite="${esc(p.url)}"><p>${richText(p.text, p.links)}</p></blockquote>`}
      ${ctx && (ctx.title || ctx.text) ? `<p class="ctx">${icon("link")}<span>${ctx.kind === "quote" ? "" : "Linked: "}${ctx.url
        ? `<a href="${esc(ctx.url)}" target="_blank" rel="noopener">${esc(ctx.title || ctx.url)}</a>` : esc(ctx.title)}${ctx.kind === "quote" && ctx.text ? `: "${esc(ctx.text.slice(0, 220))}"` : ""}</span></p>` : ""}
      ${p.meaning ? `<div class="means"><h4>What it means <span class="our">our reading, not the author's words</span></h4><p>${esc(p.meaning)}</p></div>` : ""}
      ${noteLine(p)}
      <footer>
        <a href="${esc(p.url)}" target="_blank" rel="noopener">Read the full post on ${platformName(p.platform)}</a>
        ${story ? `<span>In the news: <a href="#/today/${esc(story.date)}/${esc(story.id)}">${esc(story.title)}</a></span>` : ""}
        ${(p.concepts || []).length ? `<span class="tags">${chipsConcepts(p.concepts)}</span>` : ""}
      </footer>
    </article>`;
  }

  function activeBoard(posts, limit = 10) {
    const n = {};
    posts.forEach((p) => (n[p.person] = (n[p.person] || 0) + 1));
    const rows = Object.entries(n).sort((a, b) => b[1] - a[1] || (by.head[a[0]] || {}).name?.localeCompare((by.head[b[0]] || {}).name)).slice(0, limit);
    if (!rows.length) return `<p class="empty">No posts this week yet.</p>`;
    const max = rows[0][1];
    return `<ol class="board">${rows.map(([id, c], i) => {
      const h = by.head[id] || { id, name: id };
      return `<li><span class="n">${String(i + 1).padStart(2, "0")}</span><span class="who">${headLink(h)}</span>
        <span class="count">${c}</span><span class="bar" style="width:${Math.max(6, Math.round((c / max) * 100))}%"></span></li>`;
    }).join("")}</ol>`;
  }

  function headsTabs(active) {
    const tabs = [["heads", "Posts"], ["heads/all", "Who is followed"]];
    return `<nav class="subtabs" aria-label="Attention Heads sections">${tabs.map(([h, l]) =>
      `<a href="#/${h}"${active === h ? ' aria-current="page"' : ""}>${l}</a>`).join("")}</nav>`;
  }

  function pageHeads() {
    const H = D.heads;
    const week = weekPosts().filter((p) => p.platform !== "x");   // X posts live in the Context Window
    const onBsky = H.people.filter((h) => h.bsky).length;
    const groups = H.groups.filter((g) => week.some((p) => (by.head[p.person] || {}).group === g.id));
    view.innerHTML = `
      <div class="page-head"><h2>Attention Heads</h2>
        <p>What the people who shape AI posted on Bluesky this week, collected every night, quoted in full, with a plain note on what each post means.</p></div>
      ${headsTabs("heads")}
      <div class="today-grid">
        <div>
          <div class="filters" role="group" aria-label="Show posts from">
            <button type="button" class="chip on" data-g="">Everyone</button>
            ${groups.map((g) => `<button type="button" class="chip" data-g="${esc(g.id)}">${esc(g.label)}</button>`).join("")}
          </div>
          <div id="feed"></div>
        </div>
        <aside class="rail-box" aria-label="This week">
          <h4>Most active this week</h4>
          ${activeBoard(week)}
          <p class="stat-line"><b>${week.length}</b> AI posts in the last ${H.window_days || 7} days from <b>${new Set(week.map((p) => p.person)).size}</b> people.</p>
          <br><h4>How posts get here</h4>
          <p class="stat-line">Every night the public Bluesky posts of the ${onBsky} people with a checked Bluesky account are read
            automatically. Replies and reposts are left out, and so is anything not about AI or data.</p>
          <p class="stat-line">X posts are picked by an editor, never scraped, and shown through X's own embedded post. See the <a href="#/context-window">Context Window</a>.</p>
          <p class="stat-line">Each note is written only from the post and checked by a second AI model. Opinions stay with the person who posted them.</p>
          <br><h4>Who is followed</h4>
          <p class="stat-line"><a href="#/heads/all">${peopleOnly().length} people and ${accountsOnly().length} accounts, by group</a></p>
        </aside>
      </div>`;
    const draw = (g) => {
      const list = week.filter((p) => !g || (by.head[p.person] || {}).group === g);
      if (!list.length) { $("#feed").innerHTML = `<p class="empty">No posts from this group in the last ${H.window_days || 7} days.</p>`; return; }
      const days = {};
      list.forEach((p) => (days[istDay(p.posted_at)] = days[istDay(p.posted_at)] || []).push(p));
      $("#feed").innerHTML = Object.entries(days).sort((a, b) => b[0].localeCompare(a[0])).map(([d, ps]) =>
        `<section class="heads-day"><h3>${esc(longDate(d))}</h3>${ps.map((p) => postCard(p)).join("")}</section>`).join("");
      activateEmbeds(view);
    };
    view.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => {
      view.querySelectorAll("[data-g]").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
      draw(b.dataset.g);
    }));
    draw("");
  }

  function pageContextWindow(tab) {
    const picks = pickedPosts();
    const since = Date.now() - (D.heads.window_days || 7) * 86400000;
    const week = picks.filter((p) => new Date(p.posted_at).getTime() >= since);
    const hall = picks.filter(isClassic);
    const showHall = tab === "hall-of-fame";
    const list = (showHall ? hall : week).slice().sort((a, b) => b.posted_at.localeCompare(a.posted_at));
    const groups = D.heads.groups.filter((g) => list.some((p) => (by.head[p.person] || {}).group === g.id));
    view.innerHTML = `
      <div class="page-head"><h2>Context Window</h2>
        <p>What they said, as they posted it, and what it means. Picked by an editor every evening.</p></div>
      <div class="today-grid">
        <div>
          <nav class="subtabs minor" aria-label="Context Window views">
            <a href="#/context-window"${showHall ? "" : ' aria-current="page"'}>This week <span class="n">${week.length}</span></a>
            <a href="#/context-window/hall-of-fame"${showHall ? ' aria-current="page"' : ""}>Hall of fame <span class="n">${hall.length}</span></a>
          </nav>
          ${groups.length > 1 ? `<div class="filters" role="group" aria-label="Show posts from">
            <button type="button" class="chip on" data-g="">Everyone</button>
            ${groups.map((g) => `<button type="button" class="chip" data-g="${esc(g.id)}">${esc(g.label)}</button>`).join("")}
          </div>` : ""}
          <div id="feed"></div>
        </div>
        <aside class="rail-box" aria-label="About the Context Window">
          <h4>How this works</h4>
          <p class="stat-line">An editor reads the accounts we follow and picks the few posts worth your time. Nothing is collected automatically from X.</p>
          <p class="stat-line">Each post is shown through X's own embedded post, exactly as it was posted, so it always links back to X.</p>
          <p class="stat-line">The note under each post is our reading of it, written only from the post and checked by a second AI model.</p>
          <p class="stat-line">A post its author deletes disappears from here within a week. If you posted something here and want it taken down,
            <a href="${REPO}/issues/new?title=Remove%20a%20post" target="_blank" rel="noopener">open an issue</a> and it will be removed.</p>
          <br><h4>Who we read</h4>
          <p class="stat-line"><a href="#/heads/all">${peopleOnly().length} people and ${accountsOnly().length} official accounts</a></p>
          <br><h4>Also this week</h4>
          <p class="stat-line"><a href="#/heads">Every AI post we collected from Bluesky</a></p>
          <p class="stat-line"><a href="#/week">The week in review</a></p>
        </aside>
      </div>`;
    const draw = (g) => {
      const items = list.filter((p) => !g || (by.head[p.person] || {}).group === g);
      if (!items.length) {
        $("#feed").innerHTML = `<p class="empty">${showHall ? "No posts in the Hall of fame yet." :
          "No picks in the last 7 days yet. New ones are added each evening."}</p>`;
        return;
      }
      if (showHall) {
        $("#feed").innerHTML = items.map((p) => postCard(p)).join("");
      } else {
        const days = {};
        items.forEach((p) => (days[istDay(p.posted_at)] = days[istDay(p.posted_at)] || []).push(p));
        $("#feed").innerHTML = Object.entries(days).sort((a, b) => b[0].localeCompare(a[0])).map(([d, ps]) =>
          `<section class="heads-day"><h3>${esc(longDate(d))}</h3>${ps.map((p) => postCard(p)).join("")}</section>`).join("");
      }
      activateEmbeds(view);
    };
    view.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => {
      view.querySelectorAll("[data-g]").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); });
      draw(b.dataset.g);
    }));
    draw("");
  }

  function pageHeadsAll() {
    const H = D.heads;
    const counts = {};
    weekPosts().forEach((p) => (counts[p.person] = (counts[p.person] || 0) + 1));
    view.innerHTML = `<div class="page-head"><h2>Who is followed</h2>
        <p>${peopleOnly().length} people and ${accountsOnly().length} official accounts. A Bluesky account is used only when it is verified by Bluesky,
        on the person's own web domain, or a profile that clearly matches the person. Every X handle was checked to exist through X's embed service.</p></div>
      ${headsTabs("heads/all")}
      ${H.groups.map((g) => {
        const ps = H.people.filter((h) => h.group === g.id);
        if (!ps.length) return "";
        return `<section class="roster"><h3>${esc(g.label)}</h3>
          <table class="ledger"><thead><tr><th>${g.kind === "account" ? "Account" : "Person"}</th><th class="hide-sm">Known for</th><th>Profiles</th><th class="num">This week</th></tr></thead>
          <tbody>${ps.map((h) => `<tr><td>${headLink(h)}<span class="blurb show-sm">${esc(h.known_for)}</span></td>
            <td class="hide-sm">${esc(h.known_for)}</td>
            <td class="profiles">${h.x ? `<a href="https://x.com/${esc(h.x)}" target="_blank" rel="noopener">X</a>` : ""}
              ${h.bsky ? `<a href="https://bsky.app/profile/${esc(h.bsky)}" target="_blank" rel="noopener">Bluesky</a>` : ""}</td>
            <td class="num">${counts[h.id] || ""}</td></tr>`).join("")}</tbody></table></section>`;
      }).join("")}`;
  }

  function pageHead(id) {
    if (id === "all") return pageHeadsAll();
    const h = by.head[id];
    if (!h) return notFound();
    const posts = livePosts().filter((p) => p.person === id);
    const bskyCheck = { verified: "verified by Bluesky", "own-domain": "on their own domain", "profile-match": "profile checked by hand" };
    view.innerHTML = `<div class="concept-page"><p><a href="#/heads">Attention Heads</a>, ${esc((by.group[h.group] || {}).label || "")}</p>
      <h2>${esc(h.name)}</h2>
      <p class="def">${esc(h.known_for)}</p>
      <p>${h.x ? `<a href="https://x.com/${esc(h.x)}" target="_blank" rel="noopener">@${esc(h.x)} on X</a>` : ""}
        ${h.x && h.bsky ? ", " : ""}${h.bsky ? `<a href="https://bsky.app/profile/${esc(h.bsky)}" target="_blank" rel="noopener">@${esc(h.bsky)} on Bluesky</a>
        <span class="asof">(${esc(bskyCheck[h.bsky_check] || "")})</span>` : ""}
        ${by.person[id] ? `<br><a href="#/people/${esc(id)}">Profile, history and news mentions</a>` : ""}</p>
      <h3 class="section-title">Posts</h3>
      ${posts.length ? posts.map((p) => postCard(p, { noName: true })).join("") : `<p class="empty">No AI posts collected yet.${h.bsky ? "" : " Posts from here appear only when an editor picks one on X."}</p>`}
    </div>`;
    activateEmbeds(view);
  }

  // ------------------------------------------------------------ Week in Review
  function isoWeek(dateStr) {
    const t = new Date(dateStr + "T00:00:00Z");
    const dayNum = t.getUTCDay() || 7;
    const monday = new Date(t); monday.setUTCDate(t.getUTCDate() - dayNum + 1);
    t.setUTCDate(t.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    const n = Math.ceil(((t - yearStart) / 86400000 + 1) / 7);
    const start = monday.toISOString().slice(0, 10);
    const sunday = new Date(monday); sunday.setUTCDate(monday.getUTCDate() + 6);
    return { id: `${t.getUTCFullYear()}-W${String(n).padStart(2, "0")}`, start, end: sunday.toISOString().slice(0, 10) };
  }
  function weekRange(w) {
    const opts = { day: "numeric", month: "long", timeZone: "UTC" };
    const a = new Date(w.start + "T12:00:00Z"), b = new Date(w.end + "T12:00:00Z");
    const left = a.toLocaleDateString("en-GB", a.getUTCMonth() === b.getUTCMonth() ? { day: "numeric", timeZone: "UTC" } : opts);
    return `${left} to ${b.toLocaleDateString("en-GB", { ...opts, year: "numeric" })}`;
  }
  function allWeeks() {
    const weeks = {};
    D.index.editions.forEach((e) => {
      const w = isoWeek(e.date);
      (weeks[w.id] = weeks[w.id] || { ...w, dates: [] }).dates.push(e.date);
    });
    return Object.values(weeks).sort((a, b) => b.id.localeCompare(a.id));
  }
  function countBoard(rows, limit = 8) {
    rows = rows.sort((a, b) => b[2] - a[2]).slice(0, limit);
    if (!rows.length) return `<p class="empty">Nothing yet.</p>`;
    const max = rows[0][2];
    return `<ol class="board">${rows.map(([label, href, c], i) => `<li><span class="n">${String(i + 1).padStart(2, "0")}</span>
      <span class="who">${href ? `<a href="${href}">${esc(label)}</a>` : esc(label)}</span><span class="count">${c}</span>
      <span class="bar" style="width:${Math.max(6, Math.round((c / max) * 100))}%"></span></li>`).join("")}</ol>`;
  }
  const tally = (items, key) => {
    const n = {};
    items.forEach((x) => [].concat(key(x) || []).forEach((k) => (n[k] = (n[k] || 0) + 1)));
    return n;
  };

  function pageWeek(id) {
    const weeks = allWeeks();
    if (!weeks.length) {
      view.innerHTML = `<div class="page-head"><h2>Week in Review</h2></div><p class="notice">No editions yet.</p>`;
      return;
    }
    const i = Math.max(0, weeks.findIndex((w) => w.id === id));
    const w = weeks[i];
    const stories = w.dates.flatMap((d) => (D.editions[d] ? D.editions[d].stories : []));
    const score = (s) => (s.buzz || 1) * 2 + (s.rank === 1 ? 3 : 0) + (s.spotlight ? 2 : 0) - (s.rank || 10) * 0.1;
    const top = stories.slice().sort((a, b) => score(b) - score(a)).slice(0, 7);
    const posts = livePosts().filter((p) => { const d = istDay(p.posted_at); return d >= w.start && d <= w.end; });
    const picks = posts.filter((p) => p.via === "inbox");
    const ongoing = w.end > (D.index.latest || "");
    const topics = Object.entries(tally(stories, (s) => s.topic)).map(([k, c]) => [topicName(k), "", c]);
    const concepts = Object.entries(tally(stories, (s) => s.concepts)).filter(([k]) => by.concept[k]).sort((a, b) => b[1] - a[1]).slice(0, 10);
    const labs = Object.entries(tally(stories, (s) => s.labs)).filter(([k]) => k !== "other").map(([k, c]) => [labName(k), `#/labs/${k}`, c]);
    const voices = Object.entries(tally(posts, (p) => p.person)).map(([k, c]) => [(by.head[k] || { name: k }).name, `#/heads/${k}`, c]);
    const site = location.protocol.startsWith("http") ? location.origin + location.pathname : "";
    const summary = `The week in AI, ${weekRange(w)}${ongoing ? " (so far)" : ""}\n\n` +
      top.slice(0, 5).map((s, n) => `${n + 1}. ${s.title}\n${s.one_liner}`).join("\n\n") +
      `\n\nEvery story is written from its sources and fact-checked.${site ? `\nRead the full week: ${site}#/week/${w.id}` : ""}`;
    view.innerHTML = `
      <div class="page-head"><h2>Week in Review</h2>
        <p>${esc(weekRange(w))}${ongoing ? ", so far" : ""}. ${plural(w.dates.length, "edition")}, ${plural(stories.length, "story")}${posts.length ? `, ${plural(posts.length, "post")} from the people we follow` : ""}.</p></div>
      <nav class="subtabs minor" aria-label="Other weeks">
        ${weeks[i + 1] ? `<a href="#/week/${weeks[i + 1].id}">Earlier week</a>` : ""}
        ${weeks[i - 1] ? `<a href="#/week/${weeks[i - 1].id}">Later week</a>` : ""}
        <a href="#/archive">All editions</a>
      </nav>
      <div class="today-grid">
        <div>
          <h3 class="section-title">The stories that mattered most</h3>
          <ol class="wk-top">${top.map((s) => `<li><div class="kicker"><span>${esc(fmtDate(s.date))}</span><span>${esc(topicName(s.topic))}</span>
            <span>${plural(s.buzz || 1, "source")}</span></div>
            <a class="wk-title" href="#/today/${esc(s.date)}/${esc(s.id)}">${esc(s.title)}</a><p>${esc(s.one_liner)}</p></li>`).join("")}</ol>
          <h3 class="section-title">What the week was about</h3>
          ${countBoard(topics, 9)}
          ${concepts.length ? `<p class="stat-line">Concepts that came up most:</p><div class="tags">${concepts.map(([k, c]) =>
            `<a class="chip concept" href="#/concepts/${esc(k)}">${esc(by.concept[k].term)} <span class="mono">${c}</span></a>`).join("")}</div>` : ""}
          ${picks.length ? `<h3 class="section-title">Picked from X this week</h3>${picks.slice(0, 3).map((p) => postCard(p)).join("")}
            <p><a href="#/context-window">All picks in the Context Window</a></p>` : ""}
        </div>
        <aside class="rail-box" aria-label="This week in numbers">
          <h4>Share this week</h4>
          <p class="stat-line">A plain-text summary of the top five stories, ready to paste into a post.</p>
          <button type="button" class="more" id="copy-week">${icon("plus")}<span>Copy the summary</span></button>
          <textarea id="week-text" class="sr-only" readonly>${esc(summary)}</textarea>
          <br><br><h4>Labs in the news</h4>
          ${countBoard(labs, 8)}
          <br><h4>Most active voices</h4>
          ${countBoard(voices, 8)}
          <br><h4>Every week</h4>
          <ul class="archive">${weeks.slice(0, 8).map((x) => `<li><a href="#/week/${x.id}"${x.id === w.id ? ' aria-current="true"' : ""}>
            <time>${esc(x.id.replace("-W", " week "))}</time>${esc(weekRange(x))}</a></li>`).join("")}</ul>
        </aside>
      </div>`;
    const btn = document.getElementById("copy-week");
    btn.addEventListener("click", async () => {
      const text = document.getElementById("week-text").value;
      let ok = false;
      try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
        const ta = document.getElementById("week-text"); ta.classList.remove("sr-only"); ta.select();
        try { ok = document.execCommand("copy"); } catch (err) { ok = false; }
        ta.classList.add("sr-only");
      }
      btn.querySelector("span").textContent = ok ? "Copied" : "Select and copy the text below";
    });
    activateEmbeds(view);
  }

  function pageStack() {
    const layers = [...D.meta.layers].reverse();
    view.innerHTML = `<div class="page-head"><h2>Stack map</h2><p>The AI stack from the arithmetic at the bottom to analytics at the top.</p></div>
      <p class="stack-note">Every concept, history entry and news story is tagged with one layer. Read it bottom up: each layer is built on the ones below it.</p>
      <div class="stack">${layers.map((l) => {
        const cs = D.concepts.filter((c) => c.layer === l.id);
        const lvl = by.layer[l.id].level;
        const news = D.stories.filter((s) => (s.concepts || []).some((id) => by.concept[id] && by.concept[id].layer === l.id)).length;
        return `<section class="layer-band ${l.id === "data" ? "data" : ""}" id="layer-${l.id}"><div>
          <h3><span class="lvl">L${lvl}</span><span class="nm">${esc(l.name)}</span></h3><p>${esc(l.blurb)}</p>
          <p class="asof">${plural(cs.length, "concept")}, ${plural(news, "news story")}</p></div>
          <div class="chips">${cs.map((c) => `<a class="chip concept" href="#/concepts/${c.id}">${esc(c.term)}</a>`).join("")}</div></section>`;
      }).join("")}</div>`;
  }

  function pageAbout() {
    const counts = D.timeline.reduce((a, e) => ((a[e.check.status] = (a[e.check.status] || 0) + 1), a), {});
    view.innerHTML = `<div class="prose">
      <div class="page-head"><h2>About Attention Span</h2></div>
      <p>Attention Span is a daily AI news bulletin with a memory. Every story is tagged with the same index as a history of AI
        from 1943 to today, so you can follow any piece of news back to the ideas it came from.</p>
      <h3>How a nightly edition is made</h3>
      <ol>
        <li>Collect everything from the last 24 hours: official blogs from OpenAI, Anthropic, Google, Microsoft, Meta, Mistral, Qwen and NVIDIA,
          the Power BI and Fabric blogs, Hacker News, Hugging Face papers and trending models, new GitHub repos and tech press.</li>
        <li>Remove duplicates and group items about the same event. The number of independent sources is the buzz signal.</li>
        <li>An AI editor picks the stories that matter to people who build with AI. A rule in code makes sure a major lab's own
          announcement with a strong signal is never left out.</li>
        <li>Each story is written only from its fetched source text, with a plain summary and a "like I'm 5" explanation.</li>
        <li>A different AI model fact-checks every claim against the sources, and code checks that every number appears in them.
          A story that fails is rewritten once, then dropped if it still fails.</li>
        <li>The edition is added to open JSON files. Nothing is deleted, so the archive grows every night.</li>
      </ol>
      <h3>Attention Heads</h3>
      <p><a href="#/heads">Attention Heads</a> follows what ${peopleOnly().length} people who shape AI post. Public Bluesky posts are read
        each night through Bluesky's open API. Each post is quoted in full with a short note on what it means, written only from the post
        and checked by a second model.</p>
      <h3>Posts from X</h3>
      <p>The <a href="#/context-window">Context Window</a> shows posts from X that an editor picked by hand. Nothing is scraped and no account
        is automated: each post is shown through X's own embedded post, exactly as it was posted. Every week each X post is checked again, and
        one its author deleted is removed. Posts belong to their authors and are not covered by this site's data licence.
        To have a post taken down, <a href="${REPO}/issues/new?title=Remove%20a%20post" target="_blank" rel="noopener">open an issue</a>.</p>
      <h3>How the history is checked</h3>
      <p>Every timeline entry links an original source: the paper, the journal DOI or the lab's own announcement.
        A script checks dates against the arXiv API and Crossref, and looks for the date on other pages.
        Today: ${counts.verified || 0} entries date-checked, ${counts["link-ok"] || 0} link-checked, ${counts.unverifiable || 0} not machine-checkable (a post on X).</p>
      <h3>The index</h3>
      <ul>
        <li><b>Type</b>: paper, model, product, event, person or concept.</li>
        <li><b>Lab</b>: who made it.</li>
        <li><b>Era</b>: seven eras from Foundations (1943) to Agents and reasoning (2024 to now), worked out from the date.</li>
        <li><b>Layer</b>: where it sits in the <a href="#/stack">AI stack</a>.</li>
        <li><b>Lineage</b>: what each concept evolved from and what it led to.</li>
      </ul>
      <h3>Use the data</h3>
      <p>All data is plain JSON in this site's <code>data</code> folder. It is free for non-commercial use with credit under
        <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license">CC BY-NC 4.0</a>: "Attention Span by Shashikant".
        For commercial use, contact Shashikant through <a href="https://github.com/shashikantdev3">GitHub</a>.
        The code is MIT-licensed. Linked articles and papers belong to their publishers.</p>
      <p>Built with free AI tiers (Google Gemini and Groq) and run once a night on a laptop.</p>
      <p class="colophon">Made by <a href="https://github.com/shashikantdev3">Shashikant</a>. Set in Bodoni Moda, Newsreader and IBM Plex Mono.</p>
    </div>`;
  }

  function notFound() {
    view.innerHTML = `<div class="page-head"><h2>Not found</h2></div><p class="notice">That page does not exist. Try <a href="#/today">Today</a> or search with <kbd>/</kbd>.</p>`;
  }

  // ------------------------------------------------------------ search
  let index = null;
  function buildIndex() {
    index = [
      ...D.stories.map((s) => ({ g: "News", t: s.title, d: `${fmtDate(s.date)}. ${s.one_liner}`, h: `#/today/${s.date}/${s.id}`, k: `${s.title} ${s.one_liner} ${s.summary}` })),
      ...D.timeline.map((e) => ({ g: "History", t: e.title, d: `${fmtDate(e.date)}. ${e.one_liner}`, h: `#/timeline/${e.id}`, k: `${e.title} ${e.one_liner}` })),
      ...D.concepts.map((c) => ({ g: "Concepts", t: c.term, d: c.definition, h: `#/concepts/${c.id}`, k: `${c.term} ${(c.aka || []).join(" ")} ${c.definition}`, boost: 2 })),
      ...D.people.map((p) => ({ g: "People", t: p.name, d: p.role, h: `#/people/${p.id}`, k: `${p.name} ${p.aliases.join(" ")} ${p.known_for}`, boost: 2 })),
      ...livePosts().filter((p) => p.text).map((p) => ({ g: "Attention Heads", t: `${(by.head[p.person] || {}).name || p.person}: ${p.text.slice(0, 80)}`,
        d: `${fmtDate(istDay(p.posted_at))}. ${p.meaning || ""}`, h: `#/heads/${p.person}`, k: `${(by.head[p.person] || {}).name || ""} ${p.text} ${p.meaning || ""}` })),
      ...D.heads.people.filter((h) => !by.person[h.id]).map((h) => ({ g: "People", t: h.name, d: h.known_for, h: `#/heads/${h.id}`, k: `${h.name} ${h.known_for}`, boost: 1 })),
      ...D.meta.labs.map((l) => ({ g: "Labs", t: l.name, d: l.blurb, h: `#/labs/${l.id}`, k: `${l.name} ${l.blurb}`, boost: 1 })),
    ];
  }
  const hl = (text, q) => {
    const i = text.toLowerCase().indexOf(q);
    return i < 0 ? esc(text) : `${esc(text.slice(0, i))}<mark>${esc(text.slice(i, i + q.length))}</mark>${esc(text.slice(i + q.length))}`;
  };
  function runSearch(q) {
    const out = document.getElementById("search-results");
    q = q.trim().toLowerCase();
    if (q.length < 2) { out.innerHTML = `<p class="empty">Type at least two letters.</p>`; return; }
    if (!index) buildIndex();
    const words = q.split(/\s+/);
    const hits = index.map((r) => {
      const k = r.k.toLowerCase(), t = r.t.toLowerCase();
      if (!words.every((w) => k.includes(w))) return null;
      return { r, score: (t.includes(q) ? 10 : 0) + (t.startsWith(q) ? 5 : 0) + (r.boost || 0) };
    }).filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 40);
    if (!hits.length) { out.innerHTML = `<p class="empty">No matches for "${esc(q)}".</p>`; return; }
    const groups = {};
    hits.forEach((h) => (groups[h.r.g] = groups[h.r.g] || []).push(h.r));
    out.innerHTML = Object.entries(groups).map(([g, rs]) => `<h4>${g}</h4>${rs.map((r) =>
      `<a href="${r.h}">${hl(r.t, q)}<small>${esc(r.d.slice(0, 140))}</small></a>`).join("")}`).join("");
  }
  function setupSearch() {
    const dlg = document.getElementById("search"), input = document.getElementById("search-input");
    const open = () => { dlg.showModal(); input.select(); runSearch(input.value); };
    document.getElementById("search-open").addEventListener("click", open);
    input.addEventListener("input", () => runSearch(input.value));
    document.getElementById("search-results").addEventListener("click", (e) => { if (e.target.closest("a")) dlg.close(); });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && !dlg.open && !/input|select|textarea/i.test(document.activeElement.tagName)) { e.preventDefault(); open(); }
    });
  }

  // ------------------------------------------------------------ router
  const $ = (s) => view.querySelector(s);
  function route(keepScroll) {
    const [name, ...params] = (location.hash.replace(/^#\/?/, "") || "today").split("/");
    const navName = { week: "archive" }[name] || name;
    document.querySelectorAll("#nav a[data-route]").forEach((a) => { if (a.dataset.route !== navName) a.removeAttribute("aria-current"); else a.setAttribute("aria-current", "page"); });
    const pages = {
      today: () => { pageToday(params[0]); if (params[1]) setTimeout(() => openStory(params[1]), 0); },
      archive: pageArchive,
      timeline: () => pageTimeline(params),
      concepts: () => (params[0] ? pageConcept(params[0]) : pageConcepts()),
      labs: () => (params[0] ? pageLab(params[0]) : pageLabs()),
      people: () => (params[0] ? pagePerson(params[0]) : pagePeople()),
      heads: () => (params[0] ? pageHead(params[0]) : pageHeads()),
      "context-window": () => pageContextWindow(params[0]),
      week: () => pageWeek(params[0]),
      stack: pageStack, about: pageAbout,
    };
    (pages[name] || notFound)();
    if (keepScroll !== true && !params[1] && !(name === "timeline" && params[0])) window.scrollTo(0, 0);
    const titles = { today: "Today", archive: "Archive", timeline: "Timeline", concepts: "Concepts", labs: "Labs", people: "People", heads: "Attention Heads", "context-window": "Context Window", week: "Week in Review", stack: "Stack map", about: "About" };
    document.title = `${titles[name] || "Attention Span"}: Attention Span`;
  }

  function setupTheme() {
    const btn = document.getElementById("theme-toggle");
    const paint = () => {
      const night = document.documentElement.getAttribute("data-theme") === "night";
      btn.innerHTML = night ? `${icon("day")}<span>Day</span>` : `${icon("night")}<span>Night</span>`;
      btn.setAttribute("aria-pressed", String(night));
      btn.setAttribute("aria-label", night ? "Switch to the day edition" : "Switch to the night edition");
      document.querySelector('meta[name="theme-color"]').setAttribute("content", night ? "#191E1B" : "#EDF0EA");
    };
    btn.addEventListener("click", () => {
      const night = document.documentElement.getAttribute("data-theme") !== "night";
      if (night) document.documentElement.setAttribute("data-theme", "night");
      else document.documentElement.removeAttribute("data-theme");
      try { localStorage.setItem("as-theme", night ? "night" : "day"); } catch (e) { /* private mode: choice lasts this visit */ }
      paint();
      if (document.querySelector("[data-x]")) route(true);   // X embeds pick their colours when drawn, so draw them again
    });
    paint();
  }

  function folio() {
    const n = D.index.editions.length, latest = D.index.latest;
    const ed = latest && D.editions[latest];
    document.getElementById("folio").innerHTML = `
      <span>${latest ? `<b>Edition No. ${n}</b>` : "<b>First edition coming</b>"}</span>
      <span class="mid">${latest ? esc(longDate(latest)) : ""}</span>
      <span>${ed ? `${plural(ed.stories.length, "story")}, ` : ""}${plural(D.timeline.length, "moment")} of history, ${plural(D.concepts.length, "concept")}</span>`;
  }

  function mastheadMeta() {
    const n = D.index.editions.length;
    const latest = D.index.latest;
    document.getElementById("edition-meta").innerHTML = latest
      ? `<strong>${esc(longDate(latest))}</strong>Edition ${n}, ${plural(D.timeline.length, "moment")} of history, ${plural(D.concepts.length, "concept")}`
      : `<strong>${plural(D.timeline.length, "moment")} of history</strong>${plural(D.concepts.length, "concept")}`;
  }

  setupTheme();
  load().then(() => {
    mastheadMeta();
    folio();
    setupSearch();
    window.addEventListener("hashchange", () => route());
    route();
  }).catch((err) => {
    view.innerHTML = `<p class="notice">The data did not load (${esc(err.message)}). Try reloading the page. On your own computer you can
      also run <code>python -m http.server -d docs</code> and open http://localhost:8000.</p>`;
  });
})();
