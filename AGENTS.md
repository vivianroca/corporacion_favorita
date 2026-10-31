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
