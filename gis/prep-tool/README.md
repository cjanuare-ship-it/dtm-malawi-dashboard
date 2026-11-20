# DTM Malawi · data-prep tool for the RE2CLID GIS workspace

Large files (hundreds of thousands of features, detailed boundaries, big rasters) load faster and draw more smoothly in the
web workspace when they are prepared first. This tool does that preparation on your computer with Python.

## Start it

**Windows:** double-click `run_dtm_prep.bat`. The first run installs what it needs (internet required once, a few minutes).
A window opens: add files, choose options, press **Prepare files**. Results go to the output folder as `*_web.geojson`,
`*_web.zip` or `*_web.tif`. Load those in the workspace with **Add data**.

**Mac / Linux / command line:**

```
pip install -r requirements.txt
python dtm_prep.py                                   # window
python dtm_prep.py INPUT ... -o OUTFOLDER [options]  # command line
python dtm_prep.py --help                            # all options
```

## Typical recipes

| Data | Command |
| --- | --- |
| Building footprints (hundreds of thousands) | `python dtm_prep.py buildings.zip -o web --simplify 2 --fields type --zip` |
| Detailed boundaries or rivers for national maps | `python dtm_prep.py rivers.shp -o web --simplify 50 --zip` |
| Household points → counts per TA | `python dtm_prep.py households.csv -o web --aggregate-to ta.shp --sum-fields hh_size` |
| One file per district | `python dtm_prep.py sites.gpkg -o web --split-by district` |
| Large flood, DEM or rainfall raster | `python dtm_prep.py flood.tif -o web --raster-max 3000 --clip-malawi` |
| Land cover or IPC class raster | `python dtm_prep.py landcover.tif -o web --categorical --clip-malawi` |

## Options

| Option | Meaning |
| --- | --- |
| `--simplify M` | Remove vertices that change the shape by less than M metres (lines and polygons). |
| `--decimals N` | Round coordinates (6 ≈ 0.1 m, 5 ≈ 1 m). |
| `--fields a,b` | Keep only these attribute fields. Empty fields are dropped unless `--keep-empty-fields`. |
| `--clip-malawi` / `--clip-file F` | Keep only the Malawi area, or the area of polygons in F. |
| `--split-by FIELD` | Write one file per value. |
| `--aggregate-to F` `--sum-fields a,b` | Count features (and sum fields) per polygon of F. |
| `--raster-max PX` | Largest raster side in pixels (the workspace shows up to 3072). |
| `--categorical` | Raster holds classes: keep the values, use majority resampling. |
| `--zip` | Zip each GeoJSON output. |

Each run writes `prep_report.txt` with feature, vertex and size counts before and after. The workspace stays smooth up to a
few million vertices per map; the report flags outputs above 2 million vertices or 60 MB.
