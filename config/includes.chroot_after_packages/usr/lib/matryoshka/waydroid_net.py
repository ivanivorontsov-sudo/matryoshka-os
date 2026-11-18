import shutil
import subprocess
import sys

SUBNET = "192.168.240.0/24"
IFACE = "waydroid0"


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


def apply(run=None, have_iptables=None, have_sysctl=None):
    run = run or (lambda args: subprocess.run(args, capture_output=True, text=True))
    if have_sysctl is None:
        have_sysctl = bool(shutil.which("sysctl"))
    if have_iptables is None:
        have_iptables = bool(shutil.which("iptables"))
    if have_sysctl:
        run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
    if not have_iptables:
        print("iptables нет, сеть Android не настроена")
        return 0
    for check, add in rules():
        if run(check).returncode != 0:
            run(add)
    print("сеть Android: пересылка только для %s, NAT %s" % (IFACE, SUBNET))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        raise SystemExit(apply())
    raise SystemExit(2)
