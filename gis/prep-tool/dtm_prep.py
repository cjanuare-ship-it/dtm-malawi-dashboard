#!/usr/bin/env python3
"""
DTM Malawi — RE2CLID GIS Workspace · data preparation tool
===========================================================

Prepares heavy GIS files so they load quickly in the web workspace
(https://cjanuare-ship-it.github.io/dtm-malawi-dashboard/gis/).

What it does
  Vectors (shapefile / zipped shapefile / GeoJSON / GeoPackage / KML / CSV with lat-lon)
    • reprojects to WGS 84 (EPSG:4326), the system the workspace reads
    • repairs invalid geometries and drops empty ones
    • optionally clips to Malawi (or to a boundary file)
    • simplifies lines and polygons by a tolerance in metres (shape kept, vertices dropped)
    • keeps only the fields you choose, drops fields that are always empty
    • rounds coordinates (6 decimals ≈ 0.1 m)
    • optionally splits a layer by a field (one file per district, for example)
    • optionally summarises points into polygons (count and sums per TA or district)
  Rasters (GeoTIFF)
    • reprojects to WGS 84, clips to Malawi if asked
    • reduces the size to a maximum width/height (average for continuous data, majority for classes)
    • writes a compressed, tiled GeoTIFF with nodata set

Use it
  Window:        python dtm_prep.py                (or double-click run_dtm_prep.bat on Windows)
  Command line:  python dtm_prep.py INPUT [INPUT ...] -o OUTFOLDER [options]
                 python dtm_prep.py --help         (all options)

Needs Python 3.9+ with:  pip install geopandas pyogrio shapely rasterio numpy pandas
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
import zipfile
import tempfile
from pathlib import Path

VERSION = "1.0 (November 2026)"
MALAWI_BBOX = (32.67, -17.13, 35.92, -9.36)          # lon/lat, with a small margin
METRIC_CRS = "EPSG:32736"                              # WGS 84 / UTM 36S: metres for Malawi
VECTOR_EXT = {".shp", ".zip", ".geojson", ".json", ".gpkg", ".kml", ".kmz", ".gml", ".csv", ".tsv", ".txt"}
RASTER_EXT = {".tif", ".tiff", ".img", ".vrt", ".asc"}
# the workspace stays smooth up to a few million vertices; these are the levels the report warns at
WARN_VERTICES, WARN_MB = 2_000_000, 60


def need(mod: str):
    try:
        return __import__(mod)
    except ImportError:
        raise SystemExit(f"Missing Python package '{mod}'. Install with:\n  pip install geopandas pyogrio shapely rasterio numpy pandas")


# ----------------------------------------------------------------------------------------------- helpers
def human_mb(n: float) -> str:
    return f"{n / 1048576:.1f} MB"


def count_vertices(gs) -> int:
    import shapely
    return int(shapely.get_num_coordinates(gs.values).sum()) if len(gs) else 0


def safe_name(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(s)).strip("_")
    return (keep or "blank")[:60]


def read_vector(path: Path, log, layer: str | None = None, lat: str | None = None, lon: str | None = None):
    gpd = need("geopandas")
    pd = need("pandas")
    ext = path.suffix.lower()
    if ext in {".csv", ".tsv", ".txt"}:
        df = pd.read_csv(path, sep=None, engine="python", encoding_errors="replace")
        cols = {c.lower(): c for c in df.columns}
        la = lat or next((cols[c] for c in cols if c in ("lat", "latitude", "y", "_gps_latitude", "gps_latitude", "point_y") or c.endswith("_latitude")), None)
        lo = lon or next((cols[c] for c in cols if c in ("lon", "lng", "long", "longitude", "x", "_gps_longitude", "gps_longitude", "point_x") or c.endswith("_longitude")), None)
        wkt = next((cols[c] for c in cols if c in ("wkt", "geometry", "geom", "the_geom")), None)
        if wkt:
            from shapely import wkt as W
            g = gpd.GeoSeries(df[wkt].map(lambda s: W.loads(s) if isinstance(s, str) and s.strip() else None), crs=4326)
            return gpd.GeoDataFrame(df.drop(columns=[wkt]), geometry=g, crs=4326)
        if not (la and lo):
            raise ValueError(f"{path.name}: no latitude/longitude columns found (use --lat and --lon)")
        df[la] = pd.to_numeric(df[la], errors="coerce")
        df[lo] = pd.to_numeric(df[lo], errors="coerce")
        bad = df[la].isna() | df[lo].isna() | ((df[la] == 0) & (df[lo] == 0))
        if bad.any():
            log(f"  {int(bad.sum()):,} row(s) without coordinates skipped")
        df = df[~bad]
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lo], df[la]), crs=4326)
    src = str(path)
    if ext == ".zip":
        src = "/vsizip/" + str(path)
        names = [n for n in zipfile.ZipFile(path).namelist() if n.lower().endswith((".shp", ".geojson", ".gpkg", ".kml"))]
        if not names:
            raise ValueError(f"{path.name}: no shapefile, GeoJSON, GeoPackage or KML inside")
        src = "/vsizip/" + str(path) + "/" + names[0]
        if len(names) > 1:
            log(f"  zip holds {len(names)} layers; reading {names[0]} (unzip to process the others)")
    kw = {"layer": layer} if layer else {}
    try:
        g = gpd.read_file(src, engine="pyogrio", **kw)
    except Exception:
        g = gpd.read_file(src, **kw)
    if g.crs is None:
        x = g.total_bounds
        if abs(x[0]) > 180 or abs(x[3]) > 90:
            log("  no CRS and projected numbers: assuming WGS 84 / UTM 36S (EPSG:32736)")
            g = g.set_crs(METRIC_CRS)
        else:
            g = g.set_crs(4326)
    return g


# ----------------------------------------------------------------------------------------------- vectors
def prep_vector(path: Path, out: Path, o: dict, log) -> list[dict]:
    gpd = need("geopandas")
    shapely = need("shapely")
    t0 = time.time()
    size_in = path.stat().st_size
    g = read_vector(path, log, o.get("layer"), o.get("lat"), o.get("lon"))
    n0, v0 = len(g), count_vertices(g.geometry)
    log(f"  read {n0:,} features, {v0:,} vertices, CRS {g.crs.to_string() if g.crs else '?'}")
    # repair, reproject
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    invalid = ~g.geometry.is_valid
    if invalid.any():
        g.loc[invalid, "geometry"] = shapely.make_valid(g.loc[invalid, "geometry"].values)
        log(f"  repaired {int(invalid.sum()):,} invalid geometr{'y' if invalid.sum() == 1 else 'ies'}")
    if g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    # clip
    if o.get("clip_file"):
        mask = read_vector(Path(o["clip_file"]), log).to_crs(4326)
        g = gpd.clip(g, mask.union_all() if hasattr(mask, "union_all") else mask.unary_union)
        log(f"  clipped to {Path(o['clip_file']).name}: {len(g):,} features left")
    elif o.get("clip_malawi"):
        before = len(g)
        g = g.cx[MALAWI_BBOX[0]:MALAWI_BBOX[2], MALAWI_BBOX[1]:MALAWI_BBOX[3]]
        if len(g) < before:
            log(f"  kept {len(g):,} of {before:,} features inside the Malawi area")
    # simplify in metres (lines and polygons only)
    tol = float(o.get("simplify") or 0)
    gt = set(g.geom_type.unique())
    if tol > 0 and gt - {"Point", "MultiPoint"}:
        m = g.to_crs(METRIC_CRS)
        not_pt = ~m.geom_type.isin(["Point", "MultiPoint"])
        m.loc[not_pt, "geometry"] = m.loc[not_pt, "geometry"].simplify(tol, preserve_topology=True)
        g = m.to_crs(4326)
        g = g[g.geometry.notna() & ~g.geometry.is_empty]
        log(f"  simplified with {tol:g} m tolerance")
    # fields
    keep = [f.strip() for f in (o.get("fields") or "").split(",") if f.strip()]
    if keep:
        missing = [f for f in keep if f not in g.columns]
        if missing:
            log(f"  fields not found and ignored: {', '.join(missing)}")
        g = g[[f for f in keep if f in g.columns] + ["geometry"]]
    if o.get("drop_empty", True):
        empty = [c for c in g.columns if c != "geometry" and g[c].isna().all()]
        if empty:
            g = g.drop(columns=empty)
            log(f"  dropped {len(empty)} always-empty field(s)")
    # aggregate points into polygons
    results = []
    if o.get("aggregate_to"):
        g = aggregate(g, Path(o["aggregate_to"]), o, log)
    # split
    groups = [(None, g)]
    if o.get("split_by"):
        f = o["split_by"]
        if f not in g.columns:
            raise ValueError(f"split field '{f}' not found")
        groups = [(k, part) for k, part in g.groupby(g[f].fillna("blank").astype(str))]
        log(f"  split by {f}: {len(groups)} files")
    stem = o.get("name") or path.stem
    for key, part in groups:
        name = f"{stem}_{safe_name(key)}" if key is not None else stem
        dst = out / f"{name}_web.geojson"
        write_geojson(part, dst, int(o.get("decimals") or 6))
        v1 = count_vertices(part.geometry)
        if o.get("zip"):
            z = dst.with_suffix(".zip")
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                zf.write(dst, dst.name)
            dst.unlink()
            dst = z
        size = dst.stat().st_size
        results.append({"input": path.name, "output": dst.name, "features": len(part), "vertices_before": v0, "vertices_after": v1,
                        "mb_before": size_in / 1048576, "mb_after": size / 1048576, "seconds": time.time() - t0})
        warn = " — still heavy: raise the simplify tolerance, trim fields or split it" if (v1 > WARN_VERTICES or size / 1048576 > WARN_MB) else ""
        log(f"  → {dst.name}: {len(part):,} features, {v1:,} vertices, {human_mb(size)}{warn}")
    return results


def aggregate(points, polys_path: Path, o: dict, log):
    gpd = need("geopandas")
    polys = read_vector(polys_path, log).to_crs(4326)
    pts = points.copy()
    if not set(pts.geom_type.unique()) <= {"Point", "MultiPoint"}:
        pts["geometry"] = pts.to_crs(METRIC_CRS).representative_point().to_crs(4326)
    j = gpd.sjoin(pts, polys[["geometry"]], predicate="within", how="inner")
    agg = j.groupby("index_right").size().rename("count")
    out = polys.copy()
    out["count"] = agg.reindex(out.index).fillna(0).astype(int)
    for f in [f.strip() for f in (o.get("sum_fields") or "").split(",") if f.strip()]:
        if f in j.columns:
            out[f"sum_{f}"] = j.groupby("index_right")[f].apply(lambda s: s.astype(float).sum()).reindex(out.index).fillna(0)
    log(f"  summarised {len(j):,} of {len(pts):,} features into {len(out):,} polygons of {polys_path.name}")
    return out


def write_geojson(g, dst: Path, decimals: int):
    """Compact GeoJSON: rounded coordinates, no indentation, no null-heavy noise."""
    import shapely
    pd = need("pandas")
    g = g.copy()
    g["geometry"] = shapely.set_precision(g.geometry.values, 10 ** -decimals, mode="valid_output") if decimals < 9 else g.geometry
    g = g[~g.geometry.is_empty]
    props = g.drop(columns="geometry")
    for c in props.columns:
        if pd.api.types.is_datetime64_any_dtype(props[c]):
            props[c] = props[c].dt.strftime("%Y-%m-%d")
    geoms = shapely.to_geojson(g.geometry.values)
    recs = json.loads(props.to_json(orient="records", double_precision=6, date_format="iso")) if len(props.columns) else [{} for _ in range(len(g))]
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[')
        for i, (gj, pr) in enumerate(zip(geoms, recs)):
            if i:
                fh.write(",")
            fh.write('{"type":"Feature","properties":' + json.dumps(pr, ensure_ascii=False, separators=(",", ":")) + ',"geometry":' + gj + "}")
        fh.write("]}")


# ----------------------------------------------------------------------------------------------- rasters
def prep_raster(path: Path, out: Path, o: dict, log) -> list[dict]:
    rasterio = need("rasterio")
    np = need("numpy")
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    t0 = time.time()
    size_in = path.stat().st_size
    maxpx = int(o.get("raster_max") or 3000)
    categorical = bool(o.get("categorical"))
    rs = Resampling.mode if categorical else Resampling.average
    with rasterio.open(path) as src:
        log(f"  read {src.width:,} × {src.height:,} px, {src.count} band(s), {src.dtypes[0]}, CRS {src.crs}")
        band = int(o.get("band") or 1)
        nodata = o.get("nodata")
        nodata = float(nodata) if nodata not in (None, "") else (src.nodata if src.nodata is not None else -9999.0)
        dst_crs = "EPSG:4326"
        bounds = rasterio.warp.transform_bounds(src.crs or dst_crs, dst_crs, *src.bounds) if src.crs else src.bounds
        if o.get("clip_malawi"):
            bounds = (max(bounds[0], MALAWI_BBOX[0]), max(bounds[1], MALAWI_BBOX[1]), min(bounds[2], MALAWI_BBOX[2]), min(bounds[3], MALAWI_BBOX[3]))
            if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                raise ValueError("raster does not overlap Malawi")
        # target grid: same bounds, at most maxpx on the long side
        tr, w, h = calculate_default_transform(src.crs or dst_crs, dst_crs, src.width, src.height, *src.bounds)
        k = min(1.0, maxpx / max(w, h))
        resx, resy = tr.a / k, -tr.e / k
        W = max(1, int(round((bounds[2] - bounds[0]) / resx)))
        H = max(1, int(round((bounds[3] - bounds[1]) / resy)))
        if max(W, H) > maxpx:
            s = maxpx / max(W, H)
            W, H = max(1, int(W * s)), max(1, int(H * s))
        transform = rasterio.transform.from_bounds(*bounds, W, H)
        dtype = "float32" if not categorical else src.dtypes[band - 1]
        dst_arr = np.full((H, W), nodata, dtype=dtype)
        reproject(source=rasterio.band(src, band), destination=dst_arr, src_transform=src.transform, src_crs=src.crs or dst_crs,
                  src_nodata=src.nodata, dst_transform=transform, dst_crs=dst_crs, dst_nodata=nodata, resampling=rs)
    valid = dst_arr[dst_arr != nodata]
    if valid.size == 0:
        raise ValueError("no valid cells after processing")
    dst = out / f"{o.get('name') or path.stem}_web.tif"
    prof = dict(driver="GTiff", width=W, height=H, count=1, dtype=dtype, crs="EPSG:4326", transform=transform, nodata=nodata,
                compress="deflate", predictor=3 if dtype == "float32" else 2, tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(dst, "w", **prof) as d:
        d.write(dst_arr, 1)
        d.update_tags(source=path.name, prepared_by="DTM Malawi data-prep tool " + VERSION, resampling=rs.name)
    size = dst.stat().st_size
    log(f"  → {dst.name}: {W:,} × {H:,} px ({rs.name}), values {float(valid.min()):.4g} to {float(valid.max()):.4g}, {human_mb(size)}")
    return [{"input": path.name, "output": dst.name, "features": W * H, "vertices_before": 0, "vertices_after": 0,
             "mb_before": size_in / 1048576, "mb_after": size / 1048576, "seconds": time.time() - t0}]


# ----------------------------------------------------------------------------------------------- driver
def process(inputs: list[str], outdir: str, o: dict, log=print) -> list[dict]:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    allres = []
    for p in inputs:
        path = Path(p)
        if not path.exists():
            log(f"✗ {p}: file not found")
            continue
        ext = path.suffix.lower()
        log(f"▶ {path.name} ({human_mb(path.stat().st_size)})")
        try:
            if ext in RASTER_EXT:
                allres += prep_raster(path, out, o, log)
            elif ext in VECTOR_EXT:
                allres += prep_vector(path, out, o, log)
            else:
                log(f"  skipped: .{ext[1:]} is not a GIS format this tool reads")
        except Exception as e:
            log(f"✗ {path.name}: {e}")
            if o.get("debug"):
                log(traceback.format_exc())
    if allres:
        write_report(out, allres, o)
        log(f"\nDone. {len(allres)} file(s) in {out}. Load the *_web files in the workspace (Add data). Report: {out / 'prep_report.txt'}")
    return allres


def write_report(out: Path, res: list[dict], o: dict):
    lines = [f"DTM Malawi GIS workspace — data preparation report", f"{time.strftime('%Y-%m-%d %H:%M')} · tool {VERSION}",
             f"Options: " + ", ".join(f"{k}={v}" for k, v in o.items() if v not in (None, "", False)), ""]
    lines.append(f"{'Input':34} {'Output':40} {'Feat./px':>10} {'Vertices before':>16} {'after':>12} {'MB before':>10} {'after':>8}")
    for r in res:
        lines.append(f"{r['input'][:34]:34} {r['output'][:40]:40} {r['features']:>10,} {r['vertices_before']:>16,} {r['vertices_after']:>12,} {r['mb_before']:>10.1f} {r['mb_after']:>8.1f}")
    (out / "prep_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser():
    ap = argparse.ArgumentParser(prog="dtm_prep", description="Prepare heavy GIS files for the DTM Malawi RE2CLID GIS workspace.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Examples:\n  dtm_prep.py buildings.zip -o web --simplify 2 --fields type,area_m2\n"
                                        "  dtm_prep.py households.csv -o web --aggregate-to ta.shp --sum-fields hh_size\n"
                                        "  dtm_prep.py flood.tif -o web --raster-max 3000 --clip-malawi\n"
                                        "  dtm_prep.py roads.gpkg -o web --simplify 10 --split-by district")
    ap.add_argument("inputs", nargs="*", help="files to prepare (vectors and/or rasters)")
    ap.add_argument("-o", "--out", default="web_ready", help="output folder (default: web_ready)")
    ap.add_argument("--simplify", type=float, default=0, help="simplify lines/polygons, tolerance in metres (e.g. 5 for buildings, 50 for boundaries at national scale)")
    ap.add_argument("--decimals", type=int, default=6, help="coordinate decimals (6 ≈ 0.1 m, 5 ≈ 1 m; default 6)")
    ap.add_argument("--fields", help="comma-separated fields to keep (default: all)")
    ap.add_argument("--keep-empty-fields", action="store_true", help="keep fields that are empty everywhere")
    ap.add_argument("--zip", action="store_true", help="zip each GeoJSON (smaller to share; the workspace opens the zip directly)")
    ap.add_argument("--clip-malawi", action="store_true", help="keep only what falls in the Malawi area")
    ap.add_argument("--clip-file", help="clip to the polygons of this file (e.g. a district boundary)")
    ap.add_argument("--split-by", help="write one file per value of this field")
    ap.add_argument("--aggregate-to", help="summarise the features into the polygons of this file (count per polygon)")
    ap.add_argument("--sum-fields", help="with --aggregate-to: numeric fields to sum per polygon")
    ap.add_argument("--layer", help="layer name inside a GeoPackage")
    ap.add_argument("--lat", help="CSV latitude column (auto-detected)")
    ap.add_argument("--lon", help="CSV longitude column (auto-detected)")
    ap.add_argument("--name", help="output name (default: input name)")
    ap.add_argument("--raster-max", type=int, default=3000, help="largest raster width/height in pixels (default 3000, the workspace shows up to 3072)")
    ap.add_argument("--categorical", action="store_true", help="raster holds classes (land cover, IPC phase): keep values, use majority resampling")
    ap.add_argument("--band", type=int, default=1, help="raster band (default 1)")
    ap.add_argument("--nodata", help="raster nodata value (default: from the file, else -9999)")
    ap.add_argument("--debug", action="store_true", help="show full error details")
    ap.add_argument("--version", action="version", version=VERSION)
    return ap


def opts_from_args(a) -> dict:
    return {"simplify": a.simplify, "decimals": a.decimals, "fields": a.fields, "drop_empty": not a.keep_empty_fields, "clip_malawi": a.clip_malawi,
            "clip_file": a.clip_file, "split_by": a.split_by, "aggregate_to": a.aggregate_to, "sum_fields": a.sum_fields, "layer": a.layer,
            "lat": a.lat, "lon": a.lon, "name": a.name, "raster_max": a.raster_max, "categorical": a.categorical, "band": a.band,
            "nodata": a.nodata, "debug": a.debug, "zip": a.zip}


# ----------------------------------------------------------------------------------------------- window
def gui():
    import threading
    import tkinter as tk
    from tkinter import ttk, filedialog, scrolledtext
    BLUE, LIGHT = "#0033A0", "#F2F7FA"
    root = tk.Tk()
    root.title("DTM Malawi · prepare data for the GIS workspace")
    root.geometry("820x640")
    root.configure(bg=LIGHT)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure("TFrame", background=LIGHT)
    st.configure("TLabel", background=LIGHT, font=("Segoe UI", 10))
    st.configure("H.TLabel", background=BLUE, foreground="white", font=("Segoe UI Semibold", 13), padding=(14, 10))
    st.configure("TCheckbutton", background=LIGHT)
    st.configure("Go.TButton", font=("Segoe UI Semibold", 11), padding=(14, 6))
    ttk.Label(root, text="Prepare heavy GIS data for the RE2CLID GIS workspace", style="H.TLabel").pack(fill="x")
    body = ttk.Frame(root, padding=14)
    body.pack(fill="both", expand=True)
    files: list[str] = []
    v = {k: tk.StringVar(value=d) for k, d in [("out", str(Path.home() / "web_ready")), ("simplify", "0"), ("decimals", "6"), ("fields", ""),
                                              ("split_by", ""), ("aggregate_to", ""), ("sum_fields", ""), ("raster_max", "3000"), ("nodata", "")]}
    b = {k: tk.BooleanVar(value=d) for k, d in [("clip_malawi", True), ("categorical", False), ("drop_empty", True), ("zip", True)]}
    # files
    fl = ttk.Frame(body)
    fl.pack(fill="x")
    lst = tk.Listbox(fl, height=5, relief="flat", highlightthickness=1, highlightcolor=BLUE)
    lst.pack(side="left", fill="x", expand=True)
    bf = ttk.Frame(fl)
    bf.pack(side="left", padx=8)

    def add():
        for f in filedialog.askopenfilenames(title="Choose GIS files", filetypes=[("GIS files", "*.shp *.zip *.geojson *.json *.gpkg *.kml *.kmz *.csv *.tif *.tiff"), ("All", "*.*")]):
            if f not in files:
                files.append(f)
                lst.insert("end", f)

    def clear():
        files.clear()
        lst.delete(0, "end")
    ttk.Button(bf, text="Add files…", command=add).pack(fill="x")
    ttk.Button(bf, text="Clear", command=clear).pack(fill="x", pady=4)
    grid = ttk.Frame(body)
    grid.pack(fill="x", pady=10)

    def row(r, label, key, hint="", browse=None):
        ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=3)
        e = ttk.Entry(grid, textvariable=v[key], width=44)
        e.grid(row=r, column=1, sticky="we", padx=6)
        if browse:
            ttk.Button(grid, text="…", width=3, command=browse).grid(row=r, column=2)
        ttk.Label(grid, text=hint, foreground="#56636A").grid(row=r, column=3, sticky="w")
    grid.columnconfigure(1, weight=1)
    row(0, "Output folder", "out", "", lambda: v["out"].set(filedialog.askdirectory() or v["out"].get()))
    row(1, "Simplify (metres)", "simplify", "0 = off · 2–5 buildings · 20–100 boundaries")
    row(2, "Coordinate decimals", "decimals", "6 ≈ 0.1 m · 5 ≈ 1 m")
    row(3, "Keep only fields", "fields", "comma-separated; empty = all")
    row(4, "Split by field", "split_by", "one file per value (optional)")
    row(5, "Summarise into polygons", "aggregate_to", "points → counts per TA/district", lambda: v["aggregate_to"].set(filedialog.askopenfilename() or v["aggregate_to"].get()))
    row(6, "…and sum fields", "sum_fields", "comma-separated (optional)")
    row(7, "Raster max size (px)", "raster_max", "workspace shows up to 3072")
    row(8, "Raster nodata", "nodata", "empty = from file")
    cf = ttk.Frame(body)
    cf.pack(fill="x")
    ttk.Checkbutton(cf, text="Clip to Malawi", variable=b["clip_malawi"]).pack(side="left")
    ttk.Checkbutton(cf, text="Raster holds classes", variable=b["categorical"]).pack(side="left", padx=14)
    ttk.Checkbutton(cf, text="Drop empty fields", variable=b["drop_empty"]).pack(side="left")
    ttk.Checkbutton(cf, text="Zip GeoJSON output", variable=b["zip"]).pack(side="left", padx=14)
    logw = scrolledtext.ScrolledText(body, height=12, font=("Consolas", 9), relief="flat")
    logw.pack(fill="both", expand=True, pady=(10, 6))

    def log(msg):
        root.after(0, lambda: (logw.insert("end", msg + "\n"), logw.see("end")))
    go = ttk.Button(body, text="Prepare files", style="Go.TButton")
    go.pack(anchor="e")

    def run():
        if not files:
            log("Add one or more files first.")
            return
        o = {k: x.get() for k, x in v.items() if k != "out"}
        o.update({k: x.get() for k, x in b.items()})
        o["simplify"] = float(o["simplify"] or 0)
        go.state(["disabled"])

        def work():
            try:
                process(list(files), v["out"].get(), o, log)
            finally:
                root.after(0, lambda: go.state(["!disabled"]))
        threading.Thread(target=work, daemon=True).start()
    go.configure(command=run)
    log(f"DTM data-prep tool {VERSION}. Add files, choose options, then Prepare files.")
    root.mainloop()


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not a.inputs:
        try:
            gui()
            return
        except Exception as e:  # no display available
            print(f"(window not available: {e})\n")
            ap.print_help()
            return
    process(a.inputs, a.out, opts_from_args(a))


if __name__ == "__main__":
    main()
