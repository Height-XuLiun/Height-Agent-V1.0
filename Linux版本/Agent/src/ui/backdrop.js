const Backdrop = (() => {
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const cloud = (c, y, w, h, a) =>
    `radial-gradient(${w}% ${h}% at 50% ${y}%,rgba(${c},${a}) 0%,rgba(${c},0) 70%)`;
  const scenes = {
    dawn: {
      base: "linear-gradient(180deg,#fff2e8 0%,#fde5d3 26%,#fbd2ba 56%,#f7bfa4 84%,#f3b294 100%)",
      glow: "radial-gradient(120% 58% at 50% 98%,rgba(255,206,166,.5) 0%,rgba(255,226,208,.24) 44%,rgba(255,255,255,0) 78%)",
      tint: "rgba(255,188,148,.62)",
      layers: [cloud("255,255,255", 34, 90, 10, .5), cloud("255,236,222", 52, 110, 9, .45), cloud("255,247,240", 70, 120, 8, .4)]
    },
    grassland: {
      base: "linear-gradient(180deg,#f1faf3 0%,#e0f1e4 28%,#cde8d5 56%,#b8dcc4 100%)",
      glow: "radial-gradient(90% 55% at 22% 94%,rgba(178,210,182,.48) 0%,rgba(206,228,208,.22) 45%,rgba(255,255,255,0) 80%)",
      tint: "rgba(146,198,158,.58)",
      layers: [cloud("255,255,255", 30, 100, 12, .55), cloud("255,255,255", 50, 120, 10, .35)]
    },
    canyon: {
      base: "linear-gradient(180deg,#fdf3ea 0%,#f8e2d1 30%,#f2ceb4 62%,#e9b899 100%)",
      glow: "radial-gradient(100% 60% at 78% 92%,rgba(222,178,142,.42) 0%,rgba(236,210,186,.2) 48%,rgba(255,255,255,0) 82%)",
      tint: "rgba(226,176,138,.58)",
      layers: [cloud("255,255,255", 28, 95, 11, .5), cloud("255,238,224", 48, 115, 9, .4)]
    },
    plateau: {
      base: "linear-gradient(180deg,#f2fafc 0%,#e2f0f4 30%,#cde4ea 58%,#b6d6de 100%)",
      glow: "radial-gradient(110% 58% at 60% 96%,rgba(172,202,206,.42) 0%,rgba(206,226,228,.2) 46%,rgba(255,255,255,0) 80%)",
      tint: "rgba(146,194,202,.58)",
      layers: [cloud("255,255,255", 26, 105, 13, .55), cloud("255,255,255", 46, 125, 10, .38)]
    },
    terrace: {
      base: "linear-gradient(180deg,#faf9ef 0%,#eef3dc 28%,#dfedc8 56%,#cee2b0 100%)",
      glow: "radial-gradient(120% 60% at 30% 98%,rgba(190,210,160,.42) 0%,rgba(216,230,192,.2) 46%,rgba(255,255,255,0) 80%)",
      tint: "rgba(176,204,138,.6)",
      layers: [cloud("255,255,255", 30, 110, 11, .5), cloud("246,250,236", 52, 130, 9, .4)]
    },
    beach: {
      base: "linear-gradient(180deg,#f3fafd 0%,#e2f2f8 30%,#cde7f0 58%,#b8dce9 100%)",
      glow: "radial-gradient(120% 62% at 50% 100%,rgba(186,216,226,.5) 0%,rgba(214,234,240,.24) 46%,rgba(255,255,255,0) 80%)",
      tint: "rgba(146,198,220,.58)",
      layers: [cloud("255,255,255", 32, 115, 12, .55), cloud("255,255,255", 54, 135, 9, .35)]
    },
    blue: {
      base: "linear-gradient(180deg,#f6fbfe 0%,#eaf3fa 34%,#dbeaf6 62%,#c9def0 100%)",
      glow: "radial-gradient(120% 60% at 50% 96%,rgba(186,208,228,.34) 0%,rgba(214,230,242,.18) 46%,rgba(255,255,255,0) 80%)",
      tint: "rgba(148,188,226,.58)",
      layers: [cloud("255,255,255", 30, 100, 12, .5)]
    },
    dusk: {
      base: "linear-gradient(180deg,#fff1e6 0%,#fddfca 26%,#f9c3a6 54%,#f2a684 80%,#ec9a74 100%)",
      glow: "radial-gradient(130% 66% at 50% 100%,rgba(255,172,132,.5) 0%,rgba(255,204,176,.26) 44%,rgba(255,255,255,0) 78%)",
      tint: "rgba(255,168,128,.62)",
      layers: [cloud("255,232,214", 30, 105, 10, .5), cloud("255,214,190", 50, 125, 8, .45), cloud("255,248,240", 68, 115, 7, .4)]
    },
    night: {
      base: "linear-gradient(180deg,#e9effc 0%,#dbe5f8 30%,#cbd9f4 62%,#bccdee 100%)",
      glow: "radial-gradient(70% 40% at 76% 16%,rgba(255,255,255,.9) 0%,rgba(226,234,250,.4) 34%,rgba(255,255,255,0) 70%)",
      tint: "rgba(138,168,220,.58)",
      layers: [cloud("255,255,255", 22, 80, 9, .45)]
    }
  };
  const stars = () => {
    const dots = [];
    for (let i = 0; i < 34; i++) {
      const x = (Math.random() * 100).toFixed(1);
      const y = (Math.random() * 56).toFixed(1);
      const r = (Math.random() * 1.6 + 1.1).toFixed(2);
      dots.push(`radial-gradient(circle at ${x}% ${y}%,rgba(255,255,255,.95) 0,transparent ${r}%)`);
    }
    return dots;
  };
  const curves = (color, n, height) => {
    const out = [];
    for (let i = 0; i < n; i++) {
      const y = 100 - i * (height / n);
      out.push(`radial-gradient(140% ${height}% at 50% ${y}%,${color} 0%,transparent 62%)`);
    }
    return out.join(",");
  };
  const extra = {
    grassland: () => curves("rgba(150,192,158,.22)", 3, 34),
    canyon: () => curves("rgba(208,158,120,.20)", 3, 30),
    plateau: () => curves("rgba(150,186,190,.20)", 3, 28),
    terrace: () => curves("rgba(164,194,132,.24)", 4, 40),
    beach: () => curves("rgba(148,192,210,.22)", 3, 26),
    night: stars
  };
  function window() {
    const forced = new URLSearchParams(location.search).get("scene");
    if (forced && scenes[forced]) return { key: forced, breathe: forced === "dawn" || forced === "dusk" };
    const h = new Date().getHours() + new Date().getMinutes() / 60;
    if (h >= 5 && h < 8) return { key: "dawn", breathe: true };
    if (h >= 8 && h < 12) return { key: pick(["grassland", "canyon", "plateau"]), breathe: false };
    if (h >= 12 && h < 17) return { key: pick(["terrace", "beach", "blue"]), breathe: false };
    if (h >= 17 && h < 18.5) return { key: "dusk", breathe: true };
    return { key: "night", breathe: false };
  }
  let lastKey = "";
  function apply() {
    const w = lastKey && scenes[lastKey] ? { key: lastKey, breathe: false } : window();
    lastKey = w.key;
    const s = scenes[w.key];
    const sky = document.getElementById("sky");
    const sky2 = document.getElementById("sky2");
    const sky3 = document.getElementById("sky3");
    const ex = extra[w.key] ? extra[w.key]() : "";
    const ly = s.layers ? s.layers.join(",") : "";
    const all = [s.base, ly, ex].filter(Boolean).join(",");
    sky.style.background = all;
    sky2.style.background = s.glow;
    if (sky3) {
      const b1 = sky3.querySelector(".b1"), b2 = sky3.querySelector(".b2"),
            b3 = sky3.querySelector(".b3");
      if (b1) b1.style.background = s.tint || s.glow;
      if (b2) b2.style.background = s.glow;
      if (b3) b3.style.background = s.tint || s.glow;
    }
    const dark = document.body.classList.contains("dark");
    const veil = dark
      ? "linear-gradient(rgba(19,23,29,.9),rgba(19,23,29,.95))"
      : "linear-gradient(rgba(255,255,255,.58),rgba(255,255,255,.46))";
    const dlgs = document.querySelectorAll(".dlg");
    for (let i = 0; i < dlgs.length; i++) dlgs[i].style.background = veil + "," + s.base;
    document.body.dataset.scene = w.key;
    return w.key;
  }
  return { apply };
})();
