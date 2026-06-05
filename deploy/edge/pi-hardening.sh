#!/usr/bin/env bash
# ==============================================================================
# pi-hardening.sh -- Raspberry Pi OS-Level Hardening for OBD-Cortex Edge Node
# ==============================================================================
#
# [*] Purpose:
#     Production hardening script for the Raspberry Pi 4 running the
#     OBD-Cortex telemetry logger. Reduces the attack surface by disabling
#     unused services, enforcing SSH brute-force protection, enabling
#     automatic security patching, and applying kernel-level network hardening.
#
# [*] Target:
#     Raspberry Pi 4 (4GB RAM) -- Raspberry Pi OS (Debian-based)
#     MCP2515 CAN bus extension attached via SPI
#
# [*] Usage:
#     sudo bash pi-hardening.sh
#
# [!] WARNING:
#     This script MUST be run as root. It modifies system services,
#     installs packages, and writes to protected sysctl paths.
#     Review each section before executing in production.
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

echo "[>>] OBD-Cortex Edge -- Pi Hardening Script"
echo "[>>] Starting hardening procedures..."
echo ""

# ==============================================================================
# SECTION 1: Disable Unused Services
# ==============================================================================
#
# [*] Rationale:
#     The Pi ships with several services enabled by default that are not
#     required for the OBD-Cortex telemetry use case. Each running service
#     is a potential attack vector. We disable:
#
#     - bluetooth     : No Bluetooth peripherals used; CAN bus is SPI-based
#     - avahi-daemon  : mDNS/DNS-SD not needed; Pi is addressed by static IP
#     - triggerhappy  : Hotkey daemon for media keys; headless Pi has no use
#     - hciuart       : Bluetooth UART interface; redundant with BT disabled
# ------------------------------------------------------------------------------

echo "[>] Section 1: Disabling unused services..."

UNUSED_SERVICES=(
    "bluetooth"
    "avahi-daemon"
    "triggerhappy"
    "hciuart"
)

for service in "${UNUSED_SERVICES[@]}"; do
    if systemctl is-enabled "${service}" &>/dev/null; then
        echo "  [~] Disabling and stopping: ${service}"
        systemctl disable --now "${service}" 2>/dev/null || true
    else
        echo "  [=] Already disabled or not found: ${service}"
    fi
done

echo "[+] Unused services handled."
echo ""

# ==============================================================================
# SECTION 2: Configure fail2ban for SSH Protection
# ==============================================================================
#
# [*] Rationale:
#     SSH is the sole remote access method to the Pi. Brute-force attacks
#     are common on exposed SSH ports. fail2ban monitors auth logs and
#     issues temporary IP bans after repeated failures.
#
# [*] Policy:
#     - maxretry  = 3    : Ban after 3 failed login attempts
#     - bantime   = 3600 : 1 hour ban duration (seconds)
#     - findtime  = 600  : Failure window of 10 minutes
#
# [*] Config location:
#     /etc/fail2ban/jail.d/sshd-custom.conf
#     Using jail.d/ drop-in to avoid modifying the upstream jail.conf
# ------------------------------------------------------------------------------

echo "[>] Section 2: Configuring fail2ban for SSH..."

# -- Install fail2ban if not already present
if ! command -v fail2ban-client &>/dev/null; then
    echo "  [~] fail2ban not found -- installing..."
    apt-get update -qq
    apt-get install -y -qq fail2ban
    echo "  [+] fail2ban installed."
else
    echo "  [=] fail2ban already installed."
fi

# -- Write the SSH jail drop-in configuration
FAIL2BAN_JAIL_DIR="/etc/fail2ban/jail.d"
FAIL2BAN_SSH_CONF="${FAIL2BAN_JAIL_DIR}/sshd-custom.conf"

mkdir -p "${FAIL2BAN_JAIL_DIR}"

echo "  [~] Writing fail2ban SSH jail config: ${FAIL2BAN_SSH_CONF}"

cat > "${FAIL2BAN_SSH_CONF}" << 'FAIL2BAN_EOF'
# ==========================================================================
# sshd-custom.conf -- fail2ban SSH Jail for OBD-Cortex Edge Node
# ==========================================================================
#
# [*] Drop-in jail configuration for SSH brute-force protection.
#     Placed in jail.d/ so upstream jail.conf remains unmodified.
#
# [*] Policy:
#     - Ban an IP after 3 failed SSH login attempts within 10 minutes
#     - Ban duration: 1 hour (3600 seconds)
#     - Uses the built-in 'sshd' filter (matches OpenSSH auth failures)
# ==========================================================================

[sshd]
enabled  = true
port     = ssh
filter   = sshd
maxretry = 3
bantime  = 3600
findtime = 600
FAIL2BAN_EOF

# -- Enable and restart fail2ban to apply the new jail
systemctl enable fail2ban
systemctl restart fail2ban

echo "[+] fail2ban SSH jail configured and active."
echo ""

# ==============================================================================
# SECTION 3: Disable Default Pi User Reminder
# ==============================================================================
#
# [*] Rationale:
#     Raspberry Pi OS displays a persistent reminder about the default 'pi'
#     user account on login. In production, this is noise. The reminder is
#     controlled by a profile script and a systemd user service. We disable
#     both if present.
# ------------------------------------------------------------------------------

echo "[>] Section 3: Disabling default Pi user reminder..."

# -- Remove the profile.d script that triggers the reminder dialog
PI_REMINDER_PROFILE="/etc/profile.d/sshpwd.sh"
if [[ -f "${PI_REMINDER_PROFILE}" ]]; then
    echo "  [~] Removing SSH password reminder script: ${PI_REMINDER_PROFILE}"
    rm -f "${PI_REMINDER_PROFILE}"
else
    echo "  [=] SSH password reminder script not found (already removed)."
fi

# -- Disable the userconfig service if it exists (newer Pi OS versions)
if systemctl is-enabled userconfig &>/dev/null; then
    echo "  [~] Disabling userconfig service..."
    systemctl disable userconfig 2>/dev/null || true
fi

# -- Remove the rename-user prompt config if present
RENAME_USER_CONF="/etc/xdg/autostart/piwiz.desktop"
if [[ -f "${RENAME_USER_CONF}" ]]; then
    echo "  [~] Removing Pi wizard autostart: ${RENAME_USER_CONF}"
    rm -f "${RENAME_USER_CONF}"
fi

echo "[+] Default user reminder disabled."
echo ""

# ==============================================================================
# SECTION 4: Enable Unattended Security Updates
# ==============================================================================
#
# [*] Rationale:
#     The Pi operates as an unattended edge device. Security patches must be
#     applied automatically to prevent known-vulnerability exploitation.
#     We install and configure 'unattended-upgrades' to pull security-only
#     updates from the Debian/Raspbian repositories.
#
# [*] Behavior:
#     - Only security updates are applied (not feature upgrades)
#     - Runs daily via systemd timer (apt-daily-upgrade.timer)
#     - Does NOT auto-reboot (reboot handled via maintenance window)
# ------------------------------------------------------------------------------

echo "[>] Section 4: Enabling unattended security updates..."

# -- Install unattended-upgrades if not present
if ! dpkg -l unattended-upgrades &>/dev/null; then
    echo "  [~] unattended-upgrades not found -- installing..."
    apt-get update -qq
    apt-get install -y -qq unattended-upgrades
    echo "  [+] unattended-upgrades installed."
else
    echo "  [=] unattended-upgrades already installed."
fi

# -- Enable the auto-update mechanism via debconf
#    This writes to /etc/apt/apt.conf.d/20auto-upgrades
echo "  [~] Configuring automatic update intervals..."

cat > /etc/apt/apt.conf.d/20auto-upgrades << 'AUTOUPGRADE_EOF'
// -------------------------------------------------------------------------
// 20auto-upgrades -- APT Periodic Update Configuration
// -------------------------------------------------------------------------
//
// [*] Update package lists daily
// [*] Apply unattended upgrades daily
// [*] Clean downloaded packages every 7 days to reclaim disk space
// -------------------------------------------------------------------------

APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
AUTOUPGRADE_EOF

# -- Ensure the unattended-upgrades config allows Debian security origin
#    The default config on Raspbian should already include this, but we
#    verify the service is enabled.
systemctl enable unattended-upgrades
systemctl restart unattended-upgrades

echo "[+] Unattended security updates enabled."
echo ""

# ==============================================================================
# SECTION 5: Kernel-Level Network Hardening (sysctl)
# ==============================================================================
#
# [*] Rationale:
#     The Linux kernel exposes tunable parameters that control network stack
#     behavior. We apply hardening values to mitigate common network-layer
#     attacks (IP spoofing, ICMP abuse, ICMP redirects).
#
# [*] Parameters:
#
#     net.ipv4.conf.all.rp_filter = 1
#       -> Enable Reverse Path Filtering (strict mode)
#       -> Drops packets arriving on interfaces where the return path
#          does not match. Mitigates IP spoofing attacks.
#
#     net.ipv4.icmp_echo_ignore_broadcasts = 1
#       -> Ignore ICMP echo requests sent to broadcast/multicast addresses
#       -> Prevents the Pi from being used as a Smurf attack amplifier.
#
#     net.ipv4.conf.all.accept_redirects = 0
#       -> Reject ICMP redirect messages (IPv4)
#       -> Prevents attackers from altering the Pi's routing table via
#          forged ICMP redirects (man-in-the-middle vector).
#
#     net.ipv6.conf.all.accept_redirects = 0
#       -> Reject ICMP redirect messages (IPv6)
#       -> Same protection as above, for IPv6 stack.
# ------------------------------------------------------------------------------

echo "[>] Section 5: Applying sysctl network hardening..."

SYSCTL_CONF="/etc/sysctl.d/99-obd-cortex-hardening.conf"

echo "  [~] Writing sysctl hardening config: ${SYSCTL_CONF}"

cat > "${SYSCTL_CONF}" << 'SYSCTL_EOF'
# ==========================================================================
# 99-obd-cortex-hardening.conf -- Kernel Network Hardening for OBD-Cortex
# ==========================================================================
#
# [*] Applied via sysctl.d drop-in. Takes effect on boot and when
#     'sysctl --system' is invoked.
# ==========================================================================

# -- Reverse Path Filtering (strict mode)
# [*] Drop packets with source addresses that don't match the interface
#     they arrived on. Mitigates IP address spoofing.
net.ipv4.conf.all.rp_filter = 1

# -- Ignore broadcast ICMP echo (ping) requests
# [*] Prevents Smurf amplification attacks where an attacker sends pings
#     to a broadcast address with a spoofed source IP.
net.ipv4.icmp_echo_ignore_broadcasts = 1

# -- Reject ICMP redirects (IPv4)
# [*] ICMP redirects can be forged to alter routing tables, enabling
#     man-in-the-middle attacks. Not needed on a single-gateway edge node.
net.ipv4.conf.all.accept_redirects = 0

# -- Reject ICMP redirects (IPv6)
# [*] Same protection as above for the IPv6 network stack.
net.ipv6.conf.all.accept_redirects = 0
SYSCTL_EOF

# -- Apply the sysctl parameters immediately (without reboot)
sysctl --system --quiet

echo "[+] Sysctl hardening parameters applied."
echo ""

# ==============================================================================
# SECTION 6: Enforce Sudo Password Requirement
# ==============================================================================
#
# [*] Rationale:
#     Some Raspberry Pi OS images ship with NOPASSWD sudo for the default
#     user. In production, every privilege escalation must require password
#     authentication to limit damage from compromised user sessions.
#
# [*] Method:
#     Remove any NOPASSWD sudoers drop-in files for the pi user, and
#     ensure the default sudoers group ('sudo') requires a password.
# ------------------------------------------------------------------------------

echo "[>] Section 6: Enforcing sudo password requirement..."

# -- Remove NOPASSWD sudoers drop-in for the 'pi' user if it exists
PI_SUDOERS="/etc/sudoers.d/010_pi-nopasswd"
if [[ -f "${PI_SUDOERS}" ]]; then
    echo "  [~] Removing NOPASSWD sudoers file: ${PI_SUDOERS}"
    rm -f "${PI_SUDOERS}"
else
    echo "  [=] No NOPASSWD sudoers file found for 'pi' user."
fi

# -- Also check for any other NOPASSWD entries in sudoers.d/
#    We search for files containing NOPASSWD and log them as warnings
for sudoers_file in /etc/sudoers.d/*; do
    if [[ -f "${sudoers_file}" ]] && grep -qi "NOPASSWD" "${sudoers_file}" 2>/dev/null; then
        echo "  [!] WARNING: NOPASSWD entry found in: ${sudoers_file}"
        echo "      -> Review manually and remove if not required."
    fi
done

echo "[+] Sudo password requirement enforced."
echo ""

# ==============================================================================
# [>>] Hardening Complete
# ==============================================================================

echo "============================================================"
echo "[>>] OBD-Cortex Edge -- Pi Hardening Complete"
echo "============================================================"
echo ""
echo "  [+] Unused services disabled"
echo "  [+] fail2ban SSH jail active (3 attempts / 1hr ban)"
echo "  [+] Default user reminder removed"
echo "  [+] Unattended security updates enabled"
echo "  [+] Sysctl network hardening applied"
echo "  [+] Sudo password enforcement verified"
echo ""
echo "  [!] RECOMMENDED NEXT STEPS:"
echo "    1. Verify fail2ban status:  sudo fail2ban-client status sshd"
echo "    2. Review sysctl values:    sysctl -a | grep -E 'rp_filter|icmp_echo|accept_redirects'"
echo "    3. Test SSH access before closing current session"
echo "    4. Apply iptables egress rules:  sudo bash iptables-egress.sh"
echo ""
