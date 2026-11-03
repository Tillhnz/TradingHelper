#!/usr/bin/env bash
# TradeHelper – Installations- und Hilfsskript
#
# Am einfachsten auf dem Proxmox-Host: proxmox/tradehelper-lxc.sh (legt den Container an und ruft dieses Skript auf).
#
# Direkt installieren (auf einer frischen Debian-/Ubuntu-Maschine oder in einem LXC):
#   curl -fsSL https://raw.githubusercontent.com/Tillhnz/tradinghelper/main/install.sh | bash
#   oder im geklonten Projektordner: ./install.sh
#
# Weitere Befehle (im Projektordner):
#   ./install.sh update          Neueste Version holen und neu starten (geht auch per Knopf in der Administration)
#   ./install.sh backup          Datenbank sichern (Ordner backups/)
#   ./install.sh restore <datei> Sicherung zurückspielen (ersetzt alle aktuellen Daten)
#   ./install.sh reset-login     Konto löschen, beim nächsten Aufruf neu anlegen (Passwort vergessen)
#   ./install.sh logs            Protokolle anzeigen
#
# Umgebungsvariablen (optional):
#   TRADEHELPER_DIR=<ordner>     Zielordner bei der Installation (Standard: ~/tradinghelper)
#   TRADEHELPER_REPO=<git-url>   Anderes Repository verwenden
set -euo pipefail

REPO_URL="${TRADEHELPER_REPO:-https://github.com/Tillhnz/tradinghelper.git}"
DEFAULT_DIR="${TRADEHELPER_DIR:-$HOME/tradinghelper}"
DATA_UID=10001

info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m✘\033[0m %s\n' "$*" >&2; exit 1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else die "Dafür sind Root-Rechte nötig. Melde dich als root an oder installiere sudo."; fi
}

random_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

script_dir=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$script_dir" ] && [ -f "$script_dir/docker-compose.yml" ]; then APP_DIR="$script_dir"; else APP_DIR="$DEFAULT_DIR"; fi

get_env() { [ -f "$APP_DIR/.env" ] || return 0; grep -E "^$1=" "$APP_DIR/.env" | head -n 1 | cut -d= -f2- || true; }

set_env() {
  local key="$1" value="$2" file="$APP_DIR/.env"
  if grep -q "^${key}=" "$file"; then sed -i "s|^${key}=.*|${key}=${value}|" "$file"; else printf '%s=%s\n' "$key" "$value" >> "$file"; fi
}

web_port() { local p; p="$(get_env WEB_PORT)"; printf '%s' "${p:-8080}"; }
local_ip() { local ip; ip="$(hostname -I 2>/dev/null | awk '{print $1}')" || ip=""; printf '%s' "${ip:-localhost}"; }

ensure_packages() {
  local missing=()
  command -v git >/dev/null 2>&1 || missing+=(git)
  command -v curl >/dev/null 2>&1 || missing+=(curl)
  if [ "${#missing[@]}" -gt 0 ]; then
    command -v apt-get >/dev/null 2>&1 || die "Bitte installiere ${missing[*]} und starte das Skript erneut."
    info "Installiere ${missing[*]} …"
    as_root apt-get update -qq
    as_root apt-get install -y -qq "${missing[@]}"
  fi
}

pick_docker() {
  if docker info >/dev/null 2>&1; then DOCKER=(docker)
  elif as_root docker info >/dev/null 2>&1; then DOCKER=(as_root docker)
  else die "Der Docker-Dienst antwortet nicht. Prüfe mit: systemctl status docker"; fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    if command -v pveversion >/dev/null 2>&1; then
      die "Das hier ist ein Proxmox-Host. Bitte nicht direkt darauf installieren, sondern: bash proxmox/tradehelper-lxc.sh"
    fi
    info "Installiere Docker (offizielles Skript von get.docker.com) …"
    local tmp; tmp="$(mktemp)"
    curl -fsSL https://get.docker.com -o "$tmp"
    as_root sh "$tmp"
    rm -f "$tmp"
  fi
  pick_docker
  "${DOCKER[@]}" compose version >/dev/null 2>&1 || die "Docker Compose fehlt (docs.docker.com/compose/install)."
  ok "Docker ist bereit."
}

ensure_repo() {
  [ -f "$APP_DIR/docker-compose.yml" ] && return
  info "Lade TradeHelper nach $APP_DIR …"
  git clone "$REPO_URL" "$APP_DIR"
}

setup_env() {
  local env="$APP_DIR/.env"
  if [ -f "$env" ]; then ok ".env existiert bereits und bleibt unverändert."; else
    cp "$APP_DIR/.env.example" "$env"
    chmod 600 "$env"
    set_env SECRET_KEY "$(random_hex 32)"
    ok ".env mit zufälligem Schlüssel angelegt."
  fi
  set_env PROJECT_DIR "$APP_DIR"
  mkdir -p "$APP_DIR/data" "$APP_DIR/backups"
  as_root chown "$DATA_UID:$DATA_UID" "$APP_DIR/data"
}

start_stack() {
  info "Baue und starte TradeHelper (der erste Start dauert einige Minuten) …"
  (cd "$APP_DIR" && "${DOCKER[@]}" compose up -d --build --remove-orphans)
}

wait_healthy() {
  local port; port="$(web_port)"
  for _ in $(seq 1 60); do
    curl -fsS "http://localhost:${port}/api/health" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

report_start() {
  info "Warte, bis TradeHelper antwortet …"
  if wait_healthy; then ok "TradeHelper läuft."; else
    warn "TradeHelper antwortet noch nicht. Die letzten Protokollzeilen:"
    (cd "$APP_DIR" && "${DOCKER[@]}" compose logs --tail 40) || true
    die "Start nicht bestätigt. Mehr mit: ./install.sh logs"
  fi
}

require_install() {
  [ -f "$APP_DIR/docker-compose.yml" ] && [ -f "$APP_DIR/.env" ] || die "Keine Installation in $APP_DIR gefunden. Starte zuerst: ./install.sh"
  command -v docker >/dev/null 2>&1 || die "Docker ist nicht installiert."
  pick_docker
}

cmd_install() {
  ensure_packages
  ensure_docker
  ensure_repo
  setup_env
  start_stack
  report_start
  cat <<EOF

────────────────────────────────────────────────────────
 TradeHelper ist installiert.

 Öffnen:   http://$(local_ip):$(web_port)
 Ordner:   ${APP_DIR}

 1. Adresse öffnen und dein Konto anlegen.
 2. Unter Einstellungen ntfy-Topic und Finnhub-Schlüssel eintragen.
 3. Watchlist füllen – ab morgen früh kommt der Report.

 Updates: per Knopf unter Administration (oder ./install.sh update)
────────────────────────────────────────────────────────
EOF
}

cmd_update() {
  require_install
  if [ -d "$APP_DIR/.git" ]; then info "Hole die neueste Version …"; git -C "$APP_DIR" pull --ff-only; fi
  setup_env
  start_stack
  report_start
  ok "Update abgeschlossen."
}

cmd_backup() {
  require_install
  [ -f "$APP_DIR/data/tradehelper.db" ] || die "Es gibt noch keine Datenbank."
  local f; f="$APP_DIR/backups/tradehelper-$(date +%Y%m%d-%H%M%S).db.gz"
  mkdir -p "$APP_DIR/backups"
  (cd "$APP_DIR" && "${DOCKER[@]}" compose exec -T backend python -c \
    "import sqlite3,sys; s=sqlite3.connect('/data/tradehelper.db'); d=sqlite3.connect('/tmp/b.db'); s.backup(d); d.close()" \
    && "${DOCKER[@]}" compose exec -T backend cat /tmp/b.db | gzip > "$f" \
    && "${DOCKER[@]}" compose exec -T backend rm -f /tmp/b.db)
  chmod 600 "$f"
  ok "Gesichert: $f"
}

cmd_restore() {
  [ -n "${1:-}" ] && [ -f "$1" ] || die "Bitte eine Sicherung angeben, z. B.: ./install.sh restore backups/tradehelper-20261102-070000.db.gz"
  require_install
  gunzip -t "$1" 2>/dev/null || die "Die Datei ist keine gültige Sicherung."
  warn "Das ersetzt ALLE aktuellen Daten durch den Stand der Sicherung."
  read -r -p "Zum Fortfahren „ja“ eingeben: " answer </dev/tty
  [ "$answer" = "ja" ] || die "Abgebrochen."
  (cd "$APP_DIR" && "${DOCKER[@]}" compose stop backend)
  gunzip -c "$1" > "$APP_DIR/data/tradehelper.db"
  rm -f "$APP_DIR/data/tradehelper.db-journal" "$APP_DIR/data/tradehelper.db-wal" "$APP_DIR/data/tradehelper.db-shm"
  as_root chown "$DATA_UID:$DATA_UID" "$APP_DIR/data/tradehelper.db"
  (cd "$APP_DIR" && "${DOCKER[@]}" compose start backend)
  ok "Sicherung zurückgespielt."
}

cmd_reset_login() {
  require_install
  (cd "$APP_DIR" && "${DOCKER[@]}" compose exec -T backend python -m app.cli reset-login)
}

cmd_logs() {
  require_install
  (cd "$APP_DIR" && "${DOCKER[@]}" compose logs --tail 100 -f)
}

case "${1:-install}" in
  install) cmd_install ;;
  update) cmd_update ;;
  backup) cmd_backup ;;
  restore) cmd_restore "${2:-}" ;;
  reset-login) cmd_reset_login ;;
  logs) cmd_logs ;;
  -h|--help|help) sed -n '2,20p' "${BASH_SOURCE[0]:-$0}" | sed 's/^# \{0,1\}//' ;;
  *) die "Unbekannter Befehl: $1 (erlaubt: install, update, backup, restore, reset-login, logs)" ;;
esac
