import ctypes
import fcntl
import os
import shutil
import socket
import subprocess
import sys

SUBNET = "192.168.240.0/24"
IFACE = "waydroid0"
# Телефонная раздача часто не пропускает пакеты больше ~1280 байт и не сообщает об этом.
# Без короткого MSS соединение есть, но скорость падает до килобит.
MTU = "1280"
MSS = "1200"
SIOCETHTOOL = 0x8946
# Выключить подсчёт контрольных сумм на виртуальном кабеле: иначе ядро пересылает битые пакеты и TCP ползёт.
OFFLOAD_OFF = (0x17, 0x19, 0x1B, 0x2C, 0x2E)


class _EthtoolValue(ctypes.Structure):
    _fields_ = [("cmd", ctypes.c_uint32), ("data", ctypes.c_uint32)]


class _Ifreq(ctypes.Structure):
    _fields_ = [("ifr_name", ctypes.c_char * 16), ("ifr_data", ctypes.c_void_p)]


def rules(subnet=SUBNET, iface=IFACE, mss=MSS):
    tcp = ["-p", "tcp", "--tcp-flags", "SYN,RST", "SYN"]
    clamp = ["-j", "TCPMSS", "--set-mss", mss]
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
        (
            ["iptables", "-t", "mangle", "-C", "FORWARD"] + tcp + ["-o", iface] + clamp,
            ["iptables", "-t", "mangle", "-I", "FORWARD", "1"] + tcp + ["-o", iface] + clamp,
        ),
        (
            ["iptables", "-t", "mangle", "-C", "FORWARD"] + tcp + ["-i", iface] + clamp,
            ["iptables", "-t", "mangle", "-I", "FORWARD", "1"] + tcp + ["-i", iface] + clamp,
        ),
    )


def links(iface=IFACE):
    if not os.path.isdir("/sys/class/net/" + iface):
        return []
    found = [iface]
    br = "/sys/class/net/" + iface + "/brif"
    if os.path.isdir(br):
        found.extend(sorted(os.listdir(br)))
    return found


def offload_off(iface):
    if not os.path.exists("/sys/class/net/" + iface):
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ok = False
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
    for name in links(iface):
        run(["ip", "link", "set", "dev", name, "mtu", mtu])
        offload_off(name)
    if os.path.isdir("/sys/class/net/" + iface):
        run(["sysctl", "-w", "net.ipv4.conf.%s.rp_filter=0" % iface])
        run(["sysctl", "-w", "net.ipv6.conf.%s.disable_ipv6=1" % iface])


def apply(run=None, have_iptables=None, have_sysctl=None):
    run = run or (lambda args: subprocess.run(args, capture_output=True, text=True))
    if have_sysctl is None:
        have_sysctl = bool(shutil.which("sysctl"))
    if have_iptables is None:
        have_iptables = bool(shutil.which("iptables"))
    if have_sysctl:
        run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    tune(run)
    if not have_iptables:
        print("iptables нет, сеть Android не настроена")
        return 0
    for check, add in rules():
        if run(check).returncode != 0:
            run(add)
    print("сеть Android: пересылка только для %s, NAT %s, пакеты не больше %s" % (IFACE, SUBNET, MSS))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        raise SystemExit(apply())
    raise SystemExit(2)
