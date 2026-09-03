"""Чтение/запись значений в macOS Keychain и sha256-отпечатки для логов."""

import hashlib
import os
import subprocess
import sys

CLIENT_ID_ITEM = "yandex-oauth-client-id"
CLIENT_SECRET_ITEM = "yandex-oauth-client-secret"


def fingerprint(value):
    if not value:
        return "sha256:none"
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:8]


def keychain_get(item, required=True):
    result = subprocess.run(
        ["security", "find-generic-password", "-s", item, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if required:
            sys.exit(f"нет записи в Keychain: {item}")
        return None
    return result.stdout.strip()


def keychain_set(item, value):
    subprocess.run(["security", "delete-generic-password", "-s", item],
                   capture_output=True)
    result = subprocess.run(
        ["security", "add-generic-password", "-s", item,
         "-a", os.environ.get("USER", "-"), "-w", value, "-U"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"не удалось записать в Keychain: {item}")
