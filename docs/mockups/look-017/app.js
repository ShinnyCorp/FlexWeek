// The frame of the 0.17 mock-up: tabs, the design list, the switches, the shared top bar, the picks,
// and the state in the URL's hash, so any screen can be opened or photographed by its address:
//   #tab=designs&design=timeline&variant=B&view=week&look=dark&colours=signature
//   add &bare=1 for the 1280x800 stage alone, at full size.
// Designs register themselves with FW.register (see README.md); this file never draws a design.

(function () {
  const ORDER = ["today", "timeline", "mission", "bento", "retro", "clay", "one", "dial"];
  const LOOKS = [
    ["light", "Light"], ["dark", "Dark"], ["high-contrast", "High contrast"], ["slate", "Slate"],
    ["nocturne", "Nocturne"], ["paper", "Paper"], ["ink", "Ink"], ["terminal", "Terminal"],
    ["poster", "Poster"], ["pastel", "Pastel"],
  ];
  const DARK = new Set(["dark", "high-contrast", "nocturne", "ink", "terminal"]);
  const STAGE = { width: 1280, height: 800, bar: 56 };

  const FW = (window.FW = window.FW || {});
  FW.week = window.FW_WEEK;
  FW.time = window.FW_TIME;
  FW.looks = LOOKS;
  FW.darkLooks = DARK;
  FW.stage = STAGE;
  FW.designs = FW.designs || {};
  FW.register = function (design) {
    FW.designs[design.id] = design;
  };

  // --- small helpers every design may use -------------------------------------------------------

  FW.icon = function (name, size = 16, stroke = 1.75) {
    const inner = (window.FW_ICONS || {})[name] || "";
    return `<svg class="fw-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  };

  FW.el = function (tag, attrs = {}, html = "") {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "style" && typeof value === "object") Object.assign(node.style, value);
      else if (key === "class") node.className = value;
      else node.setAttribute(key, value);
    }
    if (html) node.innerHTML = html;
    return node;
  };

  // --- the shared top bar (plan decision 11) ----------------------------------------------------

  function topBar(ctx) {
    const views = ["Day", "Week", "Month", "My day"];
    const chosen = ctx.role === "day" ? "My day" : ctx.view === "day" ? "Day" : "Week";
    const title = ctx.role === "day" ? FW.week.dayTitle : ctx.view === "day" ? FW.week.dayTitle : FW.week.title;
    const segs = views
      .map((v) => `<span class="seg${v === chosen ? " on" : ""}">${v}</span>`)
      .join("");
    return `
      <div class="fw-bar">
        <div class="fw-bar-left">
          <span class="fw-iconbtn">${FW.icon("chevron-left", 18)}</span>
          <span class="fw-iconbtn">${FW.icon("chevron-right", 18)}</span>
          <span class="fw-btn quiet">Today</span>
          <span class="fw-title">${title}</span>
        </div>
        <div class="fw-bar-right">
          <span class="fw-segs">${segs}</span>
          <span class="fw-add"><span class="main">${FW.icon("plus", 16, 2)} Add</span><span class="more">${FW.icon("chevron-down", 16, 2)}</span></span>
          <span class="fw-btn secondary">Plan my homework</span>
          <span class="fw-btn quiet">More ${FW.icon("chevron-down", 14)}</span>
          <span class="fw-iconbtn">${FW.icon("settings", 18)}</span>
        </div>
      </div>`;
  }
  FW.topBar = topBar;

  // --- state ------------------------------------------------------------------------------------

  function readState() {
    const s = Object.fromEntries(new URLSearchParams(location.hash.slice(1)));
    return {
      tab: s.tab || "designs",
      design: ORDER.includes(s.design) ? s.design : "today",
      variant: ["current", "A", "B"].includes(s.variant) ? s.variant : "A",
      view: s.view === "day" ? "day" : "week",
      look: LOOKS.some(([id]) => id === s.look) ? s.look : "light",
      colours: s.colours === "signature" ? "signature" : "look",
      bare: s.bare === "1",
    };
  }
  let state = readState();
  function go(change) {
    state = { ...state, ...change };
    const out = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (k !== "bare" || v) out.set(k, v === true ? "1" : v);
    history.replaceState(null, "", "#" + out.toString());
    render();
  }
  window.addEventListener("hashchange", () => { state = readState(); render(); });

  const PICKS_KEY = "flexweek-017-picks";
  function picks() {
    try { return JSON.parse(localStorage.getItem(PICKS_KEY) || "{}"); } catch { return {}; }
  }
  function pick(design, value) {
    const p = picks();
    p[design] = value;
    localStorage.setItem(PICKS_KEY, JSON.stringify(p));
    render();
  }

  // --- drawing ------------------------------------------------------------------------------------

  function stageFor(design, variant, view, look, colours) {
    const stage = FW.el("div", { class: `fw-stage look-${look}${DARK.has(look) ? " dark-family" : ""}` });
    stage.style.width = STAGE.width + "px";
    stage.style.height = STAGE.height + "px";
    if (!design) {
      stage.innerHTML = `<div class="fw-empty">Not drawn yet.</div>`;
      return stage;
    }
    if (variant === "current") {
      const file = design.current && (design.current[view] || design.current.week || design.current.day);
      stage.innerHTML = file ? `<img class="fw-current" src="${file}" alt="0.16.0">` : `<div class="fw-empty">No picture.</div>`;
      return stage;
    }
    const option = design.variants && design.variants[variant];
    const ctx = {
      role: design.role || "main",
      view: design.role === "day" ? "myday" : view,
      look,
      dark: DARK.has(look),
      colours,
      week: FW.week,
      time: FW.time,
    };
    if (colours === "signature" && design.signature && design.signature.vars) {
      for (const [k, v] of Object.entries(design.signature.vars)) stage.style.setProperty(k, v);
      if (design.signature.dark) stage.classList.add("dark-family");
    }
    stage.innerHTML = topBar(ctx);
    const content = FW.el("div", { class: `fw-content design-${design.id} variant-${variant}` });
    content.style.height = STAGE.height - STAGE.bar + "px";
    stage.appendChild(content);
    if (option && option.render) {
      try { option.render(content, ctx); } catch (error) { content.innerHTML = `<pre class="fw-error">${error.stack || error}</pre>`; }
    } else {
      content.innerHTML = `<div class="fw-empty">Option ${variant} is not drawn yet.</div>`;
    }
    return stage;
  }
  FW.stageFor = stageFor;

  function scaled(stage, width) {
    const box = FW.el("div", { class: "fw-scaled" });
    const k = width / STAGE.width;
    box.style.width = width + "px";
    box.style.height = STAGE.height * k + "px";
    stage.style.transform = `scale(${k})`;
    stage.style.transformOrigin = "0 0";
    box.appendChild(stage);
    return box;
  }

  function button(label, on, click, extra = "") {
    const b = FW.el("button", { class: `chip${on ? " on" : ""} ${extra}` }, label);
    b.addEventListener("click", click);
    return b;
  }

  function renderDesigns(root) {
    const design = FW.designs[state.design];
    const side = FW.el("nav", { class: "side" });
    side.appendChild(FW.el("h2", {}, "Designs"));
    for (const id of ORDER) {
      const d = FW.designs[id];
      const chosen = picks()[id];
      const item = FW.el("button", { class: `side-item${id === state.design ? " on" : ""}` },
        `<span>${d ? d.name : id}</span><small>${d ? d.purpose || "" : "not loaded"}${chosen ? " · picked " + chosen : ""}</small>`);
      item.addEventListener("click", () => go({ design: id, variant: "A" }));
      side.appendChild(item);
    }
    root.appendChild(side);

    const main = FW.el("section", { class: "main" });
    const controls = FW.el("div", { class: "controls" });
    const variants = FW.el("div", { class: "row" }, "<label>Version</label>");
    variants.appendChild(button("0.16 now", state.variant === "current", () => go({ variant: "current" })));
    for (const v of ["A", "B"]) {
      const name = design && design.variants && design.variants[v] ? design.variants[v].name : "";
      variants.appendChild(button(`${v}${name ? " · " + name : ""}`, state.variant === v, () => go({ variant: v })));
    }
    controls.appendChild(variants);
    if (!design || design.role !== "day") {
      const views = FW.el("div", { class: "row" }, "<label>View</label>");
      for (const v of ["week", "day"]) views.appendChild(button(v === "week" ? "Week" : "Day", state.view === v, () => go({ view: v })));
      controls.appendChild(views);
    }
    const looks = FW.el("div", { class: "row wrap" }, "<label>Look</label>");
    for (const [id, name] of LOOKS) looks.appendChild(button(name, state.look === id, () => go({ look: id })));
    controls.appendChild(looks);
    if (design && design.signature) {
      const colours = FW.el("div", { class: "row" }, "<label>Colours</label>");
      colours.appendChild(button("Match my look", state.colours === "look", () => go({ colours: "look" })));
      colours.appendChild(button(design.signature.name, state.colours === "signature", () => go({ colours: "signature" })));
      controls.appendChild(colours);
    }
    main.appendChild(controls);

    const width = Math.min(1280, root.clientWidth - 560);
    main.appendChild(scaled(stageFor(design, state.variant, state.view, state.look, state.colours), Math.max(width, 640)));
    root.appendChild(main);

    const info = FW.el("aside", { class: "info" });
    const option = design && design.variants && design.variants[state.variant];
    if (state.variant === "current") {
      info.innerHTML = `<h2>${design ? design.name : ""}, as 0.16.0 draws it</h2><p>${design && design.now ? design.now : ""}</p>`;
    } else if (option) {
      info.innerHTML = `<h2>${state.variant}. ${option.name}</h2><p>${option.summary || ""}</p>` +
        (option.catalogue ? `<h3>Shaped by</h3><ul>${option.catalogue.map((c) => `<li>${c}</li>`).join("")}</ul>` : "") +
        (option.changes ? `<h3>What changes</h3><ul>${option.changes.map((c) => `<li>${c}</li>`).join("")}</ul>` : "");
    }
    if (design) {
      const chosen = picks()[design.id];
      const pickRow = FW.el("div", { class: "pick" }, "<h3>Your pick</h3>");
      for (const value of ["A", "B", "Keep as it is"]) {
        pickRow.appendChild(button(value, chosen === value, () => pick(design.id, value), "pick-btn"));
      }
      info.appendChild(pickRow);
    }
    root.appendChild(info);
  }

  function renderLooks(root) {
    const main = FW.el("section", { class: "main full" });
    main.appendChild(FW.el("h2", {}, "Every look on Today's app"));
    main.appendChild(FW.el("p", { class: "note" }, "Each look is a full set of colours, faces and shapes. None replaces your accent. Click one to open it large."));
    const grid = FW.el("div", { class: "looks-grid" });
    const today = FW.designs.today;
    const variant = picks().today === "B" ? "B" : "A";
    for (const [id, name] of LOOKS) {
      const cell = FW.el("button", { class: "look-cell" });
      cell.appendChild(scaled(stageFor(today, variant, "week", id, "look"), 380));
      cell.appendChild(FW.el("span", {}, name));
      cell.addEventListener("click", () => go({ tab: "designs", design: "today", variant, look: id }));
      grid.appendChild(cell);
    }
    main.appendChild(grid);
    root.appendChild(main);
  }

  function renderSystem(root) {
    const main = FW.el("section", { class: "main full" });
    const stage = FW.el("div", { class: `fw-stage system-stage look-${state.look}${DARK.has(state.look) ? " dark-family" : ""}` });
    if (FW.system && FW.system.render) FW.system.render(stage, { look: state.look, dark: DARK.has(state.look) });
    else stage.innerHTML = `<div class="fw-empty">The system sheet is not drawn yet.</div>`;
    const looks = FW.el("div", { class: "row wrap" }, "<label>Look</label>");
    for (const [id, name] of LOOKS) looks.appendChild(button(name, state.look === id, () => go({ look: id })));
    main.appendChild(looks);
    main.appendChild(stage);
    root.appendChild(main);
  }

  function renderPicks(root) {
    const main = FW.el("section", { class: "main full" });
    const p = picks();
    const lines = ORDER.map((id) => `${FW.designs[id] ? FW.designs[id].name : id}: ${p[id] || "not picked"}`);
    main.appendChild(FW.el("h2", {}, "Your picks"));
    main.appendChild(FW.el("p", { class: "note" }, "Copy these and send them back. Pick on each design's page."));
    const text = FW.el("textarea", { class: "picks", readonly: "readonly", rows: "10" });
    text.value = lines.join("\n");
    main.appendChild(text);
    const copy = FW.el("button", { class: "chip on" }, "Copy");
    copy.addEventListener("click", () => { text.select(); navigator.clipboard && navigator.clipboard.writeText(text.value); copy.textContent = "Copied"; });
    main.appendChild(copy);
    root.appendChild(main);
  }

  function render() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    if (state.bare) {
      document.body.classList.add("bare");
      const design = FW.designs[state.design];
      if (state.tab === "system") {
        const stage = FW.el("div", { class: `fw-stage system-stage look-${state.look}${DARK.has(state.look) ? " dark-family" : ""}` });
        if (FW.system && FW.system.render) FW.system.render(stage, { look: state.look, dark: DARK.has(state.look) });
        app.appendChild(stage);
      } else {
        app.appendChild(stageFor(design, state.variant, state.view, state.look, state.colours));
      }
      return;
    }
    document.body.classList.remove("bare");
    const tabs = FW.el("header", { class: "tabs" }, `<strong>FlexWeek 0.17 mock-up</strong>`);
    for (const [id, name] of [["designs", "Designs"], ["looks", "Looks"], ["system", "The system"], ["picks", "Your picks"]]) {
      tabs.appendChild(button(name, state.tab === id, () => go({ tab: id })));
    }
    app.appendChild(tabs);
    const body = FW.el("div", { class: "body" });
    app.appendChild(body);
    ({ designs: renderDesigns, looks: renderLooks, system: renderSystem, picks: renderPicks })[state.tab](body);
  }

  window.addEventListener("resize", () => { if (!state.bare) render(); });
  window.addEventListener("DOMContentLoaded", () => document.fonts.ready.then(render));
})();
