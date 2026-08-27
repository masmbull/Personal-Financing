"""Fix _DATE_LINE_RE pattern: change \s+ to [.,/:-]+ to match date lines without spaces."""
import pathlib

NL = chr(10)
SQ = chr(39)  # single quote

B = pathlib.Path("app/services/receipt_ocr.py").read_text("utf-8")
lines = B.split(NL)

for i, line in enumerate(lines):
    if line.strip().startswith("_DATE_LINE_RE = re.compile"):
        new_pat = "^[0-9][0-9.,/:-]*[0-9][.,/:-]+[0-9]"
        lines[i] = "_DATE_LINE_RE = re.compile(r" + SQ + new_pat + SQ + ")"
        print("Fixed _DATE_LINE_RE at line " + str(i+1))
        print("New content: " + lines[i])
        break

B = NL.join(lines)
pathlib.Path("app/services/receipt_ocr.py").write_text(B, "utf-8", newline="")
print("Done")
