import { useEffect, useRef, useState } from "react";
import { GLOSSARY } from "../texts.js";

/** Fachbegriff mit kleinem „?“, das per Klick/Tipp eine kurze Erklärung zeigt. */
export default function Term({ name, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const text = GLOSSARY[name];

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  if (!text) return children ?? name;
  return (
    <span className="term" ref={ref}>
      {children ?? name}
      <button type="button" className="term-q" aria-label={`Was bedeutet ${name}?`} aria-expanded={open}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((o) => !o); }}>?</button>
      {open && <span className="term-pop" role="tooltip"><strong>{name}</strong> {text}</span>}
    </span>
  );
}
