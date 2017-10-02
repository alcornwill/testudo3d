
import builtins
import bpy
import logging
import random
from math import floor, degrees, radians, atan2, sqrt, isclose
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.kdtree import KDTree
from .events import subscribe, unsubscribe, send_event

TOLERANCE = 0.01
CUSTOM_PROP_TILE_SIZE_Z = "t3d_tile_size_z"
CUSTOM_PROP_LAST_CURSOR = 't3d_last_cursor'
CUSTOM_PROP_TILESET = 't3d_tileset'
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
    # it's a shame there's not an IntVector
    # might have to do less rounding
    # (hmm, could you just make it? no static types in python though)
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
        if self.dupli_group:
            return self.dupli_group.name

    def get_tileset(self):
        if self.dupli_group:
            return t3d.get_tileset_from_group(self.dupli_group.name)

    # NOTE: these attribute names may conflict with other addons
    bpy.types.Object.pos = property(get_pos, set_pos)
    bpy.types.Object.rot = property(get_rot, set_rot)
    bpy.types.Object.group = property(get_group)
    bpy.types.Object.tileset = property(get_tileset)

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
    def __init__(self, objects=None):
        self.cached = {}
        self.objects = objects or [c for c in t3d.root.children if c.layers[t3d.layer]]
        size = len(self.objects)
        self.kd = KDTree(size)

        for i, obj in enumerate(self.objects):
            self.kd.insert(obj.pos, i)
        self.kd.balance()

    def get_tiles_at(self, pos):
        vec = pos.copy().freeze()
        if vec in self.cached:
            return self.cached[vec]
        else:
            objs = [self.objects[index] for pos, index, dist in self.kd.find_range(pos, TOLERANCE)]
            self.cached[vec] = objs
            return objs

class FinderManager:
    def __init__(self):
        self.finder = None # also need one for each root
        self.invalidated = True

    def get_tiles_at(self, pos):
        if self.invalidated:
            self.finder = Tile3DFinder()
            self.invalidated = False
        return self.finder.get_tiles_at(pos)

    def invalidate(self):
        self.invalidated = True

    def reset(self, objects=None):
        self.finder = Tile3DFinder(objects)

class PaintModeState:
    paint = False
    delete = False
    grab = False
    select = False

# tilesize = Vector((1.0, 1.0, 1.0))

class Tileset:
    def __init__(self, tiles, rules):
        self.tiles = tiles
        self.rules = rules

class Tilemap3D:
    def __init__(self, logging_level=logging.INFO):
        self.root = None
        self.tilesize_z = 1.0
        self.cursor = Cursor()
        self.state = PaintModeState()
        self.select_start_pos = None
        self.grabbed = None
        self.clipboard = None
        self.finder = FinderManager()
        self.manual_mode = True # hacky
        self.prop = bpy.context.scene.t3d_prop # i would prefer to not use this at all but it makes sense
        self.lastpos = None
        self.select_cube_redraw = False
        self.tilesets = None

        # init
        logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging_level)
        # logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging.WARNING)
        # logging.basicConfig(format='T3D: %(levelname)s: %(message)s', level=logging.DEBUG)
        builtins.t3d = self # note: builtin abuse
        bpy.types.Scene.t3d = self

    def get_layer(self):
        return self.prop.user_layer
    layer = property(get_layer)

    def get_tileset(self):
        return self.prop.get_tileset().tileset
    tileset = property(get_tileset)

    def init(self):
        self.init_root_obj()

        subscribe('set_tile3d', self.set_tile3d)
        subscribe('refresh_tilesets', self.refresh_tilesets)

        self.prop.tileset_idx = self.prop.tileset_idx # give it a kick
        self.prop.refresh_tilesets()

    def set_tile3d(self, tile3d):
        self.cursor.tile3d = tile3d

    def refresh_tilesets(self):
        self.tilesets = {tileset.tileset: Tileset([tile3d.tile3d for tile3d in tileset.tiles], tileset.rules)
                         for tileset in self.prop.tilesets}
        # optimized search tileset from tile3d
        self.search_tile3d = {tile3d.tile3d: tileset.tileset
                              for tileset in self.prop.tilesets
                              for tile3d in tileset.tiles}

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
        self.lastpos = self.cursor.pos
        logging.debug("initialized root obj")

    def on_quit(self):
        self.root[CUSTOM_PROP_LAST_CURSOR] = self.cursor.serialize()
        unsubscribe('refresh_tilesets', self.refresh_tilesets)
        unsubscribe('set_tile3d', self.set_tile3d)

    def error(self, msg):
        logging.error(msg)

    def on_update(self):
        self.finder.invalidate()

    def get_tileset_from_group(self, group_name):
        return self.search_tile3d[group_name]

    def get_layers_array(self):
        lst = [False] * 20
        lst[self.layer] = True
        return lst

    def _get_tiles(self):
        return self.finder.get_tiles_at(self.cursor.pos)

    def get_tile3d(self):
        tiles = self._get_tiles()
        if len(tiles) > 0:
            return tiles[0] # assume only one

    def paint(self):
        tile3d = self.cursor.tile3d
        if not tile3d: return
        self.delete()
        self.create_tile(tile3d)

    def create_tile(self, group):
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
        if tiles:
            tile3d = tiles[0] # assume only one
            self.delete_tile(tile3d)

    def delete_tile(self, obj):
        try:
            bpy.data.objects.remove(obj, True)
        except ReferenceError as e:
            # todo
            # might be because finder should have been invalidated
            # might be because drawing routines are dodgey and go over same cell twice
            logging.warning('Object deleted twice')
        logging.debug("deleted 1 object")

    def cdraw(self):
        if self.state.paint:
            self.paint()
        elif self.state.delete:
            self.delete()

    def brush_draw(self):
        if self.prop.brush_size > 1:
            radius = self.prop.brush_size - 1
            if self.prop.outline:
                self.circle(radius)
            else:
                self.circfill(radius)
        else:
            self.cdraw()

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
                self.select_cube_redraw = True
        self.cursor.rot = self.cursor.rot + rot
        self.cdraw()

    def translate(self, x, y, z):
        # translate the cursor and paint
        vec = Vector((x, y, z))
        logging.debug("moved cursor {}".format(vec))
        forward = self.cursor.forward
        vec = forward * vec
        self.on_move(vec)

    def on_move(self, vec):
        self.cursor.pos = self.cursor.pos + vec
        if self.state.grab:
            for item in self.grabbed:
                item.tile3d.pos = item.tile3d.pos + vec
            if self.state.select:
                self.select_start_pos = self.select_start_pos + vec
        self.lastpos = self.cursor.pos
        self.brush_draw()
        self.select_cube_redraw = True

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
        points = self.region_points()
        self.batch_cdraw(points)
        self.state.select = False
        self.select_cube_redraw = True

    def get_selected_tiles(self):
        # get tiles within selection bounds
        points = self.region_points()
        tiles = []
        def get_tiles(tiles):
            tile3d = t3d.get_tile3d()
            if tile3d:
                tiles.append(tile3d)
        self.do_points(points, get_tiles, tiles)
        return tiles

    def region_points(self):
        cube_min, cube_max = self.select_cube_bounds()
        return [Vector((cube_min.x + x, cube_min.y + y, cube_min.z + z))
                for x in range(int(round(abs(cube_max.x + 1 - cube_min.x))))
                for y in range(int(round(abs(cube_max.y + 1 - cube_min.y))))
                for z in range(int(round(abs(cube_max.z + 1 - cube_min.z))))]

    def select_cube_bounds(self):
        start = self.select_start_pos
        end = self.cursor.pos
        cube_min = Vector((min(start.x, end.x), min(start.y, end.y), min(start.z, end.z)))
        cube_max = Vector((max(start.x, end.x), max(start.y, end.y), max(start.z, end.z)))
        return cube_min, cube_max

    def select_cube_dim(self):
        cube_min, cube_max = self.select_cube_bounds()
        w = int(round(abs(cube_max.x + 1 - cube_min.x)))
        d = int(round(abs(cube_max.y + 1 - cube_min.y)))
        h = int(round(abs(cube_max.z + 1 - cube_min.z)))
        return w, d, h

    def batch_cdraw(self, points):
        self.do_points(points, self.cdraw)

    def do_points(self, points, func, *args, **kw):
        # do func for each point in points
        orig_pos = self.cursor.pos
        for pos in points:
            self.cursor.pos = pos
            func(*args, **kw)
        self.cursor.pos = orig_pos

    def _goto(self, x, y):
        self.cursor.pos.x = x
        self.cursor.pos.y = y
        self.select_cube_redraw = True

    def plot(self, x, y):
        self._goto(x,y)
        self.cdraw()

    def circle(self, radius):
        x0, y0, z = self.cursor.pos
        points = circle_points(radius, x0, y0, z)
        self.batch_cdraw(points)
        self._goto(x0,y0)

    def circfill(self, radius):
        x, y, z = self.cursor.pos
        points = circfill_points(x, y, radius, z)
        self.batch_cdraw(points)
        self._goto(x, y)

    def line(self, x2, y2):
        x1, y1, z = self.cursor.pos
        x1 = int(x1)
        y1 = int(y1)
        x2 = int(x2)
        y2 = int(y2)

        points = line_points(x1, x2, y1, y2, z)
        self.batch_cdraw(points)
        self._goto(x2,y2)

def circle_points(radius, x0, y0, z):
    x = radius
    y = 0
    err = 0
    points = []
    while x >= y:
        points += [
            Vector((x0 + x, y0 + y, z)).freeze(),
            Vector((x0 + y, y0 + x, z)).freeze(),
            Vector((x0 - y, y0 + x, z)).freeze(),
            Vector((x0 - x, y0 + y, z)).freeze(),
            Vector((x0 - x, y0 - y, z)).freeze(),
            Vector((x0 - y, y0 - x, z)).freeze(),
            Vector((x0 + y, y0 - x, z)).freeze(),
            Vector((x0 + x, y0 - y, z)).freeze()
        ]

        y += 1
        if err <= 0:
            err += 2 * y + 1
        if err > 0:
            x -= 1
            err -= 2 * x + 1
    points = list(set(points)) # remove duplicates...
    return points

def plot4(cx, cy, x, y, z):
    cx = int(cx)
    cy = int(cy)
    x = int(x)
    y = int(y)

    points = line_points(cx - x, cx + x, cy + y, cy + y, z)
    if x != 0 and y != 0:
        points += line_points(cx - x, cx + x, cy - y, cy - y, z)
    return points

def circfill_points(cx, cy, radius, z):
    x = radius
    y = 0
    err = -radius
    points = []
    while y <= x:
        lasty = y
        err += y
        y += 1
        err += y
        points += plot4(cx, cy, x, lasty, z)
        if err > 0:
            if x != lasty:
                points += plot4(cx, cy, lasty, x, z)
            err -= x
            x -= 1
            err -= x
    return points

def line_points(x1, x2, y1, y2, z):
    points = []
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0:
        step = 1 if dy > 0 else -1
        for y in range(y1, y2 + step, step):
            points.append(Vector((x1, y, z)))
    elif dy == 0:
        step = 1 if dx > 0 else -1
        for x in range(x1, x2 + step, step):
            points.append(Vector((x, y1, z)))
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
            frac = dy - (dx >> 1)
            while x1 != x2:
                if frac >= 0:
                    y1 = y1 + stepy
                    frac = frac - dx
                x1 = x1 + stepx
                frac = frac + dy
                points.append(Vector((x1, y1, z)))
        else:
            frac = dx - (dy >> 1)
            while y1 != y2:
                if frac >= 0:
                    x1 = x1 + stepx
                    frac = frac - dy
                y1 = y1 + stepy
                frac = frac + dx
                points.append(Vector((x1, y1, z)))
    return points