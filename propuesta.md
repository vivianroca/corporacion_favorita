# Propuesta del Laboratorio 1

## Reproducibilidad y Orquestación de un Producto de ML — Motor de Reposición de Inventario

Propuesta basada en la lectura de las cuatro páginas de `Laboratorio_1_PD_26.pdf` y en la inspección inicial del entorno. Este documento describe el trabajo propuesto; no implica que los componentes estén implementados.

## 1. Objetivo

Construir un producto que transforme ventas diarias de Corporación Favorita en pronósticos de demanda y recomendaciones semanales de pedido por tienda y familia. Cada publicación debe poder rastrearse hasta su código, datos, configuración y modelo, y reproducirse posteriormente.

El diseño debe contemplar datos que llegan por partes, fuentes con distintas frecuencias, entregas tardías y correcciones posteriores. Toda predicción usará únicamente la información disponible al momento de emitirla.

## 2. Diagnóstico inicial

| Componente | Resultado observado |
|---|---|
| Directorio `lab1` | Inicialmente vacío; posteriormente se agregó el PDF del laboratorio |
| Git | 2.54.0; todavía no se inicializó un repositorio |
| Arquitectura del entorno | arm64 |
| Python local | 3.14.4 |
| Entorno `../ejemplo3/.venv` | Python 3.14.4, confirmado en `pyvenv.cfg` |
| Python 3.12 | No encontrado en PATH ni en las ubicaciones habituales revisadas |
| Docker CLI | 29.9.2 |
| Docker Compose | v5.6.0 |
| DVC | No encontrado en PATH ni en el entorno indicado |
| pytest | No encontrado en PATH ni en el entorno indicado |
| Imágenes Docker locales | No verificadas: el acceso al socket de Docker fue denegado |

La versión real de Python difiere del contexto inicial. Se propone preparar un entorno Python 3.12 propio de `lab1`, sin modificar el entorno del otro proyecto.

Las siguientes imágenes fueron informadas como disponibles, pero su existencia, arquitectura y contenido siguen pendientes de comprobación:

- `demanda-bicis-airflow:3.3.2`
- `apache/airflow:3.3.2-python3.12`
- `postgres:16`
- `ghcr.io/mlflow/mlflow:v3.17.2`

## 3. Requisitos incorporados desde el PDF

- Usar `train.csv`, `stores.csv`, `holidays_events.csv`, `oil.csv` y `transactions.csv`.
- Excluir `test.csv` y `sample_submission.csv`.
- Construir una carga histórica inicial y una bandeja de entregas por fecha y fuente.
- Tratar la bandeja como un sistema externo: el pipeline la lee y nunca la modifica.
- Diferenciar la fecha del hecho de la fecha en que la información estuvo disponible.
- Soportar distintas frecuencias, retrasos y revisiones de las fuentes.
- Publicar pronósticos diarios con incertidumbre para un horizonte definido.
- Derivar pedidos de pronósticos y costos en configuración versionada.
- Comparar un modelo ML contra un baseline con el mismo esquema temporal y lograr una mejora.
- Definir métricas técnicas, una métrica de costo de negocio y un criterio de reemplazo del modelo vigente.
- Versionar entradas, datos procesados, modelos y pronósticos con DVC y un remoto.
- Ejecutar Airflow 3 mediante Docker Compose, con tareas idempotentes, backfill y reprocesamiento.
- Detener datos inválidos antes de contaminar resultados y manejar situaciones esperadas sin fallas innecesarias.
- Usar ramas y Pull Requests, proteger la rama principal y ejecutar pytest mediante GitHub Actions en cada PR.
- Mantener `AGENTS.md`, `README.md` y `DECISIONES.md`.
- Entregar un repositorio accesible, el tag `entrega-lab1` y evidencias de funcionamiento y reproducción histórica.

## 4. Diseño temporal y manejo de correcciones

Cada entrega tendrá fecha o periodo de referencia, momento de disponibilidad, identificador de revisión, checksum, fuente y resultado de validación.

Para cada fecha de corte se seleccionarán únicamente las versiones conocidas hasta ese momento. La regla aplica también a promociones, transacciones, petróleo y feriados: no se utilizará información futura solo porque esté presente en los CSV originales.

La simulación tendrá reglas documentadas de frecuencia, anticipación y retraso por fuente. El generador preparará la bandeja antes de su consumo; el pipeline operativo accederá a ella en modo de solo lectura.

Una corrección podrá actualizar los datos actuales y provocar un reprocesamiento, pero no sobrescribirá silenciosamente un pronóstico publicado. Se distinguirán:

- **Reproducción histórica:** reconstrucción de lo publicado usando sus datos, configuración y modelo originales.
- **Resultado revisado:** nueva publicación con identificador propio y trazabilidad hacia la corrección.

El seguimiento comparará las predicciones originales con ventas ya disponibles e identificará la versión de las ventas utilizada en la evaluación.

## 5. Estructura propuesta

```text
lab1/
├── README.md
├── DECISIONES.md
├── AGENTS.md
├── pyproject.toml
├── requirements.lock
├── Makefile
├── .gitignore
├── .env.example
├── params.yaml
├── dvc.yaml
├── dvc.lock
├── configs/
│   ├── sources.yaml
│   ├── availability.yaml
│   ├── forecasting.yaml
│   ├── costs.yaml
│   └── promotion.yaml
├── src/reposicion/
│   ├── config.py
│   ├── cli.py
│   ├── source_simulator.py
│   ├── ingestion.py
│   ├── validation.py
│   ├── snapshots.py
│   ├── features.py
│   ├── forecasting.py
│   ├── inventory.py
│   ├── evaluation.py
│   ├── registry.py
│   └── publication.py
├── dags/
├── docker/
│   ├── Dockerfile.airflow
│   └── compose.yaml
├── data/
│   ├── original/
│   ├── source_inbox/
│   ├── landing/
│   ├── quarantine/
│   └── processed/
├── models/
├── forecasts/
├── orders/
├── reports/
├── manifests/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── scenarios/
├── docs/
│   └── evidence/
└── .github/workflows/
    └── ci.yml
```

`source_inbox/` representa el sistema externo; `landing/` conserva lo recibido por el producto. Los manifiestos relacionarán cada publicación con el commit, las versiones DVC, la configuración, las fuentes y el modelo.

Git almacenará código, documentación, configuración y metadatos DVC. Los datos y modelos, incluidos los pronósticos, quedarán fuera de Git. Las pruebas generarán datos sintéticos pequeños desde código.

La lógica residirá en módulos Python probados. La CLI y los DAGs invocarán esa misma lógica; los DAGs solo orquestarán.

## 6. Pronóstico, pedidos y evaluación

- **Baseline:** pronóstico estacional semanal.
- **Modelo ML:** modelo global por tienda y familia con rezagos y estadísticas construidas con información disponible.
- **Incertidumbre:** cuantiles para representar distintos niveles de demanda.
- **Validación:** múltiples cortes temporales iguales para todos los modelos comparados.
- **Métricas:** MAE/WAPE, pérdida de cuantiles y costo de faltante y excedente. Se definirán reglas para denominadores nulos y series sin ventas.

El pedido dependerá de la demanda durante el horizonte de reposición y de los costos configurados. Como punto de partida, el cuantil objetivo se relacionará con:

```text
q = costo_faltante / (costo_faltante + costo_excedente)
```

Para pedidos de varios días se estimará la distribución de la demanda acumulada: sumar cuantiles diarios no garantiza obtener el cuantil del total.

Los archivos exigidos no aportan existencias ni pedidos en tránsito. Se documentará una política simplificada de reposición con supuestos explícitos sobre inventario, plazo de entrega y merma. Las ventas observadas también pueden subestimar la demanda cuando hubo faltantes.

Los costos serán externos al código y estarán versionados. Se demostrará que cambiarlos modifica la recomendación sin modificar la implementación.

La promoción del candidato dependerá principalmente del costo de negocio en validación, con umbrales configurados. Si no supera al baseline o al modelo vigente según el criterio definido, se conservará el vigente y continuará el trabajo de modelado hasta cumplir el requisito de mejora.

## 7. Dependencias

### Encontradas en el entorno compartido

| Grupo | Paquetes y versiones observadas |
|---|---|
| Datos | NumPy 2.5.4, pandas 3.1.0, PyArrow 25.0.1 |
| Modelado | SciPy 1.18.1, scikit-learn 1.9.1, joblib 1.6.0 |
| Configuración | PyYAML 6.0.3, Pydantic 2.14.1, python-dotenv 1.2.4 |
| Seguimiento y almacenamiento | MLflow 3.17.2, SQLAlchemy 2.1.6 |
| Visualización | Matplotlib 3.11.2 |

Estas versiones son un inventario, no un conjunto validado para Python 3.12. El entorno definitivo tendrá versiones fijadas y comprobadas.

### Por incorporar cuando se autorice

- DVC y el complemento del remoto elegido, si corresponde.
- pytest; pytest-cov será opcional.
- Ruff para revisión estática.
- psycopg únicamente si el código del producto necesita acceso directo a PostgreSQL.

Airflow quedará dentro de Docker. Statsmodels, XGBoost y LightGBM no están instalados y no son necesarios para la primera implementación propuesta. MLflow es opcional: primero se garantizará la trazabilidad con Git, DVC y manifiestos.

## 8. Infraestructura aislada y reutilización de imágenes

- Usar `apache/airflow:3.3.2-python3.12` como base de una imagen propia del laboratorio.
- Usar `postgres:16` con una instancia, credenciales, base de metadatos y volumen nuevos.
- Definir un proyecto Compose `lab1` con red propia, volúmenes propios y puertos configurables.
- Comenzar con LocalExecutor para limitar componentes.
- Mantener `demanda-bicis-airflow:3.3.2` fuera de la implementación inicial por su contenido no verificado y posible acoplamiento al otro proyecto.
- No reutilizar archivos, bases, DAGs, redes ni volúmenes del proyecto de bicicletas.
- Verificar arquitectura y registrar identificadores o digests de las imágenes utilizadas.
- Fijar dependencias y comprobar compatibilidad entre el producto y Airflow.

El remoto DVC será obligatorio, persistente y documentado. Se definirán su ubicación, credenciales y acceso para reproducción; la caché local no sustituirá al remoto. También se documentará la reconstrucción desde los CSV originales de Kaggle.

Las credenciales se proporcionarán mediante variables de entorno. Las fechas de corte, horizonte, semillas, costos, rutas y política de promoción se definirán en configuración externa.

## 9. Plan de implementación

| Etapa | Resultado verificable |
|---|---|
| 1. Base del proyecto | Python 3.12, Git, estructura, contexto del agente, configuración y dependencias fijadas |
| 2. Contratos y simulación | Lectura de los cinco CSV, histórico inicial, bandeja y reglas de disponibilidad y corrección |
| 3. Ingesta temporal | Validación, cuarentena, deduplicación y snapshots reproducibles por corte |
| 4. Modelos y pedidos | Baseline, ML, incertidumbre, validación temporal, costos y criterio de promoción |
| 5. DVC y publicación | Remoto operativo, artefactos versionados y reproducción demostrada de un pronóstico pasado |
| 6. Airflow | Ingesta, preparación, pronóstico semanal, pedidos y seguimiento; backfill y correcciones |
| 7. Robustez y CI | pytest en PRs y escenarios de retrasos, duplicados, correcciones, datos inválidos y reejecuciones |
| 8. Entrega | README desde cero, decisiones justificadas, evidencias, protección de rama y tag de entrega |

GitHub Actions ejecutará pruebas con Python 3.12 y datos sintéticos pequeños, sin depender de la descarga del conjunto completo. Las verificaciones de datos y modelos completas se ejecutarán mediante el flujo reproducible.

## 10. Criterios de comprobación final

- Un clon nuevo puede reconstruir el producto a partir de los cinco CSV originales siguiendo el README.
- La bandeja externa permanece intacta durante la operación.
- Una reejecución no duplica ni altera indebidamente los resultados.
- Un backfill conserva las reglas de disponibilidad histórica.
- Las correcciones producen nuevas versiones trazables.
- Los datos inválidos no contaminan publicaciones.
- Las ausencias y retrasos esperados reciben el tratamiento documentado.
- Los pronósticos incluyen incertidumbre y usan exclusivamente información disponible al corte.
- El modelo ML mejora al baseline bajo el mismo protocolo temporal.
- Cambiar costos en configuración cambia los pedidos sin modificar código.
- Un pronóstico pasado puede reproducirse mediante su commit y versiones DVC, con comandos y resultados documentados.
- Se conservan evidencias de Airflow, comparación de modelos y seguimiento.
- El repositorio es accesible al equipo docente y contiene el tag `entrega-lab1`.

La comprobación final simulará el procedimiento del docente: clonar, colocar los CSV originales, levantar el producto y procesar un periodo sin intervención manual.

## 11. Estado y autorización

Esta propuesta incorpora disponibilidad temporal, revisiones de datos y publicaciones reproducibles desde el inicio. La implementación queda pendiente de autorización. La creación de este documento no instala dependencias, inicializa repositorios ni levanta infraestructura.
