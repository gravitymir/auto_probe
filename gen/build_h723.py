#!/usr/bin/env python3
"""Генератор проекта KiCad: STM32H723ZGT6 core board (LQFP144), 84x84 мм, 4 слоя."""
import os, sys, math, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from pcbhelp import Builder, mm, tomm
import kigen

OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/stm32boards/out/STM32H723ZG-CoreBoard"
NAME = "STM32H723ZG-CoreBoard"
CX, CY = 150.0, 100.0
BW = BH = 84.0
HDI, HDO = 26.0, 28.54                     # внутренний / внешний ряд гребёнки
X0, X1, Y0, Y1 = CX - BW / 2, CX + BW / 2, CY - BH / 2, CY + BH / 2
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
W, WP = 0.2, 0.35

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
b.place("J1", "Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", X1 - 3.65, UCY, 90, value="USB-C")
b.place("J6", HDRLIB, "PinHeader_1x04_P2.54mm_Vertical", X1 - 19.0, Y0 + 6.8, 90, value="SWD")
b.place("SW2", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", X0 + 12.5, Y0 + 7.3, 0, value="BOOT0")
b.place("SW1", "Button_Switch_SMD", "SW_SPST_SKQG_WithoutStem", X0 + 13.0, Y1 - 7.5, 0, value="RESET")
b.place("D1", "LED_SMD", "LED_0805_2012Metric", CX - 16.0, Y1 - 4.5, 0, value="USER")
b.place("R5", R0402[0], R0402[1], CX - 12.5, Y1 - 4.5, 0, value="1k")
b.place("R4", R0402[0], R0402[1], X0 + 20.0, Y0 + 3.4, 0, value="10k")
b.place("U2", "Package_TO_SOT_SMD", "SOT-23-5", X1 - 5.0, UCY + 14.0, 0, back=True, value="AP2112K-3.3")
b.place("C50", C0805[0], C0805[1], X1 - 5.0, UCY + 18.0, 0, back=True, value="10uF")
b.place("C51", C0805[0], C0805[1], X1 - 5.0, UCY + 21.5, 0, back=True, value="10uF")
b.place("C52", C0603[0], C0603[1], X1 - 5.0, UCY + 25.0, 0, back=True, value="100nF")
b.place("R1", R0402[0], R0402[1], X1 - 1.05, UCY - 1.25, 0, back=True, value="5.1k")
b.place("R2", R0402[0], R0402[1], X1 - 1.05, UCY + 1.25, 0, back=True, value="5.1k")

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
b.place("C77", C0402[0], C0402[1], X0 + 2.8, CY + 16.0, 180, back=True, value="100nF")     # NRST

VDDP = sorted([n for n in pads if RAWNAME[n] == "VDD"])
for i, n in enumerate(VDDP, 1):
    b.place("C%d" % i, C0402[0], C0402[1], CX, CY, 0, back=True, value="100nF")

HN = 0
for hx, hy in ((X0 + 3.5, Y0 + 3.5), (X0 + 3.5, Y1 - 3.5), (X1 - 3.5, Y1 - 3.5), (X1 - 3.5, Y0 + 3.5)):
    fp = pcbnew.FootprintLoad("/usr/share/kicad/footprints/MountingHole.pretty", "MountingHole_2.2mm_M2")
    b.b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(hx), mm(hy)))
    HN += 1
    fp.SetReference("H%d" % HN)
    fp.SetValue("M2")
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)

# -------------------------------------------------------------------- схема
d = kigen.Design(NAME, "STM32H723ZGT6 core board (LQFP144) - 84x84 mm, 4 layers")
d.prepare()
d.add(kigen.Part("U1", MCU_LIBID, "STM32H723ZGT6", "%s:%s" % MCU_FP,
                 {str(n): mcu_net(n) for n in sorted(pads)}, at=(80, 150)))
for s_, ref in HSIDE.items():
    nets = {str(hn): mcu_net(mn) for (r, hn), mn in hdrmap.items() if r == ref and mn not in NO_HEADER}
    d.add(kigen.Part(ref, "Connector_Generic:Conn_02x18_Odd_Even",
                     {"J2": "PORT_L", "J3": "PORT_B", "J4": "PORT_R", "J5": "PORT_T"}[ref],
                     "%s:PinHeader_2x18_P2.54mm_Vertical" % HDRLIB, nets,
                     at=({"J2": 220, "J3": 265, "J4": 310, "J5": 355}[ref], 60)))
d.add(kigen.Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C",
                 "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                 {"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
                  "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
                  "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
                  "A7": "USB_DM", "B7": "USB_DM", "S1": "GND"}, at=(400, 60)))
d.add(kigen.Part("J6", "Connector_Generic:Conn_01x04", "SWD",
                 "%s:PinHeader_1x04_P2.54mm_Vertical" % HDRLIB,
                 {"1": "+3V3", "2": "SWCLK", "3": "GND", "4": "SWDIO"}, at=(400, 120)))
d.add(kigen.Part("U2", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
                 {"1": "VBUS", "2": "GND", "3": "VBUS", "5": "+3V3"}, at=(445, 60)))
d.add(kigen.Part("Y1", "Device:Crystal", "25MHz", "Crystal:Crystal_SMD_5032-2Pin_5.0x3.2mm",
                 {"1": "HSE_IN", "2": "HSE_OUT"}, at=(445, 95)))
d.add(kigen.Part("Y2", "Device:Crystal", "32.768kHz",
                 "Crystal:Crystal_SMD_MicroCrystal_CC7V-T1A-2Pin_3.2x1.5mm",
                 {"1": "LSE_IN", "2": "LSE_OUT"}, at=(445, 125)))
d.add(kigen.Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "NRST", "2": "GND"}, at=(445, 150)))
d.add(kigen.Part("SW2", "Switch:SW_Push", "BOOT0", "Button_Switch_SMD:SW_SPST_SKQG_WithoutStem",
                 {"1": "BOOT0", "2": "+3V3"}, at=(445, 175)))
d.add(kigen.Part("D1", "Device:LED", "LED", "LED_SMD:LED_0805_2012Metric",
                 {"1": "LED_K", "2": "LED_A"}, at=(445, 200)))

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
                     at=(500 + 45 * (i // 10), 60 + 18 * (i % 10))))
RES = {"R1": ("5.1k", ("CC1", "GND")), "R2": ("5.1k", ("CC2", "GND")),
       "R3": ("0R", ("+3V3", "+3V3A")), "R4": ("10k", ("BOOT0", "GND")),
       "R5": ("1k", ("LED_K", "GND"))}
for i, ref in enumerate(sorted(RES)):
    val, (a, k) = RES[ref]
    d.add(kigen.Part(ref, "Device:R", val, "%s:%s" % R0402, {"1": a, "2": k}, at=(620, 60 + 18 * i)))
for i, n in enumerate(["GND", "+3V3", "VBUS"]):
    d.add(kigen.Part("#FLG%d" % i, "power:PWR_FLAG", "PWR_FLAG", "", {"1": n}, at=(620, 170 + 15 * i)))

os.makedirs(OUT, exist_ok=True)
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
INNER = {}
DIST = [2.2, 3.6, 5.0]
for s_ in ("L", "R", "T", "B"):
    k = 0
    for n in sides[s_]:
        net = mcu_net(n)
        if net not in ("+3V3", "GND", "VCAP1", "VCAP2"):
            continue
        p, v = padpt(n), inward(n, DIST[k % 3])
        b.track(net, [p, v], FCU, 0.18)
        b.via(net, *v, dia=0.5, drill=0.25)
        INNER[n] = v
        k += 1

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
        st = ix - sx * 3.0
        if h["row"] == 0:
            pts = [(px, py), a, (st, hy), (hx, hy)]
        else:
            g = h["gap"]
            pts = [(px, py), a, (st, g), (ix + sx * 1.6, g), (hx, hy)]
    else:
        a = (px, py + sy * 1.4)
        st = iy - sy * 3.0
        if h["row"] == 0:
            pts = [(px, py), a, (hx, st), (hx, hy)]
        else:
            g = h["gap"]
            pts = [(px, py), a, (g, st), (g, iy + sy * 1.6), (hx, hy)]
    b.track(mcu_net(mn), pts, FCU, 0.18)

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
XVBUS = UX - 0.7
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
LDM, LDP = UX - 2.2, UX - 3.7
for y in DMY_:
    b.track("USB_DM", [(UX, y), (LDM, y)], FCU, 0.18)
    b.via("USB_DM", LDM, y, dia=0.45, drill=0.25)
b.track("USB_DM", [(LDM, DMY_[0]), (LDM, DMY_[1])], BCU, 0.18)
for y in DPY_:
    b.track("USB_DP", [(UX, y), (LDP, y)], FCU, 0.18)
    b.via("USB_DP", LDP, y, dia=0.45, drill=0.25)
b.track("USB_DP", [(LDP, DPY_[0]), (LDP, DPY_[1])], BCU, 0.18)
hy = hdrof[104]["y"]
LDP_LAY = BCU
LP1 = (LDP, hdrof[104]["gap"] if hdrof[104]["row"] == 0 else hdrof[104]["y"])
b.track("USB_DP", [(LDP, DPY_[0]), LP1], LDP_LAY, 0.18)
b.track("USB_DP", to_hdr(104, LP1, app=LDP - (CX + HDO)), LDP_LAY, 0.18)
b.track("USB_DP", [(LDP, DPY_[0]), (LDP, hy)], FCU, 0.18)
b.track("USB_DM", [(LDM, DMY_[1]), (LDM - 0.6, DMY_[1] + 1.0)], BCU, 0.18)
LDM_LAY = BCU
LP2 = (LDM, hdrof[103]["gap"] if hdrof[103]["row"] == 0 else hdrof[103]["y"])
b.track("USB_DM", [(LDM, DMY_[1]), LP2], LDM_LAY, 0.18)
b.track("USB_DM", to_hdr(103, LP2, app=LDM - (CX + HDO)), LDM_LAY, 0.18)

# --- SWD
b.track("SWDIO", [b.padxy("J6", 4), (b.padxy("J6", 4)[0], Y0 + 11.0)], FCU, W)
b.via("SWDIO", b.padxy("J6", 4)[0], Y0 + 11.0, dia=0.6, drill=0.3)
SWL = (X1 - 6.5, hdrof[105]["y"])
b.track("SWDIO", [(b.padxy("J6", 4)[0], Y0 + 11.0), (X1 - 6.5, Y0 + 13.0), SWL], BCU, W)
b.track("SWDIO", to_hdr(105, SWL, app=(X1 - 6.5) - (CX + HDO)), BCU, W)
b.track("SWCLK", [b.padxy("J6", 2), (b.padxy("J6", 2)[0], Y0 + 9.4)], FCU, W)
b.via("SWCLK", b.padxy("J6", 2)[0], Y0 + 9.4, dia=0.6, drill=0.3)
b.track("SWCLK", to_hdr(109, (b.padxy("J6", 2)[0], Y0 + 9.4), app=3.2), BCU, W)
stub("J6", 1, "+3V3", 1.8)

# --- кнопки / светодиод
for sw in ("SW1", "SW2"):
    for pn in ("1", "2"):
        pp = [(tomm(q.GetPosition().x), tomm(q.GetPosition().y)) for q in b.fps[sw].Pads() if q.GetNumber() == pn]
        if len(pp) == 2:
            net = b.fps[sw].FindPadByNumber(pn).GetNetname()
            b.track(net, [pp[0], (pp[0][0], pp[0][1] + (1.6 if pn == "1" else -1.6)),
                          (pp[1][0], pp[1][1] + (1.6 if pn == "1" else -1.6)), pp[1]], FCU, W)
bx, by = b.padxy("SW2", 1)
b.via("BOOT0", bx, by, dia=0.6, drill=0.3)
b.track("BOOT0", to_hdr(138, (bx, by)), BCU, W)
b.track("BOOT0", [(bx, by), (b.padxy("R4", 1)[0], by), b.padxy("R4", 1)], FCU, W)
sx, sy = b.padxy("SW2", 2)
b.track("+3V3", [(sx, sy), (sx, sy + 1.6)], FCU, W)
b.via("+3V3", sx, sy + 1.6, dia=0.6, drill=0.3)
nx, ny = b.padxy("SW1", 1)
b.track("NRST", [(nx, ny), (X0 + 5.5, ny), (X0 + 5.5, hdrof[25]["y"])], FCU, W)
b.via("NRST", X0 + 5.5, hdrof[25]["y"], dia=0.6, drill=0.3)
b.track("NRST", to_hdr(25, (X0 + 5.5, hdrof[25]["y"])), BCU, W)
b.track("NRST", [(X0 + 5.5, CY + 16.0), b.padxy("C77", 1)], BCU, W)
b.via("NRST", X0 + 5.5, CY + 16.0, dia=0.6, drill=0.3)
b.track("LED_A", [b.padxy("D1", 2), (b.padxy("D1", 2)[0], Y1 - 8.0)], FCU, W)
b.via("LED_A", b.padxy("D1", 2)[0], Y1 - 8.0, dia=0.6, drill=0.3)
b.track("LED_A", to_hdr(46, (b.padxy("D1", 2)[0], Y1 - 8.0)), BCU, W)
b.track("LED_K", [b.padxy("D1", 1), (b.padxy("D1", 1)[0] - 1.2, b.padxy("D1", 1)[1] + 1.8),
                  (b.padxy("R5", 1)[0], b.padxy("R5", 1)[1] + 1.8), b.padxy("R5", 1)], FCU, W)

# -------------------------------------------------- контур, полигоны, шелк
b.edge_rect(CX, CY, BW, BH, 3.0)
b.zone("GND", pcbnew.In1_Cu, CX, CY, BW - 0.8, BH - 0.8)
b.zone("+3V3", pcbnew.In2_Cu, CX, CY, BW - 0.8, BH - 0.8)
b.zone("GND", FCU, CX, CY, BW - 0.8, BH - 0.8)
b.zone("GND", BCU, CX, CY, BW - 0.8, BH - 0.8)
for mn, h in hdrof.items():
    if h["row"] != 0:
        continue
    lbl = "NC" if mn in NO_HEADER else mcu_net(mn)
    dx, dy, rot = {"L": (3.0, 0, 0), "R": (-3.0, 0, 0), "T": (0, 3.0, 90), "B": (0, -3.0, 90)}[h["side"]]
    b.text(lbl, h["x"] + dx, h["y"] + dy, pcbnew.F_SilkS, 0.6, 0.1, rot)
b.text("STM32H723ZGT6 CORE BOARD", CX, Y0 + 1.8, pcbnew.F_SilkS, 1.6, 0.28)
b.text("84x84 mm | 4 layer | rev.A", CX, Y1 - 1.8, pcbnew.F_SilkS, 1.0, 0.18)

b.finish(os.path.join(OUT, NAME + ".kicad_pcb"))
json.dump({"hdrmap": {"%s.%s" % k: v for k, v in hdrmap.items()},
           "sides": sides, "pads": {str(k): v for k, v in pads.items()},
           "netof": {str(k): mcu_net(k) for k in pads}},
          open(os.path.join(OUT, "_geom.json"), "w"), indent=1)
print("OK ->", OUT)
