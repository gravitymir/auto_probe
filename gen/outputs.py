#!/usr/bin/env python3
"""BOM + карта выводов гребёнок из готовой платы."""
import sys, os, csv, json, re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv

kicadenv.quiet()
import pcbnew

path = sys.argv[1]
out = os.path.dirname(path)
name = os.path.splitext(os.path.basename(path))[0]
b = pcbnew.LoadBoard(path)

rows = defaultdict(list)
tht = {}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    if ref.startswith("REF") or not ref:
        continue
    pads = list(fp.Pads())
    if not pads or all(p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH for p in pads):
        continue        # крепёжные отверстия: паять нечего, в BOM для сборки не нужны
    fid = "%s:%s" % (fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())
    if "SolderJumper" in fid:
        continue        # паяная перемычка - рисунок на меди, покупать и ставить нечего
    rows[(fp.GetValue(), fid)].append(ref)
    # Выводные детали (гребёнки) в SMT-монтаж не идут - помечаем, чтобы не советовать
    # для них номер LCSC как для устанавливаемой автоматом.
    if all(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in pads):
        tht[fp.GetValue()] = True

# Номера LCSC из списка Basic Parts JLCPCB. Ключ - номинал вместе с футпринтом:
# 100nF в 0402 и в 0603 это разные детали с разными номерами.
LCSC = {
    ("100nF", "C_0402_1005Metric"): "C1525",     # Samsung CL05B104KO5NNNC, 16 В
    ("18pF", "C_0402_1005Metric"): "C1549",      # Fenghua 0402CG180J500NT, 50 В, C0G
    ("100nF", "C_0603_1608Metric"): "C14663",    # Yageo CC0603KRX7R9BB104, 50 В
    ("1uF", "C_0603_1608Metric"): "C15849",      # Samsung CL10A105KB8NNNC, 50 В
    ("2.2uF", "C_0603_1608Metric"): "C23630",    # Samsung CL10A225KO8NNNC, 16 В
    ("10uF", "C_0805_2012Metric"): "C15850",     # Samsung CL21A106KAYNNNE, 25 В
    ("4.7uF", "C_0805_2012Metric"): "C1779",     # Samsung CL21A475KAQNNNE, 25 В
    ("10k", "R_0402_1005Metric"): "C25744",      # Uniroyal 0402WGF1002TCE, 1%
    ("1k", "R_0402_1005Metric"): "C11702",       # Uniroyal 0402WGF1001TCE, 1%
    ("5.1k", "R_0402_1005Metric"): "C25905",     # Uniroyal 0402WGF5101TCE, 1%
    ("0R/FB", "R_0402_1005Metric"): "C17168",    # Uniroyal 0402WGF0000TCE
    ("33pF", "C_0402_1005Metric"): "C1562",      # FH 0402CG330J500NT, 50 В, C0G
    ("120R", "R_0603_1608Metric"): "C22787",     # Uniroyal 0603WAF1200T5E, 1% - терминатор CAN
    ("LED", "LED_0805_2012Metric"): "C84256",    # NationStar FC-2012HRK-620D, красный
}
# Замены с той же распиновкой - на случай, когда штатной детали нет на складе.
ALT = {
    "AP2112K-3.3": "аналог по выводам ME6211C33M5G-N (C82942), SOT-23-5, 1 VIN / 2 GND / 3 EN / 5 VOUT",
}
# Активные детали уникальны по номиналу, футпринт для них не нужен.
LCSC_ANY = {
    "STM32G474RET6": "C521608",
    "STM32H723ZGT6": "C730146",
    "AP2112K-3.3": "C51118",
    "25MHz": "C9006",       # Yangxing X322525MOB4SI, SMD-3225 4 пада, CL 12 пФ
    "8MHz": "C115962",      # YXC X50328MSB2GI, SMD-5032 2 пада, CL 20 пФ - под обвязку 33 пФ
    # XKB TS-1187A-B-A-B: Basic Part, корпус 5.1x5.1, шаг падов 3.70 и разлёт
    # выводов 6.5 - совпадает с посадочным местом ALPS SKQG, под которое разведено.
    "RESET": "C318884",
    "BOOT0": "C318884",
    "32.768kHz": "C97606",  # SC-32S, CL 12.5 пФ, корпус 3215 - под нашу обвязку 18 пФ
    "USB-C": "C165948",
    "TCAN332G": "C2671083",  # TI TCAN332GDCNT, SOT-23-8, 3.3 В, CAN FD 5 Мбит/с
    "MSK12C02": "C431540",   # SHOU HAN, движковый SPDT - терминатор вкл/выкл
}
# Требование к нагрузочной ёмкости кварца - по номиналу. Оно остаётся в примечании
# даже когда номер известен: именно CL молча ломает плату при замене детали.
CL_NOTE = {
    "25MHz": "обвязка 18 пФ - только под CL 12...12.5 пФ",
    "32.768kHz": "обвязка 18 пФ - только под CL 12...12.5 пФ",
    "8MHz": "обвязка 33 пФ - только под CL 20 пФ",
}
with open(os.path.join(out, "BOM.csv"), "w", newline="") as f:
    w = csv.writer(f)
    # Имена колонок - те, что ждёт JLCPCB (Comment / Designator / Footprint /
    # LCSC Part #); свои Qty и примечание идут следом, лишние колонки он игнорирует.
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Qty", "Note"])
    # Пассивку берут по номиналу и типоразмеру, а активной детали нужен конкретный
    # номер - советовать для неё "подобрать по номиналу" бессмысленно.
    passive = re.compile(r"^[\d.]+\s*(?:[pnuµmk]?[FRH]|R|k|M|Ohm)\b|^0R$|^LED$", re.I)
    # Одинаковые детали сводим в одну строку по номеру LCSC. У кнопок "номинал" -
    # это функция (RESET / BOOT0), а деталь одна: две строки на один номер
    # JLCPCB помечает как "multiple lines matched to the same part".
    merged = defaultdict(list)
    for (val, fid), refs in rows.items():
        code = LCSC.get((val, fid.split(":")[-1])) or LCSC_ANY.get(val, "")
        merged[(code, fid) if code else (val, fid)].append((val, refs))
    for (_k, fid), group in sorted(merged.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        val0 = group[0][0]
        val = "/".join(sorted({v for v, _ in group}))
        refs = [r for _, rr in group for r in rr]
        code = LCSC.get((val0, fid.split(":")[-1])) or LCSC_ANY.get(val0, "")
        if code:
            note = "проверить наличие на складе"
            if val0 in ALT:
                note += "; " + ALT[val0]
            if any(r.startswith("Y") for r in refs):
                note += "; " + CL_NOTE.get(val0, "сверить CL кварца с обвязкой на плате")
        elif any(r.startswith("Y") for r in refs):
            # Кварц с другой CL уведёт частоту или не запустится.
            note = CL_NOTE.get(val0, "сверить CL кварца с обвязкой на плате") + " - брать кварц с такой же"
        elif tht.get(val0):
            note = "выводная: в SMT-монтаж не идёт, паяется отдельно"
        elif passive.match(val):
            note = "подобрать из JLCPCB Basic Parts по номиналу/типоразмеру"
        else:
            note = "уточнить номер LCSC под конкретную деталь"
        w.writerow([val, ",".join(sorted(refs)), fid, code, len(refs), note])

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
