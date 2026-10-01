#!/usr/bin/env python3
"""
Builds the trainee starter scripts in workbook/ from the full solutions in
instructor-only/solutions/. Every block between

    # >>> SOLUTION: <title>
    # HINT: ...
    <solution code>
    # <<<

is replaced by the HINT lines plus a clear "TODO" stop, so a trainee fills
the gaps in one at a time: run, read the TODO message, write the code, run again.

Edit the solutions, then run:   python3 instructor-only/make_workbook.py
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "workbook")


def strip(src, name):
    out, skipping, n = [], False, 0
    for line in src.splitlines():
        m = re.match(r"^(\s*)# >>> SOLUTION: (.*)$", line)
        if m:
            indent, title = m.groups()
            n += 1
            out.append(f"{indent}# ---- TODO {n}: {title} ----")
            skipping = True
            continue
        if skipping:
            if line.strip() == "# <<<":
                out.append(f'{indent}raise NotImplementedError("TODO {n} in {name}: {title} - see the HINT above, '
                           f'write your code, then delete this line")')
                skipping = False
            elif line.strip().startswith("# HINT") or (line.strip().startswith("#") and out[-1].strip().startswith("#")):
                out.append(line)
            continue
        out.append(line)
    return "\n".join(out) + "\n", n


os.makedirs(OUT, exist_ok=True)
for path in sorted(glob.glob(os.path.join(HERE, "solutions", "*.py"))):
    name = os.path.basename(path)
    text, n = strip(open(path).read(), name)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(text)
    print(f"workbook/{name}: {n} TODO(s)")
