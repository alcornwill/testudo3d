
import logging
from math import radians
from random import choice
import bpy
from .tilemap3d import any, Cursor, Tile3DFinder, ADJACENCY_VECTORS
from .turtle3d import Turtle3D

CUSTOM_PROP_AUTO = 't3d_auto'

def readlines(path):
    with open(path) as f:
        lines = f.readlines()
        lines = [x.strip() for x in lines]
    return lines

class Rule:
    def __init__(self, tiles, rot=0):
        self.tiles = tiles
        self.rot = rot

    def __str__(self):
        return '{} {}'.format(self.tiles, self.rot)

def parse_rules(path):
    ROTATE = {
        1: [2, 4, 8],
        3: [6, 12, 9],
        5: [10, 5, 10],
        7: [14, 13, 11]
    }
    rules = {}
    default = None
    lines = readlines(path)
    for line in lines:
        if line.startswith('#'): continue # ignore
        split = line.split(' ')
        split = [s for s in split if s]
        if not any(split): continue
        a = split[0]
        b = split[1:]
        try:
            if not b: continue # use default
            n = int(a, 2)
            rules[n] = Rule(b)
            # z rotation rules
            # (magically you can override these in rules.txt and still works)
            #     (as long as defined in numerical order)
            n_ = n & 0b001111
            d = n & 0b110000
            if n_ in ROTATE:
                copyto = ROTATE[n_]
                for i in range(3):
                    n__ = copyto[i]
                    rules[d | n__] = Rule(b, (i+1)*-90)
        except ValueError as e:
            if a == 'dfault':
                default = Rule(b or None)

    return rules, default

class AutoTiler3D(Turtle3D):
    def __init__(self, *args, **kw):
        Turtle3D.__init__(self, *args, **kw)
        self.auto_root = None

        # test
        item = bpy.context.scene.t3d_prop.tilesets.add()
        item.path = 'popo'
        item = bpy.context.scene.t3d_prop.tilesets.add()
        item.path = 'popo2'
        print("happening")

    def init(self):
        Turtle3D.init(self)
        self.cursor.tile3d = 'Tileset1' # todo tilesets
        # would be nice to change draw 2D callback to change color
        # Cursor.draw_2d()?

        self.init_auto_root()
        self.init_rules()

    def init_rules(self):
        path = bpy.context.scene.t3d_prop.rules_path
        self.rules, self.default = parse_rules(path)

    def init_auto_root(self):
        parent = self.root_obj.parent
        if parent:
            search = parent.children
        else:
            search = [obj for obj in bpy.data.objects if not obj.parent]
        for obj in search:
            if CUSTOM_PROP_AUTO in obj and obj[CUSTOM_PROP_AUTO]:
                self.auto_root = obj
                return
        # not found, create
        bpy.ops.object.empty_add()
        self.auto_root = bpy.context.object
        self.auto_root.name = 'Auto'
        self.auto_root[CUSTOM_PROP_AUTO] = True
        self.auto_root.empty_draw_size = 0.25
        if parent:
            self.auto_root.parent = parent

    def delete(self):
        # hmm this will slow down region operations and stuff... avoidable?
        Turtle3D.delete(self)
        self.do_auto_tiling()

    def paint(self):
        Turtle3D.delete(self)
        self.create_tile()
        self.do_auto_tiling()

    def get_occupied(self):
        finder = Tile3DFinder()
        center = finder.get_tiles_at(self.cursor.pos)
        adjacent = [finder.get_tiles_at(self.cursor.pos + vec) for vec in ADJACENCY_VECTORS]
        return center, adjacent

    def do_auto_tiling(self):
        self.auto_tiling()
        # repaint adjacent
        orig_pos = self.cursor.pos
        for vec in ADJACENCY_VECTORS:
            cursor = Cursor(None, orig_pos + vec, 0)
            self.do_with_cursor(cursor, self.auto_tiling)

    def auto_tiling(self):
        # check adjacent cells if occupied
        center, adjacent = self.get_occupied()
        bitmask = 0
        for i, tiles in enumerate(adjacent):
            bitmask |= bool(tiles) << i

        self.root = self.auto_root
        Turtle3D.delete(self)

        if center:
            rule = (self.rules[bitmask]
                    if bitmask in self.rules
                    else self.default)
            automode = bpy.context.scene.t3d_prop.auto_mode
            if automode == 'random':
                group = choice(rule.tiles)
            if automode == 'first':
                group = rule.tiles[0]
            if automode == 'dither':
                pos = self.cursor.pos
                idx = int(pos.x + pos.y + pos.z)
                idx %= len(rule.tiles)
                group = rule.tiles[idx]
            tile3d = self.create_tile(group)
            tile3d.rot = radians(rule.rot)
        self.root = self.root_obj
