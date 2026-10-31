# Corporación Favorita — Laboratorio 1

Motor reproducible de reposición de inventario, con contratos de datos,
Airflow, PostgreSQL, MLflow y pruebas automatizadas.

Esta rama `main` contiene la base inicial de documentación, exclusiones y CI.
La implementación está preparada para revisión en `feature/ingesta-airflow`
mediante un Pull Request hacia `main`. No se fusiona automáticamente.

- Arquitectura: [propuesta.md](propuesta.md).
- Reglas del proyecto: [AGENTS.md](AGENTS.md).
- GitHub Actions ejecuta pytest sobre cada PR hacia main.
- No se publican datasets, modelos, bases, credenciales ni volúmenes.
- El directorio de trabajo local conserva el nombre `lab1`.

La implementación y sus comandos de operación se incorporarán al aprobar el PR.
