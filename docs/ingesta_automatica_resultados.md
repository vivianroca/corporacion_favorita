# Evidencia de ingesta automática

## Configuración verificada

- DAG: `lab1_ingesta_temporal`; cron `*/5 * * * *` (Every 5 minutes).
- DAG habilitado (`is_paused=False`), sin errores de importación.
- Runs de la demostración creados por el scheduler (`run_type=scheduled`), sin triggers manuales.
- Bandeja nueva inicialmente vacía; se conserva su versión de catálogo con cero entregas.

## Runs reales del 31 de octubre de 2026

| Run ID | Estado | CSV nuevos procesados | Filas nuevas leídas | Publicación nueva |
|---|---|---:|---:|---|
| `scheduled__2026-10-31T06:10:00+00:00` | success | 1 | 54 | sí |
| `scheduled__2026-10-31T06:15:00+00:00` | success | 1 | 1782 | sí |
| `scheduled__2026-10-31T06:20:00+00:00` | success | 0 | 0 | no |

Las fechas de los IDs están en UTC: 06:10, 06:15 y 06:20 corresponden a 00:10, 00:15 y 00:20 en Guatemala. El primer run comenzó a las 06:11:08 UTC tras actualizar los contenedores; los siguientes fueron creados en sus límites de cinco minutos.

## Archivos efectivamente procesados

| Entrega | CSV de la bandeja | Revisión | SHA-256 del payload |
|---|---|---:|---|
| `stores/2013-01-01/r0001` | `historical/stores/2013-01-01/r0001.csv` | 1 | `5a2b62c10549bd9a0b6e78e0c2a3ee6c586b8efc14c06d84e482b745145ab805` |
| `train/2017-01-18/r0001` | `source_inbox/train/2017-01-18/r0001.csv` | 1 | `16342445973b8ffa2ee7e3a5ce670ea78c1eb120574780ce6742f38e36ad11e8` |

El segundo ciclo leyó únicamente ventas: tiendas se reutilizó desde el estado validado. En el tercero, `processed_files=[]`, `publication_id=null` y `reason=no_new_deliveries`.

## Publicaciones y ledger

- `d6d12d5dccd234070acfafb655677f90644898a0296be8d030895dcd87b59514` — corte `2026-10-31T06:10:00Z`.
- `7257a6b9bb2d5220ffb2fc38572b83e966e26840ffe5c142e770398965a9b07c` — corte `2026-10-31T06:15:00Z`.

Stream: `0d52e445d166a53100b95ca9e5dbf1c804c3c5d1f7330e16ccccfdb0f69b08e3`.

Ledger: `lab1_operational:/opt/lab1/operational/automatic/<stream_id>/control.sqlite`.

El ledger confirma dos recibos procesados y dos publicaciones en estado published. Las publicaciones y el landing conservan exactamente el mismo contenido y mtime en sus 16 archivos antes y después del ciclo vacío. No se generó una tercera publicación.

## Pruebas y preservación

- **88 pruebas sintéticas aprobadas**; Ruff y formato sin errores; pip check sin incompatibilidades.
- Correcciones históricas, recuperación antes y después del commit, concurrencia, conflictos de checksum y catálogo congelado cubiertos por pruebas.
- Backfill adicional `auto_backfill_verificacion`: success, con corte 2017-01-20 y referencia 2017-01-18, por la ruta histórica separada.
- Los 31 archivos operativos de la prueba de etapa 3 anterior conservaron sus hashes y mtime.
- Los 10.150 archivos de originales y simulación maestra conservaron rutas, hashes y mtime.
- Los CSV y sobres liberados son copias exactas: disponibilidad histórica y revisiones sin cambios.
- Montaje `/opt/lab1/inbox` confirmado de solo lectura. Solo el publicador agregó entregas.
- Cinco contenedores permanentes de lab1 healthy; PostgreSQL y MLflow mantienen sus contenedores y volúmenes. MLflow continúa con cero runs.
- Datos y secretos permanecen ignorados por Git. No se hicieron commits ni publicaciones remotas.

No hay problemas bloqueantes en el alcance probado. El DAG queda habilitado y continuará sondeando cada cinco minutos. No se entrenaron modelos.

Comandos y diseño: [ingesta_automatica.md](ingesta_automatica.md). Evidencia detallada por API y ledger: `data/automatic_demo/evidence.json` (ignorada por Git).
