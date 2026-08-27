"""Fix NOISE_RE to preserve @ and ' in product names."""
import pathlib
c = pathlib.Path("app/services/receipt_ocr.py").read_text("utf-8")
# Find and replace the NOISE_RE pattern
old = "_NOISE_RE = re.compile(r'[^a-zA-Z0-9.,:;() \\\\t]+')"
new = "_NOISE_RE = re.compile(r\"[^a-zA-Z0-9.,:;()@' \\\\t]+\")"
if old in c:
    c = c.replace(old, new)
    pathlib.Path("app/services/receipt_ocr.py").write_text(c, "utf-8")
    print("Fixed NOISE_RE")
else:
    print("Pattern not found")
    for ln in c.splitlines():
        if "_NOISE_RE" in ln:
            print(repr(ln))
            break