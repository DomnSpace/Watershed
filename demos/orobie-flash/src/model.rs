//! Deterministic, mass-accounted conceptual overland-flow demonstration.
//! 4-connected diffusive-wave-like Manning routing; NOT a calibrated flood forecast.
pub const N: usize = 128;
#[derive(Clone, Copy, Debug)]
struct Transfer { from: usize, to: Option<usize>, m3: f32 }

pub struct Model {
    pub z: Vec<f32>,
    pub h: Vec<f32>,
    pub soil: Vec<f32>,
    pub cell_m: f32,
    pub t: f32,
    pub peak_mm_h: f32,
    pub scenario: usize,
    pub rain_m3: f64,
    pub infiltration_m3: f64,
    pub outlet_m3: f64,
    pub outlet_q: f32,
    pub hydrograph: Vec<f32>,
}

impl Model {
    pub fn new(z: Vec<f32>, cell_m: f32) -> Self {
        assert_eq!(z.len(), N * N);
        assert!(cell_m.is_finite() && cell_m > 0.);
        Self {
            z, h: vec![0.; N*N], soil: vec![0.24; N*N], cell_m,
            t: 0., peak_mm_h: 105., scenario: 0,
            rain_m3: 0., infiltration_m3: 0., outlet_m3: 0.,
            outlet_q: 0., hydrograph: Vec::new(),
        }
    }
    pub fn reset(&mut self) {
        self.h.fill(0.);
        self.soil.fill(0.24);
        self.t = 0.;
        self.rain_m3 = 0.;
        self.infiltration_m3 = 0.;
        self.outlet_m3 = 0.;
        self.outlet_q = 0.;
        self.hydrograph.clear();
    }
    pub fn idx(x: usize, y: usize) -> usize { y*N + x }
    pub fn storage_m3(&self) -> f64 {
        let a = (self.cell_m * self.cell_m) as f64;
        self.h.iter().map(|h| (*h as f64) * a).sum()
    }
    pub fn balance_m3(&self) -> f64 {
        self.rain_m3 - self.infiltration_m3 - self.outlet_m3 - self.storage_m3()
    }
    pub fn rainfall_at(&self, x: usize, y: usize) -> f32 {
        let tx = self.t;
        let peak = (-((tx-2500.)/1150.).powi(2)).exp();
        let second = (-((tx-4700.)/700.).powi(2)).exp();
        let sx = x as f32 / (N-1) as f32;
        let sy = y as f32 / (N-1) as f32;
        let convective = (-((sx-0.63).powi(2)/0.11 + (sy-0.36).powi(2)/0.20)).exp();
        let (time, space) = match self.scenario {
            1 => (peak, 0.18 + 1.32*convective),
            2 => (peak*0.70 + second*0.70, 0.35 + 0.78*convective),
            _ => (peak, 0.75 + 0.4*convective),
        };
        self.peak_mm_h * time * space
    }
    fn offer(&self, a: usize, b: usize, dt: f32, transfers: &mut Vec<Transfer>, outgoing: &mut [f32]) {
        let ha = self.z[a] + self.h[a];
        let hb = self.z[b] + self.h[b];
        let dh = ha - hb;
        if dh.abs() < 1e-6 { return; }
        let (from, to) = if dh > 0. { (a,b) } else { (b,a) };
        if self.h[from] <= 0. { return; }
        let slope = (dh.abs()/self.cell_m).max(0.);
        // Demonstrator Manning coefficient; non-calibrated vegetation/soil assumption.
        let manning_n = 0.075;
        let q_per_width = self.h[from].powf(5./3.) * slope.sqrt() / manning_n;
        let proposed_m3 = (q_per_width * self.cell_m * dt).max(0.);
        if proposed_m3 > 0. {
            transfers.push(Transfer { from, to: Some(to), m3: proposed_m3 });
            outgoing[from] += proposed_m3;
        }
    }
    pub fn step(&mut self, dt: f32) {
        assert!(dt > 0. && dt <= 10. && dt.is_finite());
        let area = self.cell_m * self.cell_m;
        self.t += dt;
        // Rain input and simple saturation-dependent infiltration; do not interpret
        // soil parameterization as observed permeability.
        for y in 0..N { for x in 0..N {
            let i = Self::idx(x,y);
            let rain_m = self.rainfall_at(x,y) * dt / 3_600_000.;
            self.h[i] += rain_m;
            self.rain_m3 += (rain_m*area) as f64;
            let capacity_mm_h = 24. * (1. - 0.88*self.soil[i]);
            let infiltrated_m = self.h[i].min(capacity_mm_h * dt / 3_600_000.);
            self.h[i] -= infiltrated_m;
            self.infiltration_m3 += (infiltrated_m*area) as f64;
            self.soil[i] = (self.soil[i] + infiltrated_m / 0.085).min(1.);
        }}
        let mut outgoing = vec![0f32; N*N];
        let mut transfers: Vec<Transfer> = Vec::with_capacity(2*N*N+N);
        for y in 0..N { for x in 0..N {
            let a = Self::idx(x,y);
            if x+1 < N { self.offer(a,Self::idx(x+1,y),dt,&mut transfers,&mut outgoing); }
            if y+1 < N { self.offer(a,Self::idx(x,y+1),dt,&mut transfers,&mut outgoing); }
        }}
        // Open downstream edge (south edge); other edges are no-flow boundaries.
        for x in 0..N {
            let i = Self::idx(x,N-1);
            if self.h[i] <= 0. { continue; }
            let slope = 0.025 + self.h[i]/self.cell_m;
            let m3 = self.h[i].powf(5./3.) * slope.sqrt()/0.075 * self.cell_m * dt;
            if m3 > 0. {
                transfers.push(Transfer { from:i, to:None, m3 });
                outgoing[i] += m3;
            }
        }
        // Donor-limited, simultaneous updates. This prevents negative depth
        // even where several neighbouring cells demand the same water.
        let mut factor = vec![1f32; N*N];
        for i in 0..N*N {
            if outgoing[i] > self.h[i] * area && outgoing[i] > 0. {
                factor[i] = (self.h[i]*area/outgoing[i]).clamp(0.,1.);
            }
        }
        let mut delta = vec![0f32; N*N];
        let mut out = 0f64;
        for tr in transfers {
            let volume = tr.m3 * factor[tr.from];
            delta[tr.from] -= volume/area;
            if let Some(dst) = tr.to { delta[dst] += volume/area; }
            else { out += volume as f64; }
        }
        for i in 0..N*N { self.h[i] = (self.h[i]+delta[i]).max(0.); }
        self.outlet_m3 += out;
        self.outlet_q = (out / dt as f64) as f32;
        self.hydrograph.push(self.outlet_q);
        if self.hydrograph.len() > 900 { self.hydrograph.remove(0); }
    }
    pub fn peak_depth(&self) -> f32 {
        self.h.iter().copied().fold(0.,f32::max)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mass_balance_and_nonnegative_storm() {
        let z = (0..N*N).map(|i| 100. - (i/N) as f32).collect();
        let mut m=Model::new(z,30.);
        for _ in 0..420 { m.step(5.); }
        assert!(m.h.iter().all(|v| *v>=0. && v.is_finite()));
        assert!(m.rain_m3 > 0.);
        assert!(m.infiltration_m3 > 0.);
        assert!(m.balance_m3().abs() < (m.rain_m3 * 0.0005).max(0.15), "balance {}",m.balance_m3());
    }
    #[test]
    fn water_moves_downhill_without_rain() {
        let z=(0..N*N).map(|i| 300.-(i/N) as f32).collect();
        let mut m=Model::new(z,25.);
        m.peak_mm_h=0.;
        let i=Model::idx(N/2,N/2);
        m.h[i]=0.75;
        let initial_m3 = m.storage_m3();
        for _ in 0..15 { m.step(4.); }
        assert!(m.h[Model::idx(N/2,N/2+1)]>0.);
        assert!(m.h.iter().all(|v| *v>=0. && v.is_finite()));
        let accounted = m.storage_m3() + m.infiltration_m3 + m.outlet_m3;
        assert!((initial_m3-accounted).abs() < initial_m3*0.0005,
            "seeded-water balance: initial {initial_m3}, accounted {accounted}");
    }
    #[test]
    fn reproducible_replay() {
        let z=vec![100.;N*N];
        let mut a=Model::new(z,20.);
        for _ in 0..10 { a.step(3.); }
        let before=a.h.clone();
        a.reset();
        for _ in 0..10 { a.step(3.); }
        assert_eq!(before,a.h);
    }
}
