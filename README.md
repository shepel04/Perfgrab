# perfgrab

Desktop tool for testing Android games over adb. No SDK or changes to the game are needed: connect a phone by USB, pick a game and run.

It has two modes:

- **Performance** - launches the game, measures cold start time and records FPS, CPU, GPU, RAM and temperature while you play.
- **Interruptions** - takes your checklist in .xlsx, triggers interruptions on the phone (Home, lock screen, network loss, low battery...), checks how the game handled each one and fills in the checklist.

![Performance](docs/screenshots/performance.png)
![Interruptions](docs/screenshots/interruptions.png)

## Performance

- 1st and 2nd cold launch time
- Live FPS, CPU, GPU, RAM and temperature with charts
- Min / max / average FPS, frame time, 1% low
- Several games in one session
- Results as CSV, JSON, XLSX, a chart and a tab-separated row ready to paste into a spreadsheet

FPS is read from SurfaceFlinger. Four methods are tried in order and the first one that works on the device is used: frame timestamps of the game layer, TimeStats layer counter, whole-screen frame counter, gfxinfo.

## Interruptions

1. Open a checklist (.xlsx). Needed columns: **Summary** (or Check) and **Status**. ID, Priority, Category, Issue link and Comment are picked up when present. Section rows become groups.
2. Each check gets a trigger based on its text:
   - **Auto** - the tool does it: Home, Recent apps, lock screen, screen timeout, notification shade, force stop, push notification, timer, Wi-Fi / mobile data / airplane mode, low battery, charger, battery saver, Do Not Disturb, rotation, dark theme, Bluetooth, interruption during loading.
   - **Assisted** - you bring the game to the right state (ad, purchase, end of level) and press Trigger.
   - **Manual** - you do it yourself (incoming call, wired headphones) and press Done. Calls are detected automatically.
3. After each interruption the tool checks:
   - crash or ANR in logcat
   - game process restarted by the system
   - game is back in foreground
   - game audio kept playing in background
   - game renders new frames
   - screenshots before / after with a similarity score
4. You confirm or change the suggested status (`Ctrl/Cmd+1..5`) and go to the next check (`Ctrl/Cmd+Enter`).

Device settings changed by a trigger are restored after every check, and also when the run is stopped.

Output in `runs/<checklist>_<date>/`: the filled checklist (formatting and dropdowns kept), `report.md` with a short run summary, `run.json` and screenshots.

An example checklist is in [`examples/`](examples/).

## Requirements

- Python 3.9+
- adb ([Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)), on macOS: `brew install --cask android-platform-tools`
- Android phone with USB debugging enabled
- `pip install -r requirements.txt` (PySide6, openpyxl, matplotlib)

## Run

```bash
pip install -r requirements.txt
python3 perfgrab_gui.py
```

On macOS you can also double-click `perfgrab.command` - it creates a virtual environment on the first run.

Command line (performance only):

```bash
python3 perfgrab.py                                   # pick games from the installed list
python3 perfgrab.py com.example.game -g High -d 30    # 30-minute run
python3 perfgrab.py com.example.game --diag           # FPS diagnostics
```

## Limitations

- GPU load is read from kernel files that some devices close without root. The column stays empty then.
- Launch time is the time to the first frame of the activity. Engine loading screens after that are not included.
- A real incoming call can't be simulated over adb on a physical phone, so call checks are manual.
- adb can't enter a PIN or password. Disable the screen lock for interruption runs.
- Some firmwares block certain commands (e.g. airplane mode). Such checks are marked Skipped with the reason.

## Project structure

```
perfgrab.py        core: device info, launch time, FPS / CPU / GPU / RAM sampling, CLI
interrupts.py      checklist parsing, interruption triggers, automatic checks, run report
perfgrab_gui.py    desktop app (PySide6)
examples/          example interruption checklist
```

## License

MIT
