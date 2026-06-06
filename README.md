<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/version-0.1.0-orange" alt="Version">
</p>

# FRI: Fine-Resolution Interpolation for NWP Model Fields

**FRI** (Fine-Resolution Interpolation / 地形精细化插值) is a terrain-aware interpolation
algorithm for numerical weather prediction (NWP) model output. It corrects coarse-resolution
gridded forecasts using high-resolution digital elevation model (DEM) data and computed
vertical lapse rates, producing station-level or grid-level forecasts that account for local
topographic effects.

The algorithm was developed by Xiaoqing Zeng and colleagues at the China Meteorological
Administration.

> 曾晓青等, 一种针对模式预报场的精细化插值新方法

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start — Station Interpolation](#quick-start--station-interpolation)
3. [Quick Start — Grid Interpolation](#quick-start--grid-interpolation)
4. [Input Data Requirements](#input-data-requirements)
5. [Complete Workflow Guide](#complete-workflow-guide)
6. [Output Formats](#output-formats)
7. [Input Validation](#input-validation)
8. [YAML Configuration](#yaml-configuration)
9. [API Reference](#api-reference)
10. [Model Support Details](#model-support-details)
11. [Citation](#citation)
12. [License](#license)

---

## Installation

### From PyPI (recommended)

```bash
pip install fri-collect
```

With optional visualization support:

```bash
pip install "fri-collect[vis]"
```

With NetCDF output support:

```bash
pip install "fri-collect[io]"
```

### From Source

```bash
git clone https://github.com/zengxiaoqing/FRI.git
cd FRI
pip install -e ".[dev]"
```

### Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| numpy, scipy | ✅ | Array math, RegularGridInterpolator |
| h5py | ✅ | HDF5 data I/O |
| pandas | ✅ | Station data handling |
| eccodes | ✅ | GRIB2 decoding (ECMWF ecCodes C library) |
| rasterio | ✅ | GeoTIFF DEM reading |
| netCDF4 | ❌ | NetCDF output (`[io]`) |
| matplotlib, cartopy | ❌ | Visualization (`[vis]`) |

---

## Quick Start — Station Interpolation

Interpolate ECMWF or CMA-GFS model data to weather station locations.

### Minimal Example (3 lines)

```python
from fri import fri_interpolate

result = fri_interpolate("forecast.grib2", "terrain.tif", "stations.txt")
print(result["site"]["2t"])   # 2m temperature at each station
```

**No model parameter needed.** Grid range, resolution, and single/dual-grid status
are automatically detected from the GRIB file headers.

### Step-by-Step Example

```python
from fri import fri_interpolate, validate_inputs

# 1. (Optional) Preview input data
report = validate_inputs("forecast.grib2", "terrain.tif", "stations.txt")
report.summarize()
# FRI Input Validation: ✅ PASS
#   GRIB: 16 surface vars, 5 pressure vars
#   Surface grid: 561×481, 0.125° res
#   DEM: 561×481, 0.125° res
#   Stations: 2472 loaded

# 2. Run interpolation
result = fri_interpolate(
    "forecast.grib2",
    "terrain.tif",
    "stations.txt",
    variables=["2t", "10u", "10v", "sp"],  # only these variables
)

# 3. Access results
for var in ["2t", "10u", "10v", "sp"]:
    values = result["site"][var]
    print(f"{var}: min={values.min():.2f}, max={values.max():.2f}")

# 4. Save to NetCDF
result = fri_interpolate(
    "forecast.grib2", "terrain.tif", "stations.txt",
    output_file="result.nc",
)
```

### Station File Format

Plain text, space/tab/comma separated:

```
<N>
<code>  <name>  <lon>  <lat>  <alt>  <province>  <city>
...
```

Columns: `code  name  lon  lat  alt(米)  province  city`

---

## Quick Start — Grid Interpolation

Interpolate model data to a regular latitude-longitude grid (e.g., 5 km × 5 km).

### Minimal Example

```python
from fri import fri_interpolate

result = fri_interpolate(
    "forecast.grib2",
    "terrain.tif",
    target={
        "begin_lon": 115, "end_lon": 117,
        "begin_lat": 30, "end_lat": 32,
        "lon_res": 0.05, "lat_res": 0.05,      # ~5 km resolution
    },
    target_dem="high_res_terrain.tif",           # target grid DEM
)

print(result["grid"]["2t"].shape)  # (41, 41)  2D array
```

### Step-by-Step Example

```python
from fri import fri_interpolate

# 1 km resolution grid
result = fri_interpolate(
    "forecast.grib2",
    "terrain.tif",
    target={
        "begin_lon": 115, "end_lon": 117,
        "begin_lat": 30, "end_lat": 32,
        "lon_res": 0.01, "lat_res": 0.01,       # ~1 km
    },
    target_dem="high_res_terrain.tif",
    variables=["2t", "10ws"],
)

# Result is 2D arrays
temperature_2d = result["grid"]["2t"]  # shape (201, 201)
wind_2d = result["grid"]["10ws"]       # shape (201, 201)
```

---

## Input Data Requirements

### Three Inputs for Station Mode

| # | Input | Format | Description |
|---|-------|--------|-------------|
| 1 | **GRIB file** | `.grib2` / `.grb2` | NWP forecast (ECMWF, CMA-GFS, or any GRIB2) |
| 2 | **DEM file** | `.tif` or numpy dict | Model terrain elevation (GeoTIFF or numpy array) |
| 3 | **Station file** | `.txt` | Target point list with lon/lat/alt |

### Four Inputs for Grid Mode

| # | Input | Format | Description |
|---|-------|--------|-------------|
| 1 | **GRIB file** | `.grib2` | NWP forecast |
| 2 | **DEM file** | `.tif` or numpy dict | Model terrain elevation |
| 3 | **Target grid config** | Python dict | Grid bounds and resolution |
| 4 | **Target DEM** | `.tif` or numpy dict | Elevation on the target grid |

### DEM Input — Two Formats

**Format 1: GeoTIFF file** (auto-reads lon/lat from geotransform)

```python
dem_file = "EC_Terrain_12P5km.tif"
```

**Format 2: NumPy array** (user provides data + metadata)

```python
import numpy as np
dem_file = {
    "data": my_2d_array,                    # shape (Nlat, Nlon), south-up
    "lon_start": 70, "lon_end": 140,        # optional
    "lat_start": 0, "lat_end": 60,          # optional
    "lon_res": 0.125, "lat_res": 0.125,     # optional
}
```

The DEM orientation must be **south-up** (row 0 = southernmost latitude),
matching the internal convention after the GeoTIFF flip.

---

## Complete Workflow Guide

### 1. Prepare Input Files

```
project/
├── forecast.grib2          # NWP model output
├── model_terrain.tif       # DEM at model resolution
├── stations.txt            # Target points
└── target_terrain.tif      # (optional, for grid mode)
```

### 2. Validate Inputs (Recommended First Step)

```python
from fri import validate_inputs

report = validate_inputs("forecast.grib2", "model_terrain.tif", "stations.txt")

if not report.passed:
    report.summarize()  # shows all errors
    # Fix issues before proceeding
else:
    # Preview detected info
    g = report.grib_info
    print(f"Grid: {g['surface_grid']['Nlon']}×{g['surface_grid']['Nlat']}")
    print(f"Available vars: {g['surface_vars'][:5]}...")
    print(f"Dual grid: {g['has_dual_grid']}")
```

The validator checks:
- ✅ File existence
- ✅ GRIB is readable and contains forecast data
- ✅ Required variables exist (lazy check — only what you need)
- ✅ DEM is readable and its extent matches the GRIB data
- ✅ Stations are within the data domain
- ✅ GRIB grid vs DEM grid resolution compatibility
- ✅ Single vs dual grid (surface and pressure level resolution)

### 3. Run Interpolation

```python
from fri import fri_interpolate

# Station mode
result = fri_interpolate(
    "forecast.grib2", "model_terrain.tif", "stations.txt",
    variables=["2t", "2rh", "10u", "10v", "10ws", "sp"],
    output_file="result.nc",             # optional .nc or .h5 output
)
print(result["site"]["2t"])  # 1D array per station

# Grid mode
result = fri_interpolate(
    "forecast.grib2", "model_terrain.tif",
    target={"begin_lon": 115, "end_lon": 117,
            "begin_lat": 30, "end_lat": 32,
            "lon_res": 0.05, "lat_res": 0.05},
    target_dem="target_terrain.tif",
    output_file="grid_result.nc",
)
print(result["grid"]["2t"])  # 2D array
```

### 4. Access and Use Results

```python
# Station mode: 1D arrays indexed by station
temps = result["site"]["2t"]        # shape (Nstations,)
press = result["site"]["sp"]

# Grid mode: 2D arrays indexed by (lat, lon)
temps_grid = result["grid"]["2t"]   # shape (Nlat, Nlon)

# Save manually
from fri import write_netcdf, write_hdf5
write_netcdf("manual_output.nc", result, station_codes, station_names,
             station_lons, station_lats, station_alts)
```

---

## Output Formats

### In-Memory (always returned)

```python
result["site"]["2t"]   # 1D numpy array for stations
result["grid"]["2t"]   # 2D numpy array for grids
```

### NetCDF (`.nc`)

CF-compliant NetCDF4 with station/grid metadata:

```
$ ncdump -h result.nc
dimensions:
    station = 2472
variables:
    float station_lon(station)  ; units = "degrees_east"
    float station_lat(station)  ; units = "degrees_north"
    float station_alt(station)  ; units = "m"
    char  station_code(station) ;
    char  station_name(station) ;
    float 2t(station)           ; units = "degC"
    float 2rh(station)          ; units = "%"
    ...
```

### HDF5 (`.h5`)

```python
import h5py
with h5py.File("result.h5", "r") as f:
    print(list(f.keys()))
    # ['2t', '2rh', '10u', '10v', '10ws', 'sp',
    #  'station_code', 'station_lon', 'station_lat', 'station_alt']
    temps = f["2t"][:]
```

---

## Input Validation

Call `validate_inputs()` before interpolation to check data compatibility:

```python
from fri import validate_inputs

report = validate_inputs("forecast.grib2", "terrain.tif", "stations.txt")
report.summarize()
```

Output example:

```
FRI Input Validation: ✅ PASS
  GRIB: 16 surface vars, 5 pressure vars
    Surface grid: 561×481, 0.125° res
    Pressure grid: same as surface (single-grid)
  DEM: 561×481, 0.1250° res
  Stations: 2472 loaded

# Or if something is wrong:
FRI Input Validation: ❌ FAIL
  ❌ GRIB: None of the requested FRI variables were found in the file
  ❌ Compatibility: DEM resolution (0.25°) is coarser than GRIB (0.125°)
```

### What Gets Checked

| Check | What It Detects |
|-------|----------------|
| File existence | Missing or empty files |
| GRIB validity | Corrupted or non-GRIB files |
| Variable availability | Lazy check — only verifies what you requested |
| Pressure-level data | FRI needs `gh`, `t`, `sp` for lapse rate computation |
| Grid detection | Automatically reads lon/lat range and resolution from GRIB headers |
| Single/dual grid | Detects if surface and pressure grids have different resolutions |
| DEM validity | Corrupted or unreadable GeoTIFF |
| GRIB-DEM extent match | Warns if geographic boundaries differ by >0.5° |
| DEM resolution | Must be at least as fine as the GRIB grid |
| Station domain check | Counts stations outside the data domain |
| Station format | Validates column count and numeric fields |

---

## YAML Configuration

For users who prefer configuration files over Python code.

### Template

Copy the template and edit:

```bash
cp docs/fri_config.yaml my_config.yaml
```

Example `my_config.yaml`:

```yaml
grib_file: "/data/forecast/gmf.gra.2024072412009.grb2"
dem_file: "/data/terrain/CMA_Terrain_12P5km.tif"
station_file: "/data/stations/Station1.txt"
variables:
  - "2t"
  - "2rh"
  - "10ws"
output_file: "/output/result.nc"
```

### Usage

```python
from fri import fri_interpolate

result = fri_interpolate(config="my_config.yaml")
```

---

## API Reference

### `fri_interpolate()`

```python
fri_interpolate(
    grib_file: str,
    dem_file: str | dict,
    station_file: str = None,
    *,
    target: dict = None,
    target_dem: str | dict = None,
    config: str = None,
    variables: list = None,
    output_file: str = None,
    output_format: str = None,
    debug: int = 0,
) -> dict
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `grib_file` | str | — | GRIB2 forecast file |
| `dem_file` | str or dict | — | Model DEM (GeoTIFF path or numpy dict) |
| `station_file` | str | None | Station list (station mode) |
| `target` | dict | None | Grid config (grid mode): `{begin_lon, end_lon, lon_res, ...}` |
| `target_dem` | str or dict | None | Target grid DEM (required for grid mode) |
| `config` | str | None | YAML config file path |
| `variables` | list | all 6 vars | Variables to interpolate |
| `output_file` | str | None | Output path (`.nc` → NetCDF, `.h5` → HDF5) |
| `debug` | int | 0 | Verbosity level |

Returns: `{"site": {var: ndarray}}` or `{"grid": {var: 2d_array}}`

### `validate_inputs()`

```python
validate_inputs(
    grib_file: str,
    dem_file: str | dict,
    stations_file: str = None,
    fri_vars: list = None,
) -> ValidationReport
```

### `FRIInterpolator` Class Methods

| New Name | Original Name | Description |
|----------|--------------|-------------|
| `read_grib(file, surf, pres)` | `dRGrib_EC` | Decode GRIB2 → numpy arrays |
| `read_dem(input)` | `dRead_Terrain` | Read DEM (file or numpy dict) |
| `read_stations(file)` | `dRead_Station_Info` | Parse station file |
| `build_grid(cfg)` | `dlonlat_info` | Build lon/lat grid arrays |
| `interpolate_ec(...)` | `dECDMO_3d_Interp_nPQ` | ECMWF interpolation pipeline |
| `interpolate_cma(...)` | `dCMADMO_3d_Interp_nPQ` | CMA-GFS interpolation pipeline |
| `write_hdf5(path, data)` | `dWS3_Interp` | Write HDF5 output |
| `write_netcdf(path, ...)` | — | Write NetCDF output |
| `write_output(path, ...)` | — | Auto-detect format from extension |
| `expand_wind(data)` | `dwind_expand` | Compute wind speed from U/V |
| `expand_rh(data)` | `drh_expand` | Compute RH from dewpoint |
| `merge_levels(data)` | `dMulti_Level_merge` | Merge multi-level → 2D array |

All original names (`dRead_Station_Info`, `dRGrib_EC`, etc.) are preserved as
aliases for backward compatibility.

---

## Model Support Details

| Feature | ECMWF (`ec`) | CMA-GFS (`cma`) |
|---------|-------------|-----------------|
| Surface variables | `10u,10v,10fg3,2t,mn2t3,mx2t3,2d,sp` | `10u,10v,gust,2t,tmin,tmax,2r,sp` |
| Pressure levels | `gh,t,u,v,q,r` | `gh,t,u,v,q,r` |
| Grid resolution | SL: 0.125° / ML: 0.25° (dual) | 0.125° (uniform) |
| Grid range | 70–140°E, 0–60°N | 70–140°E, 0.0625–60.0625°N |
| RH source | Derived from dewpoint (2d) | Direct (2r → 2rh) |
| Lapse rate path | 25 km → 12.5 km mesh interpolation | Single grid, no mesh step |
| Weighting factor (eta) | Available for all variables | Available for all variables |

**Custom models**: Any GRIB2 file with surface and pressure-level data can be
used. Grid information is auto-detected from file headers.

---

## Citation

If you use this algorithm in research, please cite the original paper:

```bibtex
@article{zeng_fri,
  author  = {曾晓青 and others},
  title   = {一种针对模式预报场的精细化插值新方法},
  journal = {气象},
  year    = {2022},
}
```

And the software package:

```bibtex
@software{fri_collect,
  title  = {FRI\_collect: Fine-Resolution Interpolation Toolkit},
  author = {Zeng, Xiaoqing and others},
  year   = {2025},
  url    = {https://github.com/zengxiaoqing/FRI},
}
```

---

## License

[MIT License](LICENSE)

---

## Verification

```bash
# Result consistency check (CMA + EC dual model)
python scripts/compare_results.py
python scripts/compare_results_ec.py

# Generate comparison plots
python scripts/plot_comparison.py  # → output/fri_grid_ec_comparison.png
```
