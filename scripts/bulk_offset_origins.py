import bpy

offset = 1.5

bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    obj.select = True
    bpy.context.scene.cursor_location = obj.location.copy()
    bpy.context.scene.cursor_location.x += offset
    bpy.context.scene.cursor_location.y += offset
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    obj.select = False

