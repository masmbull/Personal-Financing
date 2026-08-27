#!/usr/bin/env python3
"""Assemble new receipt_ocr.py from parts."""
import pathlib

p = pathlib.Path("_ocr_parts")
out = pathlib.Path("app/services/receipt_ocr.py")

content = ""
for name in ["_sec1.txt", "sec_items.txt", "sec_cat.txt", "sec_conf.txt", "sec_engines.txt"]:
    f = p / name
    if f.exists():
        content += f.read_text("utf-8") + "\n"
        print(f"  + {name} ({len(f.read_text('utf-8'))} chars)")
    else:
        print(f"  MISSING: {name}")

out.write_text(content, "utf-8")
print(f"Wrote {out}: {len(content)} chars, {len(content.splitlines())} lines")
