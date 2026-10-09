#!/usr/bin/env python3
"""Генератор проекта KiCad: Volt-Unit - дифференциальный вольтметр-пробник.

Тракт: щупы V+ / V- через 470 кОм (0805, 150 В) на дифференциальный усилитель
LMV358 (половинка A), коэффициент 18k/470k = 0.0369; выход смещён на опору
1.65 В (делитель 10k/10k + буфер, половинка B). Прошивка считает:
    Vдифф = (OUT - 1.65) * 27.1   [диапазон около +-44 В]
Щупы можно совать любой полярностью в любые две точки - знак даёт математика.
Вольтметр БЫСТРЫЙ: полоса тракта ~0.5 МГц (узел входа 470k||18k с ёмкостью
клампов ~15 пФ, выходной RC 220R+470пФ), чтобы мозги по осциллограмме
опознавали провод: масса / питание / LIN / K-line / CAN (500 кбит виден как
меандр между уровнями) / ШИМ форсунок. Вход выдерживает выбросы до +-80 В
и случайные 220 В: ток через 470к мал, клампы BAT54S прижимают входы ОУ к
рельсам. Логика 3.3 В: J1 LOGIC (3V3, GND, OUT - на АЦП), J2 PROBE (V+, V-).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "boards/Volt-Unit"
NAME = "Volt-Unit"
X0, X1, Y0, Y1 = 112.0, 128.0, 94.0, 112.0
BW, BH = X1 - X0, Y1 - Y0
CXB, CYB = (X0 + X1) / 2, (Y0 + Y1) / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP = 0.25, 0.4

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
R0805 = ("Resistor_SMD", "R_0805_2012Metric")
HDRLIB = "Connector_PinHeader_2.54mm"
SO8 = ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")
SOT23 = ("Package_TO_SOT_SMD", "SOT-23")

b = Builder(layers=2)

# ------------------------------------------------------------ размещение
# Расстановка ручная (KiCad, 2026-10-09).
b.place("U1", SO8[0], SO8[1], 120.53, 100.91, 180, value="LMV358")
b.place("J2", HDRLIB, "PinHeader_1x02_P2.54mm_Vertical", 119.46, 96.0, 90, value="PROBE")
b.place("J1", HDRLIB, "PinHeader_1x03_P2.54mm_Vertical", 117.5, 110.0, 90, value="LOGIC")
# входные резисторы - 0805: у них рабочее напряжение 150 В (0402 всего 50 В)
b.place("R1", R0805[0], R0805[1], 113.5, 96.41, -90, value="470k")
b.place("R2", R0805[0], R0805[1], 125.5, 96.59, -90, value="470k")
# клампы входов ОУ на рельсы
b.place("D1", SOT23[0], SOT23[1], 114.56, 101.94, -90, value="BAT54S")
b.place("D2", SOT23[0], SOT23[1], 125.56, 104.5, 180, value="BAT54S")
# усилитель: плечи 18k
b.place("R3", R0402[0], R0402[1], 116.53, 104.25, 0, value="18k")
b.place("R4", R0402[0], R0402[1], 122.52, 105.25, -90, value="18k")
# опора 1.65 В
b.place("R5", R0402[0], R0402[1], 114.5, 107.51, 90, value="10k")
b.place("R6", R0402[0], R0402[1], 118.01, 107.0, 0, value="10k")
b.place("C2", C0402[0], C0402[1], 115.5, 99.0, 180, value="100nF")
# выходной RC-фильтр 220R+470пФ (~1.5 МГц - шины и ШИМ доходят до АЦП)
b.place("R7", R0402[0], R0402[1], 123.49, 107.0, 0, value="220R")
b.place("C1", C0402[0], C0402[1], 126.5, 107.98, 90, value="470pF")
# развязка питания ОУ
b.place("C3", C0402[0], C0402[1], 126.02, 99.0, 180, value="100nF")

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "Volt-Unit: differential voltmeter probe, +-44V, 3.3V logic")
d.prepare()
# LMV358: A (1,2,3) - дифф. усилитель, B (5,6,7) - буфер опоры 1.65 В
d.add(kigen.Part("U1", "Amplifier_Operational:LMV358", "LMV358",
                 "%s:%s" % SO8,
                 {"1": "AOUT", "2": "FB", "3": "INP", "4": "GND",
                  "5": "VREFD", "6": "VREF", "7": "VREF", "8": "+3V3"},
                 at=(120, 80)))
d.add(kigen.Part("J1", "Connector_Generic:Conn_01x03", "LOGIC",
                 "%s:PinHeader_1x03_P2.54mm_Vertical" % HDRLIB,
                 {"1": "+3V3", "2": "GND", "3": "OUT"}, at=(60, 80)))
d.add(kigen.Part("J2", "Connector_Generic:Conn_01x02", "PROBE",
                 "%s:PinHeader_1x02_P2.54mm_Vertical" % HDRLIB,
                 {"1": "VIN+", "2": "VIN-"}, at=(60, 140)))
d.add(kigen.Part("R1", "Device:R", "470k", "%s:%s" % R0805,
                 {"1": "VIN+", "2": "INP"}, at=(230, 60)))
d.add(kigen.Part("R2", "Device:R", "470k", "%s:%s" % R0805,
                 {"1": "VIN-", "2": "FB"}, at=(230, 100)))
d.add(kigen.Part("R3", "Device:R", "18k", "%s:%s" % R0402,
                 {"1": "INP", "2": "VREF"}, at=(230, 140)))
d.add(kigen.Part("R4", "Device:R", "18k", "%s:%s" % R0402,
                 {"1": "FB", "2": "AOUT"}, at=(230, 180)))
d.add(kigen.Part("R5", "Device:R", "10k", "%s:%s" % R0402,
                 {"1": "+3V3", "2": "VREFD"}, at=(300, 60)))
d.add(kigen.Part("R6", "Device:R", "10k", "%s:%s" % R0402,
                 {"1": "VREFD", "2": "GND"}, at=(300, 100)))
d.add(kigen.Part("R7", "Device:R", "220R", "%s:%s" % R0402,
                 {"1": "AOUT", "2": "OUT"}, at=(300, 140)))
d.add(kigen.Part("C1", "Device:C", "470pF", "%s:%s" % C0402,
                 {"1": "OUT", "2": "GND"}, at=(370, 60)))
d.add(kigen.Part("C2", "Device:C", "100nF", "%s:%s" % C0402,
                 {"1": "VREFD", "2": "GND"}, at=(370, 100)))
d.add(kigen.Part("C3", "Device:C", "100nF", "%s:%s" % C0402,
                 {"1": "+3V3", "2": "GND"}, at=(370, 140)))
# BAT54S: 1 - анод нижнего (GND), 2 - катод верхнего (3V3), 3 - средняя точка
d.add(kigen.Part("D1", "Diode:BAT54S", "BAT54S", "%s:%s" % SOT23,
                 {"1": "GND", "2": "+3V3", "3": "INP"}, at=(440, 60)))
d.add(kigen.Part("D2", "Diode:BAT54S", "BAT54S", "%s:%s" % SOT23,
                 {"1": "GND", "2": "+3V3", "3": "FB"}, at=(440, 110)))
for i, n in enumerate(["GND", "+3V3"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(480, 60 + 22 * i)))

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
# --- щупы -> входные резисторы (верхний край)
b.track("VIN+", [(119.46, 96.0), (118.3, 95.0), (114.1, 95.0), (113.5, 95.5)], FCU, W)
b.track("VIN-", [(122.0, 96.0), (123.2, 95.0), (125.0, 95.0), (125.5, 95.675)], FCU, W)
# --- INP: R1.2 -> D1.3 -> R3.1, и верхом на восток в U1.3
b.track("INP", [(113.5, 97.325), (113.5, 98.0), (114.4, 98.7), (114.4, 102.3),
                (114.562, 102.875)], FCU, W)                                     # R1.2 -> D1.3
b.track("INP", [(114.562, 102.875), (114.562, 103.6), (115.4, 104.251),
                (116.022, 104.251)], FCU, W)                                     # D1.3 -> R3.1
b.track("INP", [(113.5, 97.325), (113.78, 97.6), (123.9, 97.6), (124.35, 98.15),
                (124.35, 99.8), (123.78, 100.27), (123.0, 100.27)], FCU, W)      # R1.2 -> U1.3
# --- FB: R2.2 -> U1.2 -> D2.3 -> R4.1
b.track("FB", [(125.5, 97.5), (125.5, 98.1), (124.9, 98.55), (124.9, 103.9),
               (124.625, 104.5)], FCU, W)                                        # R2.2 -> D2.3
b.track("FB", [(124.9, 101.2), (124.0, 101.54), (123.0, 101.54)], FCU, W)        # ветка в U1.2
b.track("FB", [(124.625, 104.5), (123.5, 104.74), (122.518, 104.74)], FCU, W)    # D2.3 -> R4.1
# --- AOUT: U1.1 -> R4.2 -> R7.1
b.track("AOUT", [(123.0, 102.81), (123.0, 103.3), (121.8, 104.0), (121.8, 105.76),
                 (122.223, 105.76)], FCU, W)
b.track("AOUT", [(122.518, 105.76), (122.518, 106.3), (122.98, 106.8),
                 (122.98, 107.0)], FCU, W)
# --- OUT: R7.2 -> C1.1 и в J1.3
b.track("OUT", [(124.0, 107.0), (125.2, 107.8), (126.5, 108.46)], FCU, W)
b.track("OUT", [(124.0, 107.0), (123.2, 108.6), (122.58, 110.0)], FCU, W)
# --- VREF: мост U1.6-U1.7 и плечо R3.2
b.track("VREF", [(118.05, 100.27), (118.05, 101.54)], FCU, W)
b.track("VREF", [(117.042, 104.251), (116.65, 103.8), (116.65, 102.1),
                 (117.3, 101.54), (118.05, 101.54)], FCU, W)
# --- VREFD: C2.1 -> U1.5 поверху, юг (R5.2/R6.1) через B
b.track("VREFD", [(115.98, 99.0), (118.05, 99.0)], FCU, W)
b.track("VREFD", [(116.7, 99.0), (116.7, 99.75)], FCU, W)
b.via("VREFD", 116.7, 99.75)
b.track("VREFD", [(116.7, 99.75), (116.4, 99.75), (115.9, 107.6)], BCU, W)
b.via("VREFD", 115.9, 107.6)
b.track("VREFD", [(115.9, 107.6), (115.9, 107.0)], FCU, W)
b.track("VREFD", [(114.795, 107.0), (117.205, 107.0)], FCU, W)                   # R5.2 -> R6.1
# --- +3V3: J1.1 -> R5.1 -> запад -> D1.2; J1.1 -> U1.8; восток C3.1/D2.2 через B
b.track("+3V3", [(117.5, 110.0), (115.1, 108.6), (114.6, 108.3),
                 (114.5, 108.02)], FCU, W)                                       # J1.1 -> R5.1
b.track("+3V3", [(114.5, 108.02), (113.5, 108.02), (112.75, 107.3),
                 (112.75, 101.4), (113.2, 101.0)], FCU, W)                       # запад -> D1.2
b.track("+3V3", [(117.5, 110.0), (118.6, 109.0), (119.25, 108.5), (119.25, 103.9),
                 (118.5, 103.3), (118.3, 103.11), (118.3, 102.81)], FCU, W)      # J1.1 -> U1.8
b.track("+3V3", [(126.5, 99.0), (126.5, 103.55)], FCU, W)                        # C3.1 -> D2.2
b.track("+3V3", [(126.5, 101.5), (127.35, 102.2), (127.35, 104.5)], FCU, W)
b.via("+3V3", 127.35, 104.5)
b.track("+3V3", [(127.35, 104.5), (116.0, 109.2), (115.9, 109.2)], BCU, W)       # восток -> юго-запад по B
b.via("+3V3", 115.9, 109.2)
b.track("+3V3", [(115.9, 109.2), (116.25, 109.27)], FCU, W)                      # стык в диагональ J1.1-R5.1
# --- GND: зоны + стежки; C2.2/C3.2 зажаты дорожками - тянем явные перемычки
b.via("GND", 120.6, 98.3)
b.via("GND", 120.8, 106.2)
b.track("GND", [(115.02, 99.295), (115.513, 100.6), (115.513, 101.0)], FCU, W)   # C2.2 -> D1.1
b.track("GND", [(125.54, 99.295), (125.54, 100.2), (125.7, 100.7)], FCU, W)      # C3.2 -> via
b.via("GND", 125.7, 100.7)
b.via("GND", 120.7, 94.65)                                                       # северная полоса зоны
b.via("GND", 126.9, 94.6)
b.via("GND", 115.4, 100.2)                                                       # островок C2.2/D1.1
b.via("GND", 113.0, 110.7)                                                       # юго-запад, главный массив
b.via("GND", 127.2, 110.7)                                                       # юго-восток
b.via("GND", 125.85, 105.9)                                                      # карман D2.1
b.via("GND", 117.8, 105.5)                                                       # центр-запад (карман R6.2)

# ---------------------------------------------- позиции рефов (ручная правка)
for _r, _x, _y, _rot in (
        ("C1", 126.50, 110.00, 90), ("C2", 113.50, 99.00, 180),
        ("C3", 126.01, 100.34, 180), ("D1", 113.00, 104.00, 270),
        ("D2", 126.15, 101.98, 180), ("J1", 114.50, 110.00, 90),
        ("J2", 116.73, 96.02, 90), ("R1", 115.22, 96.38, 270),
        ("R2", 127.15, 96.59, 270), ("R3", 115.66, 105.64, 0),
        ("R4", 120.88, 106.22, 0), ("R5", 113.12, 107.66, 90),
        ("R6", 118.01, 105.83, 0), ("R7", 125.23, 107.50, 270),
        ("U1", 120.53, 104.50, 180)):
    _t = b.fps[_r].Reference()
    _t.SetPosition(V(_x, _y))
    _t.SetTextAngleDegrees(_rot)

# ------------------------------------------------- шелкография
# лицевая: подписи логики (над щупами места нет - V+/V- только сзади)
b.text("3V3", 117.53, 108.08, pcbnew.F_SilkS, 0.6, 0.12)
b.text("GND", 120.07, 108.08, pcbnew.F_SilkS, 0.6, 0.12)
b.text("OUT", 122.61, 108.08, pcbnew.F_SilkS, 0.6, 0.12)
# обратная сторона - ручная раскладка пользователя (2026-10-09), 1:1
BS = pcbnew.B_SilkS
for _x, _y, _sz, _th, _s in (
        # легенда в две колонки
        (116.50, 100.50, 0.6, 0.12, "R3, R4: 18k"),
        (116.50, 101.50, 0.6, 0.12, "R5, R6: 10k"),
        (116.19, 102.54, 0.6, 0.12, "C2, C3: 100n"),
        (116.50, 103.50, 0.6, 0.12, "U1: LMV358"),
        (124.09, 100.56, 0.6, 0.12, "R1, R2: 470k"),
        (124.98, 101.56, 0.6, 0.12, "R7: 220R"),
        (125.00, 102.50, 0.6, 0.12, "C1: 470p"),
        (123.50, 103.50, 0.6, 0.12, "D1, D2: BAT54S"),
        # формула и предел - у щупов
        (120.64, 98.11, 1.0, 0.25, "MAX +-44V"),
        (120.50, 99.50, 0.6, 0.12, "V=(OUT-1.65)x27.1"),
        # крупные подписи пинов
        (116.50, 96.00, 1.0, 0.25, "V+"),
        (124.50, 96.00, 1.0, 0.25, "V-"),
        (114.50, 110.50, 1.0, 0.25, "3V3"),
        (120.04, 108.00, 1.0, 0.25, "GND"),
        (125.50, 110.50, 1.0, 0.25, "OUT"),
        (120.00, 105.50, 1.7, 0.42, "ASTechLab")):
    b.text(_s, _x, _y, BS, _sz, _th, 0, True)

# ------------------------------------------------------------ контур, полигоны
b.edge_rect(CXB, CYB, BW, BH, 1.2)
b.zone("GND", FCU, CXB, CYB, BW - 0.6, BH - 0.6)
b.zone("GND", BCU, CXB, CYB, BW - 0.6, BH - 0.6)

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
print("OK ->", OUT)
