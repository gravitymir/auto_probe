//! Сервер площадки для модулей auto_probe (гараж, локальная сеть).
//!
//!   cargo run --release            -> слушает 0.0.0.0:7600
//!
//! Модуль (сейчас Voice-Unit, firmware/voiceunit-test):
//!   ws://.../ws?id=...  - постоянное соединение WebSocket:
//!       модуль -> сервер  текст {"type":"telemetry",...} раз в 1 с и сразу при событиях;
//!                         текст {"type":"rec","state":"start"|"stop"} - запись по голосу;
//!                         двоичные кадры - звук записи: моно, 8 кГц, μ-law;
//!       сервер -> модуль  {"type":"cmd","led":...}, {"type":"cfg","vad":..,"start":..,...}.
//!   GET  /ping, POST /telemetry - старый обмен опросом (оставлен для совместимости).
//! Человек:
//!   GET  /              - страница: модули, кнопки, живой звук, записи;
//!   ws://.../live       - события записи и звук для страницы;
//!   GET  /devices       - модули в JSON;
//!   GET  /cmd?id=..&led=on|off|blink
//!   GET  /cfg?id=..&vad=1&start=15&stop=8&hang=2500&gain=8
//!   GET  /recordings, /rec/<файл>.wav - записи (папка recordings рядом с Cargo.toml).

use std::collections::HashMap;
use std::fs::File;
use std::io::{ErrorKind, Read, Seek, SeekFrom, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::mpsc::{channel, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tungstenite::{Message, WebSocket};

const ADDR: &str = "0.0.0.0:7600";
const REC_DIR: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/recordings");

struct Device {
    ip: String,
    last: Instant,
    json: String,
    count: u64,
    /// команда для модуля на опросе (старый обмен)
    pending: Option<String>,
    /// живое WebSocket-соединение: команды уходят сразу
    link: Option<Sender<String>>,
}

type Devices = Arc<Mutex<HashMap<String, Device>>>;

/// Открытые страницы (ws://.../live): им уходят события записи и звук.
static PAGES: Mutex<Vec<Sender<Message>>> = Mutex::new(Vec::new());

fn main() {
    let _ = std::fs::create_dir_all(REC_DIR);
    let listener = TcpListener::bind(ADDR).unwrap_or_else(|e| panic!("bind {ADDR}: {e}"));
    println!("autoprobe-server: http://localhost:7600  (модули: ws://<этот ПК>:7600/ws)");
    println!("записи: {REC_DIR}");
    let devices: Devices = Arc::new(Mutex::new(HashMap::new()));
    for conn in listener.incoming().flatten() {
        let devices = devices.clone();
        std::thread::spawn(move || {
            // WebSocket или обычный HTTP - смотрим первую строку, не забирая её из сокета
            let mut peek = [0u8; 256];
            let n = conn.peek(&mut peek).unwrap_or(0);
            let first = String::from_utf8_lossy(&peek[..n]).lines().next().unwrap_or("").to_string();
            let r = if first.starts_with("GET /ws") {
                ws_device(conn, &devices, &first)
            } else if first.starts_with("GET /live") {
                ws_page(conn)
            } else {
                handle(conn, &devices)
            };
            if let Err(e) = r {
                eprintln!("{} connection: {e}", now());
            }
        });
    }
}

fn broadcast(m: Message) {
    PAGES.lock().unwrap().retain(|tx| tx.send(m.clone()).is_ok());
}

/// Записать посылку модуля и вывести строку в консоль.
fn update(devices: &Devices, id: &str, peer: &str, body: &str) -> Option<String> {
    let mut d = devices.lock().unwrap();
    let dev = d.entry(id.to_string()).or_insert_with(|| {
        println!("{} NEW device {id} ({peer})", now());
        Device { ip: peer.to_string(), last: Instant::now(), json: String::new(), count: 0, pending: None, link: None }
    });
    let changed = field(&dev.json, "led") != field(body, "led")
        || field(&dev.json, "boot_presses") != field(body, "boot_presses");
    dev.ip = peer.to_string();
    dev.last = Instant::now();
    dev.json = body.to_string();
    dev.count += 1;
    // в консоль - каждая 10-я посылка и все, где что-то поменялось
    if changed || dev.count % 10 == 1 {
        println!(
            "{} {id} {peer}  rssi {}  mic L {} R {}  фон L {} R {}  BOOT x{}  led {}  up {}s",
            now(),
            field(body, "rssi").unwrap_or("?"),
            field(body, "mic_l_db").unwrap_or("?"),
            field(body, "mic_r_db").unwrap_or("?"),
            field(body, "floor_l").unwrap_or("?"),
            field(body, "floor_r").unwrap_or("?"),
            field(body, "boot_presses").unwrap_or("?"),
            field(body, "led").unwrap_or("?").trim_matches('"'),
            field(body, "uptime").unwrap_or("?"),
        );
    }
    dev.pending.take()
}

/// Запись в WAV: μ-law с модуля раскладываем в 16 бит - так файл играет везде.
struct Wav {
    f: File,
    bytes: u32,
    name: String,
}

impl Wav {
    fn create(id: &str) -> std::io::Result<Self> {
        let name = format!("{}_{id}.wav", stamp());
        let mut f = File::create(PathBuf::from(REC_DIR).join(&name))?;
        f.write_all(&wav_header(0))?;
        Ok(Wav { f, bytes: 0, name })
    }
    fn push(&mut self, ulaw: &[u8]) -> std::io::Result<()> {
        let mut b = Vec::with_capacity(ulaw.len() * 2);
        for &u in ulaw {
            b.extend_from_slice(&ulaw_dec(u).to_le_bytes());
        }
        self.f.write_all(&b)?;
        self.bytes += b.len() as u32;
        Ok(())
    }
    fn finish(mut self) -> std::io::Result<(String, f32)> {
        self.f.seek(SeekFrom::Start(0))?;
        self.f.write_all(&wav_header(self.bytes))?;
        Ok((self.name, self.bytes as f32 / 16000.0))
    }
}

fn wav_header(data: u32) -> Vec<u8> {
    let mut h = Vec::with_capacity(44);
    h.extend_from_slice(b"RIFF");
    h.extend_from_slice(&(36 + data).to_le_bytes());
    h.extend_from_slice(b"WAVEfmt ");
    h.extend_from_slice(&16u32.to_le_bytes());
    h.extend_from_slice(&1u16.to_le_bytes()); // PCM
    h.extend_from_slice(&1u16.to_le_bytes()); // моно
    h.extend_from_slice(&8000u32.to_le_bytes());
    h.extend_from_slice(&16000u32.to_le_bytes());
    h.extend_from_slice(&2u16.to_le_bytes());
    h.extend_from_slice(&16u16.to_le_bytes());
    h.extend_from_slice(b"data");
    h.extend_from_slice(&data.to_le_bytes());
    h
}

/// G.711 μ-law -> 16 бит.
fn ulaw_dec(u: u8) -> i16 {
    let u = !u;
    let exp = ((u >> 4) & 7) as i32;
    let s = ((((u & 0x0F) as i32) << 3) + 0x84) << exp;
    (if u & 0x80 != 0 { 0x84 - s } else { s - 0x84 }) as i16
}

/// Постоянное соединение с модулем.
fn ws_device(c: TcpStream, devices: &Devices, first_line: &str) -> std::io::Result<()> {
    let peer = c.peer_addr().map(|a| a.ip().to_string()).unwrap_or_default();
    let target = first_line.split(' ').nth(1).unwrap_or("");
    let id = target.split_once('?').and_then(|(_, q)| param(q, "id")).unwrap_or(&peer).to_string();
    let mut ws: WebSocket<TcpStream> = tungstenite::accept(c).map_err(io_err)?;
    ws.get_mut().set_read_timeout(Some(Duration::from_millis(20)))?;
    let (tx, rx) = channel::<String>();
    {
        let mut d = devices.lock().unwrap();
        let dev = d.entry(id.clone()).or_insert_with(|| Device {
            ip: peer.clone(),
            last: Instant::now(),
            json: String::new(),
            count: 0,
            pending: None,
            link: None,
        });
        dev.link = Some(tx);
    }
    println!("{} WS  {id} connected ({peer})", now());
    let mut wav: Option<Wav> = None;
    let mut audio_prefix = vec![id.len() as u8];
    audio_prefix.extend_from_slice(id.as_bytes());
    let result = loop {
        // команды со страницы - сразу в модуль
        let mut send_err = None;
        while let Ok(cmd) = rx.try_recv() {
            println!("{} -> {id}: {cmd}", now());
            if let Err(e) = ws.send(Message::text(cmd)) {
                send_err = Some(e);
                break;
            }
        }
        if let Some(e) = send_err {
            break Err(io_err(e));
        }
        match ws.read() {
            Ok(Message::Text(t)) => {
                let t = t.as_str();
                if t.contains("\"type\":\"rec\"") {
                    if t.contains("\"state\":\"start\"") {
                        if let Some(w) = wav.take() {
                            let _ = w.finish();
                        }
                        wav = Wav::create(&id).ok();
                        println!(
                            "{} REC {id} start  (уровень L {} R {}, фон L {} R {})",
                            now(),
                            field(t, "l_db").unwrap_or("?"),
                            field(t, "r_db").unwrap_or("?"),
                            field(t, "floor_l").unwrap_or("?"),
                            field(t, "floor_r").unwrap_or("?")
                        );
                        broadcast(Message::text(format!("{{\"type\":\"rec\",\"id\":\"{id}\",\"state\":\"start\"}}")));
                    } else if let Some(w) = wav.take() {
                        let (name, secs) = w.finish().unwrap_or_default();
                        println!("{} REC {id} stop   {secs:.1} с -> {name}", now());
                        broadcast(Message::text(format!(
                            "{{\"type\":\"rec\",\"id\":\"{id}\",\"state\":\"stop\",\"file\":\"{name}\",\"secs\":{secs:.1}}}"
                        )));
                    }
                } else {
                    update(devices, &id, &peer, t);
                }
            }
            Ok(Message::Binary(b)) => {
                if let Some(w) = wav.as_mut() {
                    let _ = w.push(&b);
                }
                let mut m = audio_prefix.clone();
                m.extend_from_slice(&b);
                broadcast(Message::binary(m));
            }
            Ok(Message::Close(_)) => break Ok(()),
            Ok(_) => {}
            Err(tungstenite::Error::Io(e)) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {}
            Err(e) => break Err(io_err(e)),
        }
        // модуль шлёт раз в секунду: 10 с тишины - соединение мёртвое
        if devices.lock().unwrap().get(&id).map(|d| d.last.elapsed() > Duration::from_secs(10)).unwrap_or(true) {
            break Err(std::io::Error::new(ErrorKind::TimedOut, "no data for 10 s"));
        }
    };
    if let Some(w) = wav.take() {
        let _ = w.finish();
    }
    if let Some(dev) = devices.lock().unwrap().get_mut(&id) {
        dev.link = None;
    }
    println!("{} WS  {id} disconnected", now());
    result
}

/// Страница: получает события записи и звук.
fn ws_page(c: TcpStream) -> std::io::Result<()> {
    let mut ws: WebSocket<TcpStream> = tungstenite::accept(c).map_err(io_err)?;
    ws.get_mut().set_read_timeout(Some(Duration::from_millis(1)))?;
    let (tx, rx) = channel::<Message>();
    PAGES.lock().unwrap().push(tx);
    let mut last = Instant::now();
    loop {
        match rx.recv_timeout(Duration::from_millis(200)) {
            Ok(m) => {
                ws.send(m).map_err(io_err)?;
                last = Instant::now();
            }
            Err(RecvTimeoutError::Timeout) => {
                if last.elapsed() > Duration::from_secs(10) {
                    ws.send(Message::Ping(Vec::new().into())).map_err(io_err)?;
                    last = Instant::now();
                }
            }
            Err(RecvTimeoutError::Disconnected) => return Ok(()),
        }
        match ws.read() {
            Ok(Message::Close(_)) => return Ok(()),
            Ok(_) => {}
            Err(tungstenite::Error::Io(e)) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {}
            Err(e) => return Err(io_err(e)),
        }
    }
}

fn io_err(e: impl std::fmt::Display) -> std::io::Error {
    std::io::Error::new(ErrorKind::Other, e.to_string())
}

fn handle(mut c: TcpStream, devices: &Devices) -> std::io::Result<()> {
    let peer = c.peer_addr().map(|a| a.ip().to_string()).unwrap_or_default();
    c.set_read_timeout(Some(Duration::from_secs(5)))?;
    // заголовок до пустой строки, затем тело по Content-Length
    let mut buf = Vec::new();
    let mut tmp = [0u8; 2048];
    let head_end = loop {
        let n = c.read(&mut tmp)?;
        if n == 0 {
            return Ok(());
        }
        buf.extend_from_slice(&tmp[..n]);
        if let Some(i) = find(&buf, b"\r\n\r\n") {
            break i + 4;
        }
        if buf.len() > 64 * 1024 {
            return Ok(());
        }
    };
    let head = String::from_utf8_lossy(&buf[..head_end]).to_string();
    let len = head
        .lines()
        .find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().to_string()))
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(0);
    while buf.len() < head_end + len {
        let n = c.read(&mut tmp)?;
        if n == 0 {
            break;
        }
        buf.extend_from_slice(&tmp[..n]);
    }
    let body = String::from_utf8_lossy(&buf[head_end..]).to_string();
    let mut first = head.lines().next().unwrap_or("").split(' ');
    let (method, target) = (first.next().unwrap_or(""), first.next().unwrap_or("/"));
    let (path, query) = target.split_once('?').unwrap_or((target, ""));

    match (method, path) {
        ("GET", "/ping") => {
            println!("{} PING from {} ({peer})", now(), param(query, "id").unwrap_or("?"));
            reply(&mut c, "text/plain", "pong")
        }
        ("POST", "/telemetry") => {
            let id = field(&body, "id").map(|v| v.trim_matches('"').to_string()).unwrap_or_else(|| peer.clone());
            let resp = match update(devices, &id, &peer, &body) {
                Some(led) => format!("{{\"ok\":true,\"led\":\"{led}\"}}"),
                None => "{\"ok\":true}".to_string(),
            };
            reply(&mut c, "application/json", &resp)
        }
        ("GET", "/cmd") => {
            let (id, led) = (param(query, "id").unwrap_or(""), param(query, "led").unwrap_or(""));
            let answer = if !matches!(led, "on" | "off" | "blink") {
                "unknown command"
            } else {
                let mut d = devices.lock().unwrap();
                match d.get_mut(id) {
                    None => "unknown device",
                    Some(dev) => match dev.link.as_ref().map(|l| l.send(format!("{{\"type\":\"cmd\",\"led\":\"{led}\"}}"))) {
                        Some(Ok(())) => "sent",
                        _ => {
                            dev.pending = Some(led.to_string());
                            "queued"
                        }
                    },
                }
            };
            reply(&mut c, "text/plain", answer)
        }
        ("GET", "/cfg") => {
            let id = param(query, "id").unwrap_or("");
            // только числовые поля из списка - в модуль уходит чистый JSON
            let mut parts = vec!["\"type\":\"cfg\"".to_string()];
            for k in ["vad", "start", "stop", "hang", "gain"] {
                if let Some(v) = param(query, k).and_then(|v| v.parse::<f64>().ok()) {
                    parts.push(format!("\"{k}\":{v}"));
                }
            }
            let msg = format!("{{{}}}", parts.join(","));
            let d = devices.lock().unwrap();
            let answer = match d.get(id).and_then(|dev| dev.link.as_ref()) {
                Some(l) if l.send(msg).is_ok() => "sent",
                _ => "device offline",
            };
            reply(&mut c, "text/plain", answer)
        }
        ("GET", "/devices") => {
            let d = devices.lock().unwrap();
            let mut ids: Vec<_> = d.keys().cloned().collect();
            ids.sort();
            let items: Vec<String> = ids
                .iter()
                .map(|id| {
                    let dev = &d[id];
                    format!(
                        "{{\"id\":\"{id}\",\"ip\":\"{}\",\"age\":{},\"count\":{},\"ws\":{},\"data\":{}}}",
                        dev.ip,
                        dev.last.elapsed().as_secs(),
                        dev.count,
                        dev.link.is_some(),
                        if dev.json.trim().starts_with('{') { dev.json.as_str() } else { "null" }
                    )
                })
                .collect();
            reply(&mut c, "application/json", &format!("[{}]", items.join(",")))
        }
        ("GET", "/recordings") => {
            let mut list: Vec<(String, u64)> = std::fs::read_dir(REC_DIR)
                .map(|rd| {
                    rd.flatten()
                        .filter_map(|e| {
                            let name = e.file_name().to_string_lossy().to_string();
                            let size = e.metadata().ok()?.len();
                            name.ends_with(".wav").then_some((name, size))
                        })
                        .collect()
                })
                .unwrap_or_default();
            list.sort_by(|a, b| b.0.cmp(&a.0));
            let items: Vec<String> = list
                .iter()
                .take(50)
                .map(|(n, s)| format!("{{\"name\":\"{n}\",\"secs\":{:.1}}}", s.saturating_sub(44) as f64 / 16000.0))
                .collect();
            reply(&mut c, "application/json", &format!("[{}]", items.join(",")))
        }
        ("GET", p) if p.starts_with("/rec/") => {
            let name = &p[5..];
            let safe = !name.is_empty() && name.chars().all(|ch| ch.is_ascii_alphanumeric() || "-_.".contains(ch));
            match std::fs::read(PathBuf::from(REC_DIR).join(name)) {
                Ok(data) if safe => {
                    write!(
                        c,
                        "HTTP/1.1 200 OK\r\nContent-Type: audio/wav\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        data.len()
                    )?;
                    c.write_all(&data)
                }
                _ => not_found(&mut c),
            }
        }
        ("GET", "/") => reply(&mut c, "text/html; charset=utf-8", PAGE),
        _ => not_found(&mut c),
    }
}

fn not_found(c: &mut TcpStream) -> std::io::Result<()> {
    let msg = "not found";
    write!(c, "HTTP/1.1 404 Not Found\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{msg}", msg.len())
}

fn reply(c: &mut TcpStream, ctype: &str, body: &str) -> std::io::Result<()> {
    write!(
        c,
        "HTTP/1.1 200 OK\r\nContent-Type: {ctype}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    hay.windows(needle.len()).position(|w| w == needle)
}

fn param<'a>(query: &'a str, key: &str) -> Option<&'a str> {
    query.split('&').find_map(|kv| kv.split_once('=').filter(|(k, _)| *k == key).map(|(_, v)| v))
}

/// Значение поля плоского JSON как текст (строка - в кавычках).
fn field<'a>(json: &'a str, key: &str) -> Option<&'a str> {
    let i = json.find(&format!("\"{key}\":"))? + key.len() + 3;
    let rest = json[i..].trim_start();
    let end = if rest.starts_with('"') {
        rest[1..].find('"').map(|e| e + 2)?
    } else {
        rest.find([',', '}']).unwrap_or(rest.len())
    };
    Some(rest[..end].trim())
}

fn epoch() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

/// Время UTC (в Ирландии зимой совпадает с местным).
fn now() -> String {
    let s = epoch();
    format!("{:02}:{:02}:{:02}", (s / 3600) % 24, (s / 60) % 60, s % 60)
}

/// "2026-11-11_19-30-05" для имени файла.
fn stamp() -> String {
    let s = epoch();
    // дни от 1970-01-01 -> дата (алгоритм Хиннанта)
    let z = (s / 86400) as i64 + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!("{y:04}-{m:02}-{d:02}_{:02}-{:02}-{:02}", (s / 3600) % 24, (s / 60) % 60, s % 60)
}

const PAGE: &str = r#"<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>auto_probe server</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--fg:#1d2330;--mut:#6b7280;--acc:#2563eb;--ok:#16a34a;--bad:#dc2626;--rec:#e11d48;--line:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1b2027;--fg:#e6e8eb;--mut:#9aa3ad;--acc:#60a5fa;--ok:#4ade80;--bad:#f87171;--rec:#fb7185;--line:#2a313b}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}h1{font-size:20px}
h2{font-size:13px;margin:12px 0 6px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.card{background:var(--card);border-radius:12px;padding:14px;margin-bottom:12px}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.mut{color:var(--mut);font-size:13px}.ok{color:var(--ok)}.bad{color:var(--bad)}
.recon{color:var(--rec);font-weight:600}
table{border-collapse:collapse;margin:8px 0;font:12px ui-monospace,monospace}
td{padding:1px 12px 1px 0;border-bottom:1px solid var(--line)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:6px}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--acc)}
button.on{background:var(--acc);border-color:var(--acc);color:#fff}
label{font-size:13px;color:var(--mut)}
input[type=number]{width:64px;font:inherit;padding:5px 6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.recs div{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:4px 0;border-bottom:1px solid var(--line)}
.recs span{font:12px ui-monospace,monospace;min-width:230px}
audio{height:32px}
details summary{cursor:pointer;color:var(--mut);font-size:13px;margin-top:8px}
</style></head><body><main>
<h1>auto_probe — сервер гаража</h1>
<div class="card"><div class="row"><button id="live">🔊 Слушать вживую</button>
<span class="mut" id="lst">звук записи идёт на страницу, только когда кто-то говорит</span></div></div>
<div id="empty" class="mut">модулей пока нет — ждём первую посылку</div>
<div id="list"></div>
<div class="card"><h2>Записи</h2><div class="recs" id="recs"><span class="mut">пока нет</span></div></div>
</main><script>
// Карточка модуля создаётся один раз, дальше обновляются только значения:
// кнопки и поля не пересоздаются, клик и ввод не теряются.
const cards={}, wait={}, inited={};
const LED={on:'Вкл',off:'Выкл',blink:'Мигать'};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $=id=>document.getElementById(id);
function card(id){
  if(cards[id])return cards[id];
  const el=document.createElement('div');el.className='card';
  el.innerHTML='<div class="top"><b>'+esc(id)+'</b><span class="st"></span></div>'+
    '<div class="row"><span>Светодиод:</span>'+Object.keys(LED).map(m=>'<button data-m="'+m+'">'+LED[m]+'</button>').join('')+
    '<span class="mut cmd"></span></div>'+
    '<h2>Запись по голосу</h2><div class="row"><span class="rec">—</span><span class="mut lvl"></span></div>'+
    '<div class="row"><label><input type="checkbox" class="vad"> включена</label>'+
    '<label>старт: фон + <input type="number" class="v_start" min="3" max="60"> дБ</label>'+
    '<label>тишина: фон + <input type="number" class="v_stop" min="1" max="60"> дБ</label>'+
    '<label>стоп после <input type="number" class="v_hang" min="0.3" max="20" step="0.1"> с</label>'+
    '<label>усиление ×<input type="number" class="v_gain" min="1" max="256"></label>'+
    '<button class="apply">Применить</button><span class="mut cfgst"></span></div>'+
    '<details><summary>все данные модуля</summary><table></table></details>';
  el.querySelectorAll('[data-m]').forEach(b=>b.addEventListener('click',()=>send(id,b.dataset.m)));
  el.querySelector('.apply').addEventListener('click',()=>cfg(id));
  $('list').appendChild(el);
  return cards[id]=el;
}
async function send(id,m){
  const c=card(id).querySelector('.cmd');
  try{const r=await (await fetch('/cmd?id='+encodeURIComponent(id)+'&led='+m)).text();
    if(r==='sent'||r==='queued'){wait[id]=m;c.textContent='отправлено «'+LED[m]+'», ждём подтверждения…';}
    else c.textContent='ошибка: '+r;
  }catch(e){c.textContent='нет связи с сервером';}
}
async function cfg(id){
  const el=card(id),v=k=>el.querySelector('.'+k);
  const q='id='+encodeURIComponent(id)+'&vad='+(v('vad').checked?1:0)+'&start='+v('v_start').value+
    '&stop='+v('v_stop').value+'&hang='+Math.round(v('v_hang').value*1000)+'&gain='+v('v_gain').value;
  const r=await (await fetch('/cfg?'+q)).text();
  el.querySelector('.cfgst').textContent=r==='sent'?'отправлено ✓':'ошибка: '+r;
}
async function poll(){try{
  const d=await (await fetch('/devices')).json();
  $('empty').style.display=d.length?'none':'';
  for(const x of d){
    const el=card(x.id), live=x.age<15, v=x.data||{};
    const st=el.querySelector('.st');
    st.className='st '+(live?'ok':'bad');
    st.textContent=(live?(x.ws?'на связи · WebSocket':'на связи · опрос'):'молчит')+' · '+x.age+' с назад · посылок '+x.count+' · '+x.ip;
    el.querySelectorAll('[data-m]').forEach(b=>b.classList.toggle('on',b.dataset.m===v.led));
    if(wait[x.id]&&wait[x.id]===v.led){el.querySelector('.cmd').textContent='выполнено ✓';delete wait[x.id];}
    const rec=el.querySelector('.rec');
    rec.className='rec '+(v.rec?'recon':'mut');
    rec.textContent=v.rec?'● идёт запись':(v.vad?'тишина, ждём голос':'выключена');
    if(v.floor_l!==undefined)el.querySelector('.lvl').textContent='MK1 '+v.mic_l_db+' дБ (фон '+v.floor_l+') · MK2 '+v.mic_r_db+' дБ (фон '+v.floor_r+') · записей '+v.recs;
    if(!inited[x.id]&&v.v_start!==undefined){inited[x.id]=1;
      el.querySelector('.vad').checked=!!v.vad;el.querySelector('.v_start').value=v.v_start;el.querySelector('.v_stop').value=v.v_stop;
      el.querySelector('.v_hang').value=v.v_hang/1000;el.querySelector('.v_gain').value=v.v_gain;}
    el.querySelector('table').innerHTML=Object.entries(v).map(([k,val])=>'<tr><td>'+esc(k)+'</td><td>'+esc(val)+'</td></tr>').join('');
  }
}catch(e){}}
async function recs(){try{
  const r=await (await fetch('/recordings')).json();
  if(!r.length)return;
  const box=$('recs'), have=new Set([...box.querySelectorAll('[data-n]')].map(e=>e.dataset.n));
  if(r.length===have.size&&r.every(x=>have.has(x.name)))return;
  box.innerHTML=r.map(x=>'<div data-n="'+esc(x.name)+'"><span>'+esc(x.name)+' · '+x.secs+' с</span>'+
    '<audio controls preload="none" src="/rec/'+encodeURIComponent(x.name)+'"></audio></div>').join('');
}catch(e){}}
// Живой звук: μ-law 8 кГц с модуля -> Web Audio, куски встают в очередь друг за другом.
const ULAW=new Float32Array(256);
for(let i=0;i<256;i++){const u=~i&255,e=(u>>4)&7,s=((((u&15)<<3)+0x84)<<e)-0x84;ULAW[i]=(u&128?-s:s)/32768;}
let ctx=null,next=0;
$('live').onclick=()=>{
  if(ctx){ctx.close();ctx=null;$('live').classList.remove('on');$('lst').textContent='живой звук выключен';return;}
  ctx=new AudioContext();next=0;$('live').classList.add('on');$('lst').textContent='слушаем: звук появится, когда модуль начнёт запись';
};
function play(bytes){
  if(!ctx)return;
  const buf=ctx.createBuffer(1,bytes.length,8000),ch=buf.getChannelData(0);
  for(let i=0;i<bytes.length;i++)ch[i]=ULAW[bytes[i]];
  const src=ctx.createBufferSource();src.buffer=buf;src.connect(ctx.destination);
  const t=ctx.currentTime;if(next<t+0.05||next>t+1)next=t+0.15;
  src.start(next);next+=buf.duration;
}
function connect(){
  const ws=new WebSocket('ws://'+location.host+'/live');ws.binaryType='arraybuffer';
  ws.onmessage=e=>{
    if(typeof e.data==='string'){const m=JSON.parse(e.data);if(m.type==='rec'){poll();if(m.state==='stop')setTimeout(recs,300);}return;}
    const b=new Uint8Array(e.data);play(b.subarray(1+b[0]));
  };
  ws.onclose=()=>setTimeout(connect,2000);
}
connect();setInterval(poll,500);poll();setInterval(recs,10000);recs();
</script></body></html>
"#;
