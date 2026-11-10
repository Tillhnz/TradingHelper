// Schlichte Linien-Symbole (24er Raster, Strich statt Fläche) – eigene Pfade, keine fremde Bibliothek.
const P = {
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  buy: "M12 8v8M8 12h8M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18",
  sell: "M8 12h8M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18",
  bell: "M6 17v-6a6 6 0 0 1 12 0v6l2 2H4zM10 21h4",
  star: "M12 3l2.6 5.6 6.2.7-4.6 4.2 1.3 6.1L12 16.5l-5.5 3.1 1.3-6.1-4.6-4.2 6.2-.7z",
  expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  pencil: "M4 20l4-1 11-11-3-3L5 16zM14 6l3 3",
  report: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  refresh: "M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16M20 20v-4h-4",
  phone: "M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2",
  zap: "M13 3L5 13h6l-1 8 8-10h-6z",
  up: "M5 16l5-5 3 3 6-6M14 8h5v5",
  down: "M5 8l5 5 3-3 6 6M14 16h5v-5",
  arrow: "M5 12h14M13 6l6 6-6 6",
  back: "M19 12H5M11 6l-6 6 6 6",
  chev: "M9 6l6 6-6 6",
  news: "M5 5h11v14H6a1 1 0 0 1-1-1zM16 9h3v9a1 1 0 0 1-2 0M8 9h5M8 12h5M8 15h3",
  wallet: "M4 7h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4zM4 7l11-3v3M16 13h2",
  flask: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M7.5 14h9",
  briefcase: "M4 8h16v11H4zM9 8V5h6v3M4 13h16",
  layers: "M12 4l8 4-8 4-8-4zM4 12l8 4 8-4M4 16l8 4 8-4",
  activity: "M3 12h4l3-7 4 14 3-7h4",
  shield: "M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z",
  target: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 7a5 5 0 1 0 0 10a5 5 0 1 0 0-10M12 11a1 1 0 1 0 0 2a1 1 0 1 0 0-2",
  clock: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 7v5l3 2",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 11v6M12 7.5v.5",
  alert: "M12 4l9 16H3zM12 10v4M12 17v.5",
  check: "M5 12l5 5 9-10",
  x: "M6 6l12 12M18 6L6 18",
  list: "M9 6h11M9 12h11M9 18h11M4 6h.5M4 12h.5M4 18h.5",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6",
  sparkles: "M12 3l1.8 4.7L18 9.5l-4.2 1.8L12 16l-1.8-4.7L6 9.5l4.2-1.8zM19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  sun: "M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  users: "M9 11a3.5 3.5 0 1 0 0-7a3.5 3.5 0 1 0 0 7M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14c2 .6 3 2.6 3 6",
};

/** <Icon name="bell" /> – erbt Farbe und Größe (1em) vom Text daneben. */
export default function Icon({ name, size, className = "", title }) {
  const d = P[name];
  if (!d) return null;
  return (
    <svg className={`icon ${className}`} viewBox="0 0 24 24" width={size || "1em"} height={size || "1em"}
      aria-hidden={title ? undefined : "true"} role={title ? "img" : undefined} focusable="false">
      {title && <title>{title}</title>}
      <path d={d} />
    </svg>
  );
}
