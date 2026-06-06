#!/usr/bin/env python3
"""
FRI 4-panel comparison plot (final template).

Usage:
  python scripts/plot_comparison.py

Output:
  output/fri_grid_ec_comparison.png  (300 dpi, publication quality)
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "figure.dpi": 300,
    "savefig.dpi": 300,
})
import matplotlib.pyplot as plt
from matplotlib import gridspec
import numpy as np
from fri import fri_interpolate, FRIInterpolator
from scipy.spatial import cKDTree
import shapefile

# ── Config ──────────────────────────────────────────────────────
DEMO = "data/raw/Demo"
GRIB = f"{DEMO}/2024072412_009_C1D07241200072421001"
MODEL_DEM = f"{DEMO}/EC_Terrain_12P5km.tif"
TARGET_DEM = f"{DEMO}/Terrain_5km.tif"
SHAPEFILE = f"{DEMO}/cnhimap/cnhimap.shp"

# Region
LON1, LON2, LAT1, LAT2 = 115, 118, 39.3, 41.3

# Grid resolutions
RES_5KM = 0.05
RES_1KM = 0.01

# ── Data ───────────────────────────────────────────────────────
def load_data():
    i = FRIInterpolator()
    gd = i.dRGrib_EC(GRIB, ["2t"], ["gh"])
    raw = gd["2t"]
    mlon = np.arange(70, 140.001, 0.125)
    mlat = np.arange(0, 60.001, 0.125)
    ix = np.where((mlon >= LON1) & (mlon <= LON2))[0]
    iy = np.where((mlat >= LAT1) & (mlat <= LAT2))[0]
    raw_crop = raw[iy[0]:iy[-1]+1, ix[0]:ix[-1]+1]

    r5 = fri_interpolate(GRIB, MODEL_DEM,
        target={"begin_lon": LON1, "end_lon": LON2,
                "begin_lat": LAT1, "end_lat": LAT2,
                "lon_res": RES_5KM, "lat_res": RES_5KM},
        target_dem=TARGET_DEM, variables=["2t"])
    fri5 = r5["grid"]["2t"]

    r1 = fri_interpolate(GRIB, MODEL_DEM,
        target={"begin_lon": LON1, "end_lon": LON2,
                "begin_lat": LAT1, "end_lat": LAT2,
                "lon_res": RES_1KM, "lat_res": RES_1KM},
        target_dem=TARGET_DEM, variables=["2t"])
    fri1 = r1["grid"]["2t"]

    # NN 5km
    t5lon = np.arange(LON1, LON2 + 0.025, RES_5KM)
    t5lat = np.arange(LAT1, LAT2 + 0.025, RES_5KM)
    mlon2d, mlat2d = np.meshgrid(mlon, mlat)
    tree = cKDTree(np.column_stack([mlat2d.ravel(), mlon2d.ravel()]))
    _, idx = tree.query(np.column_stack([
        np.meshgrid(t5lon, t5lat)[1].ravel(),
        np.meshgrid(t5lon, t5lat)[0].ravel()]))
    nn5 = raw.ravel()[idx].reshape(t5lat.size, t5lon.size)

    return raw_crop, nn5, fri5, fri1


# ── Shapefile boundaries ────────────────────────────────────────
def load_boundaries():
    sf = shapefile.Reader(SHAPEFILE)
    boundaries = []
    for s in sf.shapes():
        pts_list, parts = list(s.points), list(s.parts) + [len(s.points)]
        for pi in range(len(parts) - 1):
            pts = np.array(pts_list[parts[pi]:parts[pi+1]])
            if len(pts) > 2:
                boundaries.append(pts)
    return boundaries


# ── Plot ────────────────────────────────────────────────────────
def make_plot(fields, titles, boundaries):
    asp = 1.0 / np.cos(np.radians((LAT1 + LAT2) / 2))
    vmin = min(f.min() for f in fields)
    vmax = max(f.max() for f in fields)

    fig = plt.figure(figsize=(22, 19))
    gs = gridspec.GridSpec(2, 2, figure=fig,
        wspace=0.015, hspace=0.08,
        left=0.10, right=0.92, bottom=0.18, top=0.92)

    for i, (fld, title) in enumerate(zip(fields, titles)):
        ax = fig.add_subplot(gs[i])
        im = ax.imshow(fld, extent=[LON1, LON2, LAT1, LAT2],
                       cmap="RdYlBu_r", origin="lower", aspect=asp)
        for b in boundaries:
            ax.plot(b[:, 0], b[:, 1], "-", color="#444444", linewidth=0.6)
        ax.set_xlim(LON1, LON2)
        ax.set_ylim(LAT1, LAT2)
        for sp in ["left", "bottom", "right", "top"]:
            ax.spines[sp].set_linewidth(1.5)

        ax.set_xticks(np.arange(LON1, LON2 + 0.5, 0.5))
        ax.set_yticks(np.arange(LAT1, LAT2 + 0.5, 0.5))
        show_x = (i >= 2)
        show_y = (i % 2 == 0)
        ax.tick_params(bottom=True, left=True, right=True, top=True,
                       labelbottom=show_x, labelleft=show_y,
                       labelsize=27, width=2, length=8, pad=10)
        if show_x:
            ax.set_xlabel("Longitude (°E)", fontsize=28, labelpad=15)
        if show_y:
            ax.set_ylabel("Latitude (°N)", fontsize=28, labelpad=15)
        ax.set_title(title, fontsize=20, fontweight="bold", pad=6)

    fig.suptitle("ECMWF 2m Temperature — Interpolation Method Comparison",
                 fontsize=24, fontweight="bold", y=0.97)

    cbar_ax = fig.add_axes([0.30, 0.045, 0.40, 0.025])
    cbar = fig.colorbar(im, cax=cbar_ax, orientation="horizontal")
    cbar.set_label("2 m Temperature (°C)", fontsize=22,
                   fontweight="bold", labelpad=15)
    cbar.ax.tick_params(labelsize=20, width=2, length=6)

    return fig


def main():
    print("Loading data ...")
    fields = load_data()
    print("Loading boundaries ...")
    boundaries = load_boundaries()
    print("Plotting ...")

    titles = [
        "(a) ECMWF Raw 12.5km",
        "(b) Nearest Neighbor 5km",
        "(c) FRI Terrain-aware 5km",
        "(d) FRI Terrain-aware 1km",
    ]
    fig = make_plot(fields, titles, boundaries)
    out = "output/fri_grid_ec_comparison.png"
    fig.savefig(out, dpi=300)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
