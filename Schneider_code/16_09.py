# ============================================================
#  PI -> USD -> PNG -> Apply to 3D Object Surface (Final Stable Solution)
# ============================================================

import asyncio, datetime, os, tempfile, time, traceback
import requests, urllib3
from decimal import Decimal, ROUND_HALF_UP
from requests.auth import HTTPBasicAuth

from omni.usd import get_context
from pxr import Sdf, UsdShade, UsdGeom

# ---------------- Pillow ----------------
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    import omni.kit.pipapi as pipapi
    pipapi.install("Pillow")
    from PIL import Image, ImageDraw, ImageFont

# ---------------- PI Web API ----------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USERNAME = r"win-lqin09i7rg4\administrator"
PASSWORD = "Brungy509@"
AUTH     = HTTPBasicAuth(USERNAME, PASSWORD)

# Define BASE_URL properly
BASE_URL = "https://192.168.74.128/piwebapi"
ATTR_URL = f"{BASE_URL}/elements/F1EmQmqOHC3i_kyP3ytLaQ6cSACt0PThFj8BGgrwAMKdv39AV0lOLUxRSU4wOUk3Ukc0XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE/attributes"

# PI name → USD attribute - Modified to include temp_01 through temp_11
ATTR_MAP = {
    "temperature":         {"prim_path": "/World/P5D_panel/Main_NS800N_/Geometry/C063N4FM_3D_simplified_0/HANDLE_ASSY_C063N320FM_3D_23/HANDLE_ASSY_C063N320FM_24/Mesh_11", "attribute": "temp_01"},
    "TemperatureSetpoint":         {"prim_path": "/World/P5D_panel/RD_district_NS800N/Geometry/C063N4FM_3D_simplified_0/COVER_ASSY_C063N320FM_3D_21/COVER_ASSY_C063N320FM_C_1_22/Mesh_10", "attribute": "temp_02"},
    "PowerUsage":         {"prim_path": "/World/P5D_panel/AC5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_03"},
    "Current":         {"prim_path": "/World/P5D_panel/E5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_04"},
    "internalCalculOutput":         {"prim_path": "/World/P5D_panel/R5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_05"},
    "temp_06":         {"prim_path": "/World/P5D_panel/L5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_06"},
    "temp_07":         {"prim_path": "/World/P5D_panel/SC3_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_07"},
    "temp_08":         {"prim_path": "/World/P5D_panel/SC1_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_08"},
    "temp_09":         {"prim_path": "/World/P5D_panel/SC2_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_09"},
    "temp_10":         {"prim_path": "/World/P5D_panel/AC1_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_10"},
    "temp_11":         {"prim_path": "/World/P5D_panel/AC2_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_11"},
}

# Fixed display labels
STATIC_LABELS = [
    "Temp 01 (°C):",
    "Temp 02 (°C):",
    "Temp 03 (°C):",
    "Temp 04 (°C):",
    "Temp 05 (°C):",
    "Temp 06 (°C):",
    "Temp 07 (°C):",
    "Temp 08 (°C):",
    "Temp 09 (°C):",
    "Temp 10 (°C):",
    "Temp 11 (°C):",
]

# ---------------- Config ----------------
TARGET_PRIM = "/World/Monitor/shell"      # Mesh to apply texture to
MAT_PATH    = "/World/Monitor/PI_PanelMat"
POLL_SEC    = 30.0

# Modified image size to be taller to accommodate 11 temperature readings
IMG_SIZE    = (1024, 768)
BG_RGBA     = (0, 0, 0, 180)
FONT_SIZE   = 45
PNG_DIR     = os.path.join(tempfile.gettempdir(), "pi_panel")
os.makedirs(PNG_DIR, exist_ok=True)

# ---------------- Globals ----------------
_session         = requests.Session()
_session.auth    = AUTH
_session.verify  = False

_font            = None
_mat_ready       = False
_last_values     = {}
_texture_path    = None
_task            = None
_stage_sub       = None

# ============================================================
# Basic Tools
# ============================================================
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

# ============================================================
# UV Assurance
# ============================================================
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

    st = pv_api.CreatePrimvar("st",
                              Sdf.ValueTypeNames.TexCoord2fArray,
                              UsdGeom.Tokens.vertex)
    st.Set(uvs)
    print("UV created (planar).")
    return True

# ============================================================
# PNG & Material
# ============================================================
def _ensure_font():
    global _font
    if _font: return _font
    try:
        _font = ImageFont.truetype("arial.ttf", FONT_SIZE)
    except Exception:
        _font = ImageFont.load_default()
    return _font

def _draw_png(values_dict, timestamp, path):
    """Draw PNG with static labels and dynamic values"""
    img = Image.new("RGBA", IMG_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _ensure_font()
    
    # Simple design
    corner_radius = 15
    bg_color = (35, 35, 35, 200)
    text_color = (255, 255, 255, 255)
    
    margin = 8
    x1, y1 = margin, margin
    x2, y2 = IMG_SIZE[0] - margin, IMG_SIZE[1] - margin
    
    temp_img = Image.new("RGBA", IMG_SIZE, (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.rounded_rectangle([x1, y1, x2, y2], radius=corner_radius, fill=bg_color)
    
    img = Image.alpha_composite(img, temp_img)
    d = ImageDraw.Draw(img)
    
    # Header
    header = f"PI Sync {timestamp}"
    d.text((40, 30), header, fill=text_color, font=font)
    
    # Temperature readings
    y = 92
    line_spacing = 62
    
    ordered_attrs = ["temperature", "TemperatureSetpoint", "PowerUsage", "Current", 
                    "internalCalculOutput", "temp_06", "temp_07", "temp_08", 
                    "temp_09", "temp_10", "temp_11"]
    
    for i, attr_name in enumerate(ordered_attrs):
        if i < len(STATIC_LABELS):
            label = STATIC_LABELS[i]
            value = values_dict.get(attr_name, "N/A")
            if value != "N/A":
                value = fmt2(value)
            line = f"{label} {value}"
            d.text((40, y), line, fill=text_color, font=font)
            y += line_spacing
    
    # Simple save - no fancy file operations
    img.save(path, "PNG")
    print(f"PNG created: {path}")

def rebuild_material(force=False):
    """Create material with single stable texture file"""
    global _mat_ready, _texture_path
    if _mat_ready and not force:
        return

    # Set up the texture path
    _texture_path = os.path.join(PNG_DIR, "panel_display.png")

    stage = get_context().get_stage()
    if force and stage.GetPrimAtPath(MAT_PATH):
        stage.RemovePrim(MAT_PATH)

    mat_prim = stage.DefinePrim(MAT_PATH, "Material")
    mat = UsdShade.Material(mat_prim)

    # primvar reader
    uv_reader = UsdShade.Shader.Define(stage, f"{MAT_PATH}/UVReader")
    uv_reader.CreateIdAttr("UsdPrimvarReader_float2")
    uv_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    uv_out = uv_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

    # texture
    tex = UsdShade.Shader.Define(stage, f"{MAT_PATH}/Tex")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(_texture_path)
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv_out)
    tex_rgb = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

    # preview surface
    prev = UsdShade.Shader.Define(stage, f"{MAT_PATH}/Preview")
    prev.CreateIdAttr("UsdPreviewSurface")
    prev.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.3)
    prev.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    prev.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_rgb)
    prev.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_rgb)
    surf_out = prev.CreateOutput("surface", Sdf.ValueTypeNames.Token)

    mat.CreateSurfaceOutput().ConnectToSource(surf_out)

    UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(TARGET_PRIM)).Bind(mat)

    _mat_ready = True
    print("Material created (stable PNG method).")

def refresh_texture(values_dict, force_update=False):
    """Update texture - ONLY when values actually change"""
    global _last_values
    
    # Compare only the numeric values (not labels, not timestamp)
    values_only = {k: fmt2(v) for k, v in values_dict.items()}
    last_values_only = {k: fmt2(v) for k, v in _last_values.items()}
    
    if values_only == last_values_only and not force_update:
        print("Sensor values unchanged, keeping current display")
        return
    
    print("Sensor values changed, updating display...")
    
    # Create the new texture
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    _draw_png(values_dict, timestamp, _texture_path)
    
    # Store current values
    _last_values = values_dict.copy()
    
    print(f"Display updated with new sensor data at {timestamp}")

# ============================================================
# Main Process
# ============================================================
async def _one_cycle():
    """Process one update cycle"""
    updated = 0
    values_dict = {}
    
    ordered_attrs = ["temperature", "TemperatureSetpoint", "PowerUsage", "Current", 
                    "internalCalculOutput", "temp_06", "temp_07", "temp_08", 
                    "temp_09", "temp_10", "temp_11"]
    
    try:
        all_attrs = {item["Name"]: item["WebId"] for item in get_element_attributes()}
        
        for name in ordered_attrs:
            if name in all_attrs and name in ATTR_MAP:
                webid = all_attrs[name]
                val = get_attribute_value(webid)
                cfg = ATTR_MAP[name]
                ok, _ = update_usd_prim(cfg["prim_path"], cfg["attribute"], val)
                if ok:
                    updated += 1
                    values_dict[name] = val
    except Exception:
        print(">>> _one_cycle error:\n", traceback.format_exc())

    if values_dict:
        try:
            refresh_texture(values_dict)
        except Exception:
            print(">>> refresh_texture error:\n", traceback.format_exc())

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] processed {updated} sensors")
    return updated

async def _polling_loop(period=POLL_SEC):
    print("Starting PI monitoring with stable PNG display")
    try:
        ensure_uv()
        rebuild_material(force=True)
        # Initial display
        test_values = {}
        ordered_attrs = ["temperature", "TemperatureSetpoint", "PowerUsage", "Current", 
                        "internalCalculOutput", "temp_06", "temp_07", "temp_08", 
                        "temp_09", "temp_10", "temp_11"]
        for attr in ordered_attrs:
            test_values[attr] = 0.0
        refresh_texture(test_values, force_update=True)
    except Exception:
        print(">>> init error:\n", traceback.format_exc())

    while True:
        try:
            await _one_cycle()
        except Exception:
            print(">>> polling_loop error:\n", traceback.format_exc())
        await asyncio.sleep(period)

# ============================================================
# Public API
# ============================================================
def start():
    """Start automatic updates"""
    global _task
    if _task and not _task.done():
        print("Already running.")
        return
    _task = asyncio.ensure_future(_polling_loop(POLL_SEC))
    print(f"Started PI monitoring ({POLL_SEC}s intervals) - Stable PNG Display")

def stop():
    """Stop automatic updates"""
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
    print("Stopped.")

def force_refresh():
    """Run one update cycle immediately (non-blocking)"""
    asyncio.ensure_future(_one_cycle())

def test_png():
    """Generate test texture without connecting to PI"""
    ensure_uv()
    rebuild_material(force=True)
    test_values = {}
    ordered_attrs = ["temperature", "TemperatureSetpoint", "PowerUsage", "Current", 
                    "internalCalculOutput", "temp_06", "temp_07", "temp_08", 
                    "temp_09", "temp_10", "temp_11"]
    for i, attr in enumerate(ordered_attrs):
        test_values[attr] = 25.0 + i * 2.5
    
    refresh_texture(test_values, force_update=True)
    print("Test display created successfully")

def diag():
    """Diagnostic function"""
    stage = get_context().get_stage()
    tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    print("== Final Stable PNG Diagnose ==")
    print("Texture path:", _texture_path)
    if _texture_path and os.path.exists(_texture_path):
        print(f"Texture file exists, size: {os.path.getsize(_texture_path)} bytes")
    else:
        print("Texture file missing")
    print("Material exists:", stage.GetPrimAtPath(MAT_PATH).IsValid())
    print("Texture shader exists:", bool(tex))
    if tex:
        print("Shader file path:", tex.GetInput("file").Get())
    bind = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(TARGET_PRIM)).GetDirectBinding().GetMaterial()
    print("Material bound:", bind.GetPrim().GetPath() if bind else None)
    print("Task running:", _task and not _task.done())
    print("Last sensor values:", {k: fmt2(v) for k, v in _last_values.items()})

# Auto-start when script is loaded
start()