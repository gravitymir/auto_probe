#!/usr/bin/env python3
"""Генератор проекта KiCad: Battery-Unit - плата питания от 18650 (ЗАГОТОВКА).

Вынесена из Voice-Unit 2026-10-12: батарейный блок усложнял голосовую плату,
отдельно - проще отладить и можно ставить к любому модулю. Схема перенесена
как была; разводки нет, расстановка черновая (пользователь расставит сам).

Выход: J3 JST PH 4 пина (2x 5V, 2x GND - по паре контактов на ток до ~1.5 А),
ответная часть - J3 "5V IN" на Voice-Unit (там диодное ИЛИ с USB).

TODO перед заказом (найдено при выносе):
  - L1 NR4030 22 мкГн насыщается ~1 А, а на 5 В/1.4 А из 3.0-4.2 В по входу
    буста течёт до ~2.8 А: нужна катушка с Isat >= 3.5 А и, вероятно, меньше
    индуктивность (MT3608 допускает 4.7-22 мкГн).
  - TP4057 заряжает максимум 500 мА - для 18650 медленно; смотреть 1-2 А зарядник.
  - Нет power-path: при заряде буст тянет из той же банки - проверить поведение.
  - Суперкап 1F (плавное выключение) - нужен ли на этой плате, решить.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "boards/Battery-Unit"
NAME = "Battery-Unit"
X0, X1, Y0, Y1 = 100.0, 145.0, 100.0, 128.0
BW, BH = X1 - X0, Y1 - Y0
CXB, CYB = (X0 + X1) / 2, (Y0 + Y1) / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
SOT23_6 = ("Package_TO_SOT_SMD", "SOT-23-6")
USBC = ("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12")
JST = "Connector_JST"

b = Builder(layers=2)

# ------------------------------------------------------------ размещение (черновая)
b.place("J1", USBC[0], USBC[1], 103.6, 108.0, 270, value="USB-C")       # только заряд
b.place("R1", R0402[0], R0402[1], 109.5, 105.0, 90, value="5.1k")      # CC1
b.place("R2", R0402[0], R0402[1], 109.5, 111.0, 90, value="5.1k")      # CC2
b.place("C2", C0805[0], C0805[1], 112.0, 103.0, 0, value="10uF")       # VBUS
b.place("U1", SOT23_6[0], SOT23_6[1], 114.0, 108.0, 0, value="TP4057")
b.place("R3", R0402[0], R0402[1], 114.0, 112.0, 0, value="2k")         # ток заряда 500 мА
b.place("D1", "LED_SMD", "LED_0805_2012Metric", 110.0, 116.0, 0, value="LED")
b.place("R4", R0402[0], R0402[1], 113.5, 116.0, 0, value="1k")
b.place("J2", JST, "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", 106.0, 123.0, 0, value="BAT")
b.place("C1", C0805[0], C0805[1], 118.0, 104.0, 90, value="22uF")      # BAT
b.place("L1", "Inductor_SMD", "L_Taiyo-Yuden_NR-40xx", 122.0, 108.0, 0, value="22uH")
b.place("U2", SOT23_6[0], SOT23_6[1], 128.0, 108.0, 0, value="MT3608")
b.place("R5", R0402[0], R0402[1], 131.0, 112.0, 180, value="22k")      # FB делитель 5 В
b.place("R6", R0402[0], R0402[1], 128.0, 112.0, 180, value="3k")
b.place("D2", "Diode_SMD", "D_SMA", 134.5, 106.0, 180, value="SS34")   # выпрямитель буста
b.place("C3", C0805[0], C0805[1], 139.5, 106.0, 90, value="22uF")      # 5V выход
b.place("R7", R0402[0], R0402[1], 134.0, 115.0, -90, value="2R2")      # заряд суперкапа
b.place("D3", "Diode_SMD", "D_SMA", 139.0, 116.0, -90, value="SS34")   # разряд суперкапа
b.place("SC1", "Capacitor_THT", "CP_Radial_D10.0mm_P5.00mm", 122.0, 120.0, 0, value="1F 5.5V")
b.place("J3", JST, "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical", 135.0, 124.0, 0, value="5V OUT")

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "Battery-Unit: 18650 charger TP4057 + MT3608 5V boost, JST 4p out")
d.prepare()
USBC_LIBID = "Connector:USB_C_Receptacle_USB2.0_16P"
SHIELD = [p.number for p in kigen.get_symbol(USBC_LIBID).pins if p.name == "SHIELD"][0]
d.add(kigen.Part("J1", USBC_LIBID, "USB-C", "%s:%s" % USBC,
                 {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
                  "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
                  "A5": "CC1", "B5": "CC2", SHIELD: "GND"}, at=(60, 60)))
d.add(kigen.Part("R1", "Device:R", "5.1k", "%s:%s" % R0402, {"1": "CC1", "2": "GND"}, at=(120, 60)))
d.add(kigen.Part("R2", "Device:R", "5.1k", "%s:%s" % R0402, {"1": "CC2", "2": "GND"}, at=(120, 85)))
d.add(kigen.Part("C2", "Device:C", "10uF", "%s:%s" % C0805, {"1": "VBUS", "2": "GND"}, at=(150, 60)))
# TP4057: 1 CHRG, 2 GND, 3 BAT, 4 VCC, 6 PROG
d.add(kigen.Part("U1", "Battery_Management:TP4057", "TP4057", "%s:%s" % SOT23_6,
                 {"1": "CHRG", "2": "GND", "3": "BAT+", "4": "VBUS", "6": "PROG"}, at=(200, 60)))
d.add(kigen.Part("R3", "Device:R", "2k", "%s:%s" % R0402, {"1": "PROG", "2": "GND"}, at=(250, 60)))
d.add(kigen.Part("D1", "Device:LED", "LED", "LED_SMD:LED_0805_2012Metric",
                 {"1": "CHRG", "2": "CHG_A"}, at=(250, 90)))
d.add(kigen.Part("R4", "Device:R", "1k", "%s:%s" % R0402, {"1": "VBUS", "2": "CHG_A"}, at=(280, 90)))
d.add(kigen.Part("J2", "Connector_Generic:Conn_01x02", "BAT",
                 "%s:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical" % JST,
                 {"1": "BAT+", "2": "GND"}, at=(60, 140)))
d.add(kigen.Part("C1", "Device:C", "22uF", "%s:%s" % C0805, {"1": "BAT+", "2": "GND"}, at=(120, 140)))
# MT3608 (символа нет - заглушка TP4057 с теми же номерами):
# фактически 1 SW, 2 GND, 3 FB, 4 EN (на вход = всегда вкл), 5 VIN
d.add(kigen.Part("U2", "Battery_Management:TP4057", "MT3608", "%s:%s" % SOT23_6,
                 {"1": "SW", "2": "GND", "3": "FB", "4": "BAT+", "5": "BAT+"}, at=(200, 140)))
d.add(kigen.Part("L1", "Device:L", "22uH", "Inductor_SMD:L_Taiyo-Yuden_NR-40xx",
                 {"1": "BAT+", "2": "SW"}, at=(150, 140)))
d.add(kigen.Part("D2", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA",
                 {"1": "+5V", "2": "SW"}, at=(250, 140)))
d.add(kigen.Part("R5", "Device:R", "22k", "%s:%s" % R0402, {"1": "+5V", "2": "FB"}, at=(280, 140)))
d.add(kigen.Part("R6", "Device:R", "3k", "%s:%s" % R0402, {"1": "FB", "2": "GND"}, at=(280, 170)))
d.add(kigen.Part("C3", "Device:C", "22uF", "%s:%s" % C0805, {"1": "+5V", "2": "GND"}, at=(310, 140)))
d.add(kigen.Part("R7", "Device:R", "2R2", "%s:%s" % R0402, {"1": "+5V", "2": "SCAP"}, at=(340, 140)))
d.add(kigen.Part("D3", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA",
                 {"1": "+5V", "2": "SCAP"}, at=(340, 170)))
d.add(kigen.Part("SC1", "Device:C_Polarized", "1F 5.5V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
                 {"1": "SCAP", "2": "GND"}, at=(370, 140)))
d.add(kigen.Part("J3", "Connector_Generic:Conn_01x04", "5V OUT",
                 "%s:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical" % JST,
                 {"1": "+5V", "2": "+5V", "3": "GND", "4": "GND"}, at=(400, 140)))
for i, n in enumerate(["GND", "VBUS", "BAT+", "+5V"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(440, 60 + 22 * i)))

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

# ------------------------------------------------------------ шелкография
b.text("5V 5V GND GND", 138.0, 120.6, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("BAT+ GND", 107.0, 119.6, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("Battery-Unit: 18650 -> 5V", CXB, 126.5, pcbnew.B_SilkS, 1.0, 0.2, 0, True)

# ------------------------------------------------------------ контур, полигоны
b.edge_rect(CXB, CYB, BW, BH, 2.0)
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
