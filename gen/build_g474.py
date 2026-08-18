#!/usr/bin/env python3
"""Генератор проекта KiCad: STM32G474RET6 core board (LQFP64), 70x70 мм, 4 слоя."""
import os, sys, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv
import pcbnew
import pcbhelp
from pcbhelp import Builder, mm, tomm, V, FPDIR
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/stm32boards/out/STM32G474RE-CoreBoard"
NAME = "STM32G474RE-CoreBoard"
CX, CY = 150.0, 100.0
BW = BH = 70.0
HD = 22.86
OFFX = 5.0                                 # кристалл левее центра платы
OFFY = 6.0                                 # кристалл ниже центра платы
BCX, BCY = CX + OFFX, CY - OFFY
X0, X1, Y0, Y1 = BCX - BW / 2, BCX + BW / 2, BCY - BH / 2, BCY + BH / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP, WD = 0.15, 0.35, 0.15   # сигнальная / силовая / USB D+D-

MCU_LIBID = "MCU_ST_STM32G4:STM32G474RETx"
MCU_FP = ("Package_QFP", "LQFP-64_10x10mm_P0.5mm")
SPECIAL = {7: "NRST", 5: "HSE_IN", 6: "HSE_OUT", 3: "LSE_IN", 4: "LSE_OUT",
           49: "SWDIO", 50: "SWCLK", 45: "USB_DM", 46: "USB_DP",
           61: "BOOT0", 19: "LED_A", 56: "SWO"}
NO_HEADER = {3, 4, 5, 6}
PWRNET = {"VDD": "+3V3", "VSS": "GND", "VBAT": "+3V3",
          "VDDA": "+3V3A", "VSSA": "GND", "VREF+": "+3V3A"}
PAIRS = [(15, 16), (31, 32), (47, 48), (63, 64)]

sym = kigen.get_symbol(MCU_LIBID)
PINNAME = {int(p.number): p.name for p in sym.pins}
mcu_net = lambda n: PWRNET.get(PINNAME[n]) or SPECIAL.get(n, PINNAME[n])

C0402 = ("Capacitor_SMD", "C_0402_1005Metric")
C0603 = ("Capacitor_SMD", "C_0603_1608Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
R0402 = ("Resistor_SMD", "R_0402_1005Metric")
HDRLIB = "Connector_PinHeader_2.54mm"

b = Builder(layers=4)
u1 = b.place("U1", MCU_FP[0], MCU_FP[1], CX, CY, 0, value="STM32G474RET6")
pads = {int(p.GetNumber()): (tomm(p.GetPosition().x) - CX, tomm(p.GetPosition().y) - CY) for p in u1.Pads()}
sides = {"L": [], "B": [], "R": [], "T": []}
for n, (x, y) in pads.items():
    sides["L" if x < -4.5 else "R" if x > 4.5 else "T" if y < -4.5 else "B"].append(n)
for k in ("L", "R"):
    sides[k].sort(key=lambda n: pads[n][1])
for k in ("T", "B"):
    sides[k].sort(key=lambda n: pads[n][0])

L16 = 15 * 2.54
b.place("J2", HDRLIB, "PinHeader_1x16_P2.54mm_Vertical", CX - HD, CY - L16 / 2, 0, value="PORT_L")
b.place("J4", HDRLIB, "PinHeader_1x16_P2.54mm_Vertical", CX + HD, CY - L16 / 2, 0, value="PORT_R")
b.place("J5", HDRLIB, "PinHeader_1x16_P2.54mm_Vertical", CX - L16 / 2, CY - HD, 90, value="PORT_T")
b.place("J3", HDRLIB, "PinHeader_1x16_P2.54mm_Vertical", CX - L16 / 2, CY + HD, 90, value="PORT_B")
HSIDE = {"L": "J2", "B": "J3", "R": "J4", "T": "J5"}
hdrmap, hdrof = {}, {}
for s, ref in HSIDE.items():
    hp = [(int(p.GetNumber()), tomm(p.GetPosition().x), tomm(p.GetPosition().y)) for p in b.fps[ref].Pads()]
    hp.sort(key=(lambda t: t[2]) if s in ("L", "R") else (lambda t: t[1]))
    for (hn, hx, hy), mn in zip(hp, sides[s]):
        hdrmap[(ref, hn)] = mn
        hdrof[mn] = (ref, hn, hx, hy, s)

# ------------------------------------------------------------ размещение
# USB-C: верхний правый угол, разъём смотрит за верхний край
UCY = (hdrof[45][3] + hdrof[46][3]) / 2 + 5.0
b.place("J1", "Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", X1 - 3.65, UCY, 90, value="USB-C")
TOPY = Y0 + 6.2
JY = Y0 + 9.6                       # ряд отладочного разъёма
b.place("J6", HDRLIB, "PinHeader_1x10_P2.54mm_Vertical", X1 - 5.6, JY, 270, value="DEBUG")
b.place("SW2", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", BCX - 3.5, TOPY, 180, value="BOOT0")
b.place("SW1", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", BCX - 15.0, TOPY, 180, value="RESET")
b.place("D1", "LED_SMD", "LED_0805_2012Metric", BCX - 26.6, TOPY, 0, value="LED")
b.place("R5", R0402[0], R0402[1], BCX - 23.7, TOPY, 0, value="1k")
b.place("R4", R0402[0], R0402[1], BCX + 0.0, TOPY + 5.6, 0, value="10k")

# обратная сторона: питание в правом кольце
b.place("U2", "Package_TO_SOT_SMD", "SOT-23-5", X1 - 5.0, UCY + 13.0, 0, back=True, value="AP2112K-3.3")
b.place("C7", C0805[0], C0805[1], X1 - 5.0, UCY + 17.2, 0, back=True, value="10uF")
b.place("C8", C0805[0], C0805[1], X1 - 5.0, UCY + 20.7, 0, back=True, value="10uF")
b.place("C6", C0603[0], C0603[1], X1 - 5.0, UCY + 24.2, 0, back=True, value="100nF")
b.place("R1", R0402[0], R0402[1], X1 - 3.4, UCY - 1.25, 0, back=True, value="5.1k")
b.place("R2", R0402[0], R0402[1], X1 - 3.4, UCY + 1.25, 0, back=True, value="5.1k")

# обратная сторона: кварцы вплотную к корпусу
XVX = CX - HD + 4.0                      # линия via для кварцевых цепей
XHY = {n: hdrof[n][3] for n in (3, 4, 5, 6)}
b.place("Y1", "Crystal", "Crystal_SMD_5032-2Pin_5.0x3.2mm", XVX + 6.0, (XHY[5] + XHY[6]) / 2, 270, back=True, value="8MHz")
b.place("C13", C0402[0], C0402[1], XVX + 12.0, XHY[5], 0, back=True, value="12pF")
b.place("C14", C0402[0], C0402[1], XVX + 12.0, XHY[6], 0, back=True, value="12pF")
b.place("Y2", "Crystal", "Crystal_SMD_MicroCrystal_CC7V-T1A-2Pin_3.2x1.5mm", XVX + 6.0, (XHY[3] + XHY[4]) / 2 - 1.2, 270, back=True, value="32.768kHz")
b.place("C15", C0402[0], C0402[1], XVX + 12.0, XHY[3], 0, back=True, value="6.8pF")
b.place("C16", C0402[0], C0402[1], XVX + 12.0, XHY[4], 0, back=True, value="6.8pF")

# обратная сторона: VDDA/VREF в диагональном "окне" между веерами
b.place("R3", R0402[0], R0402[1], CX + 11.2, CY + 11.2, 135, back=True, value="0R/FB")
b.place("C9", C0402[0], C0402[1], CX + 13.8, CY + 13.8, -45, back=True, value="100nF")
b.place("C10", C0603[0], C0603[1], CX + 16.6, CY + 16.6, -45, back=True, value="1uF")
b.place("C5", C0805[0], C0805[1], CX - 12.0, CY + 12.0, 225, back=True, value="4.7uF")
b.place("C17", C0402[0], C0402[1], X0 + 4.2, CY - 7.0, 180, back=True, value="100nF")
CORN = {(15, 16): (-7.9, 7.9), (31, 32): (7.9, 7.9), (47, 48): (7.9, -7.9), (63, 64): (-7.9, -7.9)}
for i, pr in enumerate(PAIRS, 1):
    dx, dy = CORN[pr]
    b.place("C%d" % i, C0402[0], C0402[1], CX + dx, CY + dy, 45 if dx * dy < 0 else -45, back=True, value="100nF")

HN = 0
for hx, hy in ((X0 + 3.0, Y0 + 3.0), (X0 + 3.0, Y1 - 3.0), (X1 - 3.5, Y1 - 3.5), (X1 - 3.5, Y0 + 3.5)):
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, "MountingHole.pretty"), "MountingHole_2.2mm_M2")
    b.b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(hx), mm(hy)))
    HN += 1
    fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_2.2mm_M2"))
    fp.SetReference("H%d" % HN)
    fp.SetValue("M2")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)

# ------------------------------------------------------------ схема
d = kigen.Design(NAME, "STM32G474RET6 core board (LQFP64) - 70x70 mm, 4 layers")
d.prepare()
d.add(kigen.Part("U1", MCU_LIBID, "STM32G474RET6", "%s:%s" % MCU_FP,
                 {str(n): mcu_net(n) for n in sorted(pads)}, at=(70, 110)))
for s, ref in HSIDE.items():
    nets = {str(hn): mcu_net(mn) for (r, hn), mn in hdrmap.items() if r == ref and mn not in NO_HEADER}
    d.add(kigen.Part(ref, "Connector_Generic:Conn_01x16",
                     {"J2": "PORT_L", "J3": "PORT_B", "J4": "PORT_R", "J5": "PORT_T"}[ref],
                     "%s:PinHeader_1x16_P2.54mm_Vertical" % HDRLIB, nets,
                     at=({"J2": 150, "J3": 185, "J4": 220, "J5": 255}[ref], 60)))
USBC_LIBID = "Connector:USB_C_Receptacle_USB2.0_16P"
SHIELD = [p.number for p in kigen.get_symbol(USBC_LIBID).pins if p.name == "SHIELD"][0]  # S1 в KiCad 7, SH в KiCad 10
d.add(kigen.Part("J1", USBC_LIBID, "USB-C",
                 "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                 {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
                  "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
                  "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
                  "A7": "USB_DM", "B7": "USB_DM", SHIELD: "GND"}, at=(300, 60)))
d.add(kigen.Part("J6", "Connector_Generic:Conn_01x10", "DEBUG",
                 "%s:PinHeader_1x10_P2.54mm_Vertical" % HDRLIB,
                 {"1": "VBUS", "2": "GND", "3": "PB6", "4": "PB7", "5": "NRST",
                  "6": "SWO", "7": "GND", "8": "SWCLK", "9": "SWDIO", "10": "+3V3"}, at=(300, 120)))
d.add(kigen.Part("U2", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
                 {"1": "VBUS", "2": "GND", "3": "VBUS", "5": "+3V3"}, at=(378, 62)))
d.add(kigen.Part("Y1", "Device:Crystal", "8MHz", "Crystal:Crystal_SMD_5032-2Pin_5.0x3.2mm",
                 {"1": "HSE_IN", "2": "HSE_OUT"}, at=(345, 95)))
d.add(kigen.Part("Y2", "Device:Crystal", "32.768kHz",
                 "Crystal:Crystal_SMD_MicroCrystal_CC7V-T1A-2Pin_3.2x1.5mm",
                 {"1": "LSE_IN", "2": "LSE_OUT"}, at=(345, 125)))
d.add(kigen.Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "NRST", "2": "GND"}, at=(345, 150)))
d.add(kigen.Part("SW2", "Switch:SW_Push", "BOOT0", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "BOOT0", "2": "+3V3"}, at=(345, 175)))
d.add(kigen.Part("D1", "Device:LED", "LED", "LED_SMD:LED_0805_2012Metric",
                 {"1": "LED_K", "2": "LED_A"}, at=(345, 200)))
CAPNET = {"C1": ("+3V3", "GND"), "C2": ("+3V3", "GND"), "C3": ("+3V3", "GND"),
          "C4": ("+3V3", "GND"), "C5": ("+3V3", "GND"), "C6": ("+3V3", "GND"),
          "C7": ("VBUS", "GND"), "C8": ("+3V3", "GND"), "C9": ("+3V3A", "GND"),
          "C10": ("+3V3A", "GND"),           "C13": ("HSE_IN", "GND"), "C14": ("HSE_OUT", "GND"),
          "C15": ("LSE_IN", "GND"), "C16": ("LSE_OUT", "GND"), "C17": ("NRST", "GND")}
CAPVAL = {"C1": "100nF", "C2": "100nF", "C3": "100nF", "C4": "100nF", "C5": "4.7uF",
          "C6": "100nF", "C7": "10uF", "C8": "10uF", "C9": "100nF", "C10": "1uF",
          "C13": "12pF", "C14": "12pF",
          "C15": "6.8pF", "C16": "6.8pF", "C17": "100nF"}
FPOF = {}
for ref in CAPNET:
    fp = b.fps[ref]
    FPOF[ref] = str(fp.GetFPID().GetLibNickname()) + ":" + str(fp.GetFPID().GetLibItemName())
for i, ref in enumerate(sorted(CAPNET, key=lambda r: int(r[1:]))):
    a, k = CAPNET[ref]
    d.add(kigen.Part(ref, "Device:C", CAPVAL[ref], FPOF[ref], {"1": a, "2": k},
                     at=(412 + 52 * (i // 8), 72 + 36 * (i % 8))))
RES = {"R1": ("5.1k", ("CC1", "GND")), "R2": ("5.1k", ("CC2", "GND")),
       "R3": ("0R/FB", ("+3V3", "+3V3A")), "R4": ("10k", ("BOOT0", "GND")),
       "R5": ("1k", ("LED_K", "GND"))}
for i, ref in enumerate(sorted(RES)):
    val, (a, k) = RES[ref]
    d.add(kigen.Part(ref, "Device:R", val, "%s:%s" % R0402, {"1": a, "2": k}, at=(534, 72 + 36 * i)))
for i in range(1, 5):
    d.add(kigen.Part("H%d" % i, "Mechanical:MountingHole", "M2",
                     "MountingHole:MountingHole_2.2mm_M2", {}, at=(560, 70 + 20 * i)))
for i, n in enumerate(["GND", "+3V3", "VBUS"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(534, 340 + 22 * i)))

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

# ============================================================== разводка
INNER = {}
padpt = lambda n: (CX + pads[n][0], CY + pads[n][1])


def inward(n, dist):
    x, y = pads[n]
    if abs(x) > abs(y):
        return (CX + x - math.copysign(dist, x), CY + y)
    return (CX + x, CY + y - math.copysign(dist, y))


def stub(ref, pin, net, dist=1.4, width=W, sgn=None):
    """Отвод пада на переходное отверстие. GND не разводим - его берёт полигон на этом же слое."""
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


# питание МК -> внутрь корпуса -> via в полигоны
def _away(n, other, d=0.35):
    """Единичный сдвиг от вывода other к выводу n (чтобы via земли ушла от дорожки питания)."""
    dx, dy = pads[n][0] - pads[other][0], pads[n][1] - pads[other][1]
    L = math.hypot(dx, dy) or 1.0
    return dx / L * d, dy / L * d


for vss, vdd in PAIRS:
    for n, net, dist in ((vss, "GND", 1.8), (vdd, "+3V3", 3.0)):
        p, v = padpt(n), inward(n, dist)
        if net == "GND":
            ox, oy = _away(vss, vdd)
            k = inward(n, 0.95)
            v = (v[0] + ox, v[1] + oy)
            b.track(net, [p, k, v], FCU, 0.15)
        else:
            b.track(net, [p, v], FCU, 0.15)
        b.via(net, *v, dia=0.5, drill=0.25)
        INNER[n] = v
for n, net, dist in ((27, "GND", 1.8), (29, "+3V3A", 3.0), (28, "+3V3A", 4.2), (1, "+3V3", 1.35)):
    p, v = padpt(n), inward(n, dist)
    if n == 27:
        ox, oy = _away(27, 28)
        k = inward(n, 0.95)
        v = (v[0] + ox, v[1] + oy)
        b.track(net, [p, k, v], FCU, 0.15)
    else:
        b.track(net, [p, v], FCU, 0.15)
    b.via(net, *v, dia=0.5, drill=0.25)
    INNER[n] = v

# развязка по углам корпуса (обратная сторона): +3V3 на своё via, GND - через полигон
V3 = {}
for i in range(1, 5):
    V3["C%d" % i] = stub("C%d" % i, 1, "+3V3", 1.2, sgn=(-1.0 if i == 2 else 1.0))

# кварцевые выводы: тот же веер, но обрыв на via перед гребёнкой
XV = {}
for n in (3, 4, 5, 6):
    px, py = padpt(n)
    hy = hdrof[n][3]
    b.track(mcu_net(n), [(px, py), (px - 1.2, py), (XVX, hy)], FCU, 0.18)
    b.via(mcu_net(n), XVX, hy, dia=0.5, drill=0.25)
    XV[n] = (XVX, hy)

# сигнальный веер по верхнему слою
SD = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}
for mn, (ref, hn, hx, hy, s_) in hdrof.items():
    if mn in NO_HEADER or mcu_net(mn) in ("+3V3", "GND"):
        continue
    sx, sy = SD[s_]
    px, py = padpt(mn)
    a = (px + sx * 1.2, py) if sx else (px, py + sy * 1.2)
    c = (hx - sx * 2.4, hy) if sx else (hx, hy - sy * 2.4)
    b.track(mcu_net(mn), [(px, py), a, c, (hx, hy)], FCU, W)

hxy = lambda mn: (hdrof[mn][2], hdrof[mn][3])

# --- кварцы (обратная сторона; GND падов - через полигон B.Cu)
for xtal, pins, caps in (("Y1", (5, 6), ("C13", "C14")), ("Y2", (3, 4), ("C15", "C16"))):
    for k, (mpin, cap) in enumerate(zip(pins, caps)):
        xp = b.padxy(xtal, k + 1)
        fp = b.fps[cap]
        fp.SetPosition(pcbnew.VECTOR2I(mm(tomm(fp.GetPosition().x)), mm(xp[1])))
        cp = b.padxy(cap, 1)
        b.track(mcu_net(mpin), [XV[mpin], xp], BCU, 0.18)
        b.track(mcu_net(mpin), [xp, cp], BCU, 0.18)

# --- VDDA / VREF+ : цепочка вдоль диагонали, питание берём с via конденсатора C2
b.track("+3V3A", [INNER[29], (CX + 2.6, CY + 9.4), (CX + 6.4, CY + 9.4), b.padxy("R3", 2)], BCU, W)
b.track("+3V3A", [INNER[28], INNER[29]], BCU, W)
stub("R3", 1, "+3V3", 1.4, sgn=-1.0)
PP = (0.707, -0.707)                     # нормаль к диагонали
def diag(a, c, off=1.3):
    return [a, (a[0] + PP[0] * off, a[1] + PP[1] * off),
            (c[0] + PP[0] * off, c[1] + PP[1] * off), c]
b.track("+3V3A", diag(b.padxy("R3", 2), b.padxy("C9", 1)), BCU, W)
b.track("+3V3A", diag(b.padxy("C9", 1), b.padxy("C10", 1)), BCU, W)
stub("C5", 1, "+3V3", 1.4, WP)

# --- USB-C (правое ребро) -> LDO
UX = b.padxy("J1", "A4")[0]
PY_ = lambda p_: round(b.padxy("J1", p_)[1], 3)
XVBUS = UX - 6.3                        # GND падам via не нужен: полигон F.Cu
YL0 = max(PY_("A9"), PY_("A4"))
b.track("VBUS", [(UX, YL0), (XVBUS, YL0)], FCU, WP)
b.via("VBUS", XVBUS, YL0, dia=0.6, drill=0.3)
# верхний пад VBUS уводим отдельной колонкой, чтобы не пересечь D+/D-
YU, YL = sorted((PY_("A9"), PY_("A4")))
XU = UX - 0.85
b.track("VBUS", [(UX, YU), (XU, YU)], FCU, WP)
b.via("VBUS", XU, YU, dia=0.6, drill=0.3)
b.track("VBUS", [(XU, YU), (XU, YL + 1.4), (XVBUS, YL + 1.4), (XVBUS, YL)], BCU, WP)
u1p, u3p = b.padxy("U2", 1), b.padxy("U2", 3)
YJ = u1p[1] - 2.8
b.track("VBUS", [(XVBUS, YL0), (XVBUS, u1p[1]), u1p], BCU, WP)
b.track("VBUS", [u1p, (u1p[0] - 1.9, u1p[1]), (u3p[0] - 1.9, u3p[1]), u3p], BCU, WP)
c7p = b.padxy("C7", 1)
b.track("VBUS", [(XVBUS, u1p[1]), (XVBUS, c7p[1]), c7p], BCU, WP)
stub("U2", 5, "+3V3", 1.8)
stub("C8", 1, "+3V3", 1.5)
stub("C6", 1, "+3V3", 1.5)
# CC-резисторы вплотную к падам разъёма (обратная сторона)
for p_, net, r in (("A5", "CC1", "R1"), ("B5", "CC2", "R2")):
    y = PY_(p_)
    fp = b.fps[r]
    fp.SetPosition(pcbnew.VECTOR2I(mm(tomm(fp.GetPosition().x)), mm(y)))
    b.track(net, [(UX, y), (UX + 1.2, y)], FCU, W)
    b.via(net, UX + 1.2, y, dia=0.5, drill=0.25)
    b.track(net, [(UX + 1.2, y), b.padxy(r, 1)], BCU, W)
# D+/D-
DPY_ = sorted({PY_("A6"), PY_("B6")})
DMY_ = sorted({PY_("A7"), PY_("B7")})
LDM, LDP = UX - 4.3, UX - 2.3
for y in DMY_:
    b.track("USB_DM", [(UX, y), (LDM, y)], FCU, WD)
    b.via("USB_DM", LDM, y, dia=0.45, drill=0.25)
b.track("USB_DM", [(LDM, DMY_[0]), (LDM, DMY_[1])], BCU, WD)
for y in DPY_:
    b.track("USB_DP", [(UX, y), (LDP, y)], FCU, WD)
    b.via("USB_DP", LDP, y, dia=0.45, drill=0.25)
b.track("USB_DP", [(LDP, DPY_[0]), (LDP, DPY_[1])], BCU, WD)
hx, hy = hxy(46)
b.track("USB_DP", [(LDP, DPY_[0]), (LDP, hy), (hx, hy)], BCU, WD)
hx, hy = hxy(45)
b.track("USB_DM", [(LDM, DMY_[1]), (LDM - 0.6, DMY_[1] + 1.0), (LDM - 0.6, hy), (hx, hy)], BCU, WD)

# --- отладочный разъём 1x10 (порядок как у WeAct MiniDebugger)
j = lambda n: b.padxy("J6", n)
JD = JY + 1.5                       # линия via сразу под разъёмом
LOW1, LOW2 = CY - 20.4, CY - 21.6   # полосы B.Cu между верхней и боковыми гребёнками
stub("J6", 10, "+3V3", 1.8)
# 5 В отладчика -> VBUS
b.track("VBUS", [j(1), (j(1)[0], JD)], FCU, WP)
b.via("VBUS", j(1)[0], JD, dia=0.6, drill=0.3)
VBX = X1 - 1.4
b.track("VBUS", [(j(1)[0], JD), (VBX, JD + 1.4), (VBX, YL0 + 4.0), (XVBUS, YL0 + 4.0), (XVBUS, YL0)], BCU, WP)
# SWCLK - коротким крюком по верхнему слою прямо на свой пад гребёнки
b.track("SWCLK", [j(8), (j(8)[0], JD), (hxy(50)[0], JD), hxy(50)], FCU, W)
# NRST, SWO и UART: короткий спуск по верхнему слою -> своя полоса B.Cu -> вверх к гребёнке
NRX = 130.95 + 1.27 + 2.54          # середина зазора между падами J5


def dbg_route(pin, net, lane, tx, ty):
    px = j(pin)[0]
    b.track(net, [j(pin), (px, lane)], FCU, W)
    b.via(net, px, lane, dia=0.5, drill=0.25)
    b.track(net, [(px, lane), (tx, lane)], BCU, W)
    b.via(net, tx, lane, dia=0.5, drill=0.25)
    b.track(net, [(tx, lane), (tx, ty)], FCU, W)


dbg_route(9, "SWDIO", JY + 2.3, hxy(49)[0], hxy(49)[1])
dbg_route(6, "SWO", JY + 3.0, hxy(56)[0], hxy(56)[1])
dbg_route(5, "NRST", JY + 3.7, NRX, TOPY + 1.85)
dbg_route(4, mcu_net(60), JY + 4.4, hxy(60)[0], hxy(60)[1])
dbg_route(3, mcu_net(59), JY + 5.1, hxy(59)[0], hxy(59)[1])

# --- кнопки / светодиод (все в верхнем кольце)
def dup_pad(ref, num, rightmost=True):
    pp = [(tomm(q.GetPosition().x), tomm(q.GetPosition().y)) for q in b.fps[ref].Pads() if q.GetNumber() == str(num)]
    pp.sort()
    return pp[-1] if rightmost else pp[0]


for sw in ("SW1", "SW2"):
    c = tomm(b.fps[sw].GetPosition().y)
    for pn in ("1", "2"):
        pp = [(tomm(q.GetPosition().x), tomm(q.GetPosition().y)) for q in b.fps[sw].Pads() if q.GetNumber() == pn]
        if len(pp) == 2:
            net = b.fps[sw].FindPadByNumber(pn).GetNetname()
            off = 1.6 if pp[0][1] > c else -1.6
            b.track(net, [pp[0], (pp[0][0], pp[0][1] + off),
                          (pp[1][0], pp[1][1] + off), pp[1]], FCU, W)

LANE_N = X0 + 5.4                      # полоса NRST по левому кольцу
LANE_L = X0 + 1.6                      # полоса LED_A по нижнему слою
LB, LN, LL = TOPY + 4.4, TOPY + 6.0, TOPY + 1.0

bl = dup_pad("SW2", 1, False)
br = dup_pad("SW2", 1, True)
b.track("BOOT0", [bl, (bl[0], LB), (hxy(61)[0], LB), hxy(61)], FCU, W)
r4p = b.padxy("R4", 1)
b.track("BOOT0", [br, (r4p[0], br[1]), r4p], FCU, W)
stub("R4", 2, "GND", 1.3)
sx, sy = dup_pad("SW2", 2, True)
d2 = 1.6 if sy > tomm(b.fps["SW2"].GetPosition().y) else -1.6
b.track("+3V3", [(sx, sy), (sx, sy + d2)], FCU, W)
b.via("+3V3", sx, sy + d2, dia=0.6, drill=0.3)

nx, ny = dup_pad("SW1", 1, False)
b.track("NRST", [(nx, ny), (LANE_N, ny), (LANE_N, hxy(7)[1]), hxy(7)], FCU, W)
b.track("NRST", [(NRX, TOPY + 1.85), (nx, ny)], FCU, W)
b.track("NRST", [(LANE_N, CY - 7.0), b.padxy("C17", 1)], BCU, W)
b.via("NRST", LANE_N, CY - 7.0, dia=0.6, drill=0.3)
sx, sy = dup_pad("SW1", 2, True)
d1 = 1.6 if sy > tomm(b.fps["SW1"].GetPosition().y) else -1.6
b.track("GND", [(sx, sy), (sx, sy + d1)], FCU, W)

dp = b.padxy("D1", 2)
b.track("LED_A", [dp, (dp[0], LL)], FCU, W)
b.via("LED_A", dp[0], LL, dia=0.6, drill=0.3)
b.track("LED_A", [(dp[0], LL), (LANE_L, LL), (LANE_L, Y1 - 4.6),
                  (hxy(19)[0], Y1 - 4.6), hxy(19)], BCU, W)
b.track("LED_K", [b.padxy("D1", 1), (b.padxy("D1", 1)[0] - 1.2, b.padxy("D1", 1)[1] - 1.8),
                  (b.padxy("R5", 1)[0], b.padxy("R5", 1)[1] - 1.8), b.padxy("R5", 1)], FCU, W)
stub("R5", 2, "GND", 1.2)

# ------------------------------------------------------------ контур, полигоны, шелк
b.edge_rect(BCX, BCY, BW, BH, 3.0)
b.zone("GND", pcbnew.In1_Cu, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("+3V3", pcbnew.In2_Cu, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("GND", FCU, BCX, BCY, BW - 0.8, BH - 0.8)
b.zone("GND", BCU, BCX, BCY, BW - 0.8, BH - 0.8)
# индивидуальные поправки подписей гребёнок, мм: (ref, пин) -> (dx, dy)
LBL_ADJ = {
    ("J4", 1): (6.6, 0.0),      # +3V3 - на правую сторону J4, иначе налезает на SWDIO с J5
    ("J4", 3): (-1.9, 0.0),     # USB_DP - отодвинуть от корпуса разъёма
    ("J4", 4): (-1.9, 0.0),     # USB_DM
    ("J2", 16): (-0.37, 0.02),   # +3V3 - как сдвинуто вручную
    ("J3", 3): (0.0, 0.7),      # LED_A - длинная подпись, отвести от падов
    ("J3", 12): (0.0, 0.7),     # +3V3A
    ("J3", 13): (0.0, 0.7),     # +3V3A
}
for mn, (ref, hn, hx, hy, s_) in hdrof.items():
    lbl = "NC" if mn in NO_HEADER else mcu_net(mn)
    dx, dy, rot = {"L": (-3.3, 0, 0), "R": (-3.3, 0, 0), "T": (0, 3.4, 90), "B": (0, 3.2, 90)}[s_]
    ax, ay = LBL_ADJ.get((ref, hn), (0.0, 0.0))
    b.text(lbl, hx + dx + ax, hy + dy + ay, pcbnew.F_SilkS, 0.8, 0.15, rot)
b.text("STM32G474RET6 CORE BOARD", 149.31, 116.27, pcbnew.F_SilkS, 1.3, 0.24)
b.text("70x70 mm | 4 layer | rev.A", 185.4, 110.58, pcbnew.F_SilkS, 1.0, 0.18, 90)
b.text("ASTechLab", 179.61, 113.68, pcbnew.F_SilkS, 3.0, 1.0, 90)

# --- подписи кнопок и разъёма прошивки
sw1x = tomm(b.fps["SW1"].GetPosition().x)
sw2x = tomm(b.fps["SW2"].GetPosition().x)
b.text("RST", sw1x - 5.6, TOPY, pcbnew.F_SilkS, 1.6, 0.28, 90)
b.text("BOOT", sw2x + 5.6, TOPY, pcbnew.F_SilkS, 1.6, 0.28, 270)
SWDLBL = {1: "5V", 2: "GND", 3: "RX", 4: "TX", 5: "RST",
          6: "SWO", 7: "GND", 8: "CLK", 9: "DIO", 10: "3V3"}
for pin, lbl in SWDLBL.items():
    px, py = b.padxy("J6", pin)
    b.text(lbl, px, py - 3.2, pcbnew.F_SilkS, 0.8, 0.15, 90)
b.text("DEBUG (SWD/SWO/UART)", (b.padxy("J6", 1)[0] + b.padxy("J6", 10)[0]) / 2,
       b.padxy("J6", 1)[1] - 6.3, pcbnew.F_SilkS, 1.1, 0.2, 0)

# --------------------------------------------- номиналы деталей на шелкографии
# Ставим значение рядом с деталью, перебирая позиции вокруг неё и пропуская те,
# где уже что-то нарисовано на том же слое шелка (или где мы выходим за плату).
SILK = (pcbnew.F_SilkS, pcbnew.B_SilkS)
MARGIN = 0.3


def _bb(item):
    """Габарит элемента; для текста - габарит повёрнутой рамки самого текста."""
    if hasattr(item, "GetTextBox"):
        tb = kicadenv.textbox(item)
        p = item.GetPosition()
        w, h = tomm(tb.GetWidth()), tomm(tb.GetHeight())
        a = math.radians(item.GetTextAngleDegrees())
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        W, H = w * ca + h * sa, w * sa + h * ca
        cx, cy = tomm(p.x), tomm(p.y)
        return (cx - W / 2, cy - H / 2, cx + W / 2, cy + H / 2)
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
    for d in b.b.GetDrawings():
        if d.GetLayer() in occ:
            occ[d.GetLayer()].append(_bb(d))
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


# позиции шелкографии, выставленные вручную в KiCad (абсолютные мм, угол)
REF_AT = {
    "J4": (176.030, 100.000, 0),    # как J2: середина ряда, со стороны, свободной от подписей
    "J3": (150.000, 119.690, 90),   # как J5: середина ряда, с внутренней стороны
    "U2": (188.020, 105.040, 270),
    "SW1": (140.000, 61.600, 0),
    "SW2": (151.500, 61.600, 0),
    "D1": (128.360, 63.410, 0),
    "Y1": (137.120, 96.380, 0),
    "Y2": (137.170, 83.330, 0),
    "R1": (184.890, 93.550, 90),
    "R2": (184.930, 90.460, 90),
    "R3": (161.990, 109.760, -45),
    "R4": (153.250, 70.840, 90),
    "R5": (131.280, 63.850, 0),
    "C1": (143.710, 106.810, 135),
    "C2": (159.490, 105.620, 135),
    "C3": (156.450, 93.670, 135),
    "C4": (140.700, 91.070, 45),
    "C5": (139.870, 110.320, 135),
    "C6": (187.255, 116.500, 90),
    "C7": (187.840, 109.500, 90),
    "C8": (187.780, 113.000, 270),
    "C9": (162.620, 114.950, 135),
    "C10": (168.260, 115.140, 135),
    "C13": (143.280, 89.200, 180),
    "C14": (145.000, 94.310, 90),
    "C15": (144.840, 84.240, 90),
    "C16": (144.960, 87.170, 90),
    "C17": (123.580, 91.500, 180),
}

VAL_AT = {
    "Y1": (133.980, 92.720, 90),   # 3.2 мм от детали
    "Y2": (134.050, 85.900, 90),   # 3.1 мм от детали
    "U2": (184.360, 102.340, 0),   # 3.0 мм от детали
    "D1": (128.160, 67.280, 180),   # 2.1 мм от детали
    "C1": (140.980, 107.070, 45),   # 1.4 мм от детали
    "C2": (156.990, 108.940, 135),   # 1.4 мм от детали
    "C3": (156.600, 90.930, 45),   # 1.8 мм от детали
    "C4": (140.630, 92.940, 135),   # 1.7 мм от детали
    "C5": (135.670, 111.340, 45),   # 2.4 мм от детали
    "C6": (182.150, 117.300, 90),   # 3.0 мм от детали
    "C7": (182.070, 109.470, 90),   # 2.9 мм от детали
    "C8": (182.020, 113.110, 90),   # 3.0 мм от детали
    "C9": (164.800, 112.400, -45),   # 1.7 мм от детали
    "C10": (165.370, 117.840, 135),   # 1.8 мм от детали
    "C13": (144.870, 90.910, 90),   # 1.8 мм от детали
    "C14": (142.680, 95.520, 0),   # 1.4 мм от детали
    "C15": (141.620, 83.710, 45),   # 1.9 мм от детали
    "C16": (141.280, 87.310, 90),   # 1.9 мм от детали
    "C17": (123.420, 95.920, 90),   # 3.0 мм от детали
    "R1": (188.390, 93.690, 90),   # 1.8 мм от детали
    "R2": (188.400, 90.640, 90),   # 1.8 мм от детали
    "R3": (159.500, 112.880, 135),   # 2.4 мм от детали
    "R4": (156.770, 70.840, 270),   # 1.8 мм от детали
    "R5": (131.280, 66.410, 180),   # 1.2 мм от детали
}


def _try(t, cx, cy, ang, hw, hh, lay):
    """Подобрать свободное место для надписи вокруг габарита детали."""
    steps = ((0, -1), (0, 1), (-1, 0), (1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1))
    for d in (0.75, 1.35, 2.0, 2.8, 3.7, 4.8, 6.0):
        for a_ in (ang, 0.0, 90.0):
            for su, sv in steps:
                px = cx + su * (hw + d)
                py = cy + sv * (hh + d)
                t.SetTextAngleDegrees(a_)
                t.SetPosition(V(px, py))
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
        t.SetPosition(V(x_, y_))
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


VALSILK = [("Y1", "8MHz"), ("Y2", "32.768kHz"), ("U2", "AP2112K-3.3")]
VALSILK += [(r_, v) for r_, v in sorted(CAPVAL.items(), key=lambda kv: int(kv[0][1:]))]
VALSILK += [(r_, {"R3": "0R"}.get(r_, RES[r_][0])) for r_ in sorted(RES)]   # на шелке короче, в BOM полное
VALSILK += [("D1", "LED")]
REFFIX = [r_ for r_, v in VALSILK] + ["J1", "J2", "J3", "J4", "J5", "J6", "SW1", "SW2", "U1"]
for r_, v in VALSILK:                       # закреплённые вручную - первыми, чтобы их место было занято
    if r_ in VAL_AT:
        put_value(r_, v)
for r_ in REFFIX:
    if r_ in REF_AT:
        fix_ref(r_)
_bad = [r_ for r_ in REFFIX if r_ not in REF_AT and not fix_ref(r_)]
_skip = [r_ for r_, v in VALSILK if r_ not in VAL_AT and not put_value(r_, v)]
print("шелк: номиналов %d (нет места: %s), обозначений не пристроено: %s"
      % (len(VALSILK) - len(_skip), _skip or "-", _bad or "-"))

# --- земляные пады USB-C: полигон цеплял их одной перемычкой вместо двух.
# Для экранируемого разъёма сплошное соединение и электрически лучше.
for _p in b.fps["J1"].Pads():
    if _p.GetNetname() == "GND":
        b.pad_zone_connection(_p, pcbnew.ZONE_CONNECTION_FULL)

# --- шелкография J1 выходит за контур платы (разъём намеренно свисает за край) - убираем
_keep = []
for _g in list(b.fps["J1"].GraphicalItems()):
    if _g.GetLayer() != pcbnew.F_SilkS:
        continue
    r = _g.GetBoundingBox()
    if tomm(r.GetRight()) > X1 - 0.25:
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
