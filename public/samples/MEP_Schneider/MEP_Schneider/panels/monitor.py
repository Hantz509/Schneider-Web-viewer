import requests, urllib3, asyncio, datetime
from decimal import Decimal, ROUND_HALF_UP
from requests.auth import HTTPBasicAuth
from omni.usd import get_context
from pxr import Sdf
import omni.ui as ui

# ============================================================
#  Configuration
# ============================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PI Web API connection ---
BASE_URL = "https://192.168.195.133/piwebapi"
USERNAME = r"WIN-S33DCIIJ3C6\\Administrator"
PASSWORD = "Qazw930323!"
AUTH     = HTTPBasicAuth(USERNAME, PASSWORD)
ATTR_URL = ("https://192.168.195.133/piwebapi/elements/"
            "F1Emo1CwofaPqEWTbP-5QLeDbQ7H901dxc8BGNOQAMKUls9QV0lOLVMzM0RDSUlKM0M2XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE"
            "/attributes")

# --- PI attribute name -> USD prim/attribute mapping ---
ATTR_MAP = {
    "溫度":            {"prim_path": "/World/Monitor/shell", "attribute": "temperature"},
    "溫度設定":        {"prim_path": "/World/Monitor/shell", "attribute": "temperature_setting"},
    "用電量":          {"prim_path": "/World/Monitor/shell", "attribute": "power"},
    "電流":            {"prim_path": "/World/Monitor/shell", "attribute": "current"},
    "內部運算_Output": {"prim_path": "/World/Monitor/shell", "attribute": "calculation_result"},
}

# Friendly display names (ASCII to avoid font issues)
DISPLAY = {
    "溫度":            "Temperature (°C)",
    "溫度設定":        "Set Temp (°C)",
    "用電量":          "Power (kWh)",
    "電流":            "Current (A)",
    "內部運算_Output": "Calc Output",
}

POLL_SEC = 30.0  # polling interval (seconds)

# ============================================================
#  Globals
# ============================================================

_session = requests.Session()
_session.auth   = AUTH
_session.verify = False

_win    = None           # ui.Window instance
_labels = {}             # {pi_name: ui.Label}
_task   = None           # asyncio Task handle

# ============================================================
#  Rounding helpers
# ============================================================

def fmt2(v):
    """Return a string rounded HALF_UP to 2 decimal places."""
    try:
        return str(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))
    except Exception:
        return str(v)

def to_float2(v):
    """Return a float rounded HALF_UP to 2 decimal places (for USD write)."""
    try:
        return float(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))
    except Exception:
        return float(v)

# ============================================================
#  PI Web API helpers
# ============================================================

def get_element_attributes():
    """Fetch the list of attributes for the configured element."""
    r = _session.get(ATTR_URL, timeout=5)
    r.raise_for_status()
    return r.json()["Items"]

def get_attribute_value(webid):
    """Fetch current value of a PI attribute by WebId."""
    r = _session.get(f"{BASE_URL}/streams/{webid}/value", timeout=5)
    r.raise_for_status()
    return r.json()["Value"]

# ============================================================
#  USD write helper
# ============================================================

def update_usd_prim(prim_path, attr_name, value):
    """Write value to a USD attribute. Create it if missing."""
    stage = get_context().get_stage()
    prim  = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return False, f"Prim not found: {prim_path}"

    usd_attr = prim.GetAttribute(attr_name)
    if not usd_attr.IsValid():
        usd_attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)

    usd_attr.Set(to_float2(value))
    return True, f"{attr_name} : {fmt2(value)}"

# ============================================================
#  UI construction & update
# ============================================================

def build_window(force=False):
    """Create (or show) the floating UI window and labels."""
    global _win, _labels
    _labels = {}

    if _win and not force:
        _win.visible = True
        return

    # Some Kit versions don't have DockPreference; wrap in try/except
    try:
        _win = ui.Window("PI Monitor", width=330, height=260,
                         dockPreference=ui.DockPreference.FLOAT)
    except Exception:
        _win = ui.Window("PI Monitor", width=330, height=260)

    with _win.frame:
        with ui.VStack(spacing=6, padding=8):
            ui.Label("PI Sync Panel", style={"font_size": 18})
            for name in ATTR_MAP:
                label_name = DISPLAY.get(name, name)
                with ui.HStack():
                    ui.Label(f"{label_name}:")
                    lab = ui.Label("-")
                _labels[name] = lab

            with ui.HStack():
                ui.Button("Refresh now", clicked_fn=_manual_refresh)
                ui.Button("Close", clicked_fn=lambda: setattr(_win, "visible", False))

    print(">>> window built")

def update_label(name, val):
    """Update one label's text (rounded)."""
    lab = _labels.get(name)
    if lab:
        lab.text = fmt2(val)

# ============================================================
#  Fetch cycle (shared by manual & auto)
# ============================================================

async def _one_cycle():
    """Single fetch-write-update cycle."""
    updated = 0
    try:
        items = get_element_attributes()
        for item in items:
            name, webid = item["Name"], item["WebId"]
            if name in ATTR_MAP:
                val = get_attribute_value(webid)
                cfg = ATTR_MAP[name]
                ok, _ = update_usd_prim(cfg["prim_path"], cfg["attribute"], val)
                if ok:
                    updated += 1
                    update_label(name, val)
    except Exception as exc:
        print("Sync error:", exc)

    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] updated {updated} attrs (manual/loop)")
    return updated

# Button callback
def _manual_refresh():
    asyncio.ensure_future(_one_cycle())

# ============================================================
#  Main polling loop
# ============================================================

async def polling_loop(period=POLL_SEC):
    print("Async polling loop started")
    build_window(force=True)
    while True:
        await _one_cycle()
        await asyncio.sleep(period)

# ============================================================
#  Start / Cleanup
# ============================================================

def start():
    """Start polling task and show window."""
    global _task
    if _task and not _task.done():
        print("Already running.")
        return
    _task = asyncio.ensure_future(polling_loop(POLL_SEC))
    print(f"Registered async PI sync & window ({POLL_SEC}s)")

def cleanup():
    """Stop polling task."""
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
    print("Stopped.")

# ------------------------------------------------------------
# Run
# ------------------------------------------------------------
start()

