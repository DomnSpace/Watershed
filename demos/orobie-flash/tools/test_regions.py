"""Integration checks for projected raster mosaics and scenario provenance.

Runs on synthetic *test fixtures only*; does not claim observational validity.
"""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.enums import Resampling

from build_regions import SIZE, scene_bounds, warp_merge, write_asc, valid_dem

class PackTests(unittest.TestCase):
    def test_real_coordinate_window_and_ascii_header(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            bounds=scene_bounds(10.007,46.040,100000)
            # Synthetic fixture inside a legitimate projected EPSG:32632.
            west,south,east,north=bounds
            width=640
            pixel=125000/width
            xx=np.linspace(0,1,width,dtype=np.float32)
            arr=(1200 + 400*xx[None,:] + 100*np.linspace(0,1,width,dtype=np.float32)[:,None])
            input_file=base/"test_dem.tif"
            with rasterio.open(input_file,"w",driver="GTiff",width=width,height=width,
                 count=1,dtype="float32",crs="EPSG:32632",
                 transform=from_origin(west-12500,north+12500,pixel,pixel),
                 nodata=-9999.) as dst:
                dst.write(arr.astype("float32"),1)
            out,covered=warp_merge([input_file],bounds,Resampling.bilinear)
            self.assertTrue(covered.all())
            valid_dem(out,covered,"fixture")
            self.assertGreater(float(out.max()-out.min()),100.)
            asc=base/"orobie"/"overview.asc"
            write_asc(asc,out,bounds)
            lines=asc.read_text().splitlines()
            self.assertEqual(lines[0],f"ncols {SIZE}")
            self.assertEqual(lines[1],f"nrows {SIZE}")
            self.assertAlmostEqual(float(lines[4].split()[1]),100000/SIZE,places=4)
            self.assertEqual(len(lines),SIZE+6)
    def test_uncovered_dem_fails_instead_of_fabricating_elevations(self):
        with tempfile.TemporaryDirectory() as td:
            bounds=scene_bounds(11.687,45.315,100000)
            west,south,east,north=bounds
            path=Path(td)/"too_small.tif"
            with rasterio.open(path,"w",driver="GTiff",width=64,height=64,
                 count=1,dtype="float32",crs="EPSG:32632",
                 transform=from_origin(west,north,100.,100.),nodata=-9999.) as ds:
                ds.write(np.full((64,64),200.,dtype=np.float32),1)
            z,covered=warp_merge([path],bounds,Resampling.bilinear)
            self.assertFalse(covered.all())
            with self.assertRaisesRegex(ValueError,"uncovered"):
                valid_dem(z,covered,"fixture")
    def test_bounds_and_cellsize(self):
        for lon,lat in ((10.007,46.040),(11.687,45.315)):
            a=scene_bounds(lon,lat,100000)
            b=scene_bounds(lon,lat,8000)
            self.assertAlmostEqual(a[2]-a[0],100000,places=4)
            self.assertAlmostEqual(b[3]-b[1],8000,places=4)
            self.assertAlmostEqual((a[0]+a[2])/2,(b[0]+b[2])/2,places=5)

if __name__=="__main__":
    unittest.main()
