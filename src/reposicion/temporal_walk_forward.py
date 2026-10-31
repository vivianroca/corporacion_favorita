"""Nueva evaluación de variables temporales, conservando baseline e hiperparámetros."""

import argparse
import json

from reposicion.contracts import Contracts
from reposicion.source_io import DeliveryCatalog
from reposicion.temporal_features import TemporalFeatures, temporal_pipeline
from reposicion.walk_forward import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/simulation")
    parser.add_argument("--contracts", default="configs/contracts.yaml")
    parser.add_argument("--config", default="configs/walk_forward.yaml")
    parser.add_argument("--previous", default="reports/walk_forward/january_2017")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tracking-uri", default="http://localhost:5011")
    args = parser.parse_args()
    builder = TemporalFeatures(DeliveryCatalog(args.source), Contracts(args.contracts))
    result = run(
        args.source,
        args.contracts,
        args.config,
        args.output,
        args.tracking_uri,
        feature_builder=builder,
        pipeline_factory=temporal_pipeline,
        experiment_name="corporacion_favorita-walk-forward-temporal-v2",
        baseline_reference=args.previous,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
