"""Status-only satellite archive contract. No connector is treated as archived data."""
from __future__ import annotations
import json, os
from pathlib import Path
from .history import ROOT, region_by_id

SOURCES={
 "smap":{"source":"NASA SMAP","unit":"m³/m³","quality":"Product ID and product-specific QA required"},
 "mod16":{"source":"NASA MODIS MOD16","unit":"mm/composite","quality":"ET_QC and compositing period required"},
 "hls":{"source":"NASA HLS","unit":"unitless NDVI","quality":"Cloud/shadow QA mask required"},
 "gpm":{"source":"NASA GPM IMERG","unit":"mm per supplied period","quality":"UTC interval and source QA required"}
}
def satellite_history(region_id:str,product:str)->dict:
    region_by_id(region_id)
    if product not in SOURCES: raise ValueError("Unknown satellite product")
    base=Path(os.getenv("FIELD_SHIFT_SATELLITE_DIR",str(ROOT/"data"/"satellite")))
    path=base/"curated"/region_id/(product+".json")
    if not path.exists():
        return {"status":"not_archived","product":product,"source":SOURCES[product]["source"],"region_id":region_id,"unit":SOURCES[product]["unit"],"monthly":[],"field_measurement":False,"connector_is_not_archive":True,"note":"No QA-curated archive is present. Connector configuration or a NASA catalogue result is not proof of archived observations."}
    payload=json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version")!=1 or payload.get("product")!=product or payload.get("region_id")!=region_id or not isinstance(payload.get("monthly"),list):
        raise ValueError("Satellite archive identity mismatch")
    return payload
