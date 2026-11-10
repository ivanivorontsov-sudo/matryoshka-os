import glob, os, shutil, subprocess, sys, zlib

def q(path):
    return path.replace('"', "").replace("\\", "/")

def run_line(name):
    plain = name.isascii() and " " not in name
    cmd = name if plain else '"%s"' % name
    if name.lower().endswith(".bat"):
        return "call %s\n" % cmd
    return "%s\n" % cmd

def session_text(program_dir, program, dos_root, home, shared, print_dir):
    program_dir, dos_root, home, shared, print_dir = (q(p) for p in (program_dir, dos_root, home, shared, print_dir))
    name = program.replace('"', "")
    run = run_line(name) if name else "echo C: program, D: DOS, E: home, F: shared\n"
    return """[sdl]
fullscreen=false
autolock=false
output=surface
usesystemcursor=true
mouse_emulation=always
[dosbox]
machine=svga_s3
memsize=64
captures={print_dir}
startup_verbosity=quiet
startbanner=false
quit warning=false
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
set TEMP=C:\\
set TMP=C:\\
set BLASTER=A220 I7 D1 H5 P330 T6
path c:\\;d:\\;z:\\;z:\\system;z:\\bin;z:\\dos;z:\\4dos;z:\\textutil
c:
{run}""".format(program_dir=program_dir, dos_root=dos_root, home=home, shared=shared, print_dir=print_dir, run=run)

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
    with open(path, "w", encoding="utf-8") as f:
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
    text = session_text(ascii_link(base, "c", program_dir), name, ascii_link(base, "d", dos_root), ascii_link(base, "e", home), ascii_link(base, "f", shared), ascii_link(base, "p", prints))
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
    desk = next((p for p in (os.path.join(home, "Рабочий стол"), os.path.join(home, "Desktop")) if os.path.isdir(p)), None)
    if desk and name:
        lf = os.path.join(desk, label + " (DOS).desktop")
        if not os.path.exists(lf):
            with open(lf, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=%s (DOS)\nExec=dosbox-x -nopromptfolder -fastlaunch -conf \"%s\"\nIcon=dosbox-x\n" % (label, conf))
            os.chmod(lf, 0o755)
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
    if len(sys.argv) > 1 and sys.argv[1] != "--shell":
        sys.exit(launch(sys.argv[1]))
    sys.exit(launch(None))
