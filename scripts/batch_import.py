import os
import bpy

directory = "C:\\path\\to\\models"

for filename in os.listdir(directory):
    if not filename.endswith('.obj'): continue
    filepath = os.path.join(directory, filename)
    bpy.ops.import_scene.obj(filepath = filepath, use_split_objects = False, split_mode = 'OFF')