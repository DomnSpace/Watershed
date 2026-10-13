//! Terrain loading and visibly-labelled synthetic fallback.
//! ESRI ASCII elevations must use a projected metric CRS (e.g. EPSG:32632).
use std::{fs, path::Path};
use crate::model::N;

pub struct Terrain {
    pub z: Vec<f32>,
    pub cell_m: f32,
    pub is_real: bool,
    pub label: &'static str,
}

pub fn load() -> Terrain {
    match read_asc("data/orobie.asc") {
        Ok(t) => t,
        Err(err) => {
            eprintln!("No valid data/orobie.asc ({err}); synthetic terrain demo only.");
            synthetic()
        }
    }
}
fn read_asc(path: impl AsRef<Path>) -> Result<Terrain,String> {
    let s=fs::read_to_string(path).map_err(|e|e.to_string())?;
    let mut parts=s.split_whitespace();
    let mut metadata=Vec::new();
    for _ in 0..6 {
        let key=parts.next().ok_or("short ASCII grid header")?.to_lowercase();
        let value=parts.next().ok_or("short ASCII grid header")?;
        metadata.push((key,value.to_string()));
    }
    let get=|key:&str| -> Result<f32,String> {
        metadata.iter().find(|(k,_)| k==key)
            .ok_or_else(||format!("missing grid field: {key}"))?.1
            .parse::<f32>().map_err(|_|format!("invalid grid field: {key}"))
    };
    let width=get("ncols")? as usize;
    let height=get("nrows")? as usize;
    if width!=N || height!=N { return Err(format!("expected {N}x{N}, got {width}x{height}")); }
    let cell_m=get("cellsize")?;
    if !(1. ..=1000.).contains(&cell_m) { return Err("cellsize must be in projected metres".into()); }
    let nodata=get("nodata_value").unwrap_or(-9999.);
    let mut z=Vec::with_capacity(N*N);
    for _ in 0..N*N {
        let v=parts.next().ok_or("incomplete elevation raster")?
            .parse::<f32>().map_err(|_|"invalid elevation raster")?;
        if !v.is_finite() || (v-nodata).abs()<0.01 {
            return Err("NoData in terrain; preprocess/fill source DEM first".into());
        }
        z.push(v);
    }
    if z.iter().all(|v| (*v-z[0]).abs()<0.01) {return Err("terrain has no relief".into());}
    Ok(Terrain {z,cell_m,is_real:true,label:"EXTERNAL ELEVATION GRID"})
}
fn synthetic() -> Terrain {
    let mut z=vec![0f32;N*N];
    for y in 0..N { for x in 0..N {
        let u=x as f32/(N-1) as f32;
        let v=y as f32/(N-1) as f32;
        let channel=0.50+0.075*(v*10.3).sin()+0.024*(v*24.).sin();
        let d=(u-channel).abs()*2.;
        let valley=(d.powf(1.68)*1050.).min(1450.);
        let southward=540.*(1.-v);
        let ridge=130.*(u*17.+v*8.).sin().powi(2)*d.powf(0.5);
        let folds=42.*(u*51.-v*16.).sin()*(v*28.+u*17.).cos()*d;
        let left_gully = 125.*(-((v-(0.22+u*0.43))/0.042).powi(2)).exp()*(1.-u);
        let right_gully= 140.*(-((v-(0.78-u*0.39))/0.055).powi(2)).exp()*u;
        z[y*N+x]=760.+southward+valley+ridge+folds-left_gully-right_gully;
    }}
    Terrain {z,cell_m:30.,is_real:false,label:"SYNTHETIC RELIEF / NOT ACTUAL OROBIE DTM"}
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn synthetic_has_valley_relief() {
        let t=synthetic();
        assert_eq!(t.z.len(),N*N);
        assert!(t.z[0]>t.z[N/2]);
    }
}
