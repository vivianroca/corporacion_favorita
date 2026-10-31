# Código del producto

La etapa 2 implementa un paquete de espacio de nombres `reposicion` en `src/`:

- `contracts.py`: validación de filas y relaciones de las cinco fuentes.
- `source_simulator.py`: generador externo de carga histórica y bandeja.
- `source_io.py`: metadatos, checksums y lector de entregas sin escrituras.
- `cli.py`: generación, auditoría y listado por fecha de disponibilidad.
- `ingestion.py`: ingesta a landing, validación global, cuarentena y snapshots por corte.
- `automatic.py`: ledger incremental SQLite y publicación recuperable por ciclo.
- `release.py`: liberación progresiva de copias, sin regenerar la simulación maestra.

El DAG de `dags/` solo orquesta estos módulos. No hay módulos vacíos ni modelos.
