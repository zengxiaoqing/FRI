#!/usr/bin/env python3
"""
FRI Demo — demonstrates both high-level and low-level API usage.

Run from project root:

    # High-level API (recommended for most users)
    python src/fri/demo.py high

    # Low-level API (fine-grained control)
    python src/fri/demo.py low

    # Default
    python src/fri/demo.py
"""
import os
import sys
import numpy as np

# Allow running directly from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
# 1. HIGH-LEVEL API  (1 function call)
# ═══════════════════════════════════════════════════════════════

def demo_high_level(model: str = "cma"):
    """Simplest way — one function wraps the entire pipeline."""
    from fri import fri_interpolate

    data_dir = "data/raw/Demo"

    # Map model to file names
    if model.lower() in ("ec", "ec_12p5km", "ecmwf"):
        grib_file = os.path.join(data_dir, "2024072412_009_C1D07241200072421001")
        dem_file = os.path.join(data_dir, "EC_Terrain_12P5km.tif")
        model_key = "ec"
    else:
        grib_file = os.path.join(data_dir, "gmf.gra.2024072412009.grb2")
        dem_file = os.path.join(data_dir, "CMA_Terrain_12P5km.tif")
        model_key = "cma"

    station_file = os.path.join(data_dir, "Station1")

    print(f"[high-level] model={model_key}")
    print(f"  GRIB:   {grib_file}")
    print(f"  DEM:    {dem_file}")
    print(f"  STN:    {station_file}")

    # ── One call ───────────────────────────────────────────────
    result = fri_interpolate(
        grib_file=grib_file,
        dem_file=dem_file,
        station_file=station_file,
        model=model_key,
        debug=0,
    )

    _show_results(result)
    return result


# ═══════════════════════════════════════════════════════════════
# 2. LOW-LEVEL API  (step-by-step, full control)
# ═══════════════════════════════════════════════════════════════

def demo_low_level(model: str = "cma"):
    """Full pipeline — same as the original FRI_AnyP_demo.py."""
    from fri import FRIInterpolator

    data_dir = "data/raw/Demo"
    interp = FRIInterpolator(debug=0)
    interp.ltPQ_FRI_Inst = ["2t", "2rh", "10u", "10v", "10ws", "sp"]

    # ── Read stations ──────────────────────────────────────────
    station_file = os.path.join(data_dir, "Station1")
    dtsite = interp.dRead_Station_Info(station_file)
    print(f"[low-level] Loaded {len(dtsite)} stations")

    codes, lons, lats, alts = [], [], [], []
    for code in dtsite:
        codes.append(code)
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
            "file": station_file,
        }
    }

    # ── Read GRIB ──────────────────────────────────────────────
    if model.lower() in ("ec", "ec_12p5km"):
        ltSPQ = ["10u", "10v", "10fg3", "2t", "mn2t3", "mx2t3", "2d", "sp"]
        ltMPQ = ["gh", "t", "u", "v", "q", "r"]
        grib_file = os.path.join(data_dir, "2024072412_009_C1D07241200072421001")
    else:
        ltSPQ = ["10u", "10v", "gust", "2t", "tmin", "tmax", "2r", "sp"]
        ltMPQ = ["gh", "t", "u", "v", "q", "r"]
        grib_file = os.path.join(data_dir, "gmf.gra.2024072412009.grb2")

    print(f"  GRIB: {grib_file}")
    grib_data = interp.dRGrib_EC(grib_file, ltSPQ, ltMPQ)

    # ── Read DEM terrain ───────────────────────────────────────
    if model.lower() in ("ec", "ec_12p5km"):
        dem_file = os.path.join(data_dir, "EC_Terrain_12P5km.tif")
    else:
        dem_file = os.path.join(data_dir, "CMA_Terrain_12P5km.tif")
    print(f"  DEM:  {dem_file}")
    terrain = interp.dRead_Terrain(dem_file)

    # ── Build geography ────────────────────────────────────────
    if model.lower() in ("ec", "ec_12p5km"):
        sl_grid = interp.dlonlat_info(
            {"begin_lon": 70, "end_lon": 140,
             "begin_lat": 0, "end_lat": 60,
             "lon_res": 0.125, "lat_res": 0.125},
            around=3, idebug=0, slabel="EC_SL_DMO",
        )
        ml_grid = interp.dlonlat_info(
            {"begin_lon": 70, "end_lon": 140,
             "begin_lat": 0, "end_lat": 60,
             "lon_res": 0.25, "lat_res": 0.25},
            around=2, idebug=0, slabel="EC_ML_DMO",
        )
        mask_x = np.in1d(sl_grid["ndy2d_x_lon"].flatten(),
                          ml_grid["ndy1d_x_lon"].flatten())
        mask_y = np.in1d(sl_grid["ndy2d_y_lat"].flatten(),
                          ml_grid["ndy1d_y_lat"].flatten())
        mask_common = (mask_y * mask_x).reshape(sl_grid["tpshape_lonlat"])
        sl_grid["alt"] = terrain
        sl_grid["size"] = sl_grid["ndy2d_x_lon"].size
        geography = {
            "lonlat_SL_IG_mdl": sl_grid,
            "lonlat_ML_IG_mdl": ml_grid,
            "mask2d_common_12P5km_to_25km": mask_common,
        }
    else:
        sl_grid = interp.dlonlat_info(
            {"begin_lon": 70, "end_lon": 140,
             "begin_lat": 0.0625, "end_lat": 60.0625,
             "lon_res": 0.125, "lat_res": 0.125},
            around=3, idebug=0, slabel="CMA_SL_DMO",
        )
        sl_grid["alt"] = terrain
        sl_grid["size"] = sl_grid["ndy2d_x_lon"].size
        geography = {
            "lonlat_SL_IG_mdl": sl_grid,
            "lonlat_ML_IG_mdl": None,
            "mask2d_common_12P5km_to_25km": None,
        }

    # ── Run interpolation ──────────────────────────────────────
    print("  Running interpolation...")
    if model.lower() in ("ec", "ec_12p5km"):
        result = interp.dECDMO_3d_Interp_nPQ(grib_data, geography, target_info)
    else:
        result = interp.dCMADMO_3d_Interp_nPQ(grib_data, geography, target_info)

    _show_results(result)
    return result


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _show_results(result):
    print("\n=== Results ===")
    site = result.get("site", result)
    for var, values in site.items():
        if isinstance(values, np.ndarray):
            print(f"  {var}: shape={values.shape}, "
                  f"min={values.min():.2f}, max={values.max():.2f}, "
                  f"mean={values.mean():.2f}")
    print()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    usage = (
        "Usage:\n"
        "  python src/fri/demo.py              (high-level, CMA)\n"
        "  python src/fri/demo.py high         (high-level, CMA)\n"
        "  python src/fri/demo.py high ec      (high-level, ECMWF)\n"
        "  python src/fri/demo.py low          (low-level,  CMA)\n"
        "  python src/fri/demo.py low ec       (low-level,  ECMWF)\n"
    )
    args = sys.argv[1:]

    level = "high"
    model = "cma"

    if len(args) >= 1:
        if args[0] in ("high", "low"):
            level = args[0]
        elif args[0] in ("ec", "cma", "ec_12p5km", "cma_12p5km", "--help", "-h"):
            if args[0] in ("--help", "-h"):
                print(usage)
                return
            model = args[0]
        else:
            print(f"Unknown argument: {args[0]}\n")
            print(usage)
            return

    if len(args) >= 2:
        model = args[1]

    if level == "high":
        demo_high_level(model)
    else:
        demo_low_level(model)


if __name__ == "__main__":
    main()
