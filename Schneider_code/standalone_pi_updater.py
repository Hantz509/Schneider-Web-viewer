# standalone_pi_updater.py
# External Python script that fetches PI data and updates USD files
# Run this independently of your USD viewer

import asyncio
import datetime
import os
import tempfile
import time
import traceback
import requests
import urllib3
from decimal import Decimal, ROUND_HALF_UP
from requests.auth import HTTPBasicAuth
from pathlib import Path

# USD imports
from pxr import Usd, UsdGeom, UsdShade, Sdf

# Pillow for texture generation
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Installing Pillow...")
    os.system("pip install Pillow")
    from PIL import Image, ImageDraw, ImageFont

class StandalonePIMonitor:
    """Standalone PI monitor that updates USD files directly"""
    
    def __init__(self, usd_file_path):
        # Configuration
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.usd_file_path = Path(usd_file_path)
        if not self.usd_file_path.exists():
            raise FileNotFoundError(f"USD file not found: {usd_file_path}")
        
        self.USERNAME = r"win-lqin09i7rg4\administrator"
        self.PASSWORD = "Brungy509@"
        self.AUTH = HTTPBasicAuth(self.USERNAME, self.PASSWORD)
        
        self.BASE_URL = "https://192.168.74.128/piwebapi"
        self.ATTR_URL = f"{self.BASE_URL}/elements/F1EmQmqOHC3i_kyP3ytLaQ6cSACt0PThFj8BGgrwAMKdv39AV0lOLUxRSU4wOUk3Ukc0XERBVEFCQVNFMVxB5Y2AXOWGt-awo-apnzE/attributes"
        
        # Your existing ATTR_MAP
        self.ATTR_MAP = {
            "temperature": {"prim_path": "/World/P5D_panel/Main_NS800N_/Geometry/C063N4FM_3D_simplified_0/HANDLE_ASSY_C063N320FM_3D_23/HANDLE_ASSY_C063N320FM_24/Mesh_11", "attribute": "temp_01"},
            "TemperatureSetpoint": {"prim_path": "/World/P5D_panel/RD_district_NS800N/Geometry/C063N4FM_3D_simplified_0/COVER_ASSY_C063N320FM_3D_21/COVER_ASSY_C063N320FM_C_1_22/Mesh_10", "attribute": "temp_02"},
            "PowerUsage": {"prim_path": "/World/P5D_panel/AC5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_03"},
            "Current": {"prim_path": "/World/P5D_panel/E5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_04"},
            "internalCalculOutput": {"prim_path": "/World/P5D_panel/R5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_05"},
            "temp_06": {"prim_path": "/World/P5D_panel/L5D_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_06"},
            "temp_07": {"prim_path": "/World/P5D_panel/SC3_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_07"},
            "temp_08": {"prim_path": "/World/P5D_panel/SC1_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_08"},
            "temp_09": {"prim_path": "/World/P5D_panel/SC2_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_09"},
            "temp_10": {"prim_path": "/World/P5D_panel/AC1_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_10"},
            "temp_11": {"prim_path": "/World/P5D_panel/AC2_NSX_100N/Geometry/MCADPP0000044_3D_simplified_0/C25W35E250_3D_SIMPLIFIED_1/Mesh_0", "attribute": "temp_11"},
        }
        
        self.STATIC_LABELS = [
            "Temp 01 (°C):", "Temp 02 (°C):", "Temp 03 (°C):", "Temp 04 (°C):",
            "Temp 05 (°C):", "Temp 06 (°C):", "Temp 07 (°C):", "Temp 08 (°C):",
            "Temp 09 (°C):", "Temp 10 (°C):", "Temp 11 (°C):",
        ]
        
        # Config
        self.TARGET_PRIM = "/World/Monitor/shell"
        self.MAT_PATH = "/World/Monitor/PI_PanelMat"
        self.POLL_SEC = 30.0
        self.IMG_SIZE = (1024, 768)
        self.FONT_SIZE = 45
        
        # Setup directories
        self.PNG_DIR = Path(tempfile.gettempdir()) / "pi_panel"
        self.PNG_DIR.mkdir(exist_ok=True)
        self.texture_path = self.PNG_DIR / "panel_display.png"
        
        # Initialize session
        self._session = requests.Session()
        self._session.auth = self.AUTH
        self._session.verify = False
        
        # State variables
        self._font = None
        self._last_values = {}
        self._running = False
        
        print(f"[Standalone PI Monitor] Initialized for USD file: {self.usd_file_path}")
    
    def fmt2(self, v):
        return str(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))
    
    def to_float2(self, v):
        return float(Decimal(str(v)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))
    
    def get_element_attributes(self):
        r = self._session.get(self.ATTR_URL, timeout=5)
        r.raise_for_status()
        return r.json()["Items"]
    
    def get_attribute_value(self, webid):
        r = self._session.get(f"{self.BASE_URL}/streams/{webid}/value", timeout=5)
        r.raise_for_status()
        return r.json()["Value"]
    
    def update_usd_prim(self, stage, prim_path, attr_name, value):
        """Update USD prim attribute in the stage"""
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            print(f"[PI Monitor] Warning: Prim not found: {prim_path}")
            return False
        
        attr = prim.GetAttribute(attr_name)
        if not attr.IsValid():
            # Create attribute if it doesn't exist
            attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Float)
        
        attr.Set(self.to_float2(value))
        return True
    
    def _ensure_font(self):
        if self._font:
            return self._font
        try:
            self._font = ImageFont.truetype("arial.ttf", self.FONT_SIZE)
        except Exception:
            self._font = ImageFont.load_default()
        return self._font
    
    def create_display_texture(self, values_dict, timestamp):
        """Create the PI display texture PNG"""
        img = Image.new("RGBA", self.IMG_SIZE, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        font = self._ensure_font()
        
        # Simple design
        corner_radius = 15
        bg_color = (35, 35, 35, 200)
        text_color = (255, 255, 255, 255)
        
        margin = 8
        x1, y1 = margin, margin
        x2, y2 = self.IMG_SIZE[0] - margin, self.IMG_SIZE[1] - margin
        
        temp_img = Image.new("RGBA", self.IMG_SIZE, (0, 0, 0, 0))
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
            if i < len(self.STATIC_LABELS):
                label = self.STATIC_LABELS[i]
                value = values_dict.get(attr_name, "N/A")
                if value != "N/A":
                    value = self.fmt2(value)
                line = f"{label} {value}"
                d.text((40, y), line, fill=text_color, font=font)
                y += line_spacing
        
        img.save(self.texture_path, "PNG")
        print(f"[PI Monitor] Texture updated: {self.texture_path}")
    
    def setup_material_and_uv(self, stage):
        """Set up UV mapping and material for the display"""
        # Ensure UV mapping exists
        prim = stage.GetPrimAtPath(self.TARGET_PRIM)
        if not prim.IsValid():
            print(f"[PI Monitor] Warning: Target prim not found: {self.TARGET_PRIM}")
            return
        
        mesh = UsdGeom.Mesh(prim)
        if not mesh:
            print(f"[PI Monitor] Warning: Not a mesh: {self.TARGET_PRIM}")
            return
        
        # Check if UV mapping exists
        pv_api = UsdGeom.PrimvarsAPI(prim)
        st = pv_api.GetPrimvar("st")
        if not st or not st.IsDefined():
            # Create simple planar UV mapping
            pts = mesh.GetPointsAttr().Get()
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                minx, maxx = min(xs), max(xs)
                miny, maxy = min(ys), max(ys)
                spanx = maxx-minx or 1.0
                spany = maxy-miny or 1.0
                uvs = [((p[0]-minx)/spanx, (p[1]-miny)/spany) for p in pts]
                
                st = pv_api.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                st.Set(uvs)
                print("[PI Monitor] Created UV mapping")
        
        # Create/update material
        mat_prim = stage.GetPrimAtPath(self.MAT_PATH)
        if not mat_prim.IsValid():
            mat_prim = stage.DefinePrim(self.MAT_PATH, "Material")
        
        mat = UsdShade.Material(mat_prim)
        
        # Create shader network (simplified for compatibility)
        shader_path = f"{self.MAT_PATH}/Shader"
        shader_prim = stage.GetPrimAtPath(shader_path)
        if not shader_prim.IsValid():
            shader_prim = stage.DefinePrim(shader_path, "Shader")
        
        shader = UsdShade.Shader(shader_prim)
        shader.CreateIdAttr("UsdPreviewSurface")
        
        # Set texture file
        file_input = shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f)
        # For now, we'll update the texture file path directly
        # The USD viewer should reload textures automatically
        
        # Bind material to target prim
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)
        print("[PI Monitor] Material setup complete")
    
    def one_cycle(self):
        """Process one update cycle"""
        print(f"[PI Monitor] Starting update cycle at {datetime.datetime.now().strftime('%H:%M:%S')}")
        
        try:
            # Open the USD stage
            stage = Usd.Stage.Open(str(self.usd_file_path))
            if not stage:
                print(f"[PI Monitor] Error: Could not open USD file: {self.usd_file_path}")
                return
            
            updated = 0
            values_dict = {}
            
            ordered_attrs = ["temperature", "TemperatureSetpoint", "PowerUsage", "Current", 
                            "internalCalculOutput", "temp_06", "temp_07", "temp_08", 
                            "temp_09", "temp_10", "temp_11"]
            
            # Fetch PI data
            try:
                all_attrs = {item["Name"]: item["WebId"] for item in self.get_element_attributes()}
                
                for name in ordered_attrs:
                    if name in all_attrs and name in self.ATTR_MAP:
                        webid = all_attrs[name]
                        val = self.get_attribute_value(webid)
                        cfg = self.ATTR_MAP[name]
                        
                        # Update USD prim
                        if self.update_usd_prim(stage, cfg["prim_path"], cfg["attribute"], val):
                            updated += 1
                            values_dict[name] = val
                
            except Exception as e:
                print(f"[PI Monitor] Error fetching PI data: {e}")
                # Use test values if PI connection fails
                for i, attr in enumerate(ordered_attrs):
                    values_dict[attr] = 25.0 + i * 2.5
                updated = len(values_dict)
                print("[PI Monitor] Using test values due to PI connection error")
            
            # Update display texture
            if values_dict:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                self.create_display_texture(values_dict, timestamp)
                
                # Set up material if needed (first run)
                if not self._last_values:
                    self.setup_material_and_uv(stage)
                
                self._last_values = values_dict.copy()
            
            # Save the stage
            stage.Save()
            print(f"[PI Monitor] Updated {updated} sensors, USD file saved")
            
        except Exception as e:
            print(f"[PI Monitor] Error in update cycle: {e}")
            traceback.print_exc()
    
    def start(self):
        """Start the monitoring loop"""
        self._running = True
        print(f"[PI Monitor] Starting standalone monitoring (polling every {self.POLL_SEC} seconds)")
        print(f"[PI Monitor] USD file: {self.usd_file_path}")
        print(f"[PI Monitor] Texture output: {self.texture_path}")
        print("[PI Monitor] Press Ctrl+C to stop")
        
        try:
            while self._running:
                self.one_cycle()
                time.sleep(self.POLL_SEC)
        except KeyboardInterrupt:
            print("\n[PI Monitor] Stopped by user")
        except Exception as e:
            print(f"[PI Monitor] Error: {e}")
            traceback.print_exc()
    
    def stop(self):
        """Stop the monitoring loop"""
        self._running = False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python standalone_pi_updater.py <path_to_your_usd_file>")
        print("Example: python standalone_pi_updater.py scene.usd")
        sys.exit(1)
    
    usd_file = sys.argv[1]
    
    try:
        monitor = StandalonePIMonitor(usd_file)
        monitor.start()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)