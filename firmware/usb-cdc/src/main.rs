#![no_std]
#![no_main]

use defmt::{info, panic};
use embassy_executor::Spawner;
use embassy_futures::join::join;
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_stm32::usb::{Driver, Instance};
use embassy_stm32::{bind_interrupts, peripherals, usb, Config};
use embassy_usb::class::cdc_acm::{CdcAcmClass, State};
use embassy_usb::driver::EndpointError;
use embassy_usb::Builder;
use {defmt_rtt as _, panic_probe as _};

bind_interrupts!(struct Irqs {
    OTG_HS => usb::InterruptHandler<peripherals::USB_OTG_HS>;
});

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let mut config = Config::default();
    {
        use embassy_stm32::rcc::*;
        config.rcc.hsi = Some(HSIPrescaler::DIV1);
        config.rcc.csi = true;
        config.rcc.hsi48 = Some(Hsi48Config { sync_from_usb: true });
        config.rcc.pll1 = Some(Pll {
            source: PllSource::HSI,
            prediv: PllPreDiv::DIV4,
            mul: PllMul::MUL50,
            divp: Some(PllDiv::DIV2),
            divq: None,
            divr: None,
        });
        config.rcc.sys = Sysclk::PLL1_P;
        config.rcc.ahb_pre = AHBPrescaler::DIV2;
        config.rcc.apb1_pre = APBPrescaler::DIV2;
        config.rcc.apb2_pre = APBPrescaler::DIV2;
        config.rcc.apb3_pre = APBPrescaler::DIV2;
        config.rcc.apb4_pre = APBPrescaler::DIV2;
        config.rcc.voltage_scale = VoltageScale::Scale1;
        config.rcc.mux.usbsel = mux::Usbsel::HSI48;
    }
    let p = embassy_stm32::init(config);
    info!("STM32H723ZG-CoreBoard USB-CDC console");

    let mut led = Output::new(p.PB0, Level::Low, Speed::Low);

    let mut ep_out_buffer = [0u8; 256];
    let mut usb_config = embassy_stm32::usb::Config::default();
    usb_config.vbus_detection = false;

    let driver = Driver::new_fs(
        p.USB_OTG_HS,
        Irqs,
        p.PA12,
        p.PA11,
        &mut ep_out_buffer,
        usb_config,
    );

    let mut config = embassy_usb::Config::new(0xc0de, 0xcafe);
    config.manufacturer = Some("auto_probe");
    config.product = Some("H723 CoreBoard console");
    config.serial_number = Some("0001");

    let mut config_descriptor = [0; 256];
    let mut bos_descriptor = [0; 256];
    let mut control_buf = [0; 64];

    let mut state = State::new();

    let mut builder = Builder::new(
        driver,
        config,
        &mut config_descriptor,
        &mut bos_descriptor,
        &mut [],
        &mut control_buf,
    );

    let mut class = CdcAcmClass::new(&mut builder, &mut state, 64);

    let mut usb = builder.build();
    let usb_fut = usb.run();

    let console_fut = async {
        loop {
            class.wait_connection().await;
            info!("host connected");
            let _ = console(&mut class, &mut led).await;
            info!("host disconnected");
        }
    };

    join(usb_fut, console_fut).await;
}

struct Disconnected {}

impl From<EndpointError> for Disconnected {
    fn from(val: EndpointError) -> Self {
        match val {
            EndpointError::BufferOverflow => panic!("buffer overflow"),
            EndpointError::Disabled => Disconnected {},
        }
    }
}

async fn console<'d, T: Instance + 'd>(
    class: &mut CdcAcmClass<'d, Driver<'d, T>>,
    led: &mut Output<'_>,
) -> Result<(), Disconnected> {
    let mut buf = [0u8; 64];
    let mut line = [0u8; 64];
    let mut len = 0usize;

    class
        .write_packet(b"auto_probe H723 console. commands: on, off, status\r\n")
        .await?;

    loop {
        let n = class.read_packet(&mut buf).await?;
        for &b in &buf[..n] {
            match b {
                b'\r' | b'\n' => {
                    if len > 0 {
                        let reply = run_command(&line[..len], led);
                        class.write_packet(reply).await?;
                        len = 0;
                    }
                }
                _ if len < line.len() => {
                    line[len] = b;
                    len += 1;
                }
                _ => len = 0, // overflow: drop the line
            }
        }
    }
}

fn run_command<'a>(cmd: &[u8], led: &mut Output<'_>) -> &'a [u8] {
    match cmd {
        b"on" => {
            led.set_high();
            info!("cmd: on");
            b"OK: LED on\r\n"
        }
        b"off" => {
            led.set_low();
            info!("cmd: off");
            b"OK: LED off\r\n"
        }
        b"status" => {
            if led.is_set_high() {
                b"LED is on\r\n"
            } else {
                b"LED is off\r\n"
            }
        }
        _ => b"ERR: unknown command (on, off, status)\r\n",
    }
}
