#!/usr/bin/env python3
"""Генератор проекта KiCad: STM32H723ZGT6 core board (LQFP144), 84x84 мм, 4 слоя."""
import os, sys, math, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/stm32boards/out/STM32H723ZG-CoreBoard"
NAME = "STM32H723ZG-CoreBoard"
CX, CY = 150.0, 100.0
BW = BH = 84.0
OFFX = 6.0                                 # кристалл левее центра платы
OFFY = 6.0                                 # кристалл выше нижнего края: кольца сверху и
BCX, BCY = CX + OFFX, CY - OFFY            # справа шире - там разъёмы, кнопки и брендинг
# Внутренний ряд гребёнки - ровно 11 x 2.54 от центра: противоположные гребёнки
# оказываются на шаге 22 x 2.54 и плата садится в макетку. Заодно это тот минимум,
# при котором веер из 36 выводов на сторону успевает разойтись с зазором 0.2 мм:
# крайние дорожки идут под 42 градуса, поперёк соседа остаётся 0.5*cos42 = 0.37 мм.
HDI, HDO = 27.94, 30.48                    # внутренний / внешний ряд гребёнки
APPR = 1.5                                 # где диагональ веера упирается в ряд гребёнки
X0, X1, Y0, Y1 = BCX - BW / 2, BCX + BW / 2, BCY - BH / 2, BCY + BH / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP, WD = 0.15, 0.35, 0.15               # сигнальная / силовая / USB D+D-

MCU_LIBID = "MCU_ST_STM32H7:STM32H723ZGTx"
MCU_FP = ("Package_QFP", "LQFP-144_20x20mm_P0.5mm")
SPECIAL = {105: "SWDIO", 109: "SWCLK", 103: "USB_DM", 104: "USB_DP",
           8: "LSE_IN", 9: "LSE_OUT", 23: "HSE_IN", 24: "HSE_OUT",
           46: "LED_A", 71: "VCAP1", 106: "VCAP2"}
NO_HEADER = {8, 9, 23, 24, 71, 106}
PWRNET = {"VDD": "+3V3", "VSS": "GND", "VBAT": "+3V3", "VDDA": "+3V3A",
          "VSSA": "GND", "VREF+": "+3V3A", "VDD33USB": "+3V3", "PDR_ON": "+3V3"}

sym = kigen.get_symbol(MCU_LIBID)
PINNAME = {int(p.number): re.split(r"[(/]", p.name)[0] for p in sym.pins}
RAWNAME = {int(p.number): p.name for p in sym.pins}


def mcu_net(n):
    raw = RAWNAME[n]
    if raw in PWRNET:
        return PWRNET[raw]
    return SPECIAL.get(n, PINNAME[n])


C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
HDRLIB = "Connector_PinHeader_2.54mm"

b = Builder(layers=4)
u1 = b.place("U1", MCU_FP[0], MCU_FP[1], CX, CY, 0, value="STM32H723ZGT6")
pads = {int(p.GetNumber()): (tomm(p.GetPosition().x) - CX, tomm(p.GetPosition().y) - CY) for p in u1.Pads()}
sides = {"L": [], "B": [], "R": [], "T": []}
for n, (x, y) in pads.items():
    sides["L" if x < -10 else "R" if x > 10 else "T" if y < -10 else "B"].append(n)
for k in ("L", "R"):
    sides[k].sort(key=lambda n: pads[n][1])
for k in ("T", "B"):
    sides[k].sort(key=lambda n: pads[n][0])
assert all(len(v) == 36 for v in sides.values()), {k: len(v) for k, v in sides.items()}

# Выводы для разъёма прошивки. SWO у H7 только на PB3, а UART берём USART3 (PC10/PC11):
# эта пара выходит на верхнюю гребёнку рядом со SWCLK, тогда как USART1 (PA9/PA10)
# лежит на правой гребёнке за коридором USB, куда дорожку уже не провести.
pin_of = lambda nm: next(n for n in pads if PINNAME[n] == nm)
UTX, URX, SWO = pin_of("PC10"), pin_of("PC11"), pin_of("PB3")

# ---------------------------------------------------------- гребёнки 2x18
HL = 17 * 2.54
b.place("J2", HDRLIB, "PinHeader_2x18_P2.54mm_Vertical", CX - HDO, CY - HL / 2, 0, value="PORT_L")
b.place("J4", HDRLIB, "PinHeader_2x18_P2.54mm_Vertical", CX + HDI, CY - HL / 2, 0, value="PORT_R")
b.place("J5", HDRLIB, "PinHeader_2x18_P2.54mm_Vertical", CX - HL / 2, CY - HDI, 90, value="PORT_T")
b.place("J3", HDRLIB, "PinHeader_2x18_P2.54mm_Vertical", CX - HL / 2, CY + HDO, 90, value="PORT_B")
HSIDE = {"L": "J2", "B": "J3", "R": "J4", "T": "J5"}
SD = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}

hdrmap, hdrof = {}, {}
for s_, ref in HSIDE.items():
    sx, sy = SD[s_]
    hp = [(int(p.GetNumber()), tomm(p.GetPosition().x), tomm(p.GetPosition().y)) for p in b.fps[ref].Pads()]
    tr = (lambda t: t[1]) if sx else (lambda t: t[2])      # поперёк платы
    al = (lambda t: t[2]) if sx else (lambda t: t[1])      # вдоль гребёнки
    vals = sorted({round(tr(t), 2) for t in hp})
    inner_v = vals[-1] if (sx < 0 or sy < 0) else vals[0]  # ближний к центру ряд
    inner = sorted([t for t in hp if abs(tr(t) - inner_v) < 0.1], key=al)
    outer = sorted([t for t in hp if abs(tr(t) - inner_v) >= 0.1], key=al)
    for i, mn in enumerate(sides[s_]):
        j, row = i // 2, i % 2
        hn, hx, hy = (inner if row == 0 else outer)[j]
        gap = al(inner[j]) + 1.27                          # проход между падами внутреннего ряда
        hdrmap[(ref, hn)] = mn
        hdrof[mn] = dict(ref=ref, pin=hn, x=hx, y=hy, side=s_, row=row, col=j,
                         inner=(inner[j][1], inner[j][2]), gap=gap)

# ---------------------------------------------------------------- периферия
UCY = (hdrof[103]["y"] + hdrof[104]["y"]) / 2 + 16.0
b.place("J1", "Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", X1 - 6.0, UCY, 90, value="USB-C")
# Разъём должен стоять на плате целиком, а не свисать за край. Двигаем его так,
# чтобы корпус кончался ровно на контуре: глубже нельзя - в край упрётся литьё
# вилки и она не сядет до конца.
_cb = b.fps["J1"].GetCourtyard(pcbnew.F_CrtYd).BBox()
b.fps["J1"].SetPosition(pcbnew.VECTOR2I(
    mm(tomm(b.fps["J1"].GetPosition().x) + (X1 - 0.05) - tomm(_cb.GetRight())), mm(UCY)))

# Верхнее кольцо, слева направо: светодиод, RST, BOOT, разъём прошивки - как на G474
TOPY = Y0 + 7.0
# Светодиод - в нижнем левом углу, у своей же гребёнки: вывод PB0 выходит на J3,
# и из верхнего ряда до него шла дорожка в 126 мм через всё левое кольцо.
# Пара стоит по диагонали в свободном углу между крепёжным отверстием, J2 и J3;
# анод D1 смотрит на северо-восток, в сторону своей гребёнки.
b.place("R5", R0402[0], R0402[1], X0 + 5.0, Y1 - 9.5, 135, value="1k")   # падом 1 к катоду
b.place("D1", "LED_SMD", "LED_0805_2012Metric", X0 + 8.0, Y1 - 6.5, 315, value="LED")
# RESET - в карман между верхом J2 и левым краем J5
b.place("SW1", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", X0 + 7.0, TOPY + 10.0, 0, value="RESET")
b.place("SW2", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", X0 + 10.5, TOPY, 0, value="BOOT0")
b.place("R4", R0402[0], R0402[1], X0 + 5.2, TOPY, 180, value="10k")        # вплотную к SW2:
# западнее дорожка BOOT0 пересекла бы спуск SWO на верхнюю гребёнку
JY = Y0 + 11.4                             # ряд разъёма прошивки: подписи ушли под
                                           # него, сверху остались только полосы SWO/NRST
# Разъём развёрнут: 5V у восточного края, ближе к USB. Положение задано так, чтобы
# контакт SWO встал ровно над своим падом на J5 - тогда отвод к PB3 идёт по прямой.
JX = hdrof[SWO]["x"] + 5 * 2.54             # контакт 1 - восточный край разъёма
b.place("J6", HDRLIB, "PinHeader_1x10_P2.54mm_Vertical", JX, JY, 270, value="DEBUG")
# STDC14 (2x7, 1.27 мм) - штатный разъём ST-LINK V3. Стоит под J6 сигнальным рядом
# к нему: после переворота J6 порядок сигналов у обоих совпал, и веер идёт без
# пересечений. Распиновка по UM ST: 3 T_VCC, 4 SWDIO, 5 GND, 6 SWCLK, 7 GND,
# 8 SWO, 11 GNDDETECT, 12 NRST; 1, 2, 9, 10 служебные, 13/14 - VCP UART.
# Разъём стоит вертикально, сигнальный (чётный) ряд обращён к J6, ряд GND/VCC -
# наружу. Контакты сигналов идут в обратном порядке относительно своих целей на
# J6, поэтому веер расходится по слоям, а не по глубине полос.
J7X, J7Y = JX + 4.7, JY - 1.2               # восточнее J6; выше не поднять -
                                            # верхние пады упрутся в полосы CLK/DIO
b.place("J7", "Connector_PinHeader_1.27mm", "PinHeader_2x07_P1.27mm_Vertical",
        J7X, J7Y, 180, value="STDC14")
b.place("U2", "Package_TO_SOT_SMD", "SOT-23-5", X1 - 5.0, UCY + 14.0, 0, back=True, value="AP2112K-3.3")
b.place("C50", C0805[0], C0805[1], X1 - 5.0, UCY + 18.0, 0, back=True, value="10uF")
b.place("C51", C0805[0], C0805[1], X1 - 5.0, UCY + 21.5, 0, back=True, value="10uF")
b.place("C52", C0603[0], C0603[1], X1 - 5.0, UCY + 25.0, 0, back=True, value="100nF")
b.place("R1", R0402[0], R0402[1], X1 - 1.6, UCY - 1.25, 0, back=True, value="5.1k")   # не ближе 0.3 мм к краю
b.place("R2", R0402[0], R0402[1], X1 - 1.6, UCY + 1.25, 0, back=True, value="5.1k")

XVX = CX - HDI + 2.0
b.place("Y1", "Crystal", "Crystal_SMD_5032-2Pin_5.0x3.2mm", XVX + 7.0, CY, 270, back=True, value="25MHz")
b.place("C60", C0402[0], C0402[1], XVX + 13.0, CY, 0, back=True, value="10pF")
b.place("C61", C0402[0], C0402[1], XVX + 13.0, CY, 0, back=True, value="10pF")
b.place("Y2", "Crystal", "Crystal_SMD_MicroCrystal_CC7V-T1A-2Pin_3.2x1.5mm", XVX + 7.0, CY - 10.0, 270, back=True, value="32.768kHz")
b.place("C62", C0402[0], C0402[1], XVX + 13.0, CY - 10.0, 0, back=True, value="6.8pF")
b.place("C63", C0402[0], C0402[1], XVX + 13.0, CY - 10.0, 0, back=True, value="6.8pF")

b.place("R3", R0402[0], R0402[1], CX - 11.0, CY + 11.0, 45, back=True, value="0R/FB")
b.place("C70", C0402[0], C0402[1], CX - 13.5, CY + 13.5, 225, back=True, value="100nF")
b.place("C71", C0603[0], C0603[1], CX - 16.2, CY + 16.2, 225, back=True, value="1uF")
b.place("C72", C0603[0], C0603[1], CX - 16.5, CY + 16.5, 225, back=True, value="2.2uF")   # VCAP1
b.place("C73", C0603[0], C0603[1], CX - 19.0, CY - 19.0, 45, back=True, value="2.2uF")    # VCAP2
b.place("C74", C0402[0], C0402[1], CX + 24.0, CY - 24.0, 45, back=True, value="100nF")    # VDD33USB
b.place("C75", C0805[0], C0805[1], CX - 24.0, CY - 24.0, -45, back=True, value="4.7uF")
b.place("C76", C0805[0], C0805[1], CX + 24.0, CY + 24.0, 225, back=True, value="4.7uF")
b.place("C77", C0402[0], C0402[1], X0 + 3.4, CY + 16.0, 0, back=True, value="100nF")       # NRST:
# развёрнут падом 1 к полосе NRST, иначе дорожка к нему прошла бы сквозь пад 2 (GND)

VDDP = sorted([n for n in pads if RAWNAME[n] == "VDD"])
for i, n in enumerate(VDDP, 1):
    b.place("C%d" % i, C0402[0], C0402[1], CX, CY, 0, back=True, value="100nF")

HN = 0
for hx, hy in ((X0 + 3.5, Y0 + 3.5), (X0 + 3.5, Y1 - 3.5), (X1 - 3.5, Y1 - 3.5), (X1 - 3.5, Y0 + 3.5)):
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, "MountingHole.pretty"), "MountingHole_2.2mm_M2")
    b.b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(hx), mm(hy)))
    HN += 1
    fp.SetReference("H%d" % HN)
    fp.SetValue("M2")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)

# -------------------------------------------------------------------- схема
# Лист A1: символ МК один занимает 76x188 мм, плюс четыре гребёнки 2x18 и 26
# конденсаторов - на A2 это не раскладывается, часть деталей уезжала за край.
d = kigen.Design(NAME, "STM32H723ZGT6 core board (LQFP144) - 84x84 mm, 4 layers", paper="A1")
d.prepare()
# Сетка для мелочи. Шаг 34 мм по вертикали не от щедрости: двухвыводной детали нужно
# место на провод 5.08 и вертикальную метку цепи с каждой стороны, иначе метки
# соседей слипаются в сплошной столбик.
GX, GY, GDX, GDY, GROWS = 520.0, 60.0, 55.0, 34.0, 12
grid_at = lambda i: (GX + GDX * (i // GROWS), GY + GDY * (i % GROWS))

d.add(kigen.Part("U1", MCU_LIBID, "STM32H723ZGT6", "%s:%s" % MCU_FP,
                 {str(n): mcu_net(n) for n in sorted(pads)}, at=(120, 250)))
for s_, ref in HSIDE.items():
    nets = {str(hn): mcu_net(mn) for (r, hn), mn in hdrmap.items() if r == ref and mn not in NO_HEADER}
    d.add(kigen.Part(ref, "Connector_Generic:Conn_02x18_Odd_Even",
                     {"J2": "PORT_L", "J3": "PORT_B", "J4": "PORT_R", "J5": "PORT_T"}[ref],
                     "%s:PinHeader_2x18_P2.54mm_Vertical" % HDRLIB, nets,
                     at=({"J2": 230, "J3": 290, "J4": 350, "J5": 410}[ref], 120)))
USBC_LIBID = "Connector:USB_C_Receptacle_USB2.0_16P"
SHIELD = [p.number for p in kigen.get_symbol(USBC_LIBID).pins if p.name == "SHIELD"][0]  # S1 в KiCad 7, SH в KiCad 10
d.add(kigen.Part("J1", USBC_LIBID, "USB-C",
                 "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                 {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
                  "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
                  "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
                  "A7": "USB_DM", "B7": "USB_DM", SHIELD: "GND"}, at=(230, 270)))
d.add(kigen.Part("J6", "Connector_Generic:Conn_01x10", "DEBUG",
                 "%s:PinHeader_1x10_P2.54mm_Vertical" % HDRLIB,
                 {"1": "VBUS", "2": "GND", "3": mcu_net(UTX), "4": mcu_net(URX), "5": "NRST",
                  "6": mcu_net(SWO), "7": "GND", "8": "SWCLK", "9": "SWDIO", "10": "+3V3"},
                 at=(340, 270)))
d.add(kigen.Part("J7", "Connector_Generic:Conn_02x07_Odd_Even", "STDC14",
                 "Connector_PinHeader_1.27mm:PinHeader_2x07_P1.27mm_Vertical",
                 {"3": "+3V3", "4": "SWDIO", "5": "GND", "6": "SWCLK", "7": "GND",
                  "8": mcu_net(SWO), "11": "GND", "12": "NRST"}, at=(440, 200)))
d.add(kigen.Part("U2", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
                 {"1": "VBUS", "2": "GND", "3": "VBUS", "5": "+3V3"}, at=(440, 270)))
d.add(kigen.Part("Y1", "Device:Crystal", "25MHz", "Crystal:Crystal_SMD_5032-2Pin_5.0x3.2mm",
                 {"1": "HSE_IN", "2": "HSE_OUT"}, at=(230, 350)))
d.add(kigen.Part("Y2", "Device:Crystal", "32.768kHz",
                 "Crystal:Crystal_SMD_MicroCrystal_CC7V-T1A-2Pin_3.2x1.5mm",
                 {"1": "LSE_IN", "2": "LSE_OUT"}, at=(340, 350)))
d.add(kigen.Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "NRST", "2": "GND"}, at=(440, 350)))
d.add(kigen.Part("SW2", "Switch:SW_Push", "BOOT0", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "BOOT0", "2": "+3V3"}, at=(230, 420)))
d.add(kigen.Part("D1", "Device:LED", "LED", "LED_SMD:LED_0805_2012Metric",
                 {"1": "LED_K", "2": "LED_A"}, at=(340, 420)))

CAPNET = {("C%d" % i): ("+3V3", "GND") for i in range(1, len(VDDP) + 1)}
CAPVAL = {("C%d" % i): "100nF" for i in range(1, len(VDDP) + 1)}
EXTRA = {"C50": ("VBUS", "GND", "10uF"), "C51": ("+3V3", "GND", "10uF"),
         "C52": ("+3V3", "GND", "100nF"),
         "C60": ("HSE_IN", "GND", "10pF"), "C61": ("HSE_OUT", "GND", "10pF"),
         "C62": ("LSE_IN", "GND", "6.8pF"), "C63": ("LSE_OUT", "GND", "6.8pF"),
         "C70": ("+3V3A", "GND", "100nF"), "C71": ("+3V3A", "GND", "1uF"),
         "C72": ("VCAP1", "GND", "2.2uF"), "C73": ("VCAP2", "GND", "2.2uF"),
         "C74": ("+3V3", "GND", "100nF"), "C75": ("+3V3", "GND", "4.7uF"),
         "C76": ("+3V3", "GND", "4.7uF"), "C77": ("NRST", "GND", "100nF")}
for r, (a, k, v) in EXTRA.items():
    CAPNET[r] = (a, k)
    CAPVAL[r] = v
for i, ref in enumerate(sorted(CAPNET, key=lambda r: int(r[1:]))):
    a, k = CAPNET[ref]
    fp = b.fps[ref]
    fid = "%s:%s" % (fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())
    d.add(kigen.Part(ref, "Device:C", CAPVAL[ref], fid, {"1": a, "2": k},
                     at=grid_at(i)))
NCAP = len(CAPNET)                          # резисторы и флаги продолжают ту же сетку
RES = {"R1": ("5.1k", ("CC1", "GND")), "R2": ("5.1k", ("CC2", "GND")),
       "R3": ("0R", ("+3V3", "+3V3A")), "R4": ("10k", ("BOOT0", "GND")),
       "R5": ("1k", ("LED_K", "GND"))}
for i, ref in enumerate(sorted(RES)):
    val, (a, k) = RES[ref]
    d.add(kigen.Part(ref, "Device:R", val, "%s:%s" % R0402, {"1": a, "2": k}, at=grid_at(NCAP + i)))
for i, n in enumerate(["GND", "+3V3", "VBUS"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=grid_at(NCAP + len(RES) + i)))

os.makedirs(OUT, exist_ok=True)
# схема ссылается на ту же библиотеку проекта, что и плата
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

# ===================================================================== разводка
padpt = lambda n: (CX + pads[n][0], CY + pads[n][1])


def inward(n, dist):
    x, y = pads[n]
    if abs(x) > abs(y):
        return (CX + x - math.copysign(dist, x), CY + y)
    return (CX + x, CY + y - math.copysign(dist, y))


def stub(ref, pin, net, dist=1.4, width=W, sgn=None):
    if net == "GND":
        return None
    fp = b.fps[ref]
    lay = BCU if fp.IsFlipped() else FCU
    x, y = b.padxy(ref, pin)
    ax = b.pad_axis(ref)
    if ax:
        px, py = -ax[1], ax[0]
        k = sgn if sgn is not None else (1.0 if str(pin) == "1" else -1.0)
        ex, ey = x + px * dist * k, y + py * dist * k
    else:
        c = (tomm(fp.GetPosition().x), tomm(fp.GetPosition().y))
        vx, vy = x - c[0], y - c[1]
        L = math.hypot(vx, vy) or 1.0
        ex, ey = x + vx / L * dist, y + vy / L * dist
    b.track(net, [(x, y), (ex, ey)], lay, width)
    b.via(net, ex, ey, dia=0.6, drill=0.3)
    return (ex, ey)


# --- питание корпуса: внутрь, со ступенчатым радиусом
# Шаг выводов 0.5 мм, via 0.5 мм: до дорожки соседа остаётся 0.16 мм. Соседние отводы
# и так уходят на разную глубину, но дорожка более глубокого соседа проходит мимо
# нашей via вплотную - поэтому via сдвигаем вдоль ряда прочь от такого соседа.
INNER = {}
DIST = [2.2, 3.6, 5.0]
LAT = 0.2                                  # 0.5 + 0.2 > 0.25 (via) + 0.2 (зазор) + 0.075 (дорожка)
ESCNET = ("+3V3", "GND", "VCAP1", "VCAP2")
for s_ in ("L", "R", "T", "B"):
    row = sides[s_]
    esc = [n for n in row if mcu_net(n) in ESCNET]
    depth = {n: DIST[k % 3] for k, n in enumerate(esc)}
    at = {n: i for i, n in enumerate(row)}
    for n in esc:
        i = at[n]
        nb = [row[j] for j in (i - 1, i + 1) if 0 <= j < len(row)]
        deep = [m for m in nb if depth.get(m, 0) > depth[n]]
        deep.sort(key=lambda m: depth[m])
        away = -sum(1 if at[m] > i else -1 for m in deep[-1:])   # прочь от самого глубокого
        v = inward(n, depth[n])
        if away:
            lx, ly = (0.0, LAT * away) if s_ in ("L", "R") else (LAT * away, 0.0)
            v = (v[0] + lx, v[1] + ly)
            b.track(mcu_net(n), [padpt(n), inward(n, 1.0), v], FCU, W)
        else:
            b.track(mcu_net(n), [padpt(n), v], FCU, W)
        b.via(mcu_net(n), *v, dia=0.5, drill=0.25)
        INNER[n] = v

# --- развязка по диагоналям (обратная сторона)
GRID = [(-4.8, -4.8), (-1.6, -4.8), (1.6, -4.8),
        (-4.8, -1.6), (-1.6, -1.6), (1.6, -1.6), (4.8, -1.6),
        (-4.8, 1.6), (-1.6, 1.6), (1.6, 1.6), (4.8, 1.6),
        (-4.8, 4.8), (-1.6, 4.8)]
V3 = {}
for i in range(1, len(VDDP) + 1):
    dx, dy = GRID[i - 1]
    fp = b.fps["C%d" % i]
    fp.SetPosition(pcbnew.VECTOR2I(mm(CX + dx), mm(CY + dy)))
    fp.SetOrientationDegrees(0)
    V3["C%d" % i] = stub("C%d" % i, 1, "+3V3", 1.25)

# --- кварцы: веер до via перед внутренним рядом
XV = {}
for n in (8, 9, 23, 24):
    px, py = padpt(n)
    yy = hdrof[n]["gap"] if hdrof[n]["row"] else hdrof[n]["inner"][1]
    b.track(mcu_net(n), [(px, py), (px - 1.4, py), (XVX, yy)], FCU, 0.18)
    b.via(mcu_net(n), XVX, yy, dia=0.5, drill=0.25)
    XV[n] = (XVX, yy)

# --- сигнальный веер (двухрядные гребёнки)
for mn, h in hdrof.items():
    if mn in NO_HEADER or mcu_net(mn) in ("+3V3", "GND"):
        continue
    sx, sy = SD[h["side"]]
    px, py = padpt(mn)
    hx, hy = h["x"], h["y"]
    ix, iy = h["inner"]
    if sx:
        a = (px + sx * 1.4, py)
        st = ix - sx * APPR
        if h["row"] == 0:
            pts = [(px, py), a, (st, hy), (hx, hy)]
        else:
            g = h["gap"]
            pts = [(px, py), a, (st, g), (ix + sx * 1.6, g), (hx, hy)]
    else:
        a = (px, py + sy * 1.4)
        st = iy - sy * APPR
        if h["row"] == 0:
            pts = [(px, py), a, (hx, st), (hx, hy)]
        else:
            g = h["gap"]
            pts = [(px, py), a, (g, st), (g, iy + sy * 1.6), (hx, hy)]
    b.track(mcu_net(mn), pts, FCU, W)

hxy = lambda mn: (hdrof[mn]["x"], hdrof[mn]["y"])


def to_hdr(mn, frm, app=3.0):
    """Путь снаружи платы к паду гребёнки (нижний слой: там нет веера)."""
    h = hdrof[mn]
    sx, sy = SD[h["side"]]
    hx, hy = h["x"], h["y"]
    if h["row"] == 1:
        return [frm, (hx + sx * app, hy) if sx else (hx, hy + sy * app), (hx, hy)]
    g = h["gap"]
    ox, oy = (hx + sx * 2.54, hy) if sx else (hx, hy + sy * 2.54)
    if sx:
        return [frm, (ox + sx * app, g), (ox, g), (hx + sx * 1.1, g), (hx, hy)]
    return [frm, (g, oy + sy * app), (g, oy), (g, hy + sy * 1.1), (hx, hy)]

# --- кварцы на обратной стороне
for xtal, pins, caps in (("Y1", (23, 24), ("C60", "C61")), ("Y2", (8, 9), ("C62", "C63"))):
    for k, (mpin, cap) in enumerate(zip(pins, caps)):
        xp = b.padxy(xtal, k + 1)
        fp = b.fps[cap]
        fp.SetPosition(pcbnew.VECTOR2I(mm(tomm(fp.GetPosition().x)), mm(xp[1])))
        cp = b.padxy(cap, 1)
        b.track(mcu_net(mpin), [XV[mpin], xp], BCU, 0.18)
        b.track(mcu_net(mpin), [xp, cp], BCU, 0.18)

# --- VCAP: банки максимально близко, на обратной стороне под корпусом
VCPOS = {71: (CX + 5.4, CY + 5.4, 90), 106: (CX + 5.4, CY - 5.4, 180)}
for n, cap in ((71, "C72"), (106, "C73")):
    v = INNER[n]
    fp = b.fps[cap]
    x, y, rot = VCPOS[n]
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(rot)
    cp1 = b.padxy(cap, 1)
    b.track(mcu_net(n), [v, (v[0], cp1[1]) if abs(pads[n][0]) > abs(pads[n][1]) else (cp1[0], v[1]), cp1], BCU, WP)

# --- VDDA / VREF+
va = [n for n in pads if RAWNAME[n] == "VDDA"][0]
vr = [n for n in pads if RAWNAME[n] == "VREF+"][0]
def from_inside(mn, frm):
    h = hdrof[mn]
    sx, sy = SD[h["side"]]
    hx, hy = h["x"], h["y"]
    ix, iy = h["inner"]
    if h["row"] == 0:
        return [frm, (hx - sx * 2.6, hy), (hx, hy)]
    g = h["gap"]
    if sx:
        return [frm, (ix - sx * 3.0, g), (ix + sx * 1.6, g), (hx, hy)]
    return [frm, (g, iy - sy * 3.0), (g, iy + sy * 1.6), (hx, hy)]


AP = (hdrof[va]["x"], hdrof[va]["y"])
AP2 = (hdrof[vr]["x"], hdrof[vr]["y"])
b.fps["R3"].SetPosition(pcbnew.VECTOR2I(mm(CX - HDI + 7.0), mm(AP[1] - 5.0)))
b.fps["R3"].SetOrientationDegrees(0)
b.fps["C70"].SetPosition(pcbnew.VECTOR2I(mm(CX - HDI + 7.0), mm(AP[1] - 8.0)))
b.fps["C70"].SetOrientationDegrees(180)
b.fps["C71"].SetPosition(pcbnew.VECTOR2I(mm(CX - HDI + 7.0), mm(AP[1] - 11.0)))
b.fps["C71"].SetOrientationDegrees(180)
r3a = b.padxy("R3", 2)
b.track("+3V3A", from_inside(va, (r3a[0], AP[1])), BCU, W)
b.track("+3V3A", [(r3a[0], AP[1]), r3a], BCU, W)
b.track("+3V3A", from_inside(vr, (r3a[0] + 2.4, AP2[1])), BCU, W)
b.track("+3V3A", [(r3a[0] + 2.4, AP2[1]), (r3a[0] + 2.4, AP[1]), (r3a[0], AP[1])], BCU, W)
CH = r3a[0] + 1.5
for a_, c_ in ((r3a, b.padxy("C70", 1)), (b.padxy("C70", 1), b.padxy("C71", 1))):
    b.track("+3V3A", [a_, (CH, a_[1]), (CH, c_[1]), c_], BCU, W)
stub("R3", 1, "+3V3", 1.6, sgn=-1.0)
for r in ("C74", "C75", "C76"):
    stub(r, 1, "+3V3", 1.4)

# --- USB-C
UX = b.padxy("J1", "A4")[0]
PY_ = lambda p_: round(b.padxy("J1", p_)[1], 3)
# Между внешним рядом J4 и падами разъёма остаётся коридор 2.7 мм, а колонок via
# в нём три: D+, D- и VBUS. Раскладываем их от гребёнки, а не от разъёма.
HOX = CX + HDO
# Колонки via держим у разъёма, а не у гребёнки: после сдвига кристалла коридор
# вырос до 8.4 мм, и отжимать их к падам J4 больше незачем.
LDP, LDM, XVBUS = UX - 4.2, UX - 3.0, UX - 1.8
YU, YL0 = sorted((PY_("A9"), PY_("A4")))
b.track("VBUS", [(UX, YL0), (XVBUS, YL0)], FCU, WP)
b.via("VBUS", XVBUS, YL0, dia=0.6, drill=0.3)
b.track("VBUS", [(UX, YU), (XVBUS, YU)], FCU, WP)
b.via("VBUS", XVBUS, YU, dia=0.6, drill=0.3)
b.track("VBUS", [(XVBUS, YU), (XVBUS, YL0)], BCU, WP)
u1p, u3p = b.padxy("U2", 1), b.padxy("U2", 3)
b.track("VBUS", [(XVBUS, YL0), (XVBUS, u1p[1]), u1p], BCU, WP)
b.track("VBUS", [u1p, (u1p[0] - 1.9, u1p[1]), (u3p[0] - 1.9, u3p[1]), u3p], BCU, WP)
c50 = b.padxy("C50", 1)
b.track("VBUS", [(XVBUS, u1p[1]), (XVBUS, c50[1]), c50], BCU, WP)
stub("U2", 5, "+3V3", 1.8)
stub("C51", 1, "+3V3", 1.5)
stub("C52", 1, "+3V3", 1.5)
for p_, net, r in (("A5", "CC1", "R1"), ("B5", "CC2", "R2")):
    y = PY_(p_)
    fp = b.fps[r]
    fp.SetPosition(pcbnew.VECTOR2I(mm(tomm(fp.GetPosition().x)), mm(y)))
    b.track(net, [(UX, y), (UX + 1.2, y)], FCU, W)
    b.via(net, UX + 1.2, y, dia=0.5, drill=0.25)
    b.track(net, [(UX + 1.2, y), b.padxy(r, 1)], BCU, W)
DPY_ = sorted({PY_("A6"), PY_("B6")})
DMY_ = sorted({PY_("A7"), PY_("B7")})
# Пады D+ и D- у этого разъёма чередуются с шагом 0.5 мм, поэтому дорожка D+
# идёт в свою колонку ровно посередине между via D-: 0.5 - 0.225 (via) - 0.075
# (полдорожки) = 0.2 мм, то есть впритык под правило, но не под ним.
DPV = [(LDP, y) for y in DPY_]
for y in DPY_:
    b.track("USB_DP", [(UX, y), (LDP, y)], FCU, WD)
    b.via("USB_DP", LDP, y, dia=0.45, drill=0.25)
b.track("USB_DP", [DPV[0], DPV[1]], BCU, WD)
for y in DMY_:
    b.track("USB_DM", [(UX, y), (LDM, y)], FCU, WD)
    b.via("USB_DM", LDM, y, dia=0.45, drill=0.25)
b.track("USB_DM", [(LDM, DMY_[0]), (LDM, DMY_[1])], BCU, WD)
# D+/D- заодно выведены на J4 (контакты 3 и 4) - отвод по нижнему слою вдоль гребёнки
LP1 = (LDP, hdrof[104]["gap"] if hdrof[104]["row"] == 0 else hdrof[104]["y"])
b.track("USB_DP", [DPV[0], LP1], BCU, WD)
b.track("USB_DP", to_hdr(104, LP1, app=LDP - HOX), BCU, WD)
LP2 = (LDM, hdrof[103]["gap"] if hdrof[103]["row"] == 0 else hdrof[103]["y"])
b.track("USB_DM", [(LDM, DMY_[0]), LP2], BCU, WD)
b.track("USB_DM", to_hdr(103, LP2, app=LDM - HOX), BCU, WD)

# --- разъём прошивки 1x10 (порядок как у WeAct MiniDebugger / STLink V2.1)
# Пады разъёма сквозные, так что с каждого можно уходить на любом слое. Полоса под
# разъёмом узкая (1.8 мм до внешнего ряда J5), поэтому длинные трассы на запад -
# NRST и SWO - уводим не под разъём, а над ним, вдоль верхнего края платы.
j = lambda n: b.padxy("J6", n)
# 5V спускается ниже подписей разъёма: вплотную под падами до них оставалось
# 0.275 мм при норме 0.2 - по правилам проходит, но слишком впритык.
LN5V, LNCLK = JY + 4.20, JY + 1.80          # полосы под разъёмом (F.Cu / B.Cu)
LNSWO, LNRST = Y0 + 1.40, Y0 + 2.10         # полосы над разъёмом, вдоль верхнего края
# Обход углового крепёжного отверстия: спускаемся ровно по оси SW2 (там просвет
# между двумя keepout под её корпусом) и уходим на запад уже ниже кнопки.
NDOG, NDOGY = X0 + 11.0, Y0 + 11.0
XDIO = HOX + 1.84                           # спуск SWDIO: восточнее падов J4, не в их створ
NRSTY = hdrof[25]["gap"] if hdrof[25]["row"] == 0 else hdrof[25]["y"]
LANE_N = X0 + 3.00                          # NRST спускается ниже отверстий и может
                                            # идти спокойно, вдали от контура
SWB = TOPY + 4.0                            # полоса под кнопками

# 5V -> VBUS: по верху на восток и сразу вниз, в ту же колонку VBUS. Забирать
# восточнее и возвращаться незачем - коридор между гребёнкой и разъёмом это позволяет.
# 5V идёт кратчайшим путём: короткий спуск, затем диагональ под 45 градусов через
# угол, где сходятся J5 и J4 - до падов обеих гребёнок остаётся по 2.4 мм.
# Диагональ 5V держим в 2.4 мм северо-восточнее линии, на которой лежат угловые
# пады J5 и J4 - иначе она уходит прямо в них. К положению J6 это не привязано.
VCORN = hdrof[109]["y"] - hdrof[109]["x"]
VBX0 = LN5V - VCORN + 3.33
VBEND = (XVBUS, LN5V + (XVBUS - VBX0))
b.track("VBUS", [j(1), (j(1)[0], LN5V), (VBX0, LN5V), VBEND], FCU, WP)
b.via("VBUS", *VBEND, dia=0.6, drill=0.3)
b.track("VBUS", [VBEND, (XVBUS, YU)], BCU, WP)
# SWCLK: короткая полоса на запад и вниз на свой пад
# CLK и DIO теперь на западном конце разъёма, а их цели - у восточного края.
# Ведём их поверху, над разъёмом: там освободилась полоса от SWO.
# Полоса NRST идёт на запад ровно между ними и их падами, поэтому вниз уходим
# уже за ней: короткий кусок по верхнему слою, дальше понизу.
b.track("SWCLK", [j(8), (j(8)[0], LNSWO)], FCU, W)
b.via("SWCLK", j(8)[0], LNSWO, dia=0.45, drill=0.25)   # полоса узкая, via помельче
b.track("SWCLK", [(j(8)[0], LNSWO), (hdrof[109]["x"], LNSWO),
                  (hdrof[109]["x"], hdrof[109]["y"])], BCU, W)
# SWDIO: вниз по правому кольцу, там ещё свободно - коридор USB начинается ниже
b.track("SWDIO", [j(9), (j(9)[0], LNSWO - 0.5)], FCU, W)
b.via("SWDIO", j(9)[0], LNSWO - 0.5, dia=0.45, drill=0.25)
b.track("SWDIO", [(j(9)[0], LNSWO - 0.5), (XDIO, LNSWO - 0.5),
                  (XDIO, hdrof[105]["y"] - 1.1), (HOX + 1.4, hdrof[105]["y"])], BCU, W)
b.track("SWDIO", to_hdr(105, (HOX + 1.4, hdrof[105]["y"]), app=1.4), BCU, W)
# RX/TX: сразу вниз на верхнюю гребёнку, внутренний ряд - через проход между падами
# Сперва вертикально вниз, потом на восток: наискось от пада дорожка проходила
# впритык к соседнему контакту разъёма.
# RX и TX идут в обратном порядке относительно своих целей - разводим по слоям.
b.track(mcu_net(UTX), [j(3), (j(3)[0], LNCLK + 1.3)], FCU, W)
b.via(mcu_net(UTX), j(3)[0], LNCLK + 1.3, dia=0.6, drill=0.3)
b.track(mcu_net(UTX), [(j(3)[0], LNCLK + 1.3), (hdrof[UTX]["x"], LNCLK + 1.3),
                       (hdrof[UTX]["x"], hdrof[UTX]["y"])], BCU, W)
GRX = hdrof[URX]["gap"]                     # проход между падами внешнего ряда
b.track(mcu_net(URX), [j(4), (j(4)[0], LNCLK + 0.5), (GRX, LNCLK + 0.5),
                       (GRX, hdrof[URX]["y"] - 1.1), (hdrof[URX]["x"], hdrof[URX]["y"])], BCU, W)
# SWO и NRST: над разъёмом вдоль верхнего края
# SWO стоит ровно над своим падом - ведём прямо вниз, без объезда поверху.
b.track(mcu_net(SWO), [j(6), (hdrof[SWO]["x"], hdrof[SWO]["y"])], BCU, W)
# NRST - по нижнему слою: его полоса и полоса SWO иначе пересекаются (разъём и
# цели у них идут внахлёст, в один слой такую пару не уложить).
# NRST не жмётся к краю: до левого кольца он идёт по верхней полосе, обходит
# крепёжное отверстие в углу снизу и только потом спускается.
b.track("NRST", [j(5), (j(5)[0], LNRST), (NDOG, LNRST), (NDOG, NDOGY),
                 (LANE_N, NDOGY), (LANE_N, NRSTY)], BCU, W)
# +3V3 у западного торца J6: отвод строго на север - на западе спускается BOOT0.
_j10 = b.padxy("J6", 10)
b.track("+3V3", [_j10, (_j10[0], _j10[1] - 1.8)], FCU, W)
b.via("+3V3", _j10[0], _j10[1] - 1.8, dia=0.6, drill=0.3)

# --- STDC14: сигналы идут вверх к одноимённым контактам J6. Порядок совпадает,
# поэтому веер раскрывается без пересечений; полосы разнесены по глубине.
# Веер STDC14. Каждый сигнал идёт на запад по строке своего пада - пересекаться
# между собой строкам негде. Разводим по слоям: считаться приходится с уже
# проложенными спусками от J6 (NRST низом, SWCLK и SWDIO верхом).
def j7row(pin, xt, layer):
    """Пад STDC14 -> прямо на запад до цели xt по строке пада."""
    px, py = b.padxy("J7", pin)
    net = b.fps["J7"].FindPadByNumber(str(pin)).GetNetname()
    b.track(net, [(px, py), (xt, py)], layer, W)
    return py


# NRST - самая северная строка и самая восточная цель: до своего спуска (низ)
# ей никто не мешает.
j7row(12, j(5)[0], BCU)
# SWCLK садится на свой спуск (верх); спуск NRST она пересекает по другому слою.
j7row(6, j(8)[0], FCU)
# У SWO спуска наверх нет - доводим до пада J6 сами, низом: поверху дорожка
# пересекла бы строку SWCLK.
_y8 = j7row(8, j(6)[0], FCU)
b.via(mcu_net(SWO), j(6)[0], _y8, dia=0.45, drill=0.25)
b.track(mcu_net(SWO), [(j(6)[0], _y8), (j(6)[0], JY)], BCU, W)
# SWDIO - самая западная цель: её строке мешают и спуск NRST (низ), и спуск
# SWCLK (верх). Меняем слой в промежутке между ними.
XH = (j(6)[0] + j(8)[0]) / 2 + 0.35         # между спусками SWO и SWCLK
_y4 = j7row(4, XH, FCU)
b.via("SWDIO", XH, _y4, dia=0.45, drill=0.25)
b.track("SWDIO", [(XH, _y4), (j(9)[0], _y4)], BCU, W)
b.via("SWDIO", j(9)[0], _y4, dia=0.45, drill=0.25)
# У этого разъёма пады густые, автоотвод stub() упирается в соседний - уводим
# питание на юг, в сторону от корпуса.
_p3 = b.padxy("J7", 3)
b.track("+3V3", [_p3, (_p3[0] + 1.7, _p3[1])], FCU, W)
b.via("+3V3", _p3[0] + 1.7, _p3[1], dia=0.45, drill=0.25)

# --- кнопки / светодиод
# Два пада с одним номером соединяем в обход корпуса кнопки: под ним у футпринта
# keepout, и дорожка внутрь от пада - это items_not_allowed в DRC.
for sw in ("SW1", "SW2"):
    cx, cy = tomm(b.fps[sw].GetPosition().x), tomm(b.fps[sw].GetPosition().y)
    for pn in ("1", "2"):
        pp = [(tomm(q.GetPosition().x), tomm(q.GetPosition().y)) for q in b.fps[sw].Pads() if q.GetNumber() == pn]
        if len(pp) == 2:
            net = b.fps[sw].FindPadByNumber(pn).GetNetname()
            # обход считаем от центра кнопки, а не по вертикали: кнопка может стоять
            # повёрнутой, и тогда пара падов разнесена не по x, а по y
            vx, vy = (pp[0][0] + pp[1][0]) / 2 - cx, (pp[0][1] + pp[1][1]) / 2 - cy
            L = math.hypot(vx, vy) or 1.0
            ox, oy = vx / L * 1.6, vy / L * 1.6
            b.track(net, [pp[0], (pp[0][0] + ox, pp[0][1] + oy),
                          (pp[1][0] + ox, pp[1][1] + oy), pp[1]], FCU, W)
def dup_pad(ref, num, rightmost=True):
    pp = sorted((tomm(q.GetPosition().x), tomm(q.GetPosition().y))
                for q in b.fps[ref].Pads() if q.GetNumber() == str(num))
    return pp[-1] if rightmost else pp[0]


# BOOT0: правый пад SW2 -> R4 (подтяжка вниз), левый -> вниз на свой пад гребёнки
br, bl = dup_pad("SW2", 1, False), dup_pad("SW2", 1, True)   # R4 западнее, гребёнка восточнее
R4X = b.padxy("R4", 1)[0]
if (br[0] - hdrof[SWO]["x"]) * (R4X - hdrof[SWO]["x"]) < 0:
    # Если между SW2 и R4 оказался спуск SWO на верхнюю гребёнку - перепрыгиваем понизу.
    BH0 = (hdrof[SWO]["x"] - 0.75, br[1])
    BH1 = (hdrof[SWO]["x"] + 0.95, br[1])
    b.track("BOOT0", [br, BH0], FCU, W)
    b.via("BOOT0", *BH0, dia=0.6, drill=0.3)
    b.track("BOOT0", [BH0, BH1], BCU, W)
    b.via("BOOT0", *BH1, dia=0.6, drill=0.3)
    b.track("BOOT0", [BH1, (R4X, br[1]), b.padxy("R4", 1)], FCU, W)
else:
    b.track("BOOT0", [br, (b.padxy("R4", 1)[0], br[1]), b.padxy("R4", 1)], FCU, W)
stub("R4", 2, "GND", 1.3)
# Уходим на нижний слой восточнее спуска NRST, иначе дорожка к гребёнке пересекла бы его.
BJ = (bl[0] + 1.5, bl[1])
b.track("BOOT0", [bl, BJ], FCU, W)
b.via("BOOT0", *BJ, dia=0.6, drill=0.3)
# J6 опустился, и прямая к гребёнке пошла бы прямо по его западным падам:
# спускаемся западнее разъёма и идём на восток уже под ним.
BOY = JY + 4.1                              # между полосами RX/TX и падами J5
_bp = to_hdr(138, BJ)
b.track("BOOT0", [BJ, (BJ[0], BOY), (_bp[1][0], BOY)] + _bp[2:], BCU, W)
sx, sy = dup_pad("SW2", 2, True)
b.track("+3V3", [(sx, sy), (sx, sy + 1.6)], FCU, W)
b.via("+3V3", sx, sy + 1.6, dia=0.6, drill=0.3)

# NRST: кнопка стоит рядом с разъёмом прошивки и цепляется к той же полосе,
# которая уже идёт от J6 вдоль верхнего края и вниз по левому кольцу.
# Кнопка стоит над левым кольцом, поэтому цепляем её прямо к полосе NRST сбоку,
# а не тянем вверх - наверху теперь пады BOOT0.
nx, ny = dup_pad("SW1", 1, False)   # ближний к полосе NRST пад
b.via("NRST", nx, ny, dia=0.6, drill=0.3)
b.track("NRST", [(nx, ny), (LANE_N, ny)], BCU, W)
# Заход к гребёнке привязан к самой полосе: со стандартным отступом дорожка сперва
# откатывалась назад на запад и сходилась с полосой под острым углом.
b.track("NRST", to_hdr(25, (LANE_N, NRSTY), app=(CX - HDO) - LANE_N), BCU, W)
b.track("NRST", [(LANE_N, NRSTY), (LANE_N, CY + 16.0), b.padxy("C77", 1)], BCU, W)

# LED_A: светодиод наверху, а его вывод МК - на нижней гребёнке; ведём по левому кольцу
# Светодиод стоит у своей гребёнки, так что LED_A - короткий отвод по нижнему кольцу.
YBOT = Y1 - 2.5                             # полоса под нижней гребёнкой
dp = b.padxy("D1", 2)
LV = (dp[0] + 1.5, dp[1] + 1.5)             # пад SMD - уходим вниз через via, по 45
b.track("LED_A", [dp, LV], FCU, W)
b.via("LED_A", *LV, dia=0.6, drill=0.3)
b.track("LED_A", [LV, (LV[0] + (YBOT - LV[1]), YBOT), (hdrof[46]["x"], YBOT)], BCU, W)
b.track("LED_A", to_hdr(46, (hdrof[46]["x"], YBOT)), BCU, W)
b.track("LED_K", [b.padxy("D1", 1), b.padxy("R5", 1)], FCU, W)
stub("R5", 2, "GND", 1.2)

# -------------------------------------------------- контур, полигоны, шелк
b.edge_rect(BCX, BCY, BW, BH, 3.0)
b.zone("GND", pcbnew.In1_Cu, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("+3V3", pcbnew.In2_Cu, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("GND", FCU, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("GND", BCU, BCX, BCY, BW - 0.8, BH - 0.8)
# Подписи контактов - подписан каждый, оба ряда. Строки всегда снизу и слева от
# гребёнки, ближняя строка относится к ближнему ряду контактов. У J2 и J3 подписи
# уходят наружу платы (кольца слева и снизу свободны), у J4 и J5 - внутрь: снаружи
# у них USB-C с брендингом и кнопки с разъёмом прошивки.
# У J2 и J3 кольца снаружи свободны: внешний ряд подписан снаружи платы, внутренний -
# изнутри гребёнки, по одной строке с каждой стороны.
LBL_ONE = {("L", 0): (3.0, 0.0, 0), ("L", 1): (-3.5, 0.0, 0),
           ("B", 0): (0.0, -3.0, 90), ("B", 1): (0.0, 3.5, 90)}
HDRLBL = []                                 # (надпись, вывод МК)
for mn, h in hdrof.items():
    off = LBL_ONE.get((h["side"], h["row"]))
    if off is not None:
        dx, dy, rot = off
        HDRLBL.append((b.text("NC" if mn in NO_HEADER else mcu_net(mn), h["x"] + dx, h["y"] + dy,
                              pcbnew.F_SilkS, 0.6, 0.1, rot), mn))

# У J4 и J5 снаружи стоят USB-C с брендингом и кнопки с разъёмом прошивки, поэтому обе
# строки уходят внутрь. Вторую отодвигаем не на глаз, а на фактическую ширину первой:
# имена разной длины (USB_DP против GND), подобранный вручную зазор где-нибудь не сойдётся.
LBL_DIR = {"R": -1.0, "T": 1.0}             # куда растут строки от гребёнки
LBL_GAP = 0.5


def lbl_put(mn, coord):
    h = hdrof[mn]
    horiz = h["side"] in ("L", "R")
    t = b.text("NC" if mn in NO_HEADER else mcu_net(mn),
               coord if horiz else h["x"], h["y"] if horiz else coord,
               pcbnew.F_SilkS, 0.6, 0.1, 0 if horiz else 90)
    HDRLBL.append((t, mn))
    return t


def lbl_box(t):
    """Габарит надписи с учётом поворота."""
    bb = kicadenv.textbox(t)
    w, h = tomm(bb.GetWidth()), tomm(bb.GetHeight())
    if round(t.GetTextAngleDegrees()) % 180 == 90:
        w, h = h, w
    p = t.GetPosition()
    cx, cy = tomm(p.x), tomm(p.y)
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _fp_boxes():
    """Корпуса и пады лицевой стороны - поверх них подпись ставить бессмысленно.

    Курятники самих гребёнок не считаем: подпись и должна стоять вплотную к своей
    гребёнке, иначе ей просто негде разместиться.
    """
    out = []
    for fp in b.b.GetFootprints():
        if fp.IsFlipped():
            continue
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        if poly.OutlineCount() and fp.GetReference() not in ("J2", "J3", "J4", "J5"):
            r = poly.BBox()
            out.append((tomm(r.GetLeft()), tomm(r.GetTop()), tomm(r.GetRight()), tomm(r.GetBottom())))
        for pd in fp.Pads():
            if pcbnew.F_Cu in set(pd.GetLayerSet().Seq()):
                r = pd.GetBoundingBox()
                out.append((tomm(r.GetLeft()), tomm(r.GetTop()), tomm(r.GetRight()), tomm(r.GetBottom())))
    return out


OBST = _fp_boxes()


def lbl_free(box):
    """Место под подпись: внутри платы и не на корпусе/паде."""
    x0, y0, x1, y1 = box
    if x0 < X0 + 0.5 or x1 > X1 - 0.5 or y0 < Y0 + 0.5 or y1 > Y1 - 0.5:
        return False
    return not any(x0 - 0.2 < e and a - 0.2 < x1 and y0 - 0.2 < f and c - 0.2 < y1
                   for a, c, e, f in OBST)


def lbl_edge(ts, d, horiz, near):
    """Крайняя координата группы надписей: near=True - обращённая к гребёнке.

    GetTextBox отдаёт габарит без учёта поворота, а вдоль строки надпись в обоих
    случаях вытянута именно длиной - поэтому берём ширину, а не высоту.
    """
    vals = []
    for t in ts:
        p = t.GetPosition()
        c = tomm(p.x) if horiz else tomm(p.y)
        half = tomm(kicadenv.textbox(t).GetWidth()) / 2.0
        vals.append(c - d * half if near else c + d * half)
    return min(vals) if (d > 0) == near else max(vals)


for s_ in ("T", "R"):                        # J5 первой: в углу её подписи главнее
    d = LBL_DIR[s_]
    horiz = s_ == "R"
    pins = [mn for mn in hdrof if hdrof[mn]["side"] == s_]
    ix, iy = hdrof[pins[0]]["inner"]
    line1 = (ix if horiz else iy) + d * 3.0  # ближний ряд для J4/J5 - внутренний
    t1 = [lbl_put(mn, line1) for mn in pins if hdrof[mn]["row"] == 0]
    p2 = [(lbl_put(mn, line1), mn) for mn in pins if hdrof[mn]["row"] == 1]
    t2 = [t for t, _ in p2]
    shift = (lbl_edge(t1, d, horiz, False) + d * LBL_GAP) - lbl_edge(t2, d, horiz, True)
    for t in t2:                             # вторую строку двигаем за первую
        p = t.GetPosition()
        t.SetPosition(pcbnew.VECTOR2I(p.x + (mm(shift) if horiz else 0), p.y + (0 if horiz else mm(shift))))
    if s_ == "R":
        # Внешний ряд J4 уводим вправо, за гребёнку: слева он идёт вторым столбцом и
        # отжимает подписи вглубь веера. Влезет ли справа - решает проверка по месту:
        # напротив USB-C кольцо занято самим разъёмом, и подпись откатывается влево.
        for t, mn in p2:
            inside = t.GetPosition()
            t.SetPosition(pcbnew.VECTOR2I(mm(hdrof[mn]["x"] + 3.4), inside.y))
            if not lbl_free(lbl_box(t)):
                t.SetPosition(inside)


OUTDIR = {"L": (-1.0, 0.0), "R": (1.0, 0.0), "T": (0.0, -1.0), "B": (0.0, 1.0)}


def lbl_move_out(t, mn):
    """Переставить подпись за гребёнку - в кольцо, если внутри места не нашлось."""
    h = hdrof[mn]
    ux, uy = OUTDIR[h["side"]]
    ix, iy = h["inner"]
    p = t.GetPosition()
    if ux:
        t.SetPosition(pcbnew.VECTOR2I(mm(ix + ux * (2.54 + 3.0)), p.y))
    else:
        t.SetPosition(pcbnew.VECTOR2I(p.x, mm(iy + uy * (2.54 + 3.0))))


# В верхнем правом углу полосы подписей J5 (две строки вниз) и J4 (две колонки влево)
# встречаются, и подписать там оба ряда изнутри негде. Такую подпись выносим за
# гребёнку, в свободное кольцо; снимаем только если и там занято.
def _clashes(box, boxes):
    x0, y0, x1, y1 = box
    return any(x0 - 0.2 < e and a - 0.2 < x1 and y0 - 0.2 < f and c - 0.2 < y1
               for a, c, e, f in boxes)


_kept, _out, _drop = [], [], []
for t, mn in HDRLBL:
    if _clashes(lbl_box(t), _kept):
        lbl_move_out(t, mn)
        _out.append(t.GetText())
        if _clashes(lbl_box(t), _kept):
            _out.pop()
            _drop.append(t.GetText())
            b.b.Remove(t)
            continue
    _kept.append(lbl_box(t))
print("подписи контактов: %d, вынесено за гребёнку: %s, снято: %s"
      % (len(_kept), _out or "-", _drop or "-"))
DBGLBL = {1: "5V", 2: "GND", 3: "RX", 4: "TX", 5: "RST",
          6: "SWO", 7: "GND", 8: "CLK", 9: "DIO", 10: "3V3"}
for pin, lbl in DBGLBL.items():             # подписи под разъёмом: сверху у него край платы
    px, py = b.padxy("J6", pin)
    b.text(lbl, px, py + 2.8, pcbnew.F_SilkS, 0.8, 0.15, 90)

# --- подписи кнопок, название и брендинг - как на G474
b.text("RST", tomm(b.fps["SW1"].GetPosition().x) - 5.6, tomm(b.fps["SW1"].GetPosition().y),
       pcbnew.F_SilkS, 1.6, 0.28, 90)
b.text("BOOT", tomm(b.fps["SW2"].GetPosition().x), TOPY - 4.6, pcbnew.F_SilkS, 1.6, 0.28, 0)
b.text("STM32H723ZGT6 CORE BOARD", CX, CY + 16.4, pcbnew.F_SilkS, 1.6, 0.28)
b.text("ASTechLab", X1 - 6.6, CY + 18.0, pcbnew.F_SilkS, 3.0, 1.0, 90)
b.text("84x84 mm | 4 layer | rev.A", X1 - 1.9, CY + 18.0, pcbnew.F_SilkS, 1.0, 0.18, 90)

# --------------------------------------------- номиналы деталей на шелкографии
# Ставим значение рядом с деталью, перебирая позиции вокруг неё и пропуская те,
# где уже что-то нарисовано на том же слое шелка (или где мы выходим за плату).
SILK = (pcbnew.F_SilkS, pcbnew.B_SilkS)
MARGIN = 0.3
# Позиции, выставленные вручную. J5 - в торец гребёнки справа: автоподбор ставил её
# над рядом, где она мешалась разъёму прошивки.
_J5X = max(h["x"] for h in hdrof.values() if h["side"] == "T") + 3.4
_J2Y = min(h["y"] for h in hdrof.values() if h["side"] == "L") - 3.4
# Светодиод с резистором стоят по диагонали, и автоподбор разносил их надписи так,
# что номинал одного оказывался у другого. Закрепляем: номиналы с северо-восточной
# стороны пары, обозначения с юго-западной, все вдоль самих деталей.
_XY = lambda r: (tomm(b.fps[r].GetPosition().x), tomm(b.fps[r].GetPosition().y))
_NE, _SW = (0.7071, -0.7071), (-0.7071, 0.7071)
_off = lambda r, d, k: (_XY(r)[0] + d[0] * k, _XY(r)[1] + d[1] * k, -45)
REF_AT = {"J5": (_J5X, (CY - HDI + CY - HDO) / 2, 0),
          "J2": (CX - (HDI + HDO) / 2, _J2Y, 0),   # наверх: снизу теперь светодиод
          "R5": _off("R5", _SW, 2.4), "D1": _off("D1", _SW, 2.2)}
VAL_AT = {"R5": _off("R5", _NE, 2.2), "D1": _off("D1", _NE, 2.6)}


def _bb(item):
    """Габарит элемента; для текста - габарит повёрнутой рамки самого текста."""
    if hasattr(item, "GetTextBox"):
        tb = kicadenv.textbox(item)
        p = item.GetPosition()
        w, h = tomm(tb.GetWidth()), tomm(tb.GetHeight())
        a = math.radians(item.GetTextAngleDegrees())
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        wr, hr = w * ca + h * sa, w * sa + h * ca
        cx, cy = tomm(p.x), tomm(p.y)
        return (cx - wr / 2, cy - hr / 2, cx + wr / 2, cy + hr / 2)
    r = item.GetBoundingBox()
    return (tomm(r.GetLeft()), tomm(r.GetTop()), tomm(r.GetRight()), tomm(r.GetBottom()))


def _occupied():
    occ = {l: [] for l in SILK}
    for fp in b.b.GetFootprints():
        for t in (fp.Reference(), fp.Value()):
            if t.IsVisible() and t.GetLayer() in occ:
                occ[t.GetLayer()].append(_bb(t))
        for g in fp.GraphicalItems():
            if g.GetLayer() in occ:
                occ[g.GetLayer()].append(_bb(g))
    for dr in b.b.GetDrawings():
        if dr.GetLayer() in occ:
            occ[dr.GetLayer()].append(_bb(dr))
    # корпуса деталей: под ними шелкография не видна
    for fp in b.b.GetFootprints():
        for lay, sk in ((pcbnew.F_CrtYd, pcbnew.F_SilkS), (pcbnew.B_CrtYd, pcbnew.B_SilkS)):
            poly = fp.GetCourtyard(lay)
            if poly.OutlineCount():
                r = poly.BBox()
                occ[sk].append((tomm(r.GetLeft()), tomm(r.GetTop()),
                                tomm(r.GetRight()), tomm(r.GetBottom())))
    # пады: шелк поверх открытой меди не печатают, считаем их занятыми
    for fp in b.b.GetFootprints():
        for p in fp.Pads():
            ls = set(p.GetLayerSet().Seq())
            for cu, sk in ((pcbnew.F_Cu, pcbnew.F_SilkS), (pcbnew.B_Cu, pcbnew.B_SilkS)):
                if cu in ls:
                    occ[sk].append(_bb(p))
    return occ


def _clash(box, boxes):
    x0, y0, x1, y1 = box
    for a, c, e, f in boxes:
        if x0 - MARGIN < e and a - MARGIN < x1 and y0 - MARGIN < f and c - MARGIN < y1:
            return True
    return False


OCC = _occupied()


def _try(t, cx, cy, ang, hw, hh, lay):
    """Подобрать свободное место для надписи вокруг габарита детали."""
    steps = ((0, -1), (0, 1), (-1, 0), (1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1))
    for dd in (0.75, 1.35, 2.0, 2.8, 3.7, 4.8, 6.0):
        for a_ in (ang, 0.0, 90.0):
            for su, sv in steps:
                px = cx + su * (hw + dd)
                py = cy + sv * (hh + dd)
                t.SetTextAngleDegrees(a_)
                t.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
                box = _bb(t)
                if box[0] < X0 + 0.6 or box[2] > X1 - 0.6 or box[1] < Y0 + 0.6 or box[3] > Y1 - 0.6:
                    continue
                if _clash(box, OCC[lay]):
                    continue
                OCC[lay].append(box)
                return True
    return False


def _geom(ref):
    fp = b.fps[ref]
    back = fp.IsFlipped()
    lay = pcbnew.B_SilkS if back else pcbnew.F_SilkS
    ang = fp.GetOrientationDegrees() % 180.0
    if ang > 90.0:
        ang -= 180.0
    try:
        r = fp.GetBoundingBox(False, False)
    except TypeError:
        r = fp.GetBoundingBox(False)
    hw, hh = tomm(r.GetWidth()) / 2.0, tomm(r.GetHeight()) / 2.0
    cx = (tomm(r.GetLeft()) + tomm(r.GetRight())) / 2.0
    cy = (tomm(r.GetTop()) + tomm(r.GetBottom())) / 2.0
    return fp, back, lay, ang, hw, hh, cx, cy


def fix_ref(ref, size=0.8, thick=0.15):
    """Обозначение: оставить на месте, если чисто, иначе отвести от падов/шелка."""
    fp, back, lay, ang, hw, hh, cx, cy = _geom(ref)
    t = fp.Reference()
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick))
    if ref in REF_AT:
        x_, y_, a_ = REF_AT[ref]
        t.SetTextAngleDegrees(a_)
        t.SetPosition(pcbnew.VECTOR2I(mm(x_), mm(y_)))
        OCC[lay].append(_bb(t))
        return True
    t.SetTextAngleDegrees(ang)
    box = _bb(t)
    if not _clash(box, OCC[lay]):
        OCC[lay].append(box)
        return True
    return _try(t, cx, cy, ang, hw, hh, lay)


def put_value(ref, s, size=0.8, thick=0.15):
    """Номинал рядом с деталью, по возможности вдоль её корпуса."""
    fp, back, lay, ang, hw, hh, cx, cy = _geom(ref)
    if ref in VAL_AT:
        x_, y_, a_ = VAL_AT[ref]
        t = b.text(s, x_, y_, lay, size, thick, a_, mirror=back)
        OCC[lay].append(_bb(t))
        return True
    t = b.text(s, cx, cy, lay, size, thick, ang, mirror=back)
    if _try(t, cx, cy, ang, hw, hh, lay):
        return True
    b.b.Remove(t)
    return False


VALSILK = [("Y1", "25MHz"), ("Y2", "32.768kHz"), ("U2", "AP2112K-3.3")]
VALSILK += [(r_, v) for r_, v in sorted(CAPVAL.items(), key=lambda kv: int(kv[0][1:]))]
VALSILK += [(r_, {"R3": "0R"}.get(r_, RES[r_][0])) for r_ in sorted(RES)]   # на шелке короче, в BOM полное
VALSILK += [("D1", "LED")]
# Развязка под корпусом стоит сеткой 3.2 мм - её номиналам нужен шрифт помельче
DECAP = {"C%d" % i for i in range(1, len(VDDP) + 1)}
REFFIX = [r_ for r_, v in VALSILK] + ["J1", "J2", "J3", "J4", "J5", "J6", "SW1", "SW2", "U1"]
for r_, v in VALSILK:                       # закреплённые вручную - первыми, чтобы их место было занято
    if r_ in VAL_AT:
        put_value(r_, v)
for r_ in REFFIX:
    if r_ in REF_AT:
        fix_ref(r_)
_sz = lambda r_: (0.5, 0.1) if r_ in DECAP else (0.8, 0.15)
_bad = [r_ for r_ in REFFIX if r_ not in REF_AT and not fix_ref(r_, *_sz(r_))]
_skip = [r_ for r_, v in VALSILK if r_ not in VAL_AT and not put_value(r_, v, *_sz(r_))]
print("шелк: номиналов %d (нет места: %s), обозначений не пристроено: %s"
      % (len(VALSILK) - len(_skip), _skip or "-", _bad or "-"))

# --- земляные пады USB-C: полигон цеплял их одной перемычкой вместо двух.
# Для экранируемого разъёма сплошное соединение и электрически лучше.
for _p in b.fps["J1"].Pads():
    if _p.GetNetname() == "GND":
        b.pad_zone_connection(_p, pcbnew.ZONE_CONNECTION_FULL)

# --- шелкография J1 за контуром платы (если что-то всё же вылезло) - убираем
for _g in list(b.fps["J1"].GraphicalItems()):
    if _g.GetLayer() != pcbnew.F_SilkS:
        continue
    if tomm(_g.GetBoundingBox().GetRight()) > X1:
        b.fps["J1"].Remove(_g)

b.set_model("J1", "${KICAD6_3DMODEL_DIR}/Connector_USB.3dshapes/USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal.wrl")

# ------------------------------------------------ своя библиотека футпринтов
# KiCad сравнивает футпринты платы с библиотечными. Системные библиотеки
# отличаются от версии к версии, поэтому кладём свои копии рядом с проектом:
# проект перестаёт зависеть от версии KiCad и от того, что стоит у сборщика.
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
            _c = pcbnew.Cast_to_FOOTPRINT(_fp.Duplicate(False))   # KiCad 10: addToParentGroup
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

# KiCad создаёт .kicad_pro со своими значениями по умолчанию (зазор 0.2 мм).
# Приводим правила проекта к тому, к чему плата реально разведена.
_pro = os.path.join(OUT, NAME + ".kicad_pro")
if os.path.exists(_pro):
    _d = json.load(open(_pro))
    for _c in _d.get("net_settings", {}).get("classes", []):
        if _c.get("name") == "Default":
            _c["track_width"] = W
    _d.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})["min_track_width"] = 0.15
    json.dump(_d, open(_pro, "w"), indent=2)
json.dump({"hdrmap": {"%s.%s" % k: v for k, v in hdrmap.items()},
           "sides": sides, "pads": {str(k): v for k, v in pads.items()},
           "netof": {str(k): mcu_net(k) for k in pads}},
          open(os.path.join(OUT, "_geom.json"), "w"), indent=1)
print("OK ->", OUT)
