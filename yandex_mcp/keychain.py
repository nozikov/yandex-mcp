"""Чтение OAuth-токенов из macOS Keychain."""

import subprocess


def keychain_token(name):
    result = subprocess.run(
        ["security", "find-generic-password", "-s", f"{name}-token", "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"нет токена {name} в Keychain — выпустить: yandex-oauth login --name {name}")
    return result.stdout.strip()
