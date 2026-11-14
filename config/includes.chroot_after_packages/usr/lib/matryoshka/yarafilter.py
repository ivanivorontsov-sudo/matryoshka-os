import re, sys, os, tempfile

HEAD = re.compile(r"^(?:(?:private|global)\s+)*rule\s+(\w+)")
DROP = re.compile(r'^\s*id\s*=\s*"(?:a1fbf4fe-b934-4a66-b6b1-ebe2f83505cd)"', re.M)


def split(text):
    parts, cur = [], []
    for line in text.splitlines(True):
        if HEAD.match(line) and cur:
            parts.append("".join(cur))
            cur = []
        cur.append(line)
    if cur:
        parts.append("".join(cur))
    return parts


def clean(text):
    parts = split(text)
    gone = set()
    while True:
        ref = re.compile(r"\b(" + "|".join(map(re.escape, sorted(gone))) + r")\b") if gone else None
        new = set()
        for p in parts:
            m = HEAD.match(p)
            if m and m.group(1) not in gone and (DROP.search(p) or (ref and ref.search(p[m.end():]))):
                new.add(m.group(1))
        if not new:
            break
        gone |= new
    keep = [p for p in parts if not (HEAD.match(p) and HEAD.match(p).group(1) in gone)]
    return "".join(keep), sorted(gone)


def main(path):
    text = open(path, encoding="utf-8", errors="surrogateescape").read()
    out, gone = clean(text)
    if gone:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".yar.")
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(out)
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
        os.replace(tmp, path)
    print(len(gone))


if __name__ == "__main__":
    main(sys.argv[1])
