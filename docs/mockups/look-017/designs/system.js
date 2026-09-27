// "The system" tab: the Phase 1 system of docs/0.17/plan.md (decisions 1 to 10), the controls of
// decisions 11, 20 and 22, and the motion levels of decisions 28 and 33, drawn in the chosen look.
// Values that change with the look (colours, radii, shadows, faces) are read from the page once the
// sheet is on it, so each look describes itself.

(function () {
  const W = FW.week;
  // desktop/native/look.py ACCENT_COLORS, and Blue, the default (decision 1): light, dark.
  const ACCENTS = [
    ["Blue", "#3d6fc4", "#7fa8ff"],
    ["Sky", "#0369a1", "#38bdf8"],
    ["Sea", "#0f766e", "#2dd4bf"],
    ["Gold", "#a16207", "#eab308"],
    ["Sand", "#926a2a", "#e7d5a3"],
  ];
  const SURFACES = [
    ["--page", "Page"], ["--card", "Card"], ["--card-2", "Raised"], ["--hairline", "Hairline"],
    ["--text", "Text"], ["--muted", "Muted"], ["--accent", "Accent"], ["--danger", "Danger"],
  ];
  const CATEGORIES = ["class", "assignments", "study", "exercise", "extra", "meals", "sleep", "free"];
  // Fade through (decision 28): the old page out in 90 ms, the new in in 120 ms, OutCubic; Day, Week
  // and Month add a 12-pixel slide. More stretches both; Reduce keeps the fade and drops the slide;
  // Off swaps at once (decision 33).
  const LEVELS = {
    normal: { name: "Normal", out: 90, in: 120, slide: 12, text: "Fades, and views slide 12 px." },
    more: { name: "More", out: 130, in: 175, slide: 16, text: "Longer, and views slide 16 px." },
    reduce: { name: "Reduce", out: 90, in: 120, slide: 0, text: "Fades only. Paper starts here." },
    off: { name: "Off", out: 0, in: 0, slide: 0, text: "Nothing moves." },
  };
  const DEMO = [
    { cat: "extra", title: "Soccer practice", when: "16:00 · in 20 min" },
    { cat: "meals", title: "Dinner", when: "18:30 · in 2 h 50 min" },
    { cat: "assignments", title: "History essay", when: "19:00 · in 3 h 20 min", book: true },
  ];
  const EASE = "cubic-bezier(0.33, 1, 0.68, 1)";

  const book = (size = 16) => FW.icon("book-open", size, 2);
  const card = (cls, title, note, body) => `
    <section class="sy-card ${cls}">
      <h2>${title}${note ? `<small>${note}</small>` : ""}</h2>
      ${body}
    </section>`;

  function header(ctx) {
    const look = (FW.looks.find(([id]) => id === ctx.look) || ["", ctx.look])[1];
    return `
      <header class="sy-head">
        <div>
          <h1>The system</h1>
          <p>One accent, neutral surfaces, one type scale, two weights, six steps, three radii, two shadows.</p>
        </div>
        <span class="sy-lookname">Shown in <b>${look}</b></span>
      </header>`;
  }

  function typeCard() {
    const rows = [
      ["Display", "28 pt · 700", "display", `25:00<small>numbers only</small>`],
      ["Title", "20 pt · 600", "title", W.title],
      ["Heading", "15 pt · 600", "heading", "Soccer practice"],
      ["Body", "13 pt · 400", "text", "Drag one onto the week to place it."],
      ["Caption", "11 pt · 400, 600", "caption", `<b>Not placed yet</b><span>16:00 · in 20 min</span>`],
    ];
    return card("sy-span7", "Type", "Sizes at Normal; Small and Large scale all five", `
      ${rows.map(([name, spec, cls, sample]) => `
        <div class="sy-type-row">
          <div class="sy-type-meta"><b>${name}</b><span>${spec}</span></div>
          <div class="sy-sample ${cls}">${sample}</div>
        </div>`).join("")}
      <div class="sy-weights">
        <span class="w" style="font-weight:var(--w-regular)">Aa</span><span class="l">Regular 400</span>
        <span class="w" style="font-weight:var(--w-strong)">Aa</span><span class="l">Strong 600</span>
        <span class="faces" data-faces></span>
      </div>`);
  }

  function colourCard(ctx) {
    const swatches = SURFACES.map(([v, name]) => `
      <div class="sy-sw"><div class="box" style="background:var(${v})"></div>
        <div class="nm">${name}</div><div class="hex" data-hex></div></div>`).join("");
    const accents = ACCENTS.map(([name, light, dark], i) => {
      const value = ctx.dark ? dark : light;
      return `<div class="sy-acc${i === 0 ? " on" : ""}" style="--sw:${value}">
        <span class="dot">${i === 0 ? FW.icon("check", 16, 2.5) : ""}</span>
        <span class="nm">${name}</span><span class="hex">${value}</span></div>`;
    }).join("");
    return card("sy-span5", "Colour", "Colour comes from categories", `
      <div class="sy-swatches">${swatches}</div>
      <div class="sy-divide"></div>
      <div class="sy-sub">${ctx.look === "high-contrast" ? "Accent, chosen once; High contrast uses its yellow for 7:1" : "Accent, chosen once: Blue by default"}</div>
      <div class="sy-accents">${accents}</div>
      <div class="sy-red"><i></i>Red means a problem, or deleting.</div>`);
  }

  function categoriesCard() {
    const tiles = CATEGORIES.map((c) => `
      <div class="sy-cat" data-cat="${c}">
        <div class="nm">${c === "assignments" ? book(15) : ""}${W.categories[c]}</div>
        <div class="mk"><i></i>${c === "assignments" ? "Edge and book" : c === "free" ? "No hue" : "Edge and dot"}</div>
      </div>`).join("");
    return card("sy-span7", "Categories", "One family: fills at one lightness, marks at another", `
      <div class="sy-cats">${tiles}</div>
      <p class="sy-note">Fills at OKLCH L 0.92, C 0.045; marks at L 0.62, C 0.14. On dark looks the mark sinks into the card.</p>`);
  }

  function shapeCard() {
    const steps = [4, 8, 12, 16, 24, 32].map((s) => `<div class="sy-step"><i style="width:${s}px;height:${s}px"></i><span>${s}</span></div>`).join("");
    const radii = [["--r-control", "Controls"], ["--r-card", "Cards"], ["--r-sheet", "Sheets"], ["--r-pill", "Chips"]]
      .map(([v, name]) => `<div class="sy-radius"><i style="border-top-left-radius:var(${v})"></i><span class="nm">${name}</span><span class="v" data-radius="${v}"></span></div>`).join("");
    return card("sy-span5", "Spacing and radii", "", `
      <div class="sy-sub">Six steps, in pixels</div>
      <div class="sy-steps">${steps}</div>
      <div class="sy-divide"></div>
      <div class="sy-sub">Three radii and the pill</div>
      <div class="sy-radii">${radii}</div>`);
  }

  function buttonsCard() {
    const states = ["Rest", "Hover", "Pressed", "Focus", "Disabled"];
    const kinds = [
      ["primary", "Primary", `${FW.icon("plus", 16, 2)}Add`],
      ["secondary", "Secondary", "Preview"],
      ["quiet", "Quiet", `More${FW.icon("chevron-down", 14)}`],
    ];
    const cells = kinds.map(([cls, name, label]) => `<span class="rl">${name}</span>` + states.map((s) =>
      `<button class="sy-btn ${cls} ${s.toLowerCase()}" tabindex="-1"${s === "Disabled" ? " disabled" : ""}>${label}</button>`).join("")).join("");
    return card("", "Buttons", "Hover 6 %, pressed 10 %, focus ring 40 %, disabled 40 %", `
      <div class="sy-matrix"><span></span>${states.map((s) => `<span class="hd">${s}</span>`).join("")}${cells}</div>`);
  }

  function inputsCard() {
    return card("", "Inputs and chips", "", `
      <div class="sy-inputs">
        <div>
          <div class="sy-sub">Segmented control</div>
          <div class="sy-segs"><span>Day</span><span class="on">Week</span><span>Month</span><span>My day</span></div>
        </div>
        <div>
          <div class="sy-sub">Switch</div>
          <div class="sy-switches">
            <span class="sy-switch on"><i></i>On</span>
            <span class="sy-switch"><i></i>Off</span>
            <span class="sy-switch on focus"><i></i>Focus</span>
          </div>
        </div>
        <div>
          <div class="sy-sub">Text field, empty and typing</div>
          <div class="sy-fields">
            <div class="box ph">Add a title</div>
            <div class="box focus">History essay<span class="caret"></span></div>
          </div>
        </div>
        <div>
          <div class="sy-sub">Chip and flags</div>
          <div class="sy-chips">
            <span class="sy-chip" data-cat="assignments">${book(16)}Science poster<span class="len">1 h 30 min</span></span>
            <span class="sy-tag cat" data-cat="assignments">${book(13)}Homework</span>
            <span class="sy-tag due">Due Sun</span>
          </div>
        </div>
      </div>`);
  }

  function toastCard() {
    return card("", "Toast", "Bottom right, over the side panel", `
      <div class="sy-toast"><span>Planned 2 homework blocks.</span>
        <span class="undo">${FW.icon("undo-2", 14, 2)}Undo</span><span class="x">${FW.icon("x", 16)}</span></div>`);
  }

  function menuCard() {
    return card("sy-menucard", "Menu", "Icons, a separator, red for deleting", `
      <div class="sy-menu">
        <div class="it">${FW.icon("pencil", 16)}Edit<span class="k">Enter</span></div>
        <div class="it hover">${FW.icon("copy", 16)}Duplicate<span class="k">Ctrl+D</span></div>
        <div class="it">${FW.icon("timer", 16)}Start a focus timer<span class="k">F</span></div>
        <div class="sep"></div>
        <div class="it del">${FW.icon("trash", 16)}Delete<span class="k">Del</span></div>
        <div class="it del">${book(16)}Delete homework</div>
      </div>`);
  }

  function motionCard() {
    const levels = Object.entries(LEVELS).map(([id, l]) => `
      <button class="sy-level${id === "normal" ? " on" : ""}" data-level="${id}">
        <b>${l.name}<small>${l.out ? `${l.out} + ${l.in} ms` : "at once"}</small></b><p>${l.text}</p></button>`).join("");
    return card("sy-span8", "Motion", "Four levels, chosen in Settings; nothing loops", `
      <div class="sy-motion-body">
        <div class="sy-levels">${levels}</div>
        <div class="sy-demo">
          <div class="sy-demo-stage"><div class="sy-demo-card"></div></div>
          <div class="sy-demo-row">
            <button class="sy-btn primary sy-run">Next card${FW.icon("chevron-right", 16, 2)}</button>
            <span class="sy-timing"></span>
          </div>
          <div class="sy-rm"></div>
        </div>
      </div>`);
  }

  function shadowsCard() {
    return card("sy-span4", "Two shadows", "", `
      <div class="sy-elev">
        <div style="box-shadow:var(--shadow-sm)"><div class="nm">Small</div><div class="v" data-shadow="--shadow-sm"></div></div>
        <div style="box-shadow:var(--shadow-lg)"><div class="nm">Large</div><div class="v" data-shadow="--shadow-lg"></div></div>
        <p class="use">Cards, the chosen segment, the toast</p>
        <p class="use">Menus, sheets and Ctrl+K</p>
      </div>`);
  }

  // --- values read from the page ------------------------------------------------------------------

  function toHex(css) {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.clearRect(0, 0, 1, 1);
    g.fillStyle = css;
    g.fillRect(0, 0, 1, 1);
    const [r, gr, b, a] = g.getImageData(0, 0, 1, 1).data;
    const hex = "#" + [r, gr, b].map((n) => n.toString(16).padStart(2, "0")).join("");
    return a < 250 ? `${hex} at ${Math.round((a / 255) * 100)} %` : hex;
  }

  function describeShadow(value) {
    const v = value.trim();
    if (!v || v === "none") return "None in this look";
    const px = (v.match(/-?[\d.]+px|(^|\s)0(?=\s)/g) || []).map((x) => parseFloat(x));
    const alpha = (v.match(/rgba?\([^)]*,\s*([\d.]+)\)/) || [])[1];
    if (px.length >= 3 && px[2] === 0 && (px[0] || px[1])) return `Offset ${px[0]}, ${px[1]}, no blur`;
    if (px.length >= 4 && !px[0] && !px[1] && !px[2]) return `A ${px[3]}-pixel ring, no blur`;
    return `0 ${px[1]} ${px[2]}${alpha ? ` · ${Math.round(parseFloat(alpha) * 100)} %` : ""}`;
  }

  function fillValues(stage) {
    const cs = getComputedStyle(stage);
    for (const el of stage.querySelectorAll("[data-hex]")) {
      el.textContent = toHex(getComputedStyle(el.closest(".sy-sw").querySelector(".box")).backgroundColor);
    }
    for (const el of stage.querySelectorAll("[data-radius]")) {
      const px = parseFloat(cs.getPropertyValue(el.dataset.radius));
      el.textContent = px >= 999 ? "Pill" : px === 0 ? "Square here" : `${px} px`;
    }
    for (const el of stage.querySelectorAll("[data-shadow]")) el.textContent = describeShadow(cs.getPropertyValue(el.dataset.shadow));
    const face = (v) => cs.getPropertyValue(v).split(",")[0].replace(/["']/g, "").trim();
    const head = face("--font-head");
    const text = face("--font-body");
    for (const el of stage.querySelectorAll("[data-faces]")) {
      el.innerHTML = head === text ? `Set in <b>${text}</b>` : `Headings in <b>${head}</b>, text in <b>${text}</b>`;
    }
  }

  // --- the fade-through demonstration: one click, one change, never a loop --------------------------

  function motion(stage) {
    const demo = stage.querySelector(".sy-demo-card");
    const run = stage.querySelector(".sy-run");
    const timing = stage.querySelector(".sy-timing");
    const note = stage.querySelector(".sy-rm");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let level = "normal";
    let index = 0;
    let busy = false;

    const draw = () => {
      const d = DEMO[index];
      demo.dataset.cat = d.cat;
      demo.innerHTML = `<span class="t">${d.book ? book(15) : ""}${d.title}</span><span class="w">${d.when}</span>`;
    };
    const show = () => {
      const l = LEVELS[level];
      for (const el of stage.querySelectorAll(".sy-level")) el.classList.toggle("on", el.dataset.level === level);
      const slide = reduced ? 0 : l.slide;
      timing.textContent = l.out ? `${l.out} + ${l.in} ms${slide ? `, ${slide} px slide` : ", fade only"}` : "Swapped at once";
      note.textContent = reduced && l.slide
        ? "Your computer asks for reduced motion, so the slide is left out, as the app will."
        : "Pick a level, then press Next card.";
    };
    run.addEventListener("click", () => {
      if (busy) return;
      const l = LEVELS[level];
      const slide = reduced ? 0 : l.slide;
      const next = () => { index = (index + 1) % DEMO.length; draw(); };
      if (!l.out) { next(); return; }
      busy = true;
      demo.style.transition = `opacity ${l.out}ms ${EASE}, transform ${l.out}ms ${EASE}`;
      demo.style.opacity = "0";
      demo.style.transform = `translateX(${-slide}px)`;
      setTimeout(() => {
        next();
        demo.style.transition = "none";
        demo.style.transform = `translateX(${slide}px)`;
        void demo.offsetWidth;
        demo.style.transition = `opacity ${l.in}ms ${EASE}, transform ${l.in}ms ${EASE}`;
        demo.style.opacity = "1";
        demo.style.transform = "none";
        setTimeout(() => {
          // At rest again: drop the inline styles so nothing is left mid-way if a frame was missed.
          demo.style.transition = demo.style.opacity = demo.style.transform = "";
          busy = false;
        }, l.in + 20);
      }, l.out);
    });
    for (const el of stage.querySelectorAll(".sy-level")) {
      el.addEventListener("click", () => { level = el.dataset.level; show(); });
    }
    draw();
    show();
  }

  function whenAttached(el, fn, tries = 0) {
    if (el.isConnected) {
      fn();
      document.fonts.ready.then(() => el.isConnected && fn());
    } else if (tries < 100) setTimeout(() => whenAttached(el, fn, tries + 1), 0);
  }

  FW.system = {
    render(stage, ctx) {
      stage.innerHTML = `
        <div class="sy">
          ${header(ctx)}
          ${typeCard()}
          ${colourCard(ctx)}
          ${categoriesCard()}
          ${shapeCard()}
          <div class="sy-stack sy-span7">${buttonsCard()}${inputsCard()}</div>
          <div class="sy-stack sy-span5">${toastCard()}${menuCard()}</div>
          ${motionCard()}
          ${shadowsCard()}
        </div>`;
      motion(stage);
      whenAttached(stage, () => fillValues(stage));
    },
  };
})();
