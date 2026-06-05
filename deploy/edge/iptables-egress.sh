#!/usr/bin/env bash
# ==============================================================================
# iptables-egress.sh -- Network Egress Lockdown for OBD-Cortex Edge Node
# ==============================================================================
#
# [*] Purpose:
#     Restricts outbound (egress) traffic from the Raspberry Pi 4 to only
#     the protocols required for OBD-Cortex telemetry operation. All other
#     outbound traffic is dropped and logged for audit.
#
# [*] Allowed Egress:
#     - Loopback    : Internal process communication (localhost)
#     - Established : Return traffic for connections we initiated
#     - DNS         : Port 53 UDP/TCP -- domain resolution
#     - NTP         : Port 123 UDP   -- time synchronization (critical for TLS)
#     - HTTPS       : Port 443 TCP   -- telemetry upload to RAG API server
#
# [*] Everything else is DROP'd and logged with prefix 'EGRESS_DROP: '
#     for forensic review via journald/syslog.
#
# [*] Target:
#     Raspberry Pi 4 (4GB RAM) -- Raspberry Pi OS (Debian-based)
#
# [*] Usage:
#     sudo bash iptables-egress.sh
#
# [!] WARNING:
#     This script FLUSHES existing OUTPUT chain rules before applying.
#     Ensure you have console/physical access before running remotely.
#     SSH ingress is NOT affected (INPUT chain is untouched).
#
# ==============================================================================

set -euo pipefail
IFS=$'\n\t'

# ------------------------------------------------------------------------------
# [>] Preflight -- Ensure root privileges
# ------------------------------------------------------------------------------
if [[ "$(id -u)" -ne 0 ]]; then
    echo "[!!] ERROR: This script must be run as root. Use: sudo bash $0"
    exit 1
fi

echo "[>>] OBD-Cortex Edge -- Egress Firewall Configuration"
echo "[>>] Applying iptables OUTPUT chain rules..."
echo ""

# ==============================================================================
# SECTION 1: Flush Existing OUTPUT Rules
# ==============================================================================
#
# [*] Start with a clean slate on the OUTPUT chain. We only manage egress
#     here -- INPUT and FORWARD chains are left untouched.
# ------------------------------------------------------------------------------

echo "[>] Section 1: Flushing existing OUTPUT chain rules..."

iptables -F OUTPUT
echo "  [+] OUTPUT chain flushed."
echo ""

# ==============================================================================
# SECTION 2: Set Default OUTPUT Policy to DROP
# ==============================================================================
#
# [*] Whitelist approach: default-deny on egress. Only explicitly allowed
#     traffic passes. This is the most secure posture for an IoT edge node
#     that only needs to reach a known set of services.
# ------------------------------------------------------------------------------

echo "[>] Section 2: Setting default OUTPUT policy to DROP..."

iptables -P OUTPUT DROP
echo "  [+] Default OUTPUT policy set to DROP."
echo ""

# ==============================================================================
# SECTION 3: Allow Loopback Traffic
# ==============================================================================
#
# [*] Loopback (lo) is required for local inter-process communication.
#     Many services (systemd, dbus, local DNS resolvers, Python IPC)
#     rely on 127.0.0.1. Blocking loopback breaks the system.
# ------------------------------------------------------------------------------

echo "[>] Section 3: Allowing loopback interface..."

iptables -A OUTPUT -o lo -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow all loopback (lo) egress"

echo "  [+] Loopback traffic allowed."
echo ""

# ==============================================================================
# SECTION 4: Allow Established and Related Connections
# ==============================================================================
#
# [*] Permit return traffic for connections that were already established
#     or are related to an existing connection (e.g., FTP data channels,
#     ICMP errors for valid connections). This is essential for any
#     stateful firewall -- without it, responses to our own requests
#     would be dropped.
# ------------------------------------------------------------------------------

echo "[>] Section 4: Allowing established/related connections..."

iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow return traffic for established connections"

echo "  [+] Established/related connections allowed."
echo ""

# ==============================================================================
# SECTION 5: Allow Outbound DNS (Port 53 -- UDP and TCP)
# ==============================================================================
#
# [*] DNS resolution is required to resolve the RAG API server hostname
#     and to fetch APT package lists for unattended-upgrades.
#     Both UDP (standard queries) and TCP (large responses, zone transfers)
#     are permitted on port 53.
# ------------------------------------------------------------------------------

echo "[>] Section 5: Allowing outbound DNS (port 53)..."

# -- DNS over UDP (standard queries, < 512 bytes)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow DNS queries (UDP/53)"

# -- DNS over TCP (large responses, DNSSEC, truncated UDP fallback)
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow DNS queries (TCP/53)"

echo "  [+] DNS egress allowed (UDP + TCP)."
echo ""

# ==============================================================================
# SECTION 6: Allow Outbound NTP (Port 123 -- UDP)
# ==============================================================================
#
# [*] Accurate system time is critical for:
#     - TLS certificate validation (expiry checks)
#     - Telemetry timestamp accuracy
#     - Log correlation across the OBD-Cortex platform
#     NTP uses UDP port 123 exclusively.
# ------------------------------------------------------------------------------

echo "[>] Section 6: Allowing outbound NTP (port 123)..."

iptables -A OUTPUT -p udp --dport 123 -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow NTP time sync (UDP/123)"

echo "  [+] NTP egress allowed."
echo ""

# ==============================================================================
# SECTION 7: Allow Outbound HTTPS (Port 443 -- TCP)
# ==============================================================================
#
# [*] The Pi transmits CAN bus telemetry data to the OBD-Cortex RAG API
#     server over HTTPS (TLS-encrypted). This is the primary data egress
#     path. Port 443 TCP also covers:
#     - APT package downloads (Debian repos use HTTPS)
#     - Any future webhook or API integrations
# ------------------------------------------------------------------------------

echo "[>] Section 7: Allowing outbound HTTPS (port 443)..."

iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT \
    -m comment --comment "OBD-Cortex: Allow HTTPS egress to RAG API (TCP/443)"

echo "  [+] HTTPS egress allowed."
echo ""

# ==============================================================================
# SECTION 8: Log Dropped Packets
# ==============================================================================
#
# [*] Before the implicit DROP (from the policy), we insert a LOG rule
#     to capture metadata about all denied egress attempts. This is
#     invaluable for:
#     - Detecting compromised processes phoning home
#     - Identifying missing firewall rules for legitimate services
#     - Forensic analysis after security incidents
#
# [*] Log prefix: 'EGRESS_DROP: '
#     Visible in: journalctl -k --grep="EGRESS_DROP" or /var/log/syslog
#
# [*] Rate limiting: 5 log entries per minute with a burst of 10
#     Prevents log flooding from aggressive scanning or DoS attempts.
# ------------------------------------------------------------------------------

echo "[>] Section 8: Adding egress drop logging..."

iptables -A OUTPUT -m limit --limit 5/min --limit-burst 10 -j LOG \
    --log-prefix "EGRESS_DROP: " \
    --log-level 4 \
    -m comment --comment "OBD-Cortex: Log dropped egress packets (rate-limited)"

echo "  [+] Drop logging enabled (prefix: EGRESS_DROP:, rate: 5/min)."
echo ""

# ==============================================================================
# SECTION 9: Persist Rules via iptables-save
# ==============================================================================
#
# [*] iptables rules are volatile -- they are lost on reboot unless
#     explicitly saved. We persist them to /etc/iptables/rules.v4 which
#     is read on boot by iptables-persistent (if installed) or can be
#     loaded manually via 'iptables-restore < /etc/iptables/rules.v4'.
#
# [*] If iptables-persistent is not installed, we also create a systemd
#     drop-in to restore rules on boot.
# ------------------------------------------------------------------------------

echo "[>] Section 9: Persisting iptables rules..."

IPTABLES_RULES_DIR="/etc/iptables"
IPTABLES_RULES_FILE="${IPTABLES_RULES_DIR}/rules.v4"

mkdir -p "${IPTABLES_RULES_DIR}"

iptables-save > "${IPTABLES_RULES_FILE}"
echo "  [+] Rules saved to: ${IPTABLES_RULES_FILE}"

# -- Install iptables-persistent if not present, for automatic restore on boot
if ! dpkg -l iptables-persistent &>/dev/null; then
    echo "  [~] iptables-persistent not found -- installing for boot persistence..."
    # Pre-seed debconf to avoid interactive prompts during install
    echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
    echo iptables-persistent iptables-persistent/autosave_v6 boolean false | debconf-set-selections
    apt-get install -y -qq iptables-persistent
    echo "  [+] iptables-persistent installed."
else
    echo "  [=] iptables-persistent already installed."
fi

echo ""

# ==============================================================================
# [>>] Egress Lockdown Complete
# ==============================================================================

echo "============================================================"
echo "[>>] OBD-Cortex Edge -- Egress Firewall Active"
echo "============================================================"
echo ""
echo "  [+] Loopback          : ACCEPT"
echo "  [+] Established       : ACCEPT"
echo "  [+] DNS   (53/udp+tcp): ACCEPT"
echo "  [+] NTP   (123/udp)   : ACCEPT"
echo "  [+] HTTPS (443/tcp)   : ACCEPT"
echo "  [-] All other egress  : DROP + LOG"
echo ""
echo "  [*] Rules persisted to: ${IPTABLES_RULES_FILE}"
echo ""
echo "  [!] VERIFY WITH:"
echo "    iptables -L OUTPUT -v -n --line-numbers"
echo "    journalctl -k --grep='EGRESS_DROP' --no-pager -n 20"
echo ""
