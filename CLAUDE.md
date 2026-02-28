# tv-dashboard

Pi-side server for the Apple TV Top Shelf extension. Serves JSON dashboard data and
rendered poster card images to the tvOS app.

## TODO: Port / Connection
- Port is TBD. Currently placeholder — needs to be decided and set in tv_server.py.
- The tvOS app (on Mac — check ~/Developer or ~/Projects for the Xcode project) needs to
  point to this Pi's IP + port.
- Once the port is confirmed, create a systemd service (tv-server.service) and open the
  port if needed.
- Pi IPs: local 10.0.0.14, Tailscale 100.104.197.58

## Structure
- `tv_dashboard.py` — all route handlers and image rendering (originally a Blueprint in pi_server)
- `tv_server.py` — standalone Flask app entry point (run this directly)

## Endpoints
- `GET /tv/dashboard` — all sections as JSON (todo, grocery, reminders, activity)
- `GET /tv/section/<id>` — single section
- `GET /tv/images/<id>.png` — Pillow-rendered 404x608 poster card

## Data sources
Reads live from `/home/jaredgantt/data/`:
- `lists/todo.json`, `lists/grocery.json`
- `reminders/reminders.json`
- `history/YYYY-MM-DD.json` (activity summary)

Image cache: `/home/jaredgantt/data/tv_cache/`

## tvOS App
The Apple TV Swift app lives on the Mac. It was previously co-developed alongside this
server. Check the Mac for the Xcode project when resuming work on the client side.
Mac: ssh jaredgantt@100.106.101.57 (Tailscale) or jaredgantt@Jareds-MacBook-Air.local
