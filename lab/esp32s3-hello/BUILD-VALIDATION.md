# Build validation: 2026-09-23

Status: compiled successfully on the laptop; NOT yet flashed or tested on board.

- ESP-IDF: v5.5.3, commit `2c211b236707889e8400c4dc5644dd5c4ee071e0`.
- Existing local image: `ubx-freertos-esp-idf:v5.5.3`.
- Immutable local image ID:
  `sha256:7e26ff11c758e5b93cb8303cbe27a8e658ed362e89bbb798d4f8eeefc1e3a092`.
- Image is local/custom, not an assumed official image or portable registry digest.
- Build ran with networking disabled, as the host UID/GID, without device access.
- Target: ESP32-S3; primary console USB Serial/JTAG; no secondary console.
- Flash: DIO, 40 MHz, 4 MB; external PSRAM disabled.
- Application size: `0x2c090` (180368 bytes), inside a 1 MiB factory partition.
- Secure Boot and flash encryption are disabled in this build. This says nothing
  about existing board eFuses; do not bypass esptool's security checks.

## Generated flash layout and SHA-256

These offsets are from this build's `flasher_args.json`, not guessed defaults.
Paths below are relative to the build directory and the packaged archive root.

| Offset | File | SHA-256 |
| --- | --- | --- |
| `0x0` | bootloader/bootloader.bin | `54c6a1adcc051dade8ec13d606a0e694822bfcc27f3e874ce130953fd293b444` |
| `0x8000` | partition_table/partition-table.bin | `7f00b6c042a89b15b0cac534f82ed988caf29278ff5700b0c511eb1b5bb7c820` |
| `0x10000` | tf_s3_hello.bin | `fd0103dc39b517200b83ac294d5289d7bef98f9b227d8fdf7359290d0a7adfbb` |

Hashes describe this build, not a claim of bit-for-bit reproducibility. A rebuild
may embed different timestamps; validate/re-record hashes before flashing it.
The bootloader and app image metadata were checked with the SDK's esptool.

Local bundle: `build/esp32s3-hello-v1.tar.gz`, containing only the three binaries,
`flasher_args.json`, and `flash_args`. Archive SHA-256:
`c237b999de5a413cdcaed912d9aa81f3fffab3239e938e09bc31d18735234c57`.
The bundle remains local and ignored by Git; it has not been uploaded as a job
attachment or published as a release asset.

The generated flash command defaults to `default_reset`; for this board's
aliased USB serial interface, use the already verified `usb_reset` instead.
Do not execute generated flash commands blindly or flash the app at offset zero.

## Next validation

The user requested no backup and authorized firmware replacement. Still pending:
attachment upload, target identity verification, explicit flash programming,
reset into the app, port reopening, and capture of the repeating versioned marker.
The identity-only queue remains deployed and cannot flash this firmware by itself.
