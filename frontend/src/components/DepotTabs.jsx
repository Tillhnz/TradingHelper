import { NavLink } from "react-router-dom";

/** Umschalter zwischen echtem Depot und Schattendepot. */
export default function DepotTabs() {
  return (
    <nav className="seg depot-tabs" aria-label="Depot-Ansicht">
      <NavLink to="/depot" end className={({ isActive }) => (isActive ? "on" : "")}>Mein Depot</NavLink>
      <NavLink to="/depot/schatten" className={({ isActive }) => (isActive ? "on" : "")}>Schattendepot</NavLink>
    </nav>
  );
}
