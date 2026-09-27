// Retro desktop, revised for 0.17 (docs/0.17/plan.md, Phase 2). A is Windows 98 drawn faithfully:
// two-pixel bevels, the navy-to-blue title gradient, a pixel face, a taskbar. B is System 7: one
// window with tabs under a menu bar across the screen, one-bit, the accent the only colour.
// Retro keeps its period colours inside its windows (its colourway, "Teal desktop"); under Match my
// look the desktop and the title bars take the look's accent, and B's two bits are the look's card
// and text.

(function () {
  const W = FW.week;
  const T = FW.time;
  const TODAY = W.today;
  const WEEK = { from: 8 * 60, to: 22 * 60 };
  const DAY = { from: 8 * 60, to: 21 * 60 };
  const KEYS = ["class", "assignments", "extra", "exercise", "meals"];

  const sum = (list, f) => list.reduce((n, x) => n + f(x), 0);
  const minutesOn = (day) => sum(T.on(day), (b) => b.end - b.start);
  const top = (r, minute) => ((minute - r.from) / (r.to - r.from)) * 100;
  const tall = (r, minutes) => (minutes / (r.to - r.from)) * 100;
  const book = (size = 12) => FW.icon("book-open", size, 2);
  const unplaced = W.homework.filter((h) => !h.placed);
  const ahead = T.on(TODAY).filter((b) => b.start > W.now);

  // --- the hours, shared by both options (each styles them in its own scope) --------------------

  function block(b, r, wide) {
    const len = b.end - b.start;
    const icon = b.category === "assignments" ? `<span class="rt-block-icon">${book(12)}</span>` : "";
    const time = wide ? `${T.range(b.start, b.end)} · ${T.length(len)}${b.pinned ? " · Pinned" : ""}` : T.clock(b.start);
    return `<div class="rt-block${wide ? " rt-wide" : ""}" data-cat="${b.category}" title="${b.title}, ${T.range(b.start, b.end)}"
      style="top:calc(${top(r, b.start)}% + 1.5px);height:calc(${tall(r, len)}% - 3px)">
      <div class="rt-block-title">${icon}<span class="rt-t">${b.title}</span></div><div class="rt-block-time">${time}</div></div>`;
  }

  // Nothing is cut: a block that overflows puts its time beside the title (wide) or drops it
  // (narrow), keeps its title to one line, shortens it at a word, and at last shows only its edge.
  function fit(root) {
    for (const b of root.querySelectorAll(".rt-block")) {
      const title = b.querySelector(".rt-block-title");
      const text = b.querySelector(".rt-t");
      const over = () => b.scrollHeight > b.clientHeight + 1 || title.scrollWidth > title.clientWidth + 1;
      if (!over()) continue;
      const time = b.querySelector(".rt-block-time");
      if (b.classList.contains("rt-wide")) {
        b.classList.add("rt-one");
        if (over()) time.remove();
      } else {
        time.remove();
        if (over()) b.classList.add("rt-one");
      }
      const words = text.textContent.split(" ");
      while (words.length > 1 && over()) {
        words.pop();
        text.textContent = words.join(" ");
      }
      if (over()) text.textContent = "";
    }
  }
  const fitLater = (el) => setTimeout(() => document.fonts.ready.then(() => fit(el)), 0);

  function hours(days, r, wide) {
    let rules = "";
    let labels = "";
    for (let m = r.from; m <= r.to; m += 60) {
      rules += `<div class="rt-rule" style="top:${top(r, m)}%"></div>`;
      if (Math.abs(m - W.now) >= 25) labels += `<div class="rt-hour" style="top:${top(r, m)}%">${T.clock(m)}</div>`;
    }
    const cols = days
      .map((d) => {
        const now = d === TODAY ? `<div class="rt-now" style="top:${top(r, W.now)}%"></div>` : "";
        return `<div class="rt-col${d === TODAY && days.length > 1 ? " today" : ""}">${T.on(d).map((b) => block(b, r, wide)).join("")}${now}</div>`;
      })
      .join("");
    const tag = days.includes(TODAY) ? `<div class="rt-now-tag" style="top:${top(r, W.now)}%">${T.clock(W.now)}</div>` : "";
    if (days.length > 1 && days.includes(TODAY)) rules += `<div class="rt-now-track" style="top:${top(r, W.now)}%"></div>`;
    return `<div class="rt-hours" style="--rt-cols:${days.length}">
      <div class="rt-gutter">${labels}${tag}</div>
      <div class="rt-cols"><div class="rt-rules">${rules}</div>${cols}</div>
    </div>`;
  }

  function heads(days) {
    return days
      .map((d) => `<span class="rt-head${d === TODAY ? " today" : ""}"><span>${W.days[d].short}</span> <b>${W.days[d].date}</b></span>`)
      .join("");
  }

  function freeSlots(day, r) {
    const out = [];
    let at = W.now;
    for (const b of T.on(day)) {
      if (b.end <= W.now) continue;
      if (b.start - at >= 20) out.push([at, b.start]);
      at = Math.max(at, b.end);
    }
    if (r.to - at >= 20) out.push([at, r.to]);
    return out;
  }

  function byCategory(day) {
    const by = {};
    for (const b of T.on(day)) by[b.category] = (by[b.category] || 0) + b.end - b.start;
    return by;
  }

  // --- A. Windows 98, faithful --------------------------------------------------------------------

  const caps = (help) =>
    `<span class="rt-caps">${help ? `<b class="rt-cap rt-help"><i></i></b>` : `<b class="rt-cap rt-min"><i></i></b><b class="rt-cap rt-max"><i></i></b>`}<b class="rt-cap rt-close"><i></i></b></span>`;

  function win98(cls, pos, icon, title, body, help = false) {
    return `<section class="rt-win ${cls}" style="${pos}">
      <header class="rt-title"><span class="rt-title-icon">${FW.icon(icon, 16, 2)}</span><span class="rt-title-text">${title}</span>${caps(help)}</header>
      ${body}
    </section>`;
  }

  const menu = (items) => `<nav class="rt-menu">${items.map((m) => `<span><u>${m[0]}</u>${m.slice(1)}</span>`).join("")}</nav>`;

  function scrollbar(thumbTop, thumbHeight) {
    return `<div class="rt-sb"><b class="rt-sb-btn rt-up"><i></i></b><div class="rt-sb-track"><b class="rt-sb-thumb" style="top:${thumbTop}%;height:${thumbHeight}%"></b></div><b class="rt-sb-btn rt-down"><i></i></b></div>`;
  }

  function deskIcon(icon, label, on) {
    return `<div class="rt-deskicon${on ? " on" : ""}"><span class="rt-deskicon-art rt-art-${icon}">${FW.icon(icon, 32, 1.5)}</span><span class="rt-deskicon-label">${label}</span></div>`;
  }

  function notepadText() {
    const pad = (s, n) => s + " ".repeat(Math.max(1, n - s.length));
    const rows = W.homework.map((h) => {
      const placed = W.blocks.find((b) => b.homework === h.id);
      const len = h.minutes >= 60 ? `${Math.floor(h.minutes / 60)} h${h.minutes % 60 ? " " + (h.minutes % 60) : ""}` : `${h.minutes} min`;
      const when = placed ? `${W.days[placed.days[0]].short} ${T.clock(placed.start)}` : "not placed yet";
      return pad(h.title, 17) + pad(len, 8) + when;
    });
    return ["Due Sunday 27 September, in 3 days.", "", ...rows, "", "Plan my homework can place the", "last two before Sunday."].join("\n");
  }

  function renderA(el, ctx) {
    const day = ctx.view === "day";
    const days = day ? [TODAY] : [0, 1, 2, 3, 4, 5, 6];
    const r = WEEK;
    const by = byCategory(TODAY);
    const webview = day
      ? `<aside class="rt-webview">
          <div class="rt-wv-title">Thursday</div>
          <div class="rt-wv-rule"></div>
          <p><b>24 September</b><br>${T.length(minutesOn(TODAY))} planned, ${ahead.length} still to come.</p>
          <p class="rt-wv-sub">Your day</p>
          <ul class="rt-wv-list">${KEYS.filter((c) => by[c]).map((c) => `<li><span class="rt-key" data-cat="${c}">${c === "assignments" ? book(10) : ""}</span>${W.categories[c]}<em>${T.length(by[c])}</em></li>`).join("")}</ul>
          <p class="rt-wv-sub">Free from now</p>
          <ul class="rt-wv-list">${freeSlots(TODAY, r).map(([a, b]) => `<li>${T.range(a, b)}<em>${T.length(b - a)}</em></li>`).join("")}</ul>
        </aside>`
      : "";
    const grid = `<div class="rt-field rt-grid">
        <div class="rt-heads"><span class="rt-head-gutter"></span>${heads(days)}<span class="rt-head-sb"></span></div>
        <div class="rt-grid-body">${hours(days, r, day)}${scrollbar(33, 58)}</div>
      </div>`;
    const week = win98(
      "rt-weekwin",
      "left:100px;top:12px;width:776px;height:684px",
      "calendar-days",
      day ? "Week.exe - Thursday 24 September" : "Week.exe - 21 to 27 September",
      `${menu(["File", "Edit", "View", "Homework", "Help"])}
       <div class="rt-weekwin-body${day ? " rt-with-webview" : ""}">${webview}${grid}</div>
       <footer class="rt-status"><span>Ready</span><span>${day ? `${ahead.length} still to come` : "Thursday 24, 15:40"}</span><span>${unplaced.length} homework not placed yet</span></footer>`
    );
    const notepad = win98(
      "rt-notepad",
      "left:888px;top:12px;width:380px;height:332px",
      "file-text",
      "deadlines.txt - Notepad",
      `${menu(["File", "Edit", "Search", "Help"])}
       <div class="rt-field rt-note"><pre>${notepadText()}</pre>${scrollbar(0, 100)}</div>`
    );
    const n = W.next;
    const dialog = win98(
      "rt-dialog",
      "left:888px;top:360px;width:380px;height:212px",
      "bell",
      "Up next",
      `<div class="rt-dialog-body">
        <span class="rt-dialog-art">${FW.icon("clock", 32, 1.5)}</span>
        <div class="rt-dialog-text">
          <div class="rt-dialog-head">${n.title}</div>
          <div>starts at ${T.clock(n.start)}, in ${n.inMinutes} min.</div>
          <div class="rt-dialog-then">Then Dinner at 18:30.</div>
        </div>
      </div>
      <div class="rt-dialog-buttons"><span class="rt-btn rt-default"><span>OK</span></span><span class="rt-btn"><span><span><u>M</u>y day</span></span></span></div>`,
      true
    );
    const icons = `<div class="rt-icons">
      ${deskIcon("calendar-days", "Week.exe", true)}
      ${deskIcon("file-text", "deadlines.txt")}
      ${deskIcon("folder", "Homework")}
      ${deskIcon("timer", "Focus timer")}
      ${deskIcon("trash", "Recycle Bin")}
    </div>`;
    const taskbar = `<footer class="rt-taskbar">
      <span class="rt-btn rt-start"><span>${FW.icon("calendar-days", 16, 2)}<b>Start</b></span></span>
      <span class="rt-task-sep"></span>
      <span class="rt-btn rt-task on"><span>${FW.icon("calendar-days", 14, 2)}Week.exe</span></span>
      <span class="rt-btn rt-task"><span>${FW.icon("file-text", 14, 2)}deadlines.txt</span></span>
      <span class="rt-btn rt-task"><span>${FW.icon("bell", 14, 2)}Up next</span></span>
      <span class="rt-tray">${FW.icon("bell", 14, 2)}<span>15:40</span></span>
    </footer>`;
    el.innerHTML = `<div class="rt98"><div class="rt-desk">${icons}${week}${notepad}${dialog}</div>${taskbar}</div>`;
    fitLater(el);
  }

  // --- B. System 7 --------------------------------------------------------------------------------

  function renderB(el, ctx) {
    const day = ctx.view === "day";
    const by = byCategory(TODAY);
    const legend = KEYS.map((c) => `<span class="r7-legend-item"><span class="r7-pat" data-cat="${c}"></span>${W.categories[c]}</span>`).join("");
    const n = W.next;
    const pane = day
      ? `<div class="r7-pane r7-daypane">
          <div class="r7-hours-box">${hours([TODAY], DAY, true)}</div>
          <aside class="r7-info-card">
            <div class="r7-info-head">Today</div>
            <div class="r7-info-rule"></div>
            <div class="r7-info-label">Next</div>
            <div class="r7-info-next">${n.title}</div>
            <div>${T.clock(n.start)}, in ${n.inMinutes} min. Then Dinner at 18:30.</div>
            <div class="r7-info-label">Your day, ${T.length(minutesOn(TODAY))}</div>
            <div class="r7-stack">${KEYS.filter((c) => by[c]).map((c) => `<span class="r7-pat" data-cat="${c}" style="flex:${by[c]}"></span>`).join("")}</div>
            <ul class="r7-rows">${KEYS.filter((c) => by[c]).map((c) => `<li><span class="r7-pat" data-cat="${c}"></span>${W.categories[c]}${c === "assignments" ? book(12) : ""}<em>${T.length(by[c])}</em></li>`).join("")}</ul>
            <div class="r7-info-label">Free from now</div>
            <ul class="r7-rows">${freeSlots(TODAY, WEEK).map(([a, b]) => `<li>${T.range(a, b)}<em>${T.length(b - a)}</em></li>`).join("")}</ul>
            <div class="r7-buttons"><span class="r7-btn r7-default">My day</span></div>
          </aside>
        </div>`
      : `<div class="r7-pane">
          <div class="r7-heads"><span class="r7-head-gutter"></span>${heads([0, 1, 2, 3, 4, 5, 6])}</div>
          <div class="r7-hours-box">${hours([0, 1, 2, 3, 4, 5, 6], WEEK, false)}</div>
        </div>`;
    el.innerHTML = `<div class="rt7">
      <nav class="r7-menubar">
        <span class="r7-logo">${FW.icon("calendar-days", 16, 2)}</span>
        <span class="r7-menu">File</span><span class="r7-menu">Edit</span><span class="r7-menu">View</span><span class="r7-menu">Special</span>
        <span class="r7-menubar-right"><span>Thu 15:40</span><span class="r7-logo">${FW.icon("calendar", 16, 2)}</span></span>
      </nav>
      <div class="r7-desk">
        <section class="r7-win">
          <header class="r7-title"><span class="r7-box r7-close"></span><span class="r7-title-text">FlexWeek</span><span class="r7-box r7-zoom"></span></header>
          <div class="r7-tabs">
            <span class="r7-tab${day ? "" : " on"}">Week</span>
            <span class="r7-tab">Deadlines <span class="r7-count">5</span></span>
            <span class="r7-tab${day ? " on" : ""}">Up next</span>
            <span class="r7-tabs-fill"></span>
          </div>
          <div class="r7-body">
            ${pane}
            <div class="r7-sb"><b class="r7-arrow r7-up"></b><div class="r7-sb-track"><b class="r7-sb-thumb"></b></div><b class="r7-arrow r7-down"></b></div>
          </div>
          <footer class="r7-foot">
            <span class="r7-legend">${legend}</span>
            <span class="r7-foot-next">Next: <b>${n.title}</b>, ${T.clock(n.start)} · 5 due Sunday, ${unplaced.length} not placed</span>
            <span class="r7-grow"></span>
          </footer>
        </section>
        <div class="r7-deskicon r7-hd"><span class="r7-art">${FW.icon("hard-drive", 32, 1.5)}</span><span class="r7-label">FlexWeek HD</span></div>
        <div class="r7-deskicon r7-trash"><span class="r7-art">${FW.icon("trash", 32, 1.5)}</span><span class="r7-label">Trash</span></div>
      </div>
    </div>`;
    fitLater(el);
  }

  FW.register({
    id: "retro",
    name: "Retro desktop",
    purpose: "Dashboard",
    role: "main",
    now: "A Windows 95 pastiche drawn in Inter: a teal desktop with Week.exe, deadlines.txt and an Up next box, grey blocks with a coloured edge, and a taskbar with a clock. The bevels are one pixel and the title bars flat navy; the blocks cut their names (\"Robotics …\", \"Math wor…\").",
    current: { week: "current/c-retro-week.png", day: "current/c-retro-day.png" },
    signature: {
      name: "Teal desktop",
      dark: false,
      vars: {
        "--rt-sig-desk": "#008080",
        "--rt-sig-title-a": "#000080",
        "--rt-sig-title-b": "#1084d0",
        "--rt-sig-title-ink": "#ffffff",
        "--rt-sig-accent": "#008080",
        "--rt-sig-accent-ink": "#ffffff",
        "--rt-sig-paper": "#ffffff",
        "--rt-sig-ink": "#000000",
      },
    },
    variants: {
      A: {
        name: "Windows 98, faithful",
        summary: "Windows 98 as it was drawn: two-pixel bevels lit from the top left, the gradient title bars, a pixel face, a taskbar with Start, the open windows and a clock. Week.exe holds the week, deadlines.txt the homework in Notepad, and Up next is a dialog. Under Match my look the desktop and title bars take your accent.",
        catalogue: ["Pixel Retro pairing: Pixelify Sans (OFL) for the interface, VT323 (OFL) for Notepad", "Flat Design's \"no gradients\" does not apply here by design", "High contrast follows Windows 98's own High Contrast Black scheme"],
        changes: [
          "Two-pixel bevels, light top left and dark bottom right, on every window, button, field and the taskbar; square corners throughout.",
          "The navy-to-blue title gradient with the window's icon and minimise, maximise and close drawn as pixels.",
          "Pixelify Sans instead of Inter, and deadlines.txt in VT323 as a real Notepad file.",
          "Desktop icons on the left, a Start button, a button per window and a clock at 15:40.",
          "Blocks in the category family with a 3-pixel edge inside the white field; titles wrap and shorten at a word, never cut.",
          "The now line is marked with a Windows 98 tooltip; Day adds the folder web view pane with the day's summary.",
        ],
        render: renderA,
      },
      B: {
        name: "System 7",
        summary: "One Macintosh window under a menu bar across the screen (File, Edit, View, Special), with tabs for Week, Deadlines and Up next. One bit, two colours: the look's card and text, with the accent the only colour. Categories are told apart by MacPaint-style patterns, not colour.",
        catalogue: ["System 7's window: striped title bar, close and zoom boxes, a one-pixel drop shadow", "Pixelify Sans standing in for Chicago", "Patterns as the category cue (Color Only rule), the accent for today, the now line and the chosen tab"],
        changes: [
          "One window instead of three, with tabs; the menu bar runs across the top of the screen with a clock.",
          "Two colours only, taken from the look, so it reads in Dark and High contrast as well as Light.",
          "Each category is a pattern on the block's edge, with a key along the window's foot.",
          "The week gets the window's whole width, so most titles fit on one line; the rest wrap or shorten at a word, never mid-word.",
          "The Trash sits in the corner and the disk at the top right, as on a Mac.",
          "Day opens the Up next tab: today's hours with a Get Info card beside them (what is next, the day's patterns and the free time left).",
        ],
        render: renderB,
      },
    },
  });
})();
