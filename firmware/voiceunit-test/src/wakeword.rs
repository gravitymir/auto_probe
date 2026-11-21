//! Ключевое слово «Sophia» на плате: ESP-SR WakeNet9 (по образцу ATOMVoiceS3R).
//!
//! Модель - в разделе flash "model" (srmodels.bin, прошивается отдельно). AFE на
//! один канал ("M"): на вход - смесь двух микрофонов, 16 кГц, 16 бит. Подавление
//! эха не нужно: динамик в этой прошивке выключен.
//!
//! Всё это - небезопасный FFI в компонент esp-sr; привязки из esp_sr_bindings.h.

use anyhow::{bail, Result};
use esp_idf_svc::sys::esp_sr as sys;

pub struct WakeWord {
    handle: *const sys::esp_afe_sr_iface_t,
    data: *mut sys::esp_afe_sr_data_t,
    frame: usize,
}

// AFE живёт в одной задаче, указатели наружу не уходят.
unsafe impl Send for WakeWord {}

impl WakeWord {
    pub fn new() -> Result<Self> {
        unsafe {
            let models = sys::esp_srmodel_init(c"model".as_ptr());
            if models.is_null() || (*models).num <= 0 {
                bail!("no models in flash partition \"model\" (srmodels.bin not flashed?)");
            }
            let sophia = sys::esp_srmodel_filter(models, c"wn".as_ptr(), c"sophia".as_ptr());
            if sophia.is_null() {
                bail!("WakeNet model wn9_sophia_tts not in partition");
            }
            let cfg = sys::afe_config_init(
                c"M".as_ptr(),
                models,
                sys::afe_type_t_AFE_TYPE_SR,
                sys::afe_mode_t_AFE_MODE_HIGH_PERF,
            );
            if cfg.is_null() {
                bail!("afe_config_init returned null");
            }
            (*cfg).wakenet_init = true;
            (*cfg).aec_init = false;
            (*cfg).se_init = false;
            (*cfg).ns_init = false;
            (*cfg).vad_init = false;
            (*cfg).agc_init = false;
            (*cfg).wakenet_model_name = sophia;
            (*cfg).wakenet_model_name_2 = core::ptr::null_mut();

            let handle = sys::esp_afe_handle_from_config(cfg);
            if handle.is_null() {
                sys::afe_config_free(cfg);
                bail!("esp_afe_handle_from_config returned null");
            }
            let Some(create) = (*handle).create_from_config else {
                sys::afe_config_free(cfg);
                bail!("afe.create_from_config is null");
            };
            let data = create(cfg);
            sys::afe_config_free(cfg);
            if data.is_null() {
                bail!("afe create_from_config returned null");
            }
            let chunk = (*handle).get_feed_chunksize.map(|f| f(data)).unwrap_or(0) as usize;
            let ch = (*handle).get_feed_channel_num.map(|f| f(data)).unwrap_or(0) as usize;
            if chunk == 0 || ch == 0 {
                bail!("AFE feed size unknown (chunk {chunk}, channels {ch})");
            }
            log::info!("wake word: AFE ready, feed {chunk} x {ch}");
            Ok(Self { handle, data, frame: chunk * ch })
        }
    }

    /// Сколько отсчётов i16 подавать за раз в `process`.
    pub fn frame_len(&self) -> usize {
        self.frame
    }

    /// Один кадр ровно `frame_len()` отсчётов; true - «Sophia» услышана.
    pub fn process(&mut self, frame: &[i16]) -> bool {
        debug_assert_eq!(frame.len(), self.frame);
        unsafe {
            if let Some(feed) = (*self.handle).feed {
                feed(self.data, frame.as_ptr());
            }
            let Some(fetch) = (*self.handle).fetch else { return false };
            let res = fetch(self.data);
            !res.is_null() && (*res).wakeup_state == sys::wakenet_state_t_WAKENET_DETECTED
        }
    }
}

impl Drop for WakeWord {
    fn drop(&mut self) {
        unsafe {
            if let Some(destroy) = (*self.handle).destroy {
                destroy(self.data);
            }
        }
    }
}
