"""Fix receipt_ocr.py - use chr for all special chars."""
import pathlib

BS = chr(92)   # backslash
NL = chr(10)   # newline (LF)
DQ = chr(34)   # double quote
SQ = chr(39)   # single quote
APOS = chr(0x2019)  # Unicode right single quotation mark

B = pathlib.Path("app/services/receipt_ocr.py").read_text("utf-8")
lines = B.split(NL)
fixes = 0

# 1. Fix NOISE_RE: r"[^a-zA-Z0-9.,:;() @'<APOS>\t]+"
for i, line in enumerate(lines):
    s = line.strip()
    if s.startswith("_NOISE_RE ="):
        pat = "[^a-zA-Z0-9.,:;() @" + SQ + APOS + BS + "t]+"
        lines[i] = "_NOISE_RE = re.compile(r" + DQ + pat + DQ + ")"
        print("Fixed NOISE_RE at line " + str(i+1))
        fixes += 1
        break

# 2. Remove vo\s|void| from SUMMARY_LINE_RE
for i, line in enumerate(lines):
    if "harga" in line and "jual" in line:
        target = "vo" + BS + "s|void|harga"
        if target in line:
            lines[i] = line.replace(target, "harga")
            print("Removed vo from SUMMARY at line " + str(i+1))
            fixes += 1
        break

# 3. Add vo to NAME_SKIP_RE
for i, line in enumerate(lines):
    if "hema|jumlah|qty|" in line:
        lines[i] = line.replace("hema|jumlah|qty|", "hema|jumlah|qty|vo|")
        print("Added vo to NAME_SKIP_RE at line " + str(i+1))
        fixes += 1
        break

# 4. Add _DATE_LINE_RE before _FINANCIAL_TOLERANCE
for i, line in enumerate(lines):
    if line.startswith("_FINANCIAL_TOLERANCE"):
        date_pat = "^[0-9][0-9.,/:-]*[0-9]" + BS + "s+[0-9]"
        lines[i] = "_DATE_LINE_RE = re.compile(r" + SQ + date_pat + SQ + ")" + NL + line
        print("Added _DATE_LINE_RE at line " + str(i+1))
        fixes += 1
        break

# 5. Add date check in _parse_item_line
for i, line in enumerate(lines):
    if line.startswith("def _parse_item_line"):
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and "if not line" in lines[j]:
            indent = ""
            for ch in lines[j]:
                if ch == " ":
                    indent += " "
                else:
                    break
            dc1 = indent + "if not line or _DATE_LINE_RE.match(line.strip()):"
            dc2 = indent + "    return None"
            lines[j] = dc1 + NL + dc2 + NL + lines[j]
            print("Added date check at line " + str(j+1))
            fixes += 1
        break

B = NL.join(lines)
pathlib.Path("app/services/receipt_ocr.py").write_text(B, "utf-8", newline="")
print("\nTotal fixes: " + str(fixes))
