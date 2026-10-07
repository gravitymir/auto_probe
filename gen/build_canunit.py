#!/usr/bin/env python3
"""Генератор проекта KiCad: CAN-Unit - компактный модуль CAN FD, 13x13.4 мм.

Расстановка компонентов - ручная (перенесена из правок в KiCad от 2026-10-07),
скрипт её только воспроизводит и разводит дорожки. TCAN332G (3.3 В, CAN FD
5 Мбит/с) + терминатор 120 Ом на паяной перемычке JP1. Группы выводов:
J3 - CANL/CANH (штыри 2.54), J2 - логика TX/RX, J1 - питание 3V3/GND.
Название и легенда номиналов - на обратной стороне.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "boards/CAN-Unit"
NAME = "CAN-Unit"
X0, X1, Y0, Y1 = 144.6, 157.6, 92.6, 106.0
BW, BH = X1 - X0, Y1 - Y0
CXB, CYB = (X0 + X1) / 2, (Y0 + Y1) / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP = 0.25, 0.4

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
R0603 = ("Resistor_SMD", "R_0603_1608Metric")
HDRLIB = "Connector_PinHeader_2.54mm"

b = Builder(layers=2)

# ------------------------------------------------- размещение (ручное, не менять)
b.place("U1", "Package_TO_SOT_SMD", "SOT-23-8", 147.0, 99.0, 90, value="TCAN332G")
b.place("J3", HDRLIB, "PinHeader_1x02_P2.54mm_Vertical", 147.22, 94.0, 90, value="CAN")
b.place("R1", R0603[0], R0603[1], 153.18, 95.5, 0, value="120R")
b.place("JP1", "Jumper", "SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
        156.0, 94.72, 90, value="TERM")
b.place("J1", HDRLIB, "PinHeader_1x02_P2.54mm_Vertical", 155.5, 101.54, 180, value="PWR")
b.place("J2", HDRLIB, "PinHeader_1x02_P2.54mm_Vertical", 148.46, 104.5, 90, value="LOGIC")
b.place("C1", C0402[0], C0402[1], 150.0, 99.48, 90, value="100nF")
b.place("C2", C0603[0], C0603[1], 152.0, 99.28, 90, value="1uF")

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "CAN-Unit: compact TCAN332G CAN FD module, wire-connected")
d.prepare()
d.add(kigen.Part("U1", "Interface_CAN_LIN:TCAN332", "TCAN332G",
                 "Package_TO_SOT_SMD:SOT-23-8",
                 {"1": "CAN_TX", "2": "GND", "3": "+3V3", "4": "CAN_RX",
                  "6": "CANL", "7": "CANH"}, at=(150, 80)))
d.add(kigen.Part("J1", "Connector_Generic:Conn_01x02", "PWR",
                 "%s:PinHeader_1x02_P2.54mm_Vertical" % HDRLIB,
                 {"1": "+3V3", "2": "GND"}, at=(70, 70)))
d.add(kigen.Part("J2", "Connector_Generic:Conn_01x02", "LOGIC",
                 "%s:PinHeader_1x02_P2.54mm_Vertical" % HDRLIB,
                 {"1": "CAN_TX", "2": "CAN_RX"}, at=(70, 110)))
d.add(kigen.Part("J3", "Connector_Generic:Conn_01x02", "CAN",
                 "%s:PinHeader_1x02_P2.54mm_Vertical" % HDRLIB,
                 {"1": "CANL", "2": "CANH"}, at=(230, 70)))
d.add(kigen.Part("R1", "Device:R", "120R", "%s:%s" % R0603,
                 {"1": "CANH", "2": "TERM"}, at=(230, 110)))
d.add(kigen.Part("JP1", "Jumper:SolderJumper_2_Open", "TERM",
                 "Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
                 {"1": "TERM", "2": "CANL"}, at=(230, 140)))
d.add(kigen.Part("C1", "Device:C", "100nF", "%s:%s" % C0402,
                 {"1": "+3V3", "2": "GND"}, at=(300, 80)))
d.add(kigen.Part("C2", "Device:C", "1uF", "%s:%s" % C0603,
                 {"1": "+3V3", "2": "GND"}, at=(330, 80)))
for i, n in enumerate(["GND", "+3V3"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(360, 80 + 22 * i)))

os.makedirs(OUT, exist_ok=True)
for _pt in d.parts:
    if ":" in _pt.footprint:
        _pt.footprint = "auto_probe:" + _pt.footprint.split(":", 1)[1]
d.write_sch(os.path.join(OUT, NAME + ".kicad_sch"))
for p in d.parts:
    if p.ref.startswith("#"):
        continue
    for pn, net in p.nets.items():
        try:
            b.setnet(p.ref, pn, net)
        except KeyError:
            pass

# ============================================================== разводка
u = lambda n: b.padxy("U1", n)
t1, t2 = b.padxy("J3", 1), b.padxy("J3", 2)      # CANL (147.46,94), CANH (150,94)
jp1p, jp2p = b.padxy("JP1", 1), b.padxy("JP1", 2)  # TERM (156,95.45), CANL (156,94)
r1p, r2p = b.padxy("R1", 1), b.padxy("R1", 2)      # CANH (153,94), TERM (153,95.65)
p1, p2 = b.padxy("J1", 1), b.padxy("J1", 2)        # 3V3 (155.5,101.54), GND (155.5,99)
l1, l2 = b.padxy("J2", 1), b.padxy("J2", 2)        # TX (148.46,104.5), RX (151,104.5)
c1p, c2p = b.padxy("C1", 1), b.padxy("C2", 1)      # 3V3 пады конденсаторов

# CANH: пин 7 -> вверх -> полоса под штырями CAN прямо в R1; ветка в свой штырь
b.track("CANH", [u(7), (u(7)[0], 95.5), r1p], FCU, W)
b.track("CANH", [(t2[0], 95.5), t2], FCU, W)
# CANL: пин 6 -> короткий подъём -> полоса ниже R1 -> нырок под плату:
# одной веткой назад к своему штырю (THT-пад доступен снизу), другой - к
# пятачку перемычки в обход её пада TERM
b.track("CANL", [u(6), (u(6)[0], 96.5), (154.4, 96.5), (154.4, 96.9)], FCU, W)
b.via("CANL", 154.4, 96.9, dia=0.5, drill=0.25)
b.track("CANL", [(154.4, 96.9), (148.2, 96.2), (t1[0], 94.85), t1], BCU, W)
b.track("CANL", [(154.4, 96.9), (156.75, 94.0)], BCU, W)
b.via("CANL", 156.75, 94.0, dia=0.5, drill=0.25)
b.track("CANL", [(156.75, 94.0), jp2p], FCU, W)
# терминатор: R1.2 -> пятачок TERM перемычки
b.track("TERM", [r2p, jp1p], FCU, W)

# логика: TXD/RXD вниз к штырям J2
b.track("CAN_TX", [u(1), (u(1)[0], 103.3), (l1[0], 103.3), l1], FCU, W)
b.track("CAN_RX", [u(4), (u(4)[0], 102.6), (l2[0], 102.6), l2], FCU, W)
# GND пина 2 - отводом на via в полигон (между колоннами TX/RX зоне тесно)
b.track("GND", [u(2), (u(2)[0], 102.0)], FCU, W)
b.via("GND", u(2)[0], 102.0, dia=0.5, drill=0.25)

# +3V3: пин 3 -> via -> короткий нырок -> C1 -> C2 -> штырь питания
V3 = (u(3)[0], 101.05)
b.track("+3V3", [u(3), V3], FCU, WP)
b.via("+3V3", *V3, dia=0.6, drill=0.3)
b.track("+3V3", [V3, (c1p[0], 100.9)], BCU, WP)
b.via("+3V3", c1p[0], 100.9, dia=0.6, drill=0.3)
b.track("+3V3", [(c1p[0], 100.9), c1p], FCU, WP)
b.track("+3V3", [(c1p[0], 100.9), (c2p[0], 100.9), c2p], FCU, WP)
b.track("+3V3", [(c2p[0], 100.9), (p1[0], 100.9), p1], FCU, WP)

# ------------------------------------------------------------ контур, полигоны
b.edge_rect(CXB, CYB, BW, BH, 1.2)
b.zone("GND", FCU, CXB, CYB, BW - 0.6, BH - 0.6)
b.zone("GND", BCU, CXB, CYB, BW - 0.6, BH - 0.6)

# -------------------------------------------- шелкография: лицевая - функции
b.text("CANL", t1[0], 95.55, pcbnew.F_SilkS, 0.5, 0.1)
b.text("CANH", t2[0] + 0.9, 95.55, pcbnew.F_SilkS, 0.5, 0.1)
b.text("TERM", 152.3, 97.3, pcbnew.F_SilkS, 0.5, 0.1)
b.text("TX", l1[0], 103.0, pcbnew.F_SilkS, 0.5, 0.1)
b.text("RX", l2[0], 103.0, pcbnew.F_SilkS, 0.5, 0.1)
b.text("3V3", p1[0], 102.9, pcbnew.F_SilkS, 0.5, 0.1)
b.text("GND", p2[0], 97.5, pcbnew.F_SilkS, 0.5, 0.1)
for _r in ("J1", "J2", "J3", "JP1", "U1", "C1", "C2", "R1"):
    b.fps[_r].Reference().SetVisible(False)

# ------------------------------- обратная сторона: название и легенда (зеркально)
b.text("CAN-Unit", 149.6, 95.9, pcbnew.B_SilkS, 1.1, 0.2, mirror=True)
LEGEND = ["U1 TCAN332G", "C1 100nF", "C2 1uF", "R1+JP 120R"]
wl = max(len(s) for s in LEGEND)
for i, s in enumerate(LEGEND):
    b.text(s.ljust(wl), 149.6, 97.9 + i * 1.6, pcbnew.B_SilkS, 0.8, 0.15, mirror=True)

# ------------------------------------------------ своя библиотека футпринтов
FPLIB = "auto_probe"
LIBDIR = os.path.join(OUT, FPLIB + ".pretty")
os.makedirs(LIBDIR, exist_ok=True)
for _f in os.listdir(LIBDIR):
    if _f.endswith(".kicad_mod"):
        os.remove(os.path.join(LIBDIR, _f))
_saved = set()
for _fp in b.b.GetFootprints():
    _nm = str(_fp.GetFPID().GetLibItemName())
    if _nm not in _saved:
        try:
            _c = pcbnew.Cast_to_FOOTPRINT(_fp.Duplicate(False))
        except TypeError:
            _c = _fp.Duplicate()
        if _c.IsFlipped():
            _c.Flip(_c.GetPosition(), False)
        _c.SetPosition(pcbnew.VECTOR2I(0, 0))
        _c.SetOrientationDegrees(0)
        _c.SetReference("REF**")
        _c.SetValue(_nm)
        pcbhelp.footprint_save(LIBDIR, _c)
        _saved.add(_nm)
    _fp.SetFPID(pcbnew.LIB_ID(FPLIB, _nm))
print("библиотека проекта: %d футпринтов" % len(_saved))

with open(os.path.join(OUT, "fp-lib-table"), "w") as _t:
    _t.write('(fp_lib_table\n  (version 7)\n'
             '  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")(descr "Footprints used by this board"))\n)\n'
             % (FPLIB, FPLIB))

b.finish(os.path.join(OUT, NAME + ".kicad_pcb"))

_pro = os.path.join(OUT, NAME + ".kicad_pro")
if os.path.exists(_pro):
    _d = json.load(open(_pro))
    for _c in _d.get("net_settings", {}).get("classes", []):
        if _c.get("name") == "Default":
            _c["track_width"] = W
    _d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})["min_track_width"] = 0.15
    json.dump(_d, open(_pro, "w"), indent=2)
print("OK ->", OUT)
