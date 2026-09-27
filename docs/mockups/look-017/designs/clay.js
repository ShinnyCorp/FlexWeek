// Clay deck (Agenda): the week as soft clay cards. Option A lays the seven days side by side;
// option B turns them into a carousel with today in the middle. Both keep the category family for
// blocks and the look's surfaces for cards, so no day gets a pastel of its own.

(function () {
  const W = FW.week;
  const T = FW.time;
  const FROM = 8 * 60;
  const TO = 22 * 60;
  const HOURS = (TO - FROM) / 60;

  // Text fitting, by a generous estimate of Inter's and JetBrains Mono's advance widths (a canvas
  // would measure a fallback face if Inter had not been used yet).
  let mono = false;
  function width(text, px, weight) {
    return text.length * px * (mono || weight >= 600 ? 0.6 : 0.56) + 4;
  }

  function minutesOn(day) {
    return T.on(day).reduce((sum, b) => sum + (b.end - b.start), 0);
  }

  // One block inside a day's hours. `k` is pixels per minute; `room` the text's width in pixels.
  // `size` is the text size in points (11 or 13); `full` adds the length and "Pinned".
  function block(b, k, room, { size = 11, full = false } = {}) {
    const top = (b.start - FROM) * k + 1.5;
    const height = (b.end - b.start) * k - 3;
    const px = size * 4 / 3;
    const lh = size === 13 ? 18 : 15;
    const homework = b.category === "assignments";
    const icon = homework ? `<span class="cl-bk">${FW.icon("book-open", size === 13 ? 14 : 12, 2)}</span>` : "";
    const textRoom = room - (homework ? (size === 13 ? 18 : 16) : 0);
    const range = T.range(b.start, b.end);
    const extra = `${T.length(b.end - b.start)}${b.pinned ? " · Pinned" : ""}`;
    const title = `<span class="cl-bn">${b.title}</span>`;
    let body = "";
    let shape = "tall";
    // A title too long for one line may take two when the block has room for three lines.
    if (width(b.title, px, 600) > textRoom && height >= 3 * lh + 7) shape = "tall wrap";
    if (full && height >= 3 * lh + 10) {
      body = `<span class="cl-bt">${icon}${title}</span><span class="cl-bm">${range}</span><span class="cl-bm">${extra}</span>`;
    } else if (height >= 2 * lh + 7) {
      body = `<span class="cl-bt">${icon}${title}</span><span class="cl-bm">${full ? `${range} · ${extra}` : range}</span>`;
    } else if (height >= 15) {
      shape = "line";
      // The most the line can carry: the range and length, the range, the start, or the title.
      const options = full ? [`${range} · ${extra}`, range, T.clock(b.start)] : [T.clock(b.start)];
      const time = options.find((t) => width(b.title, px, 600) + 8 + width(t, px, 400) <= textRoom);
      body = `<span class="cl-bt">${icon}${title}${time ? `<span class="cl-bm">${time}</span>` : ""}</span>`;
    } else {
      shape = "bare";
    }
    return `<div class="cl-block ${shape}" data-cat="${b.category}" style="top:${top}px;height:${height}px" title="${b.title}">${body}</div>`;
  }

  // A day's hours: rules every hour, the blocks, and on today the now line.
  function hours(day, k, room, { labels = false, size = 11, full = false } = {}) {
    let rules = "";
    for (let h = 0; h <= HOURS; h++) {
      rules += `<div class="cl-rule" style="top:${h * 60 * k}px"></div>`;
      if (labels) rules += `<div class="cl-hl" style="top:${h * 60 * k}px">${T.clock(FROM + h * 60)}</div>`;
    }
    const blocks = T.on(day).map((b) => block(b, k, room, { size, full })).join("");
    const now = day === W.today
      ? `<div class="cl-now" style="top:${(W.now - FROM) * k}px"><span class="cl-now-pill">${T.clock(W.now)}</span></div>`
      : "";
    return `${rules}<div class="cl-lane">${blocks}${now}</div>`;
  }

  function dayHead(d, extra = "") {
    const today = d.index === W.today;
    return `<header class="cl-head">
        <span class="cl-dayname">${d.name}</span>
        ${extra}
        <span class="cl-date${today ? " today" : ""}">${d.date}</span>
      </header>`;
  }

  const unplaced = () => W.homework.filter((h) => !h.placed);

  function chip(h) {
    return `<div class="cl-chip" data-cat="assignments">
        <span class="cl-chip-ic">${FW.icon("book-open", 14, 2)}</span>
        <span class="cl-chip-text"><span class="cl-chip-t">${h.title}</span><span class="cl-chip-l">${T.length(h.minutes)}</span></span>
        <span class="cl-chip-grip">${FW.icon("grip-vertical", 16)}</span>
      </div>`;
  }

  // The dish: a pressed-in tray holding the homework that has no time yet.
  function dish(layout) {
    const list = unplaced();
    const chips = list.map(chip).join("");
    if (layout === "column") {
      return `<section class="cl-dish column">
          <div class="cl-dish-head">
            <span class="cl-dish-t">Not placed yet</span>
            <span class="cl-dish-n">${list.length}</span>
          </div>
          <p class="cl-dish-sub">Due ${W.days[list[0].due.day].name} ${W.days[list[0].due.day].date}</p>
          <div class="cl-dish-chips">${chips}</div>
        </section>`;
    }
    return `<section class="cl-dish row">
        <div class="cl-dish-head">
          <span class="cl-dish-t">Not placed yet</span>
          <span class="cl-dish-sub">Due ${W.days[list[0].due.day].short} ${W.days[list[0].due.day].date}</span>
        </div>
        <div class="cl-dish-chips">${chips}</div>
        <p class="cl-dish-hint">Drag a chip onto a day.</p>
      </section>`;
  }

  // The day's hours by kind, with category dots and a thin stacked bar (plan decision 16).
  function summary(day, { left = false } = {}) {
    const by = {};
    for (const b of T.on(day)) by[b.category] = (by[b.category] || 0) + (b.end - b.start);
    const free = HOURS * 60 - minutesOn(day);
    const rows = Object.entries(by).sort((a, b) => b[1] - a[1]);
    rows.push(["free", free]);
    const total = HOURS * 60;
    const bar = rows.map(([cat, m]) => `<span data-cat="${cat}" style="flex:${m}"></span>`).join("");
    const list = rows.map(([cat, m]) => `<li data-cat="${cat}"><span class="cl-dot"></span><span>${W.categories[cat]}${cat === "assignments" ? ` ${FW.icon("book-open", 12, 2)}` : ""}</span><span class="cl-sum-l">${T.length(m)}</span></li>`).join("");
    return `<section class="cl-sum">
        <div class="cl-sum-head"><span class="cl-dish-t">${W.days[day].name}, 08:00 to 22:00</span></div>
        <div class="cl-bar" title="${total} minutes">${bar}</div>
        <ul>${list}</ul>
        ${left ? leftToday(day) : ""}
      </section>`;
  }

  // What is still ahead today: the plans after now and the free time around them.
  function leftToday(day) {
    const ahead = T.on(day).filter((b) => b.end > W.now);
    const planned = ahead.reduce((sum, b) => sum + (b.end - Math.max(b.start, W.now)), 0);
    const free = TO - W.now - planned;
    return `<div class="cl-sum-head cl-left"><span class="cl-dish-t">Left today</span></div>
        <ul class="cl-left-list">
          <li><span class="cl-ic">${FW.icon("clock", 14)}</span><span>Planned</span><span class="cl-sum-l">${T.length(planned)}</span></li>
          <li><span class="cl-ic">${FW.icon("sun", 14)}</span><span>Free until 22:00</span><span class="cl-sum-l">${T.length(free)}</span></li>
          <li><span class="cl-ic">${FW.icon("skip-forward", 14)}</span><span>Next at ${T.clock(W.next.start)}</span><span class="cl-sum-l">in ${W.next.inMinutes} min</span></li>
        </ul>`;
  }

  // The week at a glance for Day: each day's blocks along 08:00 to 22:00, today marked.
  function weekList() {
    const rows = W.days.map((d) => {
      const segs = T.on(d.index).map((b) => `<span data-cat="${b.category}" style="left:${(b.start - FROM) / (TO - FROM) * 100}%;width:${(b.end - b.start) / (TO - FROM) * 100}%"></span>`).join("");
      return `<li class="${d.index === W.today ? "on" : ""}"><span class="cl-wk-d">${d.short}</span><span class="cl-wk-n">${d.date}</span><span class="cl-wk-bar">${segs}</span></li>`;
    }).join("");
    return `<section class="cl-sum cl-week">
        <div class="cl-sum-head"><span class="cl-dish-t">This week</span></div>
        <ul>${rows}</ul>
      </section>`;
  }

  // --- A. Soft deck -------------------------------------------------------------------------

  function softDeckWeek(el, ctx) {
    const HEAD = 44;
    const BODY = 574;
    const k = BODY / (HOURS * 60);
    const cardW = (1198 - 6 * 8) / 7;
    let gutter = "";
    for (let h = 0; h <= HOURS; h++) {
      gutter += `<div class="cl-hl" style="top:${HEAD + h * 60 * k}px">${T.clock(FROM + h * 60)}</div>`;
    }
    const cards = W.days.map((d) => {
      const today = d.index === W.today;
      return `<section class="cl-card${today ? " today" : ""}" style="width:${cardW}px">
          ${dayHead(d)}
          <div class="cl-hours" style="height:${BODY}px">${hours(d.index, k, cardW - 12 - 19)}</div>
        </section>`;
    }).join("");
    el.innerHTML = `<div class="cl-root cl-a cl-a-week">
        <div class="cl-deck">
          <div class="cl-gutter">${gutter}</div>
          <div class="cl-cards">${cards}</div>
        </div>
        ${dish("row")}
      </div>`;
  }

  function softDeckDay(el, ctx) {
    const d = W.days[W.today];
    const BODY = 630;
    const k = BODY / (HOURS * 60);
    const n = T.on(d.index).length;
    el.innerHTML = `<div class="cl-root cl-a cl-a-day">
        <section class="cl-card today big">
          ${dayHead(d, `<span class="cl-head-note">${n} things planned</span>`)}
          <div class="cl-hours labelled" style="height:${BODY}px">${hours(d.index, k, 780, { labels: true, size: 13, full: true })}</div>
        </section>
        <aside class="cl-side">
          ${dish("column")}
          ${summary(d.index)}
          ${weekList()}
        </aside>
      </div>`;
  }

  // --- B. Card carousel ---------------------------------------------------------------------

  // A card at full size (the day in front) or at 70 % (a neighbour peeking). The smaller card is
  // laid out smaller rather than scaled, so its text stays on the type scale.
  function carouselCard(d, ctx, { x, w, h, front, open }) {
    const HEAD = front ? 60 : 48;
    const body = h - HEAD - (front ? 16 : 12);
    const k = body / (HOURS * 60);
    const n = T.on(d.index).length;
    const note = front ? `<span class="cl-head-note">${d.index === W.today ? "Today · " : ""}${n} ${n === 1 ? "thing" : "things"}</span>` : "";
    const inner = open
      ? `<div class="cl-open">
           <div class="cl-hours labelled" style="height:${body}px">${hours(d.index, k, w - 418, { labels: true, size: 13, full: true })}</div>
           ${summary(d.index, { left: true })}
         </div>`
      : `<div class="cl-hours${front ? " labelled" : ""}" style="height:${body}px">${hours(d.index, k, w - (front ? 106 : 38), { labels: front, full: front })}</div>`;
    return `<section class="cl-card${front ? " front" : " peek"}${d.index === W.today ? " today" : ""}${open ? " open" : ""}"
        style="left:${x}px;top:${(632 - h) / 2}px;width:${w}px;height:${h}px">
        ${dayHead(d, note)}
        ${inner}
      </section>`;
  }

  function carousel(el, ctx, open) {
    const H = 616;
    const w = open ? 800 : 452;
    const pw = Math.round(452 * 0.7);
    const ph = Math.round(H * 0.7);
    const gap = 32;
    const x0 = (1280 - w) / 2;
    const t = W.today;
    const cards = [];
    cards.push(carouselCard(W.days[t], ctx, { x: x0, w, h: H, front: true, open }));
    for (let step = 1; step <= 2; step++) {
      const left = W.days[t - step];
      const right = W.days[t + step];
      const lx = x0 - step * (pw + gap);
      const rx = x0 + w + gap + (step - 1) * (pw + gap);
      if (left) cards.push(carouselCard(left, ctx, { x: lx, w: pw, h: ph }));
      if (right) cards.push(carouselCard(right, ctx, { x: rx, w: pw, h: ph }));
    }
    const prev = W.days[t - 1];
    const next = W.days[t + 1];
    el.innerHTML = `<div class="cl-root cl-b${open ? " cl-b-day" : " cl-b-week"}">
        <div class="cl-stage">${cards.join("")}</div>
        <span class="cl-arrow" style="left:${x0 - gap / 2 - 22}px" title="${prev.name}">${FW.icon("chevron-left", 20, 2)}</span>
        <span class="cl-arrow" style="left:${x0 + w + gap / 2 - 22}px" title="${next.name}">${FW.icon("chevron-right", 20, 2)}</span>
        ${dish("row")}
      </div>`;
  }

  FW.register({
    id: "clay",
    name: "Clay deck",
    purpose: "Agenda",
    role: "main",
    now: "Seven tilted columns, each in a different pastel, cutting the first line off the top of each card. Hours scroll from 14:00, and the chips sit in a plain row at the bottom.",
    current: { week: "current/c-clay-week.png", day: "current/c-clay-day.png" },
    signature: {
      name: "Clay",
      dark: false,
      vars: {
        "--page": "#efe9fa",
        "--card": "#f9f6ff",
        "--cl-highlight": "#ffffff",
        "--card-2": "#e9e2f6",
        "--text": "#221c36",
        "--muted": "#595272",
        "--hairline": "#e2daf2",
        "--hairline-strong": "#cbc0e3",
        "--grid-rule": "#ebe5f6",
        "--shadow-sm": "0 2px 6px rgba(70, 48, 140, 0.10)",
        "--shadow-lg": "0 18px 36px -12px rgba(70, 48, 140, 0.30)",
      },
    },
    variants: {
      A: {
        name: "Soft deck",
        summary: "Seven soft clay cards side by side, each a day from 08:00 to 22:00 with its blocks in the category colours. Today's card is raised and carries the now line. Homework without a time rests in a dish along the bottom. Drawn straight; an option in Settings fans the cards at 3 degrees at most, and the fan settles when the week opens.",
        catalogue: ["Claymorphism, tempered: its inner highlight, soft outer shadow and 20 radius, without the thick borders or a pastel per day", "Soft UI Evolution: softer multi-layer shadows, contrast at 4.5:1 and more"],
        changes: [
          "One surface for every card, from the look; colour only in the blocks, from the category family.",
          "Cards straight by default, so nothing is clipped at a card's top; the fan (3 degrees at most) is an option.",
          "The whole day from 08:00 to 22:00 on every card, with no scrolling.",
          "Today raised above the rest, with the accent date chip and the now line.",
          "Not placed yet as clay chips in a pressed-in dish, with the length on each chip.",
          "Day: one large card of the day with the dish and the day's hours by kind beside it.",
        ],
        render(el, ctx) {
          mono = ctx.look === "terminal";
          if (ctx.view === "day") softDeckDay(el, ctx);
          else softDeckWeek(el, ctx);
        },
      },
      B: {
        name: "Card carousel",
        summary: "One large card per day in a row. Today sits in the middle at full size with its hours and blocks; the days either side peek at 70 %. The arrows beside the card, or the wheel, slide the row one day at a time (240 ms, a fade only under Reduce). Day opens the card in front wider, with the day's hours by kind and what is left today inside it.",
        catalogue: ["Claymorphism, tempered as in A", "Soft UI Evolution", "Carousel pattern: the neighbours show there is more to either side"],
        changes: [
          "One day at a time, large enough to read every block's time and length.",
          "Neighbours at 70 %, laid out smaller rather than shrunk, so their text stays on the type scale.",
          "Round arrows between the cards; the wheel moves the row too.",
          "Not placed yet in the same dish, under the carousel.",
          "Day: the same carousel with the day's card open, adding its hours by kind and what is left today.",
        ],
        render(el, ctx) {
          mono = ctx.look === "terminal";
          carousel(el, ctx, ctx.view === "day");
        },
      },
    },
  });
})();
