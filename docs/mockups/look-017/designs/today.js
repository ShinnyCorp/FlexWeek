// Today's app (Calendar), the reference design: docs/0.17/plan.md, Phase 2's brief and Phase 3's
// decisions 11 to 18. A keeps today's structure with every fix; B moves the side panel into a slim
// left rail and gives the week the full width, as Notion Calendar and Fantastical do.

(function () {
  const W = FW.week;
  const T = FW.time;
  // The grid opens at the time now: 08:48 at the top shows 09:00 to 22:00 whole, 15:40 in the middle.
  const HOUR = 51;
  const START = 8 * 60 + 48;
  const VIEW_H = 686;
  const LETTERS = ["M", "T", "W", "T", "F", "S", "S"];

  const y = (minute) => ((minute - START) / 60) * HOUR;
  // Poster's offset shadow would close the 3-pixel gap between neighbours, so its blocks end higher.
  let shadowGap = 0;
  const book = (size = 16) => `<span class="td-book">${FW.icon("book-open", size, 2)}</span>`;
  const isHomework = (b) => b.category === "assignments";

  const placedHomework = W.blocks
    .filter(isHomework)
    .flatMap((b) => b.days.map((day) => ({ ...b, day })))
    .sort((a, b) => a.day - b.day || a.start - b.start);
  const notPlaced = W.homework.filter((h) => !h.placed);
  const homeworkByDay = W.days.map((d) =>
    T.on(d.index).filter(isHomework).reduce((sum, b) => sum + b.end - b.start, 0));

  function dayWhen(day, minute) {
    const name = day === W.today ? "Today" : W.days[day].short;
    return `${name} ${T.clock(minute)}`;
  }

  // --- the grid ---------------------------------------------------------------------------------

  function hours(nowShown) {
    let labels = "";
    let rules = "";
    for (let h = 9; h <= 22; h++) {
      const at = y(h * 60);
      if (at < 0 || at > VIEW_H) continue;
      rules += `<div class="td-rule" style="top:${at}px"></div>`;
      const nearNow = nowShown && Math.abs(at - y(W.now)) < 20;
      if (at - 9 >= 0 && at + 9 <= VIEW_H && !nearNow) labels += `<div class="td-hour" style="top:${at}px">${T.clock(h * 60)}</div>`;
    }
    return { labels, rules };
  }

  function block(b, wide) {
    let top = y(b.start) + 1;
    const bottom = y(b.end) - 2 - shadowGap;
    const cut = top < 0;
    if (cut) top = 0;
    const icon = isHomework(b) ? `<span class="td-book">${FW.icon("book-open", wide ? 14 : 12, 2.25)}</span>` : "";
    const hw = isHomework(b) ? " hw" : "";
    const range = T.range(b.start, b.end);
    const length = T.length(b.end - b.start);
    const pin = b.pinned ? `<span title="Pinned">${FW.icon("pin", 13, 2)}</span>` : "";
    const stack = wide
      ? `<div class="td-b-stack">
           <div class="td-b-row"><div class="td-b-title${hw}">${icon}${b.title}</div><div class="td-b-len">${pin}${length}</div></div>
           <div class="td-b-time">${range}</div>
         </div>
         <div class="td-b-inline"><b class="${hw}">${icon}${b.title}</b><span>${range}</span><em>${length}</em></div>`
      : `<div class="td-b-stack">
           <div class="td-b-title${hw}">${icon}${b.title}</div>
           <div class="td-b-time">${range}</div>
           <div class="td-b-len">${length}</div>
         </div>
         <div class="td-b-inline"><b class="${hw}">${icon}${b.title}</b><span>${T.clock(b.start)}</span></div>`;
    return `<div class="td-block${wide ? " wide" : ""}${cut ? " cut-top" : ""}" data-cat="${b.category}"
      style="top:${top}px;height:${bottom - top}px">${stack}</div>`;
  }

  // One grid: the gutter, a column per day, the rules, the time now. `head(day)` draws a column's
  // header; `corner` the gutter's top cell.
  function grid(days, { head, corner = "", wide = false }) {
    const showsToday = days.includes(W.today);
    const { labels, rules } = hours(showsToday);
    const nowAt = y(W.now);
    const cols = days.map((day) => {
      const today = day === W.today;
      const blocks = T.on(day).map((b) => block(b, wide)).join("");
      const now = today ? `<div class="td-now" style="top:${nowAt - 1}px"></div>` : "";
      return `<div class="td-col${today && days.length > 1 ? " today" : ""}">${blocks}${now}</div>`;
    }).join("");
    const faint = showsToday && days.length > 1 ? `<div class="td-nowfaint" style="top:${nowAt}px"></div>` : "";
    const pill = showsToday ? `<div class="td-nowpill" style="top:${nowAt}px">${T.clock(W.now)}</div>` : "";
    return `
      <div class="td-grid${days.length === 1 ? " single" : ""}" style="--td-cols:${days.length}">
        <div class="td-head"><div class="td-corner">${corner}</div>${days.map(head).join("")}</div>
        <div class="td-body">
          <div class="td-gutter">${labels}${pill}</div>
          <div class="td-cols">${rules}${faint}${cols}</div>
        </div>
      </div>`;
  }

  const zoom = `<span class="td-zoom" title="Zoom"><span>${FW.icon("minus", 14, 2)}</span><i></i><span>${FW.icon("plus", 14, 2)}</span></span>`;

  // Choose, per block, the most it can show without cutting a word: the title (up to two lines),
  // the time, the length; then the title and start on one line; then colour only.
  function fitBlocks(root) {
    for (const b of root.querySelectorAll(".td-block")) {
      const modes = b.classList.contains("wide") ? ["full", "inline"] : ["full", "two", "one", "inline", "title"];
      const title = b.querySelector(".td-b-title");
      const tryMode = (mode) => {
        b.dataset.fit = mode;
        // Chrome keeps a stale line clamp when it changes through a selector; set it on the element.
        title.style.webkitLineClamp = mode === "one" ? "1" : "2";
        if (b.scrollHeight > b.clientHeight + 0.5) return "no";
        const cut = mode === "inline"
          ? (() => { const line = b.querySelector(".td-b-inline b"); return line.scrollWidth > line.clientWidth + 1; })()
          : title.scrollHeight > title.clientHeight + 1;
        return cut ? "cut" : "yes";
      };
      let chosen = null;
      let fallback = null;
      for (const mode of modes) {
        const result = tryMode(mode);
        if (result === "yes") { chosen = mode; break; }
        if (result === "cut" && !fallback) fallback = mode;
      }
      if (chosen) tryMode(chosen);
      else if (fallback) tryMode(fallback);
      else b.dataset.fit = "bare";
    }
  }

  // The stage is drawn before it joins the page, and a face can finish loading after that, so the
  // blocks are fitted once they are on the page and again when every font has loaded.
  function whenAttached(el, fn, tries = 0) {
    if (el.isConnected) {
      fn();
      document.fonts.ready.then(() => el.isConnected && fn());
      setTimeout(() => el.isConnected && fn(), 250);
    } else if (tries < 100) setTimeout(() => whenAttached(el, fn, tries + 1), 0);
  }

  // --- the side panel's pieces ------------------------------------------------------------------

  function focusRows() {
    return placedHomework.map((b) => `
      <div class="td-row">${book(16)}<span class="nm">${b.title}</span>
        <span class="tm${b.day === W.today ? " today" : ""}">${dayWhen(b.day, b.start)}</span></div>`).join("");
  }

  function chips() {
    return notPlaced.map((h) => `
      <div class="td-chipitem" data-cat="assignments">${book(16)}<span class="nm">${h.title}</span>
        <span class="len">${T.length(h.minutes)}</span></div>`).join("");
  }

  function load() {
    const most = Math.max(...homeworkByDay);
    const cols = homeworkByDay.map((m, i) => {
      const cls = [i === W.today ? "today" : "", i < W.today ? "past" : ""].join(" ");
      const bar = m ? `<div class="bar" style="height:${6 + Math.round((m / most) * 26)}px" title="${T.length(m)}"></div>` : `<div class="bar none"></div>`;
      return `<div class="col ${cls}"><div class="track">${bar}</div><span class="d">${LETTERS[i]}</span></div>`;
    }).join("");
    return `<div class="td-load">${cols}</div>`;
  }

  function daySummary(day) {
    const totals = {};
    for (const b of T.on(day)) totals[b.category] = (totals[b.category] || 0) + b.end - b.start;
    const order = Object.keys(totals);
    const all = order.reduce((s, c) => s + totals[c], 0);
    const stack = order.map((c) => `<span data-cat="${c}" style="flex:${totals[c]}"></span>`).join("");
    const rows = order.map((c) => `
      <div class="r" data-cat="${c}">${c === "assignments" ? book(14) : `<i class="dot"></i>`}
        <span class="nm">${W.categories[c]}</span><span class="v">${T.length(totals[c])}</span></div>`).join("");
    return { all, stack, rows, order, totals };
  }

  // --- A, Refined grid ----------------------------------------------------------------------------

  function headA(day) {
    const d = W.days[day];
    if (day === W.today) return `<div class="td-dh today"><span class="td-dn">${d.short}</span><span class="td-datechip">${d.date}</span></div>`;
    return `<div class="td-dh"><span class="td-dn">${d.short}</span><span class="td-dd">${d.date}</span></div>`;
  }

  function notPlacedCard(view) {
    return `
      <section class="td-card">
        <div class="td-sec-head"><span class="td-label">Not placed yet</span><span class="td-count">${notPlaced.length}</span></div>
        <div class="td-chips">${chips()}</div>
        <div class="td-hint">Drag one onto the ${view} to place it.</div>
      </section>`;
  }

  function renderA(el, ctx) {
    shadowGap = ctx.look === "poster" ? 1 : 0;
    if (ctx.view === "day") {
      const s = daySummary(W.today);
      const d = W.days[W.today];
      const head = () => `<div class="td-dayhead"><span class="td-dn">${d.name}</span><span class="td-datechip">${d.date}</span>
        <span class="sp"></span><span class="td-muted">${T.on(W.today).length} things · ${T.length(s.all)}</span></div>`;
      el.innerHTML = `
        <div class="td-a td-a-day">
          <div class="td-gridcard td-card">${grid([W.today], { head, corner: zoom, wide: true })}</div>
          <aside class="td-panel">
            ${notPlacedCard("day")}
            <section class="td-card">
              <div class="td-sec-head"><span class="td-label">Summary</span><span class="td-muted td-small">${T.length(s.all)}</span></div>
              <div class="td-stack">${s.stack}</div>
              <div class="td-sum">${s.rows}</div>
            </section>
          </aside>
        </div>`;
    } else {
      const total = homeworkByDay.reduce((a, b) => a + b, 0);
      el.innerHTML = `
        <div class="td-a">
          <div class="td-gridcard td-card">${grid(W.days.map((d) => d.index), { head: headA, corner: zoom })}</div>
          <aside class="td-panel">
            <section class="td-card td-next">
              <div class="td-label">Next</div>
              <div class="td-next-body" data-cat="extra">
                <div class="td-next-title">${W.next.title}</div>
                <div class="td-next-when">${T.clock(W.next.start)} · in ${W.next.inMinutes} min</div>
              </div>
            </section>
            <section class="td-card">
              <div class="td-sec-head"><span class="td-label">Start a focus timer</span></div>
              <div class="td-rows">${focusRows()}</div>
            </section>
            ${notPlacedCard("week")}
            <section class="td-card">
              <div class="td-sec-head"><span class="td-label">This week</span><span class="td-muted td-small td-tot">${book(14)}${T.length(total)}</span></div>
              ${load()}
            </section>
          </aside>
        </div>`;
    }
    whenAttached(el, () => fitBlocks(el));
  }

  // --- B, Rail --------------------------------------------------------------------------------------

  function miniMonth() {
    // September 2026, weeks from Monday: 31 August to 4 October.
    const rows = [];
    let date = new Date(2026, 7, 31);
    for (let r = 0; r < 5; r++) {
      const cells = [];
      for (let c = 0; c < 7; c++) {
        const n = date.getDate();
        const out = date.getMonth() !== 8;
        const today = !out && n === W.days[W.today].date;
        const due = !out && n === W.days[6].date;
        cells.push(`<span class="d${out ? " out" : ""}${today ? " today" : ""}${due ? " due" : ""}">${n}</span>`);
        date = new Date(date.getFullYear(), date.getMonth(), n + 1);
      }
      rows.push(`<div class="td-mm-row${r === 3 ? " this" : ""}">${cells.join("")}</div>`);
    }
    return `
      <section class="td-mm">
        <div class="td-mm-head"><b>${W.monthTitle}</b>
          <span class="td-mm-nav"><span>${FW.icon("chevron-left", 16)}</span><span>${FW.icon("chevron-right", 16)}</span></span></div>
        <div class="td-mm-row wd">${LETTERS.map((l) => `<span>${l}</span>`).join("")}</div>
        ${rows.join("")}
      </section>`;
  }

  function rail() {
    const rows = notPlaced.map((h) => `
      <div class="td-row td-cchip" data-cat="assignments">${book(15)}<span class="nm">${h.title}</span>
        <span class="tm">${T.length(h.minutes)}</span></div>`).join("");
    return `
      <aside class="td-rail">
        ${miniMonth()}
        <section>
          <div class="td-sec-head"><span class="td-label">Next</span></div>
          <div class="td-rnext" data-cat="extra">
            <div class="t">${W.next.title}</div>
            <div class="w">${T.clock(W.next.start)} · in ${W.next.inMinutes} min</div>
            <div class="then"><i></i>Then ${W.next.then}</div>
          </div>
        </section>
        <section>
          <div class="td-sec-head"><span class="td-label">Not placed yet</span><span class="td-count">${notPlaced.length}</span></div>
          <div class="td-rows">${rows}</div>
        </section>
        <section>
          <div class="td-sec-head"><span class="td-label">Start a focus timer</span></div>
          <div class="td-rows">${focusRows()}</div>
        </section>
      </aside>`;
  }

  function headB(day) {
    const d = W.days[day];
    const m = homeworkByDay[day];
    const date = day === W.today ? `<span class="td-datechip">${d.date}</span>` : `<span class="td-dd">${d.date}</span>`;
    const ld = m ? `<div class="ld">${FW.icon("book-open", 12, 2.25).replace("fw-icon", "fw-icon td-book")}${T.length(m)}</div>` : `<div class="ld"></div>`;
    return `<div class="td-bh${day === W.today ? " today" : ""}"><div class="top"><span class="td-dn">${d.short}</span>${date}</div>${ld}</div>`;
  }

  function agenda() {
    const items = T.on(W.today);
    const s = daySummary(W.today);
    let list = "";
    let nowDrawn = false;
    for (const b of items) {
      if (!nowDrawn && b.start > W.now) {
        list += `<div class="td-ag-now"><span class="p">${T.clock(W.now)}</span><span class="l"></span></div>`;
        nowDrawn = true;
      }
      const past = b.end <= W.now;
      const pin = b.pinned ? `<span class="pin">${FW.icon("pin", 12, 2)}Pinned</span>` : "";
      list += `
        <div class="td-ag-item${past ? " past" : ""}" data-cat="${b.category}">
          <div class="tm"><b>${T.clock(b.start)}</b><span>${T.clock(b.end)}</span></div>
          <div class="bd"><div class="t">${isHomework(b) ? book(14) : ""}${b.title}</div>
            <div class="s">${T.length(b.end - b.start)}${pin}</div></div>
        </div>`;
    }
    return `
      <section class="td-agenda">
        <div class="td-ag-h">${W.days[W.today].name}</div>
        <div class="td-ag-sub">${items.length} things · ${T.length(s.all)}</div>
        <div class="td-ag-list">${list}</div>
        <div class="td-ag-foot">
          <div class="td-sec-head"><span class="td-label">Summary</span></div>
          <div class="td-stack">${s.stack}</div>
          <div class="td-sum">${s.rows}</div>
        </div>
      </section>`;
  }

  function renderB(el, ctx) {
    shadowGap = ctx.look === "poster" ? 1 : 0;
    const main = ctx.view === "day"
      ? `${agenda()}${grid([W.today], { head: headB, corner: zoom, wide: true })}`
      : grid(W.days.map((d) => d.index), { head: headB, corner: zoom });
    el.innerHTML = `<div class="td-b${ctx.view === "day" ? " td-b-day" : ""}">${rail()}<div class="td-main">${main}</div></div>`;
    whenAttached(el, () => fitBlocks(el));
  }

  FW.register({
    id: "today",
    name: "Today's app",
    purpose: "Calendar",
    role: "main",
    now: "Pale blocks with no edge on a tinted page, the week opening on the night (01:00 to 15:00 at 15:40), a dangling \"·\" in every block, accent headings that look like links, a red \"(\" on each tray chip, and 400 pixels of empty panel.",
    current: { week: "current/b-light-week.png", day: "current/b-light-day.png" },
    variants: {
      A: {
        name: "Refined grid",
        summary: "Today's structure, every Phase 3 fix: hours down the left, seven columns, the side panel on the right as cards that end where their content ends.",
        catalogue: ["Flat Design", "Swiss Modernism 2.0", "Inter"],
        changes: [
          "Blocks with a 3-pixel category edge, the title at 600, the time muted, a 3-pixel gap; the length on its own line, never a \"·\" at a line end.",
          "Each block shows the most it can without cutting a word: title, time, length; a 45-minute block keeps its whole name; a 30-minute one reads \"Dinner 18:30\".",
          "Opens at the time now: 09:00 to 22:00, the now line in the accent with a halo and its pill in the gutter.",
          "Today is an accent date chip and a 3 % wash; hour rules only, thin; a small \"− +\" zoom pill; no visible scroll bar.",
          "The panel as cards: Next (\"Soccer practice\", \"16:00 · in 20 min\"), the focus list in time order with times right-aligned, chips with a straight inset edge and the length right-aligned, a quiet \"This week\" row of homework per day.",
          "Day: one wide column, no Next band; the panel holds Not placed yet and a summary with category dots and a stacked bar.",
        ],
        render: renderA,
      },
      B: {
        name: "Rail",
        summary: "The same content in a different structure: a slim left rail (a mini month with this week banded, Next, Not placed yet, the focus list) and the week on a full-width sheet.",
        catalogue: ["Notion Calendar and Fantastical's sidebar", "Flat Design", "Inter"],
        changes: [
          "No right side panel: the week gets 137-pixel columns, about 10 % more than A.",
          "Each day's header carries its homework hours (\"1 h 30 min\" with the book icon), which replaces the \"This week\" card.",
          "The mini month shows this week banded, today in the accent and a dot on the day homework is due.",
          "Faint day rules on the sheet, since the columns are wider and nothing frames them.",
          "Day: the day's agenda beside the rail (times, lengths, the time now as a line, a summary bar), and the hours wide.",
        ],
        render: renderB,
      },
    },
  });
})();
