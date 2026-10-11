# Contributing to NoLocation

Thanks for helping! NoLocation is a small project, so contributing is simple.

## Project layout

```
nolocation/main.py        Python backend: device tunnel, location simulation, search, routing, settings
nolocation/ui/index.html  The whole interface (HTML + CSS + JS, MapLibre GL map)
assets/                   Icon
build_windows.bat         Builds NoLocation.exe with PyInstaller and installs it
```

The UI talks to the backend through the `Api` class in `main.py` (`pywebview.api.<method>`).
`Api` must stay free of attributes; all state lives in the `BACKEND` object.

## Run from source

```
pip install -r requirements.txt
python nolocation/main.py
```

The app asks for administrator rights (needed for the tunnel adapter).

## Guidelines

- Keep the app small and dependency-light.
- UI text is in English. If you add a language, keep English as the default.
- Test with a real iPhone when you touch `main.py` connection code.
- Be careful with third-party web services (search, routing, tiles). They have usage policies;
  do not add heavy or commercial use of free public servers.
- By contributing you agree that your work is licensed under GPL-3.0-or-later, like the rest of the project.

## Reporting bugs

Open an issue and include your Windows version, iPhone model, iOS version and the log file at
`C:\Users\<you>\.nolocation\nolocation.log`.

## Ideas that would be great

- Translations (the UI strings are plain text in `index.html`)
- GPX import / export for routes
- Better route simulation (stops, speed variation)
- Wi-Fi (wireless) connection support
- macOS / Linux support
