#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# WireGuard VPN server setup — run this ON your Oracle/VPS server
# Sets up a WireGuard server and generates a ready-to-scan Android QR code.
#
# Usage:
#   ssh ubuntu@<your-vps-ip> "bash -s" < setup_wireguard_vps.sh
#
# Or copy it to the VPS and run directly:
#   scp setup_wireguard_vps.sh ubuntu@<your-vps-ip>:~
#   ssh ubuntu@<your-vps-ip> chmod +x setup_wireguard_vps.sh
#   ssh ubuntu@<your-vps-ip> sudo ./setup_wireguard_vps.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (edit if needed) ───────────────────────────────────────────────────
WG_IFACE="wg0"
WG_PORT=51820
SERVER_VPN_IP="10.8.0.1/24"
CLIENT_VPN_IP="10.8.0.2/32"
DNS="1.1.1.1, 8.8.8.8"   # DNS servers clients will use (Cloudflare + Google)
CONFIG_DIR="/etc/wireguard"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { echo -e "\033[1;32m[+]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[!]\033[0m $*"; }
die()   { echo -e "\033[1;31m[✗]\033[0m $*" >&2; exit 1; }

[[ $EUID -ne 0 ]] && die "Run as root (sudo ./setup_wireguard_vps.sh)"

# ── Detect public IP ──────────────────────────────────────────────────────────
PUBLIC_IP=$(curl -4 -s https://ifconfig.me || hostname -I | awk '{print $1}')
info "Detected public IP: $PUBLIC_IP"

# Detect primary outbound interface (eth0, ens3, enp0s3, etc.)
PUB_IFACE=$(ip route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}' | head -1)
info "Outbound interface: $PUB_IFACE"

# ── Install dependencies ──────────────────────────────────────────────────────
info "Installing WireGuard and qrencode …"
apt-get update -qq
apt-get install -y -qq wireguard qrencode iptables

# ── Generate keys ─────────────────────────────────────────────────────────────
info "Generating server keys …"
SERVER_PRIV=$(wg genkey)
SERVER_PUB=$(echo "$SERVER_PRIV" | wg pubkey)

info "Generating Android client keys …"
CLIENT_PRIV=$(wg genkey)
CLIENT_PUB=$(echo "$CLIENT_PRIV" | wg pubkey)
CLIENT_PSK=$(wg genpsk)   # extra layer of symmetric encryption

# ── Server config ─────────────────────────────────────────────────────────────
info "Writing server config → $CONFIG_DIR/$WG_IFACE.conf"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

cat > "$CONFIG_DIR/$WG_IFACE.conf" <<EOF
[Interface]
Address    = $SERVER_VPN_IP
ListenPort = $WG_PORT
PrivateKey = $SERVER_PRIV

# NAT: route client traffic to the internet
PostUp   = iptables -A FORWARD -i $WG_IFACE -j ACCEPT; \
           iptables -A FORWARD -o $WG_IFACE -j ACCEPT; \
           iptables -t nat -A POSTROUTING -o $PUB_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i $WG_IFACE -j ACCEPT; \
           iptables -D FORWARD -o $WG_IFACE -j ACCEPT; \
           iptables -t nat -D POSTROUTING -o $PUB_IFACE -j MASQUERADE

[Peer]
# Android phone
PublicKey    = $CLIENT_PUB
PresharedKey = $CLIENT_PSK
AllowedIPs   = $CLIENT_VPN_IP
EOF

chmod 600 "$CONFIG_DIR/$WG_IFACE.conf"

# ── Enable IP forwarding ──────────────────────────────────────────────────────
info "Enabling IP forwarding …"
if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
sysctl -qw net.ipv4.ip_forward=1

# ── Open firewall port (ufw or iptables) ─────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
    info "Opening UFW port $WG_PORT/udp …"
    ufw allow "$WG_PORT/udp" > /dev/null
fi

# Oracle Cloud also has a VCN Security List — reminder printed at end

# ── Start and enable WireGuard ────────────────────────────────────────────────
info "Starting WireGuard …"
systemctl enable --now "wg-quick@$WG_IFACE"

# ── Generate Android client config ───────────────────────────────────────────
CLIENT_CONF=$(cat <<EOF
[Interface]
PrivateKey = $CLIENT_PRIV
Address    = $CLIENT_VPN_IP
DNS        = $DNS

[Peer]
PublicKey    = $SERVER_PUB
PresharedKey = $CLIENT_PSK
Endpoint     = $PUBLIC_IP:$WG_PORT
AllowedIPs   = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
EOF
)

# Save client config file
CLIENT_CONF_FILE="$HOME/android-wireguard.conf"
echo "$CLIENT_CONF" > "$CLIENT_CONF_FILE"
chmod 600 "$CLIENT_CONF_FILE"

# ── Print QR code ─────────────────────────────────────────────────────────────
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Scan this QR code with the WireGuard Android app  "
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "$CLIENT_CONF" | qrencode -t ansiutf8
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Client config also saved to: $CLIENT_CONF_FILE   "
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
info "WireGuard server is running. Status:"
wg show

# ── Oracle Cloud reminder ─────────────────────────────────────────────────────
warn "IMPORTANT — Oracle Cloud extra step:"
warn "  You must also open port $WG_PORT/UDP in your VCN Security List:"
warn "  OCI Console → Networking → Virtual Cloud Networks → your VCN"
warn "  → Security Lists → Default → Add Ingress Rule"
warn "    Source: 0.0.0.0/0   Protocol: UDP   Port: $WG_PORT"
echo
info "Done! On Android:"
info "  1. Install 'WireGuard' from Play Store (free, open source)"
info "  2. Tap '+' → 'Scan from QR code'"
info "  3. Scan the QR above"
info "  4. Toggle the tunnel ON"
info "  All Android traffic now exits through your VPS — FortiGuard bypassed."
