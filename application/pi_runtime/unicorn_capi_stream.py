#!/usr/bin/env python3
"""Official Unicorn C API variant: libunicorn.so -> LSL."""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path

from pylsl import StreamInfo, StreamOutlet


FSAMPLE = 250
SERIAL_LEN = 14
DEFAULT_LIB_PATH = (
    Path(__file__).resolve().parent
    / "vendor"
    / "unicorn_pi_zero_w_lib"
    / "libunicorn.so"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unicorn C API -> LSL")
    parser.add_argument("--lib-path", default=str(DEFAULT_LIB_PATH), help="Path to libunicorn.so")
    parser.add_argument("--serial", default="", help="Exact Unicorn serial to open; default first discovered")
    parser.add_argument("--lsl-name", default="Unicorn", help="LSL stream name")
    parser.add_argument("--student-name", default="", help="Student name to publish in LSL metadata")
    parser.add_argument("--lsl-type", default="EEG", help="LSL stream type")
    parser.add_argument("--single-channel", action="store_true", help="Stream one channel only")
    parser.add_argument(
        "--channel-name",
        default="EEG 1",
        help='Channel name in Unicorn config, e.g. "EEG 1", "Battery Level", "Counter"',
    )
    parser.add_argument("--test-signal", action="store_true", help="Start in Unicorn test-signal mode")
    parser.add_argument("--frame-length", type=int, default=1, help="Scans per API read call")
    return parser.parse_args()


def check_ok(code: int, lib: ctypes.CDLL, context: str) -> None:
    if code != 0:
        try:
            msg = lib.UNICORN_GetLastErrorText()
            detail = msg.decode("utf-8", errors="replace") if msg else ""
        except Exception:
            detail = ""
        raise RuntimeError(f"{context} failed with code {code}. {detail}")


def decode_serial(raw: bytes) -> str:
    return raw.decode("ascii", errors="ignore").rstrip("\x00").strip()


def load_lib(path: str) -> ctypes.CDLL:
    if not Path(path).exists():
        raise FileNotFoundError(
            "libunicorn.so was not found at "
            f"{path}. Copy the Unicorn Pi Zero W library folder onto the Pi "
            "or pass --lib-path to the correct location."
        )
    lib = ctypes.CDLL(path)
    lib.UNICORN_GetLastErrorText.restype = ctypes.c_char_p
    lib.UNICORN_GetApiVersion.restype = ctypes.c_float

    lib.UNICORN_GetAvailableDevices.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_int32,
    ]
    lib.UNICORN_OpenDevice.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64)]
    lib.UNICORN_CloseDevice.argtypes = [ctypes.POINTER(ctypes.c_uint64)]
    lib.UNICORN_StartAcquisition.argtypes = [ctypes.c_uint64, ctypes.c_int32]
    lib.UNICORN_StopAcquisition.argtypes = [ctypes.c_uint64]
    lib.UNICORN_GetNumberOfAcquiredChannels.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint32)]
    lib.UNICORN_GetChannelIndex.argtypes = [ctypes.c_uint64, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32)]
    lib.UNICORN_GetData.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_uint32,
    ]
    return lib


def create_outlet(args: argparse.Namespace, channel_label: str, device_name: str) -> StreamOutlet:
    n_chan = 1 if args.single_channel else 16
    info = StreamInfo(args.lsl_name, args.lsl_type, n_chan, FSAMPLE, "float32", device_name)

    desc = info.desc()
    desc.append_child_value("student_id", args.student_name or args.lsl_name)
    desc.append_child_value("student_name", args.student_name or args.lsl_name)
    desc.append_child_value("device_name", device_name)
    channels = desc.append_child("channels")
    if args.single_channel:
        ch = channels.append_child("channel")
        ch.append_child_value("label", channel_label)
        ch.append_child_value("type", "EEG")
        ch.append_child_value("unit", "uV")
    else:
        labels = [
            "EEG 1",
            "EEG 2",
            "EEG 3",
            "EEG 4",
            "EEG 5",
            "EEG 6",
            "EEG 7",
            "EEG 8",
            "Accelerometer X",
            "Accelerometer Y",
            "Accelerometer Z",
            "Gyroscope X",
            "Gyroscope Y",
            "Gyroscope Z",
            "Battery Level",
            "Counter",
        ]
        for label in labels:
            ch = channels.append_child("channel")
            ch.append_child_value("label", label)
            ch.append_child_value("type", "EEG" if label.startswith("EEG") else "AUX")
            ch.append_child_value("unit", "uV" if label.startswith("EEG") else "arb")
    return StreamOutlet(info)


def main() -> int:
    args = parse_args()
    lib = load_lib(args.lib_path)
    print(f"[capi] lib path: {args.lib_path}")
    print(f"[capi] API version: {lib.UNICORN_GetApiVersion():.3f}")

    count = ctypes.c_uint32(0)
    check_ok(lib.UNICORN_GetAvailableDevices(None, ctypes.byref(count), 1), lib, "UNICORN_GetAvailableDevices(count)")
    if count.value == 0:
        raise RuntimeError("No Unicorn devices found")

    DeviceArray = (ctypes.c_char * SERIAL_LEN) * count.value
    devices = DeviceArray()
    check_ok(lib.UNICORN_GetAvailableDevices(devices, ctypes.byref(count), 0), lib, "UNICORN_GetAvailableDevices(list)")

    available = [decode_serial(bytes(devices[i])) for i in range(count.value)]
    print("[capi] available devices:", available)

    selected = args.serial if args.serial else available[0]
    if selected not in available:
        raise RuntimeError(f"Requested serial not found: {selected}")

    handle = ctypes.c_uint64(0)
    check_ok(lib.UNICORN_OpenDevice(selected.encode("ascii"), ctypes.byref(handle)), lib, "UNICORN_OpenDevice")
    print(f"[capi] connected to: {selected}")

    channel_count = ctypes.c_uint32(0)
    check_ok(lib.UNICORN_GetNumberOfAcquiredChannels(handle.value, ctypes.byref(channel_count)), lib, "UNICORN_GetNumberOfAcquiredChannels")
    print(f"[capi] acquired channels: {channel_count.value}")

    selected_idx = ctypes.c_uint32(0)
    if args.single_channel:
        check_ok(
            lib.UNICORN_GetChannelIndex(handle.value, args.channel_name.encode("utf-8"), ctypes.byref(selected_idx)),
            lib,
            "UNICORN_GetChannelIndex",
        )
        print(f"[capi] selected channel '{args.channel_name}' index={selected_idx.value}")

    outlet = create_outlet(args, args.channel_name, selected)
    print(f"[capi] opened LSL stream: {args.lsl_name}")

    check_ok(lib.UNICORN_StartAcquisition(handle.value, 1 if args.test_signal else 0), lib, "UNICORN_StartAcquisition")
    print("[capi] acquisition started")

    frame_len = max(1, args.frame_length)
    float_count = channel_count.value * frame_len
    buf = (ctypes.c_float * float_count)()

    sample_count = 0
    try:
        while True:
            check_ok(
                lib.UNICORN_GetData(handle.value, frame_len, buf, float_count),
                lib,
                "UNICORN_GetData",
            )
            for frame in range(frame_len):
                offset = frame * channel_count.value
                if args.single_channel:
                    sample = [float(buf[offset + selected_idx.value])]
                else:
                    sample = [float(buf[offset + i]) for i in range(min(16, channel_count.value))]
                outlet.push_sample(sample)
                sample_count += 1
    except KeyboardInterrupt:
        print("[capi] stopping (Ctrl+C)")
    finally:
        try:
            lib.UNICORN_StopAcquisition(handle.value)
        except Exception:
            pass
        try:
            lib.UNICORN_CloseDevice(ctypes.byref(handle))
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

