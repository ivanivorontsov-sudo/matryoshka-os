import ctypes
import fcntl
import os
import pwd
import shutil
import socket
import subprocess
import sys
import time

SUBNET = "192.168.240.0/24"
IFACE = "waydroid0"
# Официальный lxc.net.0.mtu у Waydroid — 1500. Короткий MTU 1280 и TCPMSS 1200
# скорость не подняли: пакеты режет не телефон, а виртуальный кабель veth.
# У veth по умолчанию включены контрольные суммы и TSO, пересланные пакеты
# приходят битыми или длиннее MTU, и TCP сползает до килобит.
MTU = "1500"
SIOCETHTOOL = 0x8946
# SRXCSUM, STXCSUM, SSG, STSO, SGSO, SGRO. Ноль в data выключает функцию.
OFFLOAD_OFF = (0x15, 0x17, 0x19, 0x1F, 0x24, 0x2C)
OFFLOAD_NAMES = ("rx", "tx", "sg", "tso", "gso", "gro")
CLONE_NEWNET = 0x40000000


class _EthtoolValue(ctypes.Structure):
    _fields_ = [("cmd", ctypes.c_uint32), ("data", ctypes.c_uint32)]


class _Ifreq(ctypes.Structure):
    # struct ifreq на x86_64 — 40 байт: имя 16 и объединение, в которое входит ifmap.
    _fields_ = [("ifr_name", ctypes.c_char * 16), ("ifr_data", ctypes.c_void_p), ("_pad", ctypes.c_char * 16)]


def rules(subnet=SUBNET, iface=IFACE):
    return (
        (
            ["iptables", "-C", "FORWARD", "-i", iface, "-j", "ACCEPT"],
            ["iptables", "-I", "FORWARD", "1", "-i", iface, "-j", "ACCEPT"],
        ),
        (
            ["iptables", "-C", "FORWARD", "-o", iface, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
            ["iptables", "-I", "FORWARD", "1", "-o", iface, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
        ),
        (
            ["iptables", "-t", "nat", "-C", "POSTROUTING", "-s", subnet, "!", "-d", subnet, "-j", "MASQUERADE"],
            ["iptables", "-t", "nat", "-A", "POSTROUTING", "-s", subnet, "!", "-d", subnet, "-j", "MASQUERADE"],
        ),
    )


def mss_deletes(iface=IFACE):
    base = ["iptables", "-t", "mangle", "-D", "FORWARD", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN"]
    tail = ["-j", "TCPMSS", "--set-mss", "1200"]
    return (base + ["-o", iface] + tail, base + ["-i", iface] + tail)


def drop_mss(run, iface=IFACE):
    for rule in mss_deletes(iface):
        for _ in range(8):
            if run(rule).returncode != 0:
                break


def links(iface=IFACE):
    if not os.path.isdir("/sys/class/net/" + iface):
        return []
    found = [iface]
    br = "/sys/class/net/" + iface + "/brif"
    if os.path.isdir(br):
        found.extend(sorted(os.listdir(br)))
    return found


def offload_off(iface, require_sysfs=True):
    if require_sysfs and not os.path.exists("/sys/class/net/" + iface):
        return False
    ok = False
    et = shutil.which("ethtool")
    if et:
        cmd = [et, "-K", iface]
        for name in OFFLOAD_NAMES:
            cmd.extend([name, "off"])
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            ok = True
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return ok
    try:
        for cmd in OFFLOAD_OFF:
            ev = _EthtoolValue(cmd, 0)
            ifr = _Ifreq()
            ifr.ifr_name = iface.encode()[:15]
            ifr.ifr_data = ctypes.addressof(ev)
            try:
                fcntl.ioctl(sock.fileno(), SIOCETHTOOL, ifr)
                ok = True
            except OSError:
                pass
        return ok
    finally:
        sock.close()


def tune(run, iface=IFACE, mtu=MTU):
    names = links(iface)
    if os.geteuid() == 0 and os.path.isdir("/sys/class/net/" + iface) and len(names) <= 1:
        for _ in range(10):
            time.sleep(0.5)
            names = links(iface)
            if len(names) > 1:
                break
    for name in names:
        run(["ip", "link", "set", "dev", name, "mtu", mtu])
        offload_off(name)
    if os.path.isdir("/sys/class/net/" + iface):
        run(["sysctl", "-w", "net.ipv4.conf.%s.rp_filter=0" % iface])
        run(["sysctl", "-w", "net.ipv6.conf.%s.disable_ipv6=0" % iface])


def useless_dns(ip):
    ip = (ip or "").lower().split("%", 1)[0].rstrip(".")
    return (not ip) or ip.startswith("127.") or ip == "::1" or ip.startswith("fe80:") or ip.startswith("192.168.240.")


def usable_nameservers(text):
    found = []
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "nameserver":
            continue
        ip = parts[1].rstrip(".")
        if useless_dns(ip) or ip in found:
            continue
        found.append(ip)
    return found


def resolvectl_servers():
    if not shutil.which("resolvectl"):
        return []
    try:
        res = subprocess.run(["resolvectl", "dns"], capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    found = []
    for line in (res.stdout or "").splitlines():
        if "waydroid0" in line or ":" not in line:
            continue
        for tok in line.split(":", 1)[1].split():
            if useless_dns(tok) or tok in found:
                continue
            found.append(tok)
    return found


def read_text(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def dnsmasq_user(current):
    parts = (current or "").split()
    if "-u" in parts:
        i = parts.index("-u")
        if i + 1 < len(parts):
            return parts[i + 1]
    for cand in ("lxc-dnsmasq", "dnsmasq", "nobody"):
        try:
            pwd.getpwnam(cand)
            return cand
        except KeyError:
            continue
    return "nobody"


def dnsmasq_argv(servers, user="nobody"):
    cmd = [
        "dnsmasq", "--conf-file=/dev/null", "--strict-order", "--bind-interfaces",
        "--pid-file=/run/waydroid-lxc/dnsmasq.pid",
        "--listen-address", "192.168.240.1",
        "--dhcp-range", "192.168.240.2,192.168.240.254",
        "--dhcp-lease-max=253", "--dhcp-no-override",
        "--except-interface=lo", "--interface=waydroid0",
        "--dhcp-leasefile=/var/lib/misc/dnsmasq.waydroid0.leases",
        "--dhcp-authoritative", "-u", user, "--no-resolv",
    ]
    for server in servers:
        cmd.extend(["--server", server])
    return cmd


def dnsmasq_state():
    pid = read_text("/run/waydroid-lxc/dnsmasq.pid").strip()
    if not pid.isdigit():
        return "", ""
    try:
        raw = open("/proc/%s/cmdline" % pid, "rb").read()
    except OSError:
        return "", ""
    text = raw.replace(b"\0", b" ").decode("utf-8", "replace")
    if "dnsmasq" not in text or "waydroid0" not in text:
        return "", ""
    return text, pid


def needs_dns(host_resolv, upstream, current):
    # dnsmasq читает /etc/resolv.conf. Если там 127.0.0.53, запросы Android
    # уходят в заглушку systemd-resolved, до которой с моста нет хода, и каждое
    # имя ждёт тайм-аут. Пока dnsmasq не запущен, свой не поднимаем.
    if not current or not upstream or usable_nameservers(host_resolv):
        return False
    return "--no-resolv" not in current or any(server not in current for server in upstream)


def restart_dns(run, pid, servers, user):
    if pid:
        run(["kill", "-9", pid])
    run(dnsmasq_argv(servers, user))
    return True


def upstream_dns():
    found = usable_nameservers(read_text("/run/systemd/resolve/resolv.conf"))
    return found or resolvectl_servers()


def container_pid(run):
    res = run(["lxc-info", "-n", "waydroid", "-pH"])
    text = getattr(res, "stdout", "") or ""
    pid = text.strip().split()[-1] if text.strip() else ""
    return pid if pid.isdigit() else ""


def guest_offload(pid):
    ns = "/proc/%s/ns/net" % pid
    if not (str(pid).isdigit() and os.path.exists(ns)):
        return False
    child = os.fork()
    if child == 0:
        try:
            fd = os.open(ns, os.O_RDONLY)
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            if libc.setns(fd, CLONE_NEWNET) != 0:
                os._exit(1)
            os.close(fd)
            subprocess.run(["ip", "link", "set", "dev", "eth0", "mtu", MTU], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            offload_off("eth0", require_sysfs=False)
            os._exit(0)
        except Exception:
            os._exit(1)
    _, status = os.waitpid(child, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def apply(run=None, have_iptables=None, have_sysctl=None):
    run = run or (lambda args: subprocess.run(args, capture_output=True, text=True))
    if have_sysctl is None:
        have_sysctl = bool(shutil.which("sysctl"))
    if have_iptables is None:
        have_iptables = bool(shutil.which("iptables"))
    if have_sysctl:
        run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    tune(run)
    # Прошлая правка выключала суммы из сеанса пользователя. Войти в сеть
    # контейнера без прав администратора нельзя, поэтому eth0 Android не менялся.
    if os.geteuid() == 0:
        pid = container_pid(run)
        if pid:
            guest_offload(pid)
        current, dns_pid = dnsmasq_state()
        upstream = upstream_dns()
        if needs_dns(read_text("/etc/resolv.conf"), upstream, current):
            restart_dns(run, dns_pid, upstream, dnsmasq_user(current))
    if not have_iptables:
        print("iptables нет, сеть Android не настроена")
        return 0
    drop_mss(run)
    for check, add in rules():
        if run(check).returncode != 0:
            run(add)
    print("сеть Android: пересылка только для %s, NAT %s, MTU %s, без ложных контрольных сумм veth" % (IFACE, SUBNET, MTU))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        raise SystemExit(apply())
    raise SystemExit(2)
