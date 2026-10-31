"""Comandos de la etapa 2; sin tareas de ingesta operativa ni entrenamiento."""

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

from reposicion import automatic, ingestion, release
from reposicion.source_io import DeliveryCatalog
from reposicion.source_simulator import simulate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-config", default="configs/sources.yaml")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("simulate", help="Generar histórico y bandeja externa")
    generate.add_argument("--originals")
    generate.add_argument("--output")
    generate.add_argument("--contracts")
    generate.add_argument("--availability")
    verify = commands.add_parser("verify-source", help="Verificar sin modificar el origen")
    verify.add_argument("--root")
    listing = commands.add_parser("list-deliveries", help="Listar metadatos conocidos al corte")
    listing.add_argument("--root")
    listing.add_argument("--as-of", required=True)
    listing.add_argument("--area", choices=["historical", "source_inbox"])
    listing.add_argument("--latest", action="store_true")
    pipeline = commands.add_parser(
        "ingest-snapshot", help="Ingestar y publicar un snapshot por corte"
    )
    pipeline.add_argument("--pipeline-config", default="configs/pipeline.yaml")
    pipeline.add_argument("--as-of", required=True)
    pipeline.add_argument("--reference-start")
    pipeline.add_argument("--reference-end")
    init = commands.add_parser(
        "initialize-inbox", help="Crear una bandeja vacía, sin eliminar nada"
    )
    init.add_argument("--master", default="data/simulation")
    init.add_argument("--inbox", default="data/operational_inbox")
    init.add_argument("--stream-name", default="lab1-live-v1")
    publish = commands.add_parser("publish-next", help="Liberar copias de entregas ya existentes")
    publish.add_argument("--master", default="data/simulation")
    publish.add_argument("--inbox", default="data/operational_inbox")
    publish.add_argument("--count", type=int, default=1)
    publish.add_argument("--delivery-id", action="append")
    poll = commands.add_parser("poll-inbox", help="Ejecutar un ciclo incremental de diagnóstico")
    poll.add_argument("--pipeline-config", default="configs/pipeline.yaml")
    poll.add_argument("--as-of", required=True)
    poll.add_argument("--cycle-id", required=True)
    args = parser.parse_args()
    settings = yaml.safe_load(Path(args.sources_config).read_text(encoding="utf-8"))
    if settings.get("schema_version") != 1:
        parser.error("Versión de configuración de fuentes no soportada")
    if args.command == "simulate":
        manifest = simulate(
            args.originals or settings["original_directory"],
            args.output or settings["simulation_directory"],
            args.contracts or settings["contracts"],
            args.availability or settings["availability"],
        )
        result = {
            "generation_id": manifest["generation_id"],
            "historical_at": manifest["historical_at"],
            "deliveries_by_area": dict(Counter(r["area"] for r in manifest["deliveries"])),
            "source_profiles": {
                s: {k: v for k, v in p.items() if k != "reference_dates"}
                for s, p in manifest["source_profiles"].items()
            },
        }
    elif args.command == "verify-source":
        catalog = DeliveryCatalog(args.root or settings["simulation_directory"])
        result = {"verified_deliveries": catalog.verify()}
    elif args.command == "list-deliveries":
        result = DeliveryCatalog(args.root or settings["simulation_directory"]).available(
            args.as_of, area=args.area, latest=args.latest
        )
    elif args.command == "ingest-snapshot":
        result = ingestion.run_pipeline(
            **ingestion.settings(args.pipeline_config),
            as_of=args.as_of,
            reference_start=args.reference_start,
            reference_end=args.reference_end,
        )
    elif args.command == "initialize-inbox":
        result = release.initialize(args.master, args.inbox, args.stream_name)
    elif args.command == "publish-next":
        result = release.publish_next(args.master, args.inbox, args.count, args.delivery_id)
    else:
        result = automatic.poll_cycle(
            **automatic.settings(args.pipeline_config), as_of=args.as_of, cycle_id=args.cycle_id
        )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
