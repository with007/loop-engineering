import sys, os

log_path = sys.argv[1]
with open(log_path, 'a', encoding='utf-8', buffering=1) as f:
    for line in sys.stdin:
        sys.stdout.write(line)
        sys.stdout.flush()
        f.write(line)
        f.flush()
