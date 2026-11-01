# Reloj simulado del pronóstico programado

## Causa del fallo

El cron semanal se ejecuta en 2026, pero las ventas originales abarcan
2013-01-01 a 2017-08-15 (diagnóstico de train). Antes, el DAG utilizaba
`data_interval_end` como emisión y exigía los 28 días anteriores de 2026 a los
snapshots de 2017. Además, el snapshot cronológicamente más reciente puede ser
una ventana parcial para seguimiento, no un histórico completo para inferencia.

Se corrige únicamente el reloj de orquestación del DAG de pronóstico. No se cambia
la validación de snapshots, el modelo, los pedidos ni los otros dos DAGs.

## Dos relojes explícitos

| Dato | Valor de la prueba |
|---|---|
| Cron físico | Domingo 06:00 America/Guatemala |
| Run original | scheduled__2026-11-01T12:00:00+00:00 |
| Tipo real del run | scheduled, sin convertirlo en manual |
| Fecha lógica física | 2026-11-01T12:00:00Z |
| Modo de datos | historical_replay |
| Origen simulado | 2017-03-05 |
| Emisión simulada | 2017-03-05T12:00:00Z |
| Historia requerida | 2017-02-05 a 2017-03-04, exactamente 28 días |
| Pronóstico | 2017-03-05 a 2017-03-11 |

La política se define en `configs/pronostico.yaml`, bloque `simulation_calendar`.
Fija modo, replay_id, límites del histórico, origen, emisión y snapshot exacto.
**No elige el último snapshot, no resta años a la fecha actual y no toma ahora().**
La fecha física solo se registra como auditoría, no se convierte en información
de ventas. Si falta la política, el DAG falla explícitamente sin fallback real.

## Replay fijo, no un calendario que avanza solo

El escenario actual fija el único snapshot completo de 28 días disponible:
`645e5d301d92ba40e3374077c4b76921e8daf49f8a1ae415ee2e24f1d58ad5c0`.
Las ejecuciones semanales de 2026 repiten ese mismo corte de datos hasta que se
cambie expresamente la configuración. Eso produce reutilización idempotente,
no datos nuevos ficticios para cada semana física.

Para avanzar, primero se requiere otro snapshot validado con los 28 días previos
y su confirmación Asset; después se cambia origen/emisión/snapshot/replay_id en
la configuración. El cron se mantiene semanal. No se crea historia ni se omiten
fechas para forzar que el sensor acepte una ventana incompleta.

## Controles temporales conservados

- El origen debe coincidir con el día local de emisión.
- Los 28 días previos y siete días de horizonte deben estar dentro del calendario
  histórico configurado. Los límites se obtienen del diagnóstico de train.
- El snapshot debe estar disponible al corte y confirmado por su ID/hash en Assets.
- Se conserva `SnapshotCatalog` sin cambios: contratos, checksums, validación,
  recibos disponibles y exigencia de los 28 días previos.
- Modelos y residuos de calibración siguen sujetos a sus disponibilidades históricas;
  el Champion actual no puede utilizarse para simular 2013 con entrenamiento futuro.

El snapshot de abril solo tiene siete días y sirve para evaluar ventas: no se
sustituye por él el snapshot completo de marzo. Datos conocidos después del corte
no se incorporan al pronóstico. El seguimiento puede evaluar después, bajo su
propio corte, sin cambiar la fecha de generación del pronóstico.

## Backfill

Se conservan origin/issued_at/snapshot_id/model_version explícitos. Una emisión
UTC que cruce medianoche se interpreta por su fecha en Guatemala, como antes.
Con solo origin, se deriva 06:00 Guatemala. Un backfill nativo usa su
`data_interval_end` **histórico**, validándolo contra el dominio: un backfill de
2026 no se hace pasar por histórico silenciosamente.

Un manual sin corte utiliza el replay configurado. Un manual con solo snapshot_id
puede resolver el corte de ese snapshot, pero la búsqueda se limita al calendario
histórico, no a la hora actual, y el corte resuelto se vuelve a validar.
La disponibilidad del modelo y los 28 días siguen siendo obligatorios.

## Trazabilidad e idempotencia

La resolución queda en logs y en el XCom de esperar_snapshot. El Asset final
incluye business_clock con política completa, SHA-256 de política, modo/resolución,
fechas físicas y origen/emisión/snapshot resueltos. Las publicaciones conservan
sus fechas de negocio existentes. Las fechas físicas de ejecución no entran en
la identidad de resultados: repetir el mismo escenario no duplica pronósticos,
pedidos o paquetes completos. Cambiar un corte efectivo o costos produce las
versiones correspondientes mediante los publicadores existentes.

## Prueba programada real

Se reabrió solo el run programado fallido de hoy mediante el mecanismo nativo
`clear_task_instances(..., run_on_latest_version=True)`, limitado a sus cuatro
tareas. Esto es importante: Airflow puede conservar una definición serializada
anterior al limpiar sin seleccionar la versión nueva. No se insertó un run manual
con nombre scheduled, ni se cambiaron run_type, logical_date o intervalo físico.
Los logs de intentos anteriores permanecen disponibles.

Resultado: `scheduled__2026-11-01T12:00:00+00:00`, **scheduled / success**.
Las cuatro tareas, incluido esperar_snapshot, terminaron correctamente:
12.474 pronósticos y 1.782 pedidos para 5–11 marzo de 2017.
Se verificó disponibilidad de todos los recibos al corte y exactamente las 28
fechas previas. Reabrir por segunda vez el mismo run reutilizó pronóstico,
pedidos y paquete completo (`reused=True`) sin recalcular resultados existentes.

- Pronóstico: bdf4290355b5f55a5f082dba182228c00833e9d1ceda42160d03e2805f86615d.
- Pedidos: 18537175d56fbeea52a6d118398d24675d8bf0d3971b1bf3d191f6ba9e8a86d6.
- Completo: d4215a0192e655e2f7fecaa29e575bddf77ab6d24f6e99b33e9932c524789613.
- Política: c168b3e407c5124dd01aea1ae05049792552d4f55c83921007eac84080587ba3.

Diecisiete pruebas sin entrenamiento cubren resolución programada independiente
la semana física, ausencia de fallback, límites, fechas locales, backfill y los
controles de snapshots/publicación existentes. Informe de verificación:
`reports/simulated_clock/verification.json`, ignorado por Git. Los hashes de los
otros DAGs y módulos de negocio/validación se conservaron. No se modifican modelos,
DVC, Git ni los originales; no se regeneran entregas ni se modifica ingesta.
