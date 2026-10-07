#![no_std]
#![no_main]

use defmt::info;
use embassy_executor::Spawner;
use embassy_stm32::gpio::{Level, Output, Speed};
use embassy_time::Timer;
use {defmt_rtt as _, panic_probe as _};

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_stm32::init(Default::default());
    info!("STM32H723ZG-CoreBoard blink: LED on PB0");

    let mut led = Output::new(p.PB0, Level::Low, Speed::Low);

    loop {
        led.set_high();
        info!("LED on");
        Timer::after_millis(500).await;
        led.set_low();
        info!("LED off");
        Timer::after_millis(500).await;
    }
}
