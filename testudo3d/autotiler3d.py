
import logging
from math import radians
from random import choice
import bpy
from .tilemap3d import any, Cursor, Tile3DFinder, ADJACENCY_VECTORS
from .turtle3d import Turtle3D

LAYER_OFFSET = 10 # hmm
CUSTOM_PROP_TILESET = 't3d_tileset'

def readlines(path):
    with open(path) as f:
        lines = f.readlines()
        lines = [x.strip() for x in lines]
    return lines

class Ruleset:
    def __init__(self, rules, default):
        self.rules = rules
        self.default = default

    def get(self, bitmask):
        if bitmask in self.rules:
            return self.rules[bitmask]
        elif self.default:
            return self.default
        # else None

class Rule:
    def __init__(self, tile3d, rot=0):
        self.tile3d = tile3d
        self.rot = rot

        # todo 'warning rule contains tile not presend in blend "{}"'

    def __str__(self):
        return '{} {}'.format(self.tile3d, self.rot)

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
        if not b: continue # none or default
        b = b[0] # only one supported
        try:
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
            if a == 'default':
                default = Rule(b or None)

    return Ruleset(rules, default)

class AutoTiler3D(Turtle3D):
    def __init__(self, *args, **kw):
        Turtle3D.__init__(self, *args, **kw)
        self.tileset_ = None
        self.manual_mode = False

    def init(self):
        Turtle3D.init(self)
        self.init_rules()

        prop = bpy.context.scene.t3d_prop
        prop.tileset_idx = prop.tileset_idx # give it a kick

    def init_rules(self):
        prop = bpy.context.scene.t3d_prop
        self.rulesets = {}
        for tileset in prop.tilesets:
            path = bpy.path.abspath(tileset.path)
            self.rulesets[tileset.tileset_name] = parse_rules(path)

    def get_tileset(self):
        return self.tileset_
    def set_tileset(self, tileset):
        self.tileset_ = tileset
        self.cursor.tile3d = tileset.tileset_name
    tileset = property(get_tileset, set_tileset)

    def delete(self, ignore=None):
        # hmm this will slow down region operations and stuff... avoidable?
        self.layer = self.user_layer + LAYER_OFFSET # hmm
        Turtle3D.delete(self, ignore)
        self.layer = self.user_layer
        self.do_auto_tiling()

    def paint(self):
        self.layer = self.user_layer + LAYER_OFFSET # hmm
        Turtle3D.delete(self)
        tile3d = self.create_tile('empty')
        self.layer = self.user_layer
        tile3d[CUSTOM_PROP_TILESET] = self.tileset.tileset_name
        self.do_auto_tiling()

    def get_occupied(self):
        self.layer = self.user_layer + LAYER_OFFSET
        finder = Tile3DFinder()
        self.layer = self.user_layer
        center = finder.get_tiles_at(self.cursor.pos)
        adjacent = [finder.get_tiles_at(self.cursor.pos + vec) for vec in ADJACENCY_VECTORS]
        return center, adjacent

    def do_auto_tiling(self):
        self.auto_tiling(self.tileset.tileset_name)
        # repaint adjacent
        orig_pos = self.cursor.pos
        for vec in ADJACENCY_VECTORS:
            cursor = Cursor(None, orig_pos + vec, 0)
            self.do_with_cursor(cursor, self.auto_tiling)

    def auto_tiling(self, tileset=None):
        # check adjacent cells if occupied
        center, adjacent = self.get_occupied()
        bitmask = 0
        for i, tiles in enumerate(adjacent):
            bitmask |= bool(tiles) << i

        if center:
            tileset = tileset or center[0][CUSTOM_PROP_TILESET]
            ruleset = self.rulesets[tileset]
            rule = ruleset.get(bitmask)

        Turtle3D.delete(self)

        if center and rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)
            tile3d[CUSTOM_PROP_TILESET] = tileset
