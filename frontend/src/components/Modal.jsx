import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/** Einfaches Dialogfenster mit Fokus, Escape zum Schließen und Klick auf den Hintergrund. */
export default function Modal({ title, onClose, children, wide = false }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  // Nur beim Öffnen fokussieren, nicht bei jeder Aktualisierung der Seite im Hintergrund
  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.querySelector("input, select, textarea, button")?.focus();
    const onKey = (e) => { if (e.key === "Escape") closeRef.current(); };
    document.addEventListener("keydown", onKey);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.classList.remove("modal-open");
      prev?.focus?.();
    };
  }, []);
  // Direkt in <body> rendern: so liegt der Dialog immer über allem, egal in welcher Spalte er geöffnet wird
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) closeRef.current(); }}>
      <div className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="link" onClick={() => closeRef.current()} aria-label="Schließen">✕</button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
