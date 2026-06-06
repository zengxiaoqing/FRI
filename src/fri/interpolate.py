"""
High-level convenience API for FRI interpolation.

Provides a single-function interface that wraps the full pipeline:
GRIB reading → DEM reading → geographic grid setup → interpolation.

Usage
-----
>>> from fri import fri_interpolate

>>> # Point interpolation (stations)
>>> result = fri_interpolate("forecast.grib2", "terrain.tif", "stations.txt")

>>> # Grid interpolation (regular grid)
>>> result = fri_interpolate("forecast.grib2", "terrain.tif", target={
...     "begin_lon": 100, "end_lon": 120,
...     "begin_lat": 20, "end_lat": 40,
...     "lon_res": 0.05, "lat_res": 0.05,
... }, target_dem="target_dem.tif")
"""

import os
import numpy as np


def _build_grid_target(target_cfg, target_dem_file):
    """Build a grid target_info entry from config dict.

    If target_dem is a GeoTIFF, crops the DEM window to the target area.
    If the DEM has no georeferencing (raw array), reads fully and trusts
    the user-provided lon/lat range.
    """
    import rasterio
    from rasterio.windows import from_bounds

    # Generate coordinate arrays
    lon1d = np.arange(target_cfg["begin_lon"],
                      target_cfg["end_lon"] + target_cfg["lon_res"] * 0.5,
                      target_cfg["lon_res"])
    lat1d = np.arange(target_cfg["begin_lat"],
                      target_cfg["end_lat"] + target_cfg["lat_res"] * 0.5,
                      target_cfg["lat_res"])
    Nlon, Nlat = len(lon1d), len(lat1d)
    lon2d, lat2d = np.meshgrid(lon1d, lat1d)

    # Read target DEM
    if isinstance(target_dem_file, dict):
        # Numpy array input — assume south-up, no flip needed
        dem_data = np.asarray(target_dem_file["data"], dtype="f4").copy()
        dem_data[dem_data < -1000] = 0.0
        dem_data[dem_data > 9000] = 0.0
    elif target_dem_file and os.path.exists(target_dem_file):
        # GeoTIFF file input — read and crop
        with rasterio.open(target_dem_file) as ds:
            try:
                window = from_bounds(
                    target_cfg["begin_lon"], target_cfg["begin_lat"],
                    target_cfg["end_lon"], target_cfg["end_lat"],
                    ds.transform,
                )
                dem_raw = ds.read(1, window=window)
            except Exception:
                dem_raw = ds.read(1)
            dem_data = dem_raw.astype("f4")
            nodata = ds.nodata if ds.nodata is not None else -9999
            dem_data[dem_raw == nodata] = 0.0
            dem_data[dem_data < -1000] = 0.0
            dem_data[dem_data > 9000] = 0.0
        dem_data = np.flipud(dem_data)  # north-up → south-up
    else:
        dem_data = np.zeros((Nlat, Nlon), dtype="f4")

    # Ensure DEM matches target grid shape; resample if needed
    if dem_data.shape != (Nlat, Nlon):
        from scipy.ndimage import zoom
        yr = Nlat / dem_data.shape[0]
        xr = Nlon / dem_data.shape[1]
        dem_data = zoom(dem_data, (yr, xr), order=1)

    return {
        "lon": lon2d.flatten(),
        "lat": lat2d.flatten(),
        "alt": dem_data.flatten(),
        "size": Nlat * Nlon,
        "dir": "Grid",
        "Nlon": Nlon,
        "Nlat": Nlat,
        "2dshape": (Nlat, Nlon),
        "begin_lon": target_cfg["begin_lon"],
        "end_lon": target_cfg["end_lon"],
        "lon_res": target_cfg["lon_res"],
        "begin_lat": target_cfg["begin_lat"],
        "end_lat": target_cfg["end_lat"],
        "lat_res": target_cfg["lat_res"],
    }


def fri_interpolate(
    grib_file=None,
    dem_file=None,
    station_file=None,
    *,
    config=None,
    target=None,
    target_dem=None,
    model=None,
    variables=None,
    output_file=None,
    output_format=None,
    debug=0,
):
    # ── Load config from YAML if provided ──────────────────────
    if config:
        import yaml
        with open(config) as f:
            cfg = yaml.safe_load(f)
        grib_file = cfg.get("grib_file", grib_file)
        dem_file = cfg.get("dem_file", dem_file)
        station_file = cfg.get("station_file", station_file)
        target = cfg.get("target", target)
        target_dem = cfg.get("target_dem", target_dem)
        variables = cfg.get("variables", variables)
        output_file = cfg.get("output_file", output_file)

    # Also support calling with a single config argument
    if isinstance(grib_file, str) and grib_file.endswith((".yaml", ".yml")):
        return fri_interpolate(config=grib_file)
    """Run FRI terrain-aware interpolation from file paths.

    The result is always returned as a Python dict (in-memory).
    If ``output_file`` is set, it is also written to disk;
    the format is auto-detected from the file extension.

    Parameters
    ----------
    grib_file : str
        Path to GRIB2 forecast file.
    dem_file : str
        Path to GeoTIFF digital elevation model.
    station_file : str, optional
        Path to station list file (point interpolation mode).
    target : dict, optional
        Grid configuration (grid interpolation mode):
        ``{"begin_lon": ..., "end_lon": ..., "lon_res": ...,
          "begin_lat": ..., "end_lat": ..., "lat_res": ...}``
    target_dem : str, optional
        Path to target grid DEM (required for grid mode).
    model : str, optional
        Deprecated. Now auto-detected from GRIB headers.
    variables : list of str, optional
        Variables to interpolate.
    output_file : str, optional
        Write results to this file (format from extension).
    output_format : str, optional
        Override format detection (``"netcdf"`` or ``"hdf5"``).
    debug : int
        Verbosity (0 = silent).

    Returns
    -------
    dict
        ``{"site": {var: ndarray}}`` or ``{"grid": {var: 2d_ndarray}}``.
    """
    # ── Determine target type ───────────────────────────────────
    grid_mode = isinstance(target, dict)
    if not grid_mode and station_file is None:
        raise ValueError("Either station_file or target (grid config) is required.")

    files_to_check = [grib_file]
    if isinstance(dem_file, str):
        files_to_check.append(dem_file)
    if station_file:
        files_to_check.append(station_file)
    if isinstance(target_dem, str):
        files_to_check.append(target_dem)

    for p in files_to_check:
        if isinstance(p, str) and not os.path.exists(p):
            raise FileNotFoundError(f"File not found: {p}")

    # ── Validate ────────────────────────────────────────────────
    from .validate import validate_inputs as _validate

    _fri_vars = variables or ["2t", "2rh", "10u", "10v", "10ws", "sp"]
    if grid_mode:
        report = _validate(grib_file, dem_file, fri_vars=_fri_vars)
    else:
        report = _validate(grib_file, dem_file, station_file, fri_vars=_fri_vars)
    if not report.passed:
        print("\nFRI input validation FAILED:")
        report.summarize()
        raise ValueError(
            "Input validation failed — fix errors above and retry."
        )

    # ── Auto-configure ──────────────────────────────────────────
    from .auto_config import auto_configure as _auto_config
    cfg = _auto_config(report)
    interp = cfg["interp"]
    interp.iDebug = debug
    interp.ltPQ_FRI_Inst = cfg["matched_vars"]
    interp.ltPQ_FRI_mxmn = []

    if variables is not None:
        interp.ltPQ_FRI_Inst = variables

    grib_data = cfg["grib_data"]
    geography = cfg["geography"]

    # ── Build target_info ───────────────────────────────────────
    if grid_mode:
        grid_info = _build_grid_target(target, target_dem)
        target_info = {"grid": grid_info}
        target_key = "grid"
        codes = None
        names = None
    else:
        dtsite = interp.dRead_Station_Info(station_file)
        codes, names, lons, lats, alts = [], [], [], [], []
        for code in dtsite:
            codes.append(code)
            names.append(dtsite[code][0])
            lons.append(dtsite[code][1])
            lats.append(dtsite[code][2])
            alts.append(dtsite[code][3])
        target_info = {
            "site": {
                "lon": np.array(lons),
                "lat": np.array(lats),
                "alt": np.array(alts),
                "size": len(codes),
                "dir": "Site",
                "code": codes,
                "file": os.path.abspath(station_file),
            }
        }
        target_key = "site"

    # ── Run interpolation ───────────────────────────────────────
    if cfg["has_dual_grid"]:
        result = interp.dECDMO_3d_Interp_nPQ(grib_data, geography, target_info)
    else:
        result = interp.dCMADMO_3d_Interp_nPQ(grib_data, geography, target_info)

    # ── File output ─────────────────────────────────────────────
    if output_file:
        from . import output as _output

        if output_format:
            fmt = output_format.lower()
        else:
            ext = os.path.splitext(output_file)[1].lower()
            fmt = "netcdf" if ext in (".nc", ".nc4") else "hdf5"

        attrs = {
            "grib_file": os.path.basename(grib_file),
            "dem_file": os.path.basename(dem_file),
        }

        if grid_mode:
            _output.write_output(
                output_file, result, [""] * target_info[target_key]["size"],
                station_lons=target_info[target_key]["lon"],
                station_lats=target_info[target_key]["lat"],
                station_alts=target_info[target_key]["alt"],
                attrs=attrs,
            )
        else:
            _output.write_output(
                output_file, result, codes, names,
                lons, lats, alts, attrs=attrs,
            )

    return result


def interpolate_from_files(
    self,
    grib_file: str,
    dem_file: str,
    station_file: str,
    model: str = None,
    variables: list = None,
    output_file: str = None,
):
    """Convenience method on FRIInterpolator."""
    return fri_interpolate(
        grib_file=grib_file,
        dem_file=dem_file,
        station_file=station_file,
        model=model,
        variables=variables or self.ltPQ_FRI_Inst,
        output_file=output_file,
        debug=self.iDebug,
    )
