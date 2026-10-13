mod model;
mod terrain;
mod visual;

use macroquad::prelude::*;
use model::{Model,N};
use terrain::{Landscape,MAP_N};
use visual::Surface;

fn window_conf()->Conf {
    Conf {window_title:"WATERSHED / OROBIE + EUGANEI".into(),window_width:1536,
          window_height:930,high_dpi:true,sample_count:4,..Default::default()}
}
fn tag(s:&str,x:f32,y:f32,size:f32,color:Color){
    draw_text(s,x,y,size,color);
}
const WHITE:Color=Color{r:0.89,g:0.95,b:0.93,a:1.};
const DIM:Color=Color{r:0.56,g:0.72,b:0.71,a:1.};
const CYAN:Color=Color{r:0.26,g:0.94,b:0.94,a:1.};
fn panel(x:f32,y:f32,w:f32,h:f32){
    draw_rectangle(x,y,w,h,Color::new(0.018,0.050,0.067,0.91));
    draw_rectangle_lines(x,y,w,h,1.,Color::new(0.22,0.43,0.46,0.92));
}
fn ribbon(x:f32,y:f32,w:f32,h:f32,name:&str,active:bool){
    draw_rectangle(x,y,w,h,if active{Color::new(0.10,0.34,0.38,0.99)}
        else{Color::new(0.07,0.15,0.18,0.95)});
    tag(name,x+11.,y+23.,19.,if active{WHITE}else{DIM});
}
struct App{
    region:usize,
    scene:Landscape,
    surface:Surface,
    sim:Model,
    overview:bool,
    hazard:Option<usize>,
    paused:bool,
    rain:bool,
    flow:bool,
    orbit:f32,
    auto_orbit:bool,
    elevation:f32,
    distance:f32,
    frame:u64,
}
impl App{
    fn new(region:usize)->Self{
        let scene=Landscape::load(region);
        let sim=scene.simulator();
        let surface=Surface::new(&scene.focus,region==0);
        Self {region,scene,surface,sim,overview:false,hazard:None,
            paused:false,rain:true,flow:true,orbit:0.69,auto_orbit:true,
            elevation:36.,distance:155.,frame:0}
    }
    fn view(&mut self,overview:bool){
        self.overview=overview;
        self.surface=Surface::new(if overview{&self.scene.overview}else{&self.scene.focus},
                                  self.region==0);
        self.surface.wet.clear();
        self.hazard=None;
    }
    fn switch_region(&mut self){
        *self=Self::new(1-self.region);
        self.view(true);
    }
    fn apply_hazard(&mut self,index:usize){
        self.overview=true;
        self.surface=Surface::new(&self.scene.overview,self.region==0);
        self.hazard=Some(index);
        if let Some(g)=self.scene.hazard[index].as_ref(){
            self.surface.water(&g.z,MAP_N,true);
        }
    }
    fn update_water(&mut self){
        if self.overview {return;}
        self.surface.water(&self.sim.h,N,false);
    }
    fn command(&mut self,dt:f32){
        if is_key_pressed(KeyCode::M){self.switch_region();}
        if is_key_pressed(KeyCode::V){self.view(!self.overview);}
        if is_key_pressed(KeyCode::Key0){self.view(true);}
        if is_key_pressed(KeyCode::Key4){self.view(false);}
        if is_key_pressed(KeyCode::H) {
            let next=match self.hazard {None=>0,Some(i)=>(i+1)%3};
            self.apply_hazard(next);
        }
        if is_key_pressed(KeyCode::Space){self.paused=!self.paused;}
        if is_key_pressed(KeyCode::R){
            self.sim.reset();
            if !self.overview{self.surface.wet.clear();}
        }
        if is_key_pressed(KeyCode::Q){self.rain=!self.rain;}
        if is_key_pressed(KeyCode::F){self.flow=!self.flow;}
        if is_key_pressed(KeyCode::C){self.auto_orbit=!self.auto_orbit;}
        if is_key_pressed(KeyCode::Key1){self.sim.scenario=0;self.sim.reset();}
        if is_key_pressed(KeyCode::Key2){self.sim.scenario=1;self.sim.reset();}
        if is_key_pressed(KeyCode::Key3){self.sim.scenario=2;self.sim.reset();}
        if is_key_pressed(KeyCode::Equal)||is_key_pressed(KeyCode::KpAdd){
            self.sim.peak_mm_h=(self.sim.peak_mm_h+10.).min(300.);
        }
        if is_key_pressed(KeyCode::Minus)||is_key_pressed(KeyCode::KpSubtract){
            self.sim.peak_mm_h=(self.sim.peak_mm_h-10.).max(0.);
        }
        if is_key_down(KeyCode::Left){self.orbit-=dt*1.0;self.auto_orbit=false;}
        if is_key_down(KeyCode::Right){self.orbit+=dt*1.0;self.auto_orbit=false;}
        if is_key_down(KeyCode::Up){self.elevation=(self.elevation+dt*25.).min(83.);}
        if is_key_down(KeyCode::Down){self.elevation=(self.elevation-dt*25.).max(8.);}
        self.distance=(self.distance-mouse_wheel().1*9.).clamp(77.,280.);
        if self.auto_orbit{self.orbit+=dt*0.040;}
    }
    fn rainfall(&self,wall:f32){
        if self.overview || !self.rain{return;}
        for y in (3..MAP_N-3).step_by(12){for x in (3..MAP_N-3).step_by(12){
            let amount=self.sim.rainfall_at(x*N/MAP_N,y*N/MAP_N);
            if amount<2.{continue;}
            let phase=(wall*(0.7+amount/130.)+(x*y%317) as f32/317.).fract();
            let mut p=self.surface.point(x,y,0.);
            p.y+=2.+(1.-phase)*8.;
            draw_line_3d(p,p+vec3(-0.20,-1.1,0.06),
                Color::new(0.29,0.79,0.94,(amount/140.).clamp(0.12,0.60)));
        }}
    }
    fn water_motion(&self,wall:f32){
        if self.overview || !self.flow {return;}
        for y in (2..MAP_N-2).step_by(7){for x in (2..MAP_N-2).step_by(7){
            let i=(y*N/MAP_N)*N+x*N/MAP_N;
            let h=self.sim.h[i];
            if h<0.04 {continue;}
            let dzdx=self.surface.grid[y*MAP_N+x+2]-self.surface.grid[y*MAP_N+x-2];
            let dzdy=self.surface.grid[(y+2)*MAP_N+x]-self.surface.grid[(y-2)*MAP_N+x];
            let down=vec2(-dzdx,-dzdy).normalize_or_zero();
            if down.length_squared()<0.0001 {continue;}
            let phase=(wall*0.15+(x*y%271) as f32/271.).fract();
            let mut origin=self.surface.point(x,y,h);
            origin.y+=0.12;
            let displacement=vec3(down.x*1.5,0.,down.y*1.5);
            let a=origin+displacement*(phase-0.5);
            draw_line_3d(a,a+displacement*0.56,
                Color::new(0.66,0.93,0.85,0.93));
        }}
    }
    fn radar(&self){
        // Rainfall is sampled from the SAME forcing that enters the flow model.
        // Never call this observed radar data.
        let x=18.;let y=230.;
        panel(x,y,256.,253.);
        tag("STORM FIELD  /  SYNTHETIC",x+14.,y+31.,17.,WHITE);
        let n=25usize;
        let square=8.05;
        for yy in 0..n { for xx in 0..n {
            let model_x=xx*(N-1)/(n-1);
            let model_y=yy*(N-1)/(n-1);
            let intensity=self.sim.rainfall_at(model_x,model_y);
            let t=(intensity/self.sim.peak_mm_h.max(1.)).clamp(0.,1.);
            let color=if t<0.03 {Color::new(0.06,0.13,0.16,1.)}
                else if t<0.30 {Color::new(0.07,0.27+1.2*t,0.47+1.0*t,1.)}
                else if t<0.65 {Color::new(0.1+1.25*(t-0.30),0.73,0.84-0.85*(t-0.30),1.)}
                else {Color::new(0.62+0.88*(t-0.65),0.66-1.3*(t-0.65),0.35+0.88*(t-0.65),1.)};
            draw_rectangle(x+26.+xx as f32*square,y+42.+yy as f32*square,
                           square+0.12,square+0.12,color);
        }}
        tag("MODEL RAINFALL  [mm/h]",x+26.,y+247.,15.,DIM);
    }
    fn hud(&self,dt:f32){
        let sw=screen_width();let sh=screen_height();
        panel(18.,18.,475.,196.);
        tag("WATERSHED  /  FLOOD LAB",37.,55.,31.,WHITE);
        tag(self.scene.title,39.,88.,19.,CYAN);
        tag(if self.overview{"100 x 100 KM  -  REGIONAL LANDSCAPE"}
            else{"8 x 8 KM  -  CONCEPT RUNOFF MODEL"},39.,121.,19.,WHITE);
        tag(if (if self.overview{&self.scene.overview}else{&self.scene.focus}).real {
            "REAL DEM / REPROJECTED EPSG:32632"
        } else {"SYNTHETIC TERRAIN  -  IMPORT DEM PACK"},39.,155.,18.,
            if (if self.overview{&self.scene.overview}else{&self.scene.focus}).real{DIM}
            else{Color::new(1.,0.74,0.45,1.)});
        tag("DEMONSTRATION  /  NOT A FLOOD FORECAST",39.,186.,16.,DIM);
        panel(sw-345.,18.,327.,262.);
        tag("VIEW / DATA",sw-326.,53.,21.,WHITE);
        ribbon(sw-326.,70.,142.,34.,"OROBIE",self.region==0);
        ribbon(sw-175.,70.,142.,34.,"EUGANEI",self.region==1);
        tag(if self.overview{"VIEW: 100 KM TERRAIN"}else{"VIEW: 8 KM CATCHMENT"},
            sw-326.,132.,19.,CYAN);
        let hr=self.hazard.map(|i|[10,100,500][i]);
        tag(&match hr{Some(t)=>format!("EFAS HAZARD: RP{t}"),
            None=>"FLOOD REFERENCE: OFF".to_string()},sw-326.,166.,19.,WHITE);
        tag(if let Some(i)=self.hazard {
            if self.scene.hazard[i].is_some(){"DEPTH GRID: LOADED"}else{"DEPTH GRID: NOT INSTALLED"}
        }else{"PRESS H TO CYCLE RP10/100/500"},sw-326.,197.,18.,DIM);
        tag("M REGION  V VIEW  H RETURN PERIOD",sw-326.,235.,16.,DIM);
        tag("SCROLL ZOOM  ARROWS CAMERA",sw-326.,258.,16.,DIM);
        let py=sh-202.;
        panel(18.,py,sw-36.,181.);
        tag("LOCAL STORM  /  OUTFLOW RESPONSE",38.,py+29.,19.,WHITE);
        tag(&format!("{:.1} mm/h",self.sim.peak_mm_h),40.,py+66.,26.,CYAN);
        tag(&format!("{:.1} m3/s",self.sim.outlet_q),40.,py+98.,23.,WHITE);
        tag(&format!("TIME {:02}:{:02} / 02:00",self.sim.t as i32/3600,
            self.sim.t as i32%3600/60),40.,py+126.,17.,DIM);
        tag(&format!("MASS RESIDUAL {:.3} m3",self.sim.balance_m3()),40.,py+151.,16.,DIM);
        let gx=305.;let gw=sw-gx-55.;let gy=py+38.;let gh=90.;
        let data=&self.sim.hydrograph;
        let peak=data.iter().copied().fold(1.,f32::max);
        for k in 0..5 {
            let yy=gy+k as f32*gh/4.;
            draw_line(gx,yy,gx+gw,yy,1.,Color::new(0.32,0.46,0.47,0.5));
        }
        if data.len()>1{
            for i in 1..data.len(){
                let xa=gx+(i-1) as f32/(data.len()-1) as f32*gw;
                let xb=gx+i as f32/(data.len()-1) as f32*gw;
                let ya=gy+gh-gh*data[i-1]/peak;
                let yb=gy+gh-gh*data[i]/peak;
                draw_line(xa,ya,xb,yb,2.4,CYAN);
            }
        }
        tag(&format!("STORM {:02}  |  {}  |  ~{:.0}x sim",
            self.sim.scenario+1,if self.paused{"PAUSED"}else{"LIVE"},12./dt.max(0.001)),
            gx,py+157.,17.,DIM);
        tag("0 OVERVIEW  4 FOCUS  1-3 STORM  SPACE PAUSE  R RESET  +/- RAIN  Q STREAKS  F FLOW  C ORBIT",
            28.,sh-7.,16.,DIM);
    }
}
#[macroquad::main(window_conf)]
async fn main(){
    let mut app=App::new(0);
    let mut wall=0.;
    loop {
        let dt=get_frame_time().min(0.1);
        wall+=dt;
        app.command(dt);
        app.frame+=1;
        if !app.paused && app.sim.t<7200. {
            // 12 simulated seconds/frame, fixed 4s updates; only the 8km focus is simulated.
            for _ in 0..3 {app.sim.step(4.);}
            if !app.overview && app.frame%4==0 {app.update_water();}
        }
        clear_background(Color::new(0.012,0.036,0.052,1.));
        // Wide matte background and horizon, camera always shows terrain.
        draw_rectangle(0.,0.,screen_width(),screen_height()*0.60,
            Color::new(0.035,0.105,0.139,1.));
        let pitch=app.elevation.to_radians();
        let radius=app.distance*pitch.cos();
        let camtarget=vec3(0.,11.,0.);
        let eye=camtarget+vec3(radius*app.orbit.cos(),
                              app.distance*pitch.sin(),radius*app.orbit.sin());
        set_camera(&Camera3D{position:eye,target:camtarget,up:vec3(0.,1.,0.),
            fovy:46.,..Default::default()});
        app.surface.draw();
        app.water_motion(wall);
        app.rainfall(wall);
        set_default_camera();
        app.radar();
        app.hud(dt);
        next_frame().await;
    }
}
