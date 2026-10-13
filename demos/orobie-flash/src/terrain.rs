//! Independent 100 km overview and 8 km focus grids, both explicitly georeferenced.
//! Terrain is never mislabelled as real when the downloaded DEM pack is absent.
use std::{fs, path::Path};
use crate::model::N;

pub const MAP_N: usize = 512;

pub struct Grid {
    pub z: Vec<f32>,
    pub cell_m: f32,
    pub real: bool,
}
pub struct Landscape {
    pub id: &'static str,
    pub title: &'static str,
    pub overview: Grid,
    pub focus: Grid,
    pub hazard: [Option<Grid>;3],
}
impl Landscape {
    pub fn load(id: usize) -> Self {
        let (id,title,kind)=if id==0 { ("orobie","OROBIE / UPPER SERIO",0) }
            else { ("euganei","EUGANEI / PADOVA",1) };
        let overpath=format!("data/{id}/overview.asc");
        let focuspath=format!("data/{id}/focus.asc");
        let overview=load_elevation(&overpath,kind,100_000.);
        let focus=load_elevation(&focuspath,kind,8_000.);
        let hazard=std::array::from_fn(|j| {
            let rp=[10,100,500][j];
            let path=format!("data/{id}/rp{rp}.asc");
            // If the overview terrain is missing, a hazard overlay over invented
            // terrain is misleading, so disable it.
            if !overview.real { return None; }
            match read_asc(&path,true) {
                Ok(g) if (g.cell_m-overview.cell_m).abs()<0.02 =>Some(g),
                _=>None,
            }
        });
        Self{id,title,overview,focus,hazard}
    }
    pub fn simulator(&self)->crate::model::Model {
        // Hydrology uses focus downsampled to 128², not the entire 100km AOI.
        let mut z=Vec::with_capacity(N*N);
        for y in 0..N { for x in 0..N {
            z.push(self.focus.z[(4*y+2)*MAP_N+4*x+2]);
        }}
        crate::model::Model::new(z,self.focus.cell_m*2.)
    }
}
fn load_elevation(path:&str,kind:usize,extent_m:f32)->Grid{
    match read_asc(path,false) {
        Ok(g) if (g.cell_m - extent_m / MAP_N as f32).abs()<0.02 => g,
        Ok(_) => {eprintln!("{path}: wrong extent; procedural DEM substitute"); synthetic(kind,extent_m)},
        Err(e) => {eprintln!("{path}: {e}; procedural DEM substitute"); synthetic(kind,extent_m)}
    }
}
fn read_asc(path: impl AsRef<Path>,nodata_allowed:bool)->Result<Grid,String> {
    let s=fs::read_to_string(path).map_err(|e|e.to_string())?;
    let mut it=s.split_whitespace();
    let mut meta=Vec::new();
    for _ in 0..6 {
        let k=it.next().ok_or("invalid ASCII raster header")?.to_lowercase();
        let v=it.next().ok_or("invalid ASCII raster header")?.parse::<f32>()
            .map_err(|_|"invalid ASCII raster header value")?;
        meta.push((k,v));
    }
    let get=|k:&str|->Result<f32,String>{meta.iter().find(|(key,_)|key==k)
        .map(|(_,v)|*v).ok_or_else(||format!("missing {k}"))};
    if get("ncols")? as usize!=MAP_N || get("nrows")? as usize!=MAP_N {
        return Err(format!("not {MAP_N}x{MAP_N}"));
    }
    let cell_m=get("cellsize")?;
    if cell_m<0.5 || !cell_m.is_finite() {return Err("invalid metric pixel size".into());}
    let nodata=get("nodata_value").unwrap_or(-9999.);
    let mut z=Vec::with_capacity(MAP_N*MAP_N);
    for _ in 0..MAP_N*MAP_N {
        let v=it.next().ok_or("incomplete raster")?.parse::<f32>().map_err(|_|"not float")?;
        if !v.is_finite(){return Err("nonfinite terrain".into());}
        if (v-nodata).abs()<0.00001 && !nodata_allowed {return Err("NoData elevation is not permitted".into());}
        z.push(if (v-nodata).abs()<0.00001 {-9999.} else {v});
    }
    if !nodata_allowed && z.iter().copied().fold(f32::MIN,f32::max)
        -z.iter().copied().fold(f32::MAX,f32::min)<2. {
        return Err("flat or invalid terrain".into());
    }
    Ok(Grid{z,cell_m,real:true})
}
fn synthetic(kind:usize,extent_m:f32)->Grid {
    let mut z=vec![0.;MAP_N*MAP_N];
    for y in 0..MAP_N { for x in 0..MAP_N {
        let u=x as f32/(MAP_N-1) as f32;
        let v=y as f32/(MAP_N-1) as f32;
        let value=if kind==0 {
            let river=0.48+0.11*(v*6.0).sin()+0.027*(v*26.).sin();
            let d=(u-river).abs()*2.;
            let ridge=2100.*d.powf(1.2)+130.*(u*51.).sin()*(v*39.).cos()*d;
            let tributary=185.*(-((v-0.22-u*0.28)/0.047).powi(2)).exp();
            690.+550.*(1.-v)+ridge-tributary
        }else{
            let radial=((u-0.48)/0.16).powi(2)+((v-0.49)/0.23).powi(2);
            let cone=370.*(-radial).exp();
            let side=140.*(-(((u-0.34)/0.085).powi(2)+((v-0.43)/0.075).powi(2))).exp();
            let side2=195.*(-(((u-0.61)/0.060).powi(2)+((v-0.62)/0.090).powi(2))).exp();
            7.+cone+side+side2+24.*((u*23.).sin()*(v*19.).cos())*(-radial/1.9).exp()
        };
        z[y*MAP_N+x]=value;
    }}
    Grid{z,cell_m:extent_m/MAP_N as f32,real:false}
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn both_domains_have_100km_and_8km_extent() {
        for i in 0..2 {
            let scene=Landscape::load(i);
            assert!((scene.overview.cell_m*MAP_N as f32-100_000.).abs()<0.1);
            assert!((scene.focus.cell_m*MAP_N as f32-8_000.).abs()<0.1);
            assert_eq!(scene.simulator().z.len(),N*N);
        }
    }
    #[test] fn hazard_is_not_fabricated() {
        for i in 0..2 {
            let s=Landscape::load(i);
            if !s.overview.real {assert!(s.hazard.iter().all(Option::is_none));}
        }
    }
}
