// Day dial (Clock): My day as a clock of the day's blocks. Option A is the whole day as a 24-hour
// ring, the day's list beside it and the week's small dials under it. Option B draws only the next
// twelve hours as a large arc, with the whole day as a small ring beside it. Both are SVG.

(function () {
  const W = FW.week;
  const T = FW.time;
  const DAY = W.today;
  const today = T.on(DAY);
  const next = today.find((b) => b.start >= W.now);

  const rad = (a) => (a * Math.PI) / 180;
  const pt = (cx, cy, r, a) => [cx + r * Math.sin(rad(a)), cy - r * Math.cos(rad(a))];
  const f = (n) => Math.round(n * 100) / 100;

  // An annular sector between radii r0 and r1, from angle a0 to a1 (degrees clockwise from 12).
  function sector(cx, cy, r0, r1, a0, a1) {
    const large = a1 - a0 > 180 ? 1 : 0;
    const [x0, y0] = pt(cx, cy, r1, a0);
    const [x1, y1] = pt(cx, cy, r1, a1);
    const [x2, y2] = pt(cx, cy, r0, a1);
    const [x3, y3] = pt(cx, cy, r0, a0);
    return `M${f(x0)} ${f(y0)}A${r1} ${r1} 0 ${large} 1 ${f(x1)} ${f(y1)}L${f(x2)} ${f(y2)}A${r0} ${r0} 0 ${large} 0 ${f(x3)} ${f(y3)}Z`;
  }

  // The day from `from` to `to` in minutes (`to` may pass midnight into the next day) as a run of
  // spans: the blocks, and the free time between them.
  function spans(day, from, to) {
    const list = T.on(day).concat(
      to > 1440 ? T.on((day + 1) % 7).map((b) => ({ ...b, start: b.start + 1440, end: b.end + 1440 })) : [],
    );
    const out = [];
    let t = from;
    for (const b of list) {
      const s = Math.max(b.start, from);
      const e = Math.min(b.end, to);
      if (e <= s) continue;
      if (s > t) out.push({ free: true, start: t, end: s });
      out.push({ ...b, start: s, end: e });
      t = e;
    }
    if (t < to) out.push({ free: true, start: t, end: to });
    return out;
  }

  function book(x, y, size, cls) {
    return `<svg class="${cls}" x="${f(x - size / 2)}" y="${f(y - size / 2)}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${window.FW_ICONS["book-open"]}</svg>`;
  }

  // The ring's paths: each span a sector, a gap of `gap` degrees between neighbours. Blocks that
  // are over take the category's fill, the rest its mark; the free span holding now is split
  // there, its elapsed part fainter, with no gap.
  function ring({ cx, cy, r0, r1, angle, from, to, day, gap, now, icons = 0 }) {
    let out = "";
    for (const s of spans(day, from, to)) {
      const a0 = angle(s.start) + gap / 2;
      const a1 = angle(s.end) - gap / 2;
      if (a1 <= a0) continue;
      if (s.free) {
        if (now > s.start && now < s.end) {
          out += `<path class="dl-free past" d="${sector(cx, cy, r0, r1, a0, angle(now))}"/>`;
          out += `<path class="dl-free" d="${sector(cx, cy, r0, r1, angle(now), a1)}"/>`;
        } else {
          out += `<path class="dl-free${s.end <= now ? " past" : ""}" d="${sector(cx, cy, r0, r1, a0, a1)}"/>`;
        }
        continue;
      }
      const past = s.end <= now;
      out += `<path class="dl-seg${past ? " past" : ""}" data-cat="${s.category}" d="${sector(cx, cy, r0, r1, a0, a1)}"><title>${s.title}</title></path>`;
      if (icons && s.category === "assignments") {
        const [x, y] = pt(cx, cy, (r0 + r1) / 2, (a0 + a1) / 2);
        out += book(x, y, icons, `dl-book${past ? " past" : ""}`);
      }
    }
    return out;
  }

  // The hand, from the hub to radius r. Small dials get a smaller hub and no ring in it.
  function hand(cx, cy, r, a, hub = 8) {
    const [x, y] = pt(cx, cy, r, a);
    const inner = hub >= 8 ? `<circle class="dl-hub-in" cx="${cx}" cy="${cy}" r="3"/>` : "";
    return `<line class="dl-hand${hub < 8 ? " thin" : ""}" x1="${cx}" y1="${cy}" x2="${f(x)}" y2="${f(y)}"/><circle class="dl-hub" cx="${cx}" cy="${cy}" r="${hub}"/>${inner}`;
  }

  // A whole day, midnight at the bottom and noon at the top.
  const angle24 = (m) => (m / 1440) * 360 - 180;

  // --- Shared: the Next card and the day's list --------------------------------------------------

  function nextCard() {
    return `<section class="dl-card dl-next">
        <div class="dl-next-top">
          <span class="dl-label">Up next</span>
          <span class="dl-in">in ${W.next.inMinutes} min</span>
        </div>
        <h2 class="dl-next-title" data-cat="${next.category}"><span class="dl-dot"></span>${next.title}</h2>
        <p class="dl-next-sub"><span>${T.range(next.start, next.end)} · ${T.length(next.end - next.start)}</span> · <span>then ${W.next.then}</span></p>
        <div class="dl-actions">
          <span class="dl-btn primary">${FW.icon("clock", 16, 2)}Running late</span>
          <span class="dl-btn">${FW.icon("chevron-left", 16, 2)}Back to planning</span>
        </div>
      </section>`;
  }

  function dayList() {
    const rows = today.map((b) => {
      const past = b.end <= W.now;
      const isNext = b === next;
      const homework = b.category === "assignments";
      return `<li class="${past ? "past" : ""}${isNext ? " next" : ""}" data-cat="${b.category}">
          <span class="dl-lt">${T.clock(b.start)}</span>
          <span class="dl-lm"></span>
          <span class="dl-ln">${homework ? FW.icon("book-open", 14, 2) : ""}<span>${b.title}</span>${past ? `<span class="dl-tag">${FW.icon("check", 12, 2.2)}Done</span>` : ""}${b.pinned ? `<span class="dl-tag">Pinned</span>` : ""}</span>
          <span class="dl-ll">${T.length(b.end - b.start)}</span>
        </li>`;
    }).join("");
    const last = today[today.length - 1];
    const unplaced = W.homework.filter((h) => !h.placed);
    return `<section class="dl-card dl-list">
        <header><span class="dl-label">Today</span><span class="dl-count">${today.length} things</span></header>
        <ol>
          ${rows}
          <li class="dl-none"><span class="dl-lt">${T.clock(last.end)}</span><span class="dl-lm"></span><span class="dl-ln"><span>Nothing else today</span></span><span class="dl-ll"></span></li>
        </ol>
        <p class="dl-unplaced">${FW.icon("book-open", 16, 2)}<span><b>${unplaced.length} homework not placed yet</b><span class="dl-un-sep"> · </span><span class="dl-un-list">${unplaced.map((h) => h.title).join(", ")}</span></span></p>
      </section>`;
  }

  // --- A. Dial ---------------------------------------------------------------------------------

  function bigDial() {
    const Wd = 600;
    const H = 588;
    const cx = 300;
    const cy = 292;
    const r1 = 232;
    const r0 = 190;
    let ticks = "";
    for (let h = 0; h < 24; h++) {
      const a = angle24(h * 60);
      const long = h % 6 === 0;
      const [x0, y0] = pt(cx, cy, r1 + 7, a);
      const [x1, y1] = pt(cx, cy, r1 + (long ? 17 : 12), a);
      ticks += `<line class="dl-tick${long ? " long" : ""}" x1="${f(x0)}" y1="${f(y0)}" x2="${f(x1)}" y2="${f(y1)}"/>`;
      if (h % 2 === 0) {
        const [lx, ly] = pt(cx, cy, r1 + 32, a);
        ticks += `<text class="dl-hour" x="${f(lx)}" y="${f(ly)}">${String(h).padStart(2, "0")}</text>`;
      }
    }
    const planned = today.filter((b) => b.end > W.now).reduce((sum, b) => sum + (b.end - Math.max(b.start, W.now)), 0);
    const free = 22 * 60 - W.now - planned;
    return `<svg class="dl-svg" width="${Wd}" height="${H}" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="Today as a 24-hour dial">
        ${ring({ cx, cy, r0, r1, angle: angle24, from: 0, to: 1440, day: DAY, gap: 2, now: W.now, icons: 18 })}
        ${ticks}
        ${hand(cx, cy, r0 - 8, angle24(W.now))}
        <text class="dl-time" x="${cx}" y="${cy + 74}">${T.clock(W.now)}</text>
        <text class="dl-note" x="${cx}" y="${cy + 108}">${T.length(free)} free until 22:00</text>
      </svg>`;
  }

  function miniDial(day, size) {
    const c = size / 2;
    const r1 = c - 2;
    const r0 = r1 - 8;
    const now = day < DAY ? 1440 : day > DAY ? -1 : W.now;
    const handHere = day === DAY ? hand(c, c, r0 - 4, angle24(W.now), 3) : "";
    return `<svg class="dl-mini" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
        ${ring({ cx: c, cy: c, r0, r1, angle: angle24, from: 0, to: 1440, day, gap: 3, now })}
        ${handHere}
      </svg>`;
  }

  function weekStrip() {
    const cells = W.days.map((d) => `<div class="dl-wd${d.index === DAY ? " today" : ""}">
        ${miniDial(d.index, 60)}
        <span class="dl-wl">${d.short} <b>${d.date}</b></span>
      </div>`).join("");
    return `<section class="dl-card dl-week">${cells}</section>`;
  }

  function dialA(el) {
    el.innerHTML = `<div class="dl-root dl-a">
        <div class="dl-face">${bigDial()}</div>
        <div class="dl-side">
          ${nextCard()}
          ${dayList()}
        </div>
        ${weekStrip()}
      </div>`;
  }

  // --- B. Next twelve hours --------------------------------------------------------------------

  function arc12() {
    const Wd = 752;
    const H = 744;
    const cx = 380;
    const cy = 452;
    const r1 = 312;
    const r0 = 256;
    const FROM = 15 * 60;
    const TO = FROM + 12 * 60;
    const A0 = -120;
    const per = 240 / 12;
    const angle = (m) => A0 + ((m - FROM) / 60) * per;
    let ticks = "";
    for (let m = FROM; m <= TO; m += 30) {
      const a = angle(m);
      const hour = m % 60 === 0;
      const [x0, y0] = pt(cx, cy, r1 + 7, a);
      const [x1, y1] = pt(cx, cy, r1 + (hour ? 16 : 11), a);
      ticks += `<line class="dl-tick${hour ? " long" : ""}" x1="${f(x0)}" y1="${f(y0)}" x2="${f(x1)}" y2="${f(y1)}"/>`;
      if (hour) {
        const [lx, ly] = pt(cx, cy, r1 + 32, a);
        ticks += `<text class="dl-hour" x="${f(lx)}" y="${f(ly)}">${String((m / 60) % 24).padStart(2, "0")}</text>`;
      }
    }
    // Each block named inside the arc, level with its middle.
    const labels = spans(DAY, FROM, TO).filter((s) => !s.free).map((s) => {
      const a = angle((s.start + s.end) / 2);
      const [x, y] = pt(cx, cy, r0 - 20, a);
      const anchor = a < -8 ? "start" : a > 8 ? "end" : "middle";
      return `<text class="dl-blabel" x="${f(x)}" y="${f(y)}" text-anchor="${anchor}"><tspan class="dl-bname">${s.title}</tspan><tspan class="dl-btime" dx="8">${T.clock(s.start)}</tspan></text>`;
    }).join("");
    const [sx, sy] = pt(cx, cy, r1 + 32, angle(FROM));
    return `<svg class="dl-svg" width="${Wd}" height="${H}" viewBox="0 0 ${Wd} ${H}" role="img" aria-label="The next twelve hours as an arc">
        ${ring({ cx, cy, r0, r1, angle, from: FROM, to: TO, day: DAY, gap: 1.5, now: W.now, icons: 20 })}
        ${ticks}
        ${labels}
        ${hand(cx, cy, r0 - 10, angle(W.now))}
        <text class="dl-note" x="${cx}" y="${cy - 132}">Next twelve hours</text>
        <text class="dl-time" x="${cx}" y="${cy - 66}">${T.clock(W.now)}</text>
      </svg>`;
  }

  function wholeDay() {
    const size = 112;
    const c = size / 2;
    const r1 = 44;
    const r0 = 32;
    const a0 = angle24(15 * 60);
    const a1 = a0 + 180;
    const [x0, y0] = pt(c, c, r1 + 7, a0 + 1);
    const [x1, y1] = pt(c, c, r1 + 7, a1 - 1);
    const planned = today.reduce((sum, b) => sum + (b.end - b.start), 0);
    return `<section class="dl-card dl-whole">
        <svg class="dl-small" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
          ${ring({ cx: c, cy: c, r0, r1, angle: angle24, from: 0, to: 1440, day: DAY, gap: 3, now: W.now })}
          <path class="dl-window" d="M${f(x0)} ${f(y0)}A${r1 + 7} ${r1 + 7} 0 0 1 ${f(x1)} ${f(y1)}"/>
          ${hand(c, c, r0 - 5, angle24(W.now), 4)}
        </svg>
        <div class="dl-whole-text">
          <span class="dl-whole-t">Whole day</span>
          <span class="dl-whole-s">${today.length} things · ${T.length(planned)} planned</span>
          <span class="dl-whole-k"><span class="dl-key"></span>The twelve hours on the left</span>
        </div>
      </section>`;
  }

  function dialB(el) {
    el.innerHTML = `<div class="dl-root dl-b">
        <div class="dl-face">${arc12()}</div>
        <div class="dl-side">
          ${wholeDay()}
          ${nextCard()}
          ${dayList()}
        </div>
      </div>`;
  }

  FW.register({
    id: "dial",
    name: "Day dial",
    purpose: "Clock",
    role: "day",
    now: "A navy dial of the day with the hand running past the ring and across \"22\", the time sitting on the hand's hub, \"UP NEXT\" and \"TODAY, HOUR BY HOUR\" in capitals, pill buttons, the past row struck through and \"2 tasks not placed yet\".",
    current: { myday: "current/d-myday-dial.png", week: "current/d-myday-dial.png" },
    signature: {
      name: "Night",
      dark: true,
      vars: {
        "--page": "#0b0f1d",
        "--card": "#141a2e",
        "--card-2": "#1b2238",
        "--text": "#e7eaf6",
        "--muted": "#9ea6c4",
        "--hairline": "#242b45",
        "--hairline-strong": "#343c5e",
        "--grid-rule": "rgba(231, 234, 246, 0.08)",
      },
    },
    variants: {
      A: {
        name: "Dial",
        summary: "The whole day as a 24-hour ring, noon at the top and midnight at the bottom, each block a segment in its category's colour with a 2-degree gap between neighbours; what is over is paler. Hour ticks and labels sit outside the ring, the hand stops at its inner edge, and the time sits under the hub (above it around midnight, when the hand points down). Beside it the Next card and the day's list, with times and lengths in columns. The week's small dials run along the bottom. Light in light looks; \"Night\" is 0.16's navy, refined.",
        catalogue: ["Soft UI Evolution: soft surfaces, clear contrast, rounded rectangles", "Swiss Modernism 2.0: aligned columns, one type scale"],
        changes: [
          "The hand stops at the ring's inner edge; the time moves under the hub.",
          "Hour ticks and labels outside the ring, so no number sits under a segment or the hand.",
          "Sentence case throughout: \"Up next\", \"Today\".",
          "The list in columns: start time, title, length right-aligned; the past row marked Done, not struck through.",
          "\"Nothing else today\" once, and \"2 homework not placed yet\" with the book icon.",
          "Rounded-rectangle buttons instead of pills.",
          "The week's small dials labelled, today's with its hand; past days paler.",
        ],
        render(el) {
          dialA(el);
        },
      },
      B: {
        name: "Next twelve hours",
        summary: "Only the next twelve hours, 15:00 to 03:00, as an arc nearly twice the size of A's ring, each block along it named at its middle and the hand at now. The window always starts at the current hour, so the hand stays low on the left and the time sits in the open bowl above the hub. The whole day stays in view as a small ring beside it, its twelve hours marked in the accent. The same Next card and list.",
        catalogue: ["Soft UI Evolution", "Data-dense clock faces: more room per hour where the day is still ahead"],
        changes: [
          "About twice the room per hour for what is still ahead; the morning drops out of the big arc.",
          "Blocks named on the arc itself, not only by colour.",
          "The whole day as a small ring beside it, the arc's twelve hours marked.",
          "The same Next card and list as A.",
        ],
        render(el) {
          dialB(el);
        },
      },
    },
  });
})();
