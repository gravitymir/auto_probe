// Привязки к ESP-SR для Rust (esp-idf-sys): esp_idf_svc::sys::esp_sr.
#include "esp_afe_config.h"    // afe_config_init, afe_config_t
#include "esp_afe_sr_models.h" // esp_afe_handle_from_config
#include "esp_afe_sr_iface.h"  // esp_afe_sr_iface_t: feed/fetch/...
#include "esp_wn_iface.h"      // WAKENET_DETECTED
#include "model_path.h"        // esp_srmodel_init, esp_srmodel_filter
