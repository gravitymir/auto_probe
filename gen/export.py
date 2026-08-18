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

    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
        "-o", os.path.join(out, "pos.csv"), pcb)
    run("pcb", "export", "pdf", "--layers", "F.Cu,F.Silkscreen,Edge.Cuts",
        "-o", os.path.join(out, "top.pdf"), pcb)
    run("pcb", "export", "pdf", "--layers", "B.Cu,B.Silkscreen,Edge.Cuts",
        "-o", os.path.join(out, "bot.pdf"), pcb)
    if os.path.exists(sch):
        run("sch", "export", "pdf", "-o", os.path.join(out, "sch.pdf"), sch)
    print("pos.csv / top.pdf / bot.pdf / sch.pdf ->", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
