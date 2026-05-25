# Pi Runtime

This folder contains the Raspberry Pi runtime only.

It is responsible for:

- opening the Unicorn headset with the official Pi Zero W C API
- publishing a local LSL stream

## Architecture Requirement

Important:

- the Unicorn Pi library currently used here is `32-bit ARM`
- the recommended setup is a `32-bit Raspberry Pi OS` userspace

## Files

- `stream_unicorn_lsl.py`: starts Unicorn acquisition and publishes LSL
- `unicorn_capi_stream.py`: Unicorn C API -> LSL implementation
- `requirements.txt`: minimal Pi Python dependencies
- `vendor/unicorn_pi_zero_w_lib/`: required Unicorn shared library
- `deploy_to_pi.ps1`: deploys this runtime to the Pi

## Deploy

From the repo root on Windows:

```powershell
.\pi_runtime\deploy_to_pi.ps1 -PiHost <pi-hostname-or-ip> -PiUser <pi-user>
```

## Run On The Pi

Start Unicorn acquisition:

```bash
cd ~/classroom-neurofeedback-pi
. .venv/bin/activate
python3 stream_unicorn_lsl.py --lsl-name Unicorn --single-channel --channel-name "EEG 1"
```