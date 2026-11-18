import ctypes
import fcntl
import os
import shutil
import socket
import subprocess
import sys

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
    for name in links(iface):
        run(["ip", "link", "set", "dev", name, "mtu", mtu])
        offload_off(name)
    if os.path.isdir("/sys/class/net/" + iface):
        run(["sysctl", "-w", "net.ipv4.conf.%s.rp_filter=0" % iface])
        run(["sysctl", "-w", "net.ipv6.conf.%s.disable_ipv6=0" % iface])


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
