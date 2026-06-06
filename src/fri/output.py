"""
Output writers for FRI interpolation results.

Supports three formats:
- In-memory dict (default, always returned)
- HDF5 (.h5 / .hdf5)
- NetCDF (.nc)

All output files include station metadata (code, name, lon, lat, alt)
alongside the interpolated variable values, making them ready for
plotting with tools like matplotlib, cartopy, GrADS, or NCL.
"""

import os
import numpy as np


# ── Helpers ─────────────────────────────────────────────────────

def _station_name_list(dtsite, codes):
    """Extract station names from raw station data, aligned to codes list."""
    return [dtsite[c][0] for c in codes]


def _station_province_list(dtsite, codes):
    """Extract province names from raw station data."""
    return [dtsite[c][4] for c in codes]


def _station_city_list(dtsite, codes):
    """Extract city names from raw station data."""
    return [dtsite[c][5] for c in codes]


def _encode_strings(strings):
    """Encode list of strings for HDF5 storage."""
    import h5py
    return np.array(strings, dtype=h5py.string_dtype())


# ── HDF5 Writer ─────────────────────────────────────────────────

def write_hdf5(filename, result, station_codes, station_names=None,
               station_lons=None, station_lats=None, station_alts=None,
               variables=None, attrs=None):
    """Write interpolation results to HDF5.

    The file contains one dataset per variable (1D array over stations)
    plus station metadata: station_code, station_lon, station_lat,
    station_alt, and optionally station_name.

    Parameters
    ----------
    filename : str
        Output .h5 path.
    result : dict
        ``{"site": {var_name: ndarray, ...}}`` from interpolation.
    station_codes : list of str
        Station identifiers (e.g. "54511").
    station_names : list of str, optional
        Station names.
    station_lons, station_lats, station_alts : array-like
        Station coordinates. If None, extracted from result dict.
    variables : list of str, optional
        Which variables to write (default: all).
    attrs : dict, optional
        Global attributes to attach.
    """
    import h5py

    site_data = result.get("site", result)
    if variables is None:
        variables = [k for k in site_data if isinstance(site_data[k], np.ndarray)]

    temp_path = filename + ".tmp"
    if os.path.exists(temp_path):
        os.remove(temp_path)
    if os.path.exists(filename):
        os.remove(filename)

    with h5py.File(temp_path, "w") as f:
        # Global attributes
        if attrs:
            for k, v in attrs.items():
                f.attrs[k] = str(v) if v is None else v

        # Station metadata
        f.create_dataset("station_code", data=_encode_strings(station_codes),
                         compression="gzip", compression_opts=9)
        if station_names is not None:
            f.create_dataset("station_name", data=_encode_strings(station_names),
                             compression="gzip", compression_opts=9)
        if station_lons is not None:
            f.create_dataset("station_lon", data=np.array(station_lons, "f4"),
                             compression="gzip", compression_opts=9)
        if station_lats is not None:
            f.create_dataset("station_lat", data=np.array(station_lats, "f4"),
                             compression="gzip", compression_opts=9)
        if station_alts is not None:
            f.create_dataset("station_alt", data=np.array(station_alts, "f4"),
                             compression="gzip", compression_opts=9)

        # Variable data
        for var in variables:
            if var in site_data:
                val = site_data[var]
                if isinstance(val, np.ndarray):
                    f.create_dataset(var, data=val,
                                     compression="gzip", compression_opts=9)

    os.rename(temp_path, filename)


# ── NetCDF Writer ───────────────────────────────────────────────

def write_netcdf(filename, result, station_codes, station_names=None,
                 station_lons=None, station_lats=None, station_alts=None,
                 variables=None, attrs=None):
    """Write interpolation results to CF-compliant NetCDF.

    The file uses a ``station`` dimension with coordinate variables
    (station_lon, station_lat, station_alt) and interpolated variables
    (2t, 2rh, 10ws, etc.) indexed by station.

    Parameters
    ----------
    filename : str
        Output .nc path.
    result : dict
        ``{"site": {var_name: ndarray, ...}}`` from interpolation.
    station_codes : list of str
        Station identifiers.
    station_names : list of str, optional
        Station names.
    station_lons, station_lats, station_alts : array-like
        Station coordinates.
    variables : list of str, optional
        Which variables to write (default: all).
    attrs : dict, optional
        Global attributes (e.g. ``{"model": "CMA", "grib_file": "..."}``).
    """
    import netCDF4 as nc4

    site_data = result.get("site", result)
    if variables is None:
        variables = [k for k in site_data if isinstance(site_data[k], np.ndarray)]

    n_stations = len(station_codes)

    # Variable metadata for CF compliance
    VAR_META = {
        "2t":   {"long_name": "2m temperature",          "units": "degC"},
        "2rh":  {"long_name": "2m relative humidity",     "units": "%"},
        "10u":  {"long_name": "10m U wind component",     "units": "m/s"},
        "10v":  {"long_name": "10m V wind component",     "units": "m/s"},
        "10ws": {"long_name": "10m wind speed",           "units": "m/s"},
        "sp":   {"long_name": "surface pressure",         "units": "hPa"},
        "10gust":  {"long_name": "10m wind gust",         "units": "m/s"},
        "2t_max":  {"long_name": "maximum 2m temperature","units": "degC"},
        "2t_min":  {"long_name": "minimum 2m temperature","units": "degC"},
        "10ws_max":{"long_name": "maximum 10m wind speed","units": "m/s"},
        "tp":   {"long_name": "total precipitation",      "units": "mm"},
        "tcc":  {"long_name": "total cloud cover",        "units": "0-1"},
    }

    with nc4.Dataset(filename, "w", format="NETCDF4") as ds:
        # Dimensions
        ds.createDimension("station", n_stations)

        # Global attributes
        if attrs:
            for k, v in attrs.items():
                setattr(ds, k, str(v) if v is None else v)
        ds.source = "FRI_interpolator"
        ds.Conventions = "CF-1.8"

        # Station coordinate variables
        lon_var = ds.createVariable("station_lon", "f4", ("station",))
        lon_var.units = "degrees_east"
        lon_var.long_name = "station longitude"
        lon_var[:] = np.array(station_lons, "f4") if station_lons else np.zeros(n_stations)

        lat_var = ds.createVariable("station_lat", "f4", ("station",))
        lat_var.units = "degrees_north"
        lat_var.long_name = "station latitude"
        lat_var[:] = np.array(station_lats, "f4") if station_lats else np.zeros(n_stations)

        alt_var = ds.createVariable("station_alt", "f4", ("station",))
        alt_var.units = "m"
        alt_var.long_name = "station elevation"
        alt_var[:] = np.array(station_alts, "f4") if station_alts else np.zeros(n_stations)

        # Station code and name (variable-length strings, support Unicode)
        code_var = ds.createVariable("station_code", str, ("station",))
        code_var.long_name = "station identifier"
        for i, code in enumerate(station_codes):
            code_var[i] = code

        if station_names:
            name_var = ds.createVariable("station_name", str, ("station",))
            name_var.long_name = "station name"
            for i, name in enumerate(station_names):
                name_var[i] = name or ""

        # Interpolated variables
        for var in variables:
            if var not in site_data:
                continue
            vals = site_data[var]
            if not isinstance(vals, np.ndarray):
                continue

            v = ds.createVariable(var, vals.dtype, ("station",),
                                  zlib=True, complevel=4)
            meta = VAR_META.get(var, {})
            if "long_name" in meta:
                v.long_name = meta["long_name"]
            if "units" in meta:
                v.units = meta["units"]
            v[:] = vals


# ── Auto-detect format ─────────────────────────────────────────

def write_output(filename, result, station_codes, station_names=None,
                 station_lons=None, station_lats=None, station_alts=None,
                 variables=None, attrs=None):
    """Write interpolation results, auto-detecting format from extension.

    Parameters
    ----------
    filename : str
        Output path. Extension determines format:
        ``.nc`` / ``.nc4`` → NetCDF;  ``.h5`` / ``.hdf5`` → HDF5.
    result, station_codes, station_names, station_lons, station_lats,
    station_alts, variables, attrs
        See ``write_hdf5()`` and ``write_netcdf()``.

    Raises
    ------
    ValueError
        If extension is not recognized.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".nc", ".nc4"):
        write_netcdf(
            filename, result, station_codes, station_names,
            station_lons, station_lats, station_alts,
            variables, attrs,
        )
    elif ext in (".h5", ".hdf5"):
        write_hdf5(
            filename, result, station_codes, station_names,
            station_lons, station_lats, station_alts,
            variables, attrs,
        )
    else:
        raise ValueError(
            f"Unrecognized output format '{ext}'. "
            f"Use .nc / .nc4 for NetCDF or .h5 / .hdf5 for HDF5."
        )
