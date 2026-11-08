"""Partial-year and date-window history. Monthly aggregates are chart-only."""
from __future__ import annotations

import calendar
import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .history import _monthly_archive_year, archive_dir, read_year, region_by_id, validate_days
from .models import Provenance, WeatherDay
from .nasa import _cache_write, power_daily

POWER_CITATION="https://power.larc.nasa.gov/docs/services/api/temporal/daily/"

def _digest(rows:list[dict])->str:
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def _ytd_path(region_id:str,year:int)->Path:
    region_by_id(region_id)
    if year < 2016 or year > date.today().year: raise ValueError("YTD year outside supported range")
    return archive_dir()/region_id/f"{year}-ytd.json"

def read_ytd(region_id:str,year:int)->tuple[tuple[WeatherDay,...],dict]:
    path=_ytd_path(region_id,year)
    payload=None
    bucket=os.getenv("FIELD_SHIFT_ARCHIVE_S3_BUCKET","").strip()
    if bucket:
        try:
            import boto3
            obj=boto3.client("s3").get_object(Bucket=bucket,Key=f"power-history/{region_id}/{year}-ytd.json")
            payload=json.loads(obj["Body"].read())
        except Exception as exc:
            if getattr(exc,"response",{}).get("Error",{}).get("Code","") not in {"NoSuchKey","404"}:
                raise RuntimeError("Persistent YTD archive could not be loaded") from exc
    if payload is None: payload=json.loads(path.read_text(encoding="utf-8"))
    through=date.fromisoformat(payload["data_through"])
    rows=payload.get("days",[])
    if payload.get("schema_version")!=2 or payload.get("region")!=region_by_id(region_id) or payload.get("year")!=year or payload.get("is_partial") is not True or through.year!=year or through>date.today() or _digest(rows)!=payload.get("sha256"):
        raise ValueError("Partial archive metadata or checksum mismatch")
    days=tuple(WeatherDay(**{**row,"d":date.fromisoformat(row["d"]),"provenance":Provenance(**row["provenance"])}) for row in rows)
    validate_days(days,date(year,1,1),through)
    return days,{k:v for k,v in payload.items() if k!="days"}

def prefetch_ytd(region_id:str,through:date,*,refresh:bool=False,progress=None)->dict:
    if through.year!=date.today().year or through<date(through.year,1,1) or through>=date.today():
        raise ValueError("Select a past date in the current year; provider latency applies")
    path=_ytd_path(region_id,through.year)
    if not refresh:
        try:
            _,meta=read_ytd(region_id,through.year)
            if date.fromisoformat(meta["data_through"])>=through:return {**meta,"retrieval_mode":"archive"}
        except (OSError,ValueError,KeyError,TypeError): pass
    region=region_by_id(region_id); start=date(through.year,1,1)
    if progress: progress("fetching")
    days=power_daily(region["lat"],region["lon"],start,through,timeout=20,retries=2,cache_dir=archive_dir()/"raw")
    if progress: progress("qa")
    validate_days(days,start,through)
    rows=json.loads(json.dumps([asdict(d) for d in days],default=str))
    payload={"schema_version":2,"region":region,"year":through.year,"is_partial":True,"source":"NASA POWER Daily","product_id":"POWER daily meteorology","native_resolution":"NASA POWER gridded point, daily","data_through":through.isoformat(),"retrieved_at":datetime.now(UTC).isoformat(),"quality_status":"qa_passed_with_imputation" if any("imputed" in d.source for d in days) else "qa_passed","coverage_fraction":1.0,"fallback_used":any("imputed" in d.source for d in days),"archive_kind":"point_not_zone","citation":POWER_CITATION,"sha256":_digest(rows),"days":rows}
    bucket=os.getenv("FIELD_SHIFT_ARCHIVE_S3_BUCKET","").strip()
    if os.getenv("VERCEL") and not bucket: raise RuntimeError("YTD archive publishing requires durable object storage")
    if progress: progress("publishing")
    _cache_write(path,payload)
    if bucket:
        try:
            import boto3
            boto3.client("s3").put_object(Bucket=bucket,Key=f"power-history/{region_id}/{through.year}-ytd.json",Body=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode(),ContentType="application/json",ServerSideEncryption="AES256")
        except Exception as exc: raise RuntimeError("Durable YTD archive publishing failed") from exc
    _,verified=read_ytd(region_id,through.year)
    return verified

def _day(value:str|date)->date:
    try:return value if isinstance(value,date) else date.fromisoformat(value)
    except (ValueError,TypeError) as exc: raise ValueError("Dates must use YYYY-MM-DD") from exc

def history_date_range(region_id:str,start:str|date,end:str|date)->dict[str,Any]:
    region=region_by_id(region_id); a,b=_day(start),_day(end)
    if a<date(1981,1,1) or b>date.today() or b<a or (b-a).days>30*366: raise ValueError("Date range must be ordered, not future, and <= 30 years")
    monthly,annual,evidence,missing=[],[],[],[]
    grouped: dict[tuple[int, int], list[WeatherDay | dict[str, Any]]] = {}
    aggregate_years=set(); available=0
    for year in range(a.year,b.year+1):
        try:
            if year==date.today().year: days,meta=read_ytd(region_id,year)
            else: days,meta=read_year(region_id,year)
        except (OSError,ValueError,KeyError,TypeError):
            compact=_monthly_archive_year(region_id,year) if year<date.today().year else None
            if compact is None: missing.append(year); continue
            records,meta=compact; aggregate_years.add(year); evidence.append(meta)
            for item in records:
                yy,mm=map(int,item["month"].split("-")); ms=date(yy,mm,1); me=date(yy,mm,calendar.monthrange(yy,mm)[1])
                if a<=ms and me<=b: grouped.setdefault((yy,mm),[]).append({**item,"aggregate_only":True}); available+=int(item["days"])
            continue
        evidence.append(meta)
        for d in days:
            if a<=d.d<=b: grouped.setdefault((d.d.year,d.d.month),[]).append(d); available+=1
    for year in range(a.year,b.year+1):
        yrows=[v for (yr,_),rows in grouped.items() if yr==year for v in rows]
        if not yrows: continue
        ystart=max(a,date(year,1,1)); yend=min(b,date(year,12,31))
        if year==date.today().year:yend=min(yend,date.today())
        expected=(yend-ystart).days+1
        if year in aggregate_years:
            aggregate_rows = [v for v in yrows if isinstance(v, dict)]
            if len(aggregate_rows) != len(yrows):
                raise ValueError("Monthly archive contains mixed record types")
            n = sum(int(v["days"]) for v in aggregate_rows)
            rain = sum(float(v["rain_mm"]) for v in aggregate_rows)
            temp = sum(float(v["temperature_c"]) * int(v["days"]) for v in aggregate_rows) / max(1, n)
        else:
            daily_rows = [v for v in yrows if isinstance(v, WeatherDay)]
            if len(daily_rows) != len(yrows):
                raise ValueError("Daily archive contains non-daily records")
            n = len(daily_rows)
            rain = sum(v.rain_mm for v in daily_rows)
            temp = sum((v.tmax_c + v.tmin_c) / 2 for v in daily_rows) / max(1, n)
        annual.append({"year":year,"rain_mm":round(rain,2),"temperature_c":round(temp,2),"days":n,"expected_days":expected,"is_partial":n!=expected or ystart!=date(year,1,1) or yend!=date(year,12,31),"archive_representation":"monthly_aggregate" if year in aggregate_years else "daily"})
    for (year,month),rows in sorted(grouped.items()):
        if year in aggregate_years:
            if not rows or not isinstance(rows[0], dict):
                raise ValueError("Monthly archive contains a non-aggregate record")
            value = rows[0]
            monthly.append({"month":f"{year}-{month:02d}","rain_mm":round(float(value["rain_mm"]),2),"temperature_c":round(float(value["temperature_c"]),2),"days":int(value["days"]),"expected_days":calendar.monthrange(year,month)[1],"is_partial":False,"archive_representation":"monthly_aggregate"})
        else:
            daily_rows = [v for v in rows if isinstance(v, WeatherDay)]
            if len(daily_rows) != len(rows):
                raise ValueError("Daily archive contains non-daily records")
            monthly.append({"month":f"{year}-{month:02d}","rain_mm":round(sum(v.rain_mm for v in daily_rows),2),"temperature_c":round(sum((v.tmax_c+v.tmin_c)/2 for v in daily_rows)/len(daily_rows),2),"days":len(daily_rows),"expected_days":calendar.monthrange(year,month)[1],"is_partial":len(daily_rows)!=calendar.monthrange(year,month)[1],"archive_representation":"daily"})
    total=(b-a).days+1
    monthly_days = sum(int(row["days"]) for row in monthly if row.get("archive_representation") == "monthly_aggregate")
    has_monthly = bool(aggregate_years)
    representation = "monthly_aggregate" if has_monthly and not any(row.get("archive_representation") == "daily" for row in monthly) else "mixed_daily_and_monthly" if has_monthly else "daily"
    return {"region":region,"start_date":a.isoformat(),"end_date":b.isoformat(),"start_year":a.year,"end_year":b.year,"product":"power","sample_type":"monthly_aggregate" if has_monthly else "single_gridded_point","archive_representation":representation,"status":"summary_only" if has_monthly and not missing else "complete" if available==total else "partial" if available else "not_downloaded","is_partial":available!=total or any(x["is_partial"] for x in annual),"coverage_fraction":None if has_monthly else round(available/total,5),"summary_day_equivalent":monthly_days if has_monthly else None,"summary_coverage_fraction":round(monthly_days/total,5) if has_monthly else None,"available_days":None if has_monthly else available,"expected_days":total,"missing_years":missing,"annual":annual,"monthly":monthly,"provenance":evidence,"units":{"rain_mm":"mm total for displayed window","temperature_c":"°C; mean of daily (Tmax + Tmin)/2"},"note":"NASA POWER grid point sample, not a farm measurement or zone average. Missing dates are not zero. Monthly aggregates are chart-only, not observed daily coverage or daily crop-model inputs; partial months are not prorated.","supplemental_history":{"smap":"not_archived","modis_et":"not_archived","hls":"not_archived","gpm":"not_archived"}}
