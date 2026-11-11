// Шаблон настроек площадки: скопировать в site.rs и вписать свои значения.
// site.rs в git не попадает (там пароль Wi-Fi).

pub const WIFI_SSID: &str = "my-network";
pub const WIFI_PASS: &str = "my-password";

/// Сервер в локальной сети.
pub const SERVER_HOST: &str = "192.168.1.100";
pub const SERVER_PORT: u16 = 7600;
