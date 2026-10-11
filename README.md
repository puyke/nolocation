<p align="center">
  <img src="assets/nolocation.png" width="120" alt="NoLocation icon">
</p>

<h1 align="center">NoLocation</h1>

<p align="center">
  Change your iPhone's location from a Windows PC over a USB cable.<br>
  No app on the phone, no jailbreak, no App Store. Free and open source.
</p>

---

NoLocation is a small desktop app that sets your iPhone's GPS location through the same developer
service Xcode uses for location simulation. Pick a point on a dark navy map, teleport there, or
draw a route and "walk", "bike", "drive" or "fly" along real roads at realistic speeds.

> **Status:** early, built and tested with an iPhone 12 Pro on iOS 26 and Windows 11. Expect rough edges.
> Bug reports and pull requests are very welcome.

## Features

- **Teleport** to any point or searched address (search suggestions, favorites, recent searches)
- **Routes** that follow real roads (walk, bike, car) or a straight line (plane)
- **Speeds per mode**, editable in settings (default: 5 / 20 / 50 / 800 km/h)
- **Travel time:** type "30 minutes" and the speed is set automatically from the route length
- **When route ends:** stay there, go back, or return to your real location
- **One-tap offline:** click the phone name in the top-left to stop spoofing instantly and return to your real location
- **Auto connect:** connects when the phone is plugged in, reconnects after unplugging
- **Follow camera** while moving, smooth wheel zoom, persistent map cache
- Minimal dark UI. Press `F2` to hide the interface

## Requirements

- Windows 10/11 (64-bit)
- iPhone with iOS 17 or newer, USB cable
- [Apple Devices](https://apps.microsoft.com/detail/9np83lwlpz9k) app from the Microsoft Store (installs the Apple USB drivers), or iTunes
- Python 3.10+ (only if you run from source)
- **Developer Mode** enabled on the iPhone (see below)
- Internet connection (map tiles, search and routing use public web services)

## Install

### Option A: build the .exe

```
git clone https://github.com/YOUR-USER/nolocation.git
cd nolocation
build_windows.bat
```

This builds `NoLocation.exe`, installs it to `%LOCALAPPDATA%\Programs\NoLocation` and puts a shortcut on your desktop.
You can delete the cloned folder afterwards.

### Option B: run from source

```
pip install -r requirements.txt
python nolocation/main.py
```

## First-time iPhone setup

1. Plug in the iPhone and tap **Trust** on the phone.
2. Enable Developer Mode. Run this in a terminal, then follow the prompt on the phone (Settings > Privacy & Security > Developer Mode, then restart):
   ```
   python -m pymobiledevice3 amfi reveal-developer-mode
   ```
3. Start NoLocation (it asks for administrator rights, which are needed to open the device tunnel).
   The pill in the top-left turns green and shows your phone's name when connected.

## Usage

| Action | How |
| --- | --- |
| Teleport | Click the map (or search), press **Teleport** |
| Route | Switch to **Route**, click points, press **Start** |
| Change vehicle / speed | Bottom-left mode dock, gear icon for speeds |
| Stop spoofing | Click the phone pill (top-left), or **Return to Real Location** in settings |
| Hide UI | `F2` |

## How it works

NoLocation uses [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) to open a tunnel to the
iPhone over USB (iOS 17+ `CoreDeviceTunnelProxy`), connects to the developer services and calls the
location simulation instrument. The UI is a MapLibre GL map inside a [pywebview](https://pywebview.flowrl.com/) window.

## Limitations

- **The iPhone's real GPS position cannot be read from a computer.** The "real location" dot uses
  Windows location services, an approximate IP lookup, or a point you pin manually in settings.
- The iPhone must stay connected by cable. Closing the app or unplugging resets the location to real.
- Free public servers (OpenFreeMap tiles, Photon / Nominatim search, OSM routing) may rate-limit or change.
- Windows only for now.

## Disclaimer

NoLocation is for development, testing, privacy and personal use. Faking location may violate the terms
of some apps and games, and using it to deceive others, cheat, or break the law is your responsibility,
not the authors'. This project is not affiliated with or endorsed by Apple Inc. "iPhone" and "Apple" are trademarks of Apple Inc.
The software is provided as is, without warranty.

## Support the project

If NoLocation is useful to you, you can support its development:

**[Donate here]([https://YOUR-DONATION-LINK](https://buymeacoffee.com/puyke))**

## Contributing

Pull requests and bug reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) (GPL-3.0), the core of the device communication
- [MapLibre GL JS](https://maplibre.org/) (BSD-3-Clause) and [OpenFreeMap](https://openfreemap.org/) tiles
- [OpenStreetMap](https://www.openstreetmap.org/copyright) data (ODbL), [Photon](https://photon.komoot.io/), [Nominatim](https://nominatim.org/), [OSRM](https://project-osrm.org/) / routing.openstreetmap.de
- [pywebview](https://pywebview.flowrl.com/) (BSD-3-Clause)

## License

[GPL-3.0-or-later](LICENSE). Because NoLocation uses pymobiledevice3 (GPL-3.0), the whole project and any
distributed binary must stay under the GPL, with source available.
