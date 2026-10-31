# Etapa 2: contratos, carga histórica y sistema de origen

## Alcance

Se implementan los contratos de los cinco CSV, la preparación de una carga histórica
inicial y un generador externo de entregas. No se implementan la ingesta operativa,
cuarentena, snapshots del producto, modelos ni DAGs de la etapa 3 o posteriores.

El diagnóstico de referencia es [diagnostico_fuentes.md](diagnostico_fuentes.md).
Los originales se leen completos y nunca se modifican. `test.csv` y
`sample_submission.csv` no se usan. Todo `data/` permanece fuera de Git.

## Comandos

Desde la raíz de `lab1`, con las dependencias ya instaladas:

```sh
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m reposicion.cli simulate
.venv/bin/python -m reposicion.cli verify-source
.venv/bin/python -m reposicion.cli list-deliveries --as-of '2017-01-01T00:00:00-05:00' --area historical
.venv/bin/python -m pytest -q
```

La CLI también está disponible como `.venv/bin/reposicion`. Las rutas por defecto
proceden de `configs/sources.yaml`; `--sources-config` permite otra configuración.
Las opciones `--originals`, `--output`, `--contracts` y `--availability` de
`simulate` permiten sobrescribir explícitamente esas rutas. Ejecutar desde la raíz
del proyecto: las rutas se resuelven respecto al directorio de ejecución.

La generación completa lee aproximadamente 3 millones de ventas, valida claves en
SQLite temporal y crea miles de archivos pequeños. Requiere espacio local adicional;
no necesita pandas, una base persistente ni servicios. Los datos sintéticos de las
pruebas son independientes de Kaggle.

## Contratos reales

`configs/contracts.yaml` es la especificación versionada. No se impone un universo
cerrado de familias ni un número fijo de tiendas. Las categorías de tipo de tienda,
tipo de evento y ámbito geográfico sí constituyen enumeraciones explícitas de esta
versión; un valor nuevo requiere revisar el contrato.

| Fuente | Clave primaria | Reglas principales |
|---|---|---|
| `train` | fecha, tienda, familia | ID también único; ventas decimales finitas no negativas; promociones enteras no negativas |
| `stores` | tienda | ciudad y estado no vacíos; tipo A–E; clúster entero positivo |
| `transactions` | fecha, tienda | conteo entero no negativo, sin familia |
| `oil` | fecha | precio decimal finito no negativo o vacío explícito |
| `holidays_events` | fecha, tipo, ámbito, ubicación, descripción | múltiples eventos por fecha; booleano estricto de traslado |

Las cabeceras pueden venir en otro orden, pero no con columnas faltantes, duplicadas
o adicionales. Las salidas recuperan el orden canónico del contrato. Las claves
se comparan con sus tipos interpretados: `01` y `1` identifican la misma tienda.
Se valida cada fila y la unicidad sobre el original completo, incluso IDs de ventas
repetidos en distintas fechas. Los CSV vacíos y las filas con ancho incorrecto fallan.

Ventas y transacciones deben referenciar tiendas de `stores`. Los eventos nacionales
referencian `Ecuador`; los regionales, un estado; los locales, una ciudad del catálogo.
`event_applies` solo comprueba el ámbito geográfico: no convierte automáticamente un
evento trasladado en descanso efectivo. Se conservan todos los campos originales.

### Cero, vacío y ausencia

- `sales=0` es una observación y se conserva como cero.
- `sales` vacío es una violación del contrato; nunca se rellena con cero.
- Petróleo vacío es una observación con medida desconocida, conservada como celda vacía.
- Una tienda–familia–fecha o tienda–fecha sin fila continúa ausente. No se crea una fila
  sintética ni se infiere cierre, falta de stock o ausencia de demanda.
- Las fechas completas sin registros, incluidos los 25 de diciembre del histórico,
  no provocan fallas por sí mismas. Tampoco se espera un evento cada día ni petróleo
  todos los fines de semana.
- `onpromotion` sigue siendo un conteo de la fila de ventas. No se extrae un supuesto
  calendario de promociones futuras a partir del CSV final.

Los errores detienen la publicación de la generación completa. El tratamiento de
cuarentena y de entregas operativas inválidas pertenece a la etapa 3.

## Políticas temporales explícitas

Los CSV no documentan disponibilidad, revisiones ni entregas: **todas las políticas
de esta sección son supuestos de simulación**, no hechos históricos de Favorita.
Se versionan en `configs/availability.yaml`.

Zona del negocio: `America/Guayaquil`, acorde con las ubicaciones continentales
del catálogo. Los manifiestos usan instantes UTC con `Z`; los cortes deben incluir
zona horaria. Se rechazan cortes sin zona.

| Fuente | Disponibilidad base simulada |
|---|---|
| Ventas | día siguiente a la fecha observada, 06:00 local |
| Transacciones | lunes 09:00 local, a partir del día siguiente al hecho; publica un lote de archivos diarios |
| Petróleo | siguiente día hábil lunes–viernes, 18:00 local; no se modelan feriados bursátiles externos |
| Feriados planificados | primer lunes 08:00 a partir de fecha de evento menos 30 días; anticipación efectiva de 24 a 30 días |
| Eventos de tipo `Event` | primer lunes 08:00 a partir del día siguiente al evento, sin anticipación |
| Tiendas | snapshot único con referencia y disponibilidad inicial `2013-01-01` a las 00:00 local |

Los cambios históricos de ciudad, tipo, clúster o fecha de apertura no están en el
archivo de tiendas. Se asume explícitamente que el snapshot describe una dimensión
constante desde la referencia configurada; no se afirma que esto refleje su vigencia
real. No se generan actualizaciones ficticias de tiendas.

Un archivo de feriados agrupa todos los eventos de su fecha. Si mezcla un evento
planificado con uno no anticipable, espera hasta que todos estén disponibles; es
una política conservadora que evita revelar el evento inesperado por adelantado.
Los eventos con referencia futura pueden estar disponibles antes del corte si son
planificados; ventas, transacciones y petróleo siempre se publican después del hecho.

### Demoras y revisiones

Una función SHA-256 de semilla, fuente, fecha de referencia y escenario selecciona
particiones, sin usar reloj ni aleatoriedad dependiente del orden de procesamiento.
Los porcentajes configurados son umbrales de selección, no cuotas exactas.

- El 5% aproximado de particiones de ventas y transacciones se retrasa 3 días
  calendario; el 5% de petróleo, 2 días. Una entrega retrasada puede caer fuera
  del horario regular: representa una recuperación extraordinaria.
- Se seleccionan para corrección aproximadamente 5% de fechas de ventas y 3%
  de transacciones y petróleo, siempre que exista alguna medida positiva.
- La revisión 1 reduce al 90% la primera medida positiva en orden canónico de clave.
  En transacciones el resultado se trunca a entero no negativo. No se alteran ceros
  ni nulos para fabricar correcciones.
- La revisión 2 llega 7 días después de la disponibilidad efectiva de la revisión 1
  y restaura exactamente los valores del CSV original para esa partición.
- Ambas revisiones contienen la partición diaria completa. La segunda **reemplaza**
  a la primera; no es un delta que deba sumarse. Nunca se modifica un archivo publicado.
- Un archivo con solo ceros o petróleo vacío no recibe una revisión artificial sin cambios.

Esta técnica trata los CSV descargados como la versión final de referencia y crea
un estado provisional sintético. No reconstruye correcciones históricas reales ni
simula eliminaciones de filas o cambios de clave, que quedan fuera de esta versión.

## Carga histórica inicial y bandeja

```text
data/
├── original/                   # intacto
└── simulation/
    ├── manifest.json           # catálogo y lote de carga inicial
    ├── historical/
    │   └── <fuente>/<fecha>/r0001.csv + r0001.json
    └── source_inbox/
        └── <fuente>/<fecha>/r0001.csv + r0001.json
```

La fecha inicial es `2017-01-01T00:00:00-05:00`. `historical/` contiene todas las
entregas conocidas hasta ese corte, incluidas revisiones ya conocidas, en lugar de
copiar todas las filas cuya fecha de referencia sea anterior. Puede incluir eventos
planificados futuros y omitir ventas antiguas que todavía no se entregaron.

El manifiesto, ordenado por disponibilidad, fuente, referencia y revisión, define
el orden de carga histórica. Es un lote de entrada listo para el futuro consumidor,
no una base operativa ya ingerida. `available(corte, area="historical")` enumera ese
lote; `available(corte, latest=True)` selecciona el recibo vigente de cada partición
entre ambas áreas. Las versiones previas siguen conservadas para reproducción.

No existe un CSV vacío para cada fecha ausente. La ausencia de una entrega no
demuestra si no hubo actividad, si faltan datos o si no se ha publicado todavía.
La evaluación de completitud operacional se implementará en la etapa 3.

Cada CSV tiene un sobre JSON con fuente, referencia, disponibilidad programada y
efectiva, revisión, ID estable, vínculo a la versión corregida, área, filas,
checksum del payload, checksum del original, checksum del contrato e indicadores
de demora y estado provisional. El catálogo incluye checksum del sobre, hashes de
configuración, semilla, política completa y un identificador de generación.

## Separación entre productor y consumidor

`simulate` actúa como **sistema externo**, escribe la generación antes de su consumo
y después no modifica las entregas. `DeliveryCatalog` es una API de lectura: no
crea marcas de consumo, mueve archivos ni escribe en `historical` o `source_inbox`.
Su método `read` exige `as_of` y rechaza leer un payload que aún no estaba disponible.
El filtrado respeta disponibilidad, no solo la fecha del hecho.

La bandeja se precarga con el escenario completo; el paso del tiempo se representa
con metadatos, no con un servicio que copie archivos usando el reloj real. La auditoría
`verify-source` puede examinar también entregas futuras; no produce entradas para un
modelo. En la futura infraestructura operativa se montará `source_inbox` con `:ro`.
Esta etapa no cambia permisos del sistema ni inicia contenedores: el aislamiento
actual es la separación de API y roles, comprobada con huellas y tiempos de modificación.

## Determinismo e idempotencia

La identidad combina versión del generador y hashes de los cinco originales,
contratos y políticas temporales. No incorpora rutas absolutas ni hora de ejecución.
Las filas se ordenan por clave y las serializaciones JSON/CSV son canónicas.

La generación se construye en un directorio temporal adyacente, valida todas las
fuentes y verifica los SHA-256 originales antes y después. Solo entonces se publica
el directorio completo mediante renombrado. Los temporales se eliminan ante un error.

Si la salida existe con la misma identidad, se verifican sobres, payloads y archivos
esperados y se devuelve la generación existente sin reescribirla. Si hay corrupción,
archivos extra o una identidad diferente, se falla en lugar de sobrescribir o reparar
el origen. Para cambiar parámetros se genera otra ruta con `--output`; no se borra
la generación previa. No se deben ejecutar productores concurrentes sobre la misma
ruta de salida; un productor por generación es un supuesto de operación de esta etapa.

Las huellas aseguran integridad local, no autenticidad frente a un atacante capaz
de reescribir el catálogo completo. El versionado externo DVC se incorpora en su etapa.

## Pruebas

Las pruebas sintéticas cubren tipos, claves, relaciones, nulos, ceros y ausencias,
eventos simultáneos y geográficos, retrasos, frecuencias, correcciones entre histórico
y bandeja, filtrado temporal, rechazo de lectura futura, checksum, rutas inseguras,
fallas sin publicación parcial, determinismo entre rutas e idempotencia sin reescritura.
Se comparan hashes y tiempos de modificación para verificar que ni el consumidor
ni una reejecución modifican el origen.

Los resultados reales de ejecución se registran en `etapa2_resultados.md`.
