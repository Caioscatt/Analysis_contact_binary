import bpy
import math
import mathutils 
import os
import csv
import sys

# ============================================================
# ARGS & PATHS
# ============================================================
args = sys.argv
args = args[args.index("--") + 1:]
asteroid_name = args[0]
spin_ra = float(args[1])
spin_dec = float(args[2])
base_dir = args[3]

cache_dir = os.path.join(base_dir, "cache")
csv_path = os.path.join(cache_dir, "simulation.csv")
with open(csv_path, "r", newline="") as f:
    simulation = list(csv.DictReader(f))

total_frames = len(simulation)
render_folder = os.path.join(base_dir, "renders", asteroid_name)
os.makedirs(render_folder, exist_ok=True)

# ============================================================
# MATH HELPER: RA/DEC TO ICRF VECTOR
# +X = RA 0, DEC 0
# +Y = RA 90, DEC 0
# +Z = DEC +90 (Polo Nord Celeste)
# ============================================================
def ra_dec_to_vec(ra_deg, dec_deg):
    ra = math.radians(float(ra_deg))
    dec = math.radians(float(dec_deg))
    return mathutils.Vector((
        math.cos(dec) * math.cos(ra),
        math.cos(dec) * math.sin(ra),
        math.sin(dec)
    ))

asteroid = bpy.data.objects.get(asteroid_name)
sun = bpy.data.objects.get("Sun")
cam = bpy.data.objects.get("Observer_Camera")

if asteroid is None or sun is None or cam is None:
    raise Exception("Errore: Oggetti mancanti nella scena Blender.")

base_sun_energy = sun.data.energy

# ============================================================
# RENDER LOOP
# ============================================================
for index, frame in enumerate(simulation, start=1):
    date_str = frame["date"]
    earth_ra = float(frame["earth_ra"])
    earth_dec = float(frame["earth_dec"])
    sun_ra = float(frame["sun_ra"])
    sun_dec = float(frame["sun_dec"])
    
    # Adattamento dinamico della luce alla distanza dal Sole
    try:
        r_sun = float(frame["sun_distance"])
        sun.data.energy = base_sun_energy / (r_sun ** 2)
        base_angle_at_1au = 0.00925 
        sun.data.angle = base_angle_at_1au / r_sun
    except KeyError:
        sun.data.energy = base_sun_energy
        sun.data.angle = 0.00925

    sys.stdout.write(f"\r[Rendering] {index}/{total_frames} (Date: {date_str})")
    sys.stdout.flush()
    

    # 1. Assegnazione diretta del Quaternione dal CSV
    qw = float(frame["qw"])
    qx = float(frame["qx"])
    qy = float(frame["qy"])
    qz = float(frame["qz"])

    asteroid.rotation_mode = "QUATERNION"
    asteroid.rotation_quaternion = mathutils.Quaternion((qw, qx, qy, qz))
    
    # 2. Posizionamento e tracciamento Sole (UP = Polo Nord Celeste +Z)
    S = ra_dec_to_vec(sun_ra, sun_dec).normalized()
    light_dir = -S
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = light_dir.to_track_quat("-Z", "Y")
    
    # 3. Posizionamento e tracciamento Fotocamera (UP = Polo Nord Celeste +Z)
    E = ra_dec_to_vec(earth_ra, earth_dec).normalized()
    cam.location = E * 300
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-E).to_track_quat("-Z", "Y")
    
    bpy.context.scene.camera = cam
    bpy.context.view_layer.update()
    
    # 4. Rendering su file TIFF
    filename = f"{asteroid_name}_{date_str}.tiff"
    output_path = os.path.join(render_folder, filename)
    bpy.context.scene.render.filepath = output_path
    bpy.context.scene.render.image_settings.file_format = "TIFF"
    bpy.context.scene.render.image_settings.color_mode = "BW"
    bpy.context.scene.render.image_settings.color_depth = "16"
    bpy.ops.render.render(write_still=True)

sys.stdout.write("\n")
sys.stdout.flush()
print("Renders completati con successo.")