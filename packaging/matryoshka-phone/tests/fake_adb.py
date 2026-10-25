#!/usr/bin/env python3
import os
import shutil
import sys
from pathlib import Path

root = Path(os.environ["FAKE_PHONE"])
a = sys.argv[1:]
if a and a[0] == "-s":
    a = a[2:]
if a == ["devices"]:
    print("List of devices attached\nABC123\tdevice\n")
elif a[0] == "shell":
    cmd = a[1]
    if cmd.startswith("pm list packages"):
        print("package:org.telegram.messenger installer=com.android.vending\npackage:com.example.game installer=com.android.vending\npackage:ru.sberbankmobile installer=null")
    elif cmd.startswith("pm path"):
        if "game" in cmd:
            print("package:/data/app/x/base.apk\npackage:/data/app/x/split_config.arm64_v8a.apk")
    elif "find" in cmd:
        import re, shlex
        base = shlex.split(cmd.split("&&")[0].strip("[] "))[-1]
        local = root / base.lstrip("/")
        if local.is_dir():
            for p in sorted(local.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    print(f"{st.st_size}|{int(st.st_mtime)}|/{p.relative_to(root)}")
elif a[0] == "pull":
    args = [x for x in a[1:] if x != "-a"]
    src, dst = args
    if src.startswith("/data/app"):
        Path(dst).write_bytes(b"APK" + src.encode())
    else:
        if os.environ.get("FAKE_FAIL") and os.environ["FAKE_FAIL"] in src:
            Path(dst).write_bytes(b"x")
            sys.exit(1)
        shutil.copyfile(root / src.lstrip("/"), dst)
else:
    sys.exit(1)
