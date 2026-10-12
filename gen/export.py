#!/usr/bin/env python3
"""Выходные файлы платы: гербера, сверловка, pos.csv, PDF и архив для завода.

    python3 gen/export.py boards/STM32H723ZG-CoreBoard

Всё делает kicad-cli, здесь только один и тот же набор ключей для всех плат,
чтобы у двух плат сходились имена файлов и настройки.
"""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicadenv

LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,"
          "F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts")


def cli():
    """kicad-cli рядом с тем pcbnew, которым собрана плата."""
    exe = "kicad-cli.exe" if os.name == "nt" else "kicad-cli"
    near = os.path.join(os.path.dirname(os.path.dirname(kicadenv.share_dir())), "bin", exe)
    return near if os.path.exists(near) else exe


def run(*args):
    r = subprocess.run([cli()] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("kicad-cli %s:\n%s" % (args[:3], r.stderr.strip()[-800:]))
    return r.stdout.strip()


# JLCPCB разбирает CPL по именам колонок и родные заголовки KiCad не понимает -
# файл отвергается целиком ("Failed processing the CPL file"). Переименовываем.
CPLHDR = {"Ref": "Designator", "PosX": "Mid X", "PosY": "Mid Y",
          "Rot": "Rotation", "Side": "Layer"}


# Поправка поворота для CPL. Библиотека JLCPCB собрана из футпринтов EasyEDA, и
# у них другое соглашение о том, в каком углу корпуса нулевой вывод: для QFP это
# регулярно даёт расхождение на 90 градусов с официальными футпринтами KiCad.
# Правка только в CPL - на самой плате и в схеме ничего не меняется.
# Ключ - подстрока имени футпринта: правило принадлежит корпусу, а не позиции
# (каждое правило проверено превью JLCPCB при реальном заказе - см. комментарии).
ROT_FIX = {
    "LQFP-144": -90.0,  # их пад 1 в просмотрщике вставал в левый нижний угол
    "LQFP-64": -90.0,   # то же семейство корпусов
    "SOT-23-8": 180.0,  # заказ CAN-Unit: пад 1 вставал в противоположный угол
    "VSON-8": -90.0,    # заказ LIN-Unit: их точка пина 1 вставала в правый нижний угол
    "SOIC-8": -90.0,    # заказ Volt-Unit: корпус лежал ножками поперёк наших падов
    "SOT-23-5": -90.0,  # заказ Voice-Unit (TLV75733): корпус лежал боком к падам. Ключ
                        # раньше "SOT-23", иначе подстрока "SOT-23" даст 180
    "SOT-23": 180.0,    # заказ Volt-Unit (BAT54S): 2-падовая сторона менялась с 1-падовой
    "TQFN-16": -90.0,   # заказ Voice-Unit (MAX98357A): их пин 1 вставал в соседний угол
    "ICS-43434": -90.0,  # заказ Voice-Unit: вертикальный корпус 2.65x3.5 ложился горизонтально
    "JST_PH_B": 180.0,   # заказ Voice-Unit: у JLCPCB (C131334) корпус и нумерация выводов
                         # нарисованы развёрнутыми на 180 относительно KiCad
}

# Футпринты, у которых точка привязки - вывод 1, а не центр корпуса. JLCPCB ставит
# деталь центром в Mid X/Y, поэтому для них в CPL пишем центр корпуса (слой F.Fab).
BODY_CENTER = ()   # (JST PH сюда не относится: у JLCPCB его привязка - линия выводов)
# А у этих привязка JLCPCB - центр поля выводов, а не центр корпуса: у модуля
# ESP32 выводы только в нижней части (сверху антенна), центр выводов на 3.62 мм ниже.
PAD_CENTER = ("ESP32-S3-WROOM",   # заказ Voice-Unit: модуль вставал на 3.5 мм к антенне
              "HRO_TYPE-C",       # заказ Voice-Unit (и H723): USB-C на 1.5 мм наружу от падов
              "JST_PH_")          # заказ Voice-Unit: J3 - центр линии выводов
# Сверка CPL с посадочными местами EasyEDA/JLCPCB: scratchpad cpl_vs_jlc.py (пады их
# детали при нашем Mid/Rotation должны лечь на наши пады).


def body_centers(pcb):
    """ref -> (x, y) точки привязки JLCPCB для футпринтов из BODY_CENTER/PAD_CENTER, мм."""
    import pcbnew
    tomm = pcbnew.ToMM
    out = {}
    for fp in pcbnew.LoadBoard(pcb).GetFootprints():
        name = str(fp.GetFPID().GetLibItemName())
        if any(k in name for k in PAD_CENTER):
            xs = [tomm(p.GetPosition().x) for p in fp.Pads()]
            ys = [tomm(p.GetPosition().y) for p in fp.Pads()]
            out[fp.GetReference()] = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
            continue
        if not any(k in name for k in BODY_CENTER):
            continue
        # контур корпуса - самый крупный элемент F.Fab (метка вывода 1 рядом смещала центр)
        best = None
        for it in fp.GraphicalItems():
            if it.GetLayer() == pcbnew.F_Fab:
                bb = it.GetBoundingBox()
                area = bb.GetWidth() * bb.GetHeight()
                if best is None or area > best[0]:
                    best = (area, bb)
        if best:
            bb = best[1]
            out[fp.GetReference()] = (tomm(bb.GetCenter().x), tomm(bb.GetCenter().y))
    return out


def jlc_cpl(path, centers=None):
    import csv
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    hdr = rows[0]
    rows[0] = [CPLHDR.get(c, c) for c in hdr]
    ir = rows[0].index("Rotation") if "Rotation" in rows[0] else None
    ip = rows[0].index("Package") if "Package" in rows[0] else None
    ix = rows[0].index("Mid X") if "Mid X" in rows[0] else None
    iy = rows[0].index("Mid Y") if "Mid Y" in rows[0] else None
    for r in rows[1:]:
        if centers and r[0] in centers and ix is not None and iy is not None:
            cx, cy = centers[r[0]]
            print("центр корпуса в CPL: %s (%s, %s) -> (%.3f, %.3f)" % (r[0], r[ix], r[iy], cx, -cy))
            r[ix], r[iy] = "%.6f" % cx, "%.6f" % -cy     # в CPL ось Y вверх
    il = rows[0].index("Layer") if "Layer" in rows[0] else None
    fixed = []
    for r in rows[1:]:
        fix = None
        # Правила ROT_FIX проверены только для верхней стороны. На обороте JLCPCB
        # зеркалит деталь, и знак поправки не установлен (H723: AP2112K на обороте
        # собран по CPL без поправки - JLCPCB подогнал при DFM). Оборот не трогаем.
        if il is not None and r[il].lower().startswith("b"):
            continue
        if ip is not None:
            for key, ang in ROT_FIX.items():
                if key in r[ip]:
                    fix = ang
                    break
        if ir is not None and fix is not None:
            r[ir] = "%.6f" % ((float(r[ir]) + fix) % 360.0)
            fixed.append(r[0])
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    if fixed:
        print("поворот в CPL поправлен: %s" % ", ".join(fixed))


def main(out):
    out = os.path.abspath(out)              # kicad-cli путается в относительных путях
    name = os.path.basename(out)
    pcb = os.path.join(out, name + ".kicad_pcb")
    sch = os.path.join(out, name + ".kicad_sch")
    gerb = os.path.join(out, "gerbers")
    if not os.path.exists(pcb):
        raise SystemExit("нет платы: %s" % pcb)

    shutil.rmtree(gerb, ignore_errors=True)
    os.makedirs(gerb, exist_ok=True)
    run("pcb", "export", "gerbers", "--layers", LAYERS, "-o", gerb, pcb)
    run("pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
        "--excellon-units", "mm", "-o", gerb, pcb)
    print("гербера:", len(os.listdir(gerb)), "файлов")

    zpath = os.path.join(out, name + "_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gerb)):
            z.write(os.path.join(gerb, f), f)
    print("архив:", os.path.basename(zpath))

    pos = os.path.join(out, "pos.csv")
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
        "-o", pos, pcb)
    jlc_cpl(pos, body_centers(pcb))
    run("pcb", "export", "pdf", "--layers", "F.Cu,F.Silkscreen,Edge.Cuts",
        "-o", os.path.join(out, "top.pdf"), pcb)
    run("pcb", "export", "pdf", "--layers", "B.Cu,B.Silkscreen,Edge.Cuts",
        "-o", os.path.join(out, "bot.pdf"), pcb)
    if os.path.exists(sch):
        run("sch", "export", "pdf", "-o", os.path.join(out, "sch.pdf"), sch)
    print("pos.csv / top.pdf / bot.pdf / sch.pdf ->", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
