import os

# Короткие признаки известных семейств. Срабатывают в программах (есть NUL или расширение
# исполняемого файла) и на тестовой строке EICAR. Обычный текст про эти имена не блокируется.
RULES = (
    ("EICAR", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", False),
    ("miner-xmrig", b"xmrig", True),
    ("miner-stratum", b"stratum+tcp", True),
    ("miner-stratum-ssl", b"stratum+ssl", True),
    ("miner-cryptonight", b"cryptonight", True),
    ("miner-randomx", b"randomx", True),
    ("miner-ethminer", b"ethminer", True),
    ("miner-nbminer", b"nbminer", True),
    ("miner-nicehash", b"nicehash", True),
    ("miner-supportxmr", b"supportxmr", True),
    ("miner-moneroocean", b"moneroocean", True),
    ("miner-trex", b"t-rex", True),
    ("miner-lolminer", b"lolminer", True),
    ("miner-minerd", b"minerd", True),
    ("trojan-meterpreter", b"meterpreter", True),
    ("trojan-mimikatz", b"mimikatz", True),
    ("trojan-cobaltstrike", b"cobaltstrike", True),
    ("ransom-wannacry", b"WANNACRY", True),
)
BIN_EXT = (".exe", ".dll", ".scr", ".com", ".sys", ".msi", ".so", ".bin", ".apk")
READ = 8 << 20


def looks_binary(data, name):
    low = (name or "").lower()
    if low.endswith(BIN_EXT):
        return True
    return b"\0" in data[:4096]


def scan_bytes(data, name=""):
    blob = data or b""
    binary = looks_binary(blob, name)
    low = blob.lower()
    name_l = (name or "").lower().encode()
    hits = []
    for rule, needle, need_bin in RULES:
        if need_bin and not binary:
            continue
        n = needle.lower()
        if n in low or n in name_l:
            hits.append(rule)
    return hits


def scan_file(path, read=READ):
    try:
        with open(path, "rb") as f:
            data = f.read(read)
    except OSError:
        return []
    return scan_bytes(data, os.path.basename(path))
