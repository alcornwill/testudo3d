# ====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ======================= END GPL LICENSE BLOCK ========================

import os
import bpy
import bgl
import blf
import json
import logging
import collections
import mathutils
import math
from math import floor
import random

from mathutils import Vector, Quaternion, Euler

class Vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

text_cursor = Vec2(0, 0)  # used for UI

SEARCH_RANGE = 0.01
ARROW = (Vector((-0.4, -0.4, 0)), Vector((0.4, -0.4, 0)), Vector((0, 0.6, 0)))
# ARROW = (Vector((-0.4, 0.1, 0)), Vector((0.4, 0.1, 0)), Vector((0, 0.45, 0)))
RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)
CYAN = (0.0, 1.0, 1.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
YELLOW = (1.0, 1.0, 0.0, 1.0)
PURPLE = (1.0, 0.0, 1.0, 1.0)
GREY = (0.5, 0.5, 0.5, 1.0)
FONT_ID = 0  # hmm
CUSTOM_PROPERTY_TILE_SIZE_Z = "T3D_tile_size_z"
ADJACENCY_VECTORS = (
    Vector((1, 0, 0)),
    Vector((-1, 0, 0)),
    Vector((0, 1, 0)),
    Vector((0, -1, 0)),
    Vector((0, 0, 1)),
    Vector((0, 0, -1)),
    # could expand to have 8 corners too? (26-bit)
    # or not do vertical adjacency but do corners (8-bit)
)

def get_key(dict_, key, default=None):
    try:
        return dict_[key]
    except KeyError:
        return default

def mid(a, b, c):
    return min(max(a, b), max(b, c), max(a, c))

def weighted_choice(choices):
    total = sum(w for c, w in choices)
    r = random.uniform(0, total)
    upto = 0
    for c, w in choices:
        if upto + w >= r:
            return c
        upto += w
    # shouldn't get here

def magnitude(x, y):
    return math.sqrt(x ** 2 + y ** 2)

def normalize(x, y):
    mag = magnitude(x, y)
    try:
        return x / mag, y / mag
    except ZeroDivisionError:
        return 0

def normalized_XY_to_Zrot(x, y):
    x, y = normalize(x, y)
    rad = math.atan2(-x, y)
    return math.degrees(rad)

def normalized_XY_to_Zrot_rad(x, y):
    x, y = normalize(x, y)
    return math.atan2(-x, y)

def rot_conv(rot):
    # convert blender object rot to format easily compared
    # it would be better if we compared the angle between two rotations
    # todo found it https://docs.blender.org/api/blender_python_api_2_70_release/mathutils.html
    # quaternion .rotation_difference()
    return int(round(math.degrees(rot))) % 360

def round_vector(vec):
    vec.x = round(vec.x)
    vec.y = round(vec.y)
    vec.z = round(vec.z)

def floor_vector(vec):
    vec.x = floor(vec.x)
    vec.y = floor(vec.y)
    vec.z = floor(vec.z)

def update_3dviews():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def draw_line_3d(start, end):
    bgl.glVertex3f(*start)
    bgl.glVertex3f(*end)

def draw_wire(edges, color=WHITE):
    bgl.glBegin(bgl.GL_LINES)
    bgl.glColor4f(*color)
    for start, end in edges:
        draw_line_3d(start, end)
    bgl.glEnd()

def draw_poly(poly, color):
    bgl.glBegin(bgl.GL_POLYGON)
    bgl.glColor4f(*color)
    for i in range(len(poly) - 1):
        draw_line_3d(poly[i], poly[i + 1])
    bgl.glEnd()

def mat_transform(mat, poly):
    return [mat * v for v in poly]

def mat_transform_edges(mat, edges):
    return [(mat * start, mat * end) for start, end in edges]

def draw_text_2d(text, size=20, color=WHITE):
    bgl.glColor4f(*color)
    text_cursor.y -= size + 3  # behaves like command line
    blf.position(FONT_ID, text_cursor.x, text_cursor.y, 0)
    blf.size(FONT_ID, size, 72)
    blf.draw(FONT_ID, text)

def restore_gl_defaults():
    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def delete_object(obj):
    bpy.data.objects.remove(obj, True)
    logging.debug("deleted 1 object")
    update_3dviews()

def delete_objects(objects):
    # use this when you can, saves calling update_3dview
    if len(objects) == 0: return
    for obj in objects:
        bpy.data.objects.remove(obj, True)
    logging.debug("deleted {} objects".format(len(objects)))
    update_3dviews()

def get_group(obj):
    if obj is not None and obj.dupli_group is not None:
        return obj.dupli_group.name

def get_first_group_name(obj):
    if len(obj.users_group) > 0:
        return obj.users_group[0].name

def construct_cube_edges(x_min, x_max, y_min, y_max, z_min, z_max):
    a = Vector((x_min, y_min, z_min))
    b = Vector((x_max, y_min, z_min))
    c = Vector((x_max, y_max, z_min))
    d = Vector((x_min, y_max, z_min))
    e = Vector((x_min, y_min, z_max))
    f = Vector((x_max, y_min, z_max))
    g = Vector((x_max, y_max, z_max))
    h = Vector((x_min, y_max, z_max))

    return [
        (a, b),
        (b, c),
        (c, d),
        (d, a),

        (e, f),
        (f, g),
        (g, h),
        (h, e),

        (a, e),
        (b, f),
        (c, g),
        (d, h)
    ]

def log_created(obj):
    logging.debug("created {}".format(str(obj)))

class Tile3DFinder:
    t3d = None

    def __init__(self):
        self.kd = None
        self.childs = None

        # init
        self.childs = self.t3d.root_obj.children
        size = len(self.childs)
        self.kd = mathutils.kdtree.KDTree(size)

        for i, child in enumerate(self.childs):
            #self.kd.insert(child.location, i)
            self.kd.insert(self.t3d.get_tilepos(child), i)
        self.kd.balance()

    def get_tiles_at(self, pos):
        return [self.childs[index] for pos, index, dist in self.kd.find_range(pos, SEARCH_RANGE)]

class RestoreCursorPos:
    # lets us edit the cursor pos and restore original value nicely
    def __init__(self, t3d):
        self.t3d = t3d
        self.original_pos = None

    def __enter__(self):
        self.original_pos = self.t3d.cursor_pos

    def __exit__(self, exc_type, exc_value, traceback):
        self.t3d.cursor_pos = self.original_pos

class PaintModeState:
    paint = False
    delete = False
    grab = False
    select = False

# tilesize = Vector((1.0, 1.0, 1.0))

class Tilemap3D:
    instance = None

    def __init__(self, logging_level=logging.INFO):
        self.root_obj = None
        self.tilesize_z = 1.0
        self.active_tile3d = None
        self.cursor_pos = Vector((0, 0, 0))
        # self.cursor_tilt = 0  # may be useful for slopes (like rollarcoaster tycoon)
        self.cursor_rot = 0
        self.state = PaintModeState()
        self.select_start_pos = None
        self.select_cube = None
        self.grabbed = None
        # used to restore the properties of tiles when a grab operation is canceled
        self.original_pos = Vector()
        self.original_rot = None
        self.clipboard = None
        self.clipboard_rot = None

        # init
        Tilemap3D.instance = self
        logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging_level)
        Tile3DFinder.t3d = self

    def init(self):
        self.init_root_obj()
        self.construct_select_cube()

    def init_root_obj(self):
        self.root_obj = bpy.context.object
        if self.root_obj is None:
            bpy.ops.object.empty_add()
            self.root_obj = bpy.context.scene.objects.active
        if CUSTOM_PROPERTY_TILE_SIZE_Z not in self.root_obj:
            self.root_obj[CUSTOM_PROPERTY_TILE_SIZE_Z] = 1.0
        self.tilesize_z = self.root_obj[CUSTOM_PROPERTY_TILE_SIZE_Z]  # todo monitor if changed? (get from linked library?)
        logging.debug("initialized root obj")

    def error(self, msg):
        logging.error(msg)

    def set_active_tile3d(self, group):
        self.active_tile3d = group

    def get_active_tile3d(self):
        return self.active_tile3d

    def get_tiles(self):
        finder = Tile3DFinder()
        return finder.get_tiles_at(self.cursor_pos)

    def get_tile3d(self):
        tiles = self.get_tiles()
        if len(tiles) > 0:
            return tiles[0] # assume only one!

    def get_tilepos(self, obj):
        vec = obj.location.copy()
        vec.z /= self.tilesize_z
        return vec

    def set_tilepos(self, obj, vec):
        vec = vec.copy()
        floor_vector(vec)
        vec.z *= self.tilesize_z
        obj.location = vec

    def paint(self):
        tile3d = self.get_active_tile3d()
        if tile3d is not None:
            self.paint_tile(tile3d)

    def delete(self):
        delete_object(self.get_tile3d())

    def adjacent_occupied(self):
        finder = Tile3DFinder()
        return [len(finder.get_tiles_at(self.cursor_pos + vec)) > 0 for vec in ADJACENCY_VECTORS]

    def cdraw(self):
        if self.state.paint:
            self.paint()
        elif self.state.delete:
            self.delete()
        self.construct_select_cube()

    def rotate(self, rot):
        # rotate the cursor and paint
        self.cursor_rot = self.cursor_rot + rot
        logging.debug("rotated cursor {}".format(rot))
        if self.state.grab:
            self.grabbed.rotation_euler[2] = self.grabbed.rotation_euler[2] + math.radians(rot)
        self.cdraw()

    def translate(self, x, y, z):
        # translate the cursor and paint
        translation = Vector((x, y, z))
        logging.debug("moved cursor {}".format(translation))
        mat_rot = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
        translation = mat_rot * translation
        self.cursor_pos = self.cursor_pos + translation
        round_vector(self.cursor_pos)
        if self.state.grab:
            pos = self.get_tilepos(self.grabbed)
            self.set_tilepos(self.grabbed, pos + translation)
        self.cdraw()

    def smart_move(self, x, y, repeat=1):
        # move in x or y, but only if already facing that direction
        mag = magnitude(x, y)
        rot = normalized_XY_to_Zrot(x, y)
        if self.cursor_rot == rot:
            for i in range(repeat):
                self.translate(0, round(mag), 0)
        else:
            self.rotate(rot - self.cursor_rot)

    def on_paint(self):
        self.delete_at(self.cursor_pos)

    def delete_at(self, pos, ignore=None):
        # hmm
        to_delete = []
        finder = Tile3DFinder()
        tiles = finder.get_tiles_at(pos)
        if ignore is not None:
            tiles = [tile for tile in tiles if tile not in ignore]
        delete_objects(tiles) # only one tile per cell now

    def start_grab(self):
        tile3d = self.get_tile3d()
        if tile3d is None: return
        logging.debug("start grab")
        self.state.grab = True
        self.grabbed = tile3d
        self.original_pos = self.cursor_pos
        self.original_rot = tile3d.rotation_euler.z

    def end_grab(self, cancel=False):
        logging.debug("end grab")
        self.state.grab = False
        if cancel:
            rot = self.original_rot
            self.set_tilepos(self.grabbed, self.original_pos)
            self.grabbed.rotation_euler.z = rot
        else:
            # combine with tiles at destination
            pos = self.cursor_pos  # assume objs are at cursor pos (invalid if was multi-cell grab)
            self.delete_at(pos, ignore=[self.grabbed])
        self.grabbed = None
        self.original_rot = None

    def create_tile(self, group, position=None, rotz=None, scale=None):
        bpy.ops.object.group_instance_add(group=group)
        tile3d = bpy.context.scene.objects.active
        tile3d.empty_draw_size = 0.25
        if position is not None:
            # cube.location = position
            self.set_tilepos(tile3d, position)
        if rotz is not None:
            tile3d.rotation_euler = mathutils.Euler((0, 0, math.radians(rotz)))
        if scale is not None:
            tile3d.scale = scale
        return tile3d

    def paint_tile(self, group):
        # creates object with data at cursor
        # create a cube then change it to a whatever
        self.on_paint()
        obj = self.create_tile(group, position=self.cursor_pos, rotz=self.cursor_rot)
        obj.parent = self.root_obj
        logging.debug("created object {}".format(obj.name))
        return obj

    def copy(self):
        tile3d = self.get_tile3d()
        if tile3d:
            self.clipboard = get_group(tile3d)
            self.clipboard_rot = tile3d.rotation_euler.z
        else:
            self.clipboard = None
            self.clipboard_rot = None
        logging.debug("copied {} objects to clipboard".format("1" if self.clipboard else "0"))

    def paste(self):
        if self.clipboard:
            new = self.paint_tile(self.clipboard)
            new.rotation_euler.z = self.clipboard_rot
        logging.debug("pasted {} objects".format("1" if self.clipboard else "0"))

    def start_select(self):
        logging.debug("start box select")
        self.state.select = True
        self.select_start_pos = self.cursor_pos
        self.construct_select_cube()

    def end_select(self):
        logging.debug("end box select")
        orig_cursor_pos = self.cursor_pos
        cube_min, cube_max = self.select_cube_bounds()
        for z in range(int(round(abs(cube_max.z + 1 - cube_min.z)))):
            for y in range(int(round(abs(cube_max.y + 1 - cube_min.y)))):
                for x in range(int(round(abs(cube_max.x + 1 - cube_min.x)))):
                    self.cursor_pos = Vector((cube_min.x + x, cube_min.y + y, cube_min.z + z))
                    self.cdraw()
        self.cursor_pos = orig_cursor_pos
        self.state.select = False
        self.construct_select_cube()

    # todo all select cube stuff should go in PaintMode? (because UI)
    def construct_select_cube(self):
        if self.state.select:
            cube_min, cube_max = self.select_cube_bounds()
        else:
            cube_min, cube_max = self.cursor_pos, self.cursor_pos
        self.select_cube = construct_cube_edges(cube_min.x - 0.5, cube_max.x + 0.5,
                                                cube_min.y - 0.5, cube_max.y + 0.5,
                                                cube_min.z, cube_max.z + 1.0)

    def select_cube_bounds(self):
        start = self.select_start_pos
        end = self.cursor_pos
        cube_min = Vector((min(start.x, end.x), min(start.y, end.y), min(start.z, end.z)))
        cube_max = Vector((max(start.x, end.x), max(start.y, end.y), max(start.z, end.z)))
        return cube_min, cube_max


class Turtle3D(Tilemap3D):
    # turtle graphics (sort-of)
    # https://docs.python.org/3/library/turtle.html
    def __init__(self, *args, **kw):
        Tilemap3D.__init__(self, *args, **kw)
        self.w = 1 # width

    def forward(self, i):
        t = Vector((0, i, 0))
        mat = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
        t = mat * t
        round_vector(t)
        t = self.cursor_pos + t
        if self.state.paint:
            self.line(self.getx(), self.gety(), t.x, t.y)
        self.goto(t.x, t.y)

    def backward(self, i):
        self.forward(-i)

    def left(self, r):
        self.rotate(-r)

    def right(self, r):
        self.rotate(r)

    def setheading(self, r):
        self.cursor_rot = r

    def goto(self, x, y):
        self.cursor_pos = Vector((x, y, 0.0))

    def setx(self, x):
        self.cursor_pos.x = x

    def sety(self, y):
        self.cursor_pos.y = y

    def getx(self):
        return self.cursor_pos.x

    def gety(self):
        return self.cursor_pos.y

    def dot(self):
        self.paint()

    def down(self):
        self.state.paint = True

    def up(self):
        self.state.paint = False

    #def width(self, w):
    #    ...

    def settile3d(self, name):
        self.set_active_tile3d(name)

    def home(self):
        self.goto(0, 0)
        self.setheading(0)

    def position(self):
        return self.cursor_pos

    def heading(self):
        return self.cursor_rot

    def undo(self):
        bpy.ops.ed.undo() # won't undo cursor position

    def isdown(self):
        return self.state.paint

    def plot(self, x, y):
        self.goto(x, y)
        self.dot()

    def circle(self, radius):
        x0 = self.getx()
        y0 = self.gety()
        x = radius
        y = 0
        err = 0

        while x >= y:
            self.plot(x0 + x, y0 + y)
            self.plot(x0 + y, y0 + x)
            self.plot(x0 - y, y0 + x)
            self.plot(x0 - x, y0 + y)
            self.plot(x0 - x, y0 - y)
            self.plot(x0 - y, y0 - x)
            self.plot(x0 + y, y0 - x)
            self.plot(x0 + x, y0 - y)

            y += 1
            if err <= 0:
                err += 2*y + 1
            if err > 0:
                x -= 1
                err -= 2*x + 1
        self.goto(x0, y0)

    def line(self, x1, y1, x2, y2):
        x1 = floor(x1)
        y1 = floor(y1)
        x2 = floor(x2)
        y2 = floor(y2)

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0:
            step = 1 if dy > 0 else -1
            for y in range(y1, y2+step, step):
                self.plot(x1, y)
        elif dy == 0:
            step = 1 if dx > 0 else -1
            for x in range(x1, x2+step, step):
                self.plot(x, y1)
        else:
            if dy < 0:
                dy = -dy
                stepy = -1
            else:
                stepy = 1

            if dx < 0:
                dx = -dx
                stepx = -1
            else:
                stepx = 1

            if dx > dy:
                fraction = dy - (dx >> 1)
                while x1 != x1:
                    if fraction >= 0:
                        y1 = y2 + stepy
                        fraction = fraction - dx
                    x1 = x1 + stepx
                    fraction = fraction + dy
                    self.plot(x1, y1)
            else:
                fraction = dx - (dy >> 1)
                while y1 != y2:
                    if fraction >= 0:
                        x1 = x1 + stepx
                        fraction = fraction - dy
                    y1 = y1 + stepy
                    fraction = fraction + dx
                    self.plot(x1, y1)

    def fill(self):
        state = self.state.paint
        self.state.paint = True
        self.end_select()
        self.state.paint = state

    def clear(self):
        self.state.delete = True
        self.end_select()
        self.state.delete = False
