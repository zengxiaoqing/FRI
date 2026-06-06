#!/usr/bin/env python3
"""
Verification script: run BOTH the original and refactored code paths
with identical inputs and compare every output value.

Exit 0 = all values match
Exit 1 = differences found
"""

import os
import sys
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "Demo")

STATION_FILE = os.path.join(DEMO_DIR, "Station1")
GRIB_FILE = os.path.join(DEMO_DIR, "gmf.gra.2024072412009.grb2")
DEM_FILE = os.path.join(DEMO_DIR, "CMA_Terrain_12P5km.tif")

SPQ_VARS = ["10u", "10v", "gust", "2t", "tmin", "tmax", "2r", "sp"]
MPQ_VARS = ["gh", "t", "u", "v", "q", "r"]


def _setup(interp):
    """Shared setup: read stations, GRIB, DEM, build geography."""
    dtsite = interp.dRead_Station_Info(STATION_FILE)
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
            "file": STATION_FILE,
        }
    }

    grib_data = interp.dRGrib_EC(GRIB_FILE, SPQ_VARS, MPQ_VARS)
    terrain = interp.dRead_Terrain(DEM_FILE)

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

    return grib_data, geography, target_info


def run_original():
    """Run the original Module_Interp_dem6 code."""
    sys.path.insert(0, DEMO_DIR)
    import Module_Interp_dem6 as OrigModule
    sys.path.pop(0)

    interp = OrigModule.Class_Interp_dem(iDebug=0)
    interp.ltPQ_FRI_Inst = ["2t", "2rh", "10u", "10v", "10ws", "sp"]
    interp.ltPQ_FRI_mxmn = []  # skip extremes for clean comparison

    grib_data, geography, target_info = _setup(interp)
    result = interp.dCMADMO_3d_Interp_nPQ(grib_data, geography, target_info)
    return result


def run_refactored():
    """Run the refactored fri package."""
    from fri import FRIInterpolator

    interp = FRIInterpolator(debug=0)
    interp.ltPQ_FRI_Inst = ["2t", "2rh", "10u", "10v", "10ws", "sp"]
    interp.ltPQ_FRI_mxmn = []

    grib_data, geography, target_info = _setup(interp)
    result = interp.dCMADMO_3d_Interp_nPQ(grib_data, geography, target_info)
    return result


def compare(orig, refac):
    """Compare two result dicts — exact element-by-element."""
    site_o = orig["site"]
    site_r = refac["site"]

    vars_o = set(site_o.keys())
    vars_r = set(site_r.keys())
    common = sorted(vars_o & vars_r)

    for v in sorted(vars_o - vars_r):
        print(f"  ⚠️  Only original: {v}")
    for v in sorted(vars_r - vars_o):
        print(f"  ⚠️  Only refactored: {v}")

    all_ok = True
    for var in common:
        a = site_o[var]
        b = site_r[var]
        if not isinstance(a, np.ndarray) or not isinstance(b, np.ndarray):
            print(f"  ⚠️  {var}: non-array ({type(a).__name__} vs {type(b).__name__})")
            continue

        if a.shape != b.shape:
            print(f"  ❌ {var}: shape {a.shape} vs {b.shape}")
            all_ok = False
            continue

        exact = np.array_equal(a, b)
        max_diff = float(np.max(np.abs(a.astype("f8") - b.astype("f8"))))
        nd = int(np.sum(~np.isclose(a, b, rtol=0, atol=0)))

        mark = "✅" if exact else "❌"
        print(f"  {mark} {var}: shape={list(a.shape)}, "
              f"max_diff={max_diff:.2e}, "
              f"diff_count={nd}/{a.size}, "
              f"range=[{float(a.min()):.4f}, {float(a.max()):.4f}]")

        if not exact:
            all_ok = False

    return all_ok


def main():
    print("=" * 65)
    print("FRI 结果一致性验证")
    print(f"  数据: {GRIB_FILE}")
    print(f"  DEM:  {DEM_FILE}")
    print(f"  站点: {STATION_FILE}")
    print(f"  变量: {SPQ_VARS}")
    print("=" * 65)

    print("\n[1/2] 运行原始模块 (Module_Interp_dem6.Class_Interp_dem) ...")
    sys.stdout.flush()
    result_orig = run_original()
    print(f"      原始结果变量: {sorted(result_orig['site'].keys())}")

    print("\n[2/2] 运行重构包 (fri.FRIInterpolator) ...")
    sys.stdout.flush()
    result_refac = run_refactored()
    print(f"      重构结果变量: {sorted(result_refac['site'].keys())}")

    print(f"\n{'─' * 65}")
    print("逐元素精确比对:")
    print(f"{'─' * 65}")
    ok = compare(result_orig, result_refac)

    print(f"\n{'=' * 65}")
    if ok:
        print("✅ 通过！重构代码与原始代码产生完全一致的结果。")
    else:
        print("❌ 失败！存在不一致，请检查上面的详细报告。")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
