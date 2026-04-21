"""Verifica las 10 mejoras del plan de gobernanza."""
import sys, io, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent

def rd(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

results = []

def chk(n, label, cond, detail=""):
    tag = "[OK] " if cond else "[ERR]"
    msg = f"  {tag}  M{n:02d}  {label}"
    if detail:
        msg += f"\n         {detail}"
    results.append((n, cond))
    print(msg)

src    = rd(ROOT / "audit.py")
dt_src = rd(ROOT / "demo_trader.py")

# 1 -- audit.py --export-md
chk(1, "audit.py --export-md",
    "--export-md" in src and "MD_LINES" in src and "write_text" in src,
    "argparse + coleccion MD_LINES + escritura a archivo")

# 2 -- .gitattributes
ga = ROOT / "governance/committee/dictamenes/.gitattributes"
chk(2, "dictamenes/.gitattributes",
    ga.exists() and "linguist-documentation" in rd(ga),
    f"Tamano: {ga.stat().st_size}b" if ga.exists() else "FALTA")

# 3 -- paso-a-live
pal = ROOT / "governance/committee/plantilla-checklist-paso-a-live.md"
chk(3, "plantilla-checklist-paso-a-live.md",
    pal.exists() and "MODE=live" in rd(pal),
    f"Tamano: {pal.stat().st_size}b" if pal.exists() else "FALTA")

# 4 -- new-dictamen.py
nd = ROOT / "governance/new-dictamen.py"
nd_src = rd(nd)
chk(4, "governance/new-dictamen.py",
    nd.exists() and "_next_seq" in nd_src and "shutil.copyfile" in nd_src,
    "auto-numeracion secuencial + copia de plantilla + apertura en editor")

# 5 -- metricas tendencia
fin = ROOT / "governance/committee/plantilla-checklist-auditoria-financiera.md"
fin_txt = rd(fin)
chk(5, "Metricas de tendencia (Seccion 2) + Funnel KPI (Seccion 10)",
    "T-3" in fin_txt and "Win rate" in fin_txt and "Funnel" in fin_txt,
    "tabla T-3/T-2/T-1/T0 + seccion funnel con umbral 30%")

# 6 -- CODEOWNERS
co = ROOT / ".github/CODEOWNERS"
co_txt = rd(co)
chk(6, ".github/CODEOWNERS",
    co.exists() and "dictamenes" in co_txt,
    co_txt.strip()[:100] if co.exists() else "FALTA")

# 7 -- PID lock Windows
chk(7, "PID lock Windows via tasklist (demo_trader.py)",
    "_pid_still_running" in dt_src and "tasklist" in dt_src,
    "funcion _pid_still_running() usa subprocess tasklist /FI en Windows")

# 8 -- postmortem
pm = ROOT / "governance/committee/plantilla-postmortem-incidente.md"
pm_txt = rd(pm)
chk(8, "plantilla-postmortem-incidente.md",
    pm.exists() and "preventiva" in pm_txt,
    f"Tamano: {pm.stat().st_size}b — cronologia + causa raiz + preventiva + leccion" if pm.exists() else "FALTA")

# 9 -- signal funnel
chk(9, "Signal funnel en demo_trader.py (signal_funnel.json)",
    "_signal_funnel" in dt_src
    and "_write_funnel_snapshot" in dt_src
    and "filtered_session" in dt_src
    and "filtered_spread" in dt_src
    and "filtered_staleness" in dt_src
    and "executed_ratio" in dt_src,
    "dict _signal_funnel + 5 puntos de conteo + snapshot JSON por tick")

# 10 -- versionado semantico
acta = ROOT / "governance/committee/plantilla-acta-y-dictamen.md"
acta_txt = rd(acta)
chk(10, "Campo 'Mejoras activas' en plantilla-acta-y-dictamen.md",
    "Mejoras activas" in acta_txt,
    "campo de IDs (#77, #80...) en encabezado del dictamen")

print()
ok_n  = sum(1 for _, c in results if c)
err_n = sum(1 for _, c in results if not c)
print(f"  {'='*50}")
print(f"  Resultado: {ok_n}/10 OK  |  {err_n} pendientes")
if err_n == 0:
    print("  Las 10 mejoras de gobernanza estan implementadas.")
