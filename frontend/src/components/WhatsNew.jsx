import { useEffect, useState } from "react";
import { newSince } from "../changelog.js";
import Modal from "./Modal.jsx";

const KEY = "tradehelper_seen_version";
const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const write = (v) => { try { localStorage.setItem(KEY, v); } catch { /* privater Modus */ } };

/** Zeigt nach einem Update einmalig, was neu ist. */
export default function WhatsNew({ version }) {
  const [entries, setEntries] = useState([]);

  useEffect(() => {
    if (!version) return;
    const seen = read();
    if (seen === version) return;
    const list = newSince(seen, version);
    if (list.length) setEntries(list);
    else write(version);
  }, [version]);

  if (!entries.length) return null;
  const close = () => { write(version); setEntries([]); };
  return (
    <Modal title={entries.length === 1 ? `Neu in Version ${entries[0].version}` : "Was ist neu?"} onClose={close} wide>
      <div className="whatsnew">
        {entries.map((e) => (
          <section key={e.version}>
            <h3>{e.title} <span className="muted small">· {e.version} · {e.date}</span></h3>
            <ul>{e.items.map((t) => <li key={t}>{t}</li>)}</ul>
          </section>
        ))}
      </div>
      <div className="actions"><button className="btn primary" onClick={close}>Alles klar</button></div>
    </Modal>
  );
}
