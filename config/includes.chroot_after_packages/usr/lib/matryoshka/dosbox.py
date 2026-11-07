import os

CONF = """[sdl]
fullscreen=false
autolock=false
output=opengl
[dosbox]
machine=svga_s3
memsize=64
captures=capture
[render]
aspect=true
scaler=none
[cpu]
core=auto
cputype=auto
cycles=max
[mixer]
nosound=false
rate=44100
[midi]
mpu401=intelligent
mididevice=default
[sblaster]
sbtype=sb16
sbbase=220
irq=7
dma=1
hdma=5
mixer=true
[gus]
gus=false
[speaker]
pcspeaker=true
[joystick]
joysticktype=auto
[serial]
serial1=dummy
[dos]
xms=true
ems=true
umb=true
keyboardlayout=ru
[autoexec]
mount c "{drive}"
mount d "{folder}"
d:
call "{program}"
"""

def conf_text(drive, folder, program):
    return CONF.format(drive=drive.replace('"', ""), folder=folder.replace('"', ""), program=program.replace('"', ""))

def write_conf(path, drive, folder, program):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(conf_text(drive, folder, program))
