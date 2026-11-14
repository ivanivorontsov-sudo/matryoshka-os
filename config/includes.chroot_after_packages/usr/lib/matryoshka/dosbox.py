import glob, os, re, shutil, subprocess, sys, zlib

def q(path):
    return path.replace('"', "").replace("\\", "/")

def run_line(name):
    plain = name.isascii() and " " not in name
    cmd = name if plain else '"%s"' % name
    if name.lower().endswith(".bat"):
        return "call %s\n" % cmd
    return "%s\n" % cmd

LNG = "/usr/share/dosbox-x/languages/ru_RU.lng"

def keyrus_line():
    return "if exist d:\\KEYRUS\\KEYRUS.COM d:\\KEYRUS\\KEYRUS.COM\n"

def session_text(program_dir, program, dos_root, home, shared, print_dir, desktop=None):
    program_dir, dos_root, home, shared, print_dir = (q(p) for p in (program_dir, dos_root, home, shared, print_dir))
    lang = "language=%s\n" % LNG if os.path.isfile(LNG) else ""
    desk = 'mount -q g "%s" -freesize 2048\n' % q(desktop) if desktop else ""
    name = program.replace('"', "")
    run = run_line(name) if name else "echo C: программа, D: DOS, E: домашняя папка, F: Общее, G: рабочий стол\n"
    return """[sdl]
fullscreen=false
autolock=false
output=ttf
usesystemcursor=true
mouse_emulation=always
[ttf]
outputswitch=auto
lins=25
cols=80
[dosbox]
machine=svga_s3
memsize=64
captures={print_dir}
startup_verbosity=quiet
startbanner=false
quit warning=false
{lang}
[render]
aspect=true
scaler=none
[cpu]
core=normal
cputype=auto
cycles=max
[mixer]
nosound=false
rate=44100
blocksize=2048
prebuffer=40
[midi]
mpu401=intelligent
mididevice=default
[sblaster]
sbtype=sb16
sbbase=220
irq=7
dma=1
hdma=5
oplmode=opl3
mixer=true
[gus]
gus=false
[speaker]
pcspeaker=true
tandy=off
disney=false
[joystick]
joysticktype=auto
[serial]
serial1=disabled
[parallel]
parallel1=printer
[printer]
printer=true
dpi=360
width=85
height=110
printoutput=ps
multipage=true
timeout=2000
docpath={print_dir}
[dos]
xms=true
ems=true
umb=true
keyboardlayout=ru
int33=true
lfn=auto
dos idle api=true
ver=7.10
[config]
files=200
fcbs=100
country=7,866
lastdrive=z
dos=high,umb
numlock=off
[autoexec]
@echo off
mount -q c "{program_dir}" -freesize 2048
mount -q d "{dos_root}" -freesize 2048
mount -q e "{home}" -freesize 2048
mount -q f "{shared}" -freesize 2048
{desk}set TEMP=C:\\
set TMP=C:\\
set BLASTER=A220 I7 D1 H5 P330 T6
path c:\\;d:\\;z:\\;z:\\system;z:\\bin;z:\\dos;z:\\4dos;z:\\textutil
{keyrus}c:
{run}""".format(program_dir=program_dir, dos_root=dos_root, home=home, shared=shared, print_dir=print_dir, run=run, lang=lang, desk=desk, keyrus=keyrus_line())

def link_base(home):
    for b in (os.path.join(home, ".config", "matryoshka", "dos", "links"), os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "matryoshka-dos-%d" % os.getuid())):
        if b.isascii() and " " not in b:
            return b
    return "/tmp/matryoshka-dos-%d" % os.getuid()

def ascii_link(base, key, target):
    if target.isascii() and " " not in target and '"' not in target:
        return target
    os.makedirs(base, exist_ok=True)
    link = os.path.join(base, key)
    if os.path.islink(link) and os.readlink(link) == target:
        return link
    tmp = link + ".new"
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)
    return link

def dos_name(name):
    base, ext = os.path.splitext(name)
    return name.isascii() and " " not in name and 0 < len(base) <= 8 and len(ext) <= 4

def conf_text(drive, folder, program):
    return session_text(folder, program, drive, drive, drive, drive + "/Печать")

def write_conf(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="cp866", errors="replace") as f:
        f.write(text)

def to_pdf(print_dir):
    tool = shutil.which("ps2pdf") or shutil.which("gs")
    made = []
    if not tool:
        return made
    for ps in sorted(glob.glob(os.path.join(print_dir, "*.ps"))):
        pdf = ps[:-3] + ".pdf"
        if tool.endswith("ps2pdf") or os.path.basename(tool) == "ps2pdf":
            cmd = [tool, ps, pdf]
        else:
            cmd = [tool, "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", "-sOutputFile=" + pdf, ps]
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 and os.path.isfile(pdf):
            made.append(pdf)
    return made

def places(home=None):
    home = home or os.path.expanduser("~")
    dos_root = os.path.join(home, "DOS")
    shared = os.path.join(home, "Общее")
    prints = os.path.join(dos_root, "Печать")
    for p in (dos_root, os.path.join(dos_root, "NC"), os.path.join(dos_root, "CAD"), os.path.join(dos_root, "Программы"), shared, prints):
        os.makedirs(p, exist_ok=True)
    note = os.path.join(dos_root, "README.txt")
    if not os.path.exists(note):
        with open(note, "w", encoding="utf-8") as f:
            f.write("Norton Commander и Festa в систему не входят. Положите свои легальные копии в DOS/NC и DOS/CAD и откройте EXE, COM или BAT двойным щелчком.\nПечать из DOS сохраняется в DOS/Печать в PDF.\n")
    return home, dos_root, shared, prints

def desktop_dir(home):
    return next((p for p in (os.path.join(home, "Рабочий стол"), os.path.join(home, "Desktop")) if os.path.isdir(p)), None)

def launcher_text(label, conf, program):
    me = "/usr/lib/matryoshka/dosbox.py"
    pq = program.replace('"', "")
    return ("[Desktop Entry]\nType=Application\nName=%s (DOS)\nExec=dosbox-x -nopromptfolder -fastlaunch -conf \"%s\"\nIcon=dosbox-x\n"
            "X-Matryoshka-DOS-Program=%s\nActions=addfile;opendir;\n\n"
            "[Desktop Action addfile]\nName=Добавить файл в папку программы\nIcon=list-add\nExec=python3 %s --add-file \"%s\"\n\n"
            "[Desktop Action opendir]\nName=Открыть папку диска программы (C:)\nIcon=folder-open\nExec=python3 %s --open-dir \"%s\"\n") % (label, conf, pq, me, pq, me, pq)

def write_launcher(home, label, conf, program):
    desk = desktop_dir(home)
    if not desk or not program:
        return None
    lf = os.path.join(desk, label + " (DOS).desktop")
    text = launcher_text(label, conf, program)
    if os.path.exists(lf):
        old = open(lf, encoding="utf-8", errors="replace").read()
        if old == text or "dosbox-x" not in old:
            return lf
    with open(lf, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(lf, 0o755)
    return lf

def program_dir_of(target):
    target = os.path.abspath(target)
    if target.endswith(".desktop") and os.path.isfile(target):
        m = re.search(r"^X-Matryoshka-DOS-Program=(.+)$", open(target, encoding="utf-8", errors="replace").read(), re.M)
        if m:
            target = m.group(1).strip()
    return target if os.path.isdir(target) else os.path.dirname(target)

def add_file(target):
    d = program_dir_of(target)
    if not os.path.isdir(d):
        subprocess.run(["kdialog", "--error", "Папка программы не найдена: %s" % d])
        return 2
    r = subprocess.run(["kdialog", "--title", "Добавить файл в папку программы (диск C:)", "--multiple", "--separate-output", "--getopenfilename", os.path.expanduser("~")], capture_output=True, text=True)
    files = [x for x in r.stdout.splitlines() if x.strip()]
    if not files:
        return 1
    done, skipped = [], []
    for f in files:
        dst = os.path.join(d, os.path.basename(f))
        if os.path.abspath(f) == dst:
            skipped.append(os.path.basename(f))
            continue
        if os.path.exists(dst) and subprocess.call(["kdialog", "--yesno", "«%s» уже есть в папке программы. Заменить?" % os.path.basename(f)]) != 0:
            skipped.append(os.path.basename(f))
            continue
        try:
            if os.path.isdir(f):
                shutil.copytree(f, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(f, dst)
            done.append(os.path.basename(f))
        except OSError as e:
            skipped.append("%s (%s)" % (os.path.basename(f), e.strerror))
    msg = "Скопировано в %s (в DOS это диск C:):\n%s" % (d, "\n".join(done) or "ничего")
    if skipped:
        msg += "\n\nПропущено:\n" + "\n".join(skipped)
    subprocess.run(["kdialog", "--title", "DOS", "--msgbox", msg])
    return 0

def open_dir(target):
    d = program_dir_of(target)
    return subprocess.call(["xdg-open", d])

def refresh_launchers(home=None):
    home = home or os.path.expanduser("~")
    desk = desktop_dir(home)
    if not desk:
        return 0
    n = 0
    for lf in glob.glob(os.path.join(desk, "* (DOS).desktop")):
        t = open(lf, encoding="utf-8", errors="replace").read()
        if "X-Matryoshka-DOS-Program=" in t or "dosbox-x" not in t:
            continue
        m = re.search(r'-conf "([^"]+)"', t)
        if not m or not os.path.isfile(m.group(1)):
            continue
        conf = m.group(1)
        c = open(conf, encoding="utf-8", errors="replace").read()
        mc = re.search(r'mount -q c "([^"]+)"', c)
        my = re.search(r'mount -q y "([^"]+)"', c)
        prog = None
        if my:
            runs = glob.glob(os.path.join(my.group(1), "RUN.*"))
            if runs:
                prog = os.path.realpath(runs[0])
        if not prog and mc:
            lines = c.split("\nc:\n", 1)
            name = lines[1].strip().splitlines()[0].replace("call ", "").strip('"') if len(lines) > 1 and lines[1].strip() else ""
            if name:
                prog = os.path.join(os.path.realpath(mc.group(1)), name)
        if not prog:
            continue
        label = os.path.basename(lf)[:-len(" (DOS).desktop")]
        with open(lf, "w", encoding="utf-8") as f:
            f.write(launcher_text(label, conf, prog))
        n += 1
    return n

def launch(program=None, home=None, timeout=None):
    home, dos_root, shared, prints = places(home)
    if program:
        program = os.path.abspath(program)
        program_dir = os.path.dirname(program)
        name = os.path.basename(program)
        tag = os.path.splitext(name)[0]
    else:
        program_dir = dos_root
        name = ""
        tag = "shell"
    conf_dir = os.path.join(home, ".config", "matryoshka", "dos")
    label = tag
    if not tag.isascii() or " " in tag:
        tag = "prog%08x" % (zlib.crc32(program.encode()) if program else 0)
    conf = os.path.join(conf_dir, tag + ".conf")
    base = os.path.join(link_base(home), tag)
    desk = desktop_dir(home)
    text = session_text(ascii_link(base, "c", program_dir), name, ascii_link(base, "d", dos_root), ascii_link(base, "e", home), ascii_link(base, "f", shared), ascii_link(base, "p", prints), ascii_link(base, "g", desk) if desk else None)
    if name and not dos_name(name):
        ext = os.path.splitext(name)[1].upper()
        if ext not in (".EXE", ".COM", ".BAT"):
            ext = ".EXE"
        run_dir = os.path.join(base, "run")
        os.makedirs(run_dir, exist_ok=True)
        for old in os.listdir(run_dir):
            os.remove(os.path.join(run_dir, old))
        os.symlink(program, os.path.join(run_dir, "RUN" + ext))
        text = text.replace("c:\n" + run_line(name), "mount -q y \"%s\"\nc:\n%s" % (run_dir, run_line("y:\\RUN" + ext)), 1)
    write_conf(conf, text)
    if name:
        write_launcher(home, label, conf, program)
    env = dict(os.environ, LANG=os.environ.get("LANG") or "ru_RU.UTF-8")
    proc = subprocess.Popen(["dosbox-x", "-nopromptfolder", "-fastlaunch", "-conf", conf], env=env)
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        code = 124
    to_pdf(prints)
    return code

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--add-file":
        sys.exit(add_file(sys.argv[2]))
    if len(sys.argv) > 2 and sys.argv[1] == "--open-dir":
        sys.exit(open_dir(sys.argv[2]))
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh-launchers":
        print(refresh_launchers())
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--add-file-dos":
        sys.exit(add_file(places()[1]))
    if len(sys.argv) > 1 and sys.argv[1] == "--open-dir-dos":
        sys.exit(open_dir(places()[1]))
    if len(sys.argv) > 1 and sys.argv[1] != "--shell":
        sys.exit(launch(sys.argv[1]))
    sys.exit(launch(None))
