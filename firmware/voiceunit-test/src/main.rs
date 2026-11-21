//! Voice-Unit: проверка собранной платы по USB, без динамика и без внешнего питания.
//!
//! Плата поднимает точку доступа "VoiceUnit-XXXX" (пароль autoprobe), страница -
//! http://192.168.71.1: сводка самопроверки, светодиод, уровни обоих микрофонов,
//! кнопка BOOT, UART-петля на J4, температура чипа и прослушивание микрофона
//! (поток WAV на порту 81 - отдельный сервер, чтобы не занимать httpd).
//! Та же сводка и уровни печатаются в USB-порт.
//!
//! Выводы (gen/build_voiceunit.py):
//!   MIC_WS IO9, MIC_SD IO10, MIC_SCK IO11 - оба ICS-43434 на одной шине I2S:
//!     MK1 (LR = GND) - левый канал, MK2 (LR = 3V3) - правый;
//!   AMP_SD IO12 (100k на землю = усилитель выключен), AMP_DIN IO13, AMP_BCLK IO14,
//!     AMP_LRCLK IO21 - MAX98357A, пока динамика нет - держим выключенным;
//!   LED_K IO48 - светодиод D3 анодом на 3V3: горит при низком уровне;
//!   BOOT IO0 - кнопка на землю;
//!   TX IO43, RX IO44 - UART на J4 (перемычка TX-RX = проверка петлёй).
//!
//! Сеть: станция в Wi-Fi площадки - первая видимая из списка src/site.rs (не в git),
//! у каждой сети свой адрес сервера, - плюс своя точка доступа
//! как запасной вход. Сервер площадки: постоянное WebSocket-соединение
//! ws://SERVER/ws?id=..., по строке JSON в кадре: плата шлёт телеметрию раз в 1 с
//! и сразу при событиях, сервер шлёт команды {"type":"cmd","led":...} мгновенно.
//! Нет связи: 3 попытки через 5 с, потом пауза 30 с (BOOT - попробовать сразу).
//! Динамик (src/speaker.rs): речь и радио от сервера, «слушаю» после «София»,
//! «Connected» при подключении к серверу,
//! USB-колонка с микрофоном (src/usbaudio.rs) - по команде сервера, выход перезагрузкой,
//! «нет сети» и «сервер недоступен» - из прошивки (assets/).
//!
//! Запись по голосу: оба микрофона громче своего фона на VAD_START дБ (2 замера
//! по 32 мс подряд) - старт, звук уходит на сервер бинарными кадрами WebSocket:
//! моно, 8 кГц, μ-law (8 КБ/с), с предзаписью 0.5 с. Оба тише фона + VAD_STOP дБ
//! дольше VAD_HANG мс - стоп. События - текстом {"type":"rec","state":...}.
//!
//! Ключевое слово «София» (ESP-SR WakeNet9, src/wakeword.rs, модель - раздел flash
//! "model"): услышана - {"type":"wake",...} и запись команды с "reason":"wake",
//! её сервер распознаёт и выполняет. Пока ключевое слово работает, запись просто
//! по громкости не включается; нет модели во flash - работает как раньше.

mod site;
mod speaker;
mod usbaudio;
mod wakeword;

use std::fmt::Write as _;
use std::io::{Read, Write as _};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU32, AtomicU8, Ordering};
use std::sync::mpsc::{sync_channel, SyncSender, TrySendError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use esp_idf_svc::eventloop::EspSystemEventLoop;
use esp_idf_svc::hal::delay::{FreeRtos, BLOCK};
use esp_idf_svc::hal::gpio::{AnyIOPin, PinDriver, Pull};
use esp_idf_svc::hal::i2s::config::{
    Config as I2sConfig, DataBitWidth, SlotMode, StdClkConfig, StdConfig, StdGpioConfig, StdSlotConfig,
};
use esp_idf_svc::hal::i2s::{I2sDriver, I2sRx};
use esp_idf_svc::hal::prelude::Peripherals;
use esp_idf_svc::hal::uart::{config::Config as UartConfig, UartDriver};
use esp_idf_svc::http::server::{Configuration as HttpConfig, EspHttpServer};
use esp_idf_svc::http::Method;
use esp_idf_svc::io::Write as _;
use esp_idf_svc::nvs::EspDefaultNvsPartition;
use esp_idf_svc::sys;
use esp_idf_svc::wifi::{
    AccessPointConfiguration, AuthMethod, BlockingWifi, ClientConfiguration, Configuration, EspWifi,
};

const RATE: u32 = 16_000;
const CHUNK: usize = 512; // кадров за одно чтение I2S (32 мс)
const FULL: f32 = 8_388_608.0; // 2^23: ICS-43434 отдаёт 24 бита в 32-битном слоте
const AP_PASS: &str = "autoprobe";

const LED_OFF: u8 = 0;
const LED_ON: u8 = 1;
const LED_BLINK: u8 = 2;
static LED_MODE: AtomicU8 = AtomicU8::new(LED_BLINK);
/// BOOT нажата - не ждать паузы, связаться с сервером сразу.
static SERVER_NOW: AtomicBool = AtomicBool::new(false);
/// Что-то поменялось (кнопка, светодиод) - отправить телеметрию, не дожидаясь секунды.
static SEND_NOW: AtomicBool = AtomicBool::new(false);
/// Сказать «Connected» при следующем подключении к серверу.
static SAY_READY: AtomicBool = AtomicBool::new(true);
const TELEMETRY_PERIOD: Duration = Duration::from_secs(1);
const RETRY_DELAY: Duration = Duration::from_secs(5);
const RETRY_COUNT: u32 = 3;
/// Попыток подключиться к каждой сети при старте (между ними 1 с), каждая не
/// дольше WIFI_TRY_MS.
const WIFI_TRIES: u32 = 4;
const WIFI_TRY_MS: u64 = 4000;
const SERVER_BACKOFF: Duration = Duration::from_secs(30);
/// Адрес сервера в той сети из site::WIFI, к которой подключились.
static SERVER_HOST: std::sync::OnceLock<String> = std::sync::OnceLock::new();
fn server_host() -> &'static str {
    SERVER_HOST.get().map(String::as_str).unwrap_or("")
}

// Запись по голосу; меняется командой {"type":"cfg",...} с сервера.
static VAD_ON: AtomicBool = AtomicBool::new(true);
static VAD_START: AtomicI32 = AtomicI32::new(15); // дБ над фоном - старт
static VAD_STOP: AtomicI32 = AtomicI32::new(8); // дБ над фоном - считается тишиной
static VAD_HANG: AtomicU32 = AtomicU32::new(2500); // мс тишины до остановки
static REC_GAIN: AtomicU32 = AtomicU32::new(8); // усиление 24 -> 16 бит перед μ-law
const CHUNK_MS: u32 = CHUNK as u32 * 1000 / RATE;
const PREROLL: usize = 16; // кусков по 32 мс = 0.5 с до старта
const REC_MAX_MS: u32 = 60_000;

// Ключевое слово «София».
/// Задача ключевого слова запущена (модель найдена) - запись только после него.
static WAKE_READY: AtomicBool = AtomicBool::new(false);
/// «София» услышана, мик-задача ещё не начала запись команды.
static WAKE_PENDING: AtomicBool = AtomicBool::new(false);
static WAKE_COUNT: AtomicU32 = AtomicU32::new(0);
/// Ключевое слово с подавлением эха: микрофон шлёт ему пары [микрофон, опорный].
static WAKE_AEC: AtomicBool = AtomicBool::new(false);
/// Звук от сервера не играть: от «София» до конца записи команды. Сервер шлёт
/// радио на 0.4 с вперёд и о «София» узнаёт не сразу - уже отправленный кусок
/// музыки иначе звучал бы сразу после «listening» (заикание радио).
static SERVER_AUDIO_MUTED: AtomicBool = AtomicBool::new(false);
/// Команда после ключевого слова: не дольше 8 с, тишина в первые 2 с не считается
/// (после «София» человек обычно делает паузу), конец - тишина дольше 1.5 с.
const WAKE_REC_MAX_MS: u32 = 8_000;
const WAKE_GRACE_MS: u32 = 2_000;
const WAKE_HANG_MS: u32 = 1_500;

#[derive(Default)]
struct State {
    summary: String,
    mic_l: String,
    mic_r: String,
    l_db: f32,
    r_db: f32,
    boot_down: bool,
    presses: u32,
    uart_loop: bool,
    listening: bool,
    sta_ip: String, // пусто - к Wi-Fi площадки не подключены
    rssi: i8,
    server: String,
    sent: u32,
    rec: bool,
    recs: u32,
    floor_l: f32,
    floor_r: f32,
}

/// Слушатель потока WAV: канал (0 - MK1, 1 - MK2, 2 - оба) и усиление.
struct Listener {
    tx: SyncSender<Vec<u8>>,
    ch: u8,
    gain: i32,
}

type Shared = Arc<Mutex<State>>;
type Audio = Arc<Mutex<Option<Listener>>>;

/// Что отправить серверу по WebSocket из других задач.
enum WsOut {
    Text(String),
    Bin(Vec<u8>),
}
/// Очередь в живой WebSocket-сеанс; None - связи нет, отправленное теряется.
type Link = Arc<Mutex<Option<SyncSender<WsOut>>>>;

fn main() {
    sys::link_patches();
    esp_idf_svc::log::EspLogger::initialize_default();
    // Старт не удался (не хватило памяти на задачу и т.п.) - не висеть полуживой
    // без Wi-Fi, а перезагрузиться.
    if let Err(e) = run() {
        log::error!("startup failed: {e:?} - restarting in 3 s");
        FreeRtos::delay_ms(3000);
        unsafe { sys::esp_restart() };
    }
}

fn run() -> anyhow::Result<()> {
    // после режима USB-колонки USB мог остаться у аудио-контроллера - вернуть COM-порту
    usbaudio::usb_back_to_serial_jtag();
    let p = Peripherals::take()?;

    // Динамик: усилитель выключен, пока нечего играть (включает задача динамика).
    let mut amp_sd = PinDriver::output(p.pins.gpio12)?;
    amp_sd.set_low()?;
    let mut spk = I2sDriver::new_std_tx(
        p.i2s1,
        &speaker::config(),
        p.pins.gpio14, // BCLK
        p.pins.gpio13, // DIN
        Option::<AnyIOPin>::None,
        p.pins.gpio21, // LRCLK
    )?;
    spk.tx_enable()?;
    std::thread::Builder::new()
        .stack_size(6 * 1024)
        .spawn(move || speaker::run(spk, amp_sd))?;
    let mut led = PinDriver::output(p.pins.gpio48)?;
    led.set_high()?;
    let mut boot = PinDriver::input(p.pins.gpio0)?;
    boot.set_pull(Pull::Up)?;

    FreeRtos::delay_ms(2000); // время открыть USB-порт после перезапуска

    let mut mac = [0u8; 6];
    unsafe { sys::esp_efuse_mac_get_default(mac.as_mut_ptr()) };
    let mut summary = String::new();
    chip_report(&mut summary, &mac);
    psram_report(&mut summary);

    // Wi-Fi: точка доступа + станция (станция только для поиска сетей - проверка антенны).
    let ssid = format!("VoiceUnit-{:02X}{:02X}", mac[4], mac[5]);
    let sysloop = EspSystemEventLoop::take()?;
    let nvs = EspDefaultNvsPartition::take()?;
    let mut wifi = BlockingWifi::wrap(EspWifi::new(p.modem, sysloop.clone(), Some(nvs))?, sysloop)?;
    let mixed = |sta_ssid: &str, sta_pass: &str| {
        Configuration::Mixed(
            ClientConfiguration {
                ssid: sta_ssid.try_into().unwrap(),
                password: sta_pass.try_into().unwrap(),
                ..Default::default()
            },
            AccessPointConfiguration {
                ssid: ssid.as_str().try_into().unwrap(),
                password: AP_PASS.try_into().unwrap(),
                auth_method: AuthMethod::WPA2Personal,
                channel: 6,
                max_connections: 4,
                ..Default::default()
            },
        )
    };
    let (first_ssid, first_pass, first_host) = site::WIFI.first().copied().unwrap_or(("", "", ""));
    wifi.set_configuration(&mixed(first_ssid, first_pass))?;
    wifi.start()?;
    // Без энергосбережения Wi-Fi: входящий кадр не ждёт, пока модем "проснётся"
    // (до 100-300 мс). Плата питается от USB/машины - экономить нечего.
    unsafe { sys::esp_wifi_set_ps(sys::wifi_ps_type_t_WIFI_PS_NONE) };
    // Подключение - сразу, сети по порядку из site.rs; скан эфира (~8 с) - потом,
    // он нужен только для сводки.
    //
    // Плата обычно перезагружается, не попрощавшись с роутером, и роутер с PMF
    // (защита кадров управления; в ESP-IDF 5 её со стороны платы не выключить)
    // первую попытку отклоняет ("Association refused temporarily") и 5-10 с
    // проверяет старое подключение. Поэтому несколько коротких попыток: начать
    // как можно раньше и не ждать отказа по 15 с, как блокирующий connect().
    let mut sta_txt = String::new();
    let mut sta_ip = String::new();
    let mut server_host = first_host;
    let mut configured = first_ssid;
    for &(s, pass, host) in site::WIFI {
        if s != configured {
            let _ = wifi.disconnect();
            wifi.set_configuration(&mixed(s, pass))?;
            configured = s;
        }
        server_host = host; // при неудаче со всеми - адрес последней пробованной
        let mut last_err = String::new();
        for attempt in 1..=WIFI_TRIES {
            match wifi_try(&mut wifi) {
                Ok(()) => {
                    let ip = wifi.wifi().sta_netif().get_ip_info()?.ip.to_string();
                    let _ = writeln!(sta_txt, "STA     : \"{s}\" -> http://{ip} (attempt {attempt})");
                    sta_ip = ip;
                    break;
                }
                Err(e) => {
                    log::warn!("Wi-Fi \"{s}\" attempt {attempt}/{WIFI_TRIES}: {e}");
                    last_err = e;
                    let _ = wifi.disconnect();
                    FreeRtos::delay_ms(1000);
                }
            }
        }
        if !sta_ip.is_empty() {
            break;
        }
        let _ = writeln!(sta_txt, "STA     : \"{s}\" not connected ({last_err})");
    }
    match wifi.scan() {
        Ok(mut aps) => {
            aps.sort_by(|a, b| b.signal_strength.cmp(&a.signal_strength));
            let _ = writeln!(summary, "WIFI    : {} networks found", aps.len());
            for ap in aps.iter().take(6) {
                let _ = writeln!(summary, "          {:>4} dBm  ch{:<2}  {}", ap.signal_strength, ap.channel, ap.ssid);
            }
        }
        Err(e) => {
            let _ = writeln!(summary, "WIFI    : scan FAILED: {e}");
        }
    }
    summary.push_str(&sta_txt);
    let _ = SERVER_HOST.set(server_host.to_string());
    if sta_ip.is_empty() {
        speaker::say(speaker::NO_WIFI);
    }
    let ip = wifi.wifi().ap_netif().get_ip_info()?.ip;
    let _ = writeln!(summary, "AP      : \"{ssid}\" password \"{AP_PASS}\" -> http://{ip}");
    let _ = writeln!(summary, "SERVER  : http://{}:{}", server_host, site::SERVER_PORT);

    let state: Shared = Arc::new(Mutex::new(State {
        summary: summary.clone(),
        sta_ip,
        server: "not tried yet".into(),
        ..Default::default()
    }));
    let audio: Audio = Arc::new(Mutex::new(None));

    // Микрофоны: отдельная задача читает I2S, считает уровни и кормит слушателя.
    let mic_cfg = StdConfig::new(
        I2sConfig::default(),
        StdClkConfig::from_sample_rate_hz(RATE),
        StdSlotConfig::philips_slot_default(DataBitWidth::Bits32, SlotMode::Stereo),
        StdGpioConfig::default(),
    );
    let mut mic = I2sDriver::new_std_rx(
        p.i2s0,
        &mic_cfg,
        p.pins.gpio11,
        p.pins.gpio10,
        Option::<AnyIOPin>::None,
        p.pins.gpio9,
    )?;
    mic.rx_enable()?;
    let link: Link = Arc::new(Mutex::new(None));
    // Ключевое слово - своя задача: AFE считает тяжело, микрофон ждать не должен.
    let (wake_tx, wake_rx) = sync_channel::<Vec<i16>>(16);
    std::thread::Builder::new()
        .stack_size(24 * 1024) // AFE/WakeNet едят стек при срабатывании
        .spawn(move || wake_task(wake_rx))?;
    {
        let (state, audio, link) = (state.clone(), audio.clone(), link.clone());
        std::thread::Builder::new()
            .stack_size(16 * 1024)
            .spawn(move || mic_task(mic, state, audio, link, wake_tx))?;
    }

    // Звук в браузер: свой маленький сервер на порту 81.
    {
        let audio = audio.clone();
        std::thread::Builder::new()
            .stack_size(8 * 1024)
            .spawn(move || audio_server(audio))?;
    }

    let _http = web_server(state.clone())?;

    // Связь с сервером площадки - своя задача: сеть может подвисать на таймаутах.
    {
        let (state, id, link) = (state.clone(), format!("voiceunit-{:02x}{:02x}", mac[4], mac[5]), link.clone());
        std::thread::Builder::new()
            .stack_size(8 * 1024)
            .spawn(move || server_task(state, id, link))?;
    }

    log::info!(
        "internal RAM free after start: {} KB (largest block {} KB)",
        unsafe { sys::heap_caps_get_free_size(sys::MALLOC_CAP_INTERNAL) } / 1024,
        unsafe { sys::heap_caps_get_largest_free_block(sys::MALLOC_CAP_INTERNAL) } / 1024
    );

    let mut uart = UartDriver::new(
        p.uart1,
        p.pins.gpio43,
        p.pins.gpio44,
        Option::<AnyIOPin>::None,
        Option::<AnyIOPin>::None,
        &UartConfig::default(),
    )?;

    println!("\n{summary}");
    let mut last_summary = Instant::now();
    let mut last_print = Instant::now();
    let mut boot_was = false;
    let mut tick = 0u32;
    let mut last_reconnect = Instant::now();
    let mut wifi_was_up = !state.lock().unwrap().sta_ip.is_empty();
    loop {
        FreeRtos::delay_ms(100);
        tick += 1;
        // Wi-Fi площадки: следим за связью, при потере - переподключение раз в 10 с.
        if tick % 10 == 0 {
            usbaudio::watch(); // режим USB-колонки: кабель выдернули - выход
        }
        if tick % 20 == 0 {
            let up = wifi.is_connected().unwrap_or(false);
            if wifi_was_up && !up {
                speaker::say(speaker::NO_WIFI); // связь пропала - сказать один раз
            }
            wifi_was_up = up;
            if !up && last_reconnect.elapsed() > Duration::from_secs(10) {
                last_reconnect = Instant::now();
                let _ = wifi_try(&mut wifi);
            }
            let ip = if wifi.is_connected().unwrap_or(false) {
                wifi.wifi().sta_netif().get_ip_info().map(|i| i.ip.to_string()).unwrap_or_default()
            } else {
                String::new()
            };
            let mut rec = sys::wifi_ap_record_t::default();
            let rssi = if !ip.is_empty() && unsafe { sys::esp_wifi_sta_get_ap_info(&mut rec) } == 0 {
                rec.rssi
            } else {
                0
            };
            let mut s = state.lock().unwrap();
            if !ip.is_empty() && summary.contains("not connected") {
                // переподключились позже старта - сводка не должна врать
                let ssid_now = unsafe { core::ffi::CStr::from_ptr(rec.ssid.as_ptr() as *const _) }
                    .to_string_lossy()
                    .into_owned();
                summary = summary
                    .lines()
                    .filter(|l| !l.starts_with("STA     :"))
                    .map(|l| {
                        if l.starts_with("AP      :") {
                            format!("STA     : \"{ssid_now}\" -> http://{ip} (reconnected)\n{l}\n")
                        } else {
                            format!("{l}\n")
                        }
                    })
                    .collect();
                s.summary = summary.clone();
            }
            s.sta_ip = ip;
            s.rssi = rssi;
        }
        match LED_MODE.load(Ordering::Relaxed) {
            LED_ON => led.set_low()?,
            LED_OFF => led.set_high()?,
            _ => {
                if tick % 5 == 0 {
                    led.toggle()?;
                }
            }
        }
        let pressed = boot.is_low();
        let loop_ok = if tick % 5 == 0 { Some(uart_loopback(&mut uart)) } else { None };
        {
            let mut s = state.lock().unwrap();
            if pressed && !boot_was && usbaudio::is_on() {
                usbaudio::exit("BOOT"); // BOOT в режиме USB-колонки - выход
            }
            if pressed && !boot_was {
                s.presses += 1;
                SERVER_NOW.store(true, Ordering::Relaxed);
                SEND_NOW.store(true, Ordering::Relaxed);
            }
            s.boot_down = pressed;
            if let Some(ok) = loop_ok {
                s.uart_loop = ok;
            }
            if last_print.elapsed() > Duration::from_millis(500) {
                println!(
                    "MIC  L/MK1 {}  |  R/MK2 {}  |  BOOT {} (x{})  |  UART J4 {}{}",
                    s.mic_l,
                    s.mic_r,
                    if pressed { "DOWN" } else { "up  " },
                    s.presses,
                    if s.uart_loop { "LOOP OK" } else { "no loop" },
                    if s.listening { "  |  streaming" } else { "" }
                );
                if tick % 50 == 0 {
                    println!(
                        "NET  STA {} {} dBm  |  server {} (sent {})",
                        if s.sta_ip.is_empty() { "down" } else { &s.sta_ip },
                        s.rssi,
                        s.server,
                        s.sent
                    );
                }
                last_print = Instant::now();
            }
        }
        boot_was = pressed;
        if last_summary.elapsed() > Duration::from_secs(10) {
            println!("\n{summary}");
            last_summary = Instant::now();
        }
    }
}

/// Одна попытка подключиться к настроенной сети: связь с точкой - не дольше
/// WIFI_TRY_MS (отказ роутера виден сразу, а не через 15 с), потом адрес по DHCP.
fn wifi_try(wifi: &mut BlockingWifi<EspWifi<'static>>) -> Result<(), String> {
    // ESP_ERR_WIFI_CONN - подключение уже идёт: не ошибка, просто ждём его
    if let Err(e) = wifi.wifi_mut().connect() {
        if e.code() != sys::ESP_ERR_WIFI_CONN as i32 {
            return Err(e.to_string());
        }
    }
    let t = Instant::now();
    while !wifi.is_connected().unwrap_or(false) {
        if t.elapsed() > Duration::from_millis(WIFI_TRY_MS) {
            return Err("no association".into());
        }
        FreeRtos::delay_ms(100);
    }
    wifi.wait_netif_up().map_err(|e| format!("no IP: {e}"))
}

fn chip_report(out: &mut String, mac: &[u8; 6]) {
    let mut flash: u32 = 0;
    unsafe { sys::esp_flash_get_size(core::ptr::null_mut(), &mut flash) };
    let _ = writeln!(out, "==== Voice-Unit self-test ====");
    let _ = writeln!(
        out,
        "CHIP    : ESP32-S3, MAC {:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}",
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
    );
    let _ = writeln!(out, "FLASH   : {} MB", flash / (1024 * 1024));
}

fn psram_report(out: &mut String) {
    let total = unsafe { sys::heap_caps_get_total_size(sys::MALLOC_CAP_SPIRAM) };
    if total == 0 {
        let _ = writeln!(out, "PSRAM   : NOT FOUND");
        return;
    }
    // запись/чтение 4 МБ псевдослучайным узором: ловит обрыв линий и залипшие биты
    const N: usize = 1024 * 1024; // слов u32 = 4 МБ
    let ptr = unsafe { sys::heap_caps_malloc(N * 4, sys::MALLOC_CAP_SPIRAM) } as *mut u32;
    if ptr.is_null() {
        let _ = writeln!(out, "PSRAM   : {} KB, alloc 4 MB FAILED", total / 1024);
        return;
    }
    let buf = unsafe { core::slice::from_raw_parts_mut(ptr, N) };
    let pat = |i: usize| (i as u32).wrapping_mul(2_654_435_761) ^ 0xA5A5_5A5A;
    let t = Instant::now();
    for (i, w) in buf.iter_mut().enumerate() {
        *w = pat(i);
    }
    let errors = buf.iter().enumerate().filter(|(i, w)| **w != pat(*i)).count();
    let ms = t.elapsed().as_millis();
    unsafe { sys::heap_caps_free(ptr as *mut core::ffi::c_void) };
    let _ = writeln!(
        out,
        "PSRAM   : {} KB, test 4 MB write/read: {} ({} errors, {} ms)",
        total / 1024,
        if errors == 0 { "OK" } else { "FAILED" },
        errors,
        ms
    );
}

fn mic_task(
    mut mic: I2sDriver<'static, I2sRx>,
    state: Shared,
    audio: Audio,
    link: Link,
    wake_tx: SyncSender<Vec<i16>>,
) {
    let mut raw = vec![0u8; CHUNK * 2 * 4];
    let mut wake_tx = Some(wake_tx);
    // детектор речи
    let mut floor: Option<(f32, f32)> = None;
    let mut rec = false;
    let mut rec_wake = false; // идущая запись - команда после «София»
    let mut wake_wait = false; // «София» услышана, ждём, пока доиграет «слушаю»
    let mut above = 0u32;
    let mut quiet_ms = 0u32;
    let mut rec_ms = 0u32;
    let mut recs = 0u32;
    let mut preroll: VecDeque<Vec<u8>> = VecDeque::with_capacity(PREROLL + 1);
    let mut l = Vec::with_capacity(RATE as usize / 4);
    let mut r = Vec::with_capacity(RATE as usize / 4);
    let mut warmup = 8; // переходный процесс после старта микрофонов
    loop {
        let mut got = 0;
        while got < raw.len() {
            match mic.read(&mut raw[got..], BLOCK) {
                Ok(n) => got += n,
                Err(e) => {
                    log::warn!("i2s read: {e}");
                    FreeRtos::delay_ms(10);
                }
            }
        }
        if warmup > 0 {
            warmup -= 1;
            continue;
        }
        let mut pcm: Option<(Vec<u8>, u8, i32)> = None;
        if let Some(lst) = audio.lock().unwrap().as_ref() {
            pcm = Some((Vec::with_capacity(CHUNK * 2), lst.ch, lst.gain));
        }
        let gain = REC_GAIN.load(Ordering::Relaxed) as i64;
        let (mut sa, mut sb, mut acc) = (0f64, 0f64, 0i64);
        let mut enc = Vec::with_capacity(CHUNK / 2);
        let need_mono = wake_tx.is_some() || usbaudio::is_on();
        let mut mono = Vec::with_capacity(if need_mono { CHUNK } else { 0 });
        for (k, f) in raw.chunks_exact(8).enumerate() {
            let a = i32::from_le_bytes([f[0], f[1], f[2], f[3]]) >> 8;
            let b = i32::from_le_bytes([f[4], f[5], f[6], f[7]]) >> 8;
            l.push(a);
            r.push(b);
            if need_mono {
                // ключевому слову и USB-микрофону - 16 кГц, среднее двух микрофонов
                let v = (((a + b) as i64 / 2 * gain) >> 8).clamp(i16::MIN as i64, i16::MAX as i64);
                mono.push(v as i16);
            }
            sa += (a as f64) * (a as f64);
            sb += (b as f64) * (b as f64);
            // моно 8 кГц: среднее двух микрофонов по двум соседним отсчётам
            acc += (a + b) as i64;
            if k % 2 == 1 {
                let v = ((acc / 4 * gain) >> 8).clamp(i16::MIN as i64, i16::MAX as i64) as i16;
                enc.push(ulaw(v));
                acc = 0;
            }
            if let Some((buf, ch, gain)) = pcm.as_mut() {
                let s = match *ch {
                    0 => a,
                    1 => b,
                    _ => (a + b) / 2,
                };
                let v = ((s as i64 * *gain as i64) >> 8).clamp(i16::MIN as i64, i16::MAX as i64) as i16;
                buf.extend_from_slice(&v.to_le_bytes());
            }
        }
        if let Some((buf, _, _)) = pcm {
            let mut slot = audio.lock().unwrap();
            if let Some(lst) = slot.as_ref() {
                if let Err(TrySendError::Disconnected(_)) = lst.tx.try_send(buf) {
                    *slot = None;
                }
            }
        }
        usbaudio::feed_mic(&mono); // режим USB-колонки: микрофон для ПК
        // опорный канал берём всегда - в темпе микрофона, иначе он отстанет
        let refs = speaker::take_ref(mono.len());
        if let Some(tx) = wake_tx.as_ref() {
            let frame = if WAKE_AEC.load(Ordering::Relaxed) {
                // пары [микрофон, что играло в динамик] - AEC вычтет второе из первого
                mono.iter().zip(refs.iter()).flat_map(|(&m, &r)| [m, r]).collect()
            } else {
                mono
            };
            // задача ключевого слова отстаёт - кусок теряется, микрофон не ждёт
            if let Err(TrySendError::Disconnected(_)) = tx.try_send(frame) {
                wake_tx = None; // модели нет - задача закончилась
            }
        }
        // --- запись по голосу
        let db = |s: f64| 20.0 * ((s / CHUNK as f64).sqrt().max(1.0) as f32 / FULL).log10();
        let (da, dbb) = (db(sa), db(sb));
        let (fa, fb) = floor.get_or_insert((da, dbb));
        if !rec {
            // фон: вниз плавно (за ~0.6 с), вверх ~1 дБ/с; во время записи не трогаем.
            // Резко вниз нельзя: фон садился на редкие провалы, и обычная тишина
            // комнаты считалась речью - запись команды не кончалась до 8 с.
            *fa = if da < *fa { *fa + (da - *fa) * 0.05 } else { *fa + 0.03 };
            *fb = if dbb < *fb { *fb + (dbb - *fb) * 0.05 } else { *fb + 0.03 };
        }
        let (start, stop) = (VAD_START.load(Ordering::Relaxed) as f32, VAD_STOP.load(Ordering::Relaxed) as f32);
        // is_on() - первым: иначе swap съел бы «София» и в обычном режиме
        if usbaudio::is_on() && WAKE_PENDING.swap(false, Ordering::Relaxed) {
            usbaudio::exit("«Sophia»"); // «София» в режиме USB-колонки - выход
        }
        if WAKE_PENDING.swap(false, Ordering::Relaxed) {
            let n = WAKE_COUNT.load(Ordering::Relaxed);
            link_send(&link, WsOut::Text(format!("{{\"type\":\"wake\",\"word\":\"sophia\",\"n\":{n}}}")));
            if rec {
                // идущую запись - закрыть, команда пойдёт отдельной
                rec = false;
                recs += 1;
                link_send(&link, WsOut::Text(format!("{{\"type\":\"rec\",\"state\":\"stop\",\"ms\":{rec_ms}}}")));
            }
            SERVER_AUDIO_MUTED.store(true, Ordering::Relaxed);
            speaker::say(speaker::LISTENING); // «слушаю» - можно говорить команду
            wake_wait = true;
        }
        // запись команды - когда «слушаю» доиграет, чтобы оно не попало в запись
        let wake = wake_wait && !speaker::busy();
        if wake {
            wake_wait = false;
            preroll.clear();
        }
        if !rec {
            // без ключевого слова - старт по громкости, как раньше
            let vad = VAD_ON.load(Ordering::Relaxed) && !WAKE_READY.load(Ordering::Relaxed);
            above = if vad && da > *fa + start && dbb > *fb + start { above + 1 } else { 0 };
            preroll.push_back(enc);
            if preroll.len() > PREROLL {
                preroll.pop_front();
            }
            if wake || above >= 2 {
                rec = true;
                rec_wake = wake;
                quiet_ms = 0;
                rec_ms = 0;
                let reason = if wake { "\"reason\":\"wake\"," } else { "" };
                link_send(
                    &link,
                    WsOut::Text(format!(
                        "{{\"type\":\"rec\",\"state\":\"start\",{reason}\"rate\":8000,\"codec\":\"mulaw\",\
                         \"l_db\":{da:.1},\"r_db\":{dbb:.1},\"floor_l\":{:.1},\"floor_r\":{:.1}}}",
                        *fa, *fb
                    )),
                );
                for p in preroll.drain(..) {
                    link_send(&link, WsOut::Bin(p));
                }
                SEND_NOW.store(true, Ordering::Relaxed);
            }
        } else {
            link_send(&link, WsOut::Bin(enc));
            rec_ms += CHUNK_MS;
            // тишина - по двум микрофонам вместе: один шумный канал её не отменяет
            let over = ((da - *fa) + (dbb - *fb)) / 2.0;
            quiet_ms = if over < stop { quiet_ms + CHUNK_MS } else { 0 };
            let done = if rec_wake {
                (rec_ms > WAKE_GRACE_MS && quiet_ms >= WAKE_HANG_MS) || rec_ms >= WAKE_REC_MAX_MS
            } else {
                quiet_ms >= VAD_HANG.load(Ordering::Relaxed) || rec_ms >= REC_MAX_MS || !VAD_ON.load(Ordering::Relaxed)
            };
            if done {
                SERVER_AUDIO_MUTED.store(false, Ordering::Relaxed); // команда сказана
                rec = false;
                recs += 1;
                link_send(&link, WsOut::Text(format!("{{\"type\":\"rec\",\"state\":\"stop\",\"ms\":{rec_ms}}}")));
                SEND_NOW.store(true, Ordering::Relaxed);
            }
        }
        {
            let mut s = state.lock().unwrap();
            s.rec = rec;
            s.recs = recs;
            s.floor_l = *fa;
            s.floor_r = *fb;
        }

        if l.len() >= RATE as usize / 4 {
            let (lt, ld) = level(&l);
            let (rt, rd) = level(&r);
            let listening = audio.lock().unwrap().is_some();
            let mut s = state.lock().unwrap();
            s.mic_l = lt;
            s.mic_r = rt;
            s.l_db = ld;
            s.r_db = rd;
            s.listening = listening;
            l.clear();
            r.clear();
        }
    }
}

/// Задача ключевого слова: кадры 16 кГц от микрофона -> AFE/WakeNet. Модели во
/// flash нет - пишет причину в журнал и заканчивается (запись по громкости остаётся).
fn wake_task(rx: std::sync::mpsc::Receiver<Vec<i16>>) {
    let mut ww = match wakeword::WakeWord::new() {
        Ok(w) => w,
        Err(e) => {
            log::warn!("wake word OFF: {e}");
            return;
        }
    };
    let n = ww.frame_len();
    let mut buf: Vec<i16> = Vec::with_capacity(n * 2);
    WAKE_AEC.store(ww.aec, Ordering::Relaxed);
    while rx.try_recv().is_ok() {} // накопленное до старта - ещё моно, выбросить
    WAKE_READY.store(true, Ordering::Relaxed);
    log::info!("wake word ON: say \"Sophia\" (echo cancellation: {})", ww.aec);
    while let Ok(chunk) = rx.recv() {
        buf.extend_from_slice(&chunk);
        while buf.len() >= n {
            if ww.process(&buf[..n]) {
                let k = WAKE_COUNT.fetch_add(1, Ordering::Relaxed) + 1;
                log::info!("wake word: Sophia ({k})");
                WAKE_PENDING.store(true, Ordering::Relaxed);
            }
            buf.drain(..n);
        }
    }
}

fn link_send(link: &Link, m: WsOut) {
    if let Some(tx) = link.lock().unwrap().as_ref() {
        let _ = tx.try_send(m); // очередь полна - кусок теряется, задача микрофона не ждёт
    }
}

/// G.711 μ-law: 16 бит -> 8 бит, как в телефонии.
fn ulaw(pcm: i16) -> u8 {
    const BIAS: i32 = 0x84;
    const CLIP: i32 = 32635;
    let mut s = pcm as i32;
    let sign = if s < 0 {
        s = -s;
        0x80
    } else {
        0
    };
    s = s.min(CLIP) + BIAS;
    let mut exp = 7;
    let mut mask = 0x4000;
    while exp > 0 && s & mask == 0 {
        exp -= 1;
        mask >>= 1;
    }
    let mant = (s >> (exp + 3)) & 0x0F;
    !((sign | (exp << 4) | mant) as u8)
}

/// Уровень канала: текст для порта и dBFS для страницы (-200 - линия мёртвая).
fn level(samples: &[i32]) -> (String, f32) {
    if samples.iter().all(|&s| s == 0) {
        return ("NO DATA (all 0)    ".into(), -200.0);
    }
    if samples.iter().all(|&s| s == -1) {
        return ("STUCK (all 1)      ".into(), -200.0);
    }
    let n = samples.len() as f32;
    let mean = samples.iter().map(|&s| s as f32).sum::<f32>() / n;
    let rms = (samples.iter().map(|&s| (s as f32 - mean).powi(2)).sum::<f32>() / n).sqrt();
    let peak = samples.iter().map(|&s| (s as f32 - mean).abs()).fold(0.0f32, f32::max);
    let db = |v: f32| 20.0 * (v.max(1.0) / FULL).log10();
    (format!("{:6.1} dBFS pk {:4.0}", db(rms), db(peak)), db(rms))
}

fn audio_server(audio: Audio) {
    let listener = match TcpListener::bind("0.0.0.0:81") {
        Ok(l) => l,
        Err(e) => {
            log::error!("audio server: {e}");
            return;
        }
    };
    for conn in listener.incoming().flatten() {
        let audio = audio.clone();
        let _ = std::thread::Builder::new()
            .stack_size(8 * 1024)
            .spawn(move || {
                if let Err(e) = stream_wav(conn, audio) {
                    log::info!("audio client gone: {e}");
                }
            });
    }
}

fn stream_wav(mut conn: TcpStream, audio: Audio) -> std::io::Result<()> {
    let mut req = [0u8; 512];
    let n = conn.read(&mut req)?;
    let req = String::from_utf8_lossy(&req[..n]);
    let line = req.lines().next().unwrap_or("");
    let ch = match query(line, "ch") {
        Some("r") => 1,
        Some("m") => 2,
        _ => 0,
    };
    let gain = query(line, "g").and_then(|g| g.parse::<i32>().ok()).unwrap_or(16).clamp(1, 256);

    // WAV без известной длины: размер "почти бесконечный", браузер играет по мере прихода.
    let mut head = Vec::with_capacity(300);
    head.extend_from_slice(
        b"HTTP/1.1 200 OK\r\nContent-Type: audio/wav\r\nCache-Control: no-cache\r\n\
          Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
    );
    let data_len: u32 = 0x7FFF_0000;
    head.extend_from_slice(b"RIFF");
    head.extend_from_slice(&(data_len + 36).to_le_bytes());
    head.extend_from_slice(b"WAVEfmt ");
    head.extend_from_slice(&16u32.to_le_bytes());
    head.extend_from_slice(&1u16.to_le_bytes()); // PCM
    head.extend_from_slice(&1u16.to_le_bytes()); // моно
    head.extend_from_slice(&RATE.to_le_bytes());
    head.extend_from_slice(&(RATE * 2).to_le_bytes());
    head.extend_from_slice(&2u16.to_le_bytes());
    head.extend_from_slice(&16u16.to_le_bytes());
    head.extend_from_slice(b"data");
    head.extend_from_slice(&data_len.to_le_bytes());
    conn.write_all(&head)?;

    // Новый слушатель вытесняет старого: у старого канал закроется и поток завершится.
    let (tx, rx) = sync_channel::<Vec<u8>>(32);
    *audio.lock().unwrap() = Some(Listener { tx, ch, gain });
    log::info!("audio client: ch {ch}, gain {gain}");
    while let Ok(buf) = rx.recv() {
        conn.write_all(&buf)?;
    }
    Ok(())
}

fn query<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let q = line.split(' ').nth(1)?.split_once('?')?.1;
    q.split('&').find_map(|kv| {
        let (k, v) = kv.split_once('=')?;
        (k == key).then_some(v)
    })
}

fn web_server(state: Shared) -> anyhow::Result<EspHttpServer<'static>> {
    let mut server = EspHttpServer::new(&HttpConfig { stack_size: 10 * 1024, ..Default::default() })?;
    server.fn_handler("/", Method::Get, |req| -> anyhow::Result<()> {
        req.into_response(200, Some("OK"), &[("Content-Type", "text/html; charset=utf-8")])?
            .write_all(PAGE.as_bytes())?;
        Ok(())
    })?;
    server.fn_handler("/led", Method::Get, |req| -> anyhow::Result<()> {
        let mode = match query(&format!("GET {} HTTP", req.uri()), "m") {
            Some("on") => LED_ON,
            Some("off") => LED_OFF,
            _ => LED_BLINK,
        };
        LED_MODE.store(mode, Ordering::Relaxed);
        SEND_NOW.store(true, Ordering::Relaxed);
        req.into_ok_response()?.write_all(b"ok")?;
        Ok(())
    })?;
    server.fn_handler("/status", Method::Get, move |req| -> anyhow::Result<()> {
        let json = {
            let s = state.lock().unwrap();
            let free_psram = unsafe { sys::heap_caps_get_free_size(sys::MALLOC_CAP_SPIRAM) };
            let up = unsafe { sys::esp_timer_get_time() } / 1_000_000;
            format!(
                "{{\"summary\":{},\"l_db\":{:.1},\"r_db\":{:.1},\"l\":{},\"r\":{},\"boot\":{},\
                 \"presses\":{},\"uart\":{},\"led\":{},\"listening\":{},\"psram_free\":{},\"uptime\":{},\
                 \"sta_ip\":{},\"rssi\":{},\"server\":{},\"sent\":{}}}",
                json_str(&s.summary),
                s.l_db,
                s.r_db,
                json_str(s.mic_l.trim()),
                json_str(s.mic_r.trim()),
                s.boot_down,
                s.presses,
                s.uart_loop,
                LED_MODE.load(Ordering::Relaxed),
                s.listening,
                free_psram / 1024,
                up,
                json_str(&s.sta_ip),
                s.rssi,
                json_str(&s.server),
                s.sent
            )
        };
        req.into_response(200, Some("OK"), &[("Content-Type", "application/json")])?
            .write_all(json.as_bytes())?;
        Ok(())
    })?;
    Ok(server)
}

fn json_str(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            c if (c as u32) < 0x20 => {}
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

/// Перемычка TX-RX на J4: отправленное должно вернуться.
fn uart_loopback(uart: &mut UartDriver<'_>) -> bool {
    let mut junk = [0u8; 64];
    while uart.read(&mut junk, 0).unwrap_or(0) > 0 {}
    let msg = b"AUTOPROBE";
    if uart.write(msg).is_err() {
        return false;
    }
    let mut back = [0u8; 16];
    let mut got = 0;
    let t = Instant::now();
    while got < msg.len() && t.elapsed() < Duration::from_millis(20) {
        got += uart.read(&mut back[got..], 2).unwrap_or(0);
    }
    &back[..got] == msg
}

const PAGE: &str = r#"<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice-Unit</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--fg:#1d2330;--mut:#6b7280;--acc:#2563eb;--ok:#16a34a;--bad:#dc2626;--bar:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1b2027;--fg:#e6e8eb;--mut:#9aa3ad;--acc:#60a5fa;--ok:#4ade80;--bad:#f87171;--bar:#2a313b}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
main{max-width:640px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 12px}
.card{background:var(--card);border-radius:12px;padding:14px;margin-bottom:12px}
h2{font-size:14px;margin:0 0 10px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
pre{margin:0;white-space:pre-wrap;font:12px/1.45 ui-monospace,monospace}
button,select{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid var(--bar);background:var(--card);color:var(--fg)}
button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.m{margin:8px 0}.m b{display:inline-block;width:76px}
.bar{height:12px;background:var(--bar);border-radius:6px;overflow:hidden;flex:1;min-width:120px}
.bar i{display:block;height:100%;width:0;background:var(--acc);transition:width .2s}
.val{font:12px ui-monospace,monospace;color:var(--mut);min-width:150px}
.ok{color:var(--ok)}.bad{color:var(--bad)}
</style></head><body><main>
<h1>Voice-Unit — проверка платы</h1>
<div class="card"><h2>Микрофоны</h2>
<div class="row m"><b>MK1 (L)</b><div class="bar"><i id="bl"></i></div><span class="val" id="vl">—</span></div>
<div class="row m"><b>MK2 (R)</b><div class="bar"><i id="br"></i></div><span class="val" id="vr">—</span></div>
<div class="row" style="margin-top:10px">
<select id="ch"><option value="l">Слушать MK1</option><option value="r">Слушать MK2</option><option value="m">Оба</option></select>
<select id="g"><option value="4">усиление ×4</option><option value="16" selected>×16</option><option value="64">×64</option><option value="256">×256</option></select>
<button id="play">▶ Слушать</button><button id="stop">■ Стоп</button></div>
<audio id="au" preload="none"></audio>
<div class="val" style="margin-top:6px">Задержка звука в браузере — 1–3 с. Похлопайте или поговорите рядом с каждым микрофоном.</div>
</div>
<div class="card"><h2>Светодиод D3 и кнопка</h2>
<div class="row"><button data-m="on">Вкл</button><button data-m="off">Выкл</button><button data-m="blink">Мигать</button></div>
<div class="m" id="btn">BOOT: —</div>
<div class="m" id="uart">UART J4: —</div>
</div>
<div class="card"><h2>Сеть и сервер</h2>
<div class="m" id="net">—</div><div class="m" id="srv">—</div>
<div class="val">Нажатие BOOT — связаться с сервером сразу, не дожидаясь паузы 30 с.</div></div>
<div class="card"><h2>Самопроверка</h2><pre id="sum">загрузка…</pre>
<div class="val" id="up" style="margin-top:8px"></div></div>
</main><script>
const $=id=>document.getElementById(id);
const pct=db=>db<-150?0:Math.max(0,Math.min(100,(db+90)/70*100));
document.querySelectorAll('[data-m]').forEach(b=>b.onclick=()=>fetch('/led?m='+b.dataset.m).then(poll));
$('play').onclick=()=>{const a=$('au');a.src='http://'+location.hostname+':81/a.wav?ch='+$('ch').value+'&g='+$('g').value+'&t='+Date.now();a.play();};
$('stop').onclick=()=>{const a=$('au');a.pause();a.removeAttribute('src');a.load();};
async function poll(){try{const s=await (await fetch('/status')).json();
$('bl').style.width=pct(s.l_db)+'%';$('br').style.width=pct(s.r_db)+'%';
$('vl').textContent=s.l;$('vr').textContent=s.r;
$('vl').className='val '+(s.l_db<-150?'bad':'');$('vr').className='val '+(s.r_db<-150?'bad':'');
$('btn').innerHTML='BOOT: '+(s.boot?'<b class="ok">нажата</b>':'отпущена')+' · нажатий: '+s.presses;
$('uart').innerHTML='UART J4: '+(s.uart?'<b class="ok">петля TX→RX работает</b>':'перемычки TX-RX нет');
document.querySelectorAll('[data-m]').forEach(b=>b.classList.toggle('on',['off','on','blink'][s.led]==b.dataset.m));
$('net').innerHTML='Wi-Fi гаража: '+(s.sta_ip?'<b class="ok">'+s.sta_ip+'</b> · '+s.rssi+' dBm':'<b class="bad">не подключено</b>');
$('srv').innerHTML='Сервер: '+(s.server.startsWith('online')?'<b class="ok">'+s.server+'</b>':'<b class="bad">'+s.server+'</b>')+' · отправлено '+s.sent;
$('sum').textContent=s.summary;$('up').textContent='работает '+s.uptime+' с · свободно PSRAM '+s.psram_free+' КБ'+(s.listening?' · идёт звук':'');
}catch(e){$('up').textContent='нет связи с платой';}}
setInterval(poll,400);poll();
</script></body></html>
"#;

/// Связь с сервером площадки по WebSocket. Нет связи - RETRY_COUNT попыток через
/// RETRY_DELAY, потом пауза SERVER_BACKOFF (или до нажатия BOOT).
fn server_task(state: Shared, id: String, link: Link) {
    let addr: SocketAddr = match format!("{}:{}", server_host(), site::SERVER_PORT).parse() {
        Ok(a) => a,
        Err(e) => {
            state.lock().unwrap().server = format!("bad address: {e}");
            return;
        }
    };
    let mut next = Instant::now();
    let mut fails = 0u32;
    let mut announced = false; // «сервер недоступен» уже сказано
    loop {
        FreeRtos::delay_ms(200);
        if SERVER_NOW.swap(false, Ordering::Relaxed) {
            next = Instant::now();
            fails = 0;
        }
        if Instant::now() < next {
            continue;
        }
        if state.lock().unwrap().sta_ip.is_empty() {
            state.lock().unwrap().server = "waiting for Wi-Fi".into();
            next = Instant::now() + Duration::from_secs(2);
            continue;
        }
        let (was_up, why) = ws_session(addr, &id, &state, &link);
        *link.lock().unwrap() = None;
        if was_up {
            fails = 0; // связь была - сразу пробуем восстановить
            announced = false;
        }
        fails += 1;
        let mut s = state.lock().unwrap();
        if fails >= RETRY_COUNT {
            if !announced {
                speaker::say(speaker::SERVER_DOWN); // один раз на каждый обрыв
                SAY_READY.store(true, Ordering::Relaxed);
                announced = true;
            }
            s.server = format!("offline ({why}), retry in 30 s");
            next = Instant::now() + SERVER_BACKOFF;
            fails = 0;
        } else {
            s.server = format!("reconnecting ({why})");
            next = Instant::now() + RETRY_DELAY;
        }
    }
}

/// Один сеанс WebSocket: (было ли соединение установлено, причина конца).
fn ws_session(addr: SocketAddr, id: &str, state: &Shared, link: &Link) -> (bool, String) {
    let mut c = match TcpStream::connect_timeout(&addr, Duration::from_secs(2)) {
        Ok(c) => c,
        Err(e) => return (false, e.to_string()),
    };
    let _ = c.set_nodelay(true);
    let _ = c.set_write_timeout(Some(Duration::from_secs(3)));
    let _ = c.set_read_timeout(Some(Duration::from_secs(3)));
    // Ключ рукопожатия фиксированный: ответ сервера (Sec-WebSocket-Accept) не проверяем,
    // нам достаточно кода 101 - сеть своя.
    let req = format!(
        "GET /ws?id={id} HTTP/1.1\r\nHost: {addr}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\
         Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n"
    );
    if let Err(e) = c.write_all(req.as_bytes()) {
        return (false, e.to_string());
    }
    let mut buf = Vec::new();
    let mut tmp = [0u8; 512];
    let head_end = loop {
        match c.read(&mut tmp) {
            Ok(0) => return (false, "closed during handshake".into()),
            Ok(n) => buf.extend_from_slice(&tmp[..n]),
            Err(e) => return (false, e.to_string()),
        }
        if let Some(i) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
            break i + 4;
        }
        if buf.len() > 4096 {
            return (false, "handshake too long".into());
        }
    };
    if !String::from_utf8_lossy(&buf[..head_end]).starts_with("HTTP/1.1 101") {
        return (false, "server refused websocket".into());
    }
    buf.drain(..head_end);
    state.lock().unwrap().server = format!("online ws://{addr}");
    // после старта и после объявленного обрыва - «Connected»
    if SAY_READY.swap(false, Ordering::Relaxed) {
        speaker::say(speaker::READY);
    }
    let _ = c.set_read_timeout(Some(Duration::from_millis(20)));
    let (tx, rx) = sync_channel::<WsOut>(64); // ~2 с звука
    *link.lock().unwrap() = Some(tx);

    let mut last_tx = Instant::now() - TELEMETRY_PERIOD;
    loop {
        match c.read(&mut tmp) {
            Ok(0) => return (true, "closed by server".into()),
            Ok(n) => buf.extend_from_slice(&tmp[..n]),
            Err(e) if matches!(e.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {}
            Err(e) => return (true, e.to_string()),
        }
        while let Some((op, payload, used)) = ws_parse(&buf) {
            buf.drain(..used);
            match op {
                0x1 => {
                    apply_command(&String::from_utf8_lossy(&payload));
                    SEND_NOW.store(true, Ordering::Relaxed); // подтвердить сразу
                }
                // речь/радио: 16 бит, 16 кГц, моно (не во время команды после «София»)
                // и не в режиме USB-колонки: тогда динамик - у компьютера
                0x2 if !SERVER_AUDIO_MUTED.load(Ordering::Relaxed) && !usbaudio::is_on() => {
                    speaker::push_pcm(&payload)
                }
                0x8 => return (true, "server closed websocket".into()),
                0x9 => {
                    if let Err(e) = ws_send(&mut c, 0xA, &payload) {
                        return (true, e.to_string());
                    }
                }
                _ => {}
            }
        }
        while let Ok(m) = rx.try_recv() {
            let r = match m {
                WsOut::Text(t) => ws_send(&mut c, 0x1, t.as_bytes()),
                WsOut::Bin(b) => ws_send(&mut c, 0x2, &b),
            };
            if let Err(e) = r {
                return (true, e.to_string());
            }
        }
        if SEND_NOW.swap(false, Ordering::Relaxed) || last_tx.elapsed() >= TELEMETRY_PERIOD {
            let body = telemetry_json(state, id);
            if let Err(e) = ws_send(&mut c, 0x1, body.as_bytes()) {
                return (true, e.to_string());
            }
            state.lock().unwrap().sent += 1;
            last_tx = Instant::now();
        }
        if state.lock().unwrap().sta_ip.is_empty() {
            return (true, "Wi-Fi lost".into());
        }
    }
}

/// Целый кадр WebSocket в начале буфера: (опкод, данные, сколько байт занял).
fn ws_parse(buf: &[u8]) -> Option<(u8, Vec<u8>, usize)> {
    if buf.len() < 2 {
        return None;
    }
    let op = buf[0] & 0x0F;
    let masked = buf[1] & 0x80 != 0;
    let (len, mut i) = match buf[1] & 0x7F {
        126 => (u16::from_be_bytes([*buf.get(2)?, *buf.get(3)?]) as usize, 4),
        127 => (u64::from_be_bytes(buf.get(2..10)?.try_into().ok()?) as usize, 10),
        n => (n as usize, 2),
    };
    let mask = if masked {
        let m: [u8; 4] = buf.get(i..i + 4)?.try_into().ok()?;
        i += 4;
        Some(m)
    } else {
        None
    };
    let mut data = buf.get(i..i + len)?.to_vec();
    if let Some(m) = mask {
        for (k, b) in data.iter_mut().enumerate() {
            *b ^= m[k % 4];
        }
    }
    Some((op, data, i + len))
}

/// Кадр от клиента: по стандарту обязательно с маской.
fn ws_send(c: &mut TcpStream, op: u8, payload: &[u8]) -> std::io::Result<()> {
    let mut f = Vec::with_capacity(payload.len() + 14);
    f.push(0x80 | op);
    match payload.len() {
        n if n < 126 => f.push(0x80 | n as u8),
        n if n < 65536 => {
            f.push(0x80 | 126);
            f.extend_from_slice(&(n as u16).to_be_bytes());
        }
        n => {
            f.push(0x80 | 127);
            f.extend_from_slice(&(n as u64).to_be_bytes());
        }
    }
    let mask = unsafe { sys::esp_random() }.to_le_bytes();
    f.extend_from_slice(&mask);
    f.extend(payload.iter().enumerate().map(|(k, b)| b ^ mask[k % 4]));
    c.write_all(&f)
}

fn telemetry_json(state: &Shared, id: &str) -> String {
    // уровень сигнала - прямо сейчас (первая посылка не ждёт главного цикла)
    let mut rec = sys::wifi_ap_record_t::default();
    let rssi = if unsafe { sys::esp_wifi_sta_get_ap_info(&mut rec) } == 0 { rec.rssi } else { 0 };
    let s = state.lock().unwrap();
    let up = unsafe { sys::esp_timer_get_time() } / 1_000_000;
    let free_psram = unsafe { sys::heap_caps_get_free_size(sys::MALLOC_CAP_SPIRAM) };
    format!(
        "{{\"type\":\"telemetry\",\"id\":{},\"fw\":\"voiceunit-test {}\",\"uptime\":{},\"ip\":{},\"rssi\":{},\
         \"mic_l_db\":{:.1},\"mic_r_db\":{:.1},\"boot_presses\":{},\"led\":\"{}\",\
         \"uart_loop\":{},\"listening\":{},\"psram_free_kb\":{},\
         \"rec\":{},\"recs\":{},\"floor_l\":{:.1},\"floor_r\":{:.1},\
         \"vad\":{},\"v_start\":{},\"v_stop\":{},\"v_hang\":{},\"v_gain\":{},\"vol\":{},\"wake\":{},\"usb\":{},\"usb_host\":{},         \"spk_under\":{},\"spk_over\":{},\"spk_peak\":{},\"spk_queue\":{},\"usb_rx\":{},\"usb_drop\":{}}}",
        json_str(id),
        env!("CARGO_PKG_VERSION"),
        up,
        json_str(&s.sta_ip),
        rssi,
        s.l_db,
        s.r_db,
        s.presses,
        ["off", "on", "blink"][LED_MODE.load(Ordering::Relaxed).min(2) as usize],
        s.uart_loop,
        s.listening,
        free_psram / 1024,
        s.rec,
        s.recs,
        s.floor_l,
        s.floor_r,
        VAD_ON.load(Ordering::Relaxed),
        VAD_START.load(Ordering::Relaxed),
        VAD_STOP.load(Ordering::Relaxed),
        VAD_HANG.load(Ordering::Relaxed),
        REC_GAIN.load(Ordering::Relaxed),
        speaker::volume(),
        WAKE_READY.load(Ordering::Relaxed),
        usbaudio::is_on(),
        usbaudio::host_connected(),
        speaker::UNDERRUNS.load(Ordering::Relaxed),
        speaker::OVERFLOW.load(Ordering::Relaxed),
        speaker::PEAK.swap(0, Ordering::Relaxed),
        speaker::queued(),
        usbaudio::RX_BYTES.load(Ordering::Relaxed),
        usbaudio::DROPPED.load(Ordering::Relaxed)
    )
}

/// Команды сервера: светодиод и настройки записи по голосу.
fn apply_command(msg: &str) {
    if msg.contains("\"type\":\"cfg\"") {
        if let Some(v) = json_num(msg, "vad") {
            VAD_ON.store(v != 0.0, Ordering::Relaxed);
        }
        if let Some(v) = json_num(msg, "start") {
            VAD_START.store((v as i32).clamp(3, 60), Ordering::Relaxed);
        }
        if let Some(v) = json_num(msg, "stop") {
            VAD_STOP.store((v as i32).clamp(1, 60), Ordering::Relaxed);
        }
        if let Some(v) = json_num(msg, "hang") {
            VAD_HANG.store((v as u32).clamp(300, 20_000), Ordering::Relaxed);
        }
        if let Some(v) = json_num(msg, "gain") {
            REC_GAIN.store((v as u32).clamp(1, 256), Ordering::Relaxed);
        }
        return;
    }
    // динамик: {"type":"cmd","vol":..} | {"tone":..,"ms":..} | {"stop":1}
    if let Some(v) = json_num(msg, "vol") {
        speaker::set_volume(v.clamp(0.0, 100.0) as u8);
    }
    if json_num(msg, "stop").is_some() {
        speaker::clear();
    }
    if let Some(f) = json_num(msg, "tone") {
        speaker::tone(f.clamp(50.0, 8000.0), json_num(msg, "ms").unwrap_or(300.0).max(0.0) as u32);
    }
    // режим USB-колонки: {"usb":1} - войти (если плату видит компьютер), {"usb":0} - выйти
    match json_num(msg, "usb") {
        Some(v) if v != 0.0 => {
            if let Err(e) = usbaudio::start() {
                log::warn!("USB speaker mode refused: {e}");
            }
        }
        Some(_) if usbaudio::is_on() => usbaudio::exit("server"),
        _ => {}
    }
    if let Some(i) = msg.find("\"led\":\"") {
        let v = &msg[i + 7..];
        let mode = match v.split('"').next().unwrap_or("") {
            "on" => LED_ON,
            "off" => LED_OFF,
            "blink" => LED_BLINK,
            _ => return,
        };
        LED_MODE.store(mode, Ordering::Relaxed);
    }
}

/// Число из плоского JSON: "key":123 / "key":-4.5 / "key":true.
fn json_num(msg: &str, key: &str) -> Option<f32> {
    let i = msg.find(&format!("\"{key}\":"))? + key.len() + 3;
    let v: String = msg[i..].trim_start().chars().take_while(|c| !matches!(c, ',' | '}')).collect();
    match v.trim() {
        "true" => Some(1.0),
        "false" => Some(0.0),
        t => t.parse().ok(),
    }
}
