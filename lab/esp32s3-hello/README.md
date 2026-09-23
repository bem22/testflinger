# ESP32-S3-Zero USB serial hello world

Minimal ESP-IDF application for the selected ESP32-S3-Zero with 4 MB embedded
flash and 2 MB PSRAM. The latter is deliberately disabled for this smoke test.
USB Serial/JTAG is the primary console, not UART0 or USB-OTG/TinyUSB.
No Wi-Fi/BLE, GPIO peripherals, or low-power modes are enabled by this app.

It prints a hello line and a versioned pass marker every second:

```text
Hello world from ESP32-S3-Zero!
TF_ESP32S3_HELLO_V1_PASS mac=e8:f6:0a:81:84:84 seq=0
```

The MAC is read from the device, not hard-coded into the firmware. Repeated
output allows a serial reader to attach after reset without missing the marker.
This marker proves application execution and console output, not comprehensive
hardware correctness.

## Build

ESP-IDF v5.5.3 is selected. With its environment activated, run `idf.py build`
in this directory. CMake fixes the target to `esp32s3`; defaults select DIO,
40 MHz flash, 4 MB flash, and a single factory application partition.

On the current laptop, `bash build-local.sh` uses the verified existing local
image by its immutable ID, with networking disabled. This image is not published
by this project; elsewhere activate an ESP-IDF v5.5.3 environment first.
See [build validation](BUILD-VALIDATION.md) for the tested toolchain and hashes.

The build produces `build/flasher_args.json`, `build/flash_args`, the bootloader,
partition table, and application binary. Use the generated mapping; do not
assume a standalone application can be flashed at address zero.

Build output and generated sdkconfig are ignored by Git. The firmware is kept
separate from agent configuration and from the upstream ARM64 contribution.
The currently deployed identity job is unchanged by this branch.

## Flashing boundary

The user authorized replacement of the installed firmware without a backup.
No flashing is performed by building this project. Before a flash job is run:

- Check that the connected target is ESP32-S3 with the selected MAC.
- Validate the build-generated offsets and image hashes.
- Do not use whole-chip erase or security override flags.
- Use the verified `usb_reset` connection mode and a narrow serial mapping.
- Plan reset and serial-port reopening; USB re-enumeration remains unvalidated.

Flash/boot/serial capture through Testflinger is still pending.

Editor note: ESP-IDF headers/toolchains live inside the build container. Host
language-server diagnostics without that SDK configuration are not the compiler
result; the full firmware build has passed. Use a matching ESP-IDF development
environment for semantic editor support rather than adding fake headers.

