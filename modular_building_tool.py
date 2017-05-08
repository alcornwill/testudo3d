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
import random
# noinspection PyUnresolvedReferences
from mathutils import Vector, Quaternion, Euler

class Vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

text_cursor = Vec2(0, 0)  # used for UI

SEARCH_RANGE = 0.01  # should be as smaller than min(tilesize.x, tilesize.y)/2
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
CUSTOM_PROPERTY_TYPE = "MBT_type"
CUSTOM_PROPERTY_TILE_SIZE_Z = "MBT_tile_size_z"
METADATA_WEIGHTS = "weights"
METADATA_CUSTOM_ROOMS = "custom_rooms"
METADATA_CUSTOM_GROUPS = "custom_groups"
ADJACENCY_VECTORS = (
    Vector((1, 0, 0)),
    Vector((-1, 0, 0)),
    Vector((0, 1, 0)),
    Vector((0, -1, 0)),
    Vector((0, 0, 1)),
    Vector((0, 0, -1))
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

def create_cube(position=None, rotz=None, scale=None):
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.scene.objects.active
    if position is not None:
        cube.location = position
    if rotz is not None:
        cube.rotation_euler = mathutils.Euler((0, 0, math.radians(rotz)))
    if scale is not None:
        cube.scale = scale
    return cube

def delete_object(obj):
    bpy.data.objects.remove(obj, True)
    logging.debug("deleted 1 object")
    update_3dviews()

def delete_objects(objects):
    # use this when you can, saves calling update_3dview
    if len(objects) == 0: return
    for m in objects:
        bpy.data.objects.remove(m, True)
    logging.debug("deleted {} objects".format(len(objects)))
    update_3dviews()

def get_group_name(meshdata):
    return meshdata[CUSTOM_PROPERTY_TYPE]

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

class Module:
    def __init__(self, data, name, group_name):
        self.data = data
        self.name = name
        self.group_name = group_name

        log_created(self)

    def __str__(self):
        return "{} {}".format(type(self).__name__, self.name)

class ModuleGroup:
    def __init__(self, name, painter, thin=False):
        self.name = name
        self.painter = painter
        self.active = -1
        self.modules = []
        self.thin = thin

        # init
        self.painter.init(self)
        log_created(self)

    def __str__(self):
        return "{} {}".format(type(self).__name__, self.name)

    def active_module(self):
        if self.active >= 0:
            return self.modules[self.active]

    def add_module(self, module_):
        self.active = 0
        self.modules.append(module_)

class RestoreCursorPos:
    # lets us edit the cursor pos and restore original value nicely
    def __init__(self, mbt):
        self.mbt = mbt
        self.original_pos = None

    def __enter__(self):
        self.original_pos = self.mbt.cursor_pos

    def __exit__(self, exc_type, exc_value, traceback):
        self.mbt.cursor_pos = self.original_pos

class Painter:
    mbt = None

    def __init__(self):
        self.group = None

    def __str__(self):
        group_name = self.group.name if self.group else '""'
        return "{} for {}".format(type(self).__name__, group_name)

    def init(self, group):
        self.group = group
        log_created(self)

    def paint(self):
        module_ = self.group.active_module()
        if module_ is not None:
            self.mbt.create_obj(module_.data)

    def delete(self):
        # delete only modules of same type
        match = [x for x in self.mbt.get_modules() if get_group_name(x.data) == self.group.name]
        if self.group.thin:
            # only delete if facing same as cursor rot
            for m in match:
                if round(math.degrees(m.rotation_euler.z)) == self.mbt.cursor_rot:
                    delete_object(m)
                    break
        else:
            if len(match) > 0:
                delete_object(match[0])  # should only be one

    def clear(self):
        self.mbt.clear()

    def draw_ui(self):
        module_ = self.group.active_module()
        if module_ is not None:
            draw_text_2d(module_.name, size=15)
        draw_text_2d(self.group.name, size=25)

class RoomPainter(Painter):
    instance = None  # singleton

    def __init__(self):
        super().__init__()
        RoomPainter.instance = self
        self.custom_rooms = {}
        self.room_modes = [
            (self.active_module, "Active Module"),
            (self.weighted_random, "Weighted Random"),
            (self.dither, "Dither")
        ]

    def init(self, group):
        super().init(group)
        self.group.modules = [None] * 3  # hack

    def paint(self):
        self.room_paint()
        self.repaint_adjacent()  # this is why it is so slow todo paint(width, height)

    def delete(self):
        self.mbt.clear()
        self.repaint_adjacent()

    def room_paint(self):
        self.mbt.clear()
        occupied = self.mbt.adjacent_occupied()
        original_rot = self.mbt.cursor_rot
        # paint walls
        for i in range(4):
            if not occupied[i]:
                vec = ADJACENCY_VECTORS[i]
                self.mbt.cursor_rot = normalized_XY_to_Zrot(vec.x, vec.y)
                wall = self.room_get_module("wall")
                if wall is not None:
                    self.mbt.create_obj(wall.data)
        # paint floor
        if not occupied[5]:
            floor = self.room_get_module("floor")
            if floor is not None:
                self.mbt.create_obj(floor.data)
        # paint ceiling
        if not occupied[4]:
            ceiling = self.room_get_module("ceiling")
            if ceiling is not None:
                self.mbt.create_obj(ceiling.data)
        self.mbt.cursor_rot = original_rot

    def repaint_adjacent(self):
        with RestoreCursorPos(self.mbt):
            orig_curs_pos = self.mbt.cursor_pos
            adjacent_occupied = self.mbt.adjacent_occupied()
            for occupied, vec in zip(adjacent_occupied, ADJACENCY_VECTORS):
                if occupied:
                    self.mbt.cursor_pos = orig_curs_pos + vec
                    self.room_paint()

    def room_get_module(self, type_):
        mode_func, mode_name = self.room_modes[self.group.active]
        return mode_func(type_)

    def active_module(self, type_):
        return self.mbt.module_groups[type_].active_module()

    def weighted_random(self, type_):
        if type_ in self.mbt.weight_info:
            return weighted_choice(self.mbt.weight_info[type_])

    def dither(self, type_):
        group = self.mbt.module_groups[type_]
        if len(group.modules) > 0:
            idx = int(self.mbt.cursor_pos.x + self.mbt.cursor_pos.y + self.mbt.cursor_pos.z)
            idx %= len(group.modules)
            return group.modules[idx]

    def custom_room(self, custom_room, type_):
        module_name = custom_room[type_]
        return self.mbt.modules[module_name]

    @staticmethod
    def add_custom_room(name, custom_room):
        self = RoomPainter.instance
        self.group.modules.append(None)
        self.custom_rooms[name] = custom_room
        self.room_modes.append((lambda type_: self.custom_room(custom_room, type_), name))

    def draw_ui(self):
        mode_func, mode_name = self.room_modes[self.group.active]
        draw_text_2d(mode_name, size=15, color=YELLOW)
        draw_text_2d("room", size=25, color=YELLOW)

class ModuleFinder:
    mbt = None

    def __init__(self):
        self.kd = None
        self.childs = None

        # init
        self.childs = self.mbt.root_obj.children
        size = len(self.childs)
        self.kd = mathutils.kdtree.KDTree(size)

        for i, child in enumerate(self.childs):
            self.kd.insert(child.location, i)
        self.kd.balance()

    def get_modules_at(self, pos):
        return [self.childs[index] for pos, index, dist in self.kd.find_range(pos, SEARCH_RANGE)]

class ModularBuildingModeState:
    paint = False
    clear = False
    delete = False
    grab = False
    select = False

tilesize = Vector((1.0, 1.0, 1.0))

class ModularBuildingTool:
    instance = None

    def __init__(self, logging_level=logging.INFO):
        self.weight_info = {}
        self.metadata = None
        self.root_obj = None
        self.module_groups = collections.OrderedDict()
        self.active_group = 0
        self.modules = {}
        self._cursor_pos = Vector((0, 0, 0))
        # self.cursor_tilt = 0  # may be useful for slopes (like rollarcoaster tycoon)
        self.cursor_rot = 0
        self.state = ModularBuildingModeState()
        self.select_start_pos = None
        self.select_cube = None
        self.grabbed = []
        # used to restore the properties of modules when a grab operation is canceled
        self.original_pos = Vector()
        self.original_rots = []
        self.clipboard = []
        self.clipboard_rots = []

        # init
        ModularBuildingTool.instance = self
        logging.basicConfig(format='MBT: %(levelname)s: %(message)s', level=logging_level)
        Painter.mbt = self
        ModuleFinder.mbt = self

    def get_cursor_pos(self):
        return self._cursor_pos

    def set_cursor_pos(self, value):
        # todo manage internal cursor_pos that is multiplied by tilesize_z
        self._cursor_pos = value

    cursor_pos = property(get_cursor_pos, set_cursor_pos)

    def init(self, metadata_path):
        use_metadata = metadata_path != ""
        if use_metadata:
            try:
                self.init_metadata(metadata_path)
            except FileNotFoundError:
                self.error("metadata file not found {}".format(metadata_path))
                use_metadata = False
            except json.decoder.JSONDecodeError as error:
                self.error('invalid json {}'.format(metadata_path))
                print(error)
                use_metadata = False
        self.init_module_groups()
        self.init_modules()
        if use_metadata:
            try:
                self.init_weights()
                self.init_custom_rooms()
                self.init_custom_groups()
            except (KeyError, ValueError, AttributeError) as error:
                self.error('metadata format error {}'.format(metadata_path))
                print(error)
        self.init_root_obj()
        self.construct_select_cube()

    def init_metadata(self, metadata_path):
        if metadata_path.startswith('//'):
            metadata_path = metadata_path[2:]  # not sure if this is always right
        metadata_path = os.path.abspath(metadata_path)
        with open(metadata_path) as metadata_file:
            self.metadata = json.load(metadata_file)
        logging.debug("initialized metadata")

    def init_module_groups(self):
        # initialize modules list
        # NOTE: would need to override this function if adding custom painter
        self.module_groups['room'] = ModuleGroup("room", RoomPainter())
        self.module_groups['wall'] = ModuleGroup('wall', Painter(), thin=True)
        self.module_groups['floor'] = ModuleGroup('floor', Painter())
        self.module_groups['ceiling'] = ModuleGroup('ceiling', Painter())
        logging.debug("initialized module groups")

    def init_modules(self):
        for mesh in bpy.data.meshes:
            # get type from custom property
            if CUSTOM_PROPERTY_TYPE not in mesh:
                continue
            group_name = get_group_name(mesh)
            try:
                group = self.module_groups[group_name]
            except KeyError:
                # create
                group = ModuleGroup(group_name, Painter())
                self.add_module_group(group)
            module_ = Module(mesh, mesh.name, group_name)
            self.add_module(module_)
            group.add_module(module_)
        logging.debug("initilized modules")

    def init_weights(self):
        # used for generators
        if METADATA_WEIGHTS not in self.metadata: return
        metadata_weights = self.metadata[METADATA_WEIGHTS]
        for mesh_name, weight in metadata_weights.items():
            try:
                mesh = self.modules[mesh_name]
            except KeyError:
                logging.warning('invalid weight. mesh not found "{}"'.format(mesh_name))
                continue
            g_name = mesh.group_name
            try:
                self.weight_info[g_name].append((mesh, weight))
            except KeyError:
                self.weight_info[g_name] = [(mesh, weight)]
        logging.debug("initialized weights")

    def init_custom_rooms(self):
        if METADATA_CUSTOM_ROOMS not in self.metadata: return
        metadata_custom_rooms = self.metadata[METADATA_CUSTOM_ROOMS]
        for name, value in metadata_custom_rooms.items():
            RoomPainter.add_custom_room(name, value)
        logging.debug("initialized custom rooms")

    def init_custom_groups(self):
        custom_groups = {}
        if METADATA_CUSTOM_GROUPS in self.metadata:
            custom_groups = self.metadata[METADATA_CUSTOM_GROUPS]
        for name, group_prop in custom_groups.items():
            if name not in self.module_groups:
                logging.warning("custom groups: {} not a module group".format(name))
                continue
            thin = get_key(group_prop, 'thin', False)
            group = self.module_groups[name]
            group.thin = thin
        logging.debug("initialized custom groups")

    def init_root_obj(self):
        self.root_obj = bpy.context.object
        if self.root_obj is None:
            bpy.ops.object.empty_add()
            self.root_obj = bpy.context.scene.objects.active
        if CUSTOM_PROPERTY_TILE_SIZE_Z not in self.root_obj:
            self.root_obj[CUSTOM_PROPERTY_TILE_SIZE_Z] = 1.0
        logging.debug("initialized root obj")

    def error(self, msg):
        logging.error(msg)

    def set_active_group_name(self, name):
        if name not in self.module_groups: return
        keys = list(self.module_groups.keys())
        self.active_group = keys.index(name)

    def set_active_module_name(self, name):
        group = self.get_active_group()
        for i, module_ in enumerate(group.modules):
            if module_.name == name:
                group.active = i

    def add_module_group(self, group):
        self.module_groups[group.name] = group

    def add_module(self, module_):
        self.modules[module_.name] = module_

    def get_modules(self):
        finder = ModuleFinder()
        return finder.get_modules_at(self.cursor_pos)

    def set_active_group(self, i):
        self.active_group = mid(0, i, len(self.module_groups) - 1)

    def get_active_group(self):
        if len(self.module_groups) > 0:
            values = list(self.module_groups.values())
            return values[self.active_group]

    def get_active_module(self):
        act_g = self.get_active_group()
        if act_g is not None:
            return act_g.modules[act_g.active]

    def clear(self):
        delete_objects(self.get_modules())

    def adjacent_occupied(self):
        finder = ModuleFinder()
        return [len(finder.get_modules_at(self.cursor_pos + vec)) > 0 for vec in ADJACENCY_VECTORS]

    def cdraw(self):
        group = self.get_active_group()
        if self.state.paint:
            group.painter.paint()
        elif self.state.delete:
            group.painter.delete()
        elif self.state.clear:
            group.painter.clear()
        self.construct_select_cube()

    def rotate(self, rot):
        # rotate the cursor and paint
        self.cursor_rot = self.cursor_rot + rot
        logging.debug("rotated cursor {}".format(rot))
        for x in self.grabbed:
            x.rotation_euler[2] = x.rotation_euler[2] + math.radians(rot)
        self.cdraw()

    def translate(self, x, y, z):
        # translate the cursor and paint
        translation = Vector((x, y, z))
        logging.debug("moved cursor {}".format(translation))
        mat_rot = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
        translation = mat_rot * translation
        self.cursor_pos = self.cursor_pos + translation
        round_vector(self.cursor_pos)
        for x in self.grabbed:
            x.location = x.location + translation
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

    def on_paint(self, module_):
        self.on_paint_at(self.cursor_pos, self.cursor_rot, module_)

    def on_paint_at(self, pos, rot, module_):
        # call this when creating or moving a module. it replaces overlapping modules
        # 'blend' would be better name? combines src with dst
        to_delete = []
        g_to = get_group_name(module_.data)
        finder = ModuleFinder()
        dest_modules = finder.get_modules_at(pos)
        for x in dest_modules:
            g_from = get_group_name(x.data)
            if g_to == g_from and x != module_:
                # module is already occupied with module of same group, may have to delete
                g = self.module_groups[g_to]
                if g.thin:
                    # only delete if x has same rotation as m (rounded to nearest ordinal direction...)
                    if rot_conv(x.rotation_euler.z) != rot:
                        continue  # don't delete existing
                # delete existing module
                to_delete.append(x)
                break  # should only be one
        delete_objects(to_delete)

    def start_grab(self):
        logging.debug("start grab")
        self.state.grab = True
        self.grabbed = self.get_modules()
        self.original_pos = self.cursor_pos
        for x in self.grabbed:
            self.original_rots.append(x.rotation_euler.z)

    def end_grab(self, cancel=False):
        logging.debug("end grab")
        self.state.grab = False
        if cancel:
            for x in range(len(self.grabbed)):
                # reset transform of grabbed
                o = self.grabbed[x]
                rot = self.original_rots[x]
                o.location = self.original_pos
                o.rotation_euler.z = rot
        else:
            # combine with modules at destination
            pos = self.cursor_pos  # assume objs are at cursor pos (invalid if was multi-cell grab)
            for g in self.grabbed:
                self.on_paint_at(pos, rot_conv(g.rotation_euler.z), g)
        self.grabbed.clear()
        self.original_rots.clear()

    def create_obj(self, data):
        # creates object with data at cursor
        # create a cube then change it to a whatever
        obj = create_cube(position=self.cursor_pos, rotz=self.cursor_rot)
        cube = obj.data
        obj.data = data
        obj.name = data.name
        bpy.data.meshes.remove(cube, True)  # clean up the cube mesh data
        obj.parent = self.root_obj
        logging.debug("created object {}".format(data.name))
        self.on_paint(obj)
        return obj

    def copy(self):
        modules = self.get_modules()
        self.clipboard = [obj.data for obj in modules]
        self.clipboard_rots.clear()
        for x in modules:
            self.clipboard_rots.append(x.rotation_euler.z)
        logging.debug("copied {} objects to clipboard".format(len(self.clipboard)))

    def paste(self):
        for x in range(len(self.clipboard)):
            data = self.clipboard[x]
            new = self.create_obj(data)
            new.rotation_euler.z = self.clipboard_rots[x]
        logging.debug("pasted {} objects".format(len(self.clipboard)))

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

    # todo all select cube stuff should go in ModularBuildingMode? (because UI)
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

    # human API stuff
    def delete(self):
        self.state.delete = True
        self.cdraw()
        self.state.delete = False

    def paint(self):
        self.state.paint = True
        self.cdraw()
        self.state.paint = False

    def fill(self):
        self.state.paint = True
        self.end_select()
        self.state.paint = False
