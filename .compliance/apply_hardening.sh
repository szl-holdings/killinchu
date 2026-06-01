#!/bin/bash
# DISA STIG image-level hardening — applied offline to a UBI9 rootfs copy.
# Mirrors the concrete operations added to the flagship Dockerfiles (Part A.4):
#  - login.defs password aging + umask + fail delay
#  - umask in /etc/profile, /etc/bashrc, /etc/csh.cshrc
#  - DoD login banner /etc/issue + /etc/issue.net
#  - disable unused kernel modules via /etc/modprobe.d
#  - sysctl hardening via /etc/sysctl.d
#  - file permissions on /etc config files (passwd/shadow/group/gshadow)
#  - cron + crypto-policy config
# Author: Yachay <yachay@szlholdings.dev>  (DCO signed)  ADDITIVE
set -u
R="$1"   # rootfs path

mkdir -p "$R/etc" "$R/etc/modprobe.d" "$R/etc/sysctl.d" "$R/etc/security" "$R/etc/cron.d"

# ---- login.defs (password aging, min length, umask, fail delay) ----
LD="$R/etc/login.defs"
touch "$LD"
set_ld(){ key="$1"; val="$2"; if grep -qE "^[[:space:]]*$key[[:space:]]" "$LD"; then sed -i -E "s|^[[:space:]]*$key[[:space:]].*|$key $val|" "$LD"; else echo "$key $val" >> "$LD"; fi; }
set_ld PASS_MAX_DAYS 60
set_ld PASS_MIN_DAYS 1
set_ld PASS_MIN_LEN 15
set_ld FAIL_DELAY 4
set_ld UMASK 077
set_ld FAILLOG_ENAB yes

# ---- umask in shell init files ----
for f in profile bashrc csh.cshrc; do
  fp="$R/etc/$f"; touch "$fp"
  if grep -qiE "umask" "$fp"; then sed -i -E "s|umask[[:space:]]+[0-7]{3,4}|umask 077|gi" "$fp"; else echo "umask 077" >> "$fp"; fi
done

# ---- DoD Standard Mandatory Notice & Consent Banner ----
BANNER='You are accessing a U.S. Government (USG) Information System (IS) that is provided for USG-authorized use only. By using this IS (which includes any device attached to this IS), you consent to the following conditions: -The USG routinely intercepts and monitors communications on this IS for purposes including, but not limited to, penetration testing, COMSEC monitoring, network operations and defense, personnel misconduct (PM), law enforcement (LE), and counterintelligence (CI) investigations.'
printf '%s\n' "$BANNER" > "$R/etc/issue"
printf '%s\n' "$BANNER" > "$R/etc/issue.net"

# ---- disable unused kernel modules ----
for m in atm bluetooth can sctp usb-storage cramfs firewire-core tipc dccp rds squashfs udf; do
  echo "install $m /bin/false" >  "$R/etc/modprobe.d/75-stig-$m.conf"
  echo "blacklist $m"          >> "$R/etc/modprobe.d/75-stig-$m.conf"
done

# ---- sysctl hardening ----
cat > "$R/etc/sysctl.d/75-stig-hardening.conf" <<'SYS'
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.suid_dumpable = 0
kernel.core_pattern = |/bin/false
kernel.kexec_load_disabled = 1
kernel.kptr_restrict = 1
kernel.randomize_va_space = 2
kernel.unprivileged_bpf_disabled = 1
kernel.yama.ptrace_scope = 1
kernel.dmesg_restrict = 1
kernel.perf_event_paranoid = 2
net.core.bpf_jit_harden = 2
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.all.forwarding = 0
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.default.log_martians = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_syncookies = 1
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.all.forwarding = 0
net.ipv6.conf.default.accept_ra = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv6.conf.default.accept_source_route = 0
user.max_user_namespaces = 0
SYS

# ---- file permissions on critical /etc config files ----
for f in passwd group; do [ -e "$R/etc/$f" ] && chmod 0644 "$R/etc/$f"; done
for f in shadow gshadow; do [ -e "$R/etc/$f" ] && chmod 0000 "$R/etc/$f"; done
[ -e "$R/etc/ssh/sshd_config" ] && chmod 0600 "$R/etc/ssh/sshd_config"
[ -d "$R/etc/cron.d" ] && chmod 0700 "$R/etc/cron.d"
[ -e "$R/etc/crontab" ] && chmod 0600 "$R/etc/crontab"

# ---- remove SUID/SGID bits from non-essential binaries (STIG: minimize SUID) ----
# (offline: clear setuid on common offenders if present)
for b in usr/bin/chage usr/bin/gpasswd usr/bin/wall usr/bin/write usr/bin/mount usr/bin/umount usr/bin/su; do
  [ -e "$R/$b" ] && chmod u-s,g-s "$R/$b" 2>/dev/null
done

# ---- crypto policy marker (FIPS intent; honest: full FIPS needs kernel boot) ----
mkdir -p "$R/etc/crypto-policies"
echo "FIPS" > "$R/etc/crypto-policies/config"

# ---- AIDE cron marker (config-level) ----
echo "0 5 * * * root /usr/sbin/aide --check" > "$R/etc/cron.d/aide-stig"
chmod 0600 "$R/etc/cron.d/aide-stig"

echo "[hardening] applied to $R"
