"""
FRI — Fine-Resolution Interpolation for Numerical Weather Prediction
====================================================================

A terrain-aware interpolation algorithm that corrects coarse NWP model
output using vertical lapse rates and high-resolution DEM data.

Reference: 曾晓青等, 一种针对模式预报场的精细化插值新方法

Quick start
-----------
>>> from fri import fri_interpolate
>>> result = fri_interpolate("data.grib2", "terrain.tif", "stations.txt")
>>> result["site"]["2t"]  # interpolated 2m temperature at each station
>>> # No "model" parameter needed — grid info auto-detected from file headers

Main class
----------
FRIInterpolator : Core interpolation engine (full control)
"""

from .interpolator import FRIInterpolator, Class_Interp_dem
from .interpolate import fri_interpolate
from .output import write_hdf5, write_netcdf, write_output
from .validate import validate_inputs

# Attach convenience method to FRIInterpolator
from . import interpolate as _interpolate
FRIInterpolator.interpolate_from_files = _interpolate.interpolate_from_files

__all__ = [
    "FRIInterpolator", "Class_Interp_dem",
    "fri_interpolate",
    "write_hdf5", "write_netcdf", "write_output",
    "validate_inputs",
]
__version__ = "0.1.0"
