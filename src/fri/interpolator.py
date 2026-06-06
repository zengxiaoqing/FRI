"""
FRI Interpolator — Fine-Resolution Interpolation for NWP Model Fields
=====================================================================

A terrain-aware interpolation algorithm that corrects coarse-resolution
numerical weather prediction (NWP) model output using vertical lapse
rates and high-resolution digital elevation model (DEM) data.

The algorithm:
  1. Reads raw NWP GRIB2 data (ECMWF or CMA-GFS) and DEM terrain
  2. Computes vertical lapse rates for each variable using model levels
  3. Interpolates lapse rates from coarse grid to fine grid (EC only)
  4. For each target station:
     a. Finds 4 surrounding grid points
     b. Corrects each point using: corrected = forecast + (station_alt - grid_alt) × lapse_rate × η
     c. Bilinearly interpolates the 4 corrected values to the station
  5. Returns dict of corrected values per station

Reference
---------
曾晓青等, 一种针对模式预报场的精细化插值新方法
"""

import os
import re
import h5py
import numpy as np
from scipy import interpolate
from shutil import copyfile


class FRIInterpolator:
    """Terrain-aware interpolation engine for NWP model fields.

    Parameters
    ----------
    debug : int, optional
        Debug level (0 = silent, 1 = verbose). Default 0.
    """

    def __init__(self, debug=0, iDebug=None):
        # Support both debug= (new) and iDebug= (legacy) parameter names
        if iDebug is not None:
            self.iDebug = iDebug
        else:
            self.iDebug = debug
        self.RGrid_Default = -32766.0
        self.RCAbsZero = 273.15
        self.fcalm_wd = 999017.0
        self.seta_dir = "eta"
        self.iN_Frost_Time = 0
        self.ltForecast_Time = [0, 24]
        self.dymdl_Geog = None
        self.dyIntp_info = None

        # Default variable names for multi-level (pressure) fields
        self.ltMPQ_shortname = ["gh", "t", "u", "v", "q", "r"]
        # Default variable names for single-level (surface) fields
        self.ltSPQ_shortname = ["10u", "10v", "10fg3", "2t", "mn2t3", "mx2t3",
                                "2d", "sp", "tp", "tcwv", "tcc"]
        # FRI terrain-interpolated instantaneous variables
        self.ltPQ_FRI_Inst = ['2t', '2rh', '10u', '10v', '10ws', 'sp']
        # FRI terrain-interpolated extreme variables
        self.ltPQ_FRI_mxmn = ['2t_max', '2t_min', '2rh_max', '2rh_min', '10ws_max']
        self.ltPQ_FRI_mxmn_fh = ['2t_max_fh', '2t_min_fh', '2rh_max_fh',
                                 '2rh_min_fh', '10ws_max_fh']
        # Bilinear-interpolated multi-level variables
        self.ltPQ_BIL_ML = ['gh', 't', 'u', 'v', 'r', 'q']
        # Bilinear-interpolated single-level variables
        self.ltPQ_BIL_SL = ['tp', 'tcc', 'tcwv']
        # Vertical lapse rate names
        self.ltgamma_name = ['gamma_' + x for x in self.ltPQ_FRI_Inst]
        # Isobaric levels (hPa)
        self.ltisobaric = [1000, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300]

        # Output precision (decimal places) per variable
        self.dyPQ_round = {
            "2t": 1, "2rh": 1, "10u": 1, "10v": 1, "10ws": 1,
            "10gust": 1, "mn2t3": 1, "mx2t3": 1, "tcc": 2,
            "2t_max": 1, "2t_min": 1, "2rh_max": 1, "2rh_min": 1,
            "10ws_max": 1, "sp": 1,
            'gh': 1, 't': 1, 'u': 1, 'v': 1, 'r': 0, 'q': 1,
            'tp': 1, 'tcc': 0, 'tcwv': 1,
            'gamma_sp': 4, 'gamma_2t': 4, 'gamma_2rh': 4,
            'gamma_10u': 4, 'gamma_10v': 4, 'gamma_10ws': 4,
            "lonlat": 3, 'alt': 1,
        }
        # Quality control ranges [min, max] per variable
        self.dyPQ_QC = {
            "2t": [-60, 60], "2rh": [0, 100], "10u": [-80, 80],
            "10v": [-80, 80], "10ws": [0, 80], "10gust": [0, 80],
            "mn2t3": [-60, 60], "mx2t3": [-60, 60], "tcc": [0, 100],
            "2t_max": [-60, 60], "2t_min": [-60, 60],
            "2rh_max": [0, 100], "2rh_min": [0, 100],
            "10ws_max": [0, 80], "sp": [200, 1100],
        }

    # ------------------------------------------------------------------
    # Data reading helpers
    # ------------------------------------------------------------------

    def read_stations(self, filepath):
        """Read station metadata from a text file.

        Expected format: first line = station count, then one station per line
        with columns: code, name, lon, lat, alt, province, city.

        Parameters
        ----------
        filepath : str
            Path to station info file.

        Returns
        -------
        dict
            {station_code: [name, lon, lat, alt, province, city], ...}
        """
        return self.dRead_Station_Info(filepath)

    def dRead_Station_Info(self, filepath):
        with open(filepath, 'r', encoding='UTF-8') as fh:
            n_sites = int(fh.readline().split()[0])
            stations = {}
            for _ in range(n_sites):
                parts = re.split('[, \t]', fh.readline().strip())
                parts = list(filter(None, parts))
                stations[parts[0]] = [
                    parts[1],
                    float(parts[2]),
                    float(parts[3]),
                    float(parts[4]),
                    parts[5], parts[6],
                ]
        return stations

    def read_terrain(self, filepath):
        """Read DEM terrain elevation from a GeoTIFF file.

        Parameters
        ----------
        filepath : str
            Path to GeoTIFF file.

        Returns
        -------
        numpy.ndarray
            2D elevation array (m), oriented south-north (top) west-east (left).
        """
        return self.dRead_Terrain(filepath)

    def dRead_Terrain(self, dem_input):
        """Read DEM terrain data.

        Parameters
        ----------
        dem_input : str or dict
            If str: path to GeoTIFF file (rasterio-readable).
            If dict: must have key ``"data"`` (2D numpy array, south-up),
            plus optionally ``"lon_start"``, ``"lon_end"``, ``"lon_res"``,
            ``"lat_start"``, ``"lat_end"``, ``"lat_res"`` for metadata.

        Returns
        -------
        numpy.ndarray
            2D elevation array, south-up orientation.
        """
        if isinstance(dem_input, dict):
            data = np.asarray(dem_input["data"], dtype="f4")
            if data.ndim != 2:
                raise ValueError(
                    f"DEM data must be a 2D array, got shape {data.shape}"
                )
            data = np.round(data, 1)
            data[data <= -1000.] = 0
            data[data >= 9000.] = 0
            return data
        # Default: file path
        import rasterio
        with rasterio.open(dem_input) as dsr:
            data = dsr.read(1)
            data = np.round(data.astype("float32"), 1)
            data[data <= -1000.] = 0
            data[data >= 9000.] = 0
            data = np.flipud(data)
        return data

    def read_grib(self, filepath, surface_vars, pressure_vars,
                  isobaric_levels=None, sl_bound=None, ml_bound=None):
        """Read GRIB2 data from ECMWF/CMA format files.

        Parameters
        ----------
        filepath : str
            Path to GRIB2 file.
        surface_vars : list of str
            Single-level (surface) variable short names to extract.
        pressure_vars : list of str
            Multi-level (pressure) variable short names to extract.
        isobaric_levels : list of int, optional
            Specific pressure levels to keep (hPa).
        sl_bound : list of int, optional
            [lat_start, lat_end, lon_start, lon_end] for surface crop.
        ml_bound : list of int, optional
            [lat_start, lat_end, lon_start, lon_end] for multi-level crop.

        Returns
        -------
        dict
            Keys are variable names. Single-level values are 2D ndarrays;
            multi-level values are dicts of {level: 2D ndarray}.
            All arrays oriented south-north, west-east.
        """
        return self.dRGrib_EC(filepath, surface_vars, pressure_vars,
                              isobaric_levels, sl_bound, ml_bound)

    def dRGrib_EC(self, filepath, surface_vars, pressure_vars,
                  isobaric_levels=None, sl_bound=None, ml_bound=None):
        from eccodes import (codes_grib_new_from_file, codes_get,
                             codes_get_values, codes_release)
        with open(filepath) as fh:
            data = {}
            while True:
                igrib = codes_grib_new_from_file(fh)
                if igrib is None:
                    break
                short_name = codes_get(igrib, "shortName")
                if short_name == "unknown":
                    cat = codes_get(igrib, "parameterCategory")
                    num = codes_get(igrib, "parameterNumber")
                    if cat == 6 and num == 1:
                        short_name = "tcc"
                    elif cat == 1 and num == 8:
                        short_name = "tp"
                    elif cat == 1 and num == 231:
                        short_name = "2rh_max"
                    elif cat == 1 and num == 232:
                        short_name = "2rh_min"

                # --- Single-level (surface) variables ---
                if short_name in surface_vars:
                    nj, ni = codes_get(igrib, "Nj"), codes_get(igrib, "Ni")
                    vals = codes_get_values(igrib).reshape(nj, ni).astype("float32")

                    if short_name == "sp":
                        vals = np.around(vals / 100., 1)  # Pa → hPa
                    elif short_name in ["2t", "2d", "mn2t3", "mx2t3", "tmax", "tmin"]:
                        vals = np.around(vals - self.RCAbsZero, 1)  # K → °C
                    elif short_name in ["10u", "10v", "10fg3", "gust", "10gust"]:
                        vals = np.around(vals, 1)
                    elif short_name in ["tcc"]:
                        vals = np.around(vals, 2)
                    elif short_name in ["2rh_max", "2rh_min"]:
                        vals = np.around(vals, 0)

                    if sl_bound is not None:
                        vals = np.flipud(vals)[
                               sl_bound[0]:sl_bound[1] + 1,
                               sl_bound[2]:sl_bound[3] + 1
                               ]
                    else:
                        vals = np.flipud(vals)

                    # Normalize short name
                    if short_name == "2r":
                        data["2rh"] = vals
                    elif short_name in ["10fg3", "gust", "10gust"]:
                        data["10gust"] = vals
                    elif short_name == "sp":
                        data["sp"] = vals
                    else:
                        data[short_name] = vals

                # --- Multi-level (pressure) variables ---
                elif short_name in pressure_vars:
                    level = codes_get(igrib, "level")
                    if level <= 200:
                        codes_release(igrib)
                        continue
                    if isobaric_levels is not None and level not in isobaric_levels:
                        codes_release(igrib)
                        continue

                    nj, ni = codes_get(igrib, "Nj"), codes_get(igrib, "Ni")
                    vals = codes_get_values(igrib).reshape(nj, ni).astype("float32")

                    if ml_bound is not None:
                        vals = np.flipud(vals)[
                               ml_bound[0]:ml_bound[1] + 1,
                               ml_bound[2]:ml_bound[3] + 1
                               ]
                    else:
                        vals = np.flipud(vals)

                    if short_name == "t":
                        vals = np.around(vals - self.RCAbsZero, 1)
                    elif short_name == "q":
                        vals = np.around(vals, 4)
                    elif short_name == "r":
                        vals[vals > 100] = 100
                        vals[vals < 0] = 0
                        vals = np.around(vals, 0)
                    else:
                        vals = np.around(vals, 1)

                    if short_name in data:
                        data[short_name][level] = vals
                    else:
                        data[short_name] = {level: vals}

                codes_release(igrib)
            return data

    # ------------------------------------------------------------------
    # Geographic utilities
    # ------------------------------------------------------------------

    def dGlonlat_init(self, grid_info):
        """Initialize lon/lat dict from a grid info list.

        Parameters
        ----------
        grid_info : list
            [begin_lon, end_lon, lon_res, begin_lat, end_lat, lat_res]

        Returns
        -------
        dict
        """
        return {
            "begin_lon": grid_info[0],
            "end_lon": grid_info[1],
            "lon_res": grid_info[2],
            "begin_lat": grid_info[3],
            "end_lat": grid_info[4],
            "lat_res": grid_info[5],
        }

    def build_grid(self, lonlat, info_level=2, around=2, label="1km"):
        """Build grid coordinate arrays from lon/lat range info.

        Parameters
        ----------
        lonlat : dict
            With keys: begin_lon, end_lon, lon_res, begin_lat, end_lat, lat_res.
        info_level : int
            0=None, 1=1D arrays, 2=2D meshgrid + flat coordinates.
        around : int
            Decimal places to round coordinates.
        label : str
            Label for debug output.

        Returns
        -------
        dict
            Enriched with Nlon, Nlat, tpshape_lonlat, and optionally
            ndy1d_x_lon, ndy1d_y_lat, ndy2d_x_lon, ndy2d_y_lat, ndy2d_xy.
        """
        return self.dlonlat_info(lonlat, info_level, around, self.iDebug, label)

    def dlonlat_info(self, lonlat, info_level=2, around=2, idebug=0, slabel="1km"):
        n_lon, n_lat = self.dNum_lonlat(lonlat)
        lonlat["Nlon"] = n_lon
        lonlat["Nlat"] = n_lat
        if idebug:
            print(f"{slabel}:{n_lat}×{n_lon}={n_lon * n_lat}")
        lonlat["tpshape_lonlat"] = (lonlat["Nlat"], lonlat["Nlon"])

        if info_level >= 1:
            lon1d = np.arange(lonlat["begin_lon"], lonlat["end_lon"] + 0.001,
                              lonlat["lon_res"])
            lat1d = np.arange(lonlat["begin_lat"], lonlat["end_lat"] + 0.001,
                              lonlat["lat_res"])
            lon1d = np.around(lon1d, around)
            lat1d = np.around(lat1d, around)
            lonlat["ndy1d_x_lon"] = lon1d
            lonlat["ndy1d_y_lat"] = lat1d

            if info_level >= 2:
                lon2d, lat2d = np.meshgrid(lon1d, lat1d)
                lon2d = np.around(lon2d, around)
                lat2d = np.around(lat2d, around)
                lonlat["ndy2d_x_lon"] = lon2d
                lonlat["ndy2d_y_lat"] = lat2d

                flat_lon = lon2d.flatten()
                flat_lat = lat2d.flatten()
                lonlat["ndy2d_xy"] = np.column_stack((flat_lat, flat_lon))

        return lonlat

    def dNum_lonlat(self, lonlat):
        n_lon = round((lonlat["end_lon"] - lonlat["begin_lon"]) / lonlat["lon_res"]) + 1
        n_lat = round((lonlat["end_lat"] - lonlat["begin_lat"]) / lonlat["lat_res"]) + 1
        return n_lon, n_lat

    # ------------------------------------------------------------------
    # Variable derivation
    # ------------------------------------------------------------------

    def expand_wind(self, model_data):
        """Compute wind speed from U/V components.

        Adds '10ws' (surface) and 'ws' (multi-level) to model_data.
        """
        return self.dwind_expand(model_data)

    def dwind_expand(self, data):
        data["10ws"] = np.sqrt(data["10u"] ** 2 + data["10v"] ** 2)
        data["ws"] = {
            ilev: np.sqrt(data["u"][ilev] ** 2 + data["v"][ilev] ** 2)
            for ilev in data["u"]
        }
        return data

    def expand_rh(self, model_data):
        """Compute 2m relative humidity from 2m temperature and dewpoint.

        Adds '2rh' to model_data.
        """
        return self.drh_expand(model_data)

    def drh_expand(self, data):
        rh = self.relative_humidity(data["2t"] + self.RCAbsZero,
                                    data["2d"] + self.RCAbsZero)
        data["2rh"] = np.around(rh, 1)
        return data

    def relative_humidity(self, temp_k, dewpoint_k):
        """Compute relative humidity from temperature and dewpoint (both in K)."""
        t_svp = self.saturation_vapor_pressure(temp_k)
        d_svp = self.saturation_vapor_pressure(dewpoint_k)
        return d_svp / t_svp * 100

    # Backward compatibility alias
    drelative_humidity = relative_humidity

    def saturation_vapor_pressure(self, temp_k):
        """Compute saturation vapor pressure (hPa) from temperature (K).

        Uses separate formulae for ice phase (< 273.15 K) and water phase.

        Note: operates in float32 to match original code's numerical precision.
        """
        ice_mask = temp_k < self.RCAbsZero
        result = temp_k.copy()
        if np.any(ice_mask):
            t = temp_k[ice_mask]
            result[ice_mask] = 10 ** (
                3.56654 * np.log10(t)
                - 0.0032098 * t
                - 2484.956 / t
                + 2.0702294
            )
        water_mask = ~ice_mask
        if np.any(water_mask):
            t = temp_k[water_mask]
            result[water_mask] = 10 ** (
                23.832241
                - 2949.076 / t
                - 5.02808 * np.log10(t)
                - 1.3816E-7 * 10 ** (11.334 - 0.0303998 * t)
                + 8.1328E-3 * 10 ** (3.49149 - 1302.8844 / t)
            )
        return result

    # Backward compatibility alias
    dsaturation_vapor_pressure = saturation_vapor_pressure

    # ------------------------------------------------------------------
    # Vertical lapse rate computation
    # ------------------------------------------------------------------

    def dsurface_scalar_vertical_rate(self, data, var="t", iround=4,
                                      common_mask=None):
        """Compute surface-level scalar vertical lapse rate.

        Uses model-level data to find the lapse rate (Δvalue/Δheight) at
        the grid point closest to the surface based on surface pressure.

        Parameters
        ----------
        data : dict
            Model data with 'gh', 'sp', and var as keys.
        var : str
            Multi-level variable name to compute lapse rate for.
            Use "p" for pressure itself (creates synthetic pressure data).
        iround : int
            Decimal places for rounding.
        common_mask : ndarray or None
            Boolean mask for coarse-grid ↔ fine-grid common points.

        Returns
        -------
        ndarray or None
            2D lapse rate array (value/m).
        """
        if ("gh" not in data) or ("sp" not in data) or (var not in data):
            if var != "p":
                return None
            # Synthetic pressure data
            data[var] = {}
            for ilev in data['gh']:
                data[var][ilev] = np.zeros_like(data["gh"][ilev], dtype="float32") + ilev

        # Merge multi-level data into 2D arrays (levels × points)
        gh_ml = self.dMulti_Level_merge(data['gh'], arnd=1)
        pq_ml = self.dMulti_Level_merge(data[var], arnd=1)

        # Vertical differences
        gh_diff = gh_ml[1:, :] - gh_ml[:-1, :]
        pq_diff = pq_ml[1:, :] - pq_ml[:-1, :]

        # Lapse rate for each level
        lr_3d = pq_diff / gh_diff
        lr_3d = np.round(np.insert(lr_3d, 0, lr_3d[0], axis=0), 4)

        # Find the level closest to surface for each grid point
        levels = np.sort(list(data['gh'].keys()))[::-1]
        ml_shape = data['gh'][levels[0]].shape

        if common_mask is not None:
            sp_1d = data['sp'][common_mask]
        else:
            sp_1d = data['sp'].flatten()

        level_grid = (levels.reshape(-1, 1)).repeat(sp_1d.size, axis=1)
        sp_diff = level_grid - sp_1d
        row_idx = np.where(sp_diff > 0, 1, 0).sum(axis=0)
        col_idx = np.arange(row_idx.size, dtype="int32")

        lr_surface = lr_3d[row_idx, col_idx].reshape(ml_shape)
        return np.round(lr_surface, iround)

    def dsurface_vector_vertical_rate(self, data, var_names=("u", "v", "ws"),
                                      common_mask=None):
        """Compute surface-level vector (U/V/WS) vertical lapse rates.

        Parameters
        ----------
        data : dict
            Model data with 'gh', 'sp', 'u', 'v', 'ws' as keys.
        var_names : tuple
            (U_name, V_name, WS_name).
        common_mask : ndarray or None
            Boolean mask for coarse-grid ↔ fine-grid common points.

        Returns
        -------
        tuple of (U_rate, V_rate, WS_rate) or (None, None, None)
        """
        u_name, v_name, ws_name = var_names
        keys = data.keys()
        if ("gh" not in keys) or ("sp" not in keys) \
           or (u_name not in keys) or (v_name not in keys):
            return None, None, None

        gh_ml = self.dMulti_Level_merge(data['gh'], arnd=1)
        u_ml = self.dMulti_Level_merge(data[u_name], arnd=1)
        v_ml = self.dMulti_Level_merge(data[v_name], arnd=1)
        ws_ml = self.dMulti_Level_merge(data[ws_name], arnd=1) if ws_name in keys else None

        gh_diff = gh_ml[1:, :] - gh_ml[:-1, :]
        u_diff = u_ml[1:, :] - u_ml[:-1, :]
        v_diff = v_ml[1:, :] - v_ml[:-1, :]

        u_lr = u_diff / gh_diff
        v_lr = v_diff / gh_diff

        u_lr = np.round(np.insert(u_lr, 0, u_lr[0], axis=0), 4)
        v_lr = np.round(np.insert(v_lr, 0, v_lr[0], axis=0), 4)

        if ws_ml is not None:
            ws_diff = ws_ml[1:, :] - ws_ml[:-1, :]
            ws_lr = ws_diff / gh_diff
            ws_lr = np.round(np.insert(ws_lr, 0, ws_lr[0], axis=0), 4)
        else:
            ws_lr = None

        levels = np.sort(list(data['gh'].keys()))[::-1]
        ml_shape = data['gh'][levels[0]].shape

        if common_mask is not None:
            sp_1d = data['sp'][common_mask]
        else:
            sp_1d = data['sp'].flatten()

        level_grid = (levels.reshape(-1, 1)).repeat(sp_1d.size, axis=1)
        sp_diff = level_grid - sp_1d
        row_idx = np.where(sp_diff > 0, 1, 0).sum(axis=0)
        col_idx = np.arange(row_idx.size, dtype="int32")

        u_surface = u_lr[row_idx, col_idx].reshape(ml_shape)
        v_surface = v_lr[row_idx, col_idx].reshape(ml_shape)
        if ws_lr is not None:
            ws_surface = ws_lr[row_idx, col_idx].reshape(ml_shape)
        else:
            ws_surface = None
        return u_surface, v_surface, ws_surface

    # ------------------------------------------------------------------
    # Grid interpolation helpers
    # ------------------------------------------------------------------

    def dMulti_Level_merge(self, ml_data, arnd=None):
        """Merge multi-level data dict into a 2D array (levels × points).

        Levels are sorted from lowest (highest pressure) to highest.
        """
        levels = sorted(ml_data.keys(), reverse=True)
        template = ml_data[levels[0]]
        result = np.zeros((len(levels), template.size), dtype="float32")
        for i, lev in enumerate(levels):
            result[i, :] = ml_data[lev].flatten()
        if arnd is not None:
            result = np.around(result, arnd)
        return result

    def interp_mesh_scalar(self, fine_grid, coarse_grid, field):
        """Interpolate a scalar field from coarse grid to fine grid.

        Uses scipy RegularGridInterpolator.
        """
        return self.dMesh_scalar_interp(fine_grid, coarse_grid, field)

    def dMesh_scalar_interp(self, fine_grid, coarse_grid, field, method='linear'):
        fine_lon = fine_grid["ndy2d_x_lon"].flatten()
        fine_lat = fine_grid["ndy2d_y_lat"].flatten()
        points = np.vstack((fine_lat, fine_lon)).T

        interp = interpolate.RegularGridInterpolator(
            (coarse_grid["ndy1d_y_lat"], coarse_grid["ndy1d_x_lon"]),
            field, method=method
        )
        return interp(points).reshape(fine_grid["tpshape_lonlat"])

    def interp_mesh_vector(self, fine_grid, coarse_grid, u_field, v_field, ws_field):
        """Interpolate vector fields (U, V, WS) from coarse grid to fine grid."""
        return self.dMesh_vector_interp(fine_grid, coarse_grid, u_field, v_field, ws_field)

    def dMesh_vector_interp(self, fine_grid, coarse_grid, u, v, ws, method='linear'):
        fine_lon = fine_grid["ndy2d_x_lon"].flatten()
        fine_lat = fine_grid["ndy2d_y_lat"].flatten()
        points = np.vstack((fine_lat, fine_lon)).T

        def _interp(field):
            if field is None:
                return None
            f = interpolate.RegularGridInterpolator(
                (coarse_grid["ndy1d_y_lat"], coarse_grid["ndy1d_x_lon"]),
                field, method=method
            )
            return f(points).reshape(fine_grid["tpshape_lonlat"])

        return _interp(u), _interp(v), _interp(ws)

    def find_4points(self, target, grid):
        """Find 4 surrounding grid points for each target station.

        Parameters
        ----------
        target : dict
            With keys: lon, lat, alt, site_code (1D arrays).
        grid : dict
            Grid metadata (begin_lon, lon_res, Nlon, etc.).

        Returns
        -------
        DataFrame
            Per-station info about the 4 surrounding grid points.
        """
        return self.dfind_interp_4point(target, grid)

    def dfind_interp_4point(self, target, grid):
        left_w_lon = np.floor(
            (target['lon'] - grid["begin_lon"]) / grid["lon_res"]
        ).astype(int)
        right_e_lon = left_w_lon + 1
        right_e_lon[right_e_lon >= grid["Nlon"]] = grid["Nlon"] - 1

        up_s_lat = np.floor(
            (target['lat'] - grid["begin_lat"]) / grid["lat_res"]
        ).astype(int)
        down_n_lat = up_s_lat + 1
        down_n_lat[down_n_lat >= grid["Nlat"]] = grid["Nlat"] - 1

        ld_wn = grid['alt'][down_n_lat, left_w_lon]
        rd_en = grid['alt'][down_n_lat, right_e_lon]
        lu_ws = grid['alt'][up_s_lat, left_w_lon]
        ru_es = grid['alt'][up_s_lat, right_e_lon]

        import pandas as pd
        return pd.DataFrame({
            "site_code": target['site_code'],
            "alt": target['alt'],
            "LD_WN": ld_wn, "RD_EN": rd_en,
            "LU_WS": lu_ws, "RU_ES": ru_es,
            "diff_LD_WN": target['alt'] - ld_wn,
            "diff_RD_EN": target['alt'] - rd_en,
            "diff_LU_WS": target['alt'] - lu_ws,
            "diff_RU_ES": target['alt'] - ru_es,
        })

    # ------------------------------------------------------------------
    # Core terrain-aware interpolation
    # ------------------------------------------------------------------

    def interpolate_terrain_scalar(self, target_points, grid_data,
                                   lapse_rate, eta=1.0, var_key="2t"):
        """Perform terrain-aware interpolation for a scalar variable.

        Corrects each of the 4 surrounding grid points using the elevation
        bias and vertical lapse rate, then bilinearly interpolates to the
        target location.

        Parameters
        ----------
        target_points : dict
            Station info with keys: lon, lat, alt.
        grid_data : dict
            Grid data with lon/lat info and the variable field under var_key.
        lapse_rate : ndarray
            2D vertical lapse rate field on the same grid as grid_data.
        eta : float or ndarray
            Scaling factor for the terrain correction.
        var_key : str
            Key into grid_data for the forecast field to interpolate.

        Returns
        -------
        ndarray
            Interpolated values at each target point.
        """
        return self.dDEM_3d_interp_scalar(
            target_points, grid_data, lapse_rate, eta, var_key
        )

    def dDEM_3d_interp_scalar(self, target, grid, lapse_rate, eta=1.0,
                              skey="2t", sout="less"):
        # Find 4 surrounding grid indices
        left_w = np.floor((target['lon'] - grid["begin_lon"]) / grid["lon_res"]).astype(int)
        right_e = left_w + 1
        right_e[right_e >= grid["Nlon"]] = grid["Nlon"] - 1

        up_s = np.floor((target['lat'] - grid["begin_lat"]) / grid["lat_res"]).astype(int)
        down_n = up_s + 1
        down_n[down_n >= grid["Nlat"]] = grid["Nlat"] - 1

        # Lon/lat of the 4 corners
        glon_wn = grid["ndy2d_x_lon"][down_n, left_w]
        glat_wn = grid["ndy2d_y_lat"][down_n, left_w]
        glon_es = grid["ndy2d_x_lon"][up_s, right_e]
        glat_es = grid["ndy2d_y_lat"][up_s, right_e]

        # Bilinear weights
        x2_x = glon_es - target['lon']
        x_x1 = target['lon'] - glon_wn
        y_y1 = target['lat'] - glat_wn
        y2_y = glat_es - target['lat']
        area = -grid["lat_res"] * grid["lon_res"]

        w1 = y2_y * x2_x / area  # lower-left
        w2 = y2_y * x_x1 / area  # lower-right
        w3 = y_y1 * x2_x / area  # upper-left
        w4 = y_y1 * x_x1 / area  # upper-right

        # Terrain bias correction
        if np.size(eta) == 1:
            b11 = (target['alt'] - grid['alt'][down_n, left_w])  * lapse_rate[down_n, left_w]  * eta
            b21 = (target['alt'] - grid['alt'][down_n, right_e]) * lapse_rate[down_n, right_e] * eta
            b12 = (target['alt'] - grid['alt'][up_s, left_w])    * lapse_rate[up_s, left_w]    * eta
            b22 = (target['alt'] - grid['alt'][up_s, right_e])   * lapse_rate[up_s, right_e]   * eta
        elif np.size(eta) == np.size(lapse_rate):
            b11 = (target['alt'] - grid['alt'][down_n, left_w])  * lapse_rate[down_n, left_w]  * eta[down_n, left_w]
            b21 = (target['alt'] - grid['alt'][down_n, right_e]) * lapse_rate[down_n, right_e] * eta[down_n, right_e]
            b12 = (target['alt'] - grid['alt'][up_s, left_w])    * lapse_rate[up_s, left_w]    * eta[up_s, left_w]
            b22 = (target['alt'] - grid['alt'][up_s, right_e])   * lapse_rate[up_s, right_e]   * eta[up_s, right_e]
        else:
            if len(eta.shape) == 2:
                eta = eta.flatten()
            b11 = (target['alt'] - grid['alt'][down_n, left_w])  * lapse_rate[down_n, left_w]  * eta
            b21 = (target['alt'] - grid['alt'][down_n, right_e]) * lapse_rate[down_n, right_e] * eta
            b12 = (target['alt'] - grid['alt'][up_s, left_w])    * lapse_rate[up_s, left_w]    * eta
            b22 = (target['alt'] - grid['alt'][up_s, right_e])   * lapse_rate[up_s, right_e]   * eta

        # Corrected values
        q11 = grid[skey][down_n, left_w]  + b11
        q21 = grid[skey][down_n, right_e] + b21
        q12 = grid[skey][up_s, left_w]    + b12
        q22 = grid[skey][up_s, right_e]   + b22

        # Bilinear interpolation
        result = q11 * w1 + q21 * w2 + q12 * w3 + q22 * w4

        # Apply physically valid bounds
        if skey in ["10ws", "10fg3", "10gust"]:
            result[result <= 0.] = 0.
        elif skey in ["2rh"]:
            result[result <= 0.] = 0.
            result[result >= 100.] = 100.
        elif skey in ["sp"]:
            result[result <= 200] = 200

        return result

    # ------------------------------------------------------------------
    # Full EC/CMA workflows
    # ------------------------------------------------------------------

    def interpolate_ec(self, model_data, geography, target_info):
        """Full FRI terrain-aware interpolation for ECMWF model fields.

        Parameters
        ----------
        model_data : dict
            Raw GRIB data from ``read_grib()``.
        geography : dict
            Geographic metadata including grids and terrain.
        target_info : dict
            Target station info (lon, lat, alt arrays).

        Returns
        -------
        dict
            Interpolated results per variable per resolution.
        """
        return self.dECDMO_3d_Interp_nPQ(model_data, geography, target_info)

    def dECDMO_3d_Interp_nPQ(self, model_data, geography, target_info):
        # Expand derived variables
        if '10ws' in self.ltPQ_FRI_Inst:
            model_data = self.dwind_expand(model_data)
        if '2rh' in self.ltPQ_FRI_Inst:
            model_data = self.drh_expand(model_data)

        # Merge geography into model data
        model_data.update(geography["lonlat_SL_IG_mdl"])

        # Compute vertical lapse rates (on coarse 25km grid)
        vr = {}
        if '2t' in self.ltPQ_FRI_Inst:
            vr["2t"] = self.dsurface_scalar_vertical_rate(
                model_data, var="t",
                common_mask=geography["mask2d_common_12P5km_to_25km"]
            )
        if '2rh' in self.ltPQ_FRI_Inst:
            vr["2rh"] = self.dsurface_scalar_vertical_rate(
                model_data, var="r",
                common_mask=geography["mask2d_common_12P5km_to_25km"]
            )
        _need_wind = any(v in self.ltPQ_FRI_Inst for v in ['10u','10v','10ws'])
        if _need_wind:
            u_vr, v_vr, ws_vr = self.dsurface_vector_vertical_rate(
                model_data,
                common_mask=geography["mask2d_common_12P5km_to_25km"]
            )
            vr["10u"] = u_vr
            vr["10v"] = v_vr
            vr["10ws"] = ws_vr
        if 'sp' in self.ltPQ_FRI_Inst:
            vr["sp"] = self.dsurface_scalar_vertical_rate(
                model_data, var="p",
                common_mask=geography["mask2d_common_12P5km_to_25km"]
            )

        # Interpolate lapse rates from 25km → 12.5km
        if '2t' in self.ltPQ_FRI_Inst:
            vr["2t"] = self.dMesh_scalar_interp(
                geography["lonlat_SL_IG_mdl"], geography["lonlat_ML_IG_mdl"], vr["2t"])
        if '2rh' in self.ltPQ_FRI_Inst:
            vr["2rh"] = self.dMesh_scalar_interp(
                geography["lonlat_SL_IG_mdl"], geography["lonlat_ML_IG_mdl"], vr["2rh"])
        if _need_wind and vr.get("10u") is not None:
            u_m, v_m, ws_m = self.dMesh_vector_interp(
                geography["lonlat_SL_IG_mdl"], geography["lonlat_ML_IG_mdl"],
                vr["10u"], vr["10v"], vr.get("10ws", None))
            vr["10u"] = u_m
            vr["10v"] = v_m
            if ws_m is not None:
                vr["10ws"] = ws_m
        if 'sp' in self.ltPQ_FRI_Inst:
            vr["sp"] = self.dMesh_scalar_interp(
                geography["lonlat_SL_IG_mdl"], geography["lonlat_ML_IG_mdl"], vr["sp"])
        if '10ws_max' in self.ltPQ_FRI_mxmn:
            vr["10ws_max"] = vr["10ws"]

        # Terrain-aware interpolation to target points
        result = {}
        for res in target_info:
            inst = {
                var: self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr[var], skey=var
                )
                for var in self.ltPQ_FRI_Inst
            }
            # Extremes
            if '2t_max' in self.ltPQ_FRI_mxmn:
                inst['2t_max'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["2t"], skey="mx2t3")
            if '2t_min' in self.ltPQ_FRI_mxmn:
                inst['2t_min'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["2t"], skey="mn2t3")
            if '10ws_max' in self.ltPQ_FRI_mxmn:
                inst['10ws_max'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["10ws_max"], skey="10gust")
            # Reshape to 2D for grid targets
            if "2dshape" in target_info[res]:
                shape = target_info[res]["2dshape"]
                for k, v in inst.items():
                    if isinstance(v, np.ndarray) and v.ndim == 1:
                        inst[k] = v.reshape(shape)
            result[res] = inst
        return result

    def interpolate_cma(self, model_data, geography, target_info):
        """Full FRI terrain-aware interpolation for CMA-GFS model fields.

        Parameters
        ----------
        model_data : dict
            Raw GRIB data from ``read_grib()``.
        geography : dict
            Geographic metadata including grids and terrain.
        target_info : dict
            Target station info (lon, lat, alt arrays).

        Returns
        -------
        dict
            Interpolated results per variable per resolution.
        """
        return self.dCMADMO_3d_Interp_nPQ(model_data, geography, target_info)

    def dCMADMO_3d_Interp_nPQ(self, model_data, geography, target_info):
        # Expand derived variables
        if '10ws' in self.ltPQ_FRI_Inst:
            model_data = self.dwind_expand(model_data)

        # Merge geography into model data
        model_data.update(geography["lonlat_SL_IG_mdl"])

        # Compute vertical lapse rates (on the model's native grid)
        vr = {}
        if '2t' in self.ltPQ_FRI_Inst:
            vr["2t"] = self.dsurface_scalar_vertical_rate(
                model_data, var="t",
                common_mask=geography.get("mask2d_common_12P5km_to_25km"))
        if '2rh' in self.ltPQ_FRI_Inst:
            vr["2rh"] = self.dsurface_scalar_vertical_rate(
                model_data, var="r",
                common_mask=geography.get("mask2d_common_12P5km_to_25km"))
        _need_wind = any(v in self.ltPQ_FRI_Inst for v in ['10u','10v','10ws'])
        if _need_wind:
            u_vr, v_vr, ws_vr = self.dsurface_vector_vertical_rate(
                model_data,
                common_mask=geography.get("mask2d_common_12P5km_to_25km"))
            vr["10u"] = u_vr
            vr["10v"] = v_vr
            vr["10ws"] = ws_vr
        if 'sp' in self.ltPQ_FRI_Inst:
            vr["sp"] = self.dsurface_scalar_vertical_rate(
                model_data, var="p",
                common_mask=geography.get("mask2d_common_12P5km_to_25km"))
        if '10ws_max' in self.ltPQ_FRI_mxmn:
            vr["10ws_max"] = vr["10ws"]

        # Terrain-aware interpolation to target points
        result = {}
        for res in target_info:
            inst = {
                var: self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr[var], skey=var
                )
                for var in self.ltPQ_FRI_Inst
            }
            if '2t_max' in self.ltPQ_FRI_mxmn:
                inst['2t_max'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["2t"], skey="tmax")
            if '2t_min' in self.ltPQ_FRI_mxmn:
                inst['2t_min'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["2t"], skey="tmin")
            if '10ws_max' in self.ltPQ_FRI_mxmn:
                inst['10ws_max'] = self.dDEM_3d_interp_scalar(
                    target_info[res], model_data, vr["10ws_max"], skey="10gust")
            # Reshape to 2D for grid targets
            if "2dshape" in target_info[res]:
                shape = target_info[res]["2dshape"]
                for k, v in inst.items():
                    if isinstance(v, np.ndarray) and v.ndim == 1:
                        inst[k] = v.reshape(shape)
            result[res] = inst
        return result

    # ------------------------------------------------------------------
    # HDF5 I/O
    # ------------------------------------------------------------------

    def write_hdf5(self, output_path, data, keys=None, attrs=None):
        """Write interpolated results to an HDF5 file.

        Parameters
        ----------
        output_path : str
            Output file path.
        data : dict
            Data to write.
        keys : list or None
            Specific keys to write (default: all).
        attrs : dict or None
            Global attributes to attach.
        """
        return self.dWS3_Interp(output_path, data, keys, attrs)

    def dWS3_Interp(self, output_path, data, keys=None, attrs=None):
        temp_path = output_path + ".tmp"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        if keys is None:
            keys = list(data.keys())

        with h5py.File(temp_path, 'w') as fh:
            if attrs is not None:
                for k in attrs:
                    fh.attrs[k] = str(attrs[k]) if attrs[k] is None else attrs[k]
            for key in keys:
                if key in self.ltPQ_BIL_ML:
                    grp = fh.create_group(key)
                    for lev in data[key]:
                        grp.create_dataset(
                            str(lev),
                            data=np.round(data[key][lev], self.dyPQ_round.get(key, 1)),
                            compression="gzip", compression_opts=9,
                        )
                else:
                    val = data[key]
                    if key not in ["site"] and key not in self.ltPQ_FRI_mxmn_fh:
                        val = np.round(val, self.dyPQ_round.get(key, 1))
                    fh.create_dataset(key, data=val, compression="gzip", compression_opts=9)
        os.rename(temp_path, output_path)

    def dmulti_WS3_Interp(self, args):
        return self.dWS3_Interp(*args)

    # ------------------------------------------------------------------
    # NetCDF I/O
    # ------------------------------------------------------------------

    def write_netcdf(self, filename, result, station_codes,
                     station_names=None, station_lons=None,
                     station_lats=None, station_alts=None,
                     variables=None, attrs=None):
        """Write results to CF-compliant NetCDF.

        Parameters
        ----------
        filename : str
            Output .nc path.
        result : dict
            ``{"site": {var: ndarray}}`` from interpolation.
        station_codes : list of str
            Station identifiers.
        station_names : list of str, optional
            Station names.
        station_lons, station_lats, station_alts : array-like, optional
            Station coordinates.
        variables : list of str, optional
            Variables to write (default: all).
        attrs : dict, optional
            Global attributes.
        """
        from . import output
        output.write_netcdf(
            filename, result, station_codes, station_names,
            station_lons, station_lats, station_alts,
            variables, attrs,
        )

    def write_output(self, filename, result, station_codes,
                     station_names=None, station_lons=None,
                     station_lats=None, station_alts=None,
                     variables=None, attrs=None):
        """Write results, auto-detecting format from file extension.

        ``.nc`` / ``.nc4`` → NetCDF;  ``.h5`` / ``.hdf5`` → HDF5.
        """
        from . import output
        output.write_output(
            filename, result, station_codes, station_names,
            station_lons, station_lats, station_alts,
            variables, attrs,
        )

    def read_hdf5(self, filepath, keys=None, rounding=None):
        """Read interpolated results from an HDF5 file.

        Parameters
        ----------
        filepath : str
            Input file path.
        keys : list or None
            Specific keys to read (default: all).
        rounding : dict, int, or None
            Rounding control per key.

        Returns
        -------
        dict
        """
        return self.dRS3_Interp(filepath, keys, rounding)

    def dRS3_Interp(self, filepath, keys=None, rounding=None):
        data = {}
        with h5py.File(filepath, 'r') as fh:
            if keys is None:
                keys = list(fh.keys())
            if rounding is None:
                rounding = {k: 2 if k == "tcc" else 1 for k in keys}
            elif isinstance(rounding, (int, float)):
                rounding = {k: rounding for k in keys}
            for key in keys:
                arr = fh[key][...]
                if key != "site":
                    arr = np.round(arr, rounding.get(key, 1))
                data[key] = arr
        return data

    def dCopy_rlt(self, src, dst):
        temp_path = dst + ".tmp"
        if os.path.exists(temp_path):
            os.remove(temp_path)
        copyfile(src, temp_path)
        if os.path.exists(dst):
            os.remove(dst)
        os.rename(temp_path, dst)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def dBI_Grid_score(self, target_info, model_data, obs_grid, config, var):
        """Compute bilinear interpolation accuracy scores against gridded observations."""
        points = np.vstack((target_info['lat'], target_info['lon'])).T
        interp = interpolate.RegularGridInterpolator(
            (model_data["ndy1d_y_lat"], model_data["ndy1d_x_lon"]),
            model_data[var], method='linear'
        )
        bi_result = interp(points).reshape(target_info["2dshape"])
        diff = bi_result - obs_grid[var]
        ae = np.abs(diff)
        ae_china = ae[target_info["mask_area"]]
        mae = np.nanmean(ae_china)
        hit = (ae_china <= config["threshold"][var]).sum() / np.count_nonzero(~np.isnan(ae_china))
        scores = {"AE": ae, "MAE_China": np.round(mae, 3), "HIT_China": np.round(hit, 3)}
        if config["InstantInfo"]["Prov_code"] is not None:
            ae_prov = ae[target_info["mask_prov"]]
            mae_prov = np.nanmean(ae_prov)
            hit_prov = (ae_prov <= config["threshold"][var]).sum() / np.count_nonzero(~np.isnan(ae_prov))
            scores.update({"MAE_Prov": np.round(mae_prov, 3), "HIT_Prov": np.round(hit_prov, 3)})
        return scores


# ── Add snake_case aliases for methods that don't have them ──
FRIInterpolator.merge_levels = FRIInterpolator.dMulti_Level_merge
FRIInterpolator.grid_size = FRIInterpolator.dNum_lonlat
FRIInterpolator.grid_init = FRIInterpolator.dGlonlat_init
FRIInterpolator.bilin_score = FRIInterpolator.dBI_Grid_score
FRIInterpolator.copy_result = FRIInterpolator.dCopy_rlt

# Backward compatibility alias
Class_Interp_dem = FRIInterpolator
