import bpy
import sys
import os

# ============================================================
# READ INPUT DATA FROM LAUNCHER
# ============================================================
args = sys.argv
args = args[args.index("--") + 1:]

asteroid_name = args[0]
asteroid_file = args[1]
camera_orthoscale = float(args[2])
base_dir = args[3]

# ============================================================
# CLEAN SCENE
# ============================================================
def clean_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

clean_scene()

# ============================================================
# IMPORT ASTEROID
# ============================================================
obj_path = os.path.join(base_dir, asteroid_file)
bpy.ops.wm.obj_import(filepath=obj_path,forward_axis='X',up_axis='Z')
#

asteroid = None
for obj in bpy.context.scene.objects:
    if obj.type == "MESH":
        asteroid = obj
        break

if asteroid is None:
    raise Exception("Asteroid mesh not found")

asteroid.name = asteroid_name

# ============================================================
# CENTER ASTEROID GEOMETRY
# ============================================================
bpy.context.view_layer.objects.active = asteroid
asteroid.select_set(True)
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
asteroid.location = (0, 0, 0)

# ============================================================
# NORMALS + SMOOTH
# ============================================================
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
for poly in asteroid.data.polygons:
    poly.use_smooth = True
for edge in asteroid.data.edges:
    edge.use_edge_sharp = True

# ============================================================
# MATERIAL
# ============================================================
if len(asteroid.data.materials) == 0:
    mat = bpy.data.materials.new("Asteroid_Rock")
    asteroid.data.materials.append(mat)
else:
    mat = asteroid.data.materials[0]

mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()
out = nodes.new("ShaderNodeOutputMaterial")
bsdf = nodes.new("ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1)
bsdf.inputs["Roughness"].default_value = 0.85
bsdf.inputs["Metallic"].default_value = 0.0
links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

# ============================================================
# SUN & CAMERA
# ============================================================
bpy.ops.object.light_add(type="SUN")
sun = bpy.context.object
sun.name = "Sun"
sun.data.energy = 4
sun.data.angle = 0.009
sun.data.shadow_soft_size = 0.2
sun.data.use_shadow = True

bpy.ops.object.camera_add()
cam = bpy.context.object
cam.name = "Observer_Camera"
cam.data.type = "ORTHO"
cam.data.ortho_scale = camera_orthoscale
cam.data.clip_start = 0.1
cam.data.clip_end = 10000
cam.location = (0, -300, 0)
cam.rotation_euler = (1.5708, 0, 0)
bpy.context.scene.camera = cam

# ============================================================
# WORLD & RENDER SETTINGS
# ============================================================
bpy.context.scene.world.use_nodes = True
bg = bpy.context.scene.world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0, 0, 0, 1)
bg.inputs[1].default_value = 0

bpy.context.scene.render.engine = "BLENDER_EEVEE"
bpy.context.scene.view_settings.view_transform = "Standard"
bpy.context.scene.view_settings.look = "None"

# ============================================================
# SAVE TO CACHE
# ============================================================
cache_dir = os.path.join(base_dir, "cache")
os.makedirs(cache_dir, exist_ok=True)

save_path = os.path.join(cache_dir, "object.blend")
bpy.ops.wm.save_as_mainfile(filepath=save_path)
print(f"Scena salvata con successo in cache: {save_path}")