import { createContext, useContext } from "react";

// "simple" (Standard) blendet Fachdetails aus, "pro" zeigt Kerzen, Indikatoren und Kennzahlen.
const KEY = "tradehelper_mode";

export function loadMode() {
  try {
    return localStorage.getItem(KEY) === "pro" ? "pro" : "simple";
  } catch {
    return "simple";
  }
}

export function saveMode(mode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* privater Modus o. Ä. */
  }
}

export const ModeContext = createContext({ mode: "simple", setMode: () => {} });
export const useMode = () => useContext(ModeContext);
