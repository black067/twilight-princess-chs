import paths
import re
import sys


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else "J2DTextBox"
    skip = sys.argv[2] if len(sys.argv) > 2 else None
    data = open(paths.dusklight_exe(), "rb").read()
    hits = {}
    for m in re.finditer(rb"[ -~]{6,200}", data):
        s = m.group().decode("ascii", "ignore")
        if pat in s and (skip is None or skip not in s):
            hits[s] = hits.get(s, 0) + 1
    print("exe bytes: %d, matches: %d" % (len(data), len(hits)))
    for s in sorted(hits):
        print(s)


main()
