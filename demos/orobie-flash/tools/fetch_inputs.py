#!/usr/bin/env python3
"""Download actual open Copernicus DEM tiles, optionally EFAS RP inundation rasters.

Free unsigned AWS S3 GLO-30 public first, GLO-90 fallback where unavailable.
No synthetic terrain is generated. This can fetch hundreds of MB. Requires
  pip install boto3 pyproj requests
EFAS Europe-wide depth grids are large (~260–334 MB each); downloading all
RP10/RP100/RP500 approaches 1 GB before processing.
"""
import argparse
import math
from pathlib import Path
from pyproj import Transformer
import boto3
from botocore import UNSIGNED
from botocore.config import Config

CENTERS={"orobie":(10.007,46.040),"euganei":(11.687,45.315)}
EFAS_ROOT="https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/flood_hazard/"
BUCKETS=[("copernicus-dem-30m","10"),("copernicus-dem-90m","30")]

def geographic_bounds(lon,lat):
    forward=Transformer.from_crs(4326,32632,always_xy=True)
    backwards=Transformer.from_crs(32632,4326,always_xy=True)
    x,y=forward.transform(lon,lat)
    samples=[]
    for i in range(9):
        f=i/8.
        for xx,yy in [
            (x-50000+f*100000,y-50000),(x-50000+f*100000,y+50000),
            (x-50000,y-50000+f*100000),(x+50000,y-50000+f*100000)
        ]:
            samples.append(backwards.transform(xx,yy))
    return min(k[0] for k in samples),min(k[1] for k in samples),max(k[0] for k in samples),max(k[1] for k in samples)

def geocell_prefix(lat,lon,res):
    ns=f"N{lat:02d}" if lat>=0 else f"S{abs(lat):02d}"
    ew=f"E{lon:03d}" if lon>=0 else f"W{abs(lon):03d}"
    return f"Copernicus_DSM_COG_{res}_{ns}_00_{ew}_00_DEM/"

def download_dem(a):
    s3=boto3.client("s3",region_name="eu-central-1",config=Config(signature_version=UNSIGNED))
    regions=CENTERS if a.region=="both" else {a.region:CENTERS[a.region]}
    keys=set()
    for lon,lat in regions.values():
        west,south,east,north=geographic_bounds(lon,lat)
        for yy in range(math.floor(south),math.ceil(north)):
            for xx in range(math.floor(west),math.ceil(east)):
                keys.add((yy,xx))
    acquired=[]
    for lat,lon in sorted(keys):
        found=False
        for bucket,res in BUCKETS:
            prefix=geocell_prefix(lat,lon,res)
            listing=s3.list_objects_v2(Bucket=bucket,Prefix=prefix)
            objs=[o["Key"] for o in listing.get("Contents",[])
                  if o["Key"].lower().endswith(".tif") and "_DEM" in o["Key"].upper()]
            if not objs:
                print(f"No public {bucket} tile for {prefix}; trying next resolution")
                continue
            key=next((o for o in objs if o.endswith("_DEM.tif")),objs[0])
            dest=a.output/"dem"/bucket/Path(key).name
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists() or dest.stat().st_size==0:
                print(f"Downloading s3://{bucket}/{key} -> {dest}",flush=True)
                s3.download_file(bucket,key,str(dest))
            else:
                print(f"Existing: {dest}")
            acquired.append(dest)
            found=True
            break
        if not found:
            raise RuntimeError(f"Neither public GLO-30 nor GLO-90 covers geocell latitude {lat}, longitude {lon}")
    print("\nOpen DEM input list in priority order (GLO-30 before GLO-90):")
    for path in sorted(acquired,key=lambda p:("90m" in str(p),str(p))):
        print(path)
    print("To override with 5 m DTM, place those local rasters first in --dem list.")

def download_flood(a):
    import requests
    folder=a.output/"efas"
    folder.mkdir(parents=True,exist_ok=True)
    for rp in a.efas:
        name=f"Europe_RP{rp}_filled_depth.tif"
        url=EFAS_ROOT+name
        dest=folder/name
        if dest.exists() and dest.stat().st_size>1000000:
            print("Existing EFAS:",dest);continue
        print(f"Downloading large EFAS depth grid {name}",flush=True)
        temp=dest.with_suffix(".download")
        with requests.get(url,stream=True,timeout=(30,180)) as resp:
            resp.raise_for_status()
            with temp.open("wb") as f:
                for chunk in resp.iter_content(1024*1024):
                    if chunk:f.write(chunk)
        temp.replace(dest)
        print("Saved",dest)
    print("Flood depth is static modelled riverine inundation; RP1000 not provided.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--region",choices=[*CENTERS,"both"],default="both")
    p.add_argument("--output",type=Path,default=Path(__file__).resolve().parent.parent/"raw_inputs")
    p.add_argument("--dem",action="store_true",help="download GLO30 public + fallback GLO90")
    p.add_argument("--efas",nargs="*",type=int,choices=[10,100,500],default=[],help="which European hazard depth rasters")
    args=p.parse_args()
    if not args.dem and not args.efas:p.error("select --dem and/or --efas 10 100 500")
    if args.dem:download_dem(args)
    if args.efas:download_flood(args)
