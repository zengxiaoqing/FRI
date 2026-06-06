"""
Input validation for FRI interpolation.

Checks all input data (GRIB, DEM, stations) before running the
interpolation pipeline. Fails fast with clear error messages.
Also extracts grid metadata from file headers for automatic
pipeline configuration.
"""

import os
import numpy as np

# ── Result type ─────────────────────────────────────────────────

class ValidationReport:
    """Structured validation result.

    Attributes
    ----------
    passed : bool
        True if all checks pass and interpolation can proceed.
    errors : list of str
        Fatal issues that must be fixed.
    warnings : list of str
        Non-fatal suggestions.
    grib_info : dict or None
        Detected GRIB metadata (variables, grids).
    dem_info : dict or None
        Detected DEM metadata (extent, resolution, shape).
    station_info : dict or None
        Detected station metadata (count, domain coverage).
    """

    def __init__(self):
        self.passed = True
        self.errors = []
        self.warnings = []
        self.grib_info = None
        self.dem_info = None
        self.station_info = None

    def _fail(self, msg):
        self.passed = False
        self.errors.append(msg)

    def _warn(self, msg):
        self.warnings.append(msg)

    def summarize(self):
        """Print a human-readable summary."""
        status = "✅ PASS" if self.passed else "❌ FAIL"
        print(f"FRI Input Validation: {status}")
        if self.grib_info:
            g = self.grib_info
            sv = g.get("surface_vars", [])
            pv = g.get("pressure_vars", [])
            sg = g.get("surface_grid", {})
            pg = g.get("pressure_grid")
            print(f"  GRIB: {len(sv)} surface vars, {len(pv)} pressure vars")
            print(f"    Surface grid: {sg.get('Nlon','?')}×{sg.get('Nlat','?')}, "
                  f"{sg.get('lon_res','?')}° res")
            if pg:
                print(f"    Pressure grid: {pg.get('Nlon','?')}×{pg.get('Nlat','?')}, "
                      f"{pg.get('lon_res','?')}° res (dual-grid)")
            else:
                print(f"    Pressure grid: same as surface (single-grid)")
        if self.dem_info:
            d = self.dem_info
            print(f"  DEM: {d['width']}×{d['height']}, {d['res_x']:.4f}° res")
        if self.station_info:
            s = self.station_info
            print(f"  Stations: {s['count']} loaded")
            if s.get("outside_domain"):
                print(f"    ⚠️  {s['outside_domain']} stations outside data domain")
            if s.get("suspicious_alt"):
                print(f"    ⚠️  {s['suspicious_alt']} stations with suspicious altitude")
        if self.warnings:
            for w in self.warnings:
                print(f"  ⚠️  {w}")
        if self.errors:
            for e in self.errors:
                print(f"  ❌ {e}")
        return self.passed


# ── Check: file existence ──────────────────────────────────────

def _check_file(path, label, report):
    if not os.path.isfile(path):
        report._fail(f"{label}: File not found: {path}")
        return False
    if os.path.getsize(path) == 0:
        report._fail(f"{label}: File is empty: {path}")
        return False
    return True


# ── Check: GRIB file ───────────────────────────────────────────

def _check_grib(filepath, fri_vars, report):
    """Validate GRIB file and extract grid metadata."""
    from eccodes import (codes_grib_new_from_file, codes_get,
                         codes_release, codes_get_values)

    # Try to open
    try:
        fh = open(filepath)
    except Exception as e:
        report._fail(f"GRIB: Cannot open file: {e}")
        return None

    # Scan all messages
    surface_found = {}
    pressure_found = {}
    surface_grid = None
    pressure_grid = None
    all_grids = []
    count = 0

    try:
        while True:
            igrib = codes_grib_new_from_file(fh)
            if igrib is None:
                break
            count += 1
            try:
                short_name = codes_get(igrib, "shortName")
                if short_name == "unknown":
                    cat = codes_get(igrib, "parameterCategory")
                    num = codes_get(igrib, "parameterNumber")
                    if cat == 6 and num == 1:
                        short_name = "tcc"
                    elif cat == 1 and num == 8:
                        short_name = "tp"

                level_type = codes_get(igrib, "typeOfLevel")
                level = codes_get(igrib, "level")
                Nj = codes_get(igrib, "Nj")
                Ni = codes_get(igrib, "Ni")

                # Read grid extent from GRIB header
                # GRIB edition 1: millidegrees (1e-3)
                # GRIB edition 2: microdegrees (1e-6)
                try:
                    edition = codes_get(igrib, "editionNumber")
                    # Determine scale factor
                    raw_lon = codes_get(igrib, "longitudeOfFirstGridPoint")
                    scale = 1e-6 if abs(raw_lon) > 180000 else 1e-3

                    lo1 = codes_get(igrib, "longitudeOfFirstGridPoint") * scale
                    la1 = codes_get(igrib, "latitudeOfFirstGridPoint") * scale
                    lo2 = codes_get(igrib, "longitudeOfLastGridPoint") * scale
                    la2 = codes_get(igrib, "latitudeOfLastGridPoint") * scale
                    di = codes_get(igrib, "iDirectionIncrement") * scale
                    dj = codes_get(igrib, "jDirectionIncrement") * scale
                    # GRIB stores north-up; ensure lat_start < lat_end
                    lat_start = min(la1, la2)
                    lat_end = max(la1, la2)
                    # Longitude: ensure start < end
                    lon_start = min(lo1, lo2)
                    lon_end = max(lo1, lo2)
                    grid_info = {
                        "Nlon": Ni, "Nlat": Nj,
                        "lon_start": lon_start, "lat_start": lat_start,
                        "lon_end": lon_end, "lat_end": lat_end,
                        "lon_res": di, "lat_res": dj,
                    }
                except Exception:
                    grid_info = {"Nlon": Ni, "Nlat": Nj}

                is_surface = level_type in ("sfc", "surface", "heightAboveGround",
                                             "heightAboveGroundLayer", "meanSea")
                is_pressure = level_type == "isobaricInhPa"

                if is_surface:
                    surface_found[short_name] = True
                    surface_grid = grid_info
                elif is_pressure:
                    if short_name not in pressure_found:
                        pressure_found[short_name] = set()
                    pressure_found[short_name].add(level)
                    pressure_grid = grid_info

                all_grids.append(grid_info)

            finally:
                codes_release(igrib)

    except Exception as e:
        report._fail(f"GRIB: Error reading file: {e}")
        return None
    finally:
        fh.close()

    if count == 0:
        report._fail("GRIB: File contains no GRIB messages")
        return None

    # Detect available FRI variables (lazy: only check what each needs)
    matched_vars, missing_vars = _check_variable_requirements(
        fri_vars, surface_found, pressure_found, report
    )

    if not matched_vars:
        report._fail(
            f"GRIB: None of the requested FRI variables ({fri_vars}) "
            f"were found in the file"
        )
        return None

    if missing_vars:
        report._warn(
            f"GRIB: Variables not found: {missing_vars}. "
            f"Will interpolate: {matched_vars}"
        )

    # Check multi-level data
    has_pressure = bool(pressure_found)
    if not has_pressure:
        report._fail(
            "GRIB: No pressure-level data found. "
            "FRI needs multi-level fields (gh, t, u, v) to compute lapse rates."
        )
        return None

    # Detect single vs dual grid
    has_dual_grid = False
    if surface_grid and pressure_grid:
        same_res = (abs(surface_grid.get("lon_res", 0) -
                        pressure_grid.get("lon_res", 0)) < 1e-6)
        has_dual_grid = not same_res

    result = {
        "count": count,
        "surface_vars": sorted(surface_found.keys()),
        "pressure_vars": {k: sorted(v) for k, v in pressure_found.items()},
        "matched_vars": matched_vars,
        "missing_vars": missing_vars,
        "has_dual_grid": has_dual_grid,
        "surface_grid": surface_grid,
        "pressure_grid": pressure_grid if has_dual_grid else None,
        "filename": report.grib_file,
    }
    return result


def _fri_to_grib_names(fri_var):
    """Map FRI variable name to possible GRIB short names."""
    mapping = {
        "2t": ["2t"],
        "2rh": ["2r", "2rh"],
        "10u": ["10u"],
        "10v": ["10v"],
        "10ws": ["10u", "10v"],  # derived from u/v
        "sp": ["sp"],
        "10gust": ["10fg3", "gust", "10gust", "i10fg"],
        "2t_max": ["mx2t3", "tmax"],
        "2t_min": ["mn2t3", "tmin"],
        "10ws_max": ["10gust", "10fg3", "gust", "i10fg"],
    }
    return mapping.get(fri_var, [fri_var])


# FRI variable → required pressure-level fields for lapse rate computation
_FRI_PRESSURE_NEEDS = {
    "2t": ["gh", "t", "sp"],
    "2rh": ["gh", "t", "sp"],
    "10u": ["gh", "u", "sp"],
    "10v": ["gh", "v", "sp"],
    "10ws": ["gh", "u", "v", "sp"],
    "sp": ["gh", "sp"],
    "2t_max": ["gh", "t", "sp"],
    "2t_min": ["gh", "t", "sp"],
    "10ws_max": ["gh", "u", "v", "sp"],
    "10gust": ["gh", "u", "v", "sp"],
}


def _check_variable_requirements(fri_vars, surface_found, pressure_found, report):
    """Lazy check: only verify what each requested variable actually needs."""
    available_surface = set(surface_found.keys())
    available_pressure = set(pressure_found.keys())

    # Minimum pressure requirement: gh + sp needed for ALL interpolation
    if "gh" not in available_pressure:
        report._fail("GRIB: No 'gh' (geopotential height) in pressure levels. "
                     "FRI needs pressure-level geopotential for lapse rate computation.")
        return [], []
    if "sp" not in available_surface:
        report._fail("GRIB: No 'sp' (surface pressure) found. "
                     "FRI needs surface pressure to locate the near-surface level.")
        return [], []

    matched = []
    missing = []

    for var in fri_vars:
        # Check surface variable
        grib_names = _fri_to_grib_names(var)
        surface_ok = any(sn in available_surface for sn in grib_names)

        # 10ws is derived from 10u+10v, not directly in GRIB
        if var == "10ws":
            surface_ok = ("10u" in available_surface and "10v" in available_surface)

        # 2rh can come from 2r or 2d
        if var == "2rh":
            surface_ok = ("2r" in available_surface or "2rh" in available_surface
                         or "2d" in available_surface)

        if not surface_ok:
            missing.append(var)
            report._warn(
                f"GRIB: Variable '{var}' not available in file "
                f"(looked for {grib_names}). Skipping."
            )
            continue

        # Check pressure requirements (optional — warn but not fail)
        needs = _FRI_PRESSURE_NEEDS.get(var, [])
        missing_pressure = [n for n in needs
                           if n not in available_pressure and n != "sp"]
        if missing_pressure:
            report._warn(
                f"GRIB: For '{var}', pressure-level data {missing_pressure} "
                f"not found. Lapse rate for this variable may be unavailable."
            )

        matched.append(var)

    return matched, missing


# ── Check: DEM file ─────────────────────────────────────────────

def _check_dem(dem_input, report):
    """Validate DEM and extract metadata.

    Accepts a GeoTIFF file path (str) or a dict with ``"data"`` (numpy array).
    """
    if isinstance(dem_input, dict):
        data = dem_input.get("data")
        if data is None:
            report._fail("DEM dict: missing required key 'data'")
            return None
        arr = np.asarray(data)
        info = {
            "width": arr.shape[1],
            "height": arr.shape[0],
            "count": 1,
            "crs": "user-provided",
            "left": dem_input.get("lon_start", 0),
            "right": dem_input.get("lon_end", 0),
            "top": dem_input.get("lat_end", 0),
            "bottom": dem_input.get("lat_start", 0),
            "res_x": dem_input.get("lon_res", 0),
            "res_y": dem_input.get("lat_res", 0),
            "dtype": str(arr.dtype),
            "filename": report.dem_file,
        }
        return info

    # File path: use rasterio
    try:
        import rasterio
    except ImportError:
        report._warn("DEM: rasterio not installed — skipping DEM validation")
        return {"skipped": True}

    try:
        with rasterio.open(dem_input) as ds:
            info = {
                "width": ds.width,
                "height": ds.height,
                "count": ds.count,
                "crs": str(ds.crs),
                "left": ds.bounds.left,
                "right": ds.bounds.right,
                "top": ds.bounds.top,
                "bottom": ds.bounds.bottom,
                "res_x": ds.res[0],
                "res_y": ds.res[1],
                "dtype": str(ds.dtypes[0]),
                "filename": report.dem_file,
            }
            if info["width"] <= 0 or info["height"] <= 0:
                report._fail(f"DEM: Invalid dimensions: {info['width']}×{info['height']}")
                return None
            return info
    except Exception as e:
        report._fail(f"DEM: Cannot read file: {e}")
        return None


# ── Check: stations file ────────────────────────────────────────

def _check_stations(filepath, grib_info, report):
    """Validate station file."""
    try:
        dtsite = {}
        with open(filepath, 'r', encoding='UTF-8') as fh:
            line = fh.readline()
            if not line:
                report._fail("Stations: File is empty")
                return None
            parts = line.split()
            if not parts or not parts[0].isdigit():
                report._fail(
                    "Stations: First line should contain station count (integer). "
                    f"Got: '{line.strip()}'"
                )
                return None
            n_expected = int(parts[0])
            for i in range(n_expected):
                line = fh.readline()
                if not line:
                    break
                import re
                parts = re.split('[, \t]', line.strip())
                parts = list(filter(None, parts))
                if len(parts) < 5:
                    report._warn(f"Stations: Line {i+2} has only {len(parts)} columns, "
                                 f"expected ≥5 (code, name, lon, lat, alt)")
                    continue
                try:
                    code = parts[0]
                    lon = float(parts[2])
                    lat = float(parts[3])
                    alt = float(parts[4])
                    dtsite[code] = [parts[1], lon, lat, alt, parts[5] if len(parts) > 5 else "",
                                    parts[6] if len(parts) > 6 else ""]
                except (ValueError, IndexError):
                    report._warn(f"Stations: Cannot parse line {i+2}: {line.strip()}")
                    continue

        if len(dtsite) == 0:
            report._fail("Stations: No valid station records found")
            return None

        # Check stations against GRIB domain
        outside = 0
        suspicious_alt = 0
        if grib_info:
            sg = grib_info.get("surface_grid", {})
            if sg and "lon_start" in sg:
                lon_min = min(sg["lon_start"], sg.get("lon_end", sg["lon_start"]))
                lon_max = max(sg["lon_start"], sg.get("lon_end", sg["lon_start"]))
                lat_min = min(sg["lat_start"], sg.get("lat_end", sg["lat_start"]))
                lat_max = max(sg["lat_start"], sg.get("lat_end", sg["lat_start"]))
                for code in dtsite:
                    s_lon = dtsite[code][1]
                    s_lat = dtsite[code][2]
                    if s_lon < lon_min or s_lon > lon_max or \
                       s_lat < lat_min or s_lat > lat_max:
                        outside += 1
                    s_alt = dtsite[code][3]
                    if s_alt < -500 or s_alt > 9000:
                        suspicious_alt += 1

        result = {
            "count": len(dtsite),
            "outside_domain": outside,
            "suspicious_alt": suspicious_alt,
            "codes": list(dtsite.keys()),
            "names": [dtsite[c][0] for c in dtsite],
            "lons": [dtsite[c][1] for c in dtsite],
            "lats": [dtsite[c][2] for c in dtsite],
            "alts": [dtsite[c][3] for c in dtsite],
            "filename": report.stations_file,
        }
        return result
    except Exception as e:
        report._fail(f"Stations: Error reading file: {e}")
        return None


# ── Check: GRIB-DEM compatibility ───────────────────────────────

def _check_compatibility(grib_info, dem_info, report):
    """Verify GRIB and DEM cover the same region."""
    if not grib_info or not dem_info:
        return

    sg = grib_info.get("surface_grid", {})
    if not sg or "lon_start" not in sg:
        return

    grib_left = sg["lon_start"]
    grib_right = sg.get("lon_end", grib_left)
    grib_bottom = sg["lat_start"]
    grib_top = sg.get("lat_end", grib_bottom)

    dem_left = dem_info.get("left", 0)
    dem_right = dem_info.get("right", 0)
    dem_bottom = dem_info.get("bottom", 0)
    dem_top = dem_info.get("top", 0)

    # Skip bounds comparison if DEM is a user-provided array without coordinates
    if dem_info.get("left") == 0 and dem_info.get("right") == 0:
        return
    # Allow ~0.5° tolerance for edge alignment
    tol = 0.5
    if abs(grib_left - dem_left) > tol:
        report._warn(
            f"Compatibility: GRIB west boundary ({grib_left:.2f}°E) "
            f"and DEM west boundary ({dem_left:.2f}°E) differ by "
            f"{abs(grib_left - dem_left):.2f}°"
        )
    if abs(grib_right - dem_right) > tol:
        report._warn(
            f"Compatibility: GRIB east boundary ({grib_right:.2f}°E) "
            f"and DEM east boundary ({dem_right:.2f}°E) differ by "
            f"{abs(grib_right - dem_right):.2f}°"
        )

    # Check DEM resolution is at least as fine as GRIB
    grib_res = sg.get("lon_res", 1)
    dem_res = dem_info.get("res_x", 0)
    if dem_res > 0 and dem_res > grib_res * 1.1:
        report._fail(
            f"Compatibility: DEM resolution ({dem_res:.4f}°) is coarser than "
            f"GRIB resolution ({grib_res:.4f}°). DEM must be at least as fine "
            f"as the GRIB grid for terrain correction."
        )


# ── Main entry point ───────────────────────────────────────────

def validate_inputs(grib_file, dem_file, stations_file=None,
                    fri_vars=None):
    """Validate all FRI input data and extract metadata.

    Call this before ``fri_interpolate()`` to check data compatibility
    and get a preview of what the pipeline will do.

    Parameters
    ----------
    grib_file : str
        Path to GRIB2 forecast file.
    dem_file : str
        Path to GeoTIFF DEM file.
    stations_file : str, optional
        Path to station list file (None for grid interpolation mode).
    fri_vars : list of str, optional
        Requested FRI variables. Default: standard 6-variable set.

    Returns
    -------
    ValidationReport
        With ``.passed``, ``.errors``, ``.warnings``, and metadata
        attributes (``.grib_info``, ``.dem_info``, ``.station_info``).
    """
    if fri_vars is None:
        fri_vars = ["2t", "2rh", "10u", "10v", "10ws", "sp"]

    report = ValidationReport()

    # 1. File existence (skip dict DEM — it's a numpy array, not a file)
    _check_file(grib_file, "GRIB", report)
    if isinstance(dem_file, str):
        _check_file(dem_file, "DEM", report)
    if stations_file:
        _check_file(stations_file, "Stations", report)

    # Store file paths for downstream use
    report.grib_file = grib_file
    report.dem_file = dem_file
    report.stations_file = stations_file or ""

    # 2. GRIB content
    if os.path.isfile(grib_file) and os.path.getsize(grib_file) > 0:
        report.grib_info = _check_grib(grib_file, fri_vars, report)

    # 3. DEM content
    if isinstance(dem_file, dict):
        report.dem_info = _check_dem(dem_file, report)
    elif os.path.isfile(dem_file) and os.path.getsize(dem_file) > 0:
        report.dem_info = _check_dem(dem_file, report)

    # 4. Stations content (skip for grid mode)
    if stations_file and os.path.isfile(stations_file) and os.path.getsize(stations_file) > 0:
        report.station_info = _check_stations(stations_file, report.grib_info, report)

    # 5. GRIB-DEM compatibility
    _check_compatibility(report.grib_info, report.dem_info, report)

    return report
