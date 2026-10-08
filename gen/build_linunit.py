#!/usr/bin/env python3
"""Генератор проекта KiCad: LIN-Unit - двухканальный зонд LIN / K-line / L-line.

2 x TLE7258D (Infineon, PG-TSON-8): LIN-трансивер без TXD-таймаута - умеет
и современный LIN, и легаси K-line с 5-бодовой инициализацией (ISO 9141 /
KWP2000). Логика 3.3 В (RxD - открытый сток), шина питается от борта 12 В.
На каждом канале мастер-подтяжка 510 Ом через паяный пятачок (запаяно =
мастер/тестер, чисто = слушающий зонд или LIN-слейв). Группы выводов:
J2 LOGIC (3V3, GND, TX1, RX1, TX2, RX2), J3 BUS (12V, GND, LIN1, LIN2).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "boards/LIN-Unit"
NAME = "LIN-Unit"
X0, X1, Y0, Y1 = 112.2, 134.2, 93.3, 116.7
BW, BH = X1 - X0, Y1 - Y0
CXB, CYB = (X0 + X1) / 2, (Y0 + Y1) / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP = 0.25, 0.4

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
R0805 = ("Resistor_SMD", "R_0805_2012Metric")
HDRLIB = "Connector_PinHeader_2.54mm"
SON = ("Package_SON", "VSON-8-1EP_3x3mm_P0.65mm_EP1.6x2.4mm")

b = Builder(layers=2)

# ------------------------------------------------------------ размещение
# Расстановка ручная (KiCad, 2026-10-08, вторая итерация): U1 на западе,
# U2 на востоке у своих пятачков, D2 (TVS 12В) в центре, TVS линий у шины.
b.place("U1", SON[0], SON[1], 115.90, 100.0, 90, value="TLE7258D")
b.place("U2", SON[0], SON[1], 128.90, 99.5, 90, value="TLE7258D")
b.place("J3", HDRLIB, "PinHeader_1x04_P2.54mm_Vertical", 116.38, 96.0, 90, value="BUS")
b.place("J2", HDRLIB, "PinHeader_1x06_P2.54mm_Vertical", 117.30, 114.0, 90, value="LOGIC")
# защита входа 12 В: диод переполюсовки + TVS (двунаправленный)
b.place("D1", "Diode_SMD", "D_SOD-123", 116.85, 110.5, 0, value="1N4148W")
b.place("D2", "Diode_SMD", "D_SMA", 122.00, 103.5, 180, value="SMAJ24CA")
# мастер-подтяжки с пятачками (канал 1 / канал 2)
b.place("R1", R0805[0], R0805[1], 123.09, 110.5, 0, value="510R")
b.place("JP1", "Jumper", "SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
        132.0, 105.28, 90, value="PU1")
b.place("R2", R0805[0], R0805[1], 127.59, 107.0, 0, value="510R")
b.place("JP2", "Jumper", "SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
        132.0, 95.72, 90, value="PU2")
# TVS на линии - вплотную к штырям LIN1/LIN2
b.place("D3", "Diode_SMD", "D_SOD-323", 120.50, 99.45, 90, value="PESD1LIN")
b.place("D4", "Diode_SMD", "D_SOD-323", 124.00, 99.5, 90, value="PESD1LIN")
# развязка и подтяжки RxD
b.place("C1", C0402[0], C0402[1], 128.52, 96.5, 0, value="100nF")
b.place("C2", C0402[0], C0402[1], 129.00, 103.48, 90, value="100nF")
b.place("C3", C0603[0], C0603[1], 129.22, 110.5, 0, value="1uF")
b.place("R3", R0402[0], R0402[1], 115.50, 105.0, 90, value="10k")
b.place("R4", R0402[0], R0402[1], 119.49, 108.0, 0, value="10k")

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "LIN-Unit: dual TLE7258D probe - LIN / K-line / L-line, 3.3V logic")
d.prepare()
UPIN = lambda tx, rx, lin: {"1": rx, "2": "+3V3", "4": tx, "5": "GND",
                            "6": lin, "7": "VS", "9": "GND"}
d.add(kigen.Part("U1", "Interface_CAN_LIN:TJA1021xTK", "TLE7258D",
                 "%s:%s" % SON, UPIN("TX1", "RX1", "LIN1"), at=(120, 80)))
d.add(kigen.Part("U2", "Interface_CAN_LIN:TJA1021xTK", "TLE7258D",
                 "%s:%s" % SON, UPIN("TX2", "RX2", "LIN2"), at=(120, 160)))
d.add(kigen.Part("J2", "Connector_Generic:Conn_01x06", "LOGIC",
                 "%s:PinHeader_1x06_P2.54mm_Vertical" % HDRLIB,
                 {"1": "+3V3", "2": "GND", "3": "TX1", "4": "RX1",
                  "5": "TX2", "6": "RX2"}, at=(60, 80)))
d.add(kigen.Part("J3", "Connector_Generic:Conn_01x04", "BUS",
                 "%s:PinHeader_1x04_P2.54mm_Vertical" % HDRLIB,
                 {"1": "+12V", "2": "GND", "3": "LIN1", "4": "LIN2"}, at=(230, 60)))
d.add(kigen.Part("D1", "Device:D", "1N4148W", "Diode_SMD:D_SOD-123",
                 {"1": "VS", "2": "+12V"}, at=(230, 100)))
d.add(kigen.Part("D2", "Device:D_TVS", "SMAJ24CA", "Diode_SMD:D_SMA",
                 {"1": "GND", "2": "+12V"}, at=(230, 130)))
d.add(kigen.Part("R1", "Device:R", "510R", "%s:%s" % R0805,
                 {"1": "VS", "2": "PU1"}, at=(300, 60)))
d.add(kigen.Part("JP1", "Jumper:SolderJumper_2_Open", "PU1",
                 "Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
                 {"1": "PU1", "2": "LIN1"}, at=(300, 90)))
d.add(kigen.Part("R2", "Device:R", "510R", "%s:%s" % R0805,
                 {"1": "VS", "2": "PU2"}, at=(300, 120)))
d.add(kigen.Part("JP2", "Jumper:SolderJumper_2_Open", "PU2",
                 "Jumper:SolderJumper-2_P1.3mm_Open_TrianglePad1.0x1.5mm",
                 {"1": "PU2", "2": "LIN2"}, at=(300, 150)))
d.add(kigen.Part("D3", "Device:D_TVS", "PESD1LIN", "Diode_SMD:D_SOD-323",
                 {"1": "GND", "2": "LIN1"}, at=(370, 60)))
d.add(kigen.Part("D4", "Device:D_TVS", "PESD1LIN", "Diode_SMD:D_SOD-323",
                 {"1": "GND", "2": "LIN2"}, at=(370, 90)))
d.add(kigen.Part("C1", "Device:C", "100nF", "%s:%s" % C0402,
                 {"1": "VS", "2": "GND"}, at=(370, 120)))
d.add(kigen.Part("C2", "Device:C", "100nF", "%s:%s" % C0402,
                 {"1": "VS", "2": "GND"}, at=(370, 150)))
d.add(kigen.Part("C3", "Device:C", "1uF", "%s:%s" % C0603,
                 {"1": "VS", "2": "GND"}, at=(400, 120)))
d.add(kigen.Part("R3", "Device:R", "10k", "%s:%s" % R0402,
                 {"1": "+3V3", "2": "RX1"}, at=(440, 60)))
d.add(kigen.Part("R4", "Device:R", "10k", "%s:%s" % R0402,
                 {"1": "+3V3", "2": "RX2"}, at=(440, 90)))
for i, n in enumerate(["GND", "+3V3", "+12V", "VS"]):
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
u1 = lambda n: b.padxy("U1", n)
u2 = lambda n: b.padxy("U2", n)
j2 = lambda n: b.padxy("J2", n)
j3 = lambda n: b.padxy("J3", n)

# --- LIN1: J3.3 -> D3 -> U1.6 (заход сверху, мимо GND-пада) + хвост на JP1.2
b.track("LIN1", [(121.46, 96.0), (120.5, 97.3), (120.5, 98.4)], FCU, W)          # J3.3 -> D3.2
b.track("LIN1", [(120.5, 98.4), (120.1, 97.75), (116.225, 97.75),
                 (116.225, 98.56)], FCU, W)                                      # D3.2 -> U1.6
b.track("LIN1", [(120.5, 98.4), (122.3, 99.3), (122.3, 105.6), (130.3, 105.6),
                 (131.3, 104.9), (132.0, 104.56)], FCU, W)                       # D3.2 -> JP1.2 югом, в щель между падами D2
# --- LIN2: J3.4 -> D4 -> U2.6 (заход сверху) + хвост на JP2.2
b.track("LIN2", [(124.0, 96.0), (124.0, 97.25)], FCU, W)                         # J3.4 вниз (через D4.2)
b.track("LIN2", [(124.0, 97.25), (124.0, 98.45)], FCU, W)                        #   ... в пад D4.2
# заход на U2.6 с востока (ответвление от хвоста JP2.2): коридор над чипом
# между C1 и верхним рядом падов занят питанием VS
b.track("LIN2", [(130.3, 95.0), (130.3, 97.15), (129.225, 97.15),
                 (129.225, 98.06)], FCU, W)                                      # хвост -> U2.6
b.track("LIN2", [(124.0, 96.0), (124.6, 95.0), (131.3, 95.0), (132.0, 95.0)], FCU, W)  # J3.4 -> JP2.2
# --- PU1: R1.2 -> JP1.1 понизу, вдоль ряда J2 (коридор y109.4 отдан VS->C3)
b.track("PU1", [(124.0, 110.5), (124.6, 111.6), (125.3, 112.6), (130.6, 112.6),
                (132.0, 111.2), (132.0, 106.3)], FCU, W)                         # R1.2 -> JP1.1
# --- PU2: R2.2 -> JP2.1; ныряет на B под хвост LIN1
b.track("PU2", [(128.5, 107.0), (130.2, 106.4), (130.8, 106.2)], FCU, W)
b.via("PU2", 130.8, 106.2)
b.track("PU2", [(130.8, 106.2), (130.8, 103.6)], BCU, W)
b.via("PU2", 130.8, 103.6)
b.track("PU2", [(130.8, 103.6), (130.8, 97.3), (131.55, 96.44), (132.0, 96.44)], FCU, W)

# --- +12V: J3.1 -> западный край -> понизу в D1.2, от D1.2 вверх в D2.2
b.track("+12V", [(116.38, 96.0), (113.6, 96.6), (113.6, 112.3),
                 (118.5, 112.3), (118.5, 110.5)], FCU, WP)                       # J3.1 -> D1.2
b.track("+12V", [(118.5, 110.5), (118.2, 109.9), (118.2, 105.3), (119.5, 105.3),
                 (120.0, 104.7), (120.0, 103.5)], FCU, W)                        # D1.2 -> D2.2 (TVS)
# --- VS: раздача от катода D1.1
# западная группа VS (D1.1 + U1.7) связана с восточной по северному краю:
# юг весь занят +12V и сигналами, а над падами J3 слой B пуст
b.track("VS", [(115.1, 97.6), (115.1, 97.3)], FCU, W)
b.via("VS", 115.1, 97.3)
b.track("VS", [(115.1, 97.3), (114.7, 95.3), (115.3, 94.6), (127.9, 94.6),
               (128.3, 95.0), (128.3, 96.5)], BCU, W)                            # северный мост на колонну
b.track("VS", [(122.18, 110.5), (122.85, 108.6), (126.68, 108.6),
               (126.68, 107.6), (126.68, 107.0)], FCU, W)                        # R1.1 -> R2.1
b.track("VS", [(115.2, 110.5), (114.3, 109.9), (114.3, 97.6),
               (115.575, 97.6), (115.575, 98.56)], FCU, W)                       # D1.1 -> U1.7 (западная колонна)
b.track("VS", [(126.68, 107.0), (126.68, 107.9), (128.0, 110.0),
               (128.44, 110.5)], FCU, W)                                         # R2.1 -> C3.1
b.track("VS", [(128.44, 110.5), (127.4, 111.5)], FCU, W)                         # C3.1 -> via
b.via("VS", 127.4, 111.5)
b.track("VS", [(127.4, 111.5), (129.0, 110.5), (129.0, 104.9)], BCU, W)          # B на север
b.via("VS", 129.0, 104.9)
b.track("VS", [(129.0, 104.9), (129.0, 104.26), (129.0, 103.96)], FCU, W)        # via C -> C2.1
b.track("VS", [(129.0, 104.9), (128.3, 104.5), (128.3, 96.5), (127.1, 96.5)], BCU, W)  # B дальше на север
b.via("VS", 127.1, 96.5)
b.track("VS", [(127.1, 96.5), (128.04, 96.5)], FCU, W)                           # заход в C1.1 с запада
b.track("VS", [(128.04, 96.5), (128.04, 97.1), (128.575, 97.5),
               (128.575, 98.06)], FCU, W)                                        # C1.1 -> U2.7

# --- сигналы к J2 (THT - заходим и по B, где F занят питанием)
b.track("TX1", [(116.875, 101.88), (117.15, 102.5), (117.15, 111.1)], FCU, W)    # U1.4 вниз, щель между падами D1
b.via("TX1", 117.15, 111.1)
b.track("TX1", [(117.15, 111.1), (122.38, 114.0)], BCU, W)                       # по B в пад J2.3
b.track("RX1", [(114.925, 101.88), (114.8, 102.5), (114.8, 107.1),
                (115.0, 107.5)], FCU, W)                                         # U1.1 вниз западом
b.track("RX1", [(114.8, 103.9), (115.5, 103.9), (115.5, 104.49)], FCU, W)        # ветка в R3.2
b.via("RX1", 115.0, 107.5)
b.track("RX1", [(115.0, 107.5), (114.45, 109.3), (114.45, 112.2), (114.3, 113.2),
                (114.3, 115.3), (124.92, 115.3), (124.92, 114.0)], BCU, W)       # по B под рядом J2 в пад J2.4
b.track("TX2", [(129.875, 101.38), (129.875, 103.9), (130.05, 104.3),
                (130.05, 104.7)], FCU, W)                                        # U2.4 вниз
b.via("TX2", 130.05, 104.7)
# GND: мостики для падов, отрезанных дорожками от полигона, и прошивка в EP
b.track("GND", [(116.875, 98.8), (116.875, 99.4)], FCU, W)                       # U1.5 -> EP U1
b.track("GND", [(129.875, 98.3), (129.875, 98.9)], FCU, W)                       # U2.5 -> EP U2
b.via("GND", 116.5, 100.0)                                                       # EP U1 -> B-полигон
b.via("GND", 129.3, 99.8)                                                        # EP U2 -> B-полигон
b.via("GND", 129.0, 103.0)                                                       # C2.2: via в паде (карман замурован)
b.via("GND", 120.9, 101.6)                                                       # карман D3.1
b.via("GND", 123.2, 101.5)                                                       # карман D4.1/D2.1
b.via("GND", 130.9, 109.6)                                                       # карман C3.2
b.track("TX2", [(130.05, 104.7), (130.0, 110.5), (129.3, 112.6),
                (127.46, 114.0)], BCU, W)                                        # по B в пад J2.5
# RX2: U2.1 -> запад по коридору между падами D3/D4 -> R4.2, хвост на юг в J2.6
b.track("RX2", [(127.925, 101.15), (127.25, 100.95), (127.25, 99.5),
                (123.05, 99.5)], FCU, W)                                         # U2.1 -> на запад, мимо брюшка U2
b.via("RX2", 123.05, 99.5)
b.track("RX2", [(123.05, 99.5), (121.5, 99.7)], BCU, W)                          # подныр под LIN1
b.via("RX2", 121.5, 99.7)
b.track("RX2", [(121.5, 99.7), (121.7, 100.1), (121.7, 107.3),
                (120.2, 108.0)], FCU, W)                                         # -> R4.2
b.track("RX2", [(120.0, 108.0), (120.0, 110.6), (121.11, 111.7), (121.11, 115.25),
                (129.9, 115.25), (130.0, 114.0)], FCU, W)                        # R4.2 -> J2.6 южным обходом
# --- +3V3: со штыря J2.1 по B на запад, раздача на R3/R4/EN обоих каналов
b.track("+3V3", [(117.3, 114.0), (116.15, 112.6), (116.15, 107.1),
                 (116.4, 106.4)], BCU, W)                                        # J2.1 (THT) -> на север по B
b.via("+3V3", 116.4, 106.4)
b.track("+3V3", [(116.4, 106.4), (115.9, 105.9), (115.6, 105.6)], FCU, W)        # -> R3.1
b.track("+3V3", [(115.5, 105.51), (115.9, 105.2), (116.2, 104.9), (116.2, 102.4),
                 (115.575, 102.1), (115.575, 101.88)], FCU, W)                   # R3.1 -> U1.2 (EN1)
b.track("+3V3", [(116.15, 107.1), (119.0, 106.9)], BCU, W)
b.via("+3V3", 119.0, 106.9)
b.track("+3V3", [(119.0, 106.9), (118.98, 107.5), (118.98, 108.0)], FCU, W)      # -> R4.1
b.track("+3V3", [(119.0, 106.9), (126.8, 105.3), (127.4, 104.9)], BCU, W)        # по B на восток
b.via("+3V3", 127.4, 104.9)
b.track("+3V3", [(127.4, 104.9), (128.3, 102.9), (128.3, 102.0),
                 (128.575, 101.5), (128.575, 101.3)], FCU, W)                    # -> U2.2 (EN2), в обход C2

# ------------------------------------------------- шелкография (обратная сторона)
# Ручная правка пользователя (KiCad, 2026-10-08) - перенесена в генератор 1:1.
BS = pcbnew.B_SilkS
for _x, _y, _sz, _th, _s in (
        # подписи пинов J3 (внутри платы, под падами)
        (116.27, 98.50, 0.6, 0.12, "12V"),
        (118.81, 98.50, 0.6, 0.12, "GND"),
        (121.35, 98.50, 0.6, 0.12, "LIN1"),
        (123.89, 98.50, 0.6, 0.12, "LIN2"),
        # подписи пинов J2 (внутри платы, над падами)
        (117.43, 111.85, 0.6, 0.12, "3V3"),
        (119.97, 111.85, 0.6, 0.12, "GND"),
        (122.51, 111.85, 0.6, 0.12, "TX1"),
        (125.05, 111.85, 0.6, 0.12, "RX1"),
        (127.59, 111.85, 0.6, 0.12, "TX2"),
        (130.13, 111.85, 0.6, 0.12, "RX2"),
        (123.75, 110.50, 0.8, 0.20, "UART1"),
        (128.65, 110.50, 0.8, 0.20, "UART2"),
        # легенда номиналов (на виде сзади - колонка слева)
        (130.00, 95.67, 0.6, 0.12, "R1, R2: 510R"),
        (130.50, 96.90, 0.6, 0.12, "R3, R4: 10k"),
        (130.23, 98.15, 0.6, 0.12, "C1, C2: 100n"),
        (130.50, 99.31, 0.6, 0.12, "D1: 1N4148"),
        (131.50, 100.50, 0.6, 0.12, "C3: 1uF"),
        (130.00, 101.68, 0.6, 0.12, "D2: SMAJ24CA"),
        (129.13, 102.89, 0.6, 0.12, "D3, D4: PESD1LIN"),
        (129.00, 104.18, 0.6, 0.12, "U1, U2: TLE7258D"),
        # имя и назначение
        (123.50, 106.50, 2.2, 0.45, "ASTechLab"),
        (123.00, 109.00, 1.0, 0.20, "LIN, K-Line, L-Line board")):
    b.text(_s, _x, _y, BS, _sz, _th, 0, True)

# полярность D1 на лицевой: полоска корпуса смотрит на минус. Знаки есть
# только у него: D2/D3/D4 - двунаправленные TVS, у них полярности нет.
b.text("-", 113.5, 110.5, pcbnew.F_SilkS, 0.6, 0.15)
b.text("+", 120.0, 110.5, pcbnew.F_SilkS, 0.6, 0.15)

# позиции рефов на лицевой - тоже ручные
for _r, _x, _y, _rot in (
        ("C1", 128.52, 95.34, 0), ("C2", 127.84, 103.48, 90),
        ("C3", 129.22, 109.07, 0), ("D1", 116.85, 108.50, 0),
        ("D2", 122.00, 106.00, 180), ("D3", 118.65, 99.45, 90),
        ("D4", 122.15, 99.50, 90), ("J2", 114.92, 114.00, 90),
        ("J3", 114.00, 96.00, 90), ("JP1", 130.20, 105.28, 90),
        ("JP2", 130.20, 95.72, 90), ("R1", 123.09, 108.85, 0),
        ("R2", 127.59, 105.35, 0), ("R3", 114.33, 105.00, 90),
        ("R4", 119.49, 106.83, 0), ("U1", 113.45, 100.00, 90),
        ("U2", 126.45, 99.50, 90)):
    _t = b.fps[_r].Reference()
    _t.SetPosition(V(_x, _y))
    _t.SetTextAngleDegrees(_rot)

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
