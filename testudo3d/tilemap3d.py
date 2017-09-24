
import builtins
import bpy
import logging
import random
from math import floor, degrees, radians, atan2, sqrt
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.kdtree import KDTree

SEARCH_RANGE = 0.01
CUSTOM_PROP_TILE_SIZE_Z = "t3d_tile_size_z"
CUSTOM_PROP_LAST_CURSOR = 't3d_last_cursor'
ADJACENCY_VECTORS = (
    # DUWSEN
    Vector((0, 1, 0)),
    Vector((1, 0, 0)),
    Vector((0, -1, 0)),
    Vector((-1, 0, 0)),
    Vector((0, 0, 1)),
    Vector((0, 0, -1))
)

def get_key(dict_, key, default=None):
    try:
        return dict_[key]
    except KeyError:
        return default

def any(lst):
    return len(lst) > 0

def roundbase(x, base):
    return int(base * round(float(x)/base))

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
    return sqrt(x ** 2 + y ** 2)

def normalize(x, y):
    mag = magnitude(x, y)
    try:
        return x / mag, y / mag
    except ZeroDivisionError:
        return 0

def normalized_XY_to_Zrot(x, y):
    x, y = normalize(x, y)
    rad = atan2(-x, y)
    return degrees(rad)

def normalized_XY_to_Zrot_rad(x, y):
    x, y = normalize(x, y)
    return atan2(-x, y)

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

def get_first_group_name(obj):
    if len(obj.users_group) > 0:
        return obj.users_group[0].name

def init_object_props():
    def get_pos(self):
        vec = self.location.copy()
        vec.z /= t3d.tilesize_z
        return vec

    def set_pos(self, vec):
        vec = vec.copy()
        vec.z *= t3d.tilesize_z
        self.location = vec

    def get_rot(self):
        return self.rotation_euler.z

    def set_rot(self, rot):
        self.rotation_euler.z = rot

    def get_group(self):
        if self.dupli_group is not None:
            return self.dupli_group.name

    # NOTE: these attribute names may conflict with other addons
    bpy.types.Object.pos = property(get_pos, set_pos)
    bpy.types.Object.rot = property(get_rot, set_rot)
    bpy.types.Object.group = property(get_group)

class Cursor:
    def __init__(self, tile3d=None, pos=None, rot=0):
        self.tile3d = tile3d
        self.pos = pos or Vector()
        self.rot = rot # in degrees

    def get_forward(self):
        return Matrix.Rotation(radians(t3d.cursor.rot), 4, 'Z')

    forward = property(get_forward)

    def copy(self):
        return Cursor(self.tile3d, self.pos.copy(), self.rot)

    def serialize(self):
        return "{tile3d},{x},{y},{z},{rot}".format(
            tile3d=self.tile3d,
            x=self.pos.x,
            y=self.pos.y,
            z=self.pos.z,
            rot=self.rot
        )

    @staticmethod
    def deserialize(str):
        tile3d, x, y, z, rot = str.split(',')
        x = float(x)
        y = float(y)
        z = float(z)
        rot = float(rot)
        return Cursor(tile3d, Vector((x, y, z)), rot)

class GrabData:
    def __init__(self, tile3d):
        self.tile3d = tile3d
        self.orig_pos = tile3d.pos
        self.orig_rot = tile3d.rot

class Clipboard:
    def __init__(self, tile3d):
        self.group = tile3d.group
        self.pos_offset = tile3d.pos - t3d.cursor.pos
        self.rot = tile3d.rot

class Tile3DFinder:
    def __init__(self):
        self.childs = [c for c in t3d.root.children if c.layers[t3d.layer]]
        size = len(self.childs)
        self.kd = KDTree(size)

        for i, child in enumerate(self.childs):
            self.kd.insert(child.pos, i)
        self.kd.balance()

    def get_tiles_at(self, pos):
        return [self.childs[index] for pos, index, dist in self.kd.find_range(pos, SEARCH_RANGE)]

class FinderManager:
    # todo
    # my thinking is that
    # a lot of the time you don't need to reconstruct the KDTree
    # even though you should, because you're looking at different cells
    def __init__(self):
        self.finder = None # also need one for each root
        self.invalidated = False

    def get_tiles_at(self, pos):
        if self.invalidated:
            self.finder = Tile3DFinder()
            self.invalidated = False
        return self.finder.get_tiles_at(pos)

    def invalidate(self):
        self.invalidated = True

class PaintModeState:
    paint = False
    delete = False
    grab = False
    select = False

# tilesize = Vector((1.0, 1.0, 1.0))

class Tilemap3D:
    def __init__(self, logging_level=logging.INFO):
        self.root = None
        self.layer = None # active layer
        self.tilesize_z = 1.0
        self.cursor = Cursor()
        self.state = PaintModeState()
        self.select_start_pos = None
        self.grabbed = None
        self.clipboard = None
        # self.finder = FinderManager()
        self.manual_mode = True # hacky

        # init
        # logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging_level)
        logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging.DEBUG)
        builtins.t3d = self # note: builtin abuse
        bpy.types.Scene.t3d = self

    def get_layer(self):
        return bpy.context.scene.t3d_prop.user_layer
    user_layer = property(get_layer)

    def init(self):
        self.init_root_obj()
        self.construct_select_cube()
        self.layer = self.user_layer

    def init_root_obj(self):
        self.root = bpy.context.object
        if self.root is None:
            bpy.ops.object.empty_add()
            self.root = bpy.context.object
            self.root.name = 'Root'
        if CUSTOM_PROP_TILE_SIZE_Z not in self.root:
            self.root[CUSTOM_PROP_TILE_SIZE_Z] = 1.0
        self.tilesize_z = self.root[CUSTOM_PROP_TILE_SIZE_Z]  # todo monitor if changed? (get from linked library?)
        if CUSTOM_PROP_LAST_CURSOR in self.root:
            self.cursor = Cursor.deserialize(self.root[CUSTOM_PROP_LAST_CURSOR])
            if self.cursor.tile3d not in bpy.data.groups:
                self.cursor.tile3d = None
        logging.debug("initialized root obj")

    def on_quit(self):
        self.root[CUSTOM_PROP_LAST_CURSOR] = self.cursor.serialize()

    def error(self, msg):
        logging.error(msg)

    def get_layers_array(self):
        lst = [False] * 20
        lst[self.layer] = True
        return lst

    def _get_tiles(self):
        finder = Tile3DFinder()
        return finder.get_tiles_at(self.cursor.pos)

    def get_tile3d(self):
        tiles = self._get_tiles()
        if len(tiles) > 0:
            return tiles[0] # assume only one

    def paint(self):
        tile3d = self.cursor.tile3d
        if tile3d is not None:
            self.delete()
            self.create_tile(tile3d)

    def create_tile(self, group):
        if group == 'empty':
            bpy.ops.object.empty_add(layers=self.get_layers_array())
        else:
            bpy.ops.object.group_instance_add(group=group, layers=self.get_layers_array())
        tile3d = bpy.context.object
        tile3d.empty_draw_size = 0.25
        tile3d.pos = self.cursor.pos
        tile3d.rot = radians(self.cursor.rot)
        tile3d.parent = self.root
        logging.debug("created object {}".format(tile3d.name))
        return tile3d

    def delete(self, ignore=None):
        tiles = self._get_tiles()
        if ignore and ignore in tiles:
            tiles.remove(ignore)
        if any(tiles):
            tile3d = tiles[0] # assume only one
            self.delete_tile(tile3d)

    def delete_tile(self, obj):
        bpy.data.objects.remove(obj, True)
        logging.debug("deleted 1 object")

    def _cdraw(self):
        if self.state.paint:
            self.paint()
        elif self.state.delete:
            self.delete()

    def rotate(self, rot):
        # rotate the cursor and paint
        logging.debug("rotated cursor {}".format(rot))
        if self.state.grab:
            mat_rot = Matrix.Rotation(radians(rot), 4, 'Z')
            for item in self.grabbed:
                vec = item.tile3d.pos - self.cursor.pos
                item.tile3d.pos = mat_rot * vec
                item.tile3d.pos = item.tile3d.pos + self.cursor.pos
                item.tile3d.rot = item.tile3d.rot + radians(rot)
            if self.state.select:
                vec = self.select_start_pos - self.cursor.pos
                self.select_start_pos = mat_rot * vec
                self.select_start_pos = self.select_start_pos + self.cursor.pos
                self.construct_select_cube()
        self.cursor.rot = self.cursor.rot + rot
        self._cdraw()

    def translate(self, x, y, z):
        # translate the cursor and paint
        vec = Vector((x, y, z))
        logging.debug("moved cursor {}".format(vec))
        forward = self.cursor.forward
        vec = forward * vec
        self.cursor.pos = self.cursor.pos + vec
        if self.state.grab:
            for item in self.grabbed:
                item.tile3d.pos = item.tile3d.pos + vec
            if self.state.select:
                self.select_start_pos = self.select_start_pos + vec
        self._cdraw()
        self.construct_select_cube()

    def smart_move(self, x, y, repeat=1):
        # move in x or y, but only if already facing that direction
        mag = magnitude(x, y)
        rot = normalized_XY_to_Zrot(x, y)
        if self.cursor.rot == rot:
            for i in range(repeat):
                self.translate(0, round(mag), 0)
        else:
            self.rotate(rot - self.cursor.rot)
            if repeat > 1:
                # translate anyway
                for i in range(repeat):
                    self.translate(0, round(mag), 0)

    def start_grab(self):
        if self.state.select:
            tiles = self.get_selected_tiles()
            if not any(tiles): return
            for tile3d in tiles:
                self.grabbed = [GrabData(tile3d) for tile3d in tiles]
        else:
            tile3d = self.get_tile3d()
            if tile3d is None: return
            self.grabbed = [GrabData(tile3d)]
        self.state.grab = True
        logging.debug("start grab")

    def end_grab(self, cancel=False):
        logging.debug("end grab")
        self.state.grab = False
        if self.state.select:
            self.end_select()
        if cancel:
            for item in self.grabbed:
                item.tile3d.pos = item.orig_pos
                item.tile3d.rot = item.orig_rot
        else:
            orig_pos = self.cursor.pos
            for item in self.grabbed:
                self.cursor.pos = item.tile3d.pos
                self.delete(ignore=item.tile3d)
            self.cursor.pos = orig_pos
        self.grabbed = None

    def copy(self):
        if self.state.select:
            tiles = self.get_selected_tiles()
            if any(tiles):
                self.clipboard = [Clipboard(tile3d) for tile3d in tiles]
            else:
                self.clipboard = None
            self.end_select()
        else:
            tile3d = self.get_tile3d()
            if tile3d:
                self.clipboard = [Clipboard(tile3d)]
            else:
                self.clipboard = None
        text = len(self.clipboard) if self.clipboard else "0"
        logging.debug("copied {} objects to clipboard".format(text))

    def paste(self):
        if self.clipboard:
            for item in self.clipboard:
                pos = self.cursor.pos + item.pos_offset
                rot = degrees(item.rot)
                cursor = Cursor(item.group, pos, rot)
                self.do_with_cursor(cursor, self.paint)
        logging.debug("pasted {} objects".format(len(self.clipboard) if self.clipboard else "0"))

    def do_with_cursor(self, cursor, func, *args, **kw):
        orig = self.cursor
        self.cursor = cursor
        func(*args, **kw)
        self.cursor = orig

    def start_select(self):
        logging.debug("start box select")
        self.state.select = True
        self.select_start_pos = self.cursor.pos

    def end_select(self):
        logging.debug("end box select")
        self.do_region(self._cdraw)
        self.state.select = False
        self.construct_select_cube()

    def get_selected_tiles(self):
        # get tiles within selection bounds
        tiles = []
        def get_tiles(tiles):
            tile3d = t3d.get_tile3d()
            if tile3d:
                tiles.append(tile3d)
        self.do_region(get_tiles, tiles)
        return tiles

    def do_region(self, func, *args, **kw):
        # do func for each cell in select bounds
        orig_pos = self.cursor.pos
        cube_min, cube_max = self.select_cube_bounds()
        for z in range(int(round(abs(cube_max.z + 1 - cube_min.z)))):
            for y in range(int(round(abs(cube_max.y + 1 - cube_min.y)))):
                for x in range(int(round(abs(cube_max.x + 1 - cube_min.x)))):
                    self.cursor.pos = Vector((cube_min.x + x, cube_min.y + y, cube_min.z + z))
                    func(*args, **kw)
        self.cursor.pos = orig_pos

    def construct_select_cube(self):
        pass

    def select_cube_bounds(self):
        start = self.select_start_pos
        end = self.cursor.pos
        cube_min = Vector((min(start.x, end.x), min(start.y, end.y), min(start.z, end.z)))
        cube_max = Vector((max(start.x, end.x), max(start.y, end.y), max(start.z, end.z)))
        return cube_min, cube_max
