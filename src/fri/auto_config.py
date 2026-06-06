"""
Auto-configure the FRI interpolation pipeline from file headers.

Uses the ValidationReport to build the ``geography`` and
``target_info`` dicts that the interpolation engine needs,
eliminating the need for hardcoded model presets.
"""

import os
import numpy as np

from .interpolator import FRIInterpolator


# ── Build surface variable list ─────────────────────────────────

_SURFACE_VAR_PRIORITY = {
    "2t": ["2t"],           # 2m temperature
    "10u": ["10u"],         # 10m U wind
    "10v": ["10v"],         # 10m V wind
    "sp": ["sp"],           # surface pressure
    # RH sources — pick what's available
    "2rh": ["2rh", "2r"],   # 2m relative humidity (direct or mapped)
    "2d": ["2d"],           # dewpoint (for RH derivation in EC)
    # Gust sources
    "10gust": ["10fg3", "gust", "10gust", "i10fg"],
    # Temp extremes
    "mn2t3": ["mn2t3", "tmin"],
    "mx2t3": ["mx2t3", "tmax"],
}

_PRESSURE_VAR_PRIORITY = {
    "gh": ["gh"],
    "t": ["t"],
    "u": ["u"],
    "v": ["v"],
    "q": ["q"],
    "r": ["r"],
}


def _select_available(needed, available_grib_vars):
    """Pick the best GRIB shortName for each needed variable.

    Parameters
    ----------
    needed : dict
        {fri_name: [grib_shortname_aliases]}
    available_grib_vars : set or list
        What's actually in the GRIB file.

    Returns
    -------
    surface_list : list
        GRIB shortNames to pass to dRGrib_EC.
    has_dewpoint : bool
        Whether 2d is available (for RH derivation).
    has_direct_rh : bool
        Whether 2r/2rh is directly available.
    has_gust : bool
        Whether any gust variable is available.
    """
    selected = []
    has_dewpoint = False
    has_direct_rh = False
    has_gust = False
    available = set(available_grib_vars)

    for fri_name, aliases in needed.items():
        for alias in aliases:
            if alias in available:
                selected.append(alias)
                if alias == "2d":
                    has_dewpoint = True
                if alias in ("2rh", "2r"):
                    has_direct_rh = True
                if alias in ("10fg3", "gust", "10gust", "i10fg"):
                    has_gust = True
                break

    return selected, has_dewpoint, has_direct_rh, has_gust


# ── Build geography from grid metadata ──────────────────────────

def _build_sl_grid(interp, meta, dem_data):
    """Build the surface-level grid dict from metadata + DEM."""
    grid = interp.dlonlat_info(
        {
            "begin_lon": meta["lon_start"],
            "end_lon": meta["lon_end"],
            "begin_lat": meta["lat_start"],
            "end_lat": meta["lat_end"],
            "lon_res": meta["lon_res"],
            "lat_res": meta["lat_res"],
        },
        around=3,
        idebug=0,
        slabel="AUTO_SL",
    )
    grid["alt"] = dem_data
    grid["size"] = grid["ndy2d_x_lon"].size
    grid["filename"] = meta.get("filename", "")
    return grid


def _build_ml_grid(interp, meta):
    """Build the multi-level grid dict (or None)."""
    if meta is None:
        return None
    return interp.dlonlat_info(
        {
            "begin_lon": meta["lon_start"],
            "end_lon": meta["lon_end"],
            "begin_lat": meta["lat_start"],
            "end_lat": meta["lat_end"],
            "lon_res": meta["lon_res"],
            "lat_res": meta["lat_res"],
        },
        around=2,
        idebug=0,
        slabel="AUTO_ML",
    )


def _compute_common_mask(sl_grid, ml_grid):
    """Compute mask of SL grid points that exist in ML grid."""
    if ml_grid is None:
        return None
    mask_x = np.in1d(
        sl_grid["ndy2d_x_lon"].flatten(),
        ml_grid["ndy1d_x_lon"].flatten(),
    )
    mask_y = np.in1d(
        sl_grid["ndy2d_y_lat"].flatten(),
        ml_grid["ndy1d_y_lat"].flatten(),
    )
    return (mask_y * mask_x).reshape(sl_grid["tpshape_lonlat"])


# ── Main entry point ───────────────────────────────────────────

def auto_configure(report):
    """Build interpolation configuration from a ValidationReport.

    Parameters
    ----------
    report : ValidationReport
        Result of ``validate_inputs()``.

    Returns
    -------
    config : dict
        With keys:
        - ``interp``: FRIInterpolator instance (pre-configured)
        - ``grib_data``: parsed GRIB data dict
        - ``geography``: grid info dict for interpolation
        - ``target_info``: station info dict
        - ``surface_vars``: GRIB surface variable list used
        - ``pressure_vars``: GRIB pressure variable list used
        - ``matched_vars``: FRI variables that will be interpolated
        - ``has_dewpoint``: whether RH is derived from dewpoint
        - ``has_dual_grid``: whether dual-grid interpolation is needed
    """
    gi = report.grib_info
    si = report.station_info
    di = report.dem_info

    if gi is None:
        raise ValueError(
            "Cannot configure: missing GRIB info. "
            "Run validate_inputs() first."
        )

    avail_surface = list(gi.get("surface_vars", []))
    avail_pressure = list(gi.get("pressure_vars", {}).keys())

    # ── 1. Select variables ─────────────────────────────────────
    surface_sel, has_dewpoint, has_direct_rh, has_gust = \
        _select_available(_SURFACE_VAR_PRIORITY, avail_surface)

    pressure_sel, _, _, _ = \
        _select_available(_PRESSURE_VAR_PRIORITY, avail_pressure)

    # ── 2. Create interpolator ──────────────────────────────────
    interp = FRIInterpolator(debug=0)
    matched_vars = gi.get("matched_vars", ["2t", "10u", "10v", "10ws", "sp"])
    interp.ltPQ_FRI_Inst = matched_vars
    interp.ltPQ_FRI_mxmn = []  # extremes require gust variable

    # ── 3. Read GRIB data ───────────────────────────────────────
    grib_data = interp.dRGrib_EC(gi["filename"], surface_sel, pressure_sel)

    # ── 4. Read DEM data ───────────────────────────────────────
    dem_data = interp.dRead_Terrain(di["filename"])

    # ── 5. Build grids ──────────────────────────────────────────
    sl_meta = gi.get("surface_grid", {})
    ml_meta = gi.get("pressure_grid", None)

    sl_grid = _build_sl_grid(interp, sl_meta, dem_data)
    ml_grid = _build_ml_grid(interp, ml_meta) if gi.get("has_dual_grid") else None

    # ── 6. Build geography ──────────────────────────────────────
    geography = {
        "lonlat_SL_IG_mdl": sl_grid,
        "lonlat_ML_IG_mdl": ml_grid,
        "mask2d_common_12P5km_to_25km": _compute_common_mask(sl_grid, ml_grid),
    }

    # ── 7. Build target_info (station mode only; grid mode builds later) ──
    target_info = None
    if si is not None:
        target_info = {
            "site": {
                "lon": np.array(si["lons"], dtype="f8"),
                "lat": np.array(si["lats"], dtype="f8"),
                "alt": np.array(si["alts"], dtype="f8"),
                "size": si["count"],
                "dir": "Site",
                "code": si["codes"],
                "file": si.get("filename", ""),
            }
        }

    return {
        "interp": interp,
        "grib_data": grib_data,
        "geography": geography,
        "target_info": target_info,
        "surface_vars": surface_sel,
        "pressure_vars": pressure_sel,
        "matched_vars": matched_vars,
        "has_dewpoint": has_dewpoint,
        "has_dual_grid": gi.get("has_dual_grid", False),
    }
