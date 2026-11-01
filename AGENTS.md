# Reglas del proyecto

- Trabajar exclusivamente en `lab1`. No leer ni reutilizar código, datos, bases, DAGs, redes, volúmenes o entornos del proyecto de bicicletas.
- Usar Python 3.12 y `.venv` dentro de este directorio. No modificar `../ejemplo3/.venv` ni instalar paquetes globalmente.
- El alcance autorizado comprende las etapas 1 a 3: base, diagnóstico, contratos, simulación existente, ingesta, validación y snapshots temporales con Airflow, PostgreSQL y MLflow exclusivos de lab1. No modificar originales ni regenerar la simulación existente. No entrenar modelos ni registrar experimentos ficticios.
- No crear módulos Python vacíos. Agregar módulos y pruebas cuando exista comportamiento que implementar.
- Mantener la lógica futura en `src/reposicion`; los DAGs solo orquestarán.
- Nunca usar información posterior a la fecha de corte. Documentar disponibilidad temporal, revisiones e idempotencia antes de implementar flujos.
- Mantener datos, modelos, pronósticos y secretos fuera de Git. Se autoriza inicializar DVC con Git y versionar únicamente los cinco CSV originales exigidos, usando storage en ~/dvc-storage/corporacion_favorita; no reutilizar ningún almacenamiento de otro proyecto.
- Versionar configuración sin credenciales; usar `.env` local y mantener `.env.example` sin secretos.
- Registrar decisiones y bloqueos en `DECISIONES.md`. No presentar una verificación pendiente como exitosa.
- Resolver y bloquear dependencias bajo Python 3.12; conservar hashes en `requirements.lock`. No generar un lock con otro intérprete para simular compatibilidad.
- Trabajar mediante ramas y PRs cuando Git esté disponible. No hacer commits, publicar ni cambiar protección de ramas sin indicación del usuario.
- No avanzar a la etapa 4 sin autorización. No detener ni modificar servicios de otros proyectos.
- Se autoriza sondeo automático cada cinco minutos y liberación progresiva en una bandeja nueva. Solo el publicador modifica esa bandeja; conservar intacta la simulación maestra y las publicaciones existentes. Mantener backfill separado del ledger vivo y registrar ejecuciones reales del scheduler.
- Se autoriza crear el repositorio público personal `vivianroca/corporacion_favorita`, preparar ramas, commits y PRs, y proteger main con PR y CI. Auditar archivos e historial antes de enviar; no hacer merge ni crear el tag entrega-lab1.
- Para DVC trabajar en feature/dvc desde main actualizado. Mantener test.csv y sample_submission.csv fuera del versionado; no agregar aún la simulación completa ni snapshots. Verificar recuperación en un espacio aislado sin borrar originales ni caché. No modificar DAGs ni entrenar modelos.
- Se autoriza implementar y evaluar únicamente el baseline estacional semanal de siete días por tienda/familia, con pruebas y registro real en MLflow existente. No modificar Airflow ni DVC para esta tarea. Mantener separados los cortes de emisión y evaluación, y los artefactos fuera de Git.
- Se autoriza RandomForestRegressor como primer candidato, con variables históricas disponibles por origen y evaluación idéntica al baseline. Registrar modelo, métricas, predicciones, comparación y gráficas en MLflow existente. No modificar Airflow ni DVC ni asignar champion.
- Para próximos entrenamientos usar el contexto training_run de src/reposicion/system_metrics.py: monitor oficial MLflow con psutil, CPU/RAM del host y duración. Conservar MAE/WAPE y gráficas. Esta preparación no autoriza reentrenar los modelos existentes ni modificar sus runs retrospectivamente.
- Se autoriza HistGradientBoostingRegressor como siguiente candidato y su registro real en Model Registry, con las mismas variables/cortes que Random Forest y MAE/WAPE, gráficas y System Metrics. No reentrenar candidatos anteriores, modificar Airflow/DVC ni asignar aliases de promoción.
- Se autoriza walk-forward con cuatro cortes semanales de enero de 2017 y horizonte siete, reentrenando RF/HGB en cada corte en runs nuevos. Mantener disponibilidad histórica y ventanas pareadas, registrar métricas por ventana y agregadas en MLflow y System Metrics en los entrenamientos. No seleccionar Champion ni modificar Airflow/DVC o los runs anteriores.
- Se autoriza la variante temporal v2 de RF/HGB: feriados por disponibilidad y alcance, rezagos excepcionales/ausentes e imputación por serie o misma familia. Conservar baseline, hiperparámetros y cuatro cortes; usar experimentos/runs nuevos. No modificar resultados anteriores, Airflow/DVC ni asignar Champion.
- Se autoriza CatBoostRegressor con configuración inicial fija y los cuatro folds/variables temporales v2, registrando modelo, parámetros, MAE/WAPE por fold/globales y System Metrics en runs nuevos. No optimizar hiperparámetros, reentrenar candidatos previos ni asignar Champion; conservar baseline, Airflow/DVC y experimentos anteriores.
- Se autoriza registrar los doce pipelines temporales v2 ya entrenados en Logged Models y Model Registry, asociados a sus runs y métricas originales. No ejecutar fit ni crear entrenamientos; conservar versión HGB anterior y métricas/historiales, sin Champion/aliases de promoción.
- Se autoriza publicar el código pendiente en ramas encadenadas, commits por etapa y tags Git lab1-*, con PR conjunto sin merge; excluir datos, artefactos y secretos, sin crear entrega-lab1.
- Se autoriza DVC exclusivamente para models/current: doce pipelines actuales y cuatro CBM de los cuatro folds temporales v2, sin entrenar ni alterar fuentes. Git solo admite models/current.dvc como metadato nuevo; no versionar simulación, snapshots, históricos u otros artefactos. Mantener storage dedicado y verificar recuperación sin borrar cachés.

- Se autoriza crear comparacion_modelos en MLflow a partir de los runs existentes temporal v2, con tablas/gráficas y runs comparables nuevos. No entrenar, sobrescribir fuentes, modificar Airflow/DVC ni asignar Champion.

- Se autoriza asignar champion a Random Forest existente, versión del último fold, conservando trazabilidad a runs, Git y DVC. Sin reentrenamiento ni alteración de pesos o métricas.

- Se autoriza lab1_pronostico_reposicion semanal configurable, consumiendo exclusivamente snapshots validados con corte explícito y Champion existente, sin reentrenar ni modificar el DAG de ingesta. Conservar backfill, linaje, versiones DVC y publicaciones inmutables; no hacer operaciones Git en esta tarea.

- Se autoriza lab1_seguimiento diario configurable y sus evaluaciones históricas: métricas de pronósticos publicados contra ventas de ingesta disponibles, incluyendo datos tardíos/correcciones y registro idempotente en MLflow. Conservar predicciones originales y ambos DAGs anteriores; sin reentrenamiento, cambios DVC ni operaciones Git.

- Se autoriza adaptar la orquestación de los tres DAGs con Assets nativos: ingesta cada tres horas, pronóstico exclusivamente semanal con sensor de snapshot confirmado y seguimiento por pronósticos O ventas. Conservar módulos de negocio, modelos, cortes/backfill e idempotencia; autorizar históricos mediante catálogo inicial y nuevas publicaciones solo mediante confirmación exitosa. Sin entrenamiento ni operaciones Git.

- Se autoriza el motor independiente de pedidos sobre cuantiles existentes con costos/plazo/inventario externos y escenarios conjuntos de demanda acumulada; documentar los supuestos no identificables. Sin modificar Airflow, Git, DVC o modelos existentes ni reentrenar; probar sensibilidad cambiando solo costos y conservar versiones de recomendaciones.

- Se autoriza integrar pedidos existentes al DAG de pronóstico con confirmación conjunta atómica, costos/inventario versionados e idempotencia. No modificar los otros DAGs ni los motores/modelos existentes; sin operaciones Git ni reentrenar. Mantener Asset sin emitir ante fallo de pedidos y probar histórico completo.

- Se autoriza corregir únicamente el reloj/sensor del DAG de pronóstico con replay histórico explícito, sin usar silenciosamente fechas físicas actuales. Conservar validación de 28 días, modelos, otros DAGs, idempotencia y backfill; probar el run programado real con la versión actual. No reentrenar ni hacer operaciones Git.

- Se autoriza versionar data/entrega mediante data/entrega.dvc y subir solo sus objetos a google_drive: una publicación histórica válida de pronósticos, pedidos y seguimiento con manifiestos/linaje, sin duplicados, credenciales, regeneración o entrenamiento. Mantener DAGs y originales; sin commit, staging ni push de Git. Solo excepción de metadatos en gitignore.

- Se autoriza restauración idempotente del Champion RF en MLflow vacío desde pesos DVC existentes y paquete adicional de parámetros/métricas/residuos/probe, sincronizando ambos punteros con google_drive. Sin entrenamiento, cambios de DAGs, originales ni modelo fuente; sin commit, push o merge Git. Probar en MLflow temporal aislado y conservar IDs fuente como trazabilidad.

- Se autoriza bootstrap reproducible por escenario desde cinco CSV: generación nueva en ruta propia o verificación/reutilización de la existente, bandeja progresiva, carga inicial y snapshots, infraestructura Docker aislada y restauración del Champion desde DVC. Solicitud explícita por Asset activa pronóstico fuera del cron semanal; seguimiento conserva OR. No entrenar ni alterar originales/resultados previos; sin commit, push ni merge Git. Documentar autenticación externa y probar instancias vacías/idempotencia.

- Se autoriza publicar el PR final de restauración del Champion, bootstrap y README: respaldar cambios, crear rama desde main remoto, separar commits por funcionalidad y verificar pytest/Ruff/auditoría/CI y sincronización DVC. Git solo conserva código/configuración/documentación y punteros; no publicar secretos, datos pesados, temporales o volúmenes. No hacer merge ni crear entrega-lab1.
