import os
import bpy

border = 4
dimx = 10
count = 0
x = 0
y = 0
for obj in bpy.data.objects:
    obj.location.x = x
    obj.location.y = y
    count += 1
    x += border
    if count >= dimx:
        y += border
        x = 0
        count = 0