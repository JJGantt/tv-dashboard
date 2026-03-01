# tv-dashboard

Flask server for the Apple TV Top Shelf extension. Serves live dashboard data and renders Pillow poster card images.

## Overview

**tv-dashboard** runs on the Raspberry Pi (port 8766) and provides JSON endpoints and rendered images for the [PiDashboard](https://github.com/JJGantt/PiDashboard) tvOS app.

The server reads live from the shared data directory and renders section data as 404×608 poster cards cached on disk.

## Architecture

- `tv_server.py` — Flask app entry point (runs on port 8766)
- `tv_dashboard.py` — Blueprint with all route handlers and image rendering

## Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /tv/dashboard` | All 4 sections as JSON (todo, grocery, reminders, activity) |
| `GET /tv/section/<id>` | Single section JSON |
| `GET /tv/images/<id>.png` | Rendered 404×608 poster card image |

## Data Sources

Reads live from `/home/jaredgantt/data/`:
- `lists/todo.json` — To-do items
- `lists/grocery.json` — Grocery list
- `reminders/reminders.json` — Reminders with due dates
- `history/YYYY-MM-DD.json` — Activity summary by source

## Image Rendering

- Pillow-based poster card generation
- Color-coded by section (blue=todo, green=grocery, orange=reminders, purple=activity)
- Text wrapping, multi-line title/subtitle support
- MD5 hash-based caching to avoid re-rendering identical cards

## Service

Runs as a systemd service (`tv-server.service`):

```bash
systemctl status tv-server
systemctl start/stop/restart tv-server
```

## Related

- **Client:** [PiDashboard](https://github.com/JJGantt/PiDashboard) — tvOS app that consumes this API
- **Data:** [mcp-data](https://github.com/JJGantt/mcp-data) — MCP server for managing lists/reminders/notes
