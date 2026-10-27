"""
interrupts - semi-automatic interruption testing of Android games over adb.

Flow per checklist item:
  prepare (game in foreground, logcat cleared, PID + screenshot)
  -> trigger (auto by adb / after the tester presses Trigger / done by the tester)
  -> resume the game -> automatic checks -> suggested status -> tester confirms.
All device settings changed by a trigger are restored after every item.
"""
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field

import perfgrab as core

STATUSES = ["Passed", "Failed", "Blocked", "Skipped", "N/A"]
NOT_RUN = {"", "not run", "notrun", "none", "-"}

AUTO, ASSISTED, MANUAL = "auto", "assisted", "manual"


# ============================================================================ checklist
@dataclass
class Item:
    row: int
    id: str
    category: str
    priority: str
    summary: str
    status: str = ""          # status already in the file
    comment: str = ""
    link: str = ""
    action: str = "generic"
    mode: str = MANUAL
    # filled during a run
    result: str = ""
    new_comment: str = ""
    new_link: str = ""
    checks: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    ran: bool = False

    @property
    def final_status(self):
        return self.result or self.status


@dataclass
class Checklist:
    path: str
    sheet: str
    header_row: int
    cols: dict
    status_cols: list          # [(col, header)]
    items: list
    info_cells: dict           # label -> (row, col) of the value cell
    sheets: list


SUMMARY_RX = re.compile(r"^(summary|check|checks|test case|test|title|description|scenario|перевірка|назва)\b", re.I)


def _norm(v):
    return "" if v is None else str(v).strip()


def _find_header(ws, max_rows=40):
    for r in range(1, min(ws.max_row, max_rows) + 1):
        cells = {c: _norm(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 40) + 1)}
        summary = next((c for c, v in cells.items() if SUMMARY_RX.match(v)), None)
        status = [(c, v) for c, v in cells.items() if v.lower().startswith("status") or v.lower() == "result"]
        if summary and status:
            return r, cells, summary, status
    return None


def load_checklist(path, sheet=None):
    import openpyxl
    wb = openpyxl.load_workbook(path)
    names = wb.sheetnames
    order = [sheet] if sheet else names
    found = None
    for name in order:
        h = _find_header(wb[name])
        if h:
            found = (name, h)
            break
    if not found:
        raise ValueError("No checklist table found (need a 'Summary'/'Check' column and a 'Status' column).")
    name, (hr, cells, summary_col, status_cols) = found
    ws = wb[name]

    def col(*keys):
        for c, v in cells.items():
            lv = v.lower()
            if any(lv == k or lv.startswith(k) for k in keys):
                return c
        return None

    cols = {
        "id": col("id", "#", "tc"), "category": col("category", "section", "feature"),
        "priority": col("priority", "severity"), "summary": summary_col,
        "link": next((c for c, v in cells.items() if "issue" in v.lower() or "bug" in v.lower()
                      or v.lower() in ("link", "jira")), None),
        "comment": next((c for c, v in cells.items() if "comment" in v.lower() or "notes" in v.lower()), None),
    }
    # info block above the header ("Game", "Build", "Tester"...): the value goes into the cell on the right
    info = {}
    for r in range(1, hr):
        for c in range(1, min(ws.max_column, 10)):
            label = _norm(ws.cell(r, c).value).rstrip(":").lower()
            if label in INFO_LABELS:
                info[INFO_LABELS[label]] = (r, c + 1)

    merged_rows = {m.min_row for m in ws.merged_cells.ranges
                   if m.min_row == m.max_row and m.min_col <= summary_col <= m.max_col}
    items, category, n = [], "", 0
    for r in range(hr + 1, ws.max_row + 1):
        summ = _norm(ws.cell(r, summary_col).value)
        if not summ:
            filled = [(c, _norm(ws.cell(r, c).value)) for c in range(1, min(ws.max_column, 40) + 1)
                      if _norm(ws.cell(r, c).value)]
            # section row: merged across the table, or a single label left of the Summary column
            if filled and (r in merged_rows or (len(filled) == 1 and filled[0][0] < summary_col)):
                category = filled[0][1]
            continue
        n += 1
        cat = _norm(ws.cell(r, cols["category"]).value) if cols["category"] else ""
        if cat:
            category = cat
        it = Item(
            row=r, id=_norm(ws.cell(r, cols["id"]).value) if cols["id"] else "",
            category=category or "General",
            priority=_norm(ws.cell(r, cols["priority"]).value) if cols["priority"] else "",
            summary=summ,
            comment=_norm(ws.cell(r, cols["comment"]).value) if cols["comment"] else "",
            link=_norm(ws.cell(r, cols["link"]).value) if cols["link"] else "",
        )
        if not it.id:
            it.id = f"R{r}"
        it.status = _norm(ws.cell(r, status_cols[0][0]).value)
        it.action, it.mode = classify(summ)
        items.append(it)
    return Checklist(path=path, sheet=name, header_row=hr, cols=cols, status_cols=status_cols,
                     items=items, info_cells=info, sheets=names)


INFO_LABELS = {
    "game": "game", "app": "game", "platform / device": "device", "device": "device", "platform": "device",
    "os version": "os", "os": "os", "build / game version": "build", "build": "build", "game version": "build",
    "version": "build", "tester": "tester", "date": "date",
}


def read_status(cl, status_col):
    import openpyxl
    ws = openpyxl.load_workbook(cl.path)[cl.sheet]
    for it in cl.items:
        it.status = _norm(ws.cell(it.row, status_col).value)


def save_checklist(cl, out_path, status_col, info=None):
    import openpyxl
    wb = openpyxl.load_workbook(cl.path)
    ws = wb[cl.sheet]
    comment_col = cl.cols.get("comment")
    if not comment_col:
        comment_col = ws.max_column + 1
        ws.cell(cl.header_row, comment_col, "Comment")
    for it in cl.items:
        if not it.result:
            continue
        _set(ws, it.row, status_col, it.result)
        if it.new_comment != it.comment:          # keep untouched cells (and their formatting) as they are
            _set(ws, it.row, comment_col, it.new_comment or None)
        if cl.cols.get("link") and it.new_link and it.new_link != it.link:
            _set(ws, it.row, cl.cols["link"], it.new_link)
    for key, (r, c) in cl.info_cells.items():
        if info and info.get(key) and not _norm(ws.cell(r, c).value):
            _set(ws, r, c, info[key])
    wb.save(out_path)


def _set(ws, r, c, v):
    try:
        ws.cell(r, c).value = v
    except AttributeError:     # merged non-anchor cell
        pass


# ============================================================================ mapping
CONTEXT_RX = re.compile(
    r"tutorial|rewarded|\bads?\b|advert|purchase|\biap\b|in-app|level end|end of (a |the )?level|results?\b|"
    r"saving|pause menu|cutscene|cut-scene|\bmatch\b|battle|\bshop\b|\bstore\b|dialog|boss|реклам|покупк|туторіал",
    re.I)

RULES = [
    (r"\bcalls?\b|дзвін", "call"),
    (r"wired headphone|headphones?.*(plug|jack)|\bjack\b|навушник.*(дрот|кабел)", "headphones_wired"),
    (r"bluetooth", "bluetooth"),
    (r"airplane|flight mode|aeroplane|політ", "airplane"),
    (r"wi-?fi.*(mobile|cellular|lte|4g)|(mobile|cellular) data.*wi-?fi|switch\w* .*(mobile|cellular)", "wifi_to_data"),
    (r"reconnect|network (is )?restor|restor\w* .*(network|connection)|back online", "net_restore"),
    (r"(network|internet|connection|wi-?fi|offline).*loading|loading.*(network|internet|connection|offline)", "net_loading"),
    (r"mobile data|cellular", "data_off"),
    (r"wi-?fi|network|internet|connection|offline|мереж", "wifi_off"),
    (r"notification (shade|panel|center|centre)|control cent|quick settings|status bar|pull\w* down|шторк", "shade"),
    (r"(tap|open|click)\w*.*notification|notification.*(tap|open)", "push_tap"),
    (r"\bsms\b|messenger|\bpush\b|notification|сповіщ", "push"),
    (r"alarm|timer|будильник", "alarm"),
    (r"low battery|battery (is )?low|battery.*\d+ ?%", "low_battery"),
    (r"battery saver|power sav|energy sav|енергозбер", "battery_saver"),
    (r"\bcharger\b|charging|зарядк", "charger"),
    (r"volume|гучн", "volume"),
    (r"music|another app.*(audio|sound)|(audio|sound) .*another app|media player|музик", "music"),
    (r"do not disturb|\bdnd\b|не турбувати", "dnd"),
    (r"rotat|orientation|landscape|portrait|поворот", "rotation"),
    (r"dark|light theme|\btheme\b|night mode|тем[аиу]", "dark_mode"),
    (r"force[- ]?(clos|stop|quit|kill)|\bkill|swipe\w* (away|up)|clos\w* .*from recent|removed from recent", "force_close"),
    (r"recent|app switch|multitask|switch\w* (to|between) (another )?app", "recents"),
    (r"time-?out|auto-?lock|automatically lock|screen (turns )?off (by|after)|\bsleep", "screen_timeout"),
    (r"\block|power button|screen off|блок", "lock"),
    (r"background.*(\d+\+? ?min|long|hour)|(\d+\+? ?min|long time).*background", "long_background"),
    (r"loading|завантаж", "loading_interrupt"),
    (r"\bhome\b|background|minimi|згорн", "home"),
]

ACTIONS = {
    # key: (default mode, short description)
    "home": (AUTO, "HOME → wait 5 s → resume"),
    "recents": (AUTO, "Recent apps → wait 4 s → resume"),
    "lock": (AUTO, "Lock screen → wait 6 s → unlock → resume"),
    "screen_timeout": (AUTO, "Screen timeout 15 s → auto-lock → unlock → resume"),
    "shade": (AUTO, "Notification shade + quick settings → close"),
    "force_close": (AUTO, "Force stop → relaunch"),
    "long_background": (AUTO, "HOME → keep in background → resume"),
    "push": (AUTO, "Post a heads-up notification (simulated push/SMS)"),
    "push_tap": (ASSISTED, "Post a notification; tester opens it, then returns to the game"),
    "alarm": (AUTO, "Set a 10 s system timer; tester dismisses it"),
    "low_battery": (AUTO, "Simulate battery 15% → 4% (system warning) → reset"),
    "battery_saver": (AUTO, "Battery saver on → off"),
    "charger": (AUTO, "Simulate charger connect → disconnect"),
    "airplane": (AUTO, "Airplane mode on 10 s → off"),
    "wifi_to_data": (AUTO, "Mobile data on, Wi-Fi off 12 s → Wi-Fi on"),
    "net_restore": (AUTO, "Wi-Fi off 10 s → on, wait for reconnect"),
    "net_loading": (AUTO, "Relaunch with Wi-Fi + data off → restore during loading"),
    "data_off": (AUTO, "Mobile data off 10 s → on"),
    "wifi_off": (AUTO, "Wi-Fi off 10 s → on"),
    "volume": (AUTO, "Volume up ×2, down ×2"),
    "music": (MANUAL, "Start music in another app, return to the game"),
    "dnd": (AUTO, "Do Not Disturb on → off"),
    "rotation": (AUTO, "Force landscape → portrait"),
    "dark_mode": (AUTO, "Toggle system dark theme → restore"),
    "bluetooth": (AUTO, "Bluetooth off → on"),
    "headphones_wired": (MANUAL, "Plug in / unplug wired headphones"),
    "call": (MANUAL, "Make the call from another phone (detected automatically)"),
    "loading_interrupt": (AUTO, "Relaunch → HOME at 2.5 s of loading → resume"),
    "generic": (MANUAL, "Manual check on the device"),
}

NEEDS_CONFIRM = {"alarm"}       # auto trigger, tester must act on the device before checks


def classify(summary):
    s = summary.lower()
    action = "generic"
    for rx, key in RULES:
        if re.search(rx, s):
            action = key
            break
    mode = ACTIONS[action][0]
    interruption = action != "generic" or re.search(r"interrupt|minimi|background|переривання|згорн", s)
    if interruption and CONTEXT_RX.search(s) and action in (
            "home", "recents", "lock", "push", "shade", "alarm", "generic",
            "wifi_off", "data_off", "airplane", "low_battery", "force_close"):
        if action == "generic":
            action = "home"
        mode = ASSISTED
    return action, mode


def describe(item):
    return ACTIONS.get(item.action, ACTIONS["generic"])[1]


# ============================================================================ device helpers
class Unsupported(Exception):
    pass


ERR_RX = re.compile(r"unknown command|not found|exception|permission denial|usage:|error|invalid", re.I)


class Ctx:
    def __init__(self, adb, pkg, component, log, stop_event, opts):
        self.adb, self.pkg, self.component = adb, pkg, component
        self.log, self.stop_event, self.opts = log, stop_event, opts
        self.restore = []          # commands, executed in reverse order
        self.saved = set()
        self.bg_audio = None
        self.expect_restart = False
        self.notes = []

    # --- basics
    def sh(self, cmd, timeout=30):
        return self.adb.sh(cmd, timeout=timeout)

    def wait(self, sec):
        if self.stop_event.wait(sec):
            raise InterruptedError
        return False

    def key(self, name):
        self.sh(f"input keyevent KEYCODE_{name}")

    def must(self, cmd, *fallbacks):
        for c in (cmd,) + fallbacks:
            out = self.sh(c).strip()
            if not ERR_RX.search(out):
                return out
        raise Unsupported(f"'{cmd}' is not supported on this device")

    def on_restore(self, cmd):
        if cmd not in self.restore:
            self.restore.append(cmd)

    def save_setting(self, ns, key):
        if (ns, key) in self.saved:
            return
        val = self.sh(f"settings get {ns} {key}").strip()
        self.saved.add((ns, key))
        self.on_restore(f"settings delete {ns} {key}" if val in ("null", "") else f"settings put {ns} {key} {val}")

    def restore_all(self):
        for cmd in reversed(self.restore):
            self.sh(cmd)
        self.restore.clear()
        self.saved.clear()

    # --- game state
    def pid(self):
        return core.pidof(self.adb, self.pkg)

    def foreground(self):
        out = self.sh("dumpsys activity activities | grep -E 'topResumedActivity|mResumedActivity|ResumedActivity:'")
        if not out.strip():
            out = self.sh("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'")
        return self.pkg in out

    def screen_on(self):
        out = self.sh("dumpsys power | grep -m1 -E 'mWakefulness='")
        return "Awake" in out or not out.strip()

    def wake_unlock(self):
        self.key("WAKEUP")
        time.sleep(0.6)
        self.sh("wm dismiss-keyguard")
        time.sleep(0.8)

    def launch(self):
        if self.component:
            self.sh(f"am start -n {self.component}")
        else:
            self.sh(f"monkey -p {self.pkg} -c android.intent.category.LAUNCHER 1")

    def to_game(self, timeout=12):
        if not self.screen_on():
            self.wake_unlock()
        if self.foreground() and self.pid():
            return True
        self.sh(f"monkey -p {self.pkg} -c android.intent.category.LAUNCHER 1")
        end = time.time() + timeout
        while time.time() < end:
            self.wait(0.7)
            if self.foreground():
                return True
        return False

    def check_bg_audio(self):
        """True if the game keeps playing audio while it is not in foreground."""
        uid = game_uid(self.adb, self.pkg)
        if not uid:
            return
        out = self.sh("dumpsys audio", timeout=20)
        players = out.split("players:", 1)[1] if "players:" in out else ""
        playing = False
        for line in players.splitlines()[:200]:
            if f"u/pid:{uid}/" in line and "state:started" in line:
                playing = True
        if self.bg_audio is None or playing:
            self.bg_audio = playing


_uid_cache = {}


def game_uid(adb, pkg):
    if pkg not in _uid_cache:
        m = re.search(r"uid:(\d+)", adb.sh(f"pm list packages -U {pkg}"))
        _uid_cache[pkg] = m.group(1) if m else None
    return _uid_cache[pkg]


def game_version(adb, pkg):
    out = adb.sh(f"dumpsys package {pkg} | grep -E 'versionName|versionCode' | head -n 2")
    name = re.search(r"versionName=(\S+)", out)
    code = re.search(r"versionCode=(\d+)", out)
    if name and code:
        return f"{name.group(1)} ({code.group(1)})"
    return name.group(1) if name else ""


def screencap(adb):
    try:
        p = subprocess.run(adb.base + ["exec-out", "screencap", "-p"], capture_output=True, timeout=20)
        data = p.stdout
        return data if data[:4] == b"\x89PNG" else None
    except Exception:
        return None


def crash_lines(adb, pkg):
    hits = []
    crash = adb.sh("logcat -d -b crash 2>/dev/null", timeout=20)
    if pkg in crash:
        for line in crash.splitlines():
            if any(k in line for k in ("FATAL EXCEPTION", ">>> ", "Process: ", "Abort message", "Fatal signal")):
                hits.append(line.strip()[:220])
        hits = hits or ["crash buffer has entries for the game"]
    ev = adb.sh("logcat -d -b events 2>/dev/null | grep -E 'am_crash|am_anr'", timeout=20)
    hits += [line.strip()[:220] for line in ev.splitlines() if pkg in line]
    anr = adb.sh(f"logcat -d -b system 2>/dev/null | grep -F 'ANR in {pkg}'", timeout=20)
    hits += [line.strip()[:220] for line in anr.splitlines() if line.strip()]
    return hits


def clear_logs(adb):
    adb.sh("logcat -c; logcat -b crash -c 2>/dev/null; logcat -b events -c 2>/dev/null")


def frames_in(adb, pkg, seconds=2.0):
    """New frames of the screen in `seconds` (whole-screen counter, then game layer timestamps)."""
    a = core.sf_frame_counter(adb)
    if a is not None:
        time.sleep(seconds)
        b = core.sf_frame_counter(adb)
        if b is not None and b > 0 and b >= a:
            return b - a
    for layer in core.find_layers(adb, pkg)[:3]:
        ts1 = core.read_latency(adb, layer)
        if ts1:
            time.sleep(seconds)
            ts2 = core.read_latency(adb, layer)
            return len([t for t in ts2 if t > ts1[-1]])
    return None


# ============================================================================ actions
def _bg(c, sec):
    c.wait(min(2, sec))
    c.check_bg_audio()
    c.wait(max(0, sec - 2))


def a_home(c):
    c.key("HOME")
    _bg(c, 5)
    c.to_game()


def a_recents(c):
    c.key("APP_SWITCH")
    _bg(c, 4)
    c.to_game()


def a_lock(c):
    c.key("SLEEP")
    _bg(c, 6)
    c.wake_unlock()
    c.to_game()


def a_screen_timeout(c):
    c.save_setting("system", "screen_off_timeout")
    c.save_setting("global", "stay_on_while_plugged_in")
    c.sh("settings put global stay_on_while_plugged_in 0")
    c.sh("settings put system screen_off_timeout 15000")
    c.log("Waiting for auto-lock (do not touch the phone)")
    end = time.time() + 45
    while time.time() < end and c.screen_on():
        c.wait(1)
    if c.screen_on():
        raise Unsupported("screen did not turn off by timeout")
    _bg(c, 4)
    c.restore_all()
    c.wake_unlock()
    c.to_game()


def a_shade(c):
    c.must("cmd statusbar expand-notifications")
    c.wait(3)
    c.sh("cmd statusbar expand-settings")
    c.wait(2)
    c.sh("cmd statusbar collapse")
    c.wait(2)


def a_force_close(c):
    c.expect_restart = True
    c.sh(f"am force-stop {c.pkg}")
    c.wait(2)
    c.launch()
    c.wait(10)
    c.to_game()


def a_long_background(c):
    c.key("HOME")
    _bg(c, max(10, int(c.opts.get("long_bg_sec", 120))))
    c.to_game()


def a_push(c):
    c.must("cmd notification post -S bigtext -t 'New message' perfgrab_test 'Interruption test notification'")
    c.wait(6)


def a_push_tap(c):
    a_push(c)


def a_alarm(c):
    c.must("am start -a android.intent.action.SET_TIMER --ei android.intent.extra.alarm.LENGTH 10 "
           "--ez android.intent.extra.alarm.SKIP_UI true")
    c.wait(2)
    c.to_game()
    c.log("Timer set, fires in ~10 s")
    c.wait(12)


def a_low_battery(c):
    c.on_restore("dumpsys battery reset")
    c.sh("dumpsys battery unplug")
    c.sh("dumpsys battery set level 15")
    c.wait(3)
    c.sh("dumpsys battery set level 4")
    c.wait(6)
    c.sh("dumpsys battery reset")


def a_battery_saver(c):
    c.on_restore("dumpsys battery reset")
    c.on_restore("cmd power set-mode 0")
    c.sh("dumpsys battery unplug")
    c.must("cmd power set-mode 1", "settings put global low_power 1")
    c.wait(6)
    c.sh("cmd power set-mode 0")
    c.wait(3)


def a_charger(c):
    c.on_restore("dumpsys battery reset")
    c.sh("dumpsys battery unplug")
    c.wait(2)
    c.sh("dumpsys battery set ac 1")
    c.sh("dumpsys battery set status 2")
    c.wait(4)
    c.sh("dumpsys battery unplug")
    c.sh("dumpsys battery set status 3")
    c.wait(4)
    c.sh("dumpsys battery reset")


def _net(c, cmd_off, cmd_on, off_sec, after_sec):
    c.on_restore(cmd_on)
    c.must(cmd_off)
    c.wait(off_sec)
    c.sh(cmd_on)
    c.wait(after_sec)


def a_wifi_off(c):
    _net(c, "svc wifi disable", "svc wifi enable", 10, 8)


def a_data_off(c):
    _net(c, "svc data disable", "svc data enable", 10, 8)


def a_net_restore(c):
    _net(c, "svc wifi disable", "svc wifi enable", 10, 15)


def a_airplane(c):
    _net(c, "cmd connectivity airplane-mode enable", "cmd connectivity airplane-mode disable", 10, 12)


def a_wifi_to_data(c):
    c.on_restore("svc data enable")
    c.sh("svc data enable")
    _net(c, "svc wifi disable", "svc wifi enable", 12, 8)


def a_net_loading(c):
    c.expect_restart = True
    c.on_restore("svc wifi enable")
    c.on_restore("svc data enable")
    c.sh(f"am force-stop {c.pkg}")
    c.must("svc wifi disable")
    c.sh("svc data disable")
    c.wait(2)
    c.launch()
    c.wait(15)
    c.sh("svc wifi enable")
    c.sh("svc data enable")
    c.wait(12)
    c.to_game()


def a_loading_interrupt(c):
    c.expect_restart = True
    c.sh(f"am force-stop {c.pkg}")
    c.wait(2)
    c.launch()
    c.wait(2.5)
    c.key("HOME")
    _bg(c, 5)
    c.to_game()
    c.wait(10)


def a_volume(c):
    for k in ("VOLUME_UP", "VOLUME_UP", "VOLUME_DOWN", "VOLUME_DOWN"):
        c.key(k)
        c.wait(0.7)
    c.wait(2)


def a_dnd(c):
    c.on_restore("cmd notification set_dnd off")
    c.must("cmd notification set_dnd priority")
    c.wait(5)
    c.sh("cmd notification set_dnd off")
    c.wait(2)


def a_rotation(c):
    c.save_setting("system", "accelerometer_rotation")
    c.save_setting("system", "user_rotation")
    c.sh("settings put system accelerometer_rotation 0")
    c.sh("settings put system user_rotation 1")
    c.wait(4)
    c.sh("settings put system user_rotation 0")
    c.wait(3)


def a_dark_mode(c):
    cur = c.sh("cmd uimode night").strip().lower()
    if "night mode" not in cur:
        raise Unsupported("cmd uimode is not available")
    orig = "yes" if "yes" in cur else ("auto" if "auto" in cur else "no")
    c.on_restore(f"cmd uimode night {orig}")
    c.sh(f"cmd uimode night {'no' if orig == 'yes' else 'yes'}")
    c.wait(5)
    c.sh(f"cmd uimode night {orig}")
    c.wait(4)
    c.to_game()


def a_bluetooth(c):
    c.on_restore("svc bluetooth enable")
    c.must("svc bluetooth disable", "cmd bluetooth_manager disable")
    c.wait(6)
    c.sh("svc bluetooth enable")
    c.sh("cmd bluetooth_manager enable")
    c.wait(4)


def a_manual(c):
    pass


ACTION_FN = {
    "home": a_home, "recents": a_recents, "lock": a_lock, "screen_timeout": a_screen_timeout,
    "shade": a_shade, "force_close": a_force_close, "long_background": a_long_background,
    "push": a_push, "push_tap": a_push_tap, "alarm": a_alarm, "low_battery": a_low_battery,
    "battery_saver": a_battery_saver, "charger": a_charger, "airplane": a_airplane,
    "wifi_to_data": a_wifi_to_data, "net_restore": a_net_restore, "net_loading": a_net_loading,
    "data_off": a_data_off, "wifi_off": a_wifi_off, "volume": a_volume, "dnd": a_dnd,
    "rotation": a_rotation, "dark_mode": a_dark_mode, "bluetooth": a_bluetooth,
    "loading_interrupt": a_loading_interrupt,
    "music": a_manual, "headphones_wired": a_manual, "call": a_manual, "generic": a_manual,
}


def call_state(adb):
    m = re.findall(r"mCallState=(\d)", adb.sh("dumpsys telephony.registry"))
    return max((int(x) for x in m), default=0)


# ============================================================================ checks
def run_checks(c, pid_before, shot_before, similarity_fn=None, evidence_dir=None, item_id="item"):
    """Returns (checks, suggested_status, auto_comment, evidence_paths)."""
    checks, fails, evidence = [], [], []

    def add(name, state, detail=""):
        checks.append({"name": name, "state": state, "detail": detail})
        if state == "fail":
            fails.append(detail or name)

    c.wait(2)
    crashes = crash_lines(c.adb, c.pkg)
    if crashes:
        kind = "ANR" if any("anr" in x.lower() for x in crashes) else "Crash"
        msg = re.sub(r"^(\d\d-\d\d \S+ +\d+ +\d+ )?[VDIWEF][ /]\s*[\w.]+\s*:\s*", "", crashes[0])
        add("Crash / ANR", "fail", f"{kind}: {msg}")
    else:
        add("Crash / ANR", "ok", "none in logcat")

    pid_after = c.pid()
    if not pid_after:
        add("Process", "fail", "Game process is not running after the interruption")
    elif c.expect_restart:
        add("Process", "ok", "relaunched")
    elif pid_before and pid_after != pid_before:
        add("Process", "fail", "Game was restarted by the system (state lost)")
    else:
        add("Process", "ok", f"same PID {pid_after}")

    fg = c.foreground() if pid_after else False
    if pid_after:
        add("Foreground", "ok" if fg else "fail", "game is on screen" if fg else "Game did not return to foreground")
    else:
        add("Foreground", "na", "")

    if c.bg_audio is None:
        add("Background audio", "na", "")
    elif c.bg_audio:
        add("Background audio", "fail", "Game audio kept playing while in background")
    else:
        add("Background audio", "ok", "silent in background")

    frames = frames_in(c.adb, c.pkg) if fg else None
    if frames is None:
        add("Rendering", "na", "frame counter unavailable")
    elif frames == 0:
        add("Rendering", "warn", "no new frames in 2 s (frozen or static screen)")
    else:
        add("Rendering", "ok", f"{frames / 2:.0f} fps")

    shot_after = screencap(c.adb)
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        for tag, data in (("before", shot_before), ("after", shot_after)):
            if data:
                p = os.path.join(evidence_dir, f"{_safe(item_id)}_{tag}.png")
                with open(p, "wb") as f:
                    f.write(data)
                evidence.append(p)
    if shot_before and shot_after and similarity_fn:
        sim = similarity_fn(shot_before, shot_after)
        if sim is not None:
            add("Screen vs before", "ok" if sim >= 0.6 else "warn", f"{sim * 100:.0f}% similar")
    for n in c.notes:
        add("Note", "warn", n)

    status = "Failed" if fails else "Passed"
    return checks, status, "; ".join(fails), evidence


def _safe(s):
    return re.sub(r"[^\w.-]+", "_", s)[:40] or "item"


# ============================================================================ report
def build_report(cl, items, meta):
    ran = [i for i in items if i.result]
    counts = {s: sum(1 for i in ran if i.result == s) for s in STATUSES}
    executed = counts["Passed"] + counts["Failed"]
    rate = f"{counts['Passed'] / executed * 100:.0f}%" if executed else "-"
    dur = meta.get("duration_min")
    lines = [
        f"# Interruptions run - {meta.get('game', '')}",
        "",
        f"- **Build:** {meta.get('build') or '-'}",
        f"- **Device:** {meta.get('device', '')}, {meta.get('os', '')}",
        f"- **Tester:** {meta.get('tester') or '-'}",
        f"- **Date:** {meta.get('date')}" + (f" ({dur:g} min)" if dur else ""),
        f"- **Checklist:** {os.path.basename(cl.path)} / {cl.sheet} / {meta.get('status_col', '')}",
        "",
        "## Summary",
        f"{len(ran)} of {len(cl.items)} checks · " + " · ".join(f"{s} {counts[s]}" for s in STATUSES if counts[s])
        + f" · Pass rate {rate}",
    ]
    failed = [i for i in ran if i.result == "Failed"]
    if failed:
        lines += ["", "## Failed"]
        for i in failed:
            pr = f" [{i.priority}]" if i.priority else ""
            extra = f" - {i.new_comment}" if i.new_comment else ""
            link = f" ({i.new_link})" if i.new_link else ""
            lines.append(f"- **{i.id}**{pr} {i.summary}{extra}{link}")
    other = [i for i in ran if i.result in ("Blocked", "Skipped")]
    if other:
        lines += ["", "## Blocked / Skipped"]
        for i in other:
            lines.append(f"- **{i.id}** {i.result}: {i.summary}" + (f" - {i.new_comment}" if i.new_comment else ""))
    modes = {m: sum(1 for i in ran if i.mode == m) for m in (AUTO, ASSISTED, MANUAL)}
    lines += ["", "## Notes",
              f"- Triggered by tool: {modes[AUTO]} auto, {modes[ASSISTED]} assisted; manual: {modes[MANUAL]}",
              "- Auto checks after each interruption: crash/ANR (logcat), process restart, foreground, "
              "background audio, rendering, screenshot before/after"]
    return "\n".join(lines) + "\n"


def save_run_json(path, cl, items, meta):
    data = {"meta": meta, "items": [{
        "id": i.id, "category": i.category, "priority": i.priority, "summary": i.summary,
        "action": i.action, "mode": i.mode, "result": i.result, "comment": i.new_comment,
        "link": i.new_link, "checks": i.checks, "evidence": i.evidence} for i in items if i.ran or i.result]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================================ runner
PROMPTS = {
    ASSISTED: ("Set up the game state for this check, then trigger.", "Trigger"),
    MANUAL: ("Do this on the device, return to the game, then press Done.", "Done"),
    "call": ("Call this phone from another device. Continues when the call ends.", "Done"),
    "alarm": ("Dismiss the timer on the device and return to the game.", "Continue"),
    "push_tap": ("Open the notification, then return to the game.", "Continue"),
}


class Runner:
    """Runs checklist items one by one. `emit(event, **data)` reports progress to the UI.
    Blocking points: wait for the tester (go) and for the verdict (submit)."""

    def __init__(self, adb, pkg, opts, emit, similarity_fn=None, evidence_dir=None):
        self.adb, self.pkg, self.opts, self.emit = adb, pkg, opts, emit
        self.similarity_fn, self.evidence_dir = similarity_fn, evidence_dir
        self.stop_event = threading.Event()
        self.go_event = threading.Event()
        self.verdict_event = threading.Event()
        self.verdict = None

    def go(self):
        self.go_event.set()

    def submit(self, verdict):
        self.verdict = verdict
        self.verdict_event.set()

    def stop(self):
        self.stop_event.set()
        self.go_event.set()
        self.verdict_event.set()

    def _wait_user(self, idx, key):
        prompt, button = PROMPTS[key]
        self.go_event.clear()
        self.emit("wait_user", idx=idx, prompt=prompt, button=button)
        if key == "call":
            seen = False
            while not self.go_event.is_set():
                st = call_state(self.adb)
                if st:
                    if not seen:
                        self.emit("log", text="Call detected")
                    seen = True
                elif seen:
                    self.emit("log", text="Call ended")
                    break
                self.go_event.wait(1)
        else:
            self.go_event.wait()
        if self.stop_event.is_set():
            raise InterruptedError
        self.emit("phase", idx=idx, text="Running")

    def run(self, queue):
        component = core.launch_component(self.adb, self.pkg)
        log = lambda t: self.emit("log", text=t)  # noqa: E731
        try:
            for idx, it in queue:
                while True:
                    if self.stop_event.is_set():
                        return
                    self.emit("item_started", idx=idx)
                    res = self._run_item(idx, it, component, log)
                    it.ran = True
                    self.emit("checked", idx=idx, **res)
                    self.verdict_event.clear()
                    self.verdict_event.wait()
                    if self.stop_event.is_set():
                        return
                    if not self.verdict.get("retry"):
                        break
                self.emit("item_done", idx=idx, verdict=self.verdict)
        except InterruptedError:
            pass
        finally:
            self.emit("finished")

    def _run_item(self, idx, it, component, log):
        c = Ctx(self.adb, self.pkg, component, log, self.stop_event, self.opts)
        try:
            self.emit("phase", idx=idx, text="Preparing")
            if not c.to_game(timeout=25):
                return {"checks": [{"name": "Game", "state": "fail", "detail": "could not bring the game to foreground"}],
                        "status": "Blocked", "comment": "Game could not be opened", "evidence": []}
            c.wait(1.5)
            if it.mode == ASSISTED:
                self._wait_user(idx, ASSISTED)
            clear_logs(self.adb)
            pid0 = c.pid()
            shot0 = screencap(self.adb)
            if it.mode == MANUAL:
                self._wait_user(idx, "call" if it.action == "call" else MANUAL)
            self.emit("phase", idx=idx, text="Triggering")
            ACTION_FN.get(it.action, a_manual)(c)
            if it.action in NEEDS_CONFIRM or it.action == "push_tap":
                self._wait_user(idx, it.action)
            c.restore_all()
            c.to_game()
            self.emit("phase", idx=idx, text="Checking")
            checks, status, comment, ev = run_checks(c, pid0, shot0, self.similarity_fn,
                                                     self.evidence_dir, it.id)
            return {"checks": checks, "status": status, "comment": comment, "evidence": ev}
        except Unsupported as e:
            return {"checks": [{"name": "Trigger", "state": "na", "detail": str(e)}],
                    "status": "Skipped", "comment": f"Not supported via adb on this device: {e}", "evidence": []}
        finally:
            c.restore_all()
