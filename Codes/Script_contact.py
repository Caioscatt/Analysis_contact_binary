import bpy
import math
import sys
import os
from mathutils import Vector

# =====================================================================
# 1. RICEZIONE ARGOMENTI DAL LAUNCHER
# =====================================================================
argv = sys.argv
if "--" in argv:
    args = argv[argv.index("--") + 1:]
    asteroid_name = args[0]
    base_dir = args[1]
    secondary_radius = float(args[2]) # Raggio della seconda sfera variabile
else:
    asteroid_name = "Binary_Analysis"
    base_dir = os.getcwd()
    secondary_radius = 20.0  

r1 = 50.0              # Raggio della sfera fissa principale
overlap = 10.0         # Intersezione fissa di 10 km

# =====================================================================
# 2. PULIZIA SCENA
# =====================================================================
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

# =====================================================================
# 3. CREAZIONE SFERA PRINCIPALE (CENTRO 0,0,0)
# =====================================================================
bpy.ops.mesh.primitive_uv_sphere_add(
    radius=r1, 
    segments=180, 
    ring_count=100,
    location=(0, 0, 0)
)
sphere1 = bpy.context.active_object
sphere1.name = asteroid_name

# =====================================================================
# 4. CREAZIONE SFERA SECONDARIA (LAT 0°, LON 180°) E UNIONE
# =====================================================================
r2 = secondary_radius
if r2 > 0.0:
    lat_rad = math.radians(0.0)
    lon_rad = math.radians(180.0)  # Longitudine 180° -> Asse -X

    # Vettore direzione (Lat 0, Lon 180 -> Vector(-1, 0, 0))
    cx = math.cos(lat_rad) * math.cos(lon_rad)
    cy = math.cos(lat_rad) * math.sin(lon_rad)
    cz = math.sin(lat_rad)
    direction = Vector((cx, cy, cz)).normalized()

    # Distanza tra i centri per mantenere esattamente 10 km di sovrapposizione
    distance = r1 + r2 - overlap
    center2 = direction * distance

    # Creazione della seconda sfera
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=r2,
        segments=180,
        ring_count=100,
        location=center2
    )
    sphere2 = bpy.context.active_object
    sphere2.name = "SecondarySphere"

    # Applicazione del Modificatore Boolean (Union) per fonderle
    bpy.context.view_layer.objects.active = sphere1
    bool_mod = sphere1.modifiers.new(name="BinaryUnion", type='BOOLEAN')
    bool_mod.operation = 'UNION'
    bool_mod.object = sphere2
    bool_mod.solver = 'EXACT'  # Fusione geometrica esatta

    # Rende permanente l'operazione
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)

    # Pulizia della seconda sfera separata
    bpy.data.objects.remove(sphere2, do_unlink=True)

# Smooth shading
for poly in sphere1.data.polygons:
    poly.use_smooth = False

# =====================================================================
# 5. ESPORTAZIONE FILE OBJ COMPATIBILE CON DAMIT
# =====================================================================
shapes_dir = os.path.join(base_dir, "Shapes")
os.makedirs(shapes_dir, exist_ok=True)
obj_path = os.path.join(shapes_dir, f"{asteroid_name}.obj")

bpy.ops.object.select_all(action='DESELECT')
sphere1.select_set(True)
bpy.context.view_layer.objects.active = sphere1

if hasattr(bpy.ops.wm, "obj_export"):
    bpy.ops.wm.obj_export(
        filepath=obj_path,
        forward_axis='X',
        up_axis='Z',
        export_selected_objects=True
    )
else:
    bpy.ops.export_scene.obj(
        filepath=obj_path,
        axis_forward='X',
        axis_up='Z',
        use_selection=True
    )

print(f"[BINARY SCRIPT SUCCESS]: Asteroide Contact Binary generato in {obj_path}")