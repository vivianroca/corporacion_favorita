"""Diagnóstico local, sin modificar originales ni implementar un flujo de ingesta.

Ejecutar desde lab1: .venv/bin/python scripts/diagnosticar_fuentes.py
Solo usa la biblioteca estándar; SQLite es temporal y reside en memoria.
"""

import csv
import hashlib
import math
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = {
    "train": (
        ["id", "date", "store_nbr", "family", "sales", "onpromotion"],
        ["date", "store_nbr", "family"],
    ),
    "stores": (["store_nbr", "city", "state", "type", "cluster"], ["store_nbr"]),
    "holidays_events": (
        ["date", "type", "locale", "locale_name", "description", "transferred"],
        ["date", "type", "locale", "locale_name", "description", "transferred"],
    ),
    "oil": (["date", "dcoilwtico"], ["date"]),
    "transactions": (["date", "store_nbr", "transactions"], ["date", "store_nbr"]),
}
INTEGER = {"id", "store_nbr", "onpromotion", "cluster", "transactions"}
REAL = {"sales", "dcoilwtico"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def calendar(start, end):
    current = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while current <= stop:
        yield current.isoformat()
        current += timedelta(days=1)


def main():
    paths = {name: ROOT / "data/original" / f"{name}.csv" for name in SPECS}
    missing = [str(p) for p in paths.values() if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise SystemExit(f"Archivos ausentes o vacíos: {missing}")
    before = {n: sha256(p) for n, p in paths.items()}
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA temp_store=MEMORY")
    summaries = {}
    lines = [
        "# Diagnóstico inicial de las fuentes de Corporación Favorita",
        "",
        "## Alcance y método",
        "",
        (
            "Lectura completa de los cinco CSV requeridos, con Python estándar y SQLite en memoria. "
            "No se usan muestras. No se modifican originales ni se entrenan modelos. "
            "Los CSV no declaran tipos: los tipos siguientes son inferidos y comprobados sobre "
            "todos los valores no vacíos. Nulo significa celda vacía o compuesta solo por espacios."
        ),
        "",
        (
            "Los SHA-256 se calculan antes y después para comprobar que los archivos no cambiaron "
            "durante el diagnóstico. Esto verifica estabilidad local, no autenticidad frente a Kaggle: "
            "no se dispone de un manifiesto externo de referencia."
        ),
        "",
        (
            "Reproducir: `.venv/bin/python scripts/diagnosticar_fuentes.py`. "
            "El script reemplaza únicamente este informe; necesita memoria para las tablas temporales."
        ),
        "",
        "## Integridad y dimensiones",
        "",
        "| Archivo | Bytes | Filas | Columnas | Filas con ancho incorrecto |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, (columns, key) in SPECS.items():
        print(f"Analizando {name}...", flush=True)
        nulls = Counter()
        invalid = Counter()
        numeric = {c: [None, None, 0, 0] for c in columns if c in INTEGER | REAL}
        count = width_errors = 0
        seen_dates = set()
        db.execute(f"CREATE TABLE {name} ({', '.join(c + ' TEXT' for c in columns)})")
        placeholders = ",".join("?" for _ in columns)
        batch = []
        with paths[name].open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader)
            if header != columns:
                raise ValueError(f"Columnas inesperadas en {name}: {header}")
            for row in reader:
                count += 1
                if len(row) != len(columns):
                    width_errors += 1
                    continue
                for col, value in zip(columns, row):
                    if not value.strip():
                        nulls[col] += 1
                        continue
                    if col == "date":
                        if value not in seen_dates:
                            try:
                                if date.fromisoformat(value).isoformat() != value:
                                    raise ValueError(value)
                            except ValueError:
                                invalid[col] += 1
                                continue
                            seen_dates.add(value)
                    elif col in numeric:
                        try:
                            number = int(value) if col in INTEGER else float(value)
                            if not math.isfinite(number):
                                raise ValueError(value)
                            stats = numeric[col]
                            stats[0] = number if stats[0] is None else min(stats[0], number)
                            stats[1] = number if stats[1] is None else max(stats[1], number)
                            stats[2] += number < 0
                            stats[3] += number == 0
                        except ValueError:
                            invalid[col] += 1
                    elif col == "transferred" and value not in {"True", "False"}:
                        invalid[col] += 1
                batch.append(row)
                if len(batch) == 10000:
                    db.executemany(f"INSERT INTO {name} VALUES ({placeholders})", batch)
                    batch.clear()
            db.executemany(f"INSERT INTO {name} VALUES ({placeholders})", batch)
        db.commit()
        summaries[name] = {
            "rows": count,
            "nulls": nulls,
            "invalid": invalid,
            "numeric": numeric,
            "dates": seen_dates,
        }
        lines.append(
            f"| {name}.csv | {paths[name].stat().st_size:,} | {count:,} | "
            f"{len(columns)} | {width_errors:,} |"
        )
    lines += ["", "## Perfil por fuente", ""]

    def scalar(query):
        return db.execute(query).fetchone()[0]

    def rows(query):
        return db.execute(query).fetchall()

    def duplicates(name, columns):
        group = ",".join(columns)
        return scalar(
            f"SELECT COALESCE(SUM(n-1),0) FROM "
            f"(SELECT COUNT(*) n FROM {name} GROUP BY {group} HAVING COUNT(*)>1)"
        )

    for name, (columns, key) in SPECS.items():
        s = summaries[name]
        lines += [
            f"### {name}.csv",
            "",
            "| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |",
            "|---|---|---:|---:|---:|",
        ]
        for c in columns:
            kind = (
                "entero"
                if c in INTEGER
                else "real"
                if c in REAL
                else "fecha ISO YYYY-MM-DD"
                if c == "date"
                else "booleano True/False"
                if c == "transferred"
                else "texto"
            )
            lines.append(
                f"| {c} | {kind} | {s['nulls'][c]:,} | "
                f"{100 * s['nulls'][c] / s['rows']:.4f}% | {s['invalid'][c]:,} |"
            )
        exact = duplicates(name, columns)
        key_dup = exact if key == columns else duplicates(name, key)
        lines += [
            "",
            f"- Duplicados exactos, como filas excedentes: **{exact:,}**.",
            (
                f"- Duplicados de la clave candidata `{', '.join(key)}`: **{key_dup:,}** "
                "filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado."
            ),
        ]
        if name == "train":
            lines.append(f"- Duplicados de `id`: **{duplicates(name, ['id']):,}**.")
            fractional = scalar(
                "SELECT COUNT(*) FROM train WHERE CAST(sales AS REAL) != CAST(sales AS INTEGER)"
            )
            zero_sales = s["numeric"]["sales"][3]
            lines += [
                (
                    f"- Ventas con parte fraccionaria: **{fractional:,}**. "
                    f"Ventas cero: **{100 * zero_sales / s['rows']:.2f}%** de las filas."
                ),
                (
                    "- `onpromotion` es un conteo entero; no debe reducirse a un booleano sin "
                    "justificar la pérdida de información."
                ),
            ]
        if s["numeric"]:
            lines += [
                "",
                "| Columna | Mínimo | Máximo | Negativos | Ceros |",
                "|---|---:|---:|---:|---:|",
            ]
            for col, (low, high, neg, zero) in s["numeric"].items():
                lines.append(f"| {col} | {low} | {high} | {neg:,} | {zero:,} |")
        cats = [c for c in columns if c not in INTEGER | REAL | {"date", "description"}]
        for col in cats:
            values = rows(f"SELECT {col}, COUNT(*) FROM {name} GROUP BY {col} ORDER BY {col}")
            lines += [
                "",
                f"Valores y frecuencias de `{col}`: "
                + "; ".join(f"`{v}`: {n:,}" for v, n in values)
                + ".",
            ]
        lines.append("")

    lines += [
        "## Cobertura temporal",
        "",
        "| Fuente | Primera fecha | Última fecha | Fechas distintas | Días calendario del intervalo | Fechas sin fila |",
        "|---|---|---|---:|---:|---:|",
    ]
    for name, s in summaries.items():
        if not s["dates"]:
            lines.append(f"| {name} | No aplica | No aplica | — | — | — |")
            continue
        start, end = min(s["dates"]), max(s["dates"])
        absent = sorted(set(calendar(start, end)) - s["dates"])
        s["absent"] = absent
        lines.append(
            f"| {name} | {start} | {end} | {len(s['dates']):,} | "
            f"{len(list(calendar(start, end))):,} | {len(absent):,} |"
        )
    lines += [
        "",
        (
            "Fechas ausentes se cuentan dentro del intervalo de cada fuente; no equivalen automáticamente a errores. "
            "En feriados se registran eventos, por lo que los días sin fila son esperables. "
            "`stores` no contiene fechas de apertura, cierre ni vigencia de sus atributos."
        ),
        "",
    ]
    for name in ("train", "transactions", "oil"):
        absent = summaries[name]["absent"]
        weekdays = Counter(date.fromisoformat(d).strftime("%A") for d in absent)
        lines += [
            (
                f"- **{name}**: primeras fechas sin fila: {', '.join(absent[:20]) or 'ninguna'}; "
                f"distribución por día de semana: {dict(weekdays)}."
            ),
        ]

    print("Analizando relaciones y cobertura...", flush=True)
    db.execute("CREATE INDEX train_store_date ON train(store_nbr,date)")
    db.execute("CREATE INDEX tx_store_date ON transactions(store_nbr,date)")
    db.execute("CREATE INDEX store_id ON stores(store_nbr)")
    train_dates = summaries["train"]["dates"]
    stores_count = scalar("SELECT COUNT(DISTINCT store_nbr) FROM train")
    families = scalar("SELECT COUNT(DISTINCT family) FROM train")
    expected = len(train_dates) * stores_count * families
    per_day = rows("SELECT MIN(n), MAX(n) FROM (SELECT COUNT(*) n FROM train GROUP BY date)")[0]
    series_range = rows(
        "SELECT MIN(n),MAX(n) FROM (SELECT COUNT(*) n FROM train GROUP BY store_nbr,family)"
    )[0]
    unknown_train = scalar(
        "SELECT COUNT(*) FROM train t WHERE NOT EXISTS (SELECT 1 FROM stores s WHERE s.store_nbr=t.store_nbr)"
    )
    unknown_tx = scalar(
        "SELECT COUNT(*) FROM transactions t WHERE NOT EXISTS (SELECT 1 FROM stores s WHERE s.store_nbr=t.store_nbr)"
    )
    missing_tx = rows(
        "SELECT COUNT(*),SUM(CASE WHEN sales_sum>0 THEN 1 ELSE 0 END) FROM "
        "(SELECT t.store_nbr,t.date,SUM(CAST(t.sales AS REAL)) sales_sum FROM train t "
        "WHERE NOT EXISTS (SELECT 1 FROM transactions x WHERE x.store_nbr=t.store_nbr AND x.date=t.date) "
        "GROUP BY t.store_nbr,t.date)"
    )[0]
    tx_extra = scalar(
        "SELECT COUNT(*) FROM transactions x WHERE NOT EXISTS (SELECT 1 FROM train t WHERE x.store_nbr=t.store_nbr AND x.date=t.date)"
    )
    oil_dates = summaries["oil"]["dates"]
    oil_null_dates = {r[0] for r in rows("SELECT date FROM oil WHERE TRIM(dcoilwtico)=''")}
    oil_no_row = train_dates - oil_dates
    oil_no_value = train_dates & oil_null_dates
    repeated_events = rows(
        "SELECT date,COUNT(*) n FROM holidays_events GROUP BY date HAVING n>1 ORDER BY n DESC,date LIMIT 10"
    )
    local_unknown = rows(
        "SELECT DISTINCT locale_name FROM holidays_events WHERE locale='Local' AND locale_name NOT IN (SELECT city FROM stores)"
    )
    regional_unknown = rows(
        "SELECT DISTINCT locale_name FROM holidays_events WHERE locale='Regional' AND locale_name NOT IN (SELECT state FROM stores)"
    )
    lines += [
        "",
        "## Relaciones, granularidad y cobertura cruzada",
        "",
        (
            f"- `stores.store_nbr` es la dimensión de tienda: **{stores_count} tiendas** en ventas. "
            f"Filas de ventas con tienda desconocida: **{unknown_train:,}**; de transacciones: **{unknown_tx:,}**."
        ),
        (
            f"- `train`: granularidad diaria por tienda y familia, con **{families} familias**. "
            f"Sobre sus {len(train_dates):,} fechas observadas, el producto cartesiano esperado "
            f"es {expected:,} combinaciones; se observaron {summaries['train']['rows']:,} filas. "
            f"Filas por fecha: mínimo {per_day[0]:,}, máximo {per_day[1]:,}; "
            f"filas por serie tienda–familia: mínimo {series_range[0]:,}, máximo {series_range[1]:,}."
        ),
        (
            "- `transactions` se relaciona por `(date, store_nbr)`, sin desglose por familia. "
            "Sus cifras no deben sumarse después de replicarlas por familia al unirlas con ventas."
        ),
        (
            f"- Pares tienda–fecha de ventas sin transacciones: **{missing_tx[0]:,}**, "
            f"de los cuales **{missing_tx[1] or 0:,}** tienen ventas agregadas positivas. "
            f"Filas de transacciones sin par en ventas: **{tx_extra:,}**. Ausencia no equivale a cero."
        ),
        (
            "- `oil` se relaciona por fecha y es una variable común a todas las tiendas. "
            f"Fechas observadas de ventas sin fila de petróleo: **{len(oil_no_row):,}**; "
            f"con fila de petróleo pero valor vacío: **{len(oil_no_value):,}**. "
            f"Total sin precio observado al unir por fecha: **{len(oil_no_row | oil_no_value):,}** fechas."
        ),
        (
            "- `holidays_events` contiene eventos, no una fila única por fecha. Los nacionales "
            "se aplican a todas las tiendas; los regionales se relacionan con `stores.state` y los "
            "locales con `stores.city`. Unir solo por fecha puede multiplicar filas y aplicar "
            "eventos a tiendas que no corresponden. Deben agregarse indicadores por tienda–fecha."
        ),
        (
            f"- Nombres de eventos locales sin ciudad correspondiente: {local_unknown or 'ninguno'}; "
            f"regionales sin estado correspondiente: {regional_unknown or 'ninguno'}."
        ),
        "- Fechas con más eventos (fecha, cantidad): "
        + "; ".join(f"{d}: {n}" for d, n in repeated_events)
        + ".",
        (
            "- `transferred` y el tipo de evento requieren reglas explícitas: un feriado trasladado "
            "no debe tratarse automáticamente como descanso efectivo en su fecha original."
        ),
        "",
        "## Hallazgos y decisiones pendientes para los contratos",
        "",
        (
            "1. Las fechas del archivo representan el hecho o calendario, **no el momento de disponibilidad**. "
            "Los CSV no proporcionan fecha de entrega, revisión ni historial de correcciones. Estos metadatos "
            "deberán definirse en la simulación; no pueden inferirse como hechos observados."
        ),
        (
            "2. Documentar los días sin ventas registradas y distinguir ausencia de fila, venta cero y tienda "
            "sin actividad. La presencia de ceros no demuestra que hubiera stock disponible."
        ),
        (
            "3. Definir políticas para precios de petróleo ausentes y frecuencia de entrega. Cualquier "
            "relleno deberá respetar la disponibilidad temporal; no interpolar usando valores futuros."
        ),
        (
            "4. Definir cuándo se conocen promociones, transacciones y calendarios. Que existan valores "
            "para una fecha posterior al corte en los archivos completos no autoriza su uso predictivo."
        ),
        (
            "5. Ventas es una magnitud real: no imponer integridad entera a `sales`. Validar por separado "
            "enteros, no negatividad, claves, categorías, cambios de esquema y correcciones."
        ),
        (
            "6. Estos controles son un diagnóstico del snapshot actual. Las claves candidatas y categorías "
            "observadas deben evaluarse antes de convertirse en contratos; futuras categorías o tiendas "
            "no deben rechazarse sin una regla de negocio documentada."
        ),
        (
            "7. No existen inventario, pedidos en tránsito ni costos en estas fuentes. No permiten calcular "
            "una reposición física sin supuestos externos explícitos."
        ),
        (
            "8. Los archivos `test.csv` y `sample_submission.csv`, aunque estén en la carpeta, se excluyen "
            "del análisis y del laboratorio."
        ),
        "",
        "## Huellas de los originales",
        "",
        "| Archivo | SHA-256 antes y después |",
        "|---|---|",
    ]
    after = {n: sha256(p) for n, p in paths.items()}
    if before != after:
        raise RuntimeError(
            "Los originales cambiaron durante el diagnóstico; no se publica el informe"
        )
    for name in SPECS:
        lines.append(f"| {name}.csv | `{before[name]}` |")
    lines += [
        "",
        "Las cinco huellas coinciden antes y después. Los originales permanecen excluidos de Git.",
        "",
    ]
    output = ROOT / "docs/diagnostico_fuentes.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe generado: {output}", flush=True)


if __name__ == "__main__":
    main()
