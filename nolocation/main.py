# -*- coding: utf-8 -*-
# NoLocation - change your iPhone's location from Windows over a USB cable.
# Copyright (C) 2026 NoLocation contributors
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. It is distributed WITHOUT ANY WARRANTY. See the LICENSE file.
"""
NoLocation - change your iPhone's location from Windows over a USB cable.

Run:        python nolocation/main.py
Requires:   pip install pymobiledevice3 pywebview
Note:       The app asks for administrator rights because opening the
            device tunnel needs a virtual network adapter.
"""
import asyncio
import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from contextlib import AsyncExitStack
from pathlib import Path

APP_DIR = Path.home() / ".nolocation"
SETTINGS_PATH = APP_DIR / "settings.json"
UA = "NoLocation/1.0 (+https://github.com/YOUR-USER/nolocation)"
MODE_KEYS = ("walk", "bike", "car", "plane")
LOG_PATH = APP_DIR / "nolocation.log"


def log(msg):
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Administrator rights
# --------------------------------------------------------------------------
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate():
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, " ".join('"%s"' % a for a in sys.argv[1:])
    else:
        exe = sys.executable
        params = " ".join('"%s"' % a for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)


# --------------------------------------------------------------------------
# Geographic helpers
# --------------------------------------------------------------------------
def haversine(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def build_path(points):
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + haversine(points[i - 1], points[i]))
    return cum


def point_at(points, cum, d):
    if d <= 0:
        return points[0]
    if d >= cum[-1]:
        return points[-1]
    for i in range(1, len(cum)):
        if d <= cum[i]:
            seg = cum[i] - cum[i - 1]
            t = 0 if seg == 0 else (d - cum[i - 1]) / seg
            a, b = points[i - 1], points[i]
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    return points[-1]


def friendly(e):
    name = e.__class__.__name__
    msg = str(e) or name
    if "NoDeviceConnected" in name or "No device" in msg:
        return "Phone not found, check the cable"
    if "DeveloperMode" in name:
        return "Developer Mode is off"
    if isinstance(e, asyncio.TimeoutError):
        return "Connection timed out"
    return msg


# --------------------------------------------------------------------------
# Network helpers: search suggestions, road routing, real location
# --------------------------------------------------------------------------
def http_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _photon(q, lat, lon):
    url = "https://photon.komoot.io/api/?limit=7&q=" + urllib.parse.quote(q)
    if lat is not None and lon is not None:
        url += "&lat=%.5f&lon=%.5f" % (float(lat), float(lon))
    out = []
    for f in http_json(url, 8).get("features", []):
        pr = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates")
        if not c or len(c) < 2:
            continue
        street = pr.get("street") or ""
        if street and pr.get("housenumber"):
            street += " " + str(pr["housenumber"])
        name = pr.get("name") or street
        if not name:
            continue
        parts = [street if street and street != name else ""] + [
            pr.get(k) for k in ("district", "city", "county", "state", "country")]
        sub = ", ".join(dict.fromkeys(x for x in parts if x and x != name))
        out.append({"name": name, "sub": sub, "lat": float(c[1]), "lon": float(c[0])})
    return out


def _nominatim(q):
    base = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=7&accept-language=en&q=" + urllib.parse.quote(q)
    data = http_json(base, 10)
    out = []
    for it in data:
        disp = str(it.get("display_name", ""))
        head, _, tail = disp.partition(",")
        out.append({"name": (it.get("name") or head).strip(), "sub": tail.strip(),
                    "lat": float(it["lat"]), "lon": float(it["lon"])})
    return out


_SUG_CACHE = {}


def suggest_places(query, lat=None, lon=None):
    q = str(query).strip()
    if len(q) < 2:
        return []
    key = q.lower()
    if key in _SUG_CACHE:
        return _SUG_CACHE[key]
    res = []
    try:
        res = _photon(q, lat, lon)
    except Exception:
        res = []
    if not res:
        res = _nominatim(q)
    if len(_SUG_CACHE) > 80:
        _SUG_CACHE.clear()
    _SUG_CACHE[key] = res
    return res


def windows_location():
    """Approximate position from the Windows location service (Wi-Fi based). None if the service is off."""
    if sys.platform != "win32":
        return None
    ps = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Device;"
        "$w=New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High);"
        "$null=$w.TryStart($false,[TimeSpan]::FromSeconds(8));"
        "$l=$w.Position.Location;"
        "if($l.IsUnknown){exit 3};"
        "[string]::Format([Globalization.CultureInfo]::InvariantCulture,'{0},{1}',$l.Latitude,$l.Longitude)"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=20, creationflags=0x08000000)
        if r.returncode != 0:
            return None
        a, b = r.stdout.strip().split(",")
        lat, lon = float(a), float(b)
        if math.isnan(lat) or math.isnan(lon):
            return None
        return [lat, lon]
    except Exception:
        return None


def ip_location():
    for url in ("https://ipwho.is/", "http://ip-api.com/json/?fields=status,lat,lon"):
        try:
            d = http_json(url, 8)
            if d.get("success") is True or d.get("status") == "success":
                lat = d.get("latitude", d.get("lat"))
                lon = d.get("longitude", d.get("lon"))
                if lat is not None and lon is not None:
                    return [float(lat), float(lon)]
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# Settings (favorites, recent searches, speeds...)
# --------------------------------------------------------------------------
def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _places(lst, cap):
    res = []
    for p in (lst or [])[:cap]:
        try:
            res.append({"name": str(p.get("name", ""))[:80], "sub": str(p.get("sub", ""))[:140],
                        "lat": float(p["lat"]), "lon": float(p["lon"])})
        except Exception:
            continue
    return res


def clean_settings(d):
    out = {}
    sp = d.get("speeds") if isinstance(d.get("speeds"), dict) else {}
    out["speeds"] = {k: max(0.5, min(2000.0, float(sp[k]))) for k in MODE_KEYS if k in sp}
    if d.get("mode") in MODE_KEYS:
        out["mode"] = d["mode"]
    out["onRoad"] = bool(d.get("onRoad", True))
    if d.get("endMode") in ("stay", "back", "real"):
        out["endMode"] = d["endMode"]
    r = d.get("real")
    if isinstance(r, (list, tuple)) and len(r) == 2 and -90 <= float(r[0]) <= 90 and -180 <= float(r[1]) <= 180:
        out["real"] = [float(r[0]), float(r[1])]
    out["favs"] = _places(d.get("favs"), 60)
    out["recents"] = _places(d.get("recents"), 8)
    return out


def write_settings(d):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean_settings(d), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)


# --------------------------------------------------------------------------
# Backend: tunnel + location simulation (runs in its own asyncio loop)
# --------------------------------------------------------------------------
class Backend:
    def __init__(self, start_watcher=True):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.loc = None
        self.stop_evt = None
        self.session_task = None
        self.connected = False
        self.connecting = False
        self.manual_off = False
        self.phone_present = False
        self.message = "Waiting for phone"
        self.device = ""
        self.pos = None
        self.speed_kmh = 5.0
        self.moving = False
        self.paused = False
        self.progress = 0.0
        self.move_task = None
        self.next_try = 0.0
        if start_watcher:
            asyncio.run_coroutine_threadsafe(self._watch(), self.loop)

    def run(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # ---- cable watcher + auto connect ----
    async def _list_usb(self):
        from pymobiledevice3.usbmux import list_devices
        return any(d.connection_type == "USB" for d in await list_devices())

    async def _watch(self):
        while True:
            try:
                try:
                    present = await self._list_usb()
                except Exception:
                    log('usbmux error\n' + traceback.format_exc())
                    present = False
                self.phone_present = present
                if not present:
                    if self.connected or self.connecting:
                        await self._disconnect(clear=False)
                        self.message = "Phone unplugged"
                    elif not self.manual_off:
                        self.message = "Waiting for phone"
                elif (not self.connected and not self.connecting and not self.manual_off
                      and time.time() >= self.next_try):
                    self.connecting = True
                    asyncio.ensure_future(self._auto_connect())
            except Exception:
                log('watcher error\n' + traceback.format_exc())
            await asyncio.sleep(2.0)

    async def _auto_connect(self):
        try:
            await self._connect()
        except Exception:
            self.next_try = time.time() + 6

    # ---- connection ----
    async def _session(self, ready):
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.remote.common import TunnelProtocol
            from pymobiledevice3.remote.module_imports import start_tunnel
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            from pymobiledevice3.remote.tunnel_service import CoreDeviceTunnelProxy
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

            async with AsyncExitStack() as stack:
                log('1 opening lockdown')
                lockdown = await create_using_usbmux()
                close = getattr(lockdown, "close", None)
                if close is not None:
                    async def _close_lockdown():
                        r = close()
                        if asyncio.iscoroutine(r):
                            await r
                    stack.push_async_callback(_close_lockdown)
                try:
                    self.device = str(lockdown.short_info.get("DeviceName", ""))
                except Exception:
                    self.device = ""

                log('2 tunnel proxy')
                proxy = await CoreDeviceTunnelProxy.create(lockdown)
                tunnel = await stack.enter_async_context(
                    start_tunnel(proxy, protocol=TunnelProtocol.TCP)
                )
                log('3 tunnel open, rsd')
                rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
                await stack.enter_async_context(rsd)
                log('4 dvt')
                dvt = await stack.enter_async_context(DvtProvider(rsd))
                loc = await stack.enter_async_context(LocationSimulation(dvt))

                log('5 connected')
                self.loc = loc
                self.stop_evt = asyncio.Event()
                self.connected = True
                self.connecting = False
                self.message = "Connected"
                if not ready.done():
                    ready.set_result(True)

                stop_wait = asyncio.ensure_future(self.stop_evt.wait())
                closed_wait = asyncio.ensure_future(tunnel.client.wait_closed())
                done, pending = await asyncio.wait(
                    {stop_wait, closed_wait}, return_when=asyncio.FIRST_COMPLETED
                )
                for p in pending:
                    p.cancel()
                if closed_wait in done and not self.manual_off:
                    self.message = "Connection lost"
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa
            log('CONNECTION ERROR\n' + traceback.format_exc())
            self.message = "Could not connect: %s" % friendly(e)
            if not ready.done():
                ready.set_exception(e)
        finally:
            self.loc = None
            self.connected = False
            self.moving = False
            self.paused = False
            self.pos = None

    async def _connect(self):
        if self.connected:
            return
        self.manual_off = False
        self.connecting = True
        self.message = "Connecting…"
        ready = self.loop.create_future()
        self.session_task = asyncio.ensure_future(self._session(ready))
        try:
            await asyncio.wait_for(ready, 60)
        except Exception:
            self.next_try = time.time() + 6
            raise
        finally:
            self.connecting = False

    async def _disconnect(self, manual=False, clear=True):
        if manual:
            self.manual_off = True
        await self._stop_move()
        if clear and self.loc is not None:
            try:
                await asyncio.wait_for(self.loc.clear(), 4)
                await asyncio.sleep(0.25)
            except Exception:
                pass
        self.pos = None
        t = self.session_task
        if t is not None and not t.done():
            if self.stop_evt is not None:
                self.stop_evt.set()
                try:
                    await asyncio.wait_for(asyncio.shield(t), 8)
                except Exception:
                    t.cancel()
            else:
                t.cancel()
            try:
                await t
            except BaseException:
                pass
        self.session_task = None
        self.stop_evt = None
        self.connected = False
        self.connecting = False
        if manual:
            self.message = "Offline"

    # ---- location ----
    async def _teleport(self, lat, lon):
        await self._stop_move()
        await self._set(lat, lon)

    async def _set(self, lat, lon):
        if self.loc is None:
            raise RuntimeError("Not connected to the phone")
        await self.loc.set(float(lat), float(lon))
        self.pos = (float(lat), float(lon))

    async def _reset(self):
        await self._stop_move()
        if self.loc is not None:
            await self.loc.clear()
        self.pos = None

    # ---- movement ----
    async def _start_move(self, points, end_mode="stay"):
        await self._stop_move()
        if self.loc is None:
            raise RuntimeError("Not connected to the phone")
        if len(points) < 2:
            raise RuntimeError("At least 2 points are needed for a route")
        self.moving = True
        self.paused = False
        self.progress = 0.0
        self.move_task = asyncio.ensure_future(self._move(points, end_mode))

    async def _move(self, points, end_mode):
        try:
            pts = list(points)
            cum = build_path(pts)
            d = 0.0
            returned = False
            last = time.monotonic()
            await self._set(*pts[0])
            while True:
                await asyncio.sleep(1.0)
                now = time.monotonic()
                dt = now - last
                last = now
                if self.paused:
                    continue
                d += (self.speed_kmh / 3.6) * dt
                total = cum[-1]
                if total <= 0:
                    break
                if d >= total:
                    await self._set(*pts[-1])
                    if end_mode == "back" and not returned:
                        returned = True
                        pts.reverse()
                        cum = build_path(pts)
                        d = 0.0
                        continue
                    if end_mode == "real" and self.loc is not None:
                        await self.loc.clear()
                        self.pos = None
                    self.progress = 1.0
                    break
                self.progress = d / total
                await self._set(*point_at(pts, cum, d))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa
            self.message = "Movement stopped: %s" % friendly(e)
        finally:
            self.moving = False
            self.paused = False

    async def _stop_move(self):
        t = self.move_task
        self.move_task = None
        if t is not None and not t.done():
            t.cancel()
            try:
                await t
            except BaseException:
                pass
        self.moving = False
        self.paused = False


BACKEND = None  # created in main()


def _wrap(fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception as e:  # noqa
        return {"ok": False, "error": friendly(e)}


# --------------------------------------------------------------------------
# API called from JS (keep this class attribute-free; all state lives in BACKEND)
# --------------------------------------------------------------------------
class Api:
    def status(self):
        b = BACKEND
        return {
            "connected": b.connected,
            "connecting": b.connecting,
            "manualOff": b.manual_off,
            "present": b.phone_present,
            "message": b.message,
            "device": b.device,
            "pos": list(b.pos) if b.pos else None,
            "moving": b.moving,
            "paused": b.paused,
            "speed": b.speed_kmh,
            "progress": b.progress,
        }

    def toggle_connection(self):
        b = BACKEND
        if b.connected or b.connecting:
            return _wrap(lambda: b.run(b._disconnect(manual=True), 25))
        return _wrap(lambda: b.run(b._connect(), 75))

    def teleport(self, lat, lon):
        return _wrap(lambda: BACKEND.run(BACKEND._teleport(lat, lon), 20))

    def reset(self):
        return _wrap(lambda: BACKEND.run(BACKEND._reset(), 20))

    def start_route(self, points, speed, end_mode="stay"):
        def go():
            pts = [(float(p[0]), float(p[1])) for p in points]
            BACKEND.speed_kmh = float(speed)
            BACKEND.run(BACKEND._start_move(pts, end_mode if end_mode in ("stay", "back", "real") else "stay"), 20)
        return _wrap(go)

    def plan_route(self, points, profile):
        """Noktalar arasi gercek yol geometrisini dondurur ([lat, lon] listesi)."""
        def go():
            coords = ";".join("%.6f,%.6f" % (float(p[1]), float(p[0])) for p in points)
            prof = profile if profile in ("foot", "bike", "car") else "foot"
            urls = ["https://routing.openstreetmap.de/routed-%s/route/v1/driving/%s?overview=full&geometries=geojson" % (prof, coords)]
            if prof == "car":
                urls.append("https://router.project-osrm.org/route/v1/driving/%s?overview=full&geometries=geojson" % coords)
            last_err = "service did not respond"
            for url in urls:
                try:
                    data = http_json(url, 20)
                    if data.get("code") == "Ok" and data.get("routes"):
                        return [[c[1], c[0]] for c in data["routes"][0]["geometry"]["coordinates"]]
                    last_err = str(data.get("code", "bilinmeyen"))
                except Exception as e:  # noqa
                    last_err = str(e) or e.__class__.__name__
            raise RuntimeError(last_err)
        return _wrap(go)

    def pause(self):
        BACKEND.paused = True
        return {"ok": True}

    def resume(self):
        BACKEND.paused = False
        return {"ok": True}

    def stop(self):
        return _wrap(lambda: BACKEND.run(BACKEND._stop_move(), 10))

    def set_speed(self, kmh):
        BACKEND.speed_kmh = max(0.1, float(kmh))
        return {"ok": True}

    def suggest(self, query, lat=None, lon=None):
        return _wrap(lambda: suggest_places(query, lat, lon))

    def locate_real(self):
        def go():
            p = windows_location()
            if p:
                return {"pos": p, "src": "windows"}
            p = ip_location()
            if p:
                return {"pos": p, "src": "ip"}
            return None
        return _wrap(go)

    def get_settings(self):
        return _wrap(load_settings)

    def save_settings(self, data):
        return _wrap(lambda: (write_settings(data), True)[1])

    def on_closing(self):
        try:
            if BACKEND is not None and BACKEND.connected:
                BACKEND.run(BACKEND._disconnect(manual=True), 10)
        except Exception:
            pass


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
def _ui_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "ui"


def load_html():
    return (_ui_dir() / "index.html").read_text(encoding="utf-8")


def main():
    global BACKEND
    if sys.platform == "win32" and not is_admin():
        elevate()
        return
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:   # no stdout/stderr in windowed exe
        sys.stdout = sys.stderr = open(LOG_PATH, 'a', encoding='utf-8')
    log('NoLocation started, frozen=%s' % getattr(sys, 'frozen', False))
    import webview

    BACKEND = Backend()
    api = Api()
    window = webview.create_window(
        "NoLocation",
        html=load_html(),
        js_api=api,
        width=1240,
        height=800,
        min_size=(960, 620),
        background_color="#060b1f",
    )
    window.events.closing += api.on_closing
    # Persistent cache: map tiles come from disk on the next start
    webview.start(private_mode=False, storage_path=str(APP_DIR / "web"))


if __name__ == "__main__":
    main()
