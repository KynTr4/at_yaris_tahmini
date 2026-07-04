"""Shared SSH connection helper for VPS maintenance scripts."""

from __future__ import annotations

import os
from pathlib import Path

import paramiko


def connect_vps(timeout: int = 10) -> paramiko.SSHClient:
    """Connect using SSH agent/key auth, with an optional password from env."""
    host = os.environ.get("VPS_HOST", "5.175.136.118")
    user = os.environ.get("VPS_USER", "root")
    password = os.environ.get("VPS_PASSWORD") or None
    key_path = os.environ.get("VPS_KEY_PATH")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    kwargs: dict[str, object] = {
        "hostname": host,
        "username": user,
        "timeout": timeout,
        "allow_agent": True,
        "look_for_keys": True,
    }
    if password:
        kwargs["password"] = password
    if key_path:
        kwargs["key_filename"] = str(Path(key_path).expanduser())

    client.connect(**kwargs)
    return client
