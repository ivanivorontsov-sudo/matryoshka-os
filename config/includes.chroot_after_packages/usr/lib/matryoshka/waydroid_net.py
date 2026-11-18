import array
import ctypes
import fcntl
import os
import pwd
import shutil
import socket
import struct
import subprocess
import sys
import time

SUBNET = "192.168.240.0/24"
IFACE = "waydroid0"
# У компьютера ТТЛ 65: точка телефона уменьшает его до 64, и оператор видит сам телефон.
# Android — Linux, у него ТТЛ 64, не 128 (128 — это Windows). Пересылка уменьшает его
# до 63, телефон — до 62, и раздача режет скорость. На выход ставится те же 65.
HOST_TTL = "65"
# Внутри контейнера на один больше: если цель TTL в iptables недоступна,
# пересылка сама уменьшит 66 до 65. При рабочей цели выход всё равно становится 65.
GUEST_TTL = "66"
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


def primary_iptables():
    # Waydroid пишет свои правила в iptables-legacy. Если то же NAT добавить ещё
    # и в iptables-nft, пакет обрабатывается дважды и у Android пропадает интернет.
    if shutil.which("iptables-legacy"):
        return "iptables-legacy"
    return "iptables"


def rules(subnet=SUBNET, iface=IFACE, binary=None):
    binary = binary or primary_iptables()
    # Обратный трафик принимаем целиком, как официальный скрипт Waydroid.
    # Условие RELATED,ESTABLISHED отбрасывало ответы, которые conntrack
    # помечал INVALID из-за сумм на veth, и страницы в Android не открывались.
    return (
        (
            [binary, "-C", "FORWARD", "-i", iface, "-j", "ACCEPT"],
            [binary, "-I", "FORWARD", "1", "-i", iface, "-j", "ACCEPT"],
        ),
        (
            [binary, "-C", "FORWARD", "-o", iface, "-j", "ACCEPT"],
            [binary, "-I", "FORWARD", "1", "-o", iface, "-j", "ACCEPT"],
        ),
        (
            [binary, "-t", "nat", "-C", "POSTROUTING", "-s", subnet, "!", "-d", subnet, "-j", "MASQUERADE"],
            [binary, "-t", "nat", "-A", "POSTROUTING", "-s", subnet, "!", "-d", subnet, "-j", "MASQUERADE"],
        ),
    )


def input_rules(iface=IFACE, binary=None):
    # DHCP и DNS Android идут на сам компьютер. Без этих разрешений
    # строгая политика INPUT оставляет контейнер без адреса и без имён.
    binary = binary or primary_iptables()
    found = []
    for proto, port in (("udp", "67"), ("tcp", "67"), ("udp", "53"), ("tcp", "53")):
        args = ["-i", iface, "-p", proto, "--dport", port, "-j", "ACCEPT"]
        found.append(([binary, "-C", "INPUT", *args], [binary, "-I", "INPUT", "1", *args]))
    return tuple(found)


def mss_clamp_rules(iface=IFACE, binary=None):
    # Не фиксированные 1200 байт: на обычной линии это только замедляло.
    # Размер подстраивается под маршрут. Когда зонд компьютера уменьшает путь,
    # крупные пакеты Android больше не пропадают молча.
    binary = binary or primary_iptables()
    found = []
    for flag in (("-i", iface), ("-o", iface)):
        args = ["-p", "tcp", "--tcp-flags", "SYN,RST", "SYN", flag[0], flag[1], "-j", "TCPMSS", "--clamp-mss-to-pmtu"]
        found.append((
            [binary, "-t", "mangle", "-C", "FORWARD", *args],
            [binary, "-t", "mangle", "-A", "FORWARD", *args],
        ))
    return tuple(found)


def mss_deletes(iface=IFACE):
    base = ["iptables", "-t", "mangle", "-D", "FORWARD", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN"]
    tail = ["-j", "TCPMSS", "--set-mss", "1200"]
    return (base + ["-o", iface] + tail, base + ["-i", iface] + tail)


def checksum_deletes(subnet=SUBNET):
    # Прошлая правка пересчитывала суммы и при ошибке выбрасывала пакет.
    # RuStore из-за этого показывал «нет интернета». Правило снимается.
    return (
        ["iptables", "-t", "mangle", "-D", "POSTROUTING", "-s", subnet, "-p", "tcp", "-j", "CHECKSUM", "--checksum-fill"],
        ["iptables", "-t", "mangle", "-D", "POSTROUTING", "-s", subnet, "-p", "udp", "-j", "CHECKSUM", "--checksum-fill"],
    )


def drop_mss(run, iface=IFACE):
    for binary in iptables_bins():
        for rule in mss_deletes(iface):
            cmd = [binary, *rule[1:]]
            for _ in range(8):
                if run(cmd).returncode != 0:
                    break


def iptables_bins():
    found = []
    for name in ("iptables", "iptables-legacy"):
        if shutil.which(name) and name not in found:
            found.append(name)
    return found or ["iptables"]


def ttl_commands(binary, subnet=SUBNET, ttl=HOST_TTL):
    # Источник ещё адрес моста: NAT стоит после mangle POSTROUTING.
    args = ["-s", subnet, "!", "-d", subnet, "-j", "TTL", "--ttl-set", ttl]
    return [binary, "-t", "mangle", "-C", "POSTROUTING", *args], [binary, "-t", "mangle", "-A", "POSTROUTING", *args]


def hop_commands(binary, iface=IFACE, ttl=HOST_TTL):
    # -i в POSTROUTING нельзя. Уменьшение предела прыжков уже сделано до FORWARD.
    args = ["-i", iface, "-j", "HL", "--hl-set", ttl]
    return [binary, "-t", "mangle", "-C", "FORWARD", *args], [binary, "-t", "mangle", "-A", "FORWARD", *args]


def apply_mark(run, check, add):
    if run(check).returncode == 0:
        return True
    run(add)
    return run(check).returncode == 0


def apply_ttl(run):
    # Одна цель TTL, в том же наборе, куда Waydroid пишет NAT.
    ok = apply_mark(run, *ttl_commands(primary_iptables()))
    for name in ("ip6tables-legacy", "ip6tables"):
        if shutil.which(name):
            apply_mark(run, *hop_commands(name))
            break
    return ok


def guest_sysctl(pid, rel, value):
    # /proc/sys снаружи — это сеть компьютера. Писать ТТЛ можно только в proc контейнера,
    # иначе 65 всей системы станет другим числом.
    if not str(pid).isdigit():
        return False
    root = "/proc/%s/root" % pid
    try:
        if os.path.samefile(root, "/"):
            return False
    except OSError:
        return False
    path = "/proc/%s/root/proc/sys/%s" % (pid, rel)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "w", encoding="ascii") as out:
            out.write(str(value).strip() + "\n")
    except OSError:
        return False
    return True


def guest_ttl(pid, ttl=GUEST_TTL):
    v4 = guest_sysctl(pid, "net/ipv4/ip_default_ttl", ttl)
    v6 = guest_sysctl(pid, "net/ipv6/conf/all/hop_limit", ttl)
    return v4 or v6


def drop_checksum(run, subnet=SUBNET):
    # Waydroid пишет правила в iptables-legacy, а iptables может быть nft.
    # Снимаем пересчёт сумм в обоих наборах. Правило DHCP (порт 68) не трогаем:
    # его ставит официальный скрипт Waydroid, без него контейнер не получает адрес.
    for binary in iptables_bins():
        for rule in checksum_deletes(subnet):
            cmd = [binary, *rule[1:]]
            for _ in range(8):
                if run(cmd).returncode != 0:
                    break
        listed = run([binary, "-t", "mangle", "-S", "POSTROUTING"])
        for line in (getattr(listed, "stdout", "") or "").splitlines():
            if "CHECKSUM" not in line or "--dport 68" in line:
                continue
            parts = line.split()
            if parts and parts[0] == "-A":
                parts[0] = "-D"
                run([binary, "-t", "mangle", *parts])


def links(iface=IFACE):
    if not os.path.isdir("/sys/class/net/" + iface):
        return []
    found = [iface]
    br = "/sys/class/net/" + iface + "/brif"
    if os.path.isdir(br):
        found.extend(sorted(os.listdir(br)))
    return found


def ethtool_off(iface):
    # struct ifreq: имя 16 байт и указатель на {cmd, data}. Ноль в data выключает функцию.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return False
    try:
        ok = False
        for cmd in OFFLOAD_OFF:
            buf = array.array("B", struct.pack("II", cmd, 0))
            ifr = struct.pack("16sP", iface.encode()[:15], buf.buffer_info()[0]).ljust(40, b"\0")
            try:
                fcntl.ioctl(sock.fileno(), SIOCETHTOOL, ifr)
                ok = True
            except OSError:
                pass
        return ok
    finally:
        sock.close()


def offload_off(iface, require_sysfs=True):
    if require_sysfs and not os.path.exists("/sys/class/net/" + iface):
        return False
    ok = ethtool_off(iface)
    et = shutil.which("ethtool")
    if et:
        cmd = [et, "-K", iface]
        for name in OFFLOAD_NAMES:
            cmd.extend([name, "off"])
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            ok = True
    if ok:
        return True
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
        # Ядро берёт максимум из all и интерфейса. Ноль здесь не выключает
        # строгую проверку, пока all равен 1, и ответы Android отбрасываются.
        run(["sysctl", "-w", "net.ipv4.conf.%s.rp_filter=2" % iface])
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
    # --no-hosts: список блокировки в /etc/hosts закрывает mc.yandex.ru.
    # Яндекс Браузер в Android без этого имени не открывает страницы.
    # Без strict-order мёртвый первый DNS не держит все остальные запросы.
    cmd = [
        "dnsmasq", "--conf-file=/dev/null", "--no-hosts", "--bind-interfaces",
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


def needs_dns(host_resolv, upstream, current, iface_ready=False):
    # dnsmasq читает /etc/resolv.conf. Если там 127.0.0.53, запросы Android
    # уходят в заглушку systemd-resolved, до которой с моста нет хода, и каждое
    # имя ждёт тайм-аут. Пока моста нет, свой dnsmasq не поднимаем: его
    # старт раньше интерфейса проигрывает гонку со скриптом Waydroid.
    # Если мост уже есть, а DHCP/DNS никто не слушает, Android остаётся без сети.
    if not upstream:
        return False
    if not current:
        return bool(iface_ready)
    if usable_nameservers(host_resolv):
        return False
    if "--no-hosts" not in current:
        return True
    return "--no-resolv" not in current or any(server not in current for server in upstream)


def restart_dns(run, pid, servers, user):
    if pid:
        run(["kill", "-9", pid])
    run(dnsmasq_argv(servers, user))
    return True


def prefer_v4(servers):
    v4 = [item for item in servers if ":" not in item]
    return v4 or list(servers)


def upstream_dns():
    for path in (
        "/run/systemd/resolve/resolv.conf",
        "/run/NetworkManager/no-stub-resolv.conf",
        "/run/NetworkManager/resolv.conf",
        "/etc/resolv.conf",
    ):
        found = prefer_v4(usable_nameservers(read_text(path)))
        if found:
            return found
    found = prefer_v4(resolvectl_servers())
    # Иначе dnsmasq спрашивает 127.0.0.53, до которого с моста хода нет,
    # и Android показывает отсутствие сети.
    # 1.1.1.1 на части российских раздач не отвечает и подвешивает имена.
    # 77.88.8.8 — DNS Яндекса, им же пользуется Яндекс Браузер.
    return found or ["77.88.8.8", "8.8.8.8"]


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
        # Строгий фильтр обратного пути (1) вместе с all=1 не даёт интерфейсу
        # стать мягче. На раздаче ответ приходит не тем интерфейсом, и Android глухой.
        run(["sysctl", "-w", "net.ipv4.conf.all.rp_filter=2"])
        run(["sysctl", "-w", "net.ipv4.conf.default.rp_filter=2"])
        # 1 — настройка всего компьютера из 90-matryoshka-net.conf.
        # Прошлый архив ставил здесь 0: зонд размера пакета выключался у системы,
        # и на раздаче с телефона интернет самого компьютера становился крайне медленным.
        run(["sysctl", "-w", "net.ipv4.tcp_mtu_probing=1"])
    tune(run)
    # Прошлая правка выключала суммы из сеанса пользователя. Войти в сеть
    # контейнера без прав администратора нельзя, поэтому eth0 Android не менялся.
    if os.geteuid() == 0:
        pid = container_pid(run)
        if pid:
            guest_offload(pid)
            guest_ttl(pid)
            # Зонд внутри контейнера, не вместо настройки компьютера.
            # Крупные пакеты на раздаче тогда уменьшаются у самого Android.
            guest_sysctl(pid, "net/ipv4/tcp_mtu_probing", "1")
            # Выключение IPv6 у всего контейнера гасит ::1. Без него Android
            # не поднимает сеть вообще, не только Яндекс Браузер.
            # Объявления маршрутизатора на eth0 не принимаем: чужой IPv6 без
            # маршрута заставляет браузер ждать, пока IPv4 уже работает.
            guest_sysctl(pid, "net/ipv6/conf/all/disable_ipv6", "0")
            guest_sysctl(pid, "net/ipv6/conf/default/disable_ipv6", "0")
            guest_sysctl(pid, "net/ipv6/conf/eth0/accept_ra", "0")
            guest_sysctl(pid, "net/ipv6/conf/eth0/autoconf", "0")
        current, dns_pid = dnsmasq_state()
        upstream = upstream_dns()
        ready = os.path.isdir("/sys/class/net/" + IFACE)
        if needs_dns(read_text("/etc/resolv.conf"), upstream, current, ready):
            restart_dns(run, dns_pid, upstream, dnsmasq_user(current))
    if not have_iptables:
        print("iptables нет, сеть Android не настроена")
        return 0
    drop_mss(run)
    drop_checksum(run)
    for check, add in rules():
        if run(check).returncode != 0:
            run(add)
    for check, add in input_rules():
        apply_mark(run, check, add)
    for check, add in mss_clamp_rules():
        apply_mark(run, check, add)
    ttl_ok = apply_ttl(run)
    ttl_note = "ТТЛ %s как у системы" % HOST_TTL if ttl_ok else "ТТЛ не записался"
    print("сеть Android: пересылка только для %s, NAT %s, MTU %s, %s, без пересчёта сумм" % (IFACE, SUBNET, MTU, ttl_note))
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        raise SystemExit(apply())
    raise SystemExit(2)
