/* Attention Span: a static site over open JSON. No framework, no build step. */
(() => {
  "use strict";

  const D = { meta: null, timeline: [], concepts: [], people: [], index: { editions: [] }, editions: {}, stories: [] };
  const by = { concept: {}, person: {}, lab: {}, layer: {}, era: {}, type: {}, entry: {}, topic: {} };
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
  const getJSON = async (path) => {
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
          <ul class="archive">${D.index.editions.slice(0, 30).map((e) => `<li><a href="#/today/${e.date}" ${e.date === day ? 'aria-current="true"' : ""}>
            <time>${esc(fmtDate(e.date))}</time>${esc(e.lead)}</a></li>`).join("")}</ul>
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
    view.innerHTML = `<div class="concept-page"><p><a href="#/people">People</a></p><h2>${esc(p.name)}</h2>
      <p class="def">${esc(p.role)}. <span class="asof">Source for this role:
        <a href="${esc(p.role_source.url)}" target="_blank" rel="noopener">${esc(p.role_source.title)}</a></span></p>
      <p>${esc(p.known_for)}</p>
      <div class="tags">${chipsConcepts(p.concepts)}${chipsLabs(p.labs)}</div>
      ${p.links.length ? `<p style="margin-top:14px">${p.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.title)}</a>`).join(", ")}</p>` : ""}
      <h3 class="section-title">In the news</h3>${miniStories(news)}
      <h3 class="section-title">In history</h3>${miniEntries(entries)}</div>`;
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
        <a href="https://creativecommons.org/licenses/by-nc/4.0/" rel="license">CC BY-NC 4.0</a>: "Attention Span by DevWithData".
        For commercial use, email <a href="mailto:business@devwithdata.com">business@devwithdata.com</a>.
        The code is MIT-licensed. Linked articles and papers belong to their publishers.</p>
      <p>Built with free AI tiers (Google Gemini and Groq) and run once a night on a laptop.</p>
      <p class="colophon">Made by <a href="https://devwithdata.com">DevWithData</a>. Set in Newsreader and IBM Plex Mono.</p>
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
  function route() {
    const [name, ...params] = (location.hash.replace(/^#\/?/, "") || "today").split("/");
    document.querySelectorAll("#nav a[data-route]").forEach((a) => { if (a.dataset.route !== name) a.removeAttribute("aria-current"); else a.setAttribute("aria-current", "page"); });
    const pages = {
      today: () => { pageToday(params[0]); if (params[1]) setTimeout(() => openStory(params[1]), 0); },
      timeline: () => pageTimeline(params),
      concepts: () => (params[0] ? pageConcept(params[0]) : pageConcepts()),
      labs: () => (params[0] ? pageLab(params[0]) : pageLabs()),
      people: () => (params[0] ? pagePerson(params[0]) : pagePeople()),
      stack: pageStack, about: pageAbout,
    };
    (pages[name] || notFound)();
    if (!params[1] && !(name === "timeline" && params[0])) window.scrollTo(0, 0);
    const titles = { today: "Today", timeline: "Timeline", concepts: "Concepts", labs: "Labs", people: "People", stack: "Stack map", about: "About" };
    document.title = `${titles[name] || "Attention Span"}: Attention Span`;
  }

  function mastheadMeta() {
    const n = D.index.editions.length;
    const latest = D.index.latest;
    document.getElementById("edition-meta").innerHTML = latest
      ? `<strong>${esc(longDate(latest))}</strong>Edition ${n}, ${plural(D.timeline.length, "moment")} of history, ${plural(D.concepts.length, "concept")}`
      : `<strong>${plural(D.timeline.length, "moment")} of history</strong>${plural(D.concepts.length, "concept")}`;
  }

  load().then(() => {
    mastheadMeta();
    setupSearch();
    window.addEventListener("hashchange", route);
    route();
  }).catch((err) => {
    view.innerHTML = `<p class="notice">The data did not load (${esc(err.message)}). If you opened index.html straight from disk,
      serve the folder instead: run <code>python -m http.server -d docs</code> and open http://localhost:8000.</p>`;
  });
})();
