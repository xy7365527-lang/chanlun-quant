from __future__ import annotations

import argparse
import os

from ..analytics.make_dataset import build_dataset
from ..analytics.fit_logistic import fit_logistic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, help="Path to trace.jsonl file.")
    parser.add_argument("--outdir", default="runs/train", help="Directory to place generated artifacts.")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, "dataset.csv")
    weights_path = os.path.join(args.outdir, "weights.json")

    build_dataset(args.trace, csv_path)
    fit_logistic(csv_path, weights_path)

    print(weights_path)


if __name__ == "__main__":
    main()
