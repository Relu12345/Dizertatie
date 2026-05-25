from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TEACHER_APP_DIR = Path(__file__).resolve().parents[3]
_PROJECT_DIR = _TEACHER_APP_DIR.parent
ADMIN_DIR = _TEACHER_APP_DIR / "admin_config"
ADMIN_CONFIG_PATH = ADMIN_DIR / "admin.json"
DEFAULT_PIN = "2002"
DEFAULT_USERNAME = "Relu12345"
DEFAULT_REMOTE_DIR = "~/classroom-neurofeedback-pi"


def verify_pin(pin: str) -> bool:
    config = load_admin_config()
    return _hash_pin(pin) == config["pin_hash"]


def change_pin(old_pin: str, new_pin: str) -> tuple[bool, str]:
    if not verify_pin(old_pin):
        return False, "Old PIN is incorrect."
    if not new_pin.isdigit() or len(new_pin) < 4:
        return False, "Use at least 4 digits for the new PIN."

    config = load_admin_config()
    config["pin_hash"] = _hash_pin(new_pin)
    config["updated_at"] = _now()
    _write_config(config)
    return True, "PIN changed."


def load_admin_config() -> dict[str, Any]:
    _ensure_admin_dir()
    if not ADMIN_CONFIG_PATH.exists():
        config = _default_config()
        _write_config(config)
        return config

    try:
        config = json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        config = _default_config()

    defaults = _default_config()
    for key, value in defaults.items():
        config.setdefault(key, value)
    _write_config(config)
    return config


def save_network_settings(host_prefix: str, scan_start: int, scan_end: int, username: str, remote_dir: str) -> None:
    config = load_admin_config()
    config["host_prefix"] = host_prefix.strip() or "relu-pi-"
    config["scan_start"] = max(1, int(scan_start))
    config["scan_end"] = max(int(scan_start), int(scan_end))
    config["username"] = username.strip() or DEFAULT_USERNAME
    config["remote_dir"] = remote_dir.strip() or DEFAULT_REMOTE_DIR
    config["updated_at"] = _now()
    _write_config(config)


def list_devices() -> list[dict[str, Any]]:
    return load_admin_config().get("devices", [])


def save_devices(devices: list[dict[str, Any]]) -> None:
    config = load_admin_config()
    clean_devices = []
    for index, device in enumerate(devices, start=1):
        hostname = str(device.get("hostname", "")).strip()
        if not hostname:
            continue
        clean_devices.append(
            {
                "hostname": hostname,
                "ip": str(device.get("ip", "")).strip(),
                "headset": str(device.get("headset", "")).strip(),
                "student": str(device.get("student", "")).strip(),
                "status": str(device.get("status", "Unknown")).strip() or "Unknown",
                "notes": str(device.get("notes", "")).strip(),
                "enabled": bool(device.get("enabled", True)),
                "sort": int(device.get("sort", index) or index),
            }
        )
    config["devices"] = sorted(clean_devices, key=lambda item: item["sort"])
    config["updated_at"] = _now()
    _write_config(config)


def discover_devices(host_prefix: str, scan_start: int, scan_end: int) -> list[dict[str, Any]]:
    discovered = []
    for number in range(int(scan_start), int(scan_end) + 1):
        hostname = f"{host_prefix}{number}"
        ip = _resolve_host(hostname)
        reachable = _ping_host(hostname) if ip else False
        discovered.append(
            {
                "hostname": hostname,
                "ip": ip or "",
                "headset": "",
                "student": "",
                "status": "Online" if reachable else ("Resolved" if ip else "Not found"),
                "notes": "",
                "enabled": bool(ip),
                "sort": number,
            }
        )
    return discovered


def merge_discovered_devices(discovered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {device["hostname"]: device for device in list_devices()}
    for device in discovered:
        current = existing.get(device["hostname"], {})
        existing[device["hostname"]] = {
            **device,
            "headset": current.get("headset", device.get("headset", "")),
            "student": current.get("student", device.get("student", "")),
            "notes": current.get("notes", device.get("notes", "")),
            "enabled": current.get("enabled", device.get("enabled", True)),
        }
    devices = sorted(existing.values(), key=lambda item: item.get("sort", 9999))
    save_devices(devices)
    return devices


def deployment_command(hostname: str, username: str, remote_dir: str, skip_install: bool = False) -> str:
    script = _PROJECT_DIR / "pi_runtime" / "deploy_to_pi.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-PiHost",
        hostname,
        "-PiUser",
        username,
        "-RemoteDir",
        remote_dir,
    ]
    if skip_install:
        command.append("-SkipInstall")
    return " ".join(_quote(part) for part in command)


def deploy_to_device(hostname: str, username: str, remote_dir: str, skip_install: bool = False) -> dict[str, Any]:
    script = _PROJECT_DIR / "pi_runtime" / "deploy_to_pi.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-PiHost",
        hostname,
        "-PiUser",
        username,
        "-RemoteDir",
        remote_dir,
    ]
    if skip_install:
        command.append("-SkipInstall")

    started_at = _now()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        success = result.returncode == 0
        output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    except subprocess.TimeoutExpired as exc:
        success = False
        output = f"Deployment timed out after 180 seconds.\n{exc.stdout or ''}\n{exc.stderr or ''}"
    except OSError as exc:
        success = False
        output = f"Could not start deployment command: {exc}"

    log = {
        "hostname": hostname,
        "started_at": started_at,
        "finished_at": _now(),
        "success": success,
        "command": deployment_command(hostname, username, remote_dir, skip_install),
        "output": output.strip(),
    }
    _append_deployment_log(log)
    return log


def deployment_logs() -> list[dict[str, Any]]:
    return load_admin_config().get("deployments", [])


def _append_deployment_log(log: dict[str, Any]) -> None:
    config = load_admin_config()
    logs = [log, *config.get("deployments", [])]
    config["deployments"] = logs[:20]
    config["updated_at"] = _now()
    _write_config(config)


def _resolve_host(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except OSError:
        return None


def _ping_host(hostname: str) -> bool:
    command = ["ping", "-n", "1", "-w", "650", hostname]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _default_config() -> dict[str, Any]:
    return {
        "pin_hash": _hash_pin(DEFAULT_PIN),
        "host_prefix": "relu-pi-",
        "scan_start": 1,
        "scan_end": 12,
        "username": DEFAULT_USERNAME,
        "remote_dir": DEFAULT_REMOTE_DIR,
        "devices": [],
        "deployments": [],
        "updated_at": _now(),
    }


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(f"classroom-admin:{pin}".encode("utf-8")).hexdigest()


def _write_config(config: dict[str, Any]) -> None:
    _ensure_admin_dir()
    ADMIN_CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _ensure_admin_dir() -> None:
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quote(value: str) -> str:
    if not value or any(char.isspace() for char in value):
        return f'"{value}"'
    return value
