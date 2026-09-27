// One thing (Focus): My day as the one thing that comes next. Option A is a poster: the next
// thing's name at display size and nothing else competing. Option B is a countdown ring, which
// merges One thing and the dial. Both follow the look ("Match my look"), or wear "Poster", the
// 0.16 black with the app's accent instead of orange. The top bar stays the app's.

(function () {
  const W = FW.week;
  const T = FW.time;
  const today = T.on(W.today);
  const next = today.find((b) => b.start >= W.now);
  const then = today.filter((b) => b.start > next.start);
  const leftToday = today.filter((b) => b.end > W.now).length;

  function top() {
    return `<div class="one-top">
        <span>Now ${T.clock(W.now)}</span>
        <span>${leftToday} things left today</span>
      </div>`;
  }

  function actions() {
    return `<div class="one-actions">
        <span class="one-btn primary">${FW.icon("clock", 18, 2)}Running late</span>
        <span class="one-btn">${FW.icon("chevron-left", 18, 2)}Back to planning</span>
      </div>`;
  }

  // --- A. Poster ------------------------------------------------------------------------------

  // The day as a thin segmented bar from 06:00 to 24:00, the now mark on it.
  function dayBar() {
    const FROM = 6 * 60;
    const TO = 24 * 60;
    const at = (m) => ((m - FROM) / (TO - FROM)) * 100;
    const segs = today.map((b) => {
      const past = b.end <= W.now ? " past" : "";
      return `<span class="one-seg${past}" data-cat="${b.category}" style="left:${at(b.start)}%;width:calc(${at(b.end) - at(b.start)}% - 2px)" title="${b.title}"></span>`;
    }).join("");
    let ticks = "";
    for (let h = 6; h <= 24; h += 3) {
      ticks += `<span class="one-tick" style="left:${at(h * 60)}%">${String(h).padStart(2, "0")}:00</span>`;
    }
    return `<div class="one-daybar">
        <div class="one-track">
          <span class="one-done" style="width:${at(W.now)}%"></span>
          ${segs}
          <span class="one-nowmark" style="left:${at(W.now)}%"></span>
        </div>
        <div class="one-ticks">${ticks}</div>
      </div>`;
  }

  function poster(el) {
    const thenText = then.map((b) => `${b.title} ${T.clock(b.start)}`).join(", ");
    el.innerHTML = `<div class="one-root one-a">
        ${top()}
        <main class="one-main">
          <p class="one-kicker">Up next</p>
          <h1 class="one-title">${next.title}</h1>
          <p class="one-when">${T.clock(next.start)} · in ${W.next.inMinutes} min</p>
          ${actions()}
        </main>
        <footer class="one-foot">
          ${dayBar()}
          <div class="one-footrow">
            <p class="one-then"><span>Then:</span> ${thenText}</p>
            <p class="one-keys"><kbd>Space</kbd> What comes after <kbd>B</kbd> Back to planning</p>
          </div>
        </footer>
      </div>`;
  }

  // --- B. Countdown ---------------------------------------------------------------------------

  // The ring is the next hour, drawn like a kitchen timer: the accent arc is the time left, from
  // the top clockwise, and it shrinks back to the top as the minutes go.
  function ring() {
    const S = 440;
    const c = S / 2;
    const R = 170;
    const left = W.next.inMinutes;
    const circ = 2 * Math.PI * R;
    const arc = (left / 60) * circ;
    let ticks = "";
    for (let m = 0; m < 60; m += 5) {
      const a = (m / 60) * 2 * Math.PI;
      const major = m % 15 === 0;
      const r0 = R + 16;
      const r1 = R + (major ? 26 : 22);
      ticks += `<line class="one-rt${major ? " major" : ""}" x1="${c + r0 * Math.sin(a)}" y1="${c - r0 * Math.cos(a)}" x2="${c + r1 * Math.sin(a)}" y2="${c - r1 * Math.cos(a)}"/>`;
      if (major) {
        const rl = R + 40;
        ticks += `<text class="one-rl" x="${c + rl * Math.sin(a)}" y="${c - rl * Math.cos(a)}">${m}</text>`;
      }
    }
    return `<svg class="one-ring" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}" aria-hidden="true">
        <circle class="one-rtrack" cx="${c}" cy="${c}" r="${R}"/>
        <circle class="one-rarc" cx="${c}" cy="${c}" r="${R}" stroke-dasharray="${arc} ${circ}" transform="rotate(-90 ${c} ${c})"/>
        ${ticks}
      </svg>`;
  }

  function countdown(el) {
    const rows = then.map((b) => `<li data-cat="${b.category}">
        <span class="one-lt">${T.clock(b.start)}</span>
        <span class="one-ld"></span>
        <span class="one-ln">${b.category === "assignments" ? FW.icon("book-open", 14, 2) : ""}${b.title}</span>
        <span class="one-ll">${T.length(b.end - b.start)}</span>
      </li>`).join("");
    el.innerHTML = `<div class="one-root one-b">
        ${top()}
        <div class="one-dial">
          ${ring()}
          <div class="one-centre">
            <p class="one-kicker">Up next</p>
            <p class="one-name">${next.title}</p>
            <p class="one-count"><b>${W.next.inMinutes}</b><span>min</span></p>
            <p class="one-at">${T.range(next.start, next.end)}</p>
          </div>
        </div>
        <section class="one-list">
          <p class="one-kicker">Then</p>
          <ul>${rows}</ul>
        </section>
        ${actions()}
      </div>`;
  }

  FW.register({
    id: "one",
    name: "One thing",
    purpose: "Focus",
    role: "day",
    now: "My day as a black page in orange and capitals: \"UP NEXT\", \"SOCCER PRACTICE\" at 96 pt, \"16:00 · IN 20 MIN\", two boxed buttons and a grey day bar. It takes over the top bar and the window's frame.",
    current: { myday: "current/d-myday-one.png", week: "current/d-myday-one.png" },
    signature: {
      name: "Poster",
      dark: true,
      vars: {
        "--page": "#000000",
        "--card": "#141414",
        "--card-2": "#1c1c1c",
        "--text": "#ffffff",
        "--muted": "#a3a3a3",
        "--hairline": "#262626",
        "--hairline-strong": "#3d3d3d",
        "--grid-rule": "rgba(255, 255, 255, 0.08)",
      },
    },
    variants: {
      A: {
        name: "Poster",
        summary: "The next thing's name at display size, in sentence case, with its time and how long until it in the accent, and nothing else competing. Two plain buttons, then a thin bar of the whole day with the now mark. White in light looks and dark in dark ones; \"Poster\" is the 0.16 black with your accent instead of orange. Capitals stay an option.",
        catalogue: ["Exaggerated Minimalism: oversized type, tight tracking, one accent, extreme negative space", "Swiss Modernism 2.0: one grid, clear hierarchy"],
        changes: [
          "Sentence case instead of capitals everywhere.",
          "Your accent instead of orange; the top bar and the window's frame stay the app's.",
          "Follows your look; the black is the \"Poster\" colourway.",
          "Rounded buttons: Running late filled, Back to planning outlined.",
          "The day bar as thin category segments, the past faded, the now mark in the accent.",
          "Keys shown as keycaps.",
        ],
        render(el) {
          poster(el);
        },
      },
      B: {
        name: "Countdown",
        summary: "One large ring counting down to the next thing. The ring is the next hour, like a kitchen timer: the accent arc is the 20 minutes left and shrinks back to the top as they pass, with the minutes in the middle as a display number. What comes after is listed under it. One thing and the dial in one, and the same ring the focus screen uses (decision 19).",
        catalogue: ["Exaggerated Minimalism: one display number, one accent", "Soft UI Evolution: the ring's soft track"],
        changes: [
          "A countdown you can read from across the room, as a ring and a number.",
          "What comes after listed under it, with times and lengths in columns.",
          "The same ring as the focus screen, so both screens look like one app.",
          "Follows your look; \"Poster\" as the colourway.",
        ],
        render(el) {
          countdown(el);
        },
      },
    },
  });
})();
