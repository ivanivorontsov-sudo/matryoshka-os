#!/usr/bin/env python3
import subprocess, sys

def newer(installed, candidate):
    if not candidate or candidate in ("(none)", "none"):
        return False
    if not installed:
        return True
    return subprocess.run(["dpkg", "--compare-versions", candidate, "gt", installed], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def installed_version(name):
    r = subprocess.run(["dpkg-query", "-W", "-f", "${Version}", name], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else ""

def candidate_version(name, apt_args):
    r = subprocess.run(["apt-cache", *apt_args, "policy", name], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "Candidate:" in line:
            parts = line.split()
            return parts[-1] if parts else ""
    return ""

def select(packages, apt_args):
    out = []
    seen = set()
    for name in packages:
        if not name or name in seen or name.startswith("#"):
            continue
        seen.add(name)
        if newer(installed_version(name), candidate_version(name, apt_args)):
            out.append(name)
    return out

def main(argv):
    if len(argv) < 2:
        return 2
    pkgs = []
    for line in open(argv[1], encoding="utf-8", errors="replace"):
        pkgs.extend(p for p in line.split() if p and not p.startswith("#"))
    for name in select(pkgs, argv[2:]):
        print(name)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
