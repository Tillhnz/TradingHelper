#!/usr/bin/env bash
# Installation in einem Debian/Ubuntu-LXC (oder VM) auf Proxmox – als root ausführen:
#   apt update && apt install -y git
#   git clone https://github.com/Tillhnz/tradinghelper.git /opt/tradehelper
#   bash /opt/tradehelper/deploy/install.sh
# Erneut ausführen = Update (git pull + Neuinstallation, .env bleibt erhalten).
set -euo pipefail

REPO="${REPO:-https://github.com/Tillhnz/tradinghelper.git}"
DIR=/opt/tradehelper

apt-get update
apt-get install -y --no-install-recommends git python3 python3-venv python3-pip ca-certificates

id tradehelper &>/dev/null || useradd -r -M -d "$DIR" -s /usr/sbin/nologin tradehelper

# Repo gehört nach dem ersten Lauf dem Service-User; ohne safe.directory verweigert git als root
git config --global --add safe.directory "$DIR"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO" "$DIR"
fi

python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip
"$DIR/.venv/bin/pip" install "$DIR"

[ -f "$DIR/.env" ] || cp "$DIR/.env.example" "$DIR/.env"
sed -i "s|^TH_DATA_DIR=.*|TH_DATA_DIR=$DIR/data|" "$DIR/.env"
mkdir -p "$DIR/data"
chown -R tradehelper:tradehelper "$DIR"

# Globaler Befehl `tradehelper` – läuft als Service-User mit dessen .env
cat > /usr/local/bin/tradehelper <<EOF
#!/usr/bin/env bash
cd $DIR && set -a && . $DIR/.env && set +a
if [ "\$(id -u)" -eq 0 ]; then exec runuser -u tradehelper -- $DIR/.venv/bin/tradehelper "\$@"; fi
exec $DIR/.venv/bin/tradehelper "\$@"
EOF
chmod +x /usr/local/bin/tradehelper

cp "$DIR/deploy/tradehelper.service" /etc/systemd/system/tradehelper.service
systemctl daemon-reload
systemctl enable tradehelper
systemctl restart tradehelper

echo
echo "Fertig. Nächste Schritte:"
echo "  1. nano $DIR/.env   (Finnhub-Key, ntfy-Topic)  → systemctl restart tradehelper"
echo "  2. tradehelper watchlist add AAPL MSFT SAP.DE"
echo "  3. tradehelper notify-test"
echo "  4. Browser: http://$(hostname -I | awk '{print $1}'):8080/chart/AAPL"
