# Pruebas

pytest 9.2.0 está instalado en `.venv` con Python 3.12 y configurado en
`pyproject.toml`. Las dependencias están bloqueadas en `requirements.lock`.
Ejecutar desde la raíz: `.venv/bin/python -m pytest -q`.

La suite contiene 120 casos; la última ejecución local aprobó todos.

Se cubren contratos, relaciones, ceros/nulos/ausencias, ámbitos geográficos,
disponibilidad, demoras, revisiones, idempotencia, integridad, publicación sin
salidas parciales, landing, snapshots históricos, cuarentena y CLI. No se necesita
Kaggle ni servicios externos. La evidencia de integración real del DAG está en
`docs/etapa3_resultados.md`; se ejecutó por el scheduler con las entregas existentes.
Las pruebas de costos y de modelos se agregarán cuando se autorice ese comportamiento.

El sondeo incremental se prueba con liberación progresiva, ciclos vacíos, lectura
exclusiva de archivos nuevos, reemplazo de revisiones, ledger persistente, conflicto
de checksums, concurrencia, recuperación antes/después del commit y separación del
backfill. La prueba real automática se registra en `docs/ingesta_automatica_resultados.md`.

La auditoría previa a publicación incluye pruebas de rutas prohibidas, secretos,
tokens, claves, tamaño, symlinks y plantillas sin credenciales. GitHub Actions
ejecuta la suite completa en cada PR a main sin datos reales ni servicios externos.

La auditoría permite únicamente los cinco punteros DVC requeridos, valida sus
campos y rechaza datos disfrazados de metadata y configuración privada. Otra prueba
comprueba que Git permite recorrer los padres de los punteros sin exponer CSV.
La recuperación real desde storage se ejecuta por separado con
`scripts/verificar_recuperacion_dvc.py`, en un clon y caché nuevos.
