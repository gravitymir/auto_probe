#!/usr/bin/env python3
"""BOM + карта выводов гребёнок из готовой платы."""
import sys, os, csv, json
from collections import defaultdict
import pcbnew

path = sys.argv[1]
out = os.path.dirname(path)
name = os.path.splitext(os.path.basename(path))[0]
b = pcbnew.LoadBoard(path)

rows = defaultdict(list)
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("REF") or not ref:
        continue
    fid = "%s:%s" % (fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())
    rows[(fp.GetValue(), fid)].append(ref)

# Проверенные номера LCSC (есть в библиотеке сборки JLCPCB)
LCSC = {
    "STM32G474RET6": "C521608",
    "AP2112K-3.3": "C51118",
    "USB-C": "C165948",
}
with open(os.path.join(out, "BOM.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Qty", "Value", "Footprint", "Designators", "LCSC", "Comment"])
    for (val, fid), refs in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        code = LCSC.get(val, "")
        note = "" if code else "подобрать из JLCPCB Basic Parts по номиналу/типоразмеру"
        w.writerow([len(refs), val, fid, ",".join(sorted(refs)), code, note])

geom = os.path.join(out, "_geom.json")
if os.path.exists(geom):
    g = json.load(open(geom))
    netof = g.get("netof", {})
    with open(os.path.join(out, "PINOUT.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Header", "HeaderPin", "MCU_Pin", "Signal"])
        for k, mn in sorted(g["hdrmap"].items(), key=lambda kv: (kv[0].split(".")[0], int(kv[0].split(".")[1]))):
            ref, hn = k.split(".")
            w.writerow([ref, hn, mn, netof.get(str(mn), "")])
print("BOM.csv / PINOUT.csv ->", out)
