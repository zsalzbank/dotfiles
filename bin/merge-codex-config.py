import os
from pathlib import Path
import shutil
import sys
import tempfile

import tomlkit


source, destination, timestamp = sys.argv[1:]
destination = Path(destination).expanduser().resolve()
original = destination.read_text() if destination.exists() else ""
config = tomlkit.parse(original)


def merge(target, settings):
    for key, value in settings.items():
        if isinstance(value, dict):
            if key not in target:
                target[key] = tomlkit.table()
            merge(target[key], value)
        else:
            target[key] = value


merge(config, tomlkit.parse(Path(source).read_text()))
updated = tomlkit.dumps(config)
if updated != original:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.copy2(destination, f"{destination}.backup.{timestamp}")
    fd, temporary = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(updated)
        if destination.exists():
            shutil.copymode(destination, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
