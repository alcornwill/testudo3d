
import logging
from math import radians
import bpy
from .turtle3d import Turtle3D

class AutoTiler3D(Turtle3D):
    def __init__(self):
        Turtle3D.__init__(self)
        self.cursor.tile3d = 'Terrain1'
        # would be nice to change draw 2D callback to change color
        # Cursor.draw_2d()?

    def create_empty(self):
        bpy.ops.object.empty_add(type='PLAIN_AXES')
        empty = bpy.context.scene.objects.active
        empty.empty_draw_size = 0.25
        empty.pos = self.cursor.pos
        empty.rot = radians(self.cursor.rot)
        empty.parent = self.root_obj
        logging.debug("created object {}".format(empty.name))
        return empty

    def paint(self):
        self.delete()
        self.create_empty()
