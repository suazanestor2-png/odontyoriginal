"""Convierte la tabla CIE10 exportada de SISPRO (Excel o CSV) al CSV que usa seed_cie10().

Uso (desde la raiz del proyecto):
    python -m app.catalogs.cie10_desde_sispro ruta/al/cie10_sispro.xlsx

Genera app/catalogs/data/cie10.csv con las columnas code,name. Si la tabla trae una
columna "Habilitado", solo se incluyen los codigos habilitados (SI).
Para leer Excel necesita openpyxl:  pip install openpyxl
"""
import csv
import sys
import unicodedata
from pathlib import Path

DESTINO = Path(__file__).parent / "data" / "cie10.csv"


def _norm(texto) -> str:
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().strip().lower()


def _leer_filas(origen: Path) -> list[list]:
    if origen.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        hoja = load_workbook(origen, read_only=True, data_only=True).active
        return [list(fila) for fila in hoja.iter_rows(values_only=True)]
    with origen.open(encoding="utf-8-sig", newline="") as f:
        muestra = f.read(4096)
        f.seek(0)
        separador = max(",;\t|", key=muestra.count)
        return [fila for fila in csv.reader(f, delimiter=separador)]


def convertir(origen: Path) -> int:
    filas = [f for f in _leer_filas(origen) if any(c not in (None, "") for c in f)]
    # La fila de encabezados es la primera que tenga una columna "codigo" y otra "nombre"/"descripcion"
    for i, fila in enumerate(filas):
        cols = [_norm(c) for c in fila]
        if "codigo" in cols and ("nombre" in cols or "descripcion" in cols):
            encabezado, datos = cols, filas[i + 1:]
            break
    else:
        raise SystemExit("No encontre las columnas 'Codigo' y 'Nombre' en el archivo")

    i_codigo = encabezado.index("codigo")
    i_nombre = encabezado.index("nombre") if "nombre" in encabezado else encabezado.index("descripcion")
    i_habilitado = encabezado.index("habilitado") if "habilitado" in encabezado else None

    vistos = {}
    for fila in datos:
        codigo = str(fila[i_codigo] or "").strip().upper().replace(".", "")
        if not codigo or len(codigo) > 4:
            continue
        if i_habilitado is not None and _norm(fila[i_habilitado]) not in ("si", "s", "1", "true"):
            continue
        vistos[codigo] = str(fila[i_nombre] or "").strip()

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with DESTINO.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name"])
        for codigo in sorted(vistos):
            w.writerow([codigo, vistos[codigo]])
    return len(vistos)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    total = convertir(Path(sys.argv[1]))
    print(f"{total} codigos CIE-10 escritos en {DESTINO}")
