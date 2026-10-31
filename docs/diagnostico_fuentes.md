# Diagnóstico inicial de las fuentes de Corporación Favorita

## Alcance y método

Lectura completa de los cinco CSV requeridos, con Python estándar y SQLite en memoria. No se usan muestras. No se modifican originales ni se entrenan modelos. Los CSV no declaran tipos: los tipos siguientes son inferidos y comprobados sobre todos los valores no vacíos. Nulo significa celda vacía o compuesta solo por espacios.

Los SHA-256 se calculan antes y después para comprobar que los archivos no cambiaron durante el diagnóstico. Esto verifica estabilidad local, no autenticidad frente a Kaggle: no se dispone de un manifiesto externo de referencia.

Reproducir: `.venv/bin/python scripts/diagnosticar_fuentes.py`. El script reemplaza únicamente este informe; necesita memoria para las tablas temporales.

## Integridad y dimensiones

| Archivo | Bytes | Filas | Columnas | Filas con ancho incorrecto |
|---|---:|---:|---:|---:|
| train.csv | 121,800,373 | 3,000,888 | 6 | 0 |
| stores.csv | 1,387 | 54 | 5 | 0 |
| holidays_events.csv | 22,309 | 350 | 6 | 0 |
| oil.csv | 20,580 | 1,218 | 2 | 0 |
| transactions.csv | 1,552,637 | 83,488 | 3 | 0 |

## Perfil por fuente

### train.csv

| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |
|---|---|---:|---:|---:|
| id | entero | 0 | 0.0000% | 0 |
| date | fecha ISO YYYY-MM-DD | 0 | 0.0000% | 0 |
| store_nbr | entero | 0 | 0.0000% | 0 |
| family | texto | 0 | 0.0000% | 0 |
| sales | real | 0 | 0.0000% | 0 |
| onpromotion | entero | 0 | 0.0000% | 0 |

- Duplicados exactos, como filas excedentes: **0**.
- Duplicados de la clave candidata `date, store_nbr, family`: **0** filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado.
- Duplicados de `id`: **0**.
- Ventas con parte fraccionaria: **462,113**. Ventas cero: **31.30%** de las filas.
- `onpromotion` es un conteo entero; no debe reducirse a un booleano sin justificar la pérdida de información.

| Columna | Mínimo | Máximo | Negativos | Ceros |
|---|---:|---:|---:|---:|
| id | 0 | 3000887 | 0 | 1 |
| store_nbr | 1 | 54 | 0 | 0 |
| sales | 0.0 | 124717.0 | 0 | 939,130 |
| onpromotion | 0 | 741 | 0 | 2,389,559 |

Valores y frecuencias de `family`: `AUTOMOTIVE`: 90,936; `BABY CARE`: 90,936; `BEAUTY`: 90,936; `BEVERAGES`: 90,936; `BOOKS`: 90,936; `BREAD/BAKERY`: 90,936; `CELEBRATION`: 90,936; `CLEANING`: 90,936; `DAIRY`: 90,936; `DELI`: 90,936; `EGGS`: 90,936; `FROZEN FOODS`: 90,936; `GROCERY I`: 90,936; `GROCERY II`: 90,936; `HARDWARE`: 90,936; `HOME AND KITCHEN I`: 90,936; `HOME AND KITCHEN II`: 90,936; `HOME APPLIANCES`: 90,936; `HOME CARE`: 90,936; `LADIESWEAR`: 90,936; `LAWN AND GARDEN`: 90,936; `LINGERIE`: 90,936; `LIQUOR,WINE,BEER`: 90,936; `MAGAZINES`: 90,936; `MEATS`: 90,936; `PERSONAL CARE`: 90,936; `PET SUPPLIES`: 90,936; `PLAYERS AND ELECTRONICS`: 90,936; `POULTRY`: 90,936; `PREPARED FOODS`: 90,936; `PRODUCE`: 90,936; `SCHOOL AND OFFICE SUPPLIES`: 90,936; `SEAFOOD`: 90,936.

### stores.csv

| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |
|---|---|---:|---:|---:|
| store_nbr | entero | 0 | 0.0000% | 0 |
| city | texto | 0 | 0.0000% | 0 |
| state | texto | 0 | 0.0000% | 0 |
| type | texto | 0 | 0.0000% | 0 |
| cluster | entero | 0 | 0.0000% | 0 |

- Duplicados exactos, como filas excedentes: **0**.
- Duplicados de la clave candidata `store_nbr`: **0** filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado.

| Columna | Mínimo | Máximo | Negativos | Ceros |
|---|---:|---:|---:|---:|
| store_nbr | 1 | 54 | 0 | 0 |
| cluster | 1 | 17 | 0 | 0 |

Valores y frecuencias de `city`: `Ambato`: 2; `Babahoyo`: 1; `Cayambe`: 1; `Cuenca`: 3; `Daule`: 1; `El Carmen`: 1; `Esmeraldas`: 1; `Guaranda`: 1; `Guayaquil`: 8; `Ibarra`: 1; `Latacunga`: 2; `Libertad`: 1; `Loja`: 1; `Machala`: 2; `Manta`: 2; `Playas`: 1; `Puyo`: 1; `Quevedo`: 1; `Quito`: 18; `Riobamba`: 1; `Salinas`: 1; `Santo Domingo`: 3.

Valores y frecuencias de `state`: `Azuay`: 3; `Bolivar`: 1; `Chimborazo`: 1; `Cotopaxi`: 2; `El Oro`: 2; `Esmeraldas`: 1; `Guayas`: 11; `Imbabura`: 1; `Loja`: 1; `Los Rios`: 2; `Manabi`: 3; `Pastaza`: 1; `Pichincha`: 19; `Santa Elena`: 1; `Santo Domingo de los Tsachilas`: 3; `Tungurahua`: 2.

Valores y frecuencias de `type`: `A`: 9; `B`: 8; `C`: 15; `D`: 18; `E`: 4.

### holidays_events.csv

| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |
|---|---|---:|---:|---:|
| date | fecha ISO YYYY-MM-DD | 0 | 0.0000% | 0 |
| type | texto | 0 | 0.0000% | 0 |
| locale | texto | 0 | 0.0000% | 0 |
| locale_name | texto | 0 | 0.0000% | 0 |
| description | texto | 0 | 0.0000% | 0 |
| transferred | booleano True/False | 0 | 0.0000% | 0 |

- Duplicados exactos, como filas excedentes: **0**.
- Duplicados de la clave candidata `date, type, locale, locale_name, description, transferred`: **0** filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado.

Valores y frecuencias de `type`: `Additional`: 51; `Bridge`: 5; `Event`: 56; `Holiday`: 221; `Transfer`: 12; `Work Day`: 5.

Valores y frecuencias de `locale`: `Local`: 152; `National`: 174; `Regional`: 24.

Valores y frecuencias de `locale_name`: `Ambato`: 12; `Cayambe`: 6; `Cotopaxi`: 6; `Cuenca`: 7; `Ecuador`: 174; `El Carmen`: 6; `Esmeraldas`: 6; `Guaranda`: 12; `Guayaquil`: 11; `Ibarra`: 7; `Imbabura`: 6; `Latacunga`: 12; `Libertad`: 6; `Loja`: 6; `Machala`: 6; `Manta`: 6; `Puyo`: 6; `Quevedo`: 6; `Quito`: 13; `Riobamba`: 12; `Salinas`: 6; `Santa Elena`: 6; `Santo Domingo`: 6; `Santo Domingo de los Tsachilas`: 6.

Valores y frecuencias de `transferred`: `False`: 338; `True`: 12.

### oil.csv

| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |
|---|---|---:|---:|---:|
| date | fecha ISO YYYY-MM-DD | 0 | 0.0000% | 0 |
| dcoilwtico | real | 43 | 3.5304% | 0 |

- Duplicados exactos, como filas excedentes: **0**.
- Duplicados de la clave candidata `date`: **0** filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado.

| Columna | Mínimo | Máximo | Negativos | Ceros |
|---|---:|---:|---:|---:|
| dcoilwtico | 26.19 | 110.62 | 0 | 0 |

### transactions.csv

| Columna | Tipo inferido | Nulos | % nulos | Valores inválidos |
|---|---|---:|---:|---:|
| date | fecha ISO YYYY-MM-DD | 0 | 0.0000% | 0 |
| store_nbr | entero | 0 | 0.0000% | 0 |
| transactions | entero | 0 | 0.0000% | 0 |

- Duplicados exactos, como filas excedentes: **0**.
- Duplicados de la clave candidata `date, store_nbr`: **0** filas excedentes. La clave es una hipótesis del diagnóstico, no un contrato aprobado.

| Columna | Mínimo | Máximo | Negativos | Ceros |
|---|---:|---:|---:|---:|
| store_nbr | 1 | 54 | 0 | 0 |
| transactions | 5 | 8359 | 0 | 0 |

## Cobertura temporal

| Fuente | Primera fecha | Última fecha | Fechas distintas | Días calendario del intervalo | Fechas sin fila |
|---|---|---|---:|---:|---:|
| train | 2013-01-01 | 2017-08-15 | 1,684 | 1,688 | 4 |
| stores | No aplica | No aplica | — | — | — |
| holidays_events | 2012-03-02 | 2017-12-26 | 312 | 2,126 | 1,814 |
| oil | 2013-01-01 | 2017-08-31 | 1,218 | 1,704 | 486 |
| transactions | 2013-01-01 | 2017-08-15 | 1,682 | 1,688 | 6 |

Fechas ausentes se cuentan dentro del intervalo de cada fuente; no equivalen automáticamente a errores. En feriados se registran eventos, por lo que los días sin fila son esperables. `stores` no contiene fechas de apertura, cierre ni vigencia de sus atributos.

- **train**: primeras fechas sin fila: 2013-12-25, 2014-12-25, 2015-12-25, 2016-12-25; distribución por día de semana: {'Wednesday': 1, 'Thursday': 1, 'Friday': 1, 'Sunday': 1}.
- **transactions**: primeras fechas sin fila: 2013-12-25, 2014-12-25, 2015-12-25, 2016-01-01, 2016-01-03, 2016-12-25; distribución por día de semana: {'Wednesday': 1, 'Thursday': 1, 'Friday': 2, 'Sunday': 2}.
- **oil**: primeras fechas sin fila: 2013-01-05, 2013-01-06, 2013-01-12, 2013-01-13, 2013-01-19, 2013-01-20, 2013-01-26, 2013-01-27, 2013-02-02, 2013-02-03, 2013-02-09, 2013-02-10, 2013-02-16, 2013-02-17, 2013-02-23, 2013-02-24, 2013-03-02, 2013-03-03, 2013-03-09, 2013-03-10; distribución por día de semana: {'Saturday': 243, 'Sunday': 243}.

## Relaciones, granularidad y cobertura cruzada

- `stores.store_nbr` es la dimensión de tienda: **54 tiendas** en ventas. Filas de ventas con tienda desconocida: **0**; de transacciones: **0**.
- `train`: granularidad diaria por tienda y familia, con **33 familias**. Sobre sus 1,684 fechas observadas, el producto cartesiano esperado es 3,000,888 combinaciones; se observaron 3,000,888 filas. Filas por fecha: mínimo 1,782, máximo 1,782; filas por serie tienda–familia: mínimo 1,684, máximo 1,684.
- `transactions` se relaciona por `(date, store_nbr)`, sin desglose por familia. Sus cifras no deben sumarse después de replicarlas por familia al unirlas con ventas.
- Pares tienda–fecha de ventas sin transacciones: **7,448**, de los cuales **118** tienen ventas agregadas positivas. Filas de transacciones sin par en ventas: **0**. Ausencia no equivale a cero.
- `oil` se relaciona por fecha y es una variable común a todas las tiendas. Fechas observadas de ventas sin fila de petróleo: **481**; con fila de petróleo pero valor vacío: **40**. Total sin precio observado al unir por fecha: **521** fechas.
- `holidays_events` contiene eventos, no una fila única por fecha. Los nacionales se aplican a todas las tiendas; los regionales se relacionan con `stores.state` y los locales con `stores.city`. Unir solo por fecha puede multiplicar filas y aplicar eventos a tiendas que no corresponden. Deben agregarse indicadores por tienda–fecha.
- Nombres de eventos locales sin ciudad correspondiente: ninguno; regionales sin estado correspondiente: ninguno.
- Fechas con más eventos (fecha, cantidad): 2014-06-25: 4; 2012-06-25: 3; 2013-06-25: 3; 2015-06-25: 3; 2016-06-25: 3; 2017-06-25: 3; 2012-07-03: 2; 2012-12-22: 2; 2012-12-24: 2; 2012-12-31: 2.
- `transferred` y el tipo de evento requieren reglas explícitas: un feriado trasladado no debe tratarse automáticamente como descanso efectivo en su fecha original.

## Hallazgos y decisiones pendientes para los contratos

1. Las fechas del archivo representan el hecho o calendario, **no el momento de disponibilidad**. Los CSV no proporcionan fecha de entrega, revisión ni historial de correcciones. Estos metadatos deberán definirse en la simulación; no pueden inferirse como hechos observados.
2. Documentar los días sin ventas registradas y distinguir ausencia de fila, venta cero y tienda sin actividad. La presencia de ceros no demuestra que hubiera stock disponible.
3. Definir políticas para precios de petróleo ausentes y frecuencia de entrega. Cualquier relleno deberá respetar la disponibilidad temporal; no interpolar usando valores futuros.
4. Definir cuándo se conocen promociones, transacciones y calendarios. Que existan valores para una fecha posterior al corte en los archivos completos no autoriza su uso predictivo.
5. Ventas es una magnitud real: no imponer integridad entera a `sales`. Validar por separado enteros, no negatividad, claves, categorías, cambios de esquema y correcciones.
6. Estos controles son un diagnóstico del snapshot actual. Las claves candidatas y categorías observadas deben evaluarse antes de convertirse en contratos; futuras categorías o tiendas no deben rechazarse sin una regla de negocio documentada.
7. No existen inventario, pedidos en tránsito ni costos en estas fuentes. No permiten calcular una reposición física sin supuestos externos explícitos.
8. Los archivos `test.csv` y `sample_submission.csv`, aunque estén en la carpeta, se excluyen del análisis y del laboratorio.

## Huellas de los originales

| Archivo | SHA-256 antes y después |
|---|---|
| train.csv | `99a1b7f4241821df10fa71f23abdd71c634f71f901e3cab1400c0f0c583f862c` |
| stores.csv | `af503b2bce11d7906d249f81cc0598f10e2addcc9f6c59aa2d95c9f2652c296b` |
| holidays_events.csv | `81a183d6c4d691b57f84a0fde6bbf734a5b3c36a74b97378bf33a592648e2999` |
| oil.csv | `944b23b857580f9d804399346fd3ed69bffcb7facfd98c55fdb408b8d057cca7` |
| transactions.csv | `e116384a6981af74932832436aa2f6a43121f77ca81accc44e3a5160158ca03c` |

Las cinco huellas coinciden antes y después. Los originales permanecen excluidos de Git.
