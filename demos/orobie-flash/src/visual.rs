//! Software hillshade mesh and honest water-depth visualization.
//! The flood reference is a static inundation depth surface, never routed as a flow.
use macroquad::prelude::*;
use macroquad::models::{Mesh, Vertex};
use crate::terrain::{Grid,MAP_N};

const SPAN: f32 = 112.;
const PATCH: usize = 32;

pub struct Surface {
    pub land: Vec<Mesh>,
    pub wet: Vec<Mesh>,
    pub grid: Vec<f32>,
    pub minz: f32,
    pub vertical: f32,
}
impl Surface {
    pub fn new(terrain: &Grid, alpine:bool)->Self{
        let minz=terrain.z.iter().copied().fold(f32::INFINITY,f32::min);
        let maxz=terrain.z.iter().copied().fold(f32::NEG_INFINITY,f32::max);
        let vertical=if alpine {25.}else{19.}/(maxz-minz).max(1.);
        let mut land=Vec::new();
        for cy in (0..MAP_N-1).step_by(PATCH) {
            for cx in (0..MAP_N-1).step_by(PATCH) {
                let endx=(cx+PATCH).min(MAP_N-1);
                let endy=(cy+PATCH).min(MAP_N-1);
                let w=endx-cx+1;
                let mut vertices=Vec::with_capacity(w*(endy-cy+1));
                let mut indices=Vec::with_capacity(PATCH*PATCH*6);
                for y in cy..=endy {for x in cx..=endx {
                    let i=y*MAP_N+x;
                    let color=land_color(terrain,x,y,minz,maxz,alpine);
                    vertices.push(Vertex::new2(pos(x,y,terrain.z[i],minz,vertical),vec2(0.,0.),color));
                }}
                for y in 0..endy-cy {for x in 0..endx-cx {
                    let i=(y*w+x) as u16;
                    let row=w as u16;
                    // +X cross +Z is downward, therefore use +Z cross +X.
                    indices.extend_from_slice(&[i,i+row,i+1,i+1,i+row,i+row+1]);
                }}
                land.push(Mesh{vertices,indices,texture:None});
            }
        }
        Self{land,wet:Vec::new(),grid:terrain.z.clone(),minz,vertical}
    }
    pub fn water(&mut self,depth:&[f32],stride:usize,hazard:bool){
        if stride==0 || depth.len()!=stride*stride {return;}
        self.wet.clear();
        let mut quads:Vec<(usize,usize,f32)>=Vec::new();
        // Quarter resolution water tessellation in each local chunk. Fully opaque
        // surfaces avoid the previous alpha/depth-sorting holes and white slivers.
        for cy in (0..MAP_N-1).step_by(PATCH) {
            for cx in (0..MAP_N-1).step_by(PATCH) {
                quads.clear();
                let y1=(cy+PATCH).min(MAP_N-1);
                let x1=(cx+PATCH).min(MAP_N-1);
                for y in cy..y1 {for x in cx..x1 {
                    let dx=(x*stride/MAP_N).min(stride-1);
                    let dy=(y*stride/MAP_N).min(stride-1);
                    let d=depth[dy*stride+dx];
                    if d.is_finite() && d>=0.025 && d<80. {
                        quads.push((x,y,d));
                    }
                }}
                if quads.is_empty(){continue;}
                let mut vertices=Vec::with_capacity(quads.len()*4);
                let mut indices=Vec::with_capacity(quads.len()*6);
                for &(x,y,d) in &quads {
                    let idx=vertices.len() as u16;
                    let tone=water_color(d,hazard);
                    for (px,py) in [(x,y),(x,y+1),(x+1,y),(x+1,y+1)]{
                        let z=self.grid[py*MAP_N+px]+d;
                        let mut p=pos(px,py,z,self.minz,self.vertical);
                        p.y+=0.060;
                        vertices.push(Vertex::new2(p,vec2(0.,0.),tone));
                    }
                    indices.extend_from_slice(&[idx,idx+1,idx+2,idx+2,idx+1,idx+3]);
                }
                self.wet.push(Mesh{vertices,indices,texture:None});
            }
        }
    }
    pub fn draw(&self){
        for m in &self.land {draw_mesh(m);}
        for m in &self.wet {draw_mesh(m);}
    }
    pub fn point(&self,x:usize,y:usize,h:f32)->Vec3 {
        pos(x,y,self.grid[y*MAP_N+x]+h,self.minz,self.vertical)
    }
}
pub fn pos(x:usize,y:usize,z:f32,minz:f32,vertical:f32)->Vec3{
    let fx=x as f32/(MAP_N-1) as f32-0.5;
    let fy=y as f32/(MAP_N-1) as f32-0.5;
    vec3(fx*SPAN,(z-minz)*vertical,fy*SPAN)
}
fn land_color(grid:&Grid,x:usize,y:usize,minz:f32,maxz:f32,alpine:bool)->Color{
    let z=grid.z[y*MAP_N+x];
    let lo=(x.saturating_sub(1),y.saturating_sub(1));
    let hi=((x+1).min(MAP_N-1),(y+1).min(MAP_N-1));
    let zx=(grid.z[y*MAP_N+hi.0]-grid.z[y*MAP_N+lo.0])/(2.*grid.cell_m);
    let zy=(grid.z[hi.1*MAP_N+x]-grid.z[lo.1*MAP_N+x])/(2.*grid.cell_m);
    let normal=vec3(-zx*3.,1.,-zy*3.).normalize();
    let sun=vec3(-0.48,0.87,0.58).normalize();
    let light=(0.31+0.81*normal.dot(sun).max(0.)).clamp(0.26,1.08);
    let alt=((z-minz)/(maxz-minz).max(1.)).clamp(0.,1.);
    let steep=(zx*zx+zy*zy).sqrt();
    let (r,g,b)=if alpine {
        if alt>0.80 {(0.73,0.79,0.78)}
        else if alt>0.52 || steep>0.75 {(0.51,0.52,0.49)}
        else if alt>0.30 {(0.32,0.43,0.35)}
        else {(0.22,0.44,0.34)}
    } else {
        if steep>0.50 {(0.46,0.46,0.40)}
        else if alt>0.40 {(0.31,0.51,0.32)}
        else if alt>0.11 {(0.36,0.57,0.31)}
        else {(0.37,0.52,0.36)}
    };
    let tone=0.82+0.18*(x as f32*0.13+y as f32*0.07).sin();
    Color::new((r*light*tone).min(1.),(g*light*tone).min(1.),(b*light*tone).min(1.),1.)
}
fn water_color(d:f32,hazard:bool)->Color{
    let t=(d/3.5).sqrt().clamp(0.,1.);
    if hazard {
        Color::new(0.14+0.06*t,0.76-0.36*t,0.92-0.06*t,1.)
    } else {
        Color::new(0.13+0.12*t,0.76-0.26*t,0.80-0.10*t,1.)
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test] fn valid_water_mesh_size_with_large_flood(){
        let grid=Grid{z:vec![5.;MAP_N*MAP_N],cell_m:390.625,real:false};
        let mut s=Surface::new(&grid,false);
        let depth=vec![3.;MAP_N*MAP_N];
        s.water(&depth,MAP_N,true);
        assert!(!s.wet.is_empty());
        assert!(s.wet.iter().all(|m|m.indices.iter().all(|i|(*i as usize)<m.vertices.len())));
    }
}
