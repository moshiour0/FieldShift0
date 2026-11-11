"""Import externally retrieved, QA-tagged satellite CSV; this does not imply provider access."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fieldshift.v3.history import REGIONS
from fieldshift.v3.satellite_archive import SOURCES, import_satellite_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True, choices=[r["id"] for r in REGIONS])
    parser.add_argument("--product", required=True, choices=list(SOURCES))
    parser.add_argument("--csv", required=True, type=Path)
    for arg in ("product-id", "version", "native-resolution", "temporal-resolution", "citation"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--smap-reprocessing-verified", action="store_true")
    parser.add_argument("--reprocessing-evidence", default="")
    args = parser.parse_args()
    out = import_satellite_csv(
        region_id=args.region, product=args.product, filepath=args.csv,
        product_id=args.product_id, version=args.version,
        native_resolution=args.native_resolution, temporal_resolution=args.temporal_resolution,
        citation=args.citation, smap_reprocessing_verified=args.smap_reprocessing_verified,
        reprocessing_evidence=args.reprocessing_evidence,
    )
    print(json.dumps({key: out[key] for key in
                      ("region_id", "product", "quality_status", "data_through",
                       "accepted_observations", "sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
