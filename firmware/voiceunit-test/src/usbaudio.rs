//! USB-колонка с микрофоном: ПК видит плату как звуковое устройство «Voice Cell»
//! (UAC 2.0, компонент espressif/usb_device_uac): звук ПК - в динамик, микрофоны
//! платы (смесь двух) - в ПК. 16 кГц, 16 бит, моно в обе стороны.
//!
//! Вход - командой сервера ({"type":"cmd","usb":1}) и только если плату видит
//! компьютер (не зарядка): это знает USB-порт по умолчанию (USB-Serial-JTAG).
//! После входа USB занят аудио: COM-порта нет, но Wi-Fi и связь с сервером
//! остаются - журнал и команды идут через сервер.
//!
//! Выход - только перезагрузкой: компонент выключаться не умеет. Поводы: «София»,
//! BOOT, выдернули кабель, команда сервера ({"usb":0}). RESET - тоже обычный
//! старт: режим нигде не запоминается.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use esp_idf_svc::hal::delay::FreeRtos;
use esp_idf_svc::sys::{self, uac};

use crate::speaker;

static ON: AtomicBool = AtomicBool::new(false);
/// Диагностика: байт звука от ПК всего и выброшено (буфер > 250 мс).
pub static RX_BYTES: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
pub static DROPPED: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
/// Выходим: звук ПК больше не играем - звучит «Switching back, one moment.»
static EXITING: AtomicBool = AtomicBool::new(false);
/// Микрофон для ПК: не больше 0.5 с (ПК забирает по 10 мс).
static MIC: Mutex<VecDeque<i16>> = Mutex::new(VecDeque::new());
const MIC_CAP: usize = 8_000;
/// Громкость платы до входа - на «звук выключен» в Windows и обратно.
static VOL_BEFORE_MUTE: AtomicU8 = AtomicU8::new(0);
static STARTED: Mutex<Option<Instant>> = Mutex::new(None);

extern "C" {
    /// TinyUSB: компьютер принял устройство (перечислил и настроил).
    fn tud_mounted() -> bool;
}

pub fn is_on() -> bool {
    ON.load(Ordering::Relaxed)
}

/// Плату видит компьютер (идут кадры USB), а не просто питание от зарядки.
/// Только в обычном режиме: после входа USB у аудио, а не у USB-Serial-JTAG.
pub fn host_connected() -> bool {
    !is_on() && unsafe { sys::usb_serial_jtag_is_connected() }
}

/// Стать USB-колонкой. Err - причина отказа.
pub fn start() -> Result<(), &'static str> {
    if is_on() {
        return Ok(());
    }
    if !host_connected() {
        return Err("no USB host (charger or cable without data?)");
    }
    MIC.lock().unwrap().clear();
    let mut cfg = uac::uac_device_config_t {
        output_cb: Some(output_cb),
        input_cb: Some(input_cb),
        set_mute_cb: Some(mute_cb),
        set_volume_cb: Some(volume_cb),
        ..Default::default()
    };
    // USB-Serial-JTAG отдаёт USB аудио: дальше журнал только через сервер
    log::warn!("USB speaker+mic mode: USB is now audio, COM port goes away until reboot");
    FreeRtos::delay_ms(100);
    let r = unsafe { uac::uac_device_init(&mut cfg) };
    if r != sys::ESP_OK {
        return Err("uac_device_init failed");
    }
    *STARTED.lock().unwrap() = Some(Instant::now());
    ON.store(true, Ordering::Relaxed);
    speaker::say(speaker::USB_ON); // «USB speaker on.» - что произошло
    Ok(())
}

/// Выйти из режима: компонент не выключается - перезагрузка в обычный режим.
/// Сначала - «Switching back, one moment.»: иначе «Connected» после перезагрузки
/// звучит как неожиданность. Звук ПК на это время не играем.
pub fn exit(why: &str) -> ! {
    log::warn!("USB speaker mode: exit ({why}) - restarting");
    EXITING.store(true, Ordering::Relaxed);
    speaker::say(speaker::USB_OFF);
    let t = Instant::now();
    FreeRtos::delay_ms(200); // задача динамика забрала фразу - busy() честный
    while speaker::busy() && t.elapsed() < Duration::from_secs(4) {
        FreeRtos::delay_ms(50);
    }
    usb_back_to_serial_jtag();
    usb_detach(300);
    unsafe { sys::esp_restart() }
}

/// Отпустить линию D+ на ms миллисекунд: для компьютера устройство «выдернули».
/// Без этого при перезагрузке линия не падала, Windows не замечала, что аудио
/// больше нет, и держала «usb uac» призраком: COM-порт не появлялся, микрофон
/// Windows оставался на мёртвом устройстве. Подтяжку D+ обратно включает
/// usb_back_to_serial_jtag() в начале старта.
fn usb_detach(ms: u32) {
    let conf0 = (sys::DR_REG_USB_SERIAL_JTAG_BASE as usize + 0x18) as *mut u32;
    const PAD_PULL_OVERRIDE: u32 = 1 << 8;
    const DP_PULLUP: u32 = 1 << 9;
    unsafe {
        let v = conf0.read_volatile();
        conf0.write_volatile((v | PAD_PULL_OVERRIDE) & !DP_PULLUP);
    }
    FreeRtos::delay_ms(ms);
}

/// Вернуть USB обычному COM-порту (USB-Serial-JTAG). Переключатель PHY живёт в
/// RTC-домене и программной перезагрузкой НЕ сбрасывается: без этого после выхода
/// из режима USB оставался подключён к аудио-контроллеру, которого уже никто не
/// запускал, и компьютер не видел плату совсем (ни COM-порта, ни usb_host) до
/// отключения питания. Вызывается перед перезагрузкой и в начале старта.
/// Регистры - как usb_fsls_phy_ll_int_jtag_enable() в ESP-IDF 5.2 (ESP32-S3).
pub fn usb_back_to_serial_jtag() {
    const USJ_CONF0: *mut u32 = sys::DR_REG_USB_SERIAL_JTAG_BASE as usize as *mut u32; // + 0x18 ниже
    const PHY_SEL: u32 = 1 << 0;
    const PAD_PULL_OVERRIDE: u32 = 1 << 8;
    const DP_PULLUP: u32 = 1 << 9;
    const USB_PAD_ENABLE: u32 = 1 << 14;
    const RTC_USB_CONF: *mut u32 = sys::RTC_CNTL_USB_CONF_REG as usize as *mut u32;
    const SW_USB_PHY_SEL: u32 = 1 << 19;
    const SW_HW_USB_PHY_SEL: u32 = 1 << 20;
    unsafe {
        let conf0 = USJ_CONF0.byte_add(0x18);
        let v = conf0.read_volatile();
        conf0.write_volatile((v & !(PHY_SEL | PAD_PULL_OVERRIDE)) | DP_PULLUP | USB_PAD_ENABLE);
        let v = RTC_USB_CONF.read_volatile();
        RTC_USB_CONF.write_volatile((v & !SW_USB_PHY_SEL) | SW_HW_USB_PHY_SEL);
    }
}

/// Раз в секунду из главного цикла: кабель выдернули (или ПК так и не принял
/// устройство за 15 с) - выходим.
pub fn watch() {
    static WAS_MOUNTED: AtomicBool = AtomicBool::new(false);
    static UNMOUNTED_SINCE: Mutex<Option<Instant>> = Mutex::new(None);
    if !is_on() {
        return;
    }
    let mounted = unsafe { tud_mounted() };
    if mounted {
        WAS_MOUNTED.store(true, Ordering::Relaxed);
        *UNMOUNTED_SINCE.lock().unwrap() = None;
        return;
    }
    let started = STARTED.lock().unwrap().unwrap_or_else(Instant::now);
    if !WAS_MOUNTED.load(Ordering::Relaxed) {
        if started.elapsed() > Duration::from_secs(15) {
            exit("PC did not accept the USB audio device");
        }
        return;
    }
    let mut since = UNMOUNTED_SINCE.lock().unwrap();
    let t = *since.get_or_insert_with(Instant::now);
    if t.elapsed() > Duration::from_secs(2) {
        exit("USB cable unplugged");
    }
}

/// Микрофон платы (16 кГц моно) - для ПК, пока режим включён.
pub fn feed_mic(samples: &[i16]) {
    if !is_on() {
        return;
    }
    let mut m = MIC.lock().unwrap();
    m.extend(samples.iter().copied());
    let extra = m.len().saturating_sub(MIC_CAP);
    m.drain(..extra);
}

/// ПК -> динамик.
unsafe extern "C" fn output_cb(buf: *mut u8, len: usize, _ctx: *mut core::ffi::c_void) -> sys::esp_err_t {
    // часы ПК и платы чуть расходятся - буфер медленно растёт; задержку держим
    // до 250 мс, лишний кусок в 10 мс выбрасываем изредка, а не упираемся в 2 с
    RX_BYTES.fetch_add(len as u32, Ordering::Relaxed);
    if speaker::queued() >= 4_000 {
        DROPPED.fetch_add(len as u32, Ordering::Relaxed);
    }
    if !buf.is_null() && len > 0 && !EXITING.load(Ordering::Relaxed) && speaker::queued() < 4_000 {
        speaker::push_pcm(core::slice::from_raw_parts(buf, len));
    }
    sys::ESP_OK
}

/// Микрофоны -> ПК: сколько просят; не накопилось - добиваем тишиной.
unsafe extern "C" fn input_cb(
    buf: *mut u8,
    len: usize,
    bytes_read: *mut usize,
    _ctx: *mut core::ffi::c_void,
) -> sys::esp_err_t {
    if buf.is_null() {
        return sys::ESP_FAIL;
    }
    let out = core::slice::from_raw_parts_mut(buf, len);
    let mut m = MIC.lock().unwrap();
    for pair in out.chunks_exact_mut(2) {
        let s = m.pop_front().unwrap_or(0);
        pair.copy_from_slice(&s.to_le_bytes());
    }
    if !bytes_read.is_null() {
        *bytes_read = len;
    }
    sys::ESP_OK
}

/// Громкость Windows (0..100) - громкость динамика платы.
unsafe extern "C" fn volume_cb(volume: u32, _ctx: *mut core::ffi::c_void) {
    speaker::set_volume(volume.min(100) as u8);
}

/// «Звук выключен» в Windows.
unsafe extern "C" fn mute_cb(mute: u32, _ctx: *mut core::ffi::c_void) {
    if mute != 0 {
        VOL_BEFORE_MUTE.store(speaker::volume(), Ordering::Relaxed);
        speaker::set_volume(0);
    } else {
        let v = VOL_BEFORE_MUTE.load(Ordering::Relaxed);
        speaker::set_volume(if v == 0 { 60 } else { v });
    }
}
