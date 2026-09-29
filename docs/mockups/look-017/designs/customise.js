// Customise: a look as a starting point that people can change and save as their own
// (docs/0.17/plan.md, "Customise (Jonathan, 27 September)"). Two options on the same controls:
// A opens them in place in Settings' Appearance under a small live preview; B is a full-window
// look editor with Today's app (the Rail) at full size. The controls stay in the look being
// customised as it was, so a bad colour never hides them; the preview takes every change at once.
//
// The page's state is in the address (`cu=`, a list of key:value), so any state can be opened or
// photographed: open:<group> (or all, customise, none), at:<group> scrolls to it, editor:off shows
// B's Settings, system:on, from:<saved look id>, name:<text>, save:<name> saves the current changes
// under that name, saveas:<name> shows A's Save as field, error:json|shape shows Import's error,
// rename:<id>, fix:<row id>|all presses Fix, zoom:actual shows B's preview at its real size, and
// any value: accent:sea, text:#888888, cat.assignments:40, corners:4, and so on.

(function () {
  const W = FW.week;
  const STORE = "flexweek-017-custom-looks";
  const LOOK_IDS = FW.looks.map(([id]) => id);
  const LOOK_NAME = Object.fromEntries(FW.looks);
  const MORE = LOOK_IDS.filter((id) => id !== "light" && id !== "dark");
  const CATS = ["class", "assignments", "study", "exercise", "extra", "meals", "sleep", "free"];
  // Decision 9's hues; Free has none (C 0.01), so its slider starts where its grey leans.
  const HUES = { class: 255, assignments: 25, study: 295, exercise: 150, extra: 205, meals: 60, sleep: 275, free: 250 };
  // desktop/native/look.py ACCENT_COLORS and Blue (decision 1): id, name, light, dark.
  const ACCENTS = [
    ["blue", "Blue", "#3d6fc4", "#7fa8ff"],
    ["sky", "Sky", "#0369a1", "#38bdf8"],
    ["sea", "Sea", "#0f766e", "#2dd4bf"],
    ["gold", "Gold", "#a16207", "#eab308"],
    ["sand", "Sand", "#926a2a", "#e7d5a3"],
  ];
  const YELLOW = ["yellow", "Yellow", "#ffd400", "#ffd400"];
  // Decisions 28 and 33, as the system sheet shows them.
  const LEVELS = {
    normal: { out: 90, in: 120, slide: 12, text: "Fades, and views slide 12 px." },
    more: { out: 130, in: 175, slide: 16, text: "Longer, and views slide 16 px." },
    reduce: { out: 90, in: 120, slide: 0, text: "Fades only. Paper starts here." },
    off: { out: 0, in: 0, slide: 0, text: "Nothing moves." },
  };
  const EASE = "cubic-bezier(0.33, 1, 0.68, 1)";
  // Every knob as the ten looks set it (looks.css and the plan's "The looks").
  const KNOBS = {
    spacing: "comfortable", shadows: "soft", body: "sans", head: "sans", size: 100, blocks: "edge", edge: 3,
    times: true, lengths: true, hours: "faint", highlight: true, now: "accent", motion: "normal",
  };
  const LOOK_KNOBS = {
    "high-contrast": { shadows: "none", blocks: "outline", edge: 4, highlight: false },
    paper: { shadows: "none", head: "serif", motion: "reduce" },
    ink: { shadows: "none", head: "serif" },
    terminal: { body: "mono", head: "mono" },
    poster: { shadows: "bold", edge: 4 },
  };
  const SOFT = {
    light: ["0 1px 3px rgba(16, 24, 40, 0.08)", "0 12px 32px rgba(16, 24, 40, 0.16)"],
    dark: ["0 1px 3px rgba(0, 0, 0, 0.4)", "0 12px 32px rgba(0, 0, 0, 0.5)"],
  };
  const SCALE = [["caption", 11], ["body", 13], ["heading", 15], ["title", 20], ["display", 28]];

  // --- the values a look can change, and how each is read from an address or a file ---------------

  const COLOUR_KEYS = ["page", "card", "text", "lines", "muted"];
  const CHOICES = {
    spacing: ["comfortable", "compact"], shadows: ["none", "soft", "bold"], body: ["sans", "serif", "mono"],
    head: ["sans", "serif", "mono"], blocks: ["edge", "filled", "outline"], hours: ["none", "faint", "clear"],
    now: ["accent", "text"], motion: ["normal", "more", "reduce", "off"],
  };
  const RANGES = { corners: [0, 16], size: [90, 130], edge: [2, 6] };
  const SWITCHES = ["times", "lengths", "highlight"];
  const KEYS = ["accent", ...COLOUR_KEYS, ...CATS.map((c) => "cat." + c), "corners", "spacing", "shadows",
    "body", "head", "size", "blocks", "edge", "times", "lengths", "hours", "highlight", "now", "motion"];

  function hexOf(raw) {
    if (typeof raw !== "string") return undefined;
    let s = raw.trim().replace(/^#/, "").toLowerCase();
    if (/^[0-9a-f]{3}$/.test(s)) s = s.split("").map((c) => c + c).join("");
    return /^[0-9a-f]{6}$/.test(s) ? "#" + s : undefined;
  }

  // One value, checked: the normal form, or undefined if it is not a value this key takes.
  function clean(key, raw) {
    if (key === "accent") {
      if (typeof raw === "string" && ACCENTS.concat([YELLOW]).some(([id]) => id === raw)) return raw;
      return hexOf(raw);
    }
    if (COLOUR_KEYS.includes(key)) return hexOf(raw);
    if (key.startsWith("cat.")) {
      // A number is a hue (so "320" is not the hex #332200); anything else must be a colour.
      if (!CATS.includes(key.slice(4))) return undefined;
      const n = typeof raw === "number" ? raw : typeof raw === "string" && /^\s*-?\d+(\.\d+)?\s*$/.test(raw) ? Number(raw) : NaN;
      if (Number.isFinite(n)) return ((Math.round(n) % 360) + 360) % 360;
      return hexOf(raw);
    }
    if (CHOICES[key]) return CHOICES[key].includes(raw) ? raw : undefined;
    if (RANGES[key]) {
      const n = typeof raw === "number" ? raw : typeof raw === "string" && raw.trim() !== "" ? Number(raw) : NaN;
      if (!Number.isFinite(n)) return undefined;
      return Math.min(RANGES[key][1], Math.max(RANGES[key][0], Math.round(n)));
    }
    if (SWITCHES.includes(key)) {
      if (raw === true || raw === "on" || raw === "true") return true;
      if (raw === false || raw === "off" || raw === "false") return false;
    }
    return undefined;
  }

  function cleanAll(changes) {
    const over = {};
    if (!changes || typeof changes !== "object" || Array.isArray(changes)) return over;
    for (const key of KEYS) {
      if (!(key in changes)) continue;
      const value = clean(key, changes[key]);
      if (value !== undefined) over[key] = value;
    }
    return over;
  }

  // --- colour: sRGB, OKLab and OKLCH, and WCAG contrast ---------------------------------------------

  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const delin = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
  const clamp01 = (v) => Math.min(1, Math.max(0, v));

  function toLab([r, g, b]) {
    const R = lin(r / 255), G = lin(g / 255), B = lin(b / 255);
    const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
    const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
    const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
    return [
      0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
      1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
      0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
    ];
  }
  function labToLinear([L, a, b]) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    return [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ];
  }
  const fromLab = (lab) => labToLinear(lab).map((v) => 255 * clamp01(delin(clamp01(v))));
  const lchToLab = ([L, C, H]) => [L, C * Math.cos((H * Math.PI) / 180), C * Math.sin((H * Math.PI) / 180)];
  function toLch(rgb) {
    const [L, a, b] = toLab(rgb);
    return [L, Math.hypot(a, b), ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360];
  }
  // OKLCH to sRGB, keeping lightness and hue and giving up chroma until the colour exists.
  function fromLch(L, C, H) {
    const fits = (c) => labToLinear(lchToLab([L, c, H])).every((v) => v >= -1e-4 && v <= 1 + 1e-4);
    if (!fits(C)) {
      let lo = 0, hi = C;
      for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid; }
      C = lo;
    }
    return fromLab(lchToLab([L, C, H]));
  }
  const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const hexFrom = (rgb) => "#" + rgb.map((v) => Math.round(clamp01(v / 255) * 255).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, t) => { const x = toLab(a), y = toLab(b); return fromLab(x.map((v, i) => v * t + y[i] * (1 - t))); };
  const lum = ([r, g, b]) => 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255);
  function contrast(a, b) {
    const x = lum(a), y = lum(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  const ratioText = (r) => (Math.floor(r * 10) / 10).toFixed(1);
  const over8 = (fg, bg) => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3]));

  // A computed colour as the browser gives it: rgb(), oklch(), oklab() or color(srgb).
  function parseCss(text) {
    const s = String(text).trim();
    const num = (x, scale = 1) => { const v = parseFloat(x); if (Number.isNaN(v)) return 0; return x.endsWith("%") ? (v / 100) * scale : v; };
    const alphaOf = (x) => (x === undefined ? 1 : num(x.trim(), 1));
    let m;
    if ((m = s.match(/^rgba?\(([^)]*)\)$/))) {
      const p = m[1].split(/[\s,/]+/).filter(Boolean);
      return [num(p[0], 255), num(p[1], 255), num(p[2], 255), alphaOf(p[3])];
    }
    if ((m = s.match(/^(oklch|oklab)\(([^)]*)\)$/))) {
      const [main, alpha] = m[2].split("/");
      const p = main.trim().split(/\s+/);
      const lab = m[1] === "oklch"
        ? lchToLab([num(p[0], 1), num(p[1], 0.4), num(p[2])])
        : [num(p[0], 1), num(p[1], 0.4), num(p[2], 0.4)];
      return [...fromLab(lab), alphaOf(alpha)];
    }
    if ((m = s.match(/^color\(srgb ([^)]*)\)$/))) {
      const [main, alpha] = m[1].split("/");
      const p = main.trim().split(/\s+/);
      return [num(p[0], 1) * 255, num(p[1], 1) * 255, num(p[2], 1) * 255, alphaOf(alpha)];
    }
    const hex = hexOf(s);
    if (hex) return [...rgbOf(hex), 1];
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.fillStyle = s;
    g.fillRect(0, 0, 1, 1);
    const [r, gr, b, a] = g.getImageData(0, 0, 1, 1).data;
    return [r, gr, b, a / 255];
  }

  // The ink that reads best on an accent: white, or the dark look's ink.
  function inkFor(hex) {
    const rgb = rgbOf(hex);
    return contrast([255, 255, 255], rgb) >= contrast([11, 18, 36], rgb) ? "#ffffff" : "#0b1224";
  }
  const accentsFor = (base) => (base === "high-contrast" ? [YELLOW, ...ACCENTS] : ACCENTS);
  function accentHex(value, dark) {
    const swatch = ACCENTS.concat([YELLOW]).find(([id]) => id === value);
    return swatch ? swatch[dark ? 3 : 2] : value;
  }
  // An exact category colour is the block's fill; its edge is the same hue at the family's mark
  // lightness, with enough chroma to show unless the colour is a grey.
  function markFor(hex, markL) {
    const [, C, H] = toLch(rgbOf(hex));
    return hexFrom(fromLch(markL, C < 0.03 ? C : Math.max(C, 0.1), H));
  }

  // --- a look with its changes, painted onto a stage ------------------------------------------------

  function knobs(base, over) {
    return { ...KNOBS, ...(LOOK_KNOBS[base] || {}), ...over };
  }

  // Sets the look's classes and the changed variables on `el` (a .fw-stage). Everything the rest of
  // the mock-up draws follows from these, so the preview is Today's app itself, not a copy.
  function paint(el, base, over, extra = "") {
    const dark = FW.darkLooks.has(base);
    const k = knobs(base, over);
    const cls = ["fw-stage", "cu-stage", "look-" + base];
    if (dark) cls.push("dark-family");
    if (over.blocks !== undefined || over.edge !== undefined || over.shadows !== undefined) cls.push("cu-blocks-" + k.blocks);
    if (k.shadows === "bold") cls.push("cu-bold");
    if (over.hours === "none" || over.hours === "clear") cls.push("cu-hours-" + over.hours);
    if (over.highlight !== undefined) cls.push(over.highlight ? "cu-today-on" : "cu-today-off");
    if (!k.times) cls.push("cu-no-times");
    if (!k.lengths) cls.push("cu-no-lengths");
    if (k.now === "text") cls.push("cu-now-text");
    if (extra) cls.push(extra);
    el.className = cls.join(" ");
    for (const p of el._cuVars || []) el.style.removeProperty(p);

    const v = {};
    if (over.accent !== undefined) {
      const accent = accentHex(over.accent, dark);
      v["--accent"] = accent;
      v["--accent-ink"] = inkFor(accent);
    }
    if (over.page) v["--page"] = over.page;
    if (over.card) v["--card"] = over.card;
    if (over.text) v["--text"] = over.text;
    if (over.lines) v["--hairline"] = over.lines;
    // Four colours set, the rest follow: muted text and raised cards from text and card, strong
    // lines from lines. A Fix on muted text keeps its own colour until text or card changes.
    if (over.text || over.card || over.lines || over.muted) {
      const b = baseInfo(base);
      const text = over.text ? rgbOf(over.text) : b.text;
      const card = over.card ? rgbOf(over.card) : b.card;
      if (over.text || over.card || over.muted) v["--muted"] = over.muted || hexFrom(mix(text, card, 0.66));
      if (over.text || over.card) v["--card-2"] = hexFrom(mix(text, card, 0.05));
      if (over.lines) v["--hairline-strong"] = hexFrom(mix(text, rgbOf(over.lines), 0.12));
    }
    for (const c of CATS) {
      const o = over["cat." + c];
      if (typeof o === "number") {
        // A hue on the family's own lightness and chroma, so it reads by construction; dark looks
        // sink the mark into the card as looks.css does.
        v[`--c-${c}-mark`] = `oklch(var(--mark-l) var(--mark-c) ${o})`;
        if (!dark) v[`--c-${c}-fill`] = `oklch(var(--fill-l) var(--fill-c) ${o})`;
      } else if (typeof o === "string") {
        v[`--c-${c}-fill`] = o;
        v[`--c-${c}-mark`] = markFor(o, baseInfo(base).markL);
      }
    }
    if (over.corners !== undefined) {
      v["--r-card"] = over.corners + "px";
      v["--r-control"] = Math.round(over.corners * 0.6) + "px";
      v["--r-sheet"] = Math.min(16, Math.round(over.corners * 1.6)) + "px";
    }
    if (k.spacing === "compact") Object.assign(v, { "--s2": "6px", "--s3": "8px", "--s4": "12px", "--s5": "16px", "--s6": "24px" });
    if (over.shadows !== undefined) {
      const s = over.shadows === "none" ? ["none", "none"]
        : over.shadows === "bold" ? ["3px 3px 0 var(--text)", "6px 6px 0 var(--text)"]
        : SOFT[dark ? "dark" : "light"];
      v["--shadow-sm"] = s[0];
      v["--shadow-lg"] = s[1];
    }
    if (over.body) v["--font-body"] = `var(--font-${over.body})`;
    if (over.head) v["--font-head"] = `var(--font-${over.head})`;
    if (over.size !== undefined && over.size !== 100) {
      for (const [name, pt] of SCALE) v[`--t-${name}`] = `${+((pt * over.size) / 100).toFixed(2)}pt`;
      // The mock-up's Rail has fixed heights; these let them grow with the type (customise.css).
      v["--cu-k"] = String(over.size / 100);
      v["--cu-bk"] = String(Math.min(over.size, 110) / 100);
      if (over.size > 100) cls.push("cu-bigtext");
      el.className = cls.join(" ");
    }
    v["--cu-edge"] = k.edge + "px";
    for (const [name, value] of Object.entries(v)) el.style.setProperty(name, value);
    el._cuVars = Object.keys(v);
  }

  // The colours a look with its changes resolves to, read from a hidden stage painted like the
  // preview, as RGB; see-through lines are laid over the card they sit on.
  function measure(base, over) {
    const stage = document.createElement("div");
    paint(stage, base, over);
    Object.assign(stage.style, { position: "fixed", left: "-4000px", top: "0", width: "8px", height: "8px", visibility: "hidden" });
    const probe = document.createElement("i");
    stage.appendChild(probe);
    document.body.appendChild(stage);
    const read = (name) => { probe.style.color = `var(${name})`; return parseCss(getComputedStyle(probe).color); };
    const flat = (c, under) => (c[3] >= 0.999 ? c.slice(0, 3) : over8(c, under));
    const page = flat(read("--page"), [255, 255, 255]);
    const card = flat(read("--card"), page);
    const out = {
      page, card,
      text: flat(read("--text"), card),
      muted: flat(read("--muted"), card),
      lines: flat(read("--hairline"), card),
      accent: flat(read("--accent"), card),
      accentInk: flat(read("--accent-ink"), card),
      ink: flat(read("--block-ink"), card),
      fills: {},
    };
    for (const c of CATS) out.fills[c] = flat(read(`--c-${c}-fill`), card);
    const cs = getComputedStyle(stage);
    out.corners = parseFloat(cs.getPropertyValue("--r-card")) || 0;
    out.markL = parseFloat(cs.getPropertyValue("--mark-l")) || 0.62;
    stage.remove();
    return out;
  }
  const baseCache = {};
  const baseInfo = (base) => baseCache[base] || (baseCache[base] = measure(base, {}));

  // --- the readability check ------------------------------------------------------------------------

  // The smallest move of a colour's OKLCH lightness, either way, that gives 4.5:1 against every
  // colour in `groups[0]`; if no lightness does, against `groups[1]`, and so on. Text sits on the
  // page, the cards and every block, so its Fix tries all of them first.
  function moveLightness(fg, ...groups) {
    const [L, C, H] = toLch(fg);
    const worst = (rgb, bgs) => Math.min(...bgs.map((bg) => contrast(rgb, bg)));
    for (const bgs of groups) {
      for (let step = 0.005; step <= 1.0001; step += 0.005) {
        for (const dir of [-1, 1]) {
          const l = L + dir * step;
          if (l < 0 || l > 1) continue;
          const rgb = rgbOf(hexFrom(fromLch(l, C, H)));
          if (worst(rgb, bgs) >= 4.55) return hexFrom(rgb);
        }
      }
    }
    const last = groups[groups.length - 1];
    const ends = [[0, 0, 0], [255, 255, 255]];
    return hexFrom(worst(ends[0], last) >= worst(ends[1], last) ? ends[0] : ends[1]);
  }
  // An accent too middling for either ink: move it until white or the dark ink reads on it.
  function moveAccent(accent) {
    const [L, C, H] = toLch(accent);
    for (let step = 0.005; step <= 1.0001; step += 0.005) {
      for (const dir of [-1, 1]) {
        const l = L + dir * step;
        if (l < 0 || l > 1) continue;
        const hex = hexFrom(fromLch(l, C, H));
        if (contrast(rgbOf(inkFor(hex)), rgbOf(hex)) >= 4.55) return hex;
      }
    }
    return hexFrom(accent);
  }

  // Each pair under 4.5:1, with the change that fixes it. Outlined blocks sit on the card, so their
  // text is the card's; three or more block colours that fail are one row.
  function checks(base, over, R) {
    const rows = [];
    const add = (id, label, fg, bg, fix) => {
      const r = contrast(fg, bg);
      if (r < 4.5) rows.push({ id, text: `${label} is ${ratioText(r)}:1`, fg, bg, fix });
    };
    const onBlocks = knobs(base, over).blocks !== "outline";
    const surfaces = [R.page, R.card];
    // Text is moved to read on the blocks too, except a block whose colour sits on the other side
    // of mid-grey from the page (a bright block on a dark look): that one gets its own Fix.
    const darkSide = (c) => lum(c) < 0.18;
    const alike = CATS.map((c) => R.fills[c]).filter((f) => darkSide(f) === darkSide(R.page));
    const under = onBlocks ? surfaces.concat(alike) : surfaces;
    const fixText = () => [["text", moveLightness(R.text, under, surfaces)]];
    add("text-page", "Text on the page", R.text, R.page, fixText);
    add("text-card", "Text on cards", R.text, R.card, fixText);
    add("muted-page", "Muted text on the page", R.muted, R.page, () => [["muted", moveLightness(R.muted, surfaces, [R.page])]]);
    add("muted-card", "Muted text on cards", R.muted, R.card, () => [["muted", moveLightness(R.muted, surfaces, [R.card])]]);
    add("accent-card", "Accent text on cards", R.accent, R.card, () => [["accent", moveLightness(R.accent, surfaces, [R.card])]]);
    add("accent-ink", "Text on accent buttons", R.accentInk, R.accent, () => [["accent", moveAccent(R.accent)]]);
    if (onBlocks) {
      const bad = CATS.filter((c) => contrast(R.ink, R.fills[c]) < 4.5);
      const fixCat = (c) => ["cat." + c, moveLightness(R.fills[c], [R.ink])];
      if (bad.length >= 3) {
        const worst = bad.reduce((a, c) => (contrast(R.ink, R.fills[c]) < contrast(R.ink, R.fills[a]) ? c : a));
        rows.push({
          id: "cats", fg: R.ink, bg: R.fills[worst], fix: () => bad.map(fixCat),
          text: `Text on ${bad.length} block colours is ${ratioText(contrast(R.ink, R.fills[worst]))}:1 at worst`,
        });
      } else {
        for (const c of bad) add("cat-" + c, `Text on ${W.categories[c]} blocks`, R.ink, R.fills[c], () => [fixCat(c)]);
      }
    }
    return rows;
  }

  // --- saved looks ----------------------------------------------------------------------------------

  function loadSaved() {
    try {
      const list = JSON.parse(localStorage.getItem(STORE) || "[]");
      if (!Array.isArray(list)) return [];
      return list
        .filter((e) => e && typeof e.id === "string" && typeof e.name === "string" && LOOK_IDS.includes(e.base))
        .map((e) => ({ id: e.id, name: e.name.slice(0, 40), base: e.base, over: cleanAll(e.over) }));
    } catch (_) {
      return [];
    }
  }
  function storeSaved(list) {
    try { localStorage.setItem(STORE, JSON.stringify(list)); } catch (_) { /* a private window: kept for this page only */ }
  }
  const newId = () => "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "look";
  function uniqueName(name, exceptId, list = loadSaved()) {
    const taken = new Set(list.filter((e) => e.id !== exceptId).map((e) => e.name.toLowerCase()));
    if (!taken.has(name.toLowerCase())) return name;
    for (let n = 2; ; n++) if (!taken.has(`${name} ${n}`.toLowerCase())) return `${name} ${n}`;
  }

  // A look file, as Export writes it; null if `data` is not one.
  function readLookFile(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) return null;
    if (data.flexweek !== "look" || !LOOK_IDS.includes(data.startsFrom)) return null;
    const name = typeof data.name === "string" && data.name.trim() ? data.name.trim().slice(0, 40) : "Imported look";
    return { name, base: data.startsFrom, over: cleanAll(data.changes) };
  }
  // Adds the look in `text` to the saved looks: the new entry, or "json" or "shape" if it is not one.
  function importText(text) {
    let data;
    try { data = JSON.parse(text); } catch (_) { return "json"; }
    const look = readLookFile(data);
    if (!look) return "shape";
    const list = loadSaved();
    const entry = { id: newId(), name: uniqueName(look.name, null, list), base: look.base, over: look.over };
    storeSaved(list.concat(entry));
    return entry;
  }
  const IMPORT_ERRORS = {
    json: "That file could not be read. Pick a look file made with Export.",
    shape: "That file is not a FlexWeek look. Pick a look file made with Export.",
  };

  // --- the page's state -------------------------------------------------------------------------------

  const GROUPS = [
    { id: "colours", name: "Colours", icon: "palette", keys: ["page", "card", "text", "lines", "muted"] },
    { id: "categories", name: "Categories", icon: "swatch-book", keys: CATS.map((c) => "cat." + c) },
    { id: "shape", name: "Shape", icon: "square-round-corner", keys: ["corners", "spacing", "shadows"] },
    { id: "type", name: "Type", icon: "type", keys: ["body", "head", "size"] },
    { id: "blocks", name: "Blocks", icon: "calendar-range", keys: ["blocks", "edge", "times", "lengths"] },
    { id: "grid", name: "Grid", icon: "grid-3x3", keys: ["hours", "highlight", "now"] },
    { id: "motion", name: "Motion", icon: "wind", keys: ["motion"] },
  ];
  const GROUP_IDS = GROUPS.map((g) => g.id);
  // B's editor has the accent in Colours; A keeps it in Settings' own Accent row.
  const groupKeys = (g) => (g.id === "colours" && S.option === "B" ? ["accent", ...g.keys] : g.keys);

  let S = null;
  let keepScroll = null;
  let placed = false;

  function decode(s) {
    try { return decodeURIComponent(s); } catch (_) { return s; }
  }

  function parse(text, look, option) {
    const ui = {
      open: new Set(option === "B" ? ["colours"] : []), customise: false, editor: true, system: false,
      error: null, saving: false, saveName: "My look", renaming: null, at: null, zoom: "fit",
    };
    const over = {};
    let from = null, name = null, save = null, openSeen = false;
    for (const item of (text || "").split(",")) {
      if (!item) continue;
      const i = item.indexOf(":");
      const key = i < 0 ? item : item.slice(0, i);
      const raw = decode(i < 0 ? "" : item.slice(i + 1));
      if (key === "open") {
        if (!openSeen) { ui.open.clear(); openSeen = true; }
        if (raw === "all") { GROUP_IDS.forEach((g) => ui.open.add(g)); ui.customise = true; }
        else if (raw === "customise") ui.customise = true;
        else if (GROUP_IDS.includes(raw)) { ui.open.add(raw); ui.customise = true; }
      } else if (key === "at") ui.at = raw;
      else if (key === "editor") ui.editor = raw !== "off";
      else if (key === "zoom") ui.zoom = raw === "actual" ? "actual" : "fit";
      else if (key === "system") ui.system = raw === "on";
      else if (key === "saveas") { ui.saving = true; if (raw && raw !== "on") ui.saveName = raw.slice(0, 40); }
      else if (key === "error" && IMPORT_ERRORS[raw]) ui.error = raw;
      else if (key === "rename") ui.renaming = raw;
      else if (key === "fix") ui.fix = raw;
      else if (key === "from") from = raw;
      else if (key === "name") name = raw.slice(0, 40);
      else if (key === "save") save = raw.trim().slice(0, 40);
      else {
        const value = clean(key, raw);
        if (value !== undefined) over[key] = value;
      }
    }
    let list = loadSaved();
    if (save) {
      // Saving by address is repeatable: the same name replaces its own look.
      const id = "n-" + slug(save);
      const entry = { id, name: save, base: look, over: { ...over } };
      const at = list.findIndex((e) => e.id === id);
      if (at >= 0) list[at] = entry; else list = list.concat(entry);
      storeSaved(list);
      from = id;
    }
    const entry = from ? list.find((e) => e.id === from && e.base === look) : null;
    if (ui.system && look !== "light" && look !== "dark") ui.system = false;
    return {
      ui, over,
      from: entry ? entry.id : null,
      start: entry ? { ...entry.over } : {},
      name: name || (entry ? entry.name : "My look"),
    };
  }

  function serialise(state = S) {
    const items = [];
    const ui = state.ui;
    if (state.option === "A") {
      if (ui.customise) {
        const open = GROUP_IDS.filter((g) => ui.open.has(g));
        items.push(...(open.length ? open.map((g) => "open:" + g) : ["open:customise"]));
      }
    } else {
      const open = GROUP_IDS.filter((g) => ui.open.has(g));
      if (!(open.length === 1 && open[0] === "colours")) items.push(...(open.length ? open.map((g) => "open:" + g) : ["open:none"]));
      if (!ui.editor) items.push("editor:off");
      if (ui.zoom === "actual") items.push("zoom:actual");
    }
    if (ui.system) items.push("system:on");
    if (state.from) items.push("from:" + state.from);
    if (state.name && state.name !== "My look" && !state.from) items.push("name:" + encodeURIComponent(state.name));
    for (const key of KEYS) {
      if (state.over[key] === undefined) continue;
      const v = state.over[key];
      items.push(`${key}:${v === true ? "on" : v === false ? "off" : v}`);
    }
    return items.join(",");
  }

  const keep = () => S.ctx.keep(serialise());
  const same = (a, b) => a === b;
  const changedKeys = () => KEYS.filter((k) => !same(S.over[k], S.start[k]));
  const isChanged = () => changedKeys().length > 0;
  const currentEntry = () => (S.from ? loadSaved().find((e) => e.id === S.from) || null : null);

  // Move to another look (or a saved one): the frame draws the page again in it.
  function goLook(base, { from = null, over = {}, name = null, system = false } = {}) {
    const scroller = S.root.querySelector("[data-scroll]");
    keepScroll = scroller ? scroller.scrollTop : null;
    const next = { ...S, from, over, ui: { ...S.ui, system, saving: false, renaming: null, error: null }, name: name || S.name };
    S.ctx.go({ look: base, cu: serialise(next) });
  }

  // --- drawing ----------------------------------------------------------------------------------------

  const ic = (name, size = 16) => FW.icon(name, size);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const seg = (k, label, options) => `
    <div class="cu-seg" role="radiogroup" aria-label="${label}" data-k="${k}">${options.map(([v, text, face]) =>
      `<button type="button" role="radio" aria-checked="false" data-v="${v}"${face ? ` style="font-family:var(--font-${face})"` : ""}>${text}</button>`).join("")}</div>`;
  const toggle = (k, label, kind = "") =>
    `<button type="button" class="cu-switch" role="switch" aria-checked="false" data-k="${k}"${kind ? ` data-kind="${kind}"` : ""}><i></i><span>${label}</span></button>`;
  const range = (k, label, min, max, step, kind = "") =>
    `<input type="range" class="cu-range${kind ? " cu-" + kind : ""}" data-k="${k}"${kind ? ` data-kind="${kind}"` : ""} min="${min}" max="${max}" step="${step}" aria-label="${label}">`;
  const colour = (k, label) => `
    <span class="cu-colour"><input type="color" data-k="${k}" aria-label="${label}"><input type="text" class="cu-hex" data-k="${k}" data-kind="hex" maxlength="7" spellcheck="false" autocomplete="off" aria-label="${label}, as a hex code"></span>`;
  const field = (label, control, { out = "", hint = "", hintKey = "" } = {}) => `
    <div class="cu-field">
      <div class="cu-field-head"><span class="cu-label">${label}</span>${out ? `<output class="cu-out" data-out="${out}"></output>` : ""}</div>
      ${control}
      ${hint ? `<p class="cu-hint"${hintKey ? ` data-hint="${hintKey}"` : ""}>${hint}</p>` : ""}
    </div>`;
  const line = (label, control) => `<div class="cu-field cu-line"><span class="cu-label">${label}</span>${control}</div>`;
  const FACES = [["sans", "Sans", "sans"], ["serif", "Serif", "serif"], ["mono", "Mono", "mono"]];

  function accentControl() {
    const dark = FW.darkLooks.has(S.base);
    const swatches = accentsFor(S.base).map(([id, name, l, d]) => {
      const value = dark ? d : l;
      return `<button type="button" class="cu-acc" role="radio" aria-checked="false" data-v="${id}" style="--sw:${value};--swi:${inkFor(value)}">
        <span class="dot">${ic("check", 16)}</span><span class="nm">${name}</span></button>`;
    }).join("");
    return `<div class="cu-accents" role="radiogroup" aria-label="Accent" data-k="accent">${swatches}
      <span class="cu-acc-any"><span class="cu-hint">Any colour</span>${colour("accent", "Accent")}</span></div>`;
  }

  const BODIES = {
    colours: () => `
      ${S.option === "B" ? field("Accent", accentControl(), { out: "accent" }) : ""}
      <div class="cu-grid">${[["page", "Page"], ["card", "Cards"], ["text", "Text"], ["lines", "Lines"]]
        .map(([k, name]) => line(name, colour(k, name))).join("")}</div>
      <p class="cu-hint">Muted text, raised cards and strong lines follow these four.</p>`,
    categories: () => `
      <div class="cu-grid cu-cats">${CATS.map((c) => `
        <div class="cu-cat" data-catrow="${c}">
          <div class="cu-cat-head">
            <span class="cu-mini" data-mini><span class="cu-chip" data-cat="${c}">Aa</span></span>
            <span class="cu-cat-name">${c === "assignments" ? ic("book-open", 15) : ""}${W.categories[c]}</span>
            ${toggle("cat." + c, "Exact colour", "exact")}
          </div>
          <div class="cu-cat-hue">${range("cat." + c, W.categories[c] + " hue", 0, 359, 1, "hue")}</div>
          <div class="cu-cat-exact">${colour("cat." + c, W.categories[c] + " colour")}</div>
        </div>`).join("")}</div>
      <p class="cu-hint">A hue always reads. Exact colour takes any colour, and Readability warns if text on it is hard to read.</p>`,
    shape: () => `
      <div class="cu-grid">
        ${field("Corners", range("corners", "Corners", 0, 16, 1), { out: "corners" })}
        ${field("Spacing", seg("spacing", "Spacing", [["comfortable", "Comfortable"], ["compact", "Compact"]]))}
        ${field("Shadows", seg("shadows", "Shadows", [["none", "None"], ["soft", "Soft"], ["bold", "Bold"]]))}
      </div>`,
    type: () => `
      <div class="cu-grid">
        ${field("Text font", seg("body", "Text font", FACES))}
        ${field("Heading font", seg("head", "Heading font", FACES))}
        ${field("Text size", seg("size", "Text size", [["90", "Small"], ["100", "Normal"], ["115", "Large"]]) + range("size", "Text size", 90, 130, 5), { out: "size" })}
      </div>`,
    blocks: () => `
      <div class="cu-grid">
        ${field("Block style", seg("blocks", "Block style", [["edge", "Edge"], ["filled", "Filled"], ["outline", "Outline"]]))}
        ${field("Edge width", range("edge", "Edge width", 2, 6, 1), { out: "edge", hint: "Filled blocks have no edge.", hintKey: "edge" })}
        <div class="cu-switches">${toggle("times", "Show times")}${toggle("lengths", "Show lengths")}</div>
      </div>`,
    grid: () => `
      <div class="cu-grid">
        ${field("Hour lines", seg("hours", "Hour lines", [["none", "None"], ["faint", "Faint"], ["clear", "Clear"]]))}
        ${field("Now line", seg("now", "Now line", [["accent", "Accent"], ["text", "Text colour"]]))}
        <div class="cu-switches">${toggle("highlight", "Today's highlight")}</div>
      </div>`,
    motion: () => `
      ${field("Motion", seg("motion", "Motion", [["normal", "Normal"], ["more", "More"], ["reduce", "Reduce"], ["off", "Off"]]))}
      <p class="cu-hint cu-motion-text" data-motion></p>
      <button type="button" class="cu-btn secondary" data-act="try">${ic("circle-play", 16)}Play it on the preview</button>`,
  };

  function groupsHTML() {
    return GROUPS.map((g) => {
      const open = S.ui.open.has(g.id);
      return `
        <section class="cu-group" data-group="${g.id}" data-open="${open}">
          <div class="cu-group-head">
            <button type="button" class="cu-group-toggle" data-act="group" data-id="${g.id}" aria-expanded="${open}">
              <span class="cu-gicon">${ic(g.icon, 18)}</span><span class="cu-gname">${g.name}</span>
              <span class="cu-tag" data-changed hidden>Changed</span>
              <span class="cu-chev">${ic("chevron-down", 18)}</span>
            </button>
            <button type="button" class="cu-btn quiet small cu-greset" data-act="reset-group" data-id="${g.id}" aria-label="Reset ${g.name}">${ic("rotate-ccw", 14)}Reset</button>
          </div>
          <div class="cu-group-body"><div class="cu-group-inner"><div class="cu-gpad">${BODIES[g.id]()}</div></div></div>
        </section>`;
    }).join("");
  }

  function lookItem({ id, name, act, selected, saved }) {
    if (saved && S.ui.renaming === id) {
      return `
        <div class="cu-lk renaming">
          <input class="cu-text" data-rename="${id}" value="${esc(name)}" maxlength="40" aria-label="New name for ${esc(name)}">
          <button type="button" class="cu-btn small primary" data-act="rename-commit" data-id="${id}">Save</button>
          <button type="button" class="cu-btn small quiet" data-act="rename-cancel">Cancel</button>
        </div>`;
    }
    return `
      <div class="cu-lk${selected ? " on" : ""}">
        <button type="button" class="cu-lk-pick" data-act="${act}" data-id="${id}" aria-pressed="${selected}">
          <span class="cu-strip" data-strip="${saved ? "saved:" + id : id}"><i class="cd"><b data-cat="class"></b><b data-cat="assignments"></b></i><i class="ac"></i></span>
          <span class="nm">${esc(name)}</span>${selected ? `<span class="tick">${ic("check", 16)}</span>` : ""}
        </button>
        ${saved ? `<span class="cu-lk-acts">
          <button type="button" class="cu-iconbtn" data-act="rename" data-id="${id}" aria-label="Rename ${esc(name)}" title="Rename">${ic("pencil", 15)}</button>
          <button type="button" class="cu-iconbtn" data-act="duplicate" data-id="${id}" aria-label="Duplicate ${esc(name)}" title="Duplicate">${ic("copy", 15)}</button>
          <button type="button" class="cu-iconbtn danger" data-act="delete" data-id="${id}" aria-label="Delete ${esc(name)}" title="Delete">${ic("trash", 15)}</button>
        </span>` : ""}
      </div>`;
  }

  function moreLooks() {
    const saved = loadSaved();
    const builtIn = MORE.map((id) => lookItem({ id, name: LOOK_NAME[id], act: "look", selected: !S.from && !S.ui.system && S.base === id }));
    const mine = saved.map((e) => lookItem({ id: e.id, name: e.name, act: "saved", selected: S.from === e.id, saved: true }));
    return `<div class="cu-more">${builtIn.join("")}
      <div class="cu-more-sub">Your looks</div>
      ${mine.length ? mine.join("") : `<p class="cu-hint cu-more-none">Looks you save show here.</p>`}</div>`;
  }

  function lookSeg(withButton) {
    const on = (id) => !S.from && (id === "system" ? S.ui.system : !S.ui.system && S.base === id);
    const b = (id, name) => `<button type="button" role="radio" aria-checked="${on(id)}" data-act="${id === "system" ? "system" : "look"}" data-id="${id}">${name}</button>`;
    return `<div class="cu-look-line"><div class="cu-seg" role="radiogroup" aria-label="Look">${b("light", "Light")}${b("dark", "Dark")}${b("system", "System")}</div>
      ${withButton ? `<button type="button" class="cu-btn secondary" data-act="editor-open">${ic("sliders-horizontal", 16)}Customise…</button>` : ""}</div>`;
  }

  const row = (id, label, hint, control) => `
    <div class="cu-setting" data-row="${id}">
      <div class="cu-sl"><span class="cu-label">${label}</span>${hint ? `<span class="cu-hint">${hint}</span>` : ""}</div>
      <div class="cu-sc">${control}</div>
    </div>`;

  const errorLine = () => (S.ui.error ? `
    <div class="cu-error" role="alert">${ic("triangle-alert", 16)}<span>${IMPORT_ERRORS[S.ui.error]}</span>
      <button type="button" class="cu-iconbtn" data-act="dismiss" aria-label="Dismiss" title="Dismiss">${ic("x", 14)}</button></div>` : "");

  const pageHead = () => `
    <header class="cu-page-head">
      <span class="cu-iconbtn" aria-hidden="true">${ic("arrow-left", 18)}</span><h1>Settings</h1>
    </header>`;
  const secTitle = (icon, name) => `<h2 class="cu-sec-title"><span class="cu-sec-icon">${ic(icon, 18)}</span>${name}</h2>`;
  const calendarStub = () => `
    <section class="cu-section cu-stub">
      ${secTitle("calendar", "Calendar")}
      <div class="cu-card cu-rows">
        ${row("week", "Week starts on", "", `<span class="cu-fake">Monday${ic("chevron-down", 16)}</span>`)}
        ${row("day", "Day starts at", "", `<span class="cu-fake">07:00${ic("chevron-down", 16)}</span>`)}
      </div>
    </section>`;

  function pageA() {
    const open = S.ui.customise;
    return `
      <div class="cu-page" data-scroll>
        <div class="cu-col">
          ${pageHead()}
          <section class="cu-section">
            ${secTitle("palette", "Appearance")}
            <div class="cu-sticky">
              <div class="cu-thumb" data-preview role="img" aria-label="Your week in this look"></div>
              <div class="cu-side"><div data-status></div><div data-check></div></div>
            </div>
            <div class="cu-card cu-rows">
              ${row("look", "Look", "System follows your computer.", lookSeg(false))}
              ${row("looks", "More looks", "", moreLooks())}
              ${row("accent", "Accent", "Buttons, today and the time now.", accentControl())}
              ${row("share", "Share a look", "A look saves as a small file you can send.", `
                <div class="cu-buttons">
                  <button type="button" class="cu-btn quiet bordered" data-act="export">${ic("download", 16)}Export</button>
                  <button type="button" class="cu-btn quiet bordered" data-act="import">${ic("upload", 16)}Import</button>
                </div>${errorLine()}`)}
              <button type="button" class="cu-custom-row" data-act="custom" data-row="customise" aria-expanded="${open}">
                <span class="cu-gicon">${ic("sliders-horizontal", 18)}</span>
                <span class="cu-sl"><span class="cu-label">Customise</span><span class="cu-hint">Colours, categories, shape, type, blocks, the grid and motion.</span></span>
                <span class="cu-tag" data-changed-all hidden>Changed</span>
                <span class="cu-chev">${ic("chevron-down", 18)}</span>
              </button>
            </div>
            <div class="cu-groups" data-groups data-open="${open}"><div class="cu-groups-inner">${groupsHTML()}</div></div>
          </section>
          ${calendarStub()}
        </div>
      </div>`;
  }

  function settingsB() {
    return `
      <div class="cu-page" data-scroll>
        <div class="cu-col">
          ${pageHead()}
          <section class="cu-section">
            ${secTitle("palette", "Appearance")}
            <div class="cu-card cu-rows">
              ${row("look", "Look", "System follows your computer. Customise changes any look and saves it as yours.", lookSeg(true))}
              ${row("looks", "More looks", "", moreLooks())}
              ${row("accent", "Accent", "Buttons, today and the time now.", accentControl())}
            </div>
          </section>
          ${calendarStub()}
        </div>
      </div>`;
  }

  function editorB() {
    const entry = currentEntry();
    const looks = FW.looks.map(([id, name]) => `<option value="look:${id}"${!entry && S.base === id ? " selected" : ""}>${name}</option>`).join("");
    const mine = loadSaved().map((e) => `<option value="saved:${e.id}"${entry && entry.id === e.id ? " selected" : ""}>${esc(e.name)}</option>`).join("");
    return `
      <div class="cu-ed">
        <header class="cu-ed-head">
          <button type="button" class="cu-iconbtn" data-act="done" aria-label="Done, back to Settings" title="Back to Settings">${ic("arrow-left", 18)}</button>
          <h1 class="cu-ed-title">Look editor</h1>
          <label class="cu-inline-field"><span class="cu-label">Start from</span>
            <span class="cu-select"><select data-act="from" aria-label="Start from"><optgroup label="Looks">${looks}</optgroup>${mine ? `<optgroup label="Your looks">${mine}</optgroup>` : ""}</select>${ic("chevron-down", 16)}</span></label>
          <label class="cu-inline-field"><span class="cu-label">Name</span>
            <input class="cu-text" data-act="name" value="${esc(S.name)}" maxlength="40" aria-label="Name of your look"></label>
          ${entry ? `<span class="cu-ed-acts">
            <button type="button" class="cu-iconbtn" data-act="duplicate" data-id="${entry.id}" aria-label="Duplicate ${esc(entry.name)}" title="Duplicate">${ic("copy", 16)}</button>
            <button type="button" class="cu-iconbtn danger" data-act="delete" data-id="${entry.id}" aria-label="Delete ${esc(entry.name)}" title="Delete">${ic("trash", 16)}</button>
          </span>` : ""}
          <span class="cu-ed-state" data-edstate></span>
        </header>
        <div class="cu-ed-body">
          <aside class="cu-ed-col" data-scroll>
            <div data-check></div>
            ${groupsHTML()}
          </aside>
          <div class="cu-ed-right">
            <div class="cu-ed-preview${S.ui.zoom === "actual" ? " actual" : ""}" data-preview role="img" aria-label="Your week in this look"></div>
            <div class="cu-ed-zoom">
              <span class="cu-hint">The whole window, ${S.ui.zoom === "actual" ? "at its real size: scroll to see all of it." : "fitted to this space."}</span>
              <div class="cu-seg" role="radiogroup" aria-label="Preview size">
                <button type="button" role="radio" aria-checked="${S.ui.zoom !== "actual"}" data-act="zoom" data-id="fit">Fit</button>
                <button type="button" role="radio" aria-checked="${S.ui.zoom === "actual"}" data-act="zoom" data-id="actual">Actual size</button>
              </div>
            </div>
          </div>
        </div>
        <footer class="cu-ed-foot">
          <button type="button" class="cu-btn quiet" data-act="reset-all">${ic("rotate-ccw", 16)}Reset all</button>
          <button type="button" class="cu-btn quiet" data-act="export">${ic("download", 16)}Export</button>
          <button type="button" class="cu-btn quiet" data-act="import">${ic("upload", 16)}Import</button>
          <span class="cu-foot-error">${errorLine()}</span>
          <button type="button" class="cu-btn secondary" data-act="b-saveas">${ic("plus", 16)}Save as new</button>
          <button type="button" class="cu-btn primary" data-act="done">Done</button>
        </footer>
      </div>`;
  }

  function statusA() {
    const entry = currentEntry();
    if (S.ui.saving) {
      return `
        <div class="cu-saveas">
          <label class="cu-label" for="cu-save-name">Name your look</label>
          <div class="cu-buttons">
            <input id="cu-save-name" class="cu-text" data-act="save-name" value="${esc(S.ui.saveName)}" maxlength="40">
            <button type="button" class="cu-btn primary" data-act="saveas-commit">Save</button>
            <button type="button" class="cu-btn quiet" data-act="saveas-cancel">Cancel</button>
          </div>
        </div>`;
    }
    const changed = isChanged();
    const title = entry ? esc(entry.name) : S.ui.system ? `System <span class="cu-sub">${LOOK_NAME[S.base]} now</span>` : LOOK_NAME[S.base];
    const note = changed ? "Changed, not saved yet." : entry ? `Your look, from ${LOOK_NAME[entry.base]}.` : "As it comes. Customise it below.";
    return `
      <div class="cu-now"><div class="cu-now-title">${title}</div><p class="cu-hint">${note}</p></div>
      <div class="cu-buttons">
        ${entry && changed ? `<button type="button" class="cu-btn primary" data-act="save">Save changes</button>` : ""}
        <button type="button" class="cu-btn secondary" data-act="saveas">${ic("plus", 16)}Save as…</button>
        <button type="button" class="cu-btn quiet" data-act="reset-all"${changed ? "" : " disabled"}>${ic("rotate-ccw", 16)}Reset</button>
      </div>`;
  }

  function checkHTML(rows) {
    const cap = S.option === "A" ? 3 : 8;
    const shown = rows.slice(0, cap);
    return `
      <section class="cu-check" aria-live="polite">
        <div class="cu-check-head"><span class="cu-label">Readability</span>
          ${rows.length > 1 ? `<button type="button" class="cu-btn small secondary" data-act="fix-all">Fix all</button>` : ""}</div>
        ${rows.length ? shown.map((r) => `
          <div class="cu-warn">${ic("triangle-alert", 16)}
            <span class="cu-pair" style="background:${hexFrom(r.bg)};color:${hexFrom(r.fg)}" aria-hidden="true">Aa</span>
            <span class="cu-warn-text">${r.text}</span>
            <button type="button" class="cu-btn small secondary" data-act="fix" data-id="${r.id}">Fix</button>
          </div>`).join("") : `<div class="cu-ok">${ic("circle-check", 16)}Everything reads</div>`}
        ${rows.length > cap ? `<p class="cu-hint">${rows.length - cap} more under 4.5:1. Fix all fixes them too.</p>` : ""}
      </section>`;
  }

  // The preview is the whole window, Today's app (the Rail) under the top bar: in A at 480 pixels,
  // in B fitted to its 920 pixels or at its real size. The Rail is drawn for 1280 pixels, so it is
  // never squeezed into less, which would cut its text.
  function drawPreview() {
    const box = S.root.querySelector("[data-preview]");
    if (!box) return;
    const stage = FW.stageFor(FW.designs.today, "B", "week", S.base, "look");
    paint(stage, S.base, S.over);
    const width = S.option === "A" ? 480 : S.ui.zoom === "actual" ? FW.stage.width : 920;
    if (width !== FW.stage.width) stage.style.transform = `scale(${width / FW.stage.width})`;
    const left = box.scrollLeft, top = box.scrollTop;
    box.replaceChildren(stage);
    box.scrollLeft = left;
    box.scrollTop = top;
  }

  function refresh() {
    S.R = measure(S.base, S.over);
    S.rows = checks(S.base, S.over, S.R);
    drawPreview();
    const check = S.root.querySelector("[data-check]");
    const html = checkHTML(S.rows);
    if (check && check._html !== html) { check.innerHTML = html; check._html = html; }
    // While the Save as field is being typed in, it is left alone.
    const status = S.root.querySelector("[data-status]");
    if (status && (!S.ui.saving || status._html === undefined)) {
      const s = statusA();
      if (status._html !== s) { status.innerHTML = s; status._html = s; }
    }
    sync();
  }

  // Puts every control in step with the look, except the one being dragged or typed in.
  function sync() {
    const root = S.root;
    const R = S.R;
    const k = knobs(S.base, S.over);
    const corners = S.over.corners !== undefined ? S.over.corners : Math.round(baseInfo(S.base).corners);
    const value = (key) => (key === "corners" ? corners : k[key]);
    const colourOf = (key) => (key === "accent" ? hexFrom(R.accent) : key.startsWith("cat.") ? hexFrom(R.fills[key.slice(4)]) : hexFrom(R[key]));
    const hueOf = (key) => {
      const v = S.over[key];
      return typeof v === "number" ? v : typeof v === "string" ? Math.round(toLch(rgbOf(v))[2]) : HUES[key.slice(4)];
    };
    const accent = S.over.accent !== undefined ? S.over.accent : S.base === "high-contrast" ? "yellow" : "blue";
    const active = document.activeElement;
    for (const el of root.querySelectorAll("[data-k]")) {
      const key = el.dataset.k;
      if (el.classList.contains("cu-seg") || el.classList.contains("cu-accents")) {
        const v = key === "accent" ? accent : String(value(key));
        for (const b of el.querySelectorAll(":scope > [data-v]")) b.setAttribute("aria-checked", String(b.dataset.v === v));
      } else if (el.classList.contains("cu-switch")) {
        const on = el.dataset.kind === "exact" ? typeof S.over[key] === "string" : !!value(key);
        el.setAttribute("aria-checked", String(on));
      } else if (el.type === "range") {
        if (el !== active) el.value = el.dataset.kind === "hue" ? hueOf(key) : value(key);
        el.disabled = key === "edge" && k.blocks === "filled";
        const pct = ((Number(el.value) - Number(el.min)) / (Number(el.max) - Number(el.min))) * 100;
        el.style.setProperty("--cu-fill", pct.toFixed(1) + "%");
      } else if (el.type === "color") {
        if (el !== active) el.value = colourOf(key);
      } else if (el.dataset.kind === "hex") {
        if (el !== active) { el.value = colourOf(key); el.removeAttribute("aria-invalid"); }
      }
    }
    for (const row of root.querySelectorAll("[data-catrow]")) {
      row.dataset.mode = typeof S.over["cat." + row.dataset.catrow] === "string" ? "exact" : "hue";
    }
    const swatch = accentsFor(S.base).find(([id]) => id === accent);
    const outs = {
      corners: `${corners} px`, size: `${k.size} %`, edge: `${k.edge} px`,
      accent: swatch ? swatch[1] : "Your colour",
    };
    for (const el of root.querySelectorAll("[data-out]")) el.textContent = outs[el.dataset.out];
    for (const el of root.querySelectorAll('[data-hint="edge"]')) el.hidden = k.blocks !== "filled";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const el of root.querySelectorAll("[data-motion]")) {
      el.textContent = LEVELS[k.motion].text + (reduced && LEVELS[k.motion].slide ? " Your computer asks for less motion, so nothing slides." : "");
    }
    for (const el of root.querySelectorAll("[data-mini]")) paint(el, S.base, S.over, "cu-mini");
    let any = false;
    for (const g of GROUPS) {
      const card = root.querySelector(`[data-group="${g.id}"]`);
      if (!card) continue;
      const changed = groupKeys(g).some((key) => !same(S.over[key], S.start[key]));
      any = any || changed;
      card.querySelector("[data-changed]").hidden = !changed;
      card.querySelector(".cu-greset").disabled = !changed;
    }
    const all = root.querySelector("[data-changed-all]");
    if (all) all.hidden = !any;
    const state = root.querySelector("[data-edstate]");
    if (state) {
      const entry = currentEntry();
      state.textContent = isChanged() ? "Changed, not saved" : entry ? "Saved" : "";
    }
  }

  function paintStrips() {
    const saved = loadSaved();
    for (const el of S.root.querySelectorAll("[data-strip]")) {
      const ref = el.dataset.strip;
      if (ref.startsWith("saved:")) {
        const e = saved.find((x) => x.id === ref.slice(6));
        if (e) paint(el, e.base, e.over, "cu-strip");
      } else {
        paint(el, ref, {}, "cu-strip");
      }
    }
  }

  function draw() {
    const root = S.root;
    const old = root.querySelector("[data-scroll]");
    const top = old ? old.scrollTop : null;
    root.innerHTML = (S.option === "A" ? pageA() : S.ui.editor ? editorB() : settingsB()) +
      `<input type="file" accept=".json,application/json" data-file hidden>`;
    const scroller = root.querySelector("[data-scroll]");
    if (scroller && top !== null) scroller.scrollTop = top;
    paintStrips();
    refresh();
  }

  // Scrolls to what the address asks for, or the first open group, once the page is on screen.
  function place() {
    const scroller = S.root.querySelector("[data-scroll]");
    if (!scroller) return;
    const ask = S.ui.at;
    let target = null;
    if (ask) target = S.root.querySelector(`[data-group="${ask}"], [data-row="${ask}"]`);
    if (!target && S.option === "A" && S.ui.customise) {
      const first = GROUP_IDS.find((g) => S.ui.open.has(g));
      target = S.root.querySelector(first ? `[data-group="${first}"]` : `[data-row="customise"]`);
    }
    if (!target) return;
    const scale = scroller.getBoundingClientRect().height / scroller.offsetHeight || 1;
    const sticky = S.root.querySelector(".cu-sticky");
    const cover = sticky ? sticky.offsetHeight : 0;
    const gap = (target.getBoundingClientRect().top - scroller.getBoundingClientRect().top) / scale;
    scroller.scrollTop += gap - cover - 12;
  }

  function whenAttached(el, fn, tries = 0) {
    if (el.isConnected) {
      fn();
      document.fonts.ready.then(() => el.isConnected && fn());
    } else if (tries < 100) setTimeout(() => whenAttached(el, fn, tries + 1), 0);
  }

  // --- changes ----------------------------------------------------------------------------------------

  let pending = false;
  function set(key, value) {
    if (value === undefined) delete S.over[key]; else S.over[key] = value;
    // A fixed muted colour belongs to the text and card it was fixed against.
    if ((key === "text" || key === "card") && S.over.muted !== undefined && S.start.muted === undefined) delete S.over.muted;
    keep();
    if (pending) return;
    pending = true;
    // Once per frame while a slider is dragged; the timer covers a page that draws no frames.
    const run = () => { if (pending) { pending = false; refresh(); } };
    requestAnimationFrame(run);
    setTimeout(run, 50);
  }
  function setNow(pairs) {
    for (const [key, value] of pairs) {
      if (value === undefined) delete S.over[key]; else S.over[key] = value;
    }
    keep();
    refresh();
  }

  function fix(id) {
    const row = S.rows.find((r) => r.id === id);
    if (row) setNow(row.fix());
  }
  function fixAll() {
    for (let i = 0; i < 16; i++) {
      const rows = checks(S.base, S.over, measure(S.base, S.over));
      if (!rows.length) break;
      for (const [key, value] of rows[0].fix()) S.over[key] = value;
    }
    keep();
    refresh();
  }

  function saveNew(name) {
    const list = loadSaved();
    const entry = { id: newId(), name: uniqueName(name.trim() || "My look", null, list), base: S.base, over: { ...S.over } };
    storeSaved(list.concat(entry));
    S.from = entry.id;
    S.start = { ...S.over };
    S.name = entry.name;
    S.ui.system = false;
    return entry;
  }
  function saveInto(entry) {
    storeSaved(loadSaved().map((e) => (e.id === entry.id ? { ...e, over: { ...S.over } } : e)));
    S.start = { ...S.over };
  }

  function exportLook() {
    const entry = currentEntry();
    const name = entry ? entry.name : S.name || "My look";
    const data = { flexweek: "look", version: 1, name, startsFrom: S.base, changes: { ...S.over } };
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${slug(name)}.flexweek-look.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    return data;
  }

  function useEntry(entry) {
    goLook(entry.base, { from: entry.id, over: { ...entry.over }, name: entry.name });
  }

  function tryMotion() {
    const content = S.root.querySelector("[data-preview] .fw-content");
    if (!content) return;
    const l = LEVELS[knobs(S.base, S.over).motion];
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const slide = reduced ? 0 : l.slide;
    if (!l.out) return;
    content.style.transition = `opacity ${l.out}ms ${EASE}, transform ${l.out}ms ${EASE}`;
    content.style.opacity = "0";
    content.style.transform = `translateX(${-slide}px)`;
    setTimeout(() => {
      content.style.transition = "none";
      content.style.transform = `translateX(${slide}px)`;
      void content.offsetWidth;
      content.style.transition = `opacity ${l.in}ms ${EASE}, transform ${l.in}ms ${EASE}`;
      content.style.opacity = "1";
      content.style.transform = "none";
      setTimeout(() => { content.style.transition = content.style.opacity = content.style.transform = ""; }, l.in + 20);
    }, l.out);
  }

  function toggleGroup(id) {
    if (S.ui.open.has(id)) S.ui.open.delete(id); else S.ui.open.add(id);
    const card = S.root.querySelector(`[data-group="${id}"]`);
    const open = S.ui.open.has(id);
    card.dataset.open = String(open);
    card.querySelector(".cu-group-toggle").setAttribute("aria-expanded", String(open));
    keep();
  }

  const ACTIONS = {
    custom() {
      S.ui.customise = !S.ui.customise;
      S.root.querySelector("[data-groups]").dataset.open = String(S.ui.customise);
      S.root.querySelector("[data-act='custom']").setAttribute("aria-expanded", String(S.ui.customise));
      keep();
    },
    group: (id) => toggleGroup(id),
    "reset-group": (id) => {
      const g = GROUPS.find((x) => x.id === id);
      setNow(groupKeys(g).map((key) => [key, S.start[key]]));
    },
    "reset-all": () => { S.over = { ...S.start }; keep(); refresh(); },
    look: (id) => goLook(id),
    system: () => goLook(window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light", { system: true }),
    saved: (id) => { const e = loadSaved().find((x) => x.id === id); if (e) useEntry(e); },
    saveas: () => {
      S.ui.saving = true;
      S.ui.saveName = uniqueName(currentEntry() ? currentEntry().name : "My look");
      draw();
      const input = S.root.querySelector("[data-act='save-name']");
      if (input) { input.focus(); input.select(); }
    },
    "saveas-cancel": () => { S.ui.saving = false; draw(); },
    "saveas-commit": () => { S.ui.saving = false; saveNew(S.ui.saveName); keep(); draw(); },
    save: () => { const e = currentEntry(); if (e) { saveInto(e); keep(); draw(); } },
    "b-saveas": () => { saveNew(S.name); keep(); draw(); },
    done: () => {
      const e = currentEntry();
      if (e && isChanged()) saveInto(e);
      else if (!e && isChanged()) saveNew(S.name);
      S.ui.editor = false;
      keep();
      draw();
    },
    "editor-open": () => { S.ui.editor = true; keep(); draw(); },
    zoom: (id) => { S.ui.zoom = id === "actual" ? "actual" : "fit"; keep(); draw(); },
    rename: (id) => {
      S.ui.renaming = id;
      draw();
      const input = S.root.querySelector(`[data-rename="${id}"]`);
      if (input) { input.focus(); input.select(); }
    },
    "rename-commit": (id) => {
      const input = S.root.querySelector(`[data-rename="${id}"]`);
      const name = input ? input.value.trim() : "";
      if (name) {
        const unique = uniqueName(name, id);
        storeSaved(loadSaved().map((e) => (e.id === id ? { ...e, name: unique } : e)));
        if (S.from === id) S.name = unique;
      }
      S.ui.renaming = null;
      draw();
    },
    "rename-cancel": () => { S.ui.renaming = null; draw(); },
    duplicate: (id) => {
      const list = loadSaved();
      const e = list.find((x) => x.id === id);
      if (!e) return;
      storeSaved(list.concat({ ...e, id: newId(), name: uniqueName(`${e.name} copy`, null, list) }));
      draw();
    },
    delete: (id) => {
      storeSaved(loadSaved().filter((e) => e.id !== id));
      if (S.from === id) { S.from = null; S.start = {}; S.name = "My look"; keep(); }
      draw();
    },
    export: () => exportLook(),
    import: () => S.root.querySelector("[data-file]").click(),
    dismiss: () => { S.ui.error = null; draw(); },
    fix: (id) => fix(id),
    "fix-all": () => fixAll(),
    try: () => tryMotion(),
  };

  function bind(root) {
    if (root._cuBound) return;
    root._cuBound = true;
    root.addEventListener("click", (e) => {
      const t = e.target.closest("button, [data-act]");
      if (!t || !root.contains(t) || t.disabled) return;
      if (t.classList.contains("cu-switch")) {
        const key = t.dataset.k;
        if (t.dataset.kind === "exact") {
          const v = S.over[key];
          const c = key.slice(4);
          set(key, typeof v === "string" ? Math.round(toLch(rgbOf(v))[2]) : hexFrom(S.R.fills[c]));
        } else {
          set(key, !knobs(S.base, S.over)[key]);
        }
        return;
      }
      const group = t.dataset.v !== undefined && t.parentElement && t.parentElement.dataset.k;
      if (group) { set(group, clean(group, t.dataset.v)); return; }
      const act = ACTIONS[t.dataset.act];
      if (act && t.tagName === "BUTTON") act(t.dataset.id);
    });
    root.addEventListener("input", (e) => {
      const el = e.target;
      if (el.dataset.act === "name") { S.name = el.value.slice(0, 40) || "My look"; keep(); return; }
      if (el.dataset.act === "save-name") { S.ui.saveName = el.value; return; }
      const key = el.dataset.k;
      if (!key) return;
      if (el.type === "range") set(key, clean(key, el.value));
      else if (el.type === "color") set(key, el.value);
      else if (el.dataset.kind === "hex") {
        const hex = hexOf(el.value);
        if (hex) { el.removeAttribute("aria-invalid"); set(key, hex); } else el.setAttribute("aria-invalid", "true");
      }
    });
    root.addEventListener("change", (e) => {
      const el = e.target;
      if (el.dataset.act === "from") {
        const [kind, id] = el.value.split(":");
        if (kind === "look") goLook(id);
        else { const entry = loadSaved().find((x) => x.id === id); if (entry) useEntry(entry); }
      } else if (el.dataset.act === "name") {
        const entry = currentEntry();
        if (entry && el.value.trim()) {
          const unique = uniqueName(el.value.trim(), entry.id);
          storeSaved(loadSaved().map((x) => (x.id === entry.id ? { ...x, name: unique } : x)));
          S.name = unique;
          el.value = unique;
        }
      } else if (el.dataset.kind === "hex") {
        sync();
      } else if (el.matches("[data-file]") && el.files && el.files[0]) {
        const reader = new FileReader();
        reader.onload = () => {
          const result = importText(String(reader.result));
          if (typeof result === "string") { S.ui.error = result; draw(); } else { S.ui.error = null; useEntry(result); }
        };
        reader.onerror = () => { S.ui.error = "json"; draw(); };
        reader.readAsText(el.files[0]);
      }
    });
    root.addEventListener("keydown", (e) => {
      const el = e.target;
      if (el.dataset.act === "save-name") {
        if (e.key === "Enter") ACTIONS["saveas-commit"]();
        if (e.key === "Escape") ACTIONS["saveas-cancel"]();
      } else if (el.dataset.rename) {
        if (e.key === "Enter") ACTIONS["rename-commit"](el.dataset.rename);
        if (e.key === "Escape") ACTIONS["rename-cancel"]();
      }
    });
  }

  function mount(el, ctx, option) {
    S = { option, ctx, root: el, base: ctx.look, ...parse(ctx.cu, ctx.look, option) };
    bind(el);
    draw();
    // fix:<row> or fix:all presses Fix once, as if clicked; the address then holds the fixed colours.
    if (S.ui.fix) {
      const which = S.ui.fix;
      S.ui.fix = null;
      if (which === "all") fixAll(); else fix(which);
    }
    whenAttached(el, () => {
      const scroller = el.querySelector("[data-scroll]");
      if (keepScroll !== null && scroller) { scroller.scrollTop = keepScroll; keepScroll = null; placed = true; }
      else if (!placed || S.ui.at) { place(); placed = true; }
    });
  }

  FW.customise = {
    variants: {
      A: {
        name: "In Settings",
        summary: "Customise opens in place under Look in Settings' Appearance: seven cards that fold, under a small live preview of the week that stays at the top while you scroll. Look and Accent stay as simple as they are; most people never open Customise.",
        catalogue: [
          "Decision 24: Settings as a centred column, Look as Light | Dark | System with More looks",
          "GNOME's and macOS's Appearance settings: a preview above the choices",
          "One closed Customise row, so the simple choices stay simple",
          "UX rules: Color Contrast (4.5:1), Color Only, Error Messages",
        ],
        changes: [
          "Appearance gets a 480-pixel preview of Today's app (the Rail) that stays in view, with the look's name, Save as…, Reset and Readability beside it.",
          "More looks lists High contrast and the other seven with a small sample of each; looks you save join the list with rename, duplicate and delete.",
          "Accent keeps its five swatches and takes any colour, by a picker or a hex code.",
          "Customise opens seven cards in place: Colours (four colours; muted text, raised cards and strong lines follow), Categories (a hue on the family's lightness, or an exact colour), Shape, Type, Blocks, Grid and Motion, each with its own Reset.",
          "Readability checks text on the page and on cards, muted text, the accent, and text on every block colour as you go; anything under 4.5:1 gets a Fix that moves that colour's lightness until it passes.",
          "The controls stay in the look you started from while you edit, so a bad colour never hides them; the preview takes each change at once.",
          "Share a look: Export saves it as a small file and Import reads one back; a file that is not a look says so in a plain line.",
        ],
        render: (el, ctx) => mount(el, ctx, "A"),
      },
      B: {
        name: "Look editor",
        summary: "Settings keeps the Look row with a Customise… button beside it. The button opens a full-window editor: the controls in a 360-pixel column on the left, and Today's app (the Rail) large on the right, changing as you go.",
        catalogue: [
          "Material Theme Builder: the controls on the left, the product on the right",
          "Decision 24: Settings as a centred column, Look as Light | Dark | System with More looks",
          "UX rules: Color Contrast (4.5:1), Color Only, Error Messages",
        ],
        changes: [
          "Settings stays short: Look (Light | Dark | System) with Customise… beside it, More looks with your saved looks, and Accent.",
          "The editor's top bar: Start from (any of the ten looks or one you saved) and the look's name, with Duplicate and Delete for a saved look.",
          "The left column: Readability first, then Colours (with the accent), Categories, Shape, Type, Blocks, Grid and Motion as cards that fold, each with its own Reset.",
          "The right side is the whole window, top bar and Rail, fitted to its 920 pixels (72 %); Actual size shows it at its real size and scrolls, so blocks, corners and type read as they will. The Rail is never squeezed into 920 pixels, which cut its text.",
          "The bottom bar: Reset all, Export and Import; then Save as new, and Done, which keeps your look under the name you gave it.",
          "The controls stay in the look you started from while you edit, so a bad colour never hides them.",
        ],
        render: (el, ctx) => mount(el, ctx, "B"),
      },
    },
    // For the check scripts: the pieces that can be tested without clicking.
    test: { parse, clean, cleanAll, readLookFile, importText, contrast, moveLightness, measure, checks, parseCss, hexFrom, rgbOf },
  };
})();
