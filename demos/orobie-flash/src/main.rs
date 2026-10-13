mod model;
mod terrain;

use macroquad::prelude::*;
use macroquad::models::{Mesh, Vertex};
use model::{Model, N};

const XY_SCALE: f32 = 0.245;
const Z_SCALE: f32 = 0.014;

fn window_conf() -> Conf {
    Conf {
        window_title: "OROBIE / FLASH — Alpine Hydrology".into(),
        window_width: 1460, window_height: 900,
        high_dpi: true, sample_count: 4, ..Default::default()
    }
}
fn pt(i: usize, elev: f32, base: f32) -> Vec3 {
    let x=(i%N) as f32 - (N-1) as f32*0.5;
    let y=(i/N) as f32 - (N-1) as f32*0.5;
    vec3(x*XY_SCALE, (elev-base)*Z_SCALE, y*XY_SCALE)
}
fn surface_mesh(sim: &Model, base: f32, water: bool) -> Mesh {
    let mut vertices=Vec::with_capacity(N*N);
    let mut indices=Vec::with_capacity(6*(N-1)*(N-1));
    let (zmin,zmax)=sim.z.iter().copied().fold((f32::MAX,f32::MIN),
        |(lo,hi),z| (lo.min(z),hi.max(z)));
    for y in 0..N { for x in 0..N {
        let i=y*N+x;
        let p=pt(i, sim.z[i]+if water {0.55} else {0.},base);
        let color=if water { Color::new(0.08,0.84,0.94,0.) }
        else {
            let left=sim.z[y*N+x.saturating_sub(1)];
            let right=sim.z[y*N+(x+1).min(N-1)];
            let top=sim.z[y.saturating_sub(1)*N+x];
            let bottom=sim.z[(y+1).min(N-1)*N+x];
            let sx=(right-left)/(2.*sim.cell_m);
            let sy=(bottom-top)/(2.*sim.cell_m);
            let shade=(0.76-0.52*sx+0.29*sy).clamp(0.30,1.17);
            let alt=((sim.z[i]-zmin)/(zmax-zmin).max(1.)).clamp(0.,1.);
            let (r,g,b)=if alt < 0.30 {
                (0.15+alt*0.34,0.29+alt*0.30,0.27+alt*0.22)
            } else if alt < 0.72 {
                (0.29+alt*0.33,0.35+alt*0.18,0.33+alt*0.17)
            } else {
                (0.35+alt*0.46,0.39+alt*0.43,0.43+alt*0.42)
            };
            Color::new((r*shade).min(1.),(g*shade).min(1.),(b*shade).min(1.),1.)
        };
        vertices.push(Vertex::new2(p,vec2(0.,0.),color));
    }}
    for y in 0..N-1 { for x in 0..N-1 {
        let i=(y*N+x) as u16;
        indices.extend_from_slice(&[i,i+1,i+N as u16,i+1,i+N as u16+1,i+N as u16]);
    }}
    Mesh { vertices, indices, texture: None }
}
fn update_water(mesh: &mut Mesh, sim: &Model, base: f32) {
    for (i,v) in mesh.vertices.iter_mut().enumerate() {
        let h=sim.h[i];
        // Elevation and opacity are deliberately visually amplified.
        let lift=(h*5.).min(2.);
        v.position.y=pt(i,sim.z[i]+0.55+lift,base).y;
        let a=if h<0.0008 {0.} else {(0.22+0.65*(h/0.55).sqrt()).min(0.88)};
        let hot=(h/0.3).min(1.);
        v.color=Color::new(0.05+hot*0.13,0.70+hot*0.17,0.90-hot*0.09,a).into();
    }
}
fn draw_contours(sim: &Model,base:f32) {
    for y in (0..N-1).step_by(3) { for x in (0..N-1).step_by(3) {
        let i=y*N+x;
        let a=sim.z[i];
        for j in [i+3.min(N-1-x),i+(3.min(N-1-y))*N] {
            let b=sim.z[j];
            let k1=(a/150.).floor() as i32;
            let k2=(b/150.).floor() as i32;
            if k1==k2 {continue;}
            let h=(if a<b{k2}else{k1}) as f32*150.;
            let t=((h-a)/(b-a)).clamp(0.,1.);
            let p=pt(i,a+2.,base);
            let q=pt(j,b+2.,base);
            let c=p.lerp(q,t);
            draw_line_3d(c-vec3(0.075,0.,0.075),c+vec3(0.075,0.,0.075),
                Color::new(0.55,0.78,0.76,0.45));
        }
    }}
}
fn draw_flow(sim:&Model,base:f32,time:f32) {
    for y in (2..N-2).step_by(4) { for x in (2..N-2).step_by(4) {
        let i=y*N+x;
        let h=sim.h[i];
        if h<0.002 {continue;}
        let center=sim.z[i]+h;
        let slope_x=(sim.z[i+1]+sim.h[i+1])-(sim.z[i-1]+sim.h[i-1]);
        let slope_y=(sim.z[i+N]+sim.h[i+N])-(sim.z[i-N]+sim.h[i-N]);
        let dir=vec2(-slope_x,-slope_y).normalize_or_zero();
        let n=dir.length();
        if n<0.001 {continue;}
        let head=pt(i,center+1.5,base);
        let phase=(time*0.21+(x*y) as f32*0.011).fract();
        let from=head + vec3(dir.x*(phase-0.6)*0.55,0.,dir.y*(phase-0.6)*0.55);
        let to=from+vec3(dir.x*0.50,0.,dir.y*0.50);
        draw_line_3d(from,to,Color::new(0.26,0.93,1.,0.72));
    }}
}
fn draw_rain(sim:&Model,base:f32,time:f32) {
    // Rain streaks sampled from the same scenario field that feeds the model.
    for j in 0..27 { for k in 0..27 {
        let x=(j*5+3)%N;
        let y=(k*5+4)%N;
        let mmh=sim.rainfall_at(x,y);
        if mmh<3. {continue;}
        let hash=((j*131+k*79) as f32*0.61803).fract();
        let phase=(time*(0.22+mmh/900.)+hash).fract();
        let floor=pt(y*N+x,sim.z[y*N+x],base);
        let height=2.+(1.-phase)*10.;
        let p=floor+vec3(0.,height,0.);
        draw_line_3d(p,p-vec3(0.055,0.78,0.04),
            Color::new(0.23,0.80,1.,(mmh/120.).clamp(0.13,0.70)));
    }}
}
fn label(s:&str,x:f32,y:f32,size:f32,opacity:f32) {
    draw_text(s,x,y,size,Color::new(0.81,0.94,0.95,opacity));
}
fn panel(x:f32,y:f32,w:f32,h:f32) {
    draw_rectangle(x,y,w,h,Color::new(0.020,0.055,0.077,0.88));
    draw_rectangle_lines(x,y,w,h,1.,Color::new(0.26,0.40,0.43,0.68));
}
fn dashboard(sim:&Model,source:&str,paused:bool,seconds:f32,show_rain:bool) {
    let sw=screen_width();
    let sh=screen_height();
    panel(23.,22.,440.,145.);
    label("OROBIE  /  FLASH",42.,68.,32.,1.);
    label("ALPINE RUNOFF LAB  |  RUST",44.,95.,19.,0.72);
    label(source,44.,125.,17.,if source.starts_with("SYNTHETIC"){0.98}else{0.62});
    label("CONCEPT SIMULATION  •  NOT A FLOOD FORECAST",44.,150.,15.,0.76);
    panel(sw-298.,22.,274.,252.);
    label("STORM / LIVE INPUT",sw-280.,55.,19.,0.88);
    label(&format!("SCENARIO    0{} / 03",sim.scenario+1),sw-280.,91.,19.,0.81);
    label(&format!("PEAK INPUT    {:.0} mm/h",sim.peak_mm_h),sw-280.,122.,19.,1.);
    label(&format!("LOCAL RAIN    {:.1} mm/h",sim.rainfall_at(N/2,N/2)),sw-280.,153.,17.,0.75);
    label(&format!("TIME          {:02}:{:02}",(sim.t as i32/3600),(sim.t as i32%3600/60)),sw-280.,184.,19.,1.);
    label(&format!("MAX DEPTH     {:.2} m",sim.peak_depth()),sw-280.,214.,17.,0.80);
    label(&format!("MODE          {}",if paused{"PAUSED"}else{"RUNNING"}),sw-280.,249.,17.,0.90);
    let bottom_y=sh-195.;
    panel(23.,bottom_y,sw-46.,169.);
    label("OUTLET DISCHARGE",43.,bottom_y+29.,18.,0.78);
    label(&format!("{:.2} m3/s",sim.outlet_q),43.,bottom_y+61.,27.,1.);
    label(&format!("RAIN {:.0} m3",sim.rain_m3),43.,bottom_y+94.,18.,0.72);
    label(&format!("INFILTRATED {:.0} m3",sim.infiltration_m3),43.,bottom_y+120.,18.,0.72);
    let err=sim.balance_m3();
    label(&format!("MASS RESIDUAL {:.3} m3",err),43.,bottom_y+147.,16.,if err.abs()>100.{1.}else{0.59});
    let gx=280.;
    let gy=bottom_y+32.;
    let gw=sw-gx-60.;
    let gh=100.;
    let qmax=sim.hydrograph.iter().copied().fold(1.,f32::max);
    for t in 0..5 {
        let yy=gy+t as f32*gh/4.;
        draw_line(gx,yy,gx+gw,yy,1.,Color::new(0.27,0.37,0.41,0.37));
    }
    let len=sim.hydrograph.len();
    for i in 1..len {
        let x0=gx+(i-1) as f32/899.*gw;
        let x1=gx+i as f32/899.*gw;
        let y0=gy+gh-(sim.hydrograph[i-1]/qmax)*gh;
        let y1=gy+gh-(sim.hydrograph[i]/qmax)*gh;
        draw_line(x0,y0,x1,y1,2.4,Color::new(0.22,0.90,0.98,0.97));
    }
    label("OUTLET Q  /  RUNOFF RESPONSE",gx,gy+gh+25.,17.,0.68);
    label(&format!("RAIN LAYER {}  |  SIM SPEED ~{:.0}x",if show_rain{"ON"}else{"OFF"},12./seconds.max(0.001)),gx+gw-290.,gy+gh+25.,16.,0.68);
    label("SPACE PAUSE   R RESET   1-3 STORM   +/- INTENSITY   ARROWS CAMERA   Q RAIN   C ORBIT   WHEEL ZOOM",
        31.,sh-8.,15.,0.62);
    // Storm timeline visible above hydrograph.
    let frac=(sim.t/7200.).clamp(0.,1.);
    draw_rectangle(gx,gy+gh+33.,gw,3.,Color::new(0.2,0.29,0.32,1.));
    draw_rectangle(gx,gy+gh+33.,gw*frac,3.,Color::new(0.35,0.91,1.,1.));
    draw_circle(gx+gw*frac,gy+gh+34.,4.,Color::new(0.74,0.99,1.,1.));
}

#[macroquad::main(window_conf)]
async fn main() {
    let terrain=terrain::load();
    let source=terrain.label;
    let mut sim=Model::new(terrain.z,terrain.cell_m);
    let min_z=sim.z.iter().copied().fold(f32::MAX,f32::min);
    let ground=surface_mesh(&sim,min_z,false);
    let mut water=surface_mesh(&sim,min_z,true);
    let mut orbit=0.78f32;
    let mut distance=66f32;
    let mut elevation=32f32;
    let mut auto_orbit=true;
    let mut show_rain=true;
    let mut paused=false;
    let mut wall=0f32;
    loop {
        let dt=get_frame_time().min(0.1);
        wall+=dt;
        if is_key_pressed(KeyCode::Space){paused=!paused;}
        if is_key_pressed(KeyCode::R){sim.reset();paused=false;}
        if is_key_pressed(KeyCode::Q){show_rain=!show_rain;}
        if is_key_pressed(KeyCode::C){auto_orbit=!auto_orbit;}
        if is_key_pressed(KeyCode::Key1){sim.scenario=0;sim.reset();}
        if is_key_pressed(KeyCode::Key2){sim.scenario=1;sim.reset();}
        if is_key_pressed(KeyCode::Key3){sim.scenario=2;sim.reset();}
        if is_key_pressed(KeyCode::Equal)||is_key_pressed(KeyCode::KpAdd){
            sim.peak_mm_h=(sim.peak_mm_h+10.).min(300.);
        }
        if is_key_pressed(KeyCode::Minus)||is_key_pressed(KeyCode::KpSubtract){
            sim.peak_mm_h=(sim.peak_mm_h-10.).max(0.);
        }
        if is_key_down(KeyCode::Left){orbit-=dt*1.2;auto_orbit=false;}
        if is_key_down(KeyCode::Right){orbit+=dt*1.2;auto_orbit=false;}
        if is_key_down(KeyCode::Up){elevation=(elevation+dt*22.).min(70.);}
        if is_key_down(KeyCode::Down){elevation=(elevation-dt*22.).max(9.);}
        distance=(distance-mouse_wheel().1*3.).clamp(31.,125.);
        if auto_orbit {orbit+=dt*0.047;}
        if !paused && sim.t<7200. {
            // 12 simulated seconds per rendered frame; deterministic fixed steps.
            for _ in 0..3 {sim.step(4.);}
        }
        update_water(&mut water,&sim,min_z);
        clear_background(Color::new(0.012,0.038,0.054,1.));
        let radius=distance*elevation.to_radians().cos();
        let target=vec3(0.,10.8,0.);
        set_camera(&Camera3D {
            position:target+vec3(radius*orbit.cos(),distance*elevation.to_radians().sin(),radius*orbit.sin()),
            target,up:vec3(0.,1.,0.),fovy:45.,..Default::default()
        });
        draw_mesh(&ground);
        draw_contours(&sim,min_z);
        draw_mesh(&water);
        draw_flow(&sim,min_z,wall);
        if show_rain {draw_rain(&sim,min_z,wall);}
        set_default_camera();
        dashboard(&sim,source,paused,dt,show_rain);
        next_frame().await;
    }
}
