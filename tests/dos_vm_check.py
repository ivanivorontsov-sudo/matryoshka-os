import os, shutil, struct, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import dosbox

COM = r"""
org 100h
bits 16
start:
    mov ah,3Ch
    xor cx,cx
    mov dx,result
    int 21h
    jc die
    mov [handle],ax
    mov bx,ax
    mov dx,greet
    mov cx,greet_len
    mov ah,40h
    int 21h
    mov ah,4Eh
    mov cx,37h
    mov dx,maskc
    int 21h
    jc noc
    mov dx,cok
    mov cx,cok_len
    jmp wc
noc:
    mov dx,cno
    mov cx,cno_len
wc:
    mov ah,40h
    mov bx,[handle]
    int 21h
    mov ah,4Eh
    mov cx,37h
    mov dx,maskd
    int 21h
    jc nod
    mov dx,dok
    mov cx,dok_len
    jmp wd
nod:
    mov dx,dno
    mov cx,dno_len
wd:
    mov ah,40h
    mov bx,[handle]
    int 21h
    xor ax,ax
    int 33h
    cmp ax,0FFFFh
    jne nom
    mov dx,mok
    mov cx,mok_len
    jmp wm
nom:
    mov dx,mno
    mov cx,mno_len
wm:
    mov ah,40h
    mov bx,[handle]
    int 21h
    mov dx,226h
    mov al,1
    out dx,al
    mov cx,20
sbd1:
    push cx
    mov cx,0FFFFh
sbd2:
    loop sbd2
    pop cx
    loop sbd1
    xor al,al
    out dx,al
    mov cx,20
sbd3:
    push cx
    mov cx,0FFFFh
sbd4:
    loop sbd4
    pop cx
    loop sbd3
    mov dx,22Eh
    mov cx,0FFFFh
sbwait:
    in al,dx
    test al,80h
    jnz sbdata
    loop sbwait
    jmp nosb
sbdata:
    mov dx,22Ah
    in al,dx
    cmp al,0AAh
    je sbgood
    jmp nosb
sbgood:
    mov dx,sok
    mov cx,sok_len
    jmp wsb
nosb:
    mov dx,sno
    mov cx,sno_len
wsb:
    mov ah,40h
    mov bx,[handle]
    int 21h
    mov si,page
pr:
    lodsb
    test al,al
    jz prdone
    mov dx,378h
    out dx,al
    mov dx,37Ah
    push ax
    mov al,0Dh
    out dx,al
    mov al,0Ch
    out dx,al
    pop ax
    jmp pr
prdone:
    mov cx,8
outer:
    push cx
    mov cx,0FFFFh
inner:
    loop inner
    pop cx
    loop outer
    mov ah,3Eh
    mov bx,[handle]
    int 21h
    mov ax,4C00h
    int 21h
die:
    mov ax,4C01h
    int 21h
delay:
    mov cx,2000h
dloop:
    loop dloop
    ret
handle dw 0
result db "RESULT.TXT",0
maskc db "C:\*.*",0
maskd db "D:\*.*",0
greet db "CP866:",0AFh,0E0h,0A8h,0A2h,0A5h,0E2h,13,10
greet_len equ $-greet
cok db "C=OK",13,10
cok_len equ $-cok
cno db "C=NO",13,10
cno_len equ $-cno
dok db "D=OK",13,10
dok_len equ $-dok
dno db "D=NO",13,10
dno_len equ $-dno
mok db "MOUSE=OK",13,10
mok_len equ $-mok
mno db "MOUSE=NO",13,10
mno_len equ $-mno
sok db "SB=OK",13,10
sok_len equ $-sok
sno db "SB=NO",13,10
sno_len equ $-sno
page db "DOS-PRINT",13,10,12,0
"""

EXE_BODY = r"""
org 0
bits 16
    push cs
    pop ds
    mov ah,3Ch
    xor cx,cx
    mov dx,name
    int 21h
    jc bad
    mov bx,ax
    mov ah,3Eh
    int 21h
    mov ax,4C00h
    int 21h
bad:
    mov ax,4C02h
    int 21h
name db "EXE.OK",0
"""

def asm(src, out):
    p = out + ".asm"
    open(p, "w").write(src)
    r = subprocess.run(["nasm", "-f", "bin", "-o", out, p], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr)

def mz(payload):
    size = 32 + len(payload)
    hdr = bytearray(32)
    hdr[0:2] = b"MZ"
    hdr[2:4] = struct.pack("<H", size % 512)
    hdr[4:6] = struct.pack("<H", (size + 511) // 512)
    hdr[8:10] = struct.pack("<H", 2)
    hdr[10:12] = struct.pack("<H", 0x20)
    hdr[14:16] = struct.pack("<H", 0)
    hdr[16:18] = struct.pack("<H", 0x200)
    hdr[20:22] = struct.pack("<H", 0)
    hdr[22:24] = struct.pack("<H", 0)
    return bytes(hdr) + payload

def main():
    root = tempfile.mkdtemp(prefix="dosvm-")
    os.makedirs(os.path.join(root, "DOS"))
    os.makedirs(os.path.join(root, "Общее"))
    prog = os.path.join(root, "prog")
    os.makedirs(prog)
    asm(COM, os.path.join(prog, "PROBE.COM"))
    body = os.path.join(prog, "body.bin")
    asm(EXE_BODY, body)
    open(os.path.join(prog, "PROBE.EXE"), "wb").write(mz(open(body, "rb").read()))
    open(os.path.join(prog, "RUN.BAT"), "w", newline="\r\n").write("@echo off\r\necho BATOK> C:\\BAT.OK\r\nSET > C:\\ENV.TXT\r\nCONFIG -get sblaster sbtype > C:\\SBTYPE.TXT\r\nPROBE.COM\r\nPROBE.EXE\r\nexit\r\n")
    open(os.path.join(prog, "DATA.CAD"), "w").write("cad-data")
    env = dict(os.environ, DISPLAY=os.environ.get("DISPLAY") or ":1", SDL_AUDIODRIVER=os.environ.get("SDL_AUDIODRIVER") or "dummy")
    os.environ.update(env)
    code = dosbox.launch(os.path.join(prog, "RUN.BAT"), home=root, timeout=90)
    prints = os.path.join(root, "DOS", "Печать")
    result = os.path.join(prog, "RESULT.TXT")
    bat = os.path.join(prog, "BAT.OK")
    exe = os.path.join(prog, "EXE.OK")
    pdfs = []
    if os.path.isdir(prints):
        pdfs = [n for n in os.listdir(prints) if n.lower().endswith(".pdf") or n.lower().endswith(".ps")]
    text = open(result, "rb").read() if os.path.isfile(result) else b""
    print("ROOT", root)
    print("EXIT", code)
    print("RESULT", text)
    print("BAT", os.path.isfile(bat), "EXE", os.path.isfile(exe))
    print("PRINT", pdfs)
    pdf = next((os.path.join(prints, n) for n in pdfs if n.lower().endswith(".pdf")), "")
    ink = False
    if pdf and shutil.which("gs"):
        png = os.path.join(prints, "page.png")
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=png16m", "-r40", "-sOutputFile=" + png, pdf], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(png):
            raw = open(png, "rb").read()
            ink = raw.count(b"\xff\xff\xff") * 3 < len(raw) - 200
    env = open(os.path.join(prog, "ENV.TXT"), "rb").read() if os.path.isfile(os.path.join(prog, "ENV.TXT")) else b""
    sbtype = open(os.path.join(prog, "SBTYPE.TXT"), "rb").read() if os.path.isfile(os.path.join(prog, "SBTYPE.TXT")) else b""
    print("ENV", env)
    print("SBTYPE", sbtype)
    print("INK", ink)
    printed = ink
    sound = b"SB=OK" in text or (b"sb16" in sbtype.lower() and b"BLASTER=A220" in env.upper())
    ok = code == 0 and b"CP866:" in text and bytes([0xAF, 0xE0, 0xA8]) in text and b"C=OK" in text and b"D=OK" in text and b"MOUSE=OK" in text and sound and os.path.isfile(bat) and os.path.isfile(exe) and printed
    print("PDF_HAS_TEXT", printed)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
