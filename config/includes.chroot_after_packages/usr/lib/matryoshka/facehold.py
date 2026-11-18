import os
import time

HOLD = 300
USER = os.path.expanduser("~/.local/state/matryoshka/face-hold")
WAKE = "/run/matryoshka-face-hold"


def allow_face(now, stamps, hold=HOLD):
    nums = []
    for s in stamps or []:
        try:
            nums.append(float(s))
        except (TypeError, ValueError):
            continue
    if not nums:
        return False
    return float(now) - max(nums) >= hold


def read_stamp(path):
    try:
        return float(open(path, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        return None


def stamps(user_path=USER, wake_path=WAKE):
    out = []
    for p in (user_path, wake_path):
        v = read_stamp(p)
        if v is not None:
            out.append(v)
    return out


def pam_exit(now=None, user_path=USER, wake_path=WAKE):
    now = time.time() if now is None else now
    user_v = read_stamp(user_path)
    if user_v is None:
        try:
            os.makedirs(os.path.dirname(user_path), exist_ok=True)
            open(user_path, "w", encoding="utf-8").write("%s\n" % now)
        except OSError:
            pass
        return 1
    return 0 if allow_face(now, stamps(user_path, wake_path)) else 1


if __name__ == "__main__":
    raise SystemExit(pam_exit())
