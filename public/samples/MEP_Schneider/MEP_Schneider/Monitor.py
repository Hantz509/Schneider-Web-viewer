# ============================================================
#  PI -> USD -> PNG -> 貼到 3D 物件表面  (Stable Auto Version)
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

BASE_URL = "https://192.168.195.133/piwebapi"
USERNAME = r"WIN-S33DCIIJ3C6\\Administrator"
PASSWORD = "Qazw930323!"
AUTH     = HTTPBasicAuth(USERNAME, PASSWORD)
ATTR_URL = ("https://192.168.195.133/piwebapi/elements/"
            "F1Emo1CwofaPqEWTbP-5QLeDbQ7H901dxc8BGNOQAMKUls9QV0lOLVMzM0M2XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE"
            "/attributes")

# PI 名稱 → USD attribute
ATTR_MAP = {
    "溫度":            {"prim_path": "/World/Monitor/shell", "attribute": "temperature"},
    "溫度設定":        {"prim_path": "/World/Monitor/shell", "attribute": "temperature_setting"},
    "用電量":          {"prim_path": "/World/Monitor/shell", "attribute": "power"},
    "電流":            {"prim_path": "/World/Monitor/shell", "attribute": "current"},
    "內部運算_Output": {"prim_path": "/World/Monitor/shell", "attribute": "calculation_result"},
}
DISPLAY = {
    "溫度":            "Temperature (°C)",
    "溫度設定":        "Set Temp (°C)",
    "用電量":          "Power (kWh)",
    "電流":            "Current (A)",
    "內部運算_Output": "Calc Output",
}

# ---------------- Config ----------------
TARGET_PRIM = "/World/Monitor/shell"      # 要貼圖的 Mesh
MAT_PATH    = "/World/Monitor/PI_PanelMat"
POLL_SEC    = 30.0                        # 輪詢秒數

IMG_SIZE    = (1024, 512)
BG_RGBA     = (0, 0, 0, 180)
FONT_SIZE   = 42
PNG_DIR     = os.path.join(tempfile.gettempdir(), "pi_panel")
os.makedirs(PNG_DIR, exist_ok=True)

# ---------------- Globals ----------------
_session         = requests.Session()
_session.auth    = AUTH
_session.verify  = False

_font            = None
_mat_ready       = False
_png_idx         = 0
_task            = None          # asyncio Task
_stage_sub       = None          # Stage event subscription（可選）

# ============================================================
# 基本工具
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
# UV 保障
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
# PNG & 材質
# ============================================================
def _ensure_font():
    global _font
    if _font: return _font
    try:
        _font = ImageFont.truetype("arial.ttf", FONT_SIZE)
    except Exception:
        _font = ImageFont.load_default()
    return _font

def _draw_png(lines, path):
    img = Image.new("RGBA", IMG_SIZE, BG_RGBA)
    d   = ImageDraw.Draw(img)
    font= _ensure_font()
    y = 30
    for txt in lines:
        d.text((40, y), txt, fill=(255,255,255,255), font=font)
        y += FONT_SIZE + 28
    img.save(path)

def rebuild_material(force=False):
    global _mat_ready
    if _mat_ready and not force:
        return

    stage = get_context().get_stage()
    if force and stage.GetPrimAtPath(MAT_PATH):
        stage.RemovePrim(MAT_PATH)

    mat_prim = stage.DefinePrim(MAT_PATH, "Material")
    mat      = UsdShade.Material(mat_prim)

    # primvar reader
    uv_reader = UsdShade.Shader.Define(stage, f"{MAT_PATH}/UVReader")
    uv_reader.CreateIdAttr("UsdPrimvarReader_float2")
    uv_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    uv_out = uv_reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

    # texture
    tex = UsdShade.Shader.Define(stage, f"{MAT_PATH}/Tex")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(os.path.join(PNG_DIR, "panel_0.png"))
    tex.CreateInput("st",   Sdf.ValueTypeNames.Float2).ConnectToSource(uv_out)
    tex_rgb = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)

    # preview surface
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
    print("Material rebuilt & bound.")

def refresh_texture(lines):
    """畫 PNG 並更新 shader file（輪替檔名避免快取）"""
    global _png_idx
    _png_idx = (_png_idx + 1) % 5
    new_path = os.path.join(PNG_DIR, f"panel_{_png_idx}.png")
    _draw_png(lines, new_path)

    stage = get_context().get_stage()
    tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    if not tex:
        rebuild_material(force=True)
        tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")

    tex.GetInput("file").Set(Sdf.AssetPath(new_path))
    # 若你想要更激進的 cache bust：tex.GetInput("file").Set(Sdf.AssetPath(new_path + f"?t={time.time()}"))
    print("texture updated ->", new_path)

# ============================================================
# 主流程
# ============================================================
async def _one_cycle():
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
                    lines.append(f"{DISPLAY.get(name, name)}: {fmt2(val)}")
    except Exception:
        print(">>> _one_cycle error:\n", traceback.format_exc())

    if lines:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        lines.insert(0, f"PI Sync {ts}")
        try:
            refresh_texture(lines)
        except Exception:
            print(">>> refresh_texture error:\n", traceback.format_exc())

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] updated {updated} attrs")
    return updated

async def _polling_loop(period=POLL_SEC):
    print("Async polling loop started")
    try:
        ensure_uv()
        rebuild_material(force=True)
        refresh_texture(["Loading..."])
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
    """開始自動更新"""
    global _task
    if _task and not _task.done():
        print("Already running.")
        return
    _task = asyncio.ensure_future(_polling_loop(POLL_SEC))
    print(f"Registered async PI sync & texture panel ({POLL_SEC}s)")

def stop():
    """停止自動更新"""
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
    print("Stopped.")

def force_refresh():
    """立即跑一次更新（非阻塞）"""
    asyncio.ensure_future(_one_cycle())

def test_png():
    """不連 PI，直接畫測試圖驗證貼圖是否會換"""
    ensure_uv()
    rebuild_material(force=True)
    refresh_texture(["HELLO PNG", str(time.time())])
    print("test png done")

def diag():
    """診斷目前材質 / 貼圖 / 任務狀態"""
    stage = get_context().get_stage()
    tex = UsdShade.Shader.Get(stage, f"{MAT_PATH}/Tex")
    print("== Diagnose ==")
    print("PNG_DIR:", PNG_DIR, "files:", os.listdir(PNG_DIR))
    print("mat prim exists:", stage.GetPrimAtPath(MAT_PATH).IsValid())
    print("tex node exists:", bool(tex))
    if tex:
        print("shader file:", tex.GetInput("file").Get())
    bind = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(TARGET_PRIM)).GetDirectBinding().GetMaterial()
    print("bound material:", bind.GetPrim().GetPath() if bind else None)
    print("_task:", _task, "done?", (_task.done() if _task else None))

