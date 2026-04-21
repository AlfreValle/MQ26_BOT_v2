#!/usr/bin/env python3
"""Crea un nuevo dictamen numerado en governance/committee/dictamenes/.

Uso:
  python governance/new-dictamen.py [etiqueta]
  python governance/new-dictamen.py paso_a_live

El número secuencial es YYYY-NNN según archivos existentes en dictamenes/.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMITTEE = ROOT / "governance" / "committee"
DICT = COMMITTEE / "dictamenes"
TEMPLATE = COMMITTEE / "plantilla-acta-y-dictamen.md"


def _next_seq(year: int) -> int:
    rx = re.compile(rf"^{year}-(\d{{3}})_.+\.md$")
    best = 0
    for p in DICT.glob("*.md"):
        m = rx.match(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best + 1


def main() -> int:
    if not TEMPLATE.is_file():
        print(f"No se encuentra plantilla: {TEMPLATE}", file=sys.stderr)
        return 1
    DICT.mkdir(parents=True, exist_ok=True)
    year = datetime.now(timezone.utc).year
    seq = _next_seq(year)
    raw = sys.argv[1] if len(sys.argv) > 1 else "borrador"
    safe = re.sub(r"[^\w\-]+", "_", raw).strip("_")[:60] or "borrador"
    name = f"{year}-{seq:03d}_dictamen_{safe}.md"
    dest = DICT / name
    shutil.copyfile(TEMPLATE, dest)
    print(dest.resolve())
    editor = os.environ.get("EDITOR")
    if not editor:
        editor = "notepad" if sys.platform == "win32" else "nano"
    try:
        subprocess.Popen([editor, str(dest)], close_fds=sys.platform != "win32")
    except OSError as e:
        print(f"Aviso: no se pudo abrir el editor ({editor}): {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
