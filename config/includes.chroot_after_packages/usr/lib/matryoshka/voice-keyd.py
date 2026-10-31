import os, socket, struct, subprocess, time
from evdev import UInput, ecodes as e

SOCK = "/run/matryoshka-voice.sock"
KEYS = {b"paste": [e.KEY_LEFTCTRL, e.KEY_V], b"paste-term": [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_V]}

def allowed(uid):
    if uid < 1000: return False
    r = subprocess.run(["loginctl", "show-user", str(uid), "-p", "State", "--value"], capture_output=True, text=True)
    return r.stdout.strip() == "active"

def main():
    ui = UInput({e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_V]}, name="matryoshka-voice")
    if os.path.exists(SOCK): os.remove(SOCK)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM); s.bind(SOCK); os.chmod(SOCK, 0o666)
    while True:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        msg, anc, _f, _a = s.recvmsg(64, socket.CMSG_SPACE(12))
        uid = None
        for lvl, typ, data in anc:
            if lvl == socket.SOL_SOCKET and typ == socket.SCM_CREDENTIALS: _pid, uid, _gid = struct.unpack("iII", data[:12])
        k = KEYS.get(msg.strip())
        if k is None or uid is None or not allowed(uid): continue
        for c in k: ui.write(e.EV_KEY, c, 1)
        ui.syn(); time.sleep(0.02)
        for c in reversed(k): ui.write(e.EV_KEY, c, 0)
        ui.syn()

if __name__ == "__main__":
    main()
