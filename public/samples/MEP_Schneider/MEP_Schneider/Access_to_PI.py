"""
PI Web API  →  Omniverse USD Live Sync
------------------------------------------------
• Queries selected PI attributes every 30 s
• Writes the values to the corresponding USD prim attributes
• Prints a clear, time‑stamped summary after each sync cycle
"""

import requests
import urllib3
import asyncio
import datetime
from requests.auth import HTTPBasicAuth
from omni.usd import get_context
from pxr import Sdf

# Disable SSL certificate warnings (for local testing only)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- PI Web API connection settings ------------------------------------------------
BASE_URL  = "https://192.168.195.133/piwebapi"
USERNAME  = r"WIN-S33DCIIJ3C6\\Administrator"
PASSWORD  = "Qazw930323!"
auth      = HTTPBasicAuth(USERNAME, PASSWORD)

# --- PI attribute → USD attribute mapping -----------------------------------------
attribute_to_usd_mapping = {
    "溫度":            {"prim_path": "/World/MEP____/Geometry/Architecture/Column/_100_x_100cm/____1124940_Test_", "attribute": "temperature"},
    "溫度設定":        {"prim_path": "/World/MEP____/Geometry/Architecture/Column/_100_x_100cm/____1124940_Test_", "attribute": "temperature_setting"},
    "用電量":          {"prim_path": "/World/MEP____/Geometry/Architecture/Column/_100_x_100cm/____1124940_Test_", "attribute": "power"},
    "電流":            {"prim_path": "/World/MEP____/Geometry/Architecture/Column/_100_x_100cm/____1124940_Test_", "attribute": "current"},
    "內部運算_Output": {"prim_path": "/World/MEP____/Geometry/Architecture/Column/_100_x_100cm/____1124940_Test_", "attribute": "calculation_result"},
}

# PI element attributes endpoint
ATTR_URL = (
    "https://192.168.195.133/piwebapi/elements/"
    "F1Emo1CwofaPqEWTbP-5QLeDbQ7H901dxc8BGNOQAMKUls9QV0lOLVMzM0RDSUlKM0M2XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE"
    "/attributes"
)

# ----------------------------------------------------------------------------- helpers
def get_element_attributes():
    """Return metadata for all attributes of the element."""
    r = requests.get(ATTR_URL, auth=auth, verify=False, timeout=5)
    r.raise_for_status()
    return r.json()["Items"]

def get_attribute_value(webid):
    """Return the current value of a PI attribute by WebId."""
    r = requests.get(f"{BASE_URL}/streams/{webid}/value", auth=auth, verify=False, timeout=5)
    r.raise_for_status()
    return r.json()["Value"]

def update_usd_prim(prim_path, attr_name, value):
    """
    Write value to the given USD prim attribute.
    Returns (success: bool, log_message: str)
    """
    stage = get_context().get_stage()
    prim  = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return False, f"Prim not found: {prim_path}"

    usd_attr = prim.GetAttribute(attr_name)
    if not usd_attr.IsValid():
        usd_attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)

    usd_attr.Set(round(float(value), 2))
    return True, f"{attr_name} : {value}"

# --------------------------------------------------------------------------- main loop
async def polling_loop(period_sec: float = 30.0):
    """Async loop: sync every `period_sec` seconds."""
    print("Async polling loop started")
    while True:
        updated_logs = []              # collect per‑cycle messages
        try:
            for item in get_element_attributes():
                name  = item["Name"]
                webid = item["WebId"]
                if name in attribute_to_usd_mapping:
                    val  = get_attribute_value(webid)
                    cfg  = attribute_to_usd_mapping[name]
                    ok, msg = update_usd_prim(cfg["prim_path"], cfg["attribute"], val)
                    if ok:
                        updated_logs.append(msg)
                    else:
                        print(msg)     # prim not found
        except Exception as exc:
            print(f"Sync error: {exc}")

        # formatted summary
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"\n===== {ts}   updated {len(updated_logs)} attributes =====")
        for line in updated_logs:
            print("--", line)
        print("===== end ==================================\n")

        await asyncio.sleep(period_sec)

# kick‑off
asyncio.ensure_future(polling_loop(30.0))
print("Registered async PI sync (every 30s)")


