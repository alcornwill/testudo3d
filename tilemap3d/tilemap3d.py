
import builtins
import bpy
import logging
import random
from math import floor, degrees, radians, atan2, sqrt
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.kdtree import KDTree

SEARCH_RANGE = 0.01
CUSTOM_PROPERTY_TILE_SIZE_Z = "T3D_tile_size_z"
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

def any(lst):
    return len(lst) > 0

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

def get_first_group_name(obj):
    if len(obj.users_group) > 0:
        return obj.users_group[0].name

def log_created(obj):
    logging.debug("created {}".format(str(obj)))

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
    def __init__(self):
        self.pos = Vector()
        self.rot = 0 # in degrees

    def get_forward(self):
        return Matrix.Rotation(radians(t3d.cursor.rot), 4, 'Z')

    forward = property(get_forward)

class GrabData:
    def __init__(self, tile3d):
        self.tile3d = tile3d
        self.orig_pos = tile3d.pos
        self.orig_rot = tile3d.rot

class Clipboard:
    def __init__(self, tile3d):
        self.group = tile3d.group
        self.pos_offset = tile3d.pos - t3d.cursor.pos
        self.rot_offset = tile3d.rot - radians(t3d.cursor.rot)

class Tile3DFinder:
    def __init__(self):
        self.kd = None
        self.childs = None

        # init
        self.childs = t3d.root_obj.children
        size = len(self.childs)
        self.kd = KDTree(size)

        for i, child in enumerate(self.childs):
            self.kd.insert(child.pos, i)
        self.kd.balance()

    def get_tiles_at(self, pos):
        return [self.childs[index] for pos, index, dist in self.kd.find_range(pos, SEARCH_RANGE)]

class PaintModeState:
    paint = False
    delete = False
    grab = False
    select = False

# tilesize = Vector((1.0, 1.0, 1.0))

class Tilemap3D:
    def __init__(self, logging_level=logging.INFO):
        self.root_obj = None
        self.tilesize_z = 1.0
        self.active_tile3d = None
        self.cursor = Cursor()
        self.state = PaintModeState()
        self.select_start_pos = None
        self.grabbed = None
        self.clipboard = None

        # init
        logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging_level)
        builtins.t3d = self # note: builtin abuse
        init_object_props()

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

    def _get_tiles(self):
        finder = Tile3DFinder()
        return finder.get_tiles_at(self.cursor.pos)

    def get_tile3d(self):
        tiles = self._get_tiles()
        if len(tiles) > 0:
            return tiles[0] # assume only one!

    def paint(self):
        tile3d = self.active_tile3d
        if tile3d is not None:
            self.paint_tile(tile3d)

    def paint_tile(self, group):
        self.delete()
        obj = self.create_tile(group, position=self.cursor.pos, rotz=self.cursor.rot)
        logging.debug("created object {}".format(obj.name))
        return obj

    def create_tile(self, group, position=None, rotz=None):
        bpy.ops.object.group_instance_add(group=group)
        tile3d = bpy.context.scene.objects.active
        tile3d.empty_draw_size = 0.25
        if position is not None:
            tile3d.pos = position
        if rotz is not None:
            tile3d.rot = radians(rotz)
        tile3d.parent = self.root_obj
        return tile3d

    def delete(self, ignore=None):
        tile3d = self.get_tile3d()
        if tile3d:
            if ignore:
                if tile3d == ignore: return
            delete_object(tile3d)

    def adjacent_occupied(self):
        finder = Tile3DFinder()
        return [len(finder.get_tiles_at(self.cursor.pos + vec)) > 0 for vec in ADJACENCY_VECTORS]

    def cdraw(self):
        # contextual draw
        if self.state.paint:
            self.paint()
        elif self.state.delete:
            self.delete()
        self.construct_select_cube()

    def rotate(self, rot):
        # rotate the cursor and paint
        self.cursor.rot = self.cursor.rot + rot
        logging.debug("rotated cursor {}".format(rot))
        if self.state.grab:
            self.grabbed.tile3d.rot = self.grabbed.tile3d.rot + radians(rot)
        self.cdraw()

    def translate(self, x, y, z):
        # translate the cursor and paint
        vec = Vector((x, y, z))
        logging.debug("moved cursor {}".format(vec))
        forward = self.cursor.forward
        vec = forward * vec
        self.cursor.pos = self.cursor.pos + vec
        if self.state.grab:
            self.grabbed.tile3d.pos = self.grabbed.tile3d.pos + vec
        self.cdraw()

    def smart_move(self, x, y, repeat=1):
        # move in x or y, but only if already facing that direction
        mag = magnitude(x, y)
        rot = normalized_XY_to_Zrot(x, y)
        if self.cursor.rot == rot:
            for i in range(repeat):
                self.translate(0, round(mag), 0)
        else:
            self.rotate(rot - self.cursor.rot)

    def start_grab(self):
        if self.state.select:
            # todo grab everything in select bounds
            pass
        tile3d = self.get_tile3d()
        if tile3d is None: return
        logging.debug("start grab")
        self.state.grab = True
        self.grabbed = GrabData(tile3d) # todo list

    def end_grab(self, cancel=False):
        logging.debug("end grab")
        self.state.grab = False
        if cancel:
            self.grabbed.tile3d.pos = self.grabbed.orig_pos
            self.grabbed.tile3d.rot = self.grabbed.orig_rot
        else:
            self.delete(ignore=self.grabbed.tile3d)
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
            forward = self.cursor.forward
            orig_pos = self.cursor.pos
            for item in self.clipboard:
                vec = forward * item.pos_offset
                self.cursor.pos = orig_pos + vec
                new = self.paint_tile(item.group)
                new.rot = radians(self.cursor.rot) + item.rot_offset
            self.cursor.pos = orig_pos
        logging.debug("pasted {} objects".format(len(self.clipboard) if self.clipboard else "0"))

    def start_select(self):
        logging.debug("start box select")
        self.state.select = True
        self.select_start_pos = self.cursor.pos
        self.construct_select_cube()

    def end_select(self):
        logging.debug("end box select")
        self.select_bounds_func(self.cdraw)
        self.state.select = False
        self.construct_select_cube()

    def get_selected_tiles(self):
        # get tiles within selection bounds
        tiles = []
        def get_tiles(tiles):
            tile3d = t3d.get_tile3d()
            if tile3d:
                tiles.append(tile3d)
        self.select_bounds_func(get_tiles, tiles)
        return tiles

    def select_bounds_func(self, func, *args):
        # do func for each cell in select bounds
        orig_cursor_pos = self.cursor.pos
        cube_min, cube_max = self.select_cube_bounds()
        for z in range(int(round(abs(cube_max.z + 1 - cube_min.z)))):
            for y in range(int(round(abs(cube_max.y + 1 - cube_min.y)))):
                for x in range(int(round(abs(cube_max.x + 1 - cube_min.x)))):
                    self.cursor.pos = Vector((cube_min.x + x, cube_min.y + y, cube_min.z + z))
                    func(*args)
        self.cursor.pos = orig_cursor_pos

    def construct_select_cube(self):
        pass

    def select_cube_bounds(self):
        start = self.select_start_pos
        end = self.cursor.pos
        cube_min = Vector((min(start.x, end.x), min(start.y, end.y), min(start.z, end.z)))
        cube_max = Vector((max(start.x, end.x), max(start.y, end.y), max(start.z, end.z)))
        return cube_min, cube_max
