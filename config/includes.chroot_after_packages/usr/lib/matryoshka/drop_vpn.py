#!/usr/bin/env python3
"""Удаляет клиенты VPN, плагины NetworkManager для VPN и прокси.

Не трогает NetworkManager, wpa_supplicant, ModemManager, ppp, dnsmasq-base,
Wi-Fi, кабель, USB-модем и NAT контейнера Android. libopenconnect5 остаётся:
от этой библиотеки зависит plasma-nm, это не клиент.
"""
import glob
import os
import pwd
import re
import subprocess
import sys

# Пакеты Debian 13, которые ставят клиент, плагин NM или прокси-демон.
# ppp, dnsmasq-base, modemmanager, network-manager, libopenconnect5,
# openssh-client и plasma-nm сюда не входят.
PACKAGES = (
    "network-manager-openvpn",
    "network-manager-openvpn-gnome",
    "network-manager-vpnc",
    "network-manager-vpnc-gnome",
    "network-manager-pptp",
    "network-manager-pptp-gnome",
    "network-manager-l2tp",
    "network-manager-l2tp-gnome",
    "network-manager-strongswan",
    "network-manager-openconnect",
    "network-manager-openconnect-gnome",
    "network-manager-iodine",
    "network-manager-iodine-gnome",
    "network-manager-ssh",
    "network-manager-ssh-gnome",
    "network-manager-sstp",
    "network-manager-sstp-gnome",
    "network-manager-fortisslvpn",
    "network-manager-fortisslvpn-gnome",
    "openvpn",
    "openvpn-systemd-resolved",
    "openvpn3-client",
    "openvpn-auth-ldap",
    "openvpn-auth-radius",
    "openvpn-dco-dkms",
    "easy-rsa",
    "openconnect",
    "ocproxy",
    "vpnc",
    "vpnc-scripts",
    "pptp-linux",
    "xl2tpd",
    "sstp-client",
    "iodine",
    "openfortivpn",
    "strongswan",
    "strongswan-charon",
    "strongswan-nm",
    "strongswan-starter",
    "strongswan-swanctl",
    "strongswan-pki",
    "strongswan-libcharon",
    "libreswan",
    "charon-systemd",
    "libcharon-extra-plugins",
    "libcharon-extauth-plugins",
    "wireguard",
    "wireguard-tools",
    "wireguard-go",
    "riseup-vpn",
    "sshuttle",
    "proxychains",
    "proxychains4",
    "tsocks",
    "redsocks",
    "privoxy",
    "squid",
    "squid-common",
    "squid-openssl",
    "squid-cgi",
    "squidclient",
    "squidguard",
    "tinyproxy",
    "tinyproxy-bin",
    "microsocks",
    "shadowsocks-libev",
    "trojan",
    "v2ray",
    "cntlm",
    "stunnel4",
    "corkscrew",
    "proxytunnel",
    "connect-proxy",
    "tor",
    "torsocks",
    "obfs4proxy",
    "apt-transport-tor",
)

KEEP_TYPES = {
    "802-11-wireless",
    "802-3-ethernet",
    "gsm",
    "cdma",
    "bluetooth",
    "pppoe",
    "adsl",
    "vlan",
    "bond",
    "bridge",
    "team",
    "macvlan",
    "infiniband",
    "wifi-p2p",
    "wimax",
    "olpc-mesh",
    "generic",
    "loopback",
}
DROP_TYPES = {"vpn", "wireguard", "tun", "ip-tunnel", "vxlan"}
PROXY_ASSIGN = re.compile(
    r"^\s*(?:export\s+)?(?:https?_proxy|ftp_proxy|all_proxy|socks_proxy|no_proxy)\s*=",
    re.I,
)
APT_PROXY = re.compile(r"Acquire::(?:https?|socks|ftp)::Proxy", re.I)
UNITS = (
    "openvpn.service",
    "openvpn-server@.service",
    "openvpn-client@.service",
    "wg-quick@.service",
    "tor.service",
    "tor@default.service",
    "privoxy.service",
    "redsocks.service",
    "squid.service",
    "tinyproxy.service",
    "shadowsocks-libev.service",
    "shadowsocks-libev-local@.service",
    "strongswan.service",
    "strongswan-starter.service",
    "xl2tpd.service",
    "iodined.service",
    "stunnel4.service",
    "cntlm.service",
    "v2ray.service",
    "trojan.service",
    "microsocks.service",
)


def connection_is_vpn(text):
    """True только для профиля VPN, WireGuard или прокси. Wi-Fi и модем остаются."""
    if not isinstance(text, str) or not text.strip():
        return False
    kind = ""
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == "connection" and line.lower().startswith("type="):
            kind = line.split("=", 1)[1].strip().lower()
    if kind in KEEP_TYPES:
        return False
    if kind in DROP_TYPES:
        return True
    low = text.lower()
    return "[vpn]" in low or "[wireguard]" in low or "[proxy]" in low


def strip_proxy_text(text):
    kept = []
    changed = False
    for line in text.splitlines(keepends=True):
        body = line.split("#", 1)[0]
        if PROXY_ASSIGN.match(body) or APT_PROXY.search(body):
            changed = True
            continue
        kept.append(line)
    return "".join(kept), changed


def clear_kio_proxy(text):
    if "ProxyType=" not in text and "[Proxy Settings]" not in text:
        return text, False
    lines = []
    changed = False
    for line in text.splitlines():
        if line.startswith("ProxyType=") and line.strip() != "ProxyType=0":
            lines.append("ProxyType=0")
            changed = True
        elif line.startswith(("httpProxy=", "httpsProxy=", "ftpProxy=", "socksProxy=")) and not line.endswith("="):
            lines.append(line.split("=", 1)[0] + "=")
            changed = True
        else:
            lines.append(line)
    if not changed:
        return text, False
    body = "\n".join(lines)
    if text.endswith("\n"):
        body += "\n"
    return body, True


def installed_packages(probe):
    found = []
    for name in PACKAGES:
        if probe(name):
            found.append(name)
    return found


def _run(argv, timeout=180):
    try:
        return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def _write_if_changed(path, new, changed):
    if not changed or new == open(path, encoding="utf-8", errors="replace").read():
        return False
    tmp = path + ".matryoshka-new"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(new)
    os.replace(tmp, path)
    return True


def _strip_file(path):
    try:
        old = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    new, changed = strip_proxy_text(old)
    if not changed:
        return False
    if not new.strip() and "proxy" in os.path.basename(path).lower():
        try:
            os.remove(path)
        except OSError:
            return False
        return True
    return _write_if_changed(path, new, True)


def _kio_file(path):
    try:
        old = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    new, changed = clear_kio_proxy(old)
    return _write_if_changed(path, new, changed)


def purge_packages():
    present = []
    for name in PACKAGES:
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f", "${db:Status-Abbrev}", name],
                capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.startswith("ii"):
            present.append(name)
    if not present:
        return []
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    subprocess.run(
        ["apt-get", "purge", "-y", "--no-install-recommends", *present],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600,
    )
    return present


def delete_profiles(path="/etc/NetworkManager/system-connections"):
    removed = []
    if not os.path.isdir(path):
        return removed
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if not connection_is_vpn(text):
            continue
        try:
            os.remove(full)
        except OSError:
            continue
        removed.append(full)
    return removed


def delete_live_profiles():
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    gone = []
    for line in result.stdout.splitlines():
        uuid, sep, kind = line.partition(":")
        if not sep or kind.strip().lower() not in DROP_TYPES:
            continue
        if _run(["nmcli", "connection", "delete", uuid], timeout=20) == 0:
            gone.append(uuid)
    return gone


def strip_proxy_files():
    paths = ["/etc/environment", "/etc/xdg/kioslaverc"]
    for folder in ("/etc/environment.d", "/etc/profile.d", "/etc/apt/apt.conf.d"):
        paths.extend(glob.glob(os.path.join(folder, "*")))
    changed = []
    for path in paths:
        if not os.path.isfile(path):
            continue
        if os.path.basename(path) == "91matryoshka-auto":
            continue
        if path.endswith("kioslaverc"):
            if _kio_file(path):
                changed.append(path)
            continue
        if _strip_file(path):
            changed.append(path)
    homes = []
    try:
        homes = [item.pw_dir for item in pwd.getpwall() if 1000 <= item.pw_uid < 60000]
    except Exception:
        homes = []
    homes.append("/etc/skel")
    for home in homes:
        for rel in (".config/kioslaverc", ".pam_environment"):
            path = os.path.join(home, rel)
            if rel.endswith("kioslaverc"):
                if _kio_file(path):
                    changed.append(path)
            elif _strip_file(path):
                changed.append(path)
        for path in glob.glob(os.path.join(home, ".config", "environment.d", "*")):
            if _strip_file(path):
                changed.append(path)
        for path in glob.glob(os.path.join(home, ".config", "autostart", "*")):
            base = os.path.basename(path).lower()
            if any(word in base for word in ("vpn", "openvpn", "wireguard", "proxychain", "privoxy", "tor-browser")):
                try:
                    os.remove(path)
                    changed.append(path)
                except OSError:
                    pass
    return changed


def stop_units():
    for unit in UNITS:
        _run(["systemctl", "disable", "--now", unit], timeout=30)


def desktop_leftovers():
    removed = []
    patterns = (
        "*openvpn*", "*wireguard*", "*vpnc*", "*openconnect*", "*proxychains*",
        "*privoxy*", "*squid*", "*redsocks*", "*shadowsocks*", "*riseup*",
    )
    for folder in ("/usr/share/applications", "/etc/xdg/autostart"):
        for pattern in patterns:
            for path in glob.glob(os.path.join(folder, pattern)):
                if not os.path.isfile(path):
                    continue
                try:
                    os.remove(path)
                    removed.append(path)
                except OSError:
                    pass
    if removed:
        _run(["update-desktop-database", "-q", "/usr/share/applications"], timeout=60)
    return removed


def apply_all():
    if os.geteuid() != 0:
        print("нужны права администратора", file=sys.stderr)
        return 1
    stop_units()
    purged = purge_packages()
    files = delete_profiles()
    live = delete_live_profiles()
    proxy = strip_proxy_files()
    menus = desktop_leftovers()
    print("VPN и прокси: пакетов %d, профилей %d, живых %d, файлов прокси %d, ярлыков %d" % (
        len(purged), len(files), len(live), len(proxy), len(menus)))
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "apply"
    if cmd == "apply":
        return apply_all()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
