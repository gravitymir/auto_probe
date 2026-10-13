#!/usr/bin/env python3
"""Генератор проекта KiCad: PSU-Unit - питание всего прибора от АКБ автомобиля.

Вход: клеммы на АКБ (крокодилы), 6...16 В рабочих; выдерживает сброс нагрузки,
переполюсовку и прикуривание от 24 В. Выход 5 В на три разъёма:
  J2, J3  JST PH 4p "5V OUT": 5V_BUS, 5V_BUS, GND, GND - Voice-Unit, мозги (H723).
  J4      JST PH 6p "BAT MOD": 5V_CHG, 5V_CHG, 5V_BUS, 5V_BUS, GND, GND - будущий
          батарейный модуль: берёт 5V_CHG на заряд и, когда крокодил отпал, сам
          держит 5V_BUS через свой диод, чтобы прибор не перезагружался.

Цепочка: J1 -> F1 5 А -> D1 TVS SMCJ24CA (двунаправленный: на переполюсовке не
открывается и не жжёт предохранитель) -> Q1 P-FET DMP6023LE (защита от переполюсовки,
затвор ограничен стабилитроном D2 12 В) -> C1 100 мкФ 63 В + C2/C3 2.2 мкФ 100 В ->
U1 TPS54360B-Q1 (60 В, 3.5 А, AEC-Q100) -> 5V_CHG 5.28 В -> D4 B560C (диодное ИЛИ) ->
5V_BUS ~4.85 В при 2 А.

Номиналы (даташит TI SLVSDV1, раздел 8.2, пересчёт примера 5 В/600 кГц):
  fsw ~404 кГц: R4 240k (RT = 101756 / f^1.008) - ниже AM-диапазона; на 60 В
     время включения 0.24 мкс > минимальных 0.135 мкс.
  Vout = 0.8 * (1 + R5/R6) = 0.8 * (1 + 56k/10k) = 5.28 В.
  UVLO: R2 470k / R3 82k - старт 7.5 В, стоп 5.9 В (держит прокрутку стартером).
     EN не выше 8.4 В: при 39 В (ограничение TVS) на EN ~5.8 В.
  L1 10 мкГн (Isat 15 А): размах тока 0.45 А при 8 В ... 1.2 А при 60 В.
  Выход C5..C8 4x22 мкФ 25 В 1206 (~50 мкФ с учётом смещения):
     fp(mod) = 3.5 А / (2pi * 5.3 В * 50 мкФ) = 2.1 кГц, fco ~20 кГц.
  Компенсация: R7 10k, C9 8.2 нФ (ноль на fp(mod)), C10 82 пФ (полюс ~fsw/2).
  D3 B560C - обратный диод: 60 В, 5 А, до ~2.5 Вт на 60 В - нужна медь.

Расстановка - пользователя (2026-10-12); C5..C8 развёрнуты плюсом к катушке.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "boards/PSU-Unit"
NAME = "PSU-Unit"
X0, X1, Y0, Y1 = 100.0, 158.0, 100.0, 144.0
BW, BH = X1 - X0, Y1 - Y0
CXB, CYB = (X0 + X1) / 2, (Y0 + Y1) / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
GEN = os.path.dirname(os.path.abspath(__file__))

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C1206 = ("Capacitor_SMD", "C_1206_3216Metric")
C1210 = ("Capacitor_SMD", "C_1210_3225Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
SMC = ("Diode_SMD", "D_SMC")
SMB = ("Diode_SMD", "D_SMB")
SOD123 = ("Diode_SMD", "D_SOD-123")
SOT223 = ("Package_TO_SOT_SMD", "SOT-223-3_TabPin2")
SO8PP = ("Package_SO", "TI_SO-PowerPAD-8_ThermalVias")
CPEL = ("Capacitor_SMD", "CP_Elec_10x10")
TERM = ("TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal")
JST = "Connector_JST"
JST4 = "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical"
JST6 = "JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical"
CUST = "footprints"          # gen/footprints.pretty - свои посадочные места
L_SPM = "L_TDK_SPM10065VT"
F_2410 = "Fuse_Littelfuse_451_2410"

b = Builder(layers=2)


def place_custom(ref, name, x, y, rot=0.0, value=""):
    """Футпринт из gen/footprints.pretty (у KiCad такого нет)."""
    keep = pcbhelp.FPDIR
    pcbhelp.FPDIR = GEN
    try:
        return b.place(ref, CUST, name, x, y, rot, value=value)
    finally:
        pcbhelp.FPDIR = keep


# ------------------------------------------------------------ размещение (пользователя, 2026-10-12)
# вход и защита - левая часть
b.place("J1", TERM[0], TERM[1], 105.66, 120.0, -90, value="12V IN")
place_custom("F1", F_2410, 113.67, 103.5, 0, value="5A")
b.place("D1", SMC[0], SMC[1], 116.0, 115.0, 90, value="SMCJ24CA")
b.place("Q1", SOT223[0], SOT223[1], 123.0, 106.15, 90, value="DMP6023LE")
b.place("D2", SOD123[0], SOD123[1], 123.15, 112.5, 180, value="BZT52C12")
b.place("R1", R0402[0], R0402[1], 121.99, 116.0, 0, value="100k")
b.place("C1", CPEL[0], CPEL[1], 121.5, 127.5, 180, value="100uF 63V")
b.place("C2", C1210[0], C1210[1], 128.53, 116.0, 180, value="2.2uF 100V")
b.place("C3", C1210[0], C1210[1], 129.5, 111.47, 90, value="2.2uF 100V")
b.place("R2", R0402[0], R0402[1], 130.49, 119.5, 0, value="470k")
b.place("R3", R0402[0], R0402[1], 133.49, 119.5, 0, value="82k")
# преобразователь - середина
b.place("U1", SO8PP[0], SO8PP[1], 135.8, 115.41, 0, value="TPS54360B-Q1")
# футпринт KiCad ссылается на несуществующую модель HTSOP-8-1EP_3.9x4.9mm_Pitch1.27mm
b.set_model("U1", "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/TI_SO-PowerPAD-8.step")
b.place("C4", C0402[0], C0402[1], 137.02, 110.5, 0, value="100nF")
b.place("R4", R0402[0], R0402[1], 132.99, 111.5, 0, value="240k")
b.place("R5", R0402[0], R0402[1], 149.5, 125.0, -90, value="56k")
b.place("R6", R0402[0], R0402[1], 156.0, 124.99, 90, value="10k")
b.place("R7", R0402[0], R0402[1], 136.5, 122.99, -90, value="10k")
b.place("C9", C0402[0], C0402[1], 134.48, 123.0, 180, value="8.2nF")
b.place("C10", C0402[0], C0402[1], 137.02, 119.5, 180, value="82pF")
b.place("D3", SMC[0], SMC[1], 132.9, 105.0, 180, value="B560C")
place_custom("L1", L_SPM, 145.0, 106.5, 0, value="10uH")
# выход - правая часть. C5..C8 развёрнуты плюсом (пад 1) к катушке: шина 5V_CHG
# идёт прямо от L1, а земли конденсаторов - нижним рядом
for _i, _r in enumerate(("C5", "C6", "C7", "C8")):
    b.place(_r, C1206[0], C1206[1], 142.0 + 3.0 * _i, 115.97, 270, value="22uF")
b.place("D4", SMC[0], SMC[1], 143.0, 129.0, 0, value="B560C")
b.place("C11", C1206[0], C1206[1], 154.97, 114.5, 180, value="22uF")
b.place("D5", SMB[0], SMB[1], 153.15, 121.5, 180, value="SMBJ5.0A")
b.place("D6", "LED_SMD", "LED_0805_2012Metric", 154.44, 109.0, 0, value="LED")
b.place("R8", R0402[0], R0402[1], 155.51, 111.0, 180, value="1k")
# разъёмы - нижний край
b.place("J2", JST, JST4, 110.0, 139.5, 0, value="5V OUT")
b.place("J3", JST, JST4, 125.0, 139.5, 0, value="5V OUT")
b.place("J4", JST, JST6, 139.0, 139.5, 0, value="BAT MOD")
for _r, _x, _y in (("H1", 103.0, 103.0), ("H2", 155.0, 103.0), ("H3", 103.0, 141.0), ("H4", 155.0, 141.0)):
    b.place(_r, "MountingHole", "MountingHole_2.7mm_M2.5", _x, _y, 0, value="M2.5")
    b.fps[_r].Reference().SetVisible(False)
# подписи позиционных обозначений - как расставил пользователь: (x, y, поворот)
REFPOS = {
    "C1": (121.5, 133.7, 0), "C2": (128.53, 118.5, 0), "C3": (127.2, 111.47, 90),
    "C4": (137.02, 109.34, 0), "C5": (140.15, 115.97, 90), "C6": (142.0, 119.5, 90),
    "C7": (145.0, 120.0, 90), "C8": (148.0, 119.5, 90), "C9": (133.5, 124.5, 0),
    "C10": (137.02, 120.66, 0), "C11": (154.97, 116.35, 0), "D1": (111.9, 115.0, 90),
    "D2": (123.15, 114.5, 0), "D3": (132.9, 109.1, 0), "D4": (143.0, 124.9, 0),
    "D5": (153.15, 124.5, 0), "D6": (154.44, 107.35, 0), "F1": (113.67, 106.5, 0),
    "J1": (111.97, 122.5, 90), "J2": (113.0, 136.6, 0), "J3": (128.0, 136.6, 0),
    "J4": (144.0, 136.6, 0), "L1": (145.0, 113.0, 0), "Q1": (118.5, 106.15, 90),
    "R1": (122.0, 118.0, 0), "R2": (130.5, 121.5, 0), "R3": (133.5, 121.5, 0),
    "R4": (132.99, 110.33, 0), "R5": (150.67, 125.0, 90), "R6": (154.83, 124.99, 90),
    "R7": (138.0, 123.5, 90), "R8": (155.51, 112.17, 0), "U1": (135.8, 111.91, 0),
}
for _r, (_x, _y, _a) in REFPOS.items():
    _t = b.fps[_r].Reference()
    _t.SetPosition(V(_x, _y))
    _t.SetTextAngleDegrees(_a)

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "PSU-Unit: car battery 6-16V (load dump, reverse) -> 5V 3.5A, TPS54360B-Q1")
d.prepare()
P = lambda *a, **k: d.add(kigen.Part(*a, **k))
fpn = lambda t: "%s:%s" % t
# вход и защита
P("J1", "Connector:Screw_Terminal_01x02", "12V IN", fpn(TERM), {"1": "VIN_RAW", "2": "GND"}, at=(40, 60))
P("F1", "Device:Fuse", "5A", "%s:%s" % (CUST, F_2410), {"1": "VIN_RAW", "2": "VIN_F"}, at=(70, 60))
P("D1", "Device:D_TVS", "SMCJ24CA", fpn(SMC), {"1": "GND", "2": "VIN_F"}, at=(95, 80))
# P-FET в плюсовом проводе: сток - к входу (диод тела проводит вход -> нагрузка),
# исток - к нагрузке, затвор на массу через R1; на переполюсовке Vgs = 0 - закрыт.
P("Q1", "Transistor_FET:ZXMP4A16G", "DMP6023LE", fpn(SOT223), {"1": "GATE", "2": "VIN_F", "3": "VIN"}, at=(125, 60))
P("D2", "Device:D_Zener", "BZT52C12", fpn(SOD123), {"1": "VIN", "2": "GATE"}, at=(150, 85))
P("R1", "Device:R", "100k", fpn(R0402), {"1": "GATE", "2": "GND"}, at=(125, 100))
P("C1", "Device:C_Polarized", "100uF 63V", fpn(CPEL), {"1": "VIN", "2": "GND"}, at=(175, 80))
P("C2", "Device:C", "2.2uF 100V", fpn(C1210), {"1": "VIN", "2": "GND"}, at=(195, 80))
P("C3", "Device:C", "2.2uF 100V", fpn(C1210), {"1": "VIN", "2": "GND"}, at=(215, 80))
P("R2", "Device:R", "470k", fpn(R0402), {"1": "VIN", "2": "EN"}, at=(235, 80))
P("R3", "Device:R", "82k", fpn(R0402), {"1": "EN", "2": "GND"}, at=(235, 105))
# преобразователь
P("U1", "Regulator_Switching:TPS54360DDA", "TPS54360B-Q1", fpn(SO8PP),
  {"1": "BOOT", "2": "VIN", "3": "EN", "4": "RT", "5": "FB", "6": "COMP", "7": "GND",
   "8": "SW", "9": "GND"}, at=(280, 80))
P("C4", "Device:C", "100nF", fpn(C0402), {"1": "BOOT", "2": "SW"}, at=(315, 60))
P("R4", "Device:R", "240k", fpn(R0402), {"1": "RT", "2": "GND"}, at=(260, 120))
P("D3", "Device:D_Schottky", "B560C", fpn(SMC), {"1": "SW", "2": "GND"}, at=(320, 100))
P("L1", "Device:L", "10uH", "%s:%s" % (CUST, L_SPM), {"1": "SW", "2": "5V_CHG"}, at=(345, 80))
P("R5", "Device:R", "56k", fpn(R0402), {"1": "5V_CHG", "2": "FB"}, at=(370, 105))
P("R6", "Device:R", "10k", fpn(R0402), {"1": "FB", "2": "GND"}, at=(370, 130))
P("R7", "Device:R", "10k", fpn(R0402), {"1": "COMP", "2": "COMP_RC"}, at=(290, 125))
P("C9", "Device:C", "8.2nF", fpn(C0402), {"1": "COMP_RC", "2": "GND"}, at=(290, 150))
P("C10", "Device:C", "82pF", fpn(C0402), {"1": "COMP", "2": "GND"}, at=(310, 135))
for _i, _r in enumerate(("C5", "C6", "C7", "C8")):
    P(_r, "Device:C", "22uF", fpn(C1206), {"1": "5V_CHG", "2": "GND"}, at=(395 + 18 * _i, 100))
# диодное ИЛИ на шину: батарейный модуль сможет держать 5V_BUS, не питая 5V_CHG
P("D4", "Device:D_Schottky", "B560C", fpn(SMC), {"1": "5V_BUS", "2": "5V_CHG"}, at=(400, 60))
P("C11", "Device:C", "22uF", fpn(C1206), {"1": "5V_BUS", "2": "GND"}, at=(470, 80))
P("D5", "Device:D_TVS", "SMBJ5.0A", fpn(SMB), {"1": "5V_BUS", "2": "GND"}, at=(490, 80))
P("R8", "Device:R", "1k", fpn(R0402), {"1": "5V_BUS", "2": "LED_A"}, at=(510, 80))
P("D6", "Device:LED", "LED", "LED_SMD:LED_0805_2012Metric", {"1": "GND", "2": "LED_A"}, at=(510, 105))
# выходы
P("J2", "Connector_Generic:Conn_01x04", "5V OUT", "%s:%s" % (JST, JST4),
  {"1": "5V_BUS", "2": "5V_BUS", "3": "GND", "4": "GND"}, at=(550, 60))
P("J3", "Connector_Generic:Conn_01x04", "5V OUT", "%s:%s" % (JST, JST4),
  {"1": "5V_BUS", "2": "5V_BUS", "3": "GND", "4": "GND"}, at=(550, 95))
P("J4", "Connector_Generic:Conn_01x06", "BAT MOD", "%s:%s" % (JST, JST6),
  {"1": "5V_CHG", "2": "5V_CHG", "3": "5V_BUS", "4": "5V_BUS", "5": "GND", "6": "GND"}, at=(550, 135))
for _i, _h in enumerate(["H1", "H2", "H3", "H4"]):
    P(_h, "Mechanical:MountingHole", "M2.5", "MountingHole:MountingHole_2.7mm_M2.5", {}, at=(40 + 20 * _i, 160))
for i, n in enumerate(["GND", "VIN_RAW", "VIN", "5V_CHG", "5V_BUS"]):
    P("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(40 + 22 * i, 185))

os.makedirs(OUT, exist_ok=True)
for _pt in d.parts:
    if ":" in _pt.footprint:
        _pt.footprint = "auto_probe:" + _pt.footprint.split(":", 1)[1]
d.write_sch(os.path.join(OUT, NAME + ".kicad_sch"))
for p in d.parts:
    if p.ref.startswith("#"):
        continue
    for pn, net in p.nets.items():
        b.setnet(p.ref, pn, net)
# теплоотвод U1 и его переходные - сплошь в землю: через него уходит тепло корпуса
for _p in b.fps["U1"].Pads():
    if _p.GetNumber() == "9":
        b.pad_zone_connection(_p, pcbnew.ZONE_CONNECTION_FULL)

# ------------------------------------------------------------ разводка
WP, WV, WO, W = 2.0, 1.2, 1.5, 0.25
VP = dict(dia=0.8, drill=0.4)          # силовые переходные: ~2 А каждая
# вход: клемма -> предохранитель -> сток P-FET, TVS сразу за предохранителем
b.track("VIN_RAW", [(105.66, 120.0), (108.2, 117.46), (108.2, 106.6), (111.34, 103.5)], FCU, WP)
b.track("VIN_F", [(116.0, 103.5), (123.0, 103.5)], FCU, WP)                 # F1.2 -> теплоотвод Q1 (сток)
b.track("VIN_F", [(123.0, 103.5), (123.0, 109.3)], FCU, 1.0)                 # теплоотвод -> вывод 2 (тоже сток)
b.track("VIN_F", [(116.0, 103.5), (116.0, 111.6)], FCU, WO)                  # -> D1 (TVS)
b.track("GATE", [(120.7, 109.3), (120.7, 110.8), (121.5, 111.6), (121.5, 112.5),
                 (121.48, 116.0)], FCU, 0.4)
# VIN после P-FET: исток -> стабилитрон, C3, C2, U1.VIN, делитель EN, электролит
b.track("VIN", [(125.3, 109.3), (125.3, 111.2), (127.0, 112.95), (129.5, 112.95)], FCU, WV)
b.track("VIN", [(124.8, 112.5), (125.3, 111.6)], FCU, 0.5)
b.track("VIN", [(130.0, 112.95), (130.0, 116.0)], FCU, 1.0)
b.track("VIN", [(130.0, 114.0), (131.2, 114.77), (132.6, 114.77)], FCU, 0.6)
b.track("VIN", [(130.0, 116.0), (129.98, 119.5)], FCU, 0.4)
b.track("VIN", [(121.5 + 4.0, 127.5), (125.5, 121.2), (128.4, 118.3), (130.0, 118.3)], FCU, 1.0)
# EN: U1.3 -> середина делителя R2/R3
b.track("EN", [(132.6, 116.04), (131.5, 116.04), (131.5, 119.5), (130.49 + 0.51, 119.5)], FCU, W)
b.track("EN", [(131.5, 119.5), (132.98, 119.5)], FCU, W)
# RT: R4 над U1, вывод 4 внизу слева - низом под корпусом
b.track("RT", [(132.48, 111.5), (130.9, 111.2)], FCU, W)
b.via("RT", 130.9, 111.2)
b.track("RT", [(130.9, 111.2), (130.9, 116.6), (132.65, 118.35), (133.1, 118.35)], BCU, W)
b.via("RT", 133.1, 118.35)
b.track("RT", [(133.1, 118.35), (133.1, 117.31)], FCU, W)
# BOOT: C4 справа сверху, вывод 1 слева - низом над теплоотводом
b.track("BOOT", [(136.54, 110.5), (135.6, 111.9)], FCU, 0.3)
b.via("BOOT", 135.6, 111.9)
b.track("BOOT", [(135.6, 111.9), (131.7, 113.5)], BCU, 0.3)
b.via("BOOT", 131.7, 113.5)
b.track("BOOT", [(131.7, 113.5), (133.1, 113.5)], FCU, 0.3)
# SW: U1.8 / C4 / катод D3 / L1 - петля как можно короче
b.track("SW", [(136.3, 105.5), (140.5, 105.5)], FCU, 2.5)
b.track("SW", [(139.0, 113.5), (140.3, 112.2), (140.3, 106.5)], FCU, 1.0)
b.track("SW", [(137.5, 110.5), (138.6, 111.6), (140.3, 111.6)], FCU, 0.4)
# земля горячей петли: D3 (анод) <-> C3, U1.GND -> теплоотвод
b.track("GND", [(129.5, 106.6), (129.5, 109.5)], FCU, WP)
b.track("GND", [(138.5, 114.77), (137.2, 114.77)], FCU, 0.3)
# COMP: справа выход мимо FB невозможен - низом к C10, затем R7 -> C9
b.track("COMP", [(139.0, 116.04), (140.1, 116.0)], FCU, W)
b.via("COMP", 140.1, 116.0)
b.track("COMP", [(140.1, 116.0), (138.5, 119.5)], BCU, W)
b.via("COMP", 138.5, 119.5)
b.track("COMP", [(138.5, 119.5), (137.5, 119.5), (137.5, 121.6), (136.5, 122.48)], FCU, W)
b.track("COMP_RC", [(136.5, 123.5), (135.5, 123.5), (134.96, 123.0)], FCU, W)
# FB: U1.5 -> R5 (верх делителя у выходных конденсаторов) -> R6
b.track("FB", [(139.0, 117.31), (140.0, 117.31), (140.0, 124.2), (141.3, 125.5),
               (149.5, 125.51)], FCU, W)
b.track("FB", [(149.5, 125.51), (156.0, 125.5)], FCU, W)
# 5V_CHG: L1 -> шина по плюсовым падам C5..C8 -> R5 (сенс) / D4 / J4 (низом)
b.track("5V_CHG", [(149.5, 106.5), (149.5, 114.5)], FCU, 2.5)
b.track("5V_CHG", [(142.0, 114.5), (151.0, 114.5)], FCU, 1.0)
b.track("5V_CHG", [(149.5, 114.5), (149.5, 118.4), (149.2, 118.7), (149.2, 124.0),
                   (149.5, 124.49)], FCU, 0.3)
for _x, _y in ((143.5, 114.5), (146.5, 114.5), (149.5, 111.5)):
    b.via("5V_CHG", _x, _y, **VP)
b.track("5V_CHG", [(143.5, 114.5), (146.5, 114.5)], BCU, WO)
b.track("5V_CHG", [(149.5, 111.5), (146.5, 114.5)], BCU, WO)
b.track("5V_CHG", [(146.5, 114.5), (146.5, 126.5), (146.5, 131.5), (141.3, 136.5),
                   (141.0, 138.7), (141.0, 139.5)], BCU, WO)
b.track("5V_CHG", [(139.0, 139.5), (141.0, 139.5)], BCU, 1.0)              # J4.1-J4.2
for _x in (145.7, 147.2):
    b.via("5V_CHG", _x, 126.5, **VP)
    b.track("5V_CHG", [(_x, 126.5), (146.4, 128.0)], FCU, 1.0)              # -> D4.2
b.track("5V_CHG", [(145.7, 126.5), (147.2, 126.5)], BCU, WO)
# 5V_BUS: D4.1 -> J4.3/4, J3, J2 верхом; к TVS/C11/светодиоду - низом справа
b.track("5V_BUS", [(139.6, 129.0), (139.6, 133.0), (143.0, 136.4), (143.0, 139.5)], FCU, WO)
b.track("5V_BUS", [(143.0, 139.5), (145.0, 139.5)], FCU, 1.0)              # J4.3-J4.4
b.track("5V_BUS", [(139.6, 133.0), (136.3, 136.3), (110.0, 136.3)], FCU, WO)
for _x in (110.0, 112.0, 125.0, 127.0):
    b.track("5V_BUS", [(_x, 136.3), (_x, 139.5)], FCU, 1.0)
b.track("5V_BUS", [(145.0, 139.5), (145.0, 137.8), (147.0, 135.8), (153.5, 132.3),
                   (153.5, 123.6)], BCU, WO)
b.via("5V_BUS", 153.5, 123.6, **VP)
b.track("5V_BUS", [(153.5, 123.6), (155.0, 122.4)], FCU, 1.0)              # -> D5 (TVS)
b.track("5V_BUS", [(155.6, 120.35), (156.4, 119.2), (156.4, 115.0)], FCU, 1.0)  # -> C11
b.track("5V_BUS", [(156.4, 113.6), (156.1, 111.0)], FCU, 0.4)              # -> R8
b.track("LED_A", [(155.38, 109.7), (155.0, 110.7)], FCU, 0.3)
# переходные земли: сшивка слоёв у силовых падов
for _x, _y in ((129.0, 108.0), (130.0, 108.0), (125.6, 116.0), (143.5, 118.6), (145.0, 118.9),
               (152.6, 118.3), (151.0, 123.6), (113.4, 119.6), (117.5, 124.6), (121.0, 124.6),
               (127.2, 106.0), (127.2, 102.6), (135.0, 125.0), (138.6, 122.0)):
    b.via("GND", _x, _y, **VP)
# крупные пады земли - сплошным подключением к полигону (ток и тепло)
for _r in ("D1", "D3", "D5", "C1", "C2", "C3", "C5", "C6", "C7", "C8", "C11", "J1"):
    for _p in b.fps[_r].Pads():
        if _p.GetNetname() == "GND":
            b.pad_zone_connection(_p, pcbnew.ZONE_CONNECTION_FULL)

# ------------------------------------------------------------ шелкография
b.text("+", 104.0, 113.5, pcbnew.F_SilkS, 2.0, 0.5, 0)
b.text("-", 104.0, 130.5, pcbnew.F_SilkS, 2.0, 0.5, 0)
b.text("6-16V", 108.5, 130.5, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("5V 5V GND GND", 113.0, 135.0, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("5V 5V GND GND", 125.0, 135.0, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("CHG CHG BUS BUS GND GND", 143.5, 135.0, pcbnew.F_SilkS, 0.8, 0.15, 0)
b.text("PSU-Unit: 12V car -> 5V 3.5A", 129.0, 106.0, pcbnew.B_SilkS, 1.0, 0.2, 0, True)

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
