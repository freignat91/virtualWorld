import sys

buffer = []
in_traceback = False

for line in sys.stdin:
    if line.startswith("Traceback"):
        in_traceback = True
        buffer = [line]
        continue
    if in_traceback:
        buffer.append(line)
        if not line.startswith(" ") and not line.startswith("Traceback"):
            if "ssl" not in "".join(buffer).lower() and "Removing descriptor" not in "".join(buffer):
                sys.stdout.write("".join(buffer))
                sys.stdout.flush()
            buffer = []
            in_traceback = False
        continue
    if "Removing descriptor" in line:
        continue
    sys.stdout.write(line)
    sys.stdout.flush()
