
import logging
from math import radians
from random import choice
import bpy
from .tilemap3d import any, Cursor, Tile3DFinder, ADJACENCY_VECTORS
from .turtle3d import Turtle3D

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
    for line_no, line in enumerate(lines):
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
            else:
                e.line_no = line_no+1
                e.line = line
                raise e

    return Ruleset(rules, default)

class AutoTiler3D(Turtle3D):
    # todo ok this is still really inefficient for region operations (fill/clear)
    # in such cases each cell can be repainted up to 6 times!
    # the code is much simpler this way though...
    # otherwise would have to calculate the bitmasks of every cell we are operating on
    # then go round and create all the objects
    # sounds buggy
    def __init__(self, *args, **kw):
        Turtle3D.__init__(self, *args, **kw)
        self.tileset_ = None
        self.manual_mode = False
        self.changed = []

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
            try:
                self.rulesets[tileset.tileset_name] = parse_rules(path)
            except FileNotFoundError as e:
                self.error('Rules file "{}" not found'.format(e.filename))
            except ValueError as e:
                self.error('"{}": Invalid bitmask, line {}: "{}"'.format(tileset.path, e.line_no, e.line))

    def get_tileset(self):
        return self.tileset_
    def set_tileset(self, tileset):
        self.tileset_ = tileset
        self.cursor.tile3d = tileset.tileset_name
    tileset = property(get_tileset, set_tileset)

    def delete(self, ignore=None):
        Turtle3D.delete(self, ignore)
        self.finder.invalidate()
        self.repaint_adjacent()

    def paint(self):
        Turtle3D.delete(self)
        self.new_auto_tile(self.tileset.tileset_name)
        self.finder.invalidate()
        self.repaint_adjacent()

    def get_occupied(self):
        center = self.finder.get_tiles_at(self.cursor.pos)
        adjacent = [self.finder.get_tiles_at(self.cursor.pos + vec) for vec in ADJACENCY_VECTORS]
        return center, adjacent

    def repaint_adjacent(self):
        orig_pos = self.cursor.pos
        for vec in ADJACENCY_VECTORS:
            cursor = Cursor(None, orig_pos + vec, 0)
            self.do_with_cursor(cursor, self.auto_tiling)
        self.finder.invalidate() # hmm, calling this quite a lot

    def get_bitmask(self, adjacent):
        bitmask = 0
        for i, tiles in enumerate(adjacent):
            bitmask |= bool(tiles) << i
        return bitmask

    def new_auto_tile(self, tileset):
        # same as auto_tile but always create at center
        center, adjacent = self.get_occupied()
        bitmask = self.get_bitmask(adjacent)

        ruleset = self.rulesets[tileset]
        rule = ruleset.get(bitmask)

        if center:
            self.delete_tile(center[0])

        if rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)
            tile3d[CUSTOM_PROP_TILESET] = tileset

    def auto_tiling(self):
        # check adjacent cells if occupied
        center, adjacent = self.get_occupied()
        if not center: return # nothing to repaint
        bitmask = self.get_bitmask(adjacent)

        tileset = center[0][CUSTOM_PROP_TILESET]
        ruleset = self.rulesets[tileset]
        rule = ruleset.get(bitmask)

        self.delete_tile(center[0])

        if rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)
            tile3d[CUSTOM_PROP_TILESET] = tileset
