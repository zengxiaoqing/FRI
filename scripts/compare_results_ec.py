#!/usr/bin/env python3
"""Additional verification: EC model (dual-grid, more complex path)."""

import os, sys, numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_DIR = os.path.join(PROJECT_ROOT, "data", "raw", "Demo")

STN = os.path.join(DEMO_DIR, "Station1")
GRIB_EC = os.path.join(DEMO_DIR, "2024072412_009_C1D07241200072421001")
DEM_EC = os.path.join(DEMO_DIR, "EC_Terrain_12P5km.tif")


def _setup_ec(interp):
    dtsite = interp.dRead_Station_Info(STN)
    codes, lons, lats, alts = [], [], [], []
    for code in dtsite:
        codes.append(code)
        lons.append(dtsite[code][1])
        lats.append(dtsite[code][2])
        alts.append(dtsite[code][3])

    ti = {"site": {
        "lon": np.array(lons), "lat": np.array(lats), "alt": np.array(alts),
        "size": len(codes), "dir": "Site", "code": codes, "file": STN,
    }}

    spq = ["10u","10v","10fg3","2t","mn2t3","mx2t3","2d","sp"]
    mpq = ["gh","t","u","v","q","r"]
    gd = interp.dRGrib_EC(GRIB_EC, spq, mpq)
    terrain = interp.dRead_Terrain(DEM_EC)

    sl = interp.dlonlat_info(
        {"begin_lon":70,"end_lon":140,"begin_lat":0,"end_lat":60,
         "lon_res":0.125,"lat_res":0.125},
        around=3, idebug=0, slabel="EC_SL_DMO")
    ml = interp.dlonlat_info(
        {"begin_lon":70,"end_lon":140,"begin_lat":0,"end_lat":60,
         "lon_res":0.25,"lat_res":0.25},
        around=2, idebug=0, slabel="EC_ML_DMO")

    mx = np.in1d(sl["ndy2d_x_lon"].flatten(), ml["ndy1d_x_lon"].flatten())
    my = np.in1d(sl["ndy2d_y_lat"].flatten(), ml["ndy1d_y_lat"].flatten())
    mc = (my * mx).reshape(sl["tpshape_lonlat"])

    sl["alt"] = terrain
    sl["size"] = sl["ndy2d_x_lon"].size

    geog = {"lonlat_SL_IG_mdl": sl, "lonlat_ML_IG_mdl": ml,
            "mask2d_common_12P5km_to_25km": mc}
    return gd, geog, ti


def run_orig_ec():
    sys.path.insert(0, DEMO_DIR)
    import Module_Interp_dem6 as M
    sys.path.pop(0)
    i = M.Class_Interp_dem(iDebug=0)
    i.ltPQ_FRI_Inst = ["2t","2rh","10u","10v","10ws","sp"]
    i.ltPQ_FRI_mxmn = []
    gd, gg, ti = _setup_ec(i)
    return i.dECDMO_3d_Interp_nPQ(gd, gg, ti)


def run_refac_ec():
    from fri import FRIInterpolator
    i = FRIInterpolator(debug=0)
    i.ltPQ_FRI_Inst = ["2t","2rh","10u","10v","10ws","sp"]
    i.ltPQ_FRI_mxmn = []
    gd, gg, ti = _setup_ec(i)
    return i.dECDMO_3d_Interp_nPQ(gd, gg, ti)


def main():
    print("=" * 65)
    print("FRI 一致性验证 — EC 模型 (双网格, 含递减率再插值)")
    print("=" * 65)

    print("\n[1/2] 原始模块 (EC) ...")
    sys.stdout.flush()
    ro = run_orig_ec()
    print(f"  OK, 变量: {sorted(ro['site'].keys())}")

    print("\n[2/2] 重构包 (EC) ...")
    sys.stdout.flush()
    rr = run_refac_ec()
    print(f"  OK, 变量: {sorted(rr['site'].keys())}")

    print(f"\n{'─' * 65}")
    all_ok = True
    for var in sorted(ro["site"].keys()):
        a, b = ro["site"][var], rr["site"][var]
        exact = np.array_equal(a, b)
        md = float(np.max(np.abs(a.astype("f8") - b.astype("f8"))))
        nd = int(np.sum(~np.isclose(a, b, rtol=0, atol=0)))
        mark = "✅" if exact else "❌"
        print(f"  {mark} {var}: max_diff={md:.2e}, diff_count={nd}/{a.size}, "
              f"range=[{float(a.min()):.4f}, {float(a.max()):.4f}]")
        if not exact:
            all_ok = False

    print(f"\n{'=' * 65}")
    if all_ok:
        print("✅ EC 模型验证通过！")
    else:
        print("❌ EC 模型存在差异！")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
