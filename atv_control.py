"""Apple TV control via pyatv — used by tv_server endpoints."""

import asyncio
import json
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _apple_tv():
    """Connect to the Apple TV, yield it, then clean up properly."""
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, identifier=APPLE_TV_ID, timeout=5)
    if not atvs:
        raise RuntimeError("Apple TV not found on network")
    conf = atvs[0]
    creds = _load_credentials()
    for protocol, credential in creds.items():
        if credential:
            conf.set_credentials(protocol, credential)
    atv = await pyatv.connect(conf, loop)
    try:
        yield atv
    finally:
        atv.close()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _run(coro):
    """Run an async coroutine in a fresh event loop (sync wrapper)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- Wake / Sleep ---

async def wake_and_focus():
    """Wake the Apple TV and switch TV input to it via CEC."""
    async with _apple_tv() as atv:
        await atv.remote_control.home()


async def sleep_tv():
    """Put the Apple TV to sleep."""
    async with _apple_tv() as atv:
        await atv.power.turn_off()


# --- Remote Control ---

async def send_command(command: str):
    """Send a remote control command to the Apple TV."""
    async with _apple_tv() as atv:
        cmd = getattr(atv.remote_control, command, None)
        if cmd is None:
            raise ValueError(f"Unknown command: {command}")
        await cmd()


# --- Now Playing ---

async def now_playing() -> dict:
    """Get metadata about what's currently playing."""
    async with _apple_tv() as atv:
        playing = await atv.metadata.playing()
        return {
            "title": playing.title,
            "artist": playing.artist,
            "album": playing.album,
            "genre": playing.genre,
            "series_name": playing.series_name,
            "season_number": playing.season_number,
            "episode_number": playing.episode_number,
            "total_time": playing.total_time,
            "position": playing.position,
            "media_type": str(playing.media_type),
            "device_state": str(playing.device_state),
            "repeat": str(playing.repeat),
            "shuffle": str(playing.shuffle),
        }


# --- Apps ---

async def list_apps() -> list[dict]:
    """List installed apps on the Apple TV."""
    async with _apple_tv() as atv:
        apps = await atv.apps.app_list()
        return [{"name": a.name, "id": a.identifier} for a in apps]


async def launch_app(app_id: str):
    """Launch an app by bundle ID."""
    async with _apple_tv() as atv:
        await atv.apps.launch_app(app_id)


# --- Streaming ---

async def play_url(url: str):
    """Stream a URL via AirPlay."""
    async with _apple_tv() as atv:
        await atv.stream.play_url(url)


# --- Audio ---

async def set_volume(level: float):
    """Set volume to a specific level (0.0–100.0)."""
    async with _apple_tv() as atv:
        await atv.audio.set_volume(level)


async def volume_up():
    """Increase volume one step."""
    async with _apple_tv() as atv:
        await atv.audio.volume_up()


async def volume_down():
    """Decrease volume one step."""
    async with _apple_tv() as atv:
        await atv.audio.volume_down()


# --- Sync wrappers (called by Flask endpoints) ---

def run_wake_and_focus():
    return _run(wake_and_focus())

def run_sleep():
    return _run(sleep_tv())

def run_command(command: str):
    return _run(send_command(command))

def run_now_playing() -> dict:
    return _run(now_playing())

def run_list_apps() -> list[dict]:
    return _run(list_apps())

def run_launch_app(app_id: str):
    return _run(launch_app(app_id))

def run_play_url(url: str):
    return _run(play_url(url))

def run_set_volume(level: float):
    return _run(set_volume(level))

def run_volume_up():
    return _run(volume_up())

def run_volume_down():
    return _run(volume_down())
