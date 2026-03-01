"""Apple TV control via pyatv — used by tv_server endpoints."""

import asyncio
import json
from pathlib import Path

import pyatv
from pyatv.const import Protocol

APPLE_TV_ID = "C46B1CD9-2AF6-4275-955C-84A61C657EEE"
CONF_PATH = Path.home() / ".pyatv.conf"


def _load_credentials() -> dict:
    """Load stored credentials from .pyatv.conf."""
    if not CONF_PATH.exists():
        return {}
    data = json.loads(CONF_PATH.read_text())
    for device in data.get("devices", []):
        protocols = device.get("protocols", {})
        companion = protocols.get("companion", {})
        if companion.get("identifier") == APPLE_TV_ID:
            return {
                Protocol.Companion: companion.get("credentials"),
                Protocol.AirPlay: protocols.get("airplay", {}).get("credentials"),
            }
    return {}


async def _connect():
    """Connect to the Apple TV with stored credentials."""
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, identifier=APPLE_TV_ID, timeout=5)
    if not atvs:
        raise RuntimeError("Apple TV not found on network")
    conf = atvs[0]
    creds = _load_credentials()
    for protocol, credential in creds.items():
        if credential:
            conf.set_credentials(protocol, credential)
    return await pyatv.connect(conf, loop)


async def wake_and_focus():
    """Wake the Apple TV and switch TV input to it."""
    atv = await _connect()
    try:
        await atv.remote_control.home()
    finally:
        atv.close()
        # Let pending cleanup tasks finish before the loop closes
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def send_command(command: str):
    """Send a remote control command to the Apple TV."""
    atv = await _connect()
    try:
        rc = atv.remote_control
        cmd = getattr(rc, command, None)
        if cmd is None:
            raise ValueError(f"Unknown command: {command}")
        await cmd()
    finally:
        atv.close()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def run_wake_and_focus():
    """Synchronous wrapper for wake_and_focus."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(wake_and_focus())
    finally:
        loop.close()


def run_command(command: str):
    """Synchronous wrapper for send_command."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(send_command(command))
    finally:
        loop.close()
