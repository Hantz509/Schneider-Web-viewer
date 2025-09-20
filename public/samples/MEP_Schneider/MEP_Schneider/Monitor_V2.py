# ============================================================
#  Enhanced PI -> USD -> PNG -> Interactive Info Panel (Upgraded Version)
# ============================================================

import asyncio, datetime, os, tempfile, time, traceback, json
import requests, urllib3
from decimal import Decimal, ROUND_HALF_UP
from requests.auth import HTTPBasicAuth

from omni.usd import get_context
from pxr import Sdf, UsdShade, UsdGeom
import omni.ui as ui

# ---------------- Pillow ----------------
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    import omni.kit.pipapi as pipapi
    pipapi.install("Pillow")
    from PIL import Image, ImageDraw, ImageFont

# ---------------- PI Web API ----------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://192.168.195.133/piwebapi"
USERNAME = r"WIN-S33DCIIJ3C6\\Administrator"
PASSWORD = "Qazw930323!"
AUTH     = HTTPBasicAuth(USERNAME, PASSWORD)
ATTR_URL = ("https://192.168.195.133/piwebapi/elements/"
            "F1Emo1CwofaPqEWTbP-5QLeDbQ7H901dxc8BGNOQAMKUls9QV0lOLVMzM0M2XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE"
            "/attributes")
# PI Tag Name -> USD Attribute Mapping with Enhanced Info
ATTR_MAP = {
    "溫度": {
        "prim_path": "/World/Monitor/shell", 
        "attribute": "temperature",
        "info": {
            "description": "Main temperature sensor reading from NS800N unit",
            "unit": "°C",
            "normal_range": "20-25°C",
            "critical_high": 30.0,
            "critical_low": 15.0,
            "location": "Main Control Panel",
            "sensor_type": "Thermocouple Type K",
            "update_frequency": "Every 5 seconds",
            "alarm_enabled": True
        }
    },
    "溫度設定": {
        "prim_path": "/World/Monitor/shell", 
        "attribute": "temperature_setting",
        "info": {
            "description": "Target temperature setpoint for climate control",
            "unit": "°C",
            "normal_range": "18-28°C",
            "critical_high": 35.0,
            "critical_low": 10.0,
            "location": "RD District Control",
            "control_type": "PID Controller",
            "update_frequency": "Manual/Scheduled",
            "alarm_enabled": False
        }
    },
    "用電量": {
        "prim_path": "/World/Monitor/shell", 
        "attribute": "power",
        "info": {
            "description": "Real-time power consumption monitoring",
            "unit": "kWh",
            "normal_range": "10-50 kWh",
            "critical_high": 80.0,
            "critical_low": 0.0,
            "location": "AC5D Electrical Panel",
            "meter_type": "Smart Energy Meter",
            "update_frequency": "Every 15 seconds",
            "alarm_enabled": True
        }
    },
    "電流": {
        "prim_path": "/World/Monitor/shell", 
        "attribute": "current",
        "info": {
            "description": "Electrical current measurement in main circuit",
            "unit": "A",
            "normal_range": "20-90 A",
            "critical_high": 100.0,
            "critical_low": 5.0,
            "location": "R5D Distribution Panel",
            "sensor_type": "Current Transformer",
            "update_frequency": "Every 2 seconds",
            "alarm_enabled": True
        }
    },
    "內部運算_Output": {
        "prim_path": "/World/Monitor/shell", 
        "attribute": "calculation_result",
        "info": {
            "description": "Internal calculation output from control algorithm",
            "unit": "Calculated Value",
            "normal_range": "50-200",
            "critical_high": 250.0,
            "critical_low": 0.0,
            "location": "E5D Processing Unit",
            "calculation_type": "PID + Feedforward",
            "update_frequency": "Every 10 seconds",
            "alarm_enabled": False
        }
    }
}

DISPLAY = {
    "溫度":            "Temperature (°C)",
    "溫度設定":        "Set Temp (°C)",
    "用電量":          "Power (kWh)",
    "電流":            "Current (A)",
    "內部運算_Output": "Calc Output",
}

TARGET_PRIM = "/World/Monitor/shell"
MAT_PATH    = "/World/Monitor/PI_PanelMat"
POLL_SEC    = 30.0

IMG_SIZE    = (1200, 600)  # Increased size for better layout
BG_RGBA     = (0, 0, 0, 180)
FONT_SIZE   = 36
SMALL_FONT_SIZE = 24
PNG_DIR     = os.path.join(tempfile.gettempdir(), "pi_panel")
os.makedirs(PNG_DIR, exist_ok=True)

# Global variables for UI elements
_session         = requests.Session()
_session.auth    = AUTH
_session.verify  = False

_font            = None
_small_font      = None
_mat_ready       = False
_png_idx         = 0
_task            = None
_stage_sub       = None
_info_window     = None
_control_window  = None
_live_labels     = {}
_current_values  = {}
_historical_data = {}

def fmt2(v):
    return str(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))

def to_float2(v):
    return float(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))

def get_element_attributes():
    r = _session.get(ATTR_URL, timeout=5)
    r.raise_for_status()
    return r.json()["Items"]

def get_attribute_value(webid):
    r = _session.get(f"{BASE_URL}/streams/{webid}/value", timeout=5)
    r.raise_for_status()
    return r.json()["Value"]

def get_historical_data(webid, hours=24):
    """Get historical data for trend analysis"""
    try:
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(hours=hours)
        
        url = f"{BASE_URL}/streams/{webid}/recorded"
        params = {
            "startTime": start_time.isoformat(),
            "endTime": end_time.isoformat(),
            "maxCount": 100
        }
        
        r = _session.get(url, params=params, timeout=10)
        r.raise_for_status()
        
        items = r.json().get("Items", [])
        return [(item["Timestamp"], item["Value"]) for item in items]
    except Exception as e:
        print(f"Historical data error: {e}")
        return []

def update_usd_prim(prim_path, attr_name, value):
    stage = get_context().get_stage()
    prim  = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return False, f"Prim not found: {prim_path}"
    attr = prim.GetAttribute(attr_name)
    if not attr.IsValid():
        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)
    attr.Set(to_float2(value))
    return True, f"{attr_name}:{fmt2(value)}"

def ensure_uv():
    stage = get_context().get_stage()
    prim  = stage.GetPrimAtPath(TARGET_PRIM)
    mesh  = UsdGeom.Mesh(prim)
    if not mesh:
        print("Mesh not found:", TARGET_PRIM)
        return False

    pv_api = UsdGeom.PrimvarsAPI(prim)
    st = pv_api.GetPrimvar("st")
    if st and st.IsDefined():
        return True

    pts = mesh.GetPointsAttr().Get()
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
    spanx = maxx-minx or 1.0; spany = maxy-miny or 1.0
    uvs = [((p[0]-minx)/spanx, (p[1]-miny)/spany) for p in pts]

    st = pv_api.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(uvs)
    print("UV created (planar).")
    return True

def _ensure_fonts():
    global _font, _small_font
    if _font and _small_font: 
        return _font, _small_font
    try:
        _font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        _small_font = ImageFont.truetype("arial.ttf", SMALL_FONT_SIZE)
    except Exception:
        _font = ImageFont.load_default()
        _small_font = ImageFont.load_default()
    return _font, _small_font

def get_status_color(attr_name, value):
    """Get color based on value status"""
    if attr_name not in ATTR_MAP:
        return (255, 255, 255, 255)  # White default
    
    info = ATTR_MAP[attr_name]["info"]
    critical_high = info.get("critical_high", float('inf'))
    critical_low = info.get("critical_low", float('-inf'))
    
    if value >= critical_high:
        return (255, 100, 100, 255)  # Red for critical high
    elif value <= critical_low:
        return (100, 150, 255, 255)  # Blue for critical low
    else:
        return (150, 255, 150, 255)  # Green for normal

def _draw_enhanced_png(data_lines, path):
    """Enhanced PNG drawing with status indicators and click hints"""
    try:
        bg_path = os.path.join(PNG_DIR, "panel_bg.png")
        img = Image.open(bg_path).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", IMG_SIZE, BG_RGBA)
    
    d = ImageDraw.Draw(img)
    font, small_font = _ensure_fonts()
    
    # Draw main border
    border_margin = 20
    d.rounded_rectangle(
        [border_margin, border_margin, IMG_SIZE[0] - border_margin, IMG_SIZE[1] - border_margin],
        radius=40,
        outline=(255, 255, 255, 120),
        width=4
    )
    
    # Title
    title_y = 30
    d.text((40, title_y), "PI Data Monitor - Click attribute names for details", 
           fill=(255, 220, 150, 255), font=font)
    
    y = title_y + 60
    
    # Draw data with status colors and click indicators
    for line in data_lines:
        if ":" in line and any(attr in line for attr in DISPLAY.values()):
            label, value = line.split(":", 1)
            value = value.strip()
            
            # Find the attribute name for this display label
            attr_name = None
            for key, display_name in DISPLAY.items():
                if display_name in label:
                    attr_name = key
                    break
            
            if attr_name and attr_name in _current_values:
                color = get_status_color(attr_name, _current_values[attr_name])
                
                # Draw clickable indicator
                d.ellipse([15, y + 5, 25, y + 15], fill=(100, 200, 255, 200))
                
                # Draw status indicator
                status_color = color[:3] + (200,)
                d.rectangle([350, y, 360, y + 25], fill=status_color)
                
                d.text((40, y), label + ":", fill=(200, 200, 255, 255), font=font)
                d.text((400, y), value, fill=color, font=font)
            else:
                d.text((40, y), label + ":", fill=(200, 200, 255, 255), font=font)
                d.text((400, y), value, fill=(255, 255, 255, 255), font=font)
        else:
            if "PI Sync" not in line:  # Skip timestamp line
                d.text((40, y), line, fill=(255, 220, 150, 255), font=font)
        
        y += FONT_SIZE + 20
    
    # Instructions
    instruction_y = IMG_SIZE[1] - 80
    d.text((40, instruction_y), "Click blue dots for detailed information", 
           fill=(100, 200, 255, 200), font=small_font)
    d.text((40, instruction_y + 30), "Status: Green=Normal, Red=High, Blue=Low", 
           fill=(180, 180, 180, 200), font=small_font)
           
    img.save(path)

def create_info_window(attr_name):
    """Create detailed information window for an attribute"""
    global _info_window
    
    if attr_name not in ATTR_MAP:
        return
    
    info = ATTR_MAP[attr_name]["info"]
    current_value = _current_values.get(attr_name, "N/A")
    
    # Close existing window
    if _info_window:
        _info_window.destroy()
    
    # Create new info window
    _info_window = ui.Window(f"Attribute Details: {DISPLAY.get(attr_name, attr_name)}", 
                            width=400, height=500)
    
    with _info_window.frame:
        with ui.VStack(spacing=10):
            ui.Label(f"Current Value: {fmt2(current_value) if isinstance(current_value, (int, float)) else current_value}", 
                    style={"font_size": 18, "color": 0xFF00FF00})
            
            ui.Separator()
            
            ui.Label("Description:", style={"font_size": 14, "color": 0xFFCCCCCC})
            ui.Label(info["description"], word_wrap=True, style={"font_size": 12})
            
            ui.Spacer(height=5)
            
            with ui.HStack():
                ui.Label("Unit:", style={"font_size": 12, "color": 0xFFCCCCCC})
                ui.Label(info["unit"], style={"font_size": 12, "color": 0xFFFFFFFF})
            
            with ui.HStack():
                ui.Label("Normal Range:", style={"font_size": 12, "color": 0xFFCCCCCC})
                ui.Label(info["normal_range"], style={"font_size": 12, "color": 0xFF00FF00})
            
            with ui.HStack():
                ui.Label("Location:", style={"font_size": 12, "color": 0xFFCCCCCC})
                ui.Label(info["location"], style={"font_size": 12, "color": 0xFFFFFFFF})
            
            with ui.HStack():
                ui.Label("Update Frequency:", style={"font_size": 12, "color": 0xFFCCCCCC})
                ui.Label(info["update_frequency"], style={"font_size": 12, "color": 0xFFFFFFFF})
            
            ui.Separator()
            
            # Status information
            if isinstance(current_value, (int, float)):
                status = "NORMAL"
                status_color = 0xFF00FF00
                
                if current_value >= info.get("critical_high", float('inf')):
                    status = "CRITICAL HIGH"
                    status_color = 0xFFFF0000
                elif current_value <= info.get("critical_low", float('-inf')):
                    status = "CRITICAL LOW"
                    status_color = 0xFF0080FF
                
                ui.Label(f"Status: {status}", style={"font_size": 14, "color": status_color})
            
            # Historical trend (simplified)
            hist_data = _historical_data.get(attr_name, [])
            if hist_data:
                recent_values = [v for _, v in hist_data[-10:]]
                if len(recent_values) >= 2:
                    trend = "RISING" if recent_values[-1] > recent_values[0] else "FALLING"
                    trend_color = 0xFFFF8000 if trend == "RISING" else 0xFF0080FF
                    ui.Label(f"Recent Trend: {trend}", style={"font_size": 12, "color": trend_color})
            
            ui.Spacer()
            
            def close_window():
                global _info_window
                if _info_window:
                    _info_window.destroy()
                    _info_window = None
            
            ui.Button("Close", clicked_fn=close_window, height=30)

# Enhanced UI Panel with live data display and clickable attributes
def create_control_panel():
    """Create an enhanced control panel with live data and clickable attributes"""
    global _control_window, _live_labels
    
    _control_window = ui.Window("PI Data Monitor & Controls", width=400, height=600)
    _live_labels = {}
    
    with _control_window.frame:
        with ui.VStack(spacing=8):
            # Header
            ui.Label("PI Data Monitor & Controls", style={"font_size": 18, "color": 0xFF00AAFF})
            ui.Separator()
            
            # Live Data Section
            ui.Label("Live Data (Click for Details):", style={"font_size": 14, "color": 0xFFCCCCCC})
            
            # Create clickable data display for each attribute
            for attr_name, display_name in DISPLAY.items():
                with ui.HStack(height=35):
                    # Status indicator
                    status_rect = ui.Rectangle(width=15, height=15)
                    status_rect.set_style({"background_color": 0xFF00AA00, "border_radius": 3})
                    _live_labels[f"{attr_name}_status"] = status_rect
                    
                    ui.Spacer(width=5)
                    
                    # Clickable button with attribute name and value
                    def make_info_callback(name):
                        return lambda: create_info_window(name)
                    
                    value_button = ui.Button(
                        f"{display_name}: Loading...", 
                        clicked_fn=make_info_callback(attr_name),
                        height=30,
                        style={"background_color": 0xFF333333, "color": 0xFFFFFFFF}
                    )
                    _live_labels[f"{attr_name}_button"] = value_button
            
            ui.Separator()
            
            # Control Buttons Section
            ui.Label("Controls:", style={"font_size": 14, "color": 0xFFCCCCCC})
            
            with ui.HStack():
                ui.Button("Force Refresh", clicked_fn=force_refresh, height=35, width=120)
                ui.Button("Test PNG", clicked_fn=test_png, height=35, width=120)
            
            with ui.HStack():
                ui.Button("Diagnostics", clicked_fn=diag, height=35, width=120)
                
                def toggle_monitoring():
                    global _task
                    if _task and not _task.done():
                        stop()
                    else:
                        start_monitoring_only()
                
                ui.Button("Start/Stop", clicked_fn=toggle_monitoring, height=35, width=120)
            
            ui.Separator()
            
            # Instructions
            ui.Label("How to Use:", style={"font_size": 12, "color": 0xFFAAAAAA})
            ui.Label("Click any data button above for detailed info", style={"font_size": 10})
            ui.Label("Status dots: 🟢=Normal, 🔴=High, 🔵=Low", style={"font_size": 10})
            ui.Label("Data updates every 30 seconds", style={"font_size": 10})
            
            ui.Spacer()

def update_live_display():
    """Update the live data display in the control panel"""
    global _live_labels, _current_values
    
    if not _live_labels:
        return
    
    for attr_name, display_name in DISPLAY.items():
        if attr_name in _current_values:
            value = _current_values[attr_name]
            
            # Update button text
            button_key = f"{attr_name}_button"
            if button_key in _live_labels:
                _live_labels[button_key].text = f"{display_name}: {fmt2(value)}"
            
            # Update status color
            status_key = f"{attr_name}_status"
            if status_key in _live_labels:
                color = get_status_color(attr_name, value)
                # Convert RGBA to hex color for UI
                hex_color = (color[0] << 16) | (color[1] << 8) | color[2] | 0xFF000000
                _live_labels[status_key].set_style({"background_color": hex_color, "border_radius": 3})

def rebuild_material(force=False):
    global _mat_ready
    if _mat_ready and not force:
        return

    stage = get_context().get_stage()
    if force and stage.GetPrimAtPath(MAT_PATH):
        stage.RemovePrim(MAT_PATH)

    mat_prim = stage.DefinePrim(MAT_PATH, "Material")
    mat      = UsdShade.Material(mat_prim)

    uv_reader = UsdShade.Shader.Define(stage, f"{MAT_PATH}/UVReader")
    uv_reader.CreateIdAttr("UsdPrimvarReader_float2")
    uv_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    uv_out = uv_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

    tex = UsdShade.Shader.Define(stage, f"{MAT_PATH}/Tex")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(os.path.join(PNG_DIR, "panel_0.png"))
    tex.CreateInput("st",   Sdf.ValueTypeNames.Float2).ConnectToSource(uv_out)
    tex_rgb = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

    prev = UsdShade.Shader.Define(stage, f"{MAT_PATH}/Preview")
    prev.CreateIdAttr("UsdPreviewSurface")
    prev.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.3)
    prev.CreateInput("metallic",  Sdf.ValueTypeNames.Float).Set(0.0)
    prev.CreateInput("diffuseColor",  Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_rgb)
    prev.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_rgb)
    surf_out = prev.CreateOutput("surface", Sdf.ValueTypeNames.Token)

    mat.CreateSurfaceOutput().ConnectToSource(surf_out)
    UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(TARGET_PRIM)).Bind(mat)
    _mat_ready = True
    print("Enhanced material rebuilt & bound.")

def refresh_texture(lines):
    global _png_idx
    _png_idx = (_png_idx + 1) % 5
    new_path = os.path.join(PNG_DIR, f"panel_{_png_idx}.png")
    _draw_enhanced_png(lines, new_path)

    stage = get_context().get_stage()
    tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    if not tex:
        rebuild_material(force=True)
        tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    tex.GetInput("file").Set(Sdf.AssetPath(new_path))
    print("Enhanced texture updated ->", new_path)

async def _one_cycle():
    global _current_values, _historical_data
    updated, lines = 0, []
    
    try:
        for item in get_element_attributes():
            name, webid = item["Name"], item["WebId"]
            if name in ATTR_MAP:
                val = get_attribute_value(webid)
                cfg = ATTR_MAP[name]
                ok, _ = update_usd_prim(cfg["prim_path"], cfg["attribute"], val)
                
                if ok:
                    updated += 1
                    _current_values[name] = val
                    lines.append(f"{DISPLAY.get(name, name)}: {fmt2(val)}")
                    
                    # Collect historical data occasionally
                    if updated == 1:  # Only for first attribute to avoid too many requests
                        _historical_data[name] = get_historical_data(webid, hours=6)
                        
    except Exception:
        print(">>> _one_cycle error:\n", traceback.format_exc())

    if lines:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        lines.insert(0, f"PI Sync {ts}")
        try:
            refresh_texture(lines)
            update_live_display()  # Update the UI panel with new data
        except Exception:
            print(">>> refresh_texture error:\n", traceback.format_exc())

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] updated {updated} attrs")
    return updated

async def _polling_loop(period=POLL_SEC):
    print("Enhanced async polling loop started")
    try:
        ensure_uv()
        rebuild_material(force=True)
        refresh_texture(["Loading Enhanced Panel..."])
    except Exception:
        print(">>> init error:\n", traceback.format_exc())

    while True:
        try:
            await _one_cycle()
        except Exception:
            print(">>> polling_loop error:\n", traceback.format_exc())
        await asyncio.sleep(period)

def start():
    global _task
    if _task and not _task.done():
        print("Already running.")
        return
    _task = asyncio.ensure_future(_polling_loop(POLL_SEC))
    create_control_panel()
    print(f"Enhanced PI sync with interactive panel started ({POLL_SEC}s)")

def start_monitoring_only():
    """Start only the monitoring task without recreating UI"""
    global _task
    if _task and not _task.done():
        print("Already running.")
        return
    _task = asyncio.ensure_future(_polling_loop(POLL_SEC))
    print(f"PI monitoring restarted ({POLL_SEC}s)")

def stop():
    global _task, _info_window, _control_window
    if _task and not _task.done():
        _task.cancel()
    _task = None
    if _info_window:
        _info_window.destroy()
        _info_window = None
    print("Monitoring stopped.")

def cleanup_all():
    """Clean up all UI windows"""
    global _info_window, _control_window
    stop()
    if _control_window:
        _control_window.destroy()
        _control_window = None
    print("All windows closed.")

def force_refresh():
    asyncio.ensure_future(_one_cycle())

def test_png():
    ensure_uv()
    rebuild_material(force=True)
    # Test with sample data
    _current_values.update({
        "溫度": 23.5,
    	"溫度設定": 22.0,
    	"用電量": 45.2,
    	"電流": 67.8,
    	"內部運算_Output": 125.3
    })
    test_lines = [f"{DISPLAY[k]}: {fmt2(v)}" for k, v in _current_values.items()]
    refresh_texture(test_lines)
    print("Enhanced test PNG generated")

def diag():
    stage = get_context().get_stage()
    tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    print("== Enhanced Diagnostics ==")
    print("PNG_DIR:", PNG_DIR, "files:", os.listdir(PNG_DIR))
    print("mat prim exists:", stage.GetPrimAtPath(MAT_PATH).IsValid())
    print("tex node exists:", bool(tex))
    if tex:
        print("shader file:", tex.GetInput("file").Get())
    bind = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(TARGET_PRIM)).GetDirectBinding().GetMaterial()
    print("bound material:", bind.GetPrim().GetPath() if bind else None)
    print("_task:", _task, "done?", (_task.done() if _task else None))
    print("current values:", _current_values)
    print("info window active:", _info_window is not None)

def close_window():
    global _info_window
    if _info_window:
        try:
            _info_window.destroy()
        except Exception:
            _info_window.visible = False
        _info_window = None

# Auto-start the enhanced system
try: stop()
except: pass
start()




