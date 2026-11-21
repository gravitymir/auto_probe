//! Динамик: MAX98357A на I2S1 (DIN IO13, BCLK IO14, LRCLK IO21, SD IO12).
//!
//! Звук - 16 бит, моно, 16 кГц: от сервера (речь, радио - бинарные кадры WebSocket),
//! готовые фразы из прошивки (assets/*.pcm) и тон. Всё идёт в общий буфер на 2 с,
//! задача динамика выбирает его кадрами по 16 мс. Буфер пуст дольше секунды -
//! усилитель выключается (тише, холоднее, меньше ток).
//!
//! Громкость 0..100 % от потолка AMP_MAX: на шине 5 В мало объёмной ёмкости
//! (README voice_cell), на полной шкале пики тока роняют питание. 70 % амплитуды -
//! вдвое меньший ток ценой 3 дБ.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use esp_idf_svc::hal::delay::BLOCK;
use esp_idf_svc::hal::gpio::{Output, OutputPin, PinDriver};
use esp_idf_svc::hal::i2s::config::{
    Config as I2sConfig, DataBitWidth, SlotMode, StdClkConfig, StdConfig, StdGpioConfig, StdSlotConfig,
};
use esp_idf_svc::hal::i2s::{I2sDriver, I2sTx};

const RATE: u32 = 16_000;
const CAP: usize = 2 * RATE as usize; // 2 с
const FRAME: usize = 256; // 16 мс
const AMP_MAX: f32 = 0.7;

pub const LISTENING: &[u8] = include_bytes!("../assets/listening.pcm");
pub const NO_WIFI: &[u8] = include_bytes!("../assets/no_wifi.pcm");
pub const SERVER_DOWN: &[u8] = include_bytes!("../assets/server_down.pcm");
pub const READY: &[u8] = include_bytes!("../assets/ready.pcm"); // «Connected and ready.» (голос сервера, prompts/ready)

static BUF: Mutex<VecDeque<i16>> = Mutex::new(VecDeque::new());
static VOLUME: AtomicU8 = AtomicU8::new(60);
/// Звук играет (буфер не пуст или только что опустел).
static BUSY: AtomicBool = AtomicBool::new(false);

pub fn volume() -> u8 {
    VOLUME.load(Ordering::Relaxed)
}

pub fn set_volume(v: u8) {
    VOLUME.store(v.min(100), Ordering::Relaxed);
}

/// Звук ещё играет: запись команды ждёт, пока «слушаю» доиграет.
pub fn busy() -> bool {
    BUSY.load(Ordering::Relaxed) || !BUF.lock().unwrap().is_empty()
}

/// 16-битные отсчёты (LE) в буфер; не влезает - лишнее теряется.
pub fn push_pcm(bytes: &[u8]) {
    let mut b = BUF.lock().unwrap();
    for s in bytes.chunks_exact(2) {
        if b.len() >= CAP {
            break;
        }
        b.push_back(i16::from_le_bytes([s[0], s[1]]));
    }
}

/// Сразу сыграть фразу: всё, что было в буфере, выкидывается.
pub fn say(pcm: &[u8]) {
    clear();
    push_pcm(pcm);
}

pub fn clear() {
    BUF.lock().unwrap().clear();
}

/// Тон freq Гц длительностью ms (не дольше 2 с).
pub fn tone(freq: f32, ms: u32) {
    let n = (RATE as usize * ms.min(2000) as usize / 1000).min(CAP);
    let mut b = BUF.lock().unwrap();
    b.clear();
    for i in 0..n {
        let t = i as f32 / RATE as f32;
        // мягкие края 5 мс - без щелчков
        let edge = (i.min(n - i) as f32 / (RATE as f32 * 0.005)).min(1.0);
        b.push_back(((2.0 * core::f32::consts::PI * freq * t).sin() * 12_000.0 * edge) as i16);
    }
}

/// Задача динамика: из буфера в I2S, усилитель включается только на время звука.
pub fn run<P: OutputPin>(mut tx: I2sDriver<'static, I2sTx>, mut sd: PinDriver<'static, P, Output>) {
    let mut frame = vec![0i16; FRAME];
    let mut out = vec![0u8; FRAME * 4]; // стерео: одинаковый отсчёт в оба канала
    let mut last_sound = Instant::now() - Duration::from_secs(10);
    let mut amp_on = false;
    loop {
        let n = {
            let mut b = BUF.lock().unwrap();
            let n = b.len().min(FRAME);
            for (k, s) in b.drain(..n).enumerate() {
                frame[k] = s;
            }
            n
        };
        for s in frame[n..].iter_mut() {
            *s = 0;
        }
        if n > 0 {
            last_sound = Instant::now();
            if !amp_on {
                let _ = sd.set_high();
                amp_on = true;
            }
        }
        let idle = last_sound.elapsed();
        BUSY.store(idle < Duration::from_millis(150), Ordering::Relaxed);
        if amp_on && idle > Duration::from_secs(1) {
            let _ = sd.set_low();
            amp_on = false;
        }
        let g = VOLUME.load(Ordering::Relaxed) as f32 / 100.0 * AMP_MAX;
        for (k, s) in frame.iter().enumerate() {
            let v = ((*s as f32) * g) as i16;
            let b = v.to_le_bytes();
            out[k * 4..k * 4 + 2].copy_from_slice(&b);
            out[k * 4 + 2..k * 4 + 4].copy_from_slice(&b);
        }
        // write с BLOCK держит темп: I2S забирает ровно 16 кГц
        let _ = tx.write_all(&out, BLOCK);
    }
}

/// I2S1 на выход: 16 кГц, 16 бит, стерео.
pub fn config() -> StdConfig {
    StdConfig::new(
        I2sConfig::default(),
        StdClkConfig::from_sample_rate_hz(RATE),
        StdSlotConfig::philips_slot_default(DataBitWidth::Bits16, SlotMode::Stereo),
        StdGpioConfig::default(),
    )
}
