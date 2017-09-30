
import logging
from math import radians
from random import choice
import bpy
from .tilemap3d import any, Cursor, Tilemap3D, Tile3DFinder, ADJACENCY_VECTORS

CUSTOM_PROP_RULES_FILE = 't3d_rules_file'

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

def parse_rules(text):
    ROTATE = {
        1: [2, 4, 8],
        3: [6, 12, 9],
        5: [10, 5, 10],
        7: [14, 13, 11]
    }
    rules = {}
    default = None
    lines = [line.body for line in text.lines]
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

class AutoTiler3D(Tilemap3D):
    # todo ok this is still really inefficient for region operations (fill/clear)
    # in such cases each cell can be repainted up to 6 times!
    # the code is much simpler this way though...
    # otherwise would have to calculate the bitmasks of every cell we are operating on
    # then go round and create all the objects
    # sounds buggy
    def __init__(self, *args, **kw):
        Tilemap3D.__init__(self, *args, **kw)
        self.manual_mode = False
        self.changed = []
        self.alt = True # auto-tiling mode

    def init(self):
        Tilemap3D.init(self)
        self.init_rules()

    def init_rules(self):
        self.rulesets = {}
        for scene in self.tilesets.values():
            if not scene.rules:
                self.error('Tileset "{}" has no ruleset'.format(scene.name))
                self.on_quit()
                return
            text = bpy.data.texts[scene.rules]
            try:
                self.rulesets[scene.name] = parse_rules(text) # note: monkey patching
            except ValueError as e:
                self.error('"{}": Invalid bitmask, line {}: "{}"'.format(scene.rules, e.line_no, e.line))
                self.on_quit()
                return

    def refresh_tilesets(self):
        Tilemap3D.refresh_tilesets(self)
        self.init_rules()

    def delete(self, ignore=None):
        Tilemap3D.delete(self, ignore)
        if self.alt:
            self.finder.invalidate()
            self.repaint_adjacent()

    def paint(self):
        if self.alt:
            Tilemap3D.delete(self)
            self.new_auto_tile()
            self.finder.invalidate()
            self.repaint_adjacent()
        else:
            Tilemap3D.paint(self)

    def paste(self):
        # no auto-tiling
        self.alt = False
        Tilemap3D.paste(self)
        self.alt = True

    def end_grab(self):
        # no auto-tiling
        self.alt = False
        Tilemap3D.end_grab(self)
        self.alt = True

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

    def optimized_new_auto_tile(self, bitmasks):
        # assume obstructing tiles already deleted
        # use pre-calculated bitmask

        pos = self.cursor.pos.copy().freeze()
        bitmask = bitmasks[pos]
        ruleset = self.rulesets[self.tileset]
        rule = ruleset.get(bitmask)

        if rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)

    def do_region(self, func, *args, **kw):
        if func == self.cdraw and self.state.paint:
            # completely override behaviour (optimization)
            # clear region first
            self.alt = False
            Tilemap3D.do_region(self, self.delete)
            self.alt = True
            self.finder.reset()
            # create a fake scene state
            objects = list(self.finder.finder.objects)
            class FakeObject:
                def __init__(self, pos):
                    self.pos = pos
            def fake_paint(objects):
                obj = FakeObject(self.cursor.pos.copy())
                objects.append(obj)
            Tilemap3D.do_region(self, fake_paint, objects)
            self.finder.reset(objects)
            # get bitmasks for fake state
            bitmasks = {}
            def get_bitmask(bitmasks):
                adjacent = [self.finder.get_tiles_at(self.cursor.pos + vec) for vec in ADJACENCY_VECTORS]
                bitmask = self.get_bitmask(adjacent)
                pos = self.cursor.pos.copy().freeze()
                bitmasks[pos] = bitmask
            Tilemap3D.do_region(self, get_bitmask, bitmasks)
            # do paint
            Tilemap3D.do_region(self, self.optimized_new_auto_tile, bitmasks)
            # for each 'face' of selection bounds do auto_tiling
            cube_min, cube_max = self.select_cube_bounds()
            def repaint_perimeter(cube_min, cube_max):
                # todo didn't work once, floating point error? (use isclose)
                pos = self.cursor.pos
                if pos.x == cube_min.x:
                    pos.x -= 1; self.auto_tiling(); pos.x += 1
                if pos.y == cube_min.y:
                    pos.y -= 1; self.auto_tiling(); pos.y += 1
                if pos.z == cube_min.z:
                    pos.z -= 1; self.auto_tiling(); pos.z += 1
                if pos.x == cube_max.x:
                    pos.x += 1; self.auto_tiling(); pos.x -= 1
                if pos.y == cube_max.y:
                    pos.y += 1; self.auto_tiling(); pos.y -= 1
                if pos.z == cube_max.z:
                    pos.z += 1; self.auto_tiling(); pos.z -= 1
            Tilemap3D.do_region(self, repaint_perimeter, cube_min, cube_max)
        elif func == self.cdraw and self.state.delete:
            # clear region
            self.alt = False
            Tilemap3D.do_region(self, self.delete)
            self.alt = True
            self.finder.reset()
            # for each 'face' of selection bounds do auto_tiling
            cube_min, cube_max = self.select_cube_bounds()
            def repaint_perimeter(cube_min, cube_max):
                pos = self.cursor.pos
                if pos.x == cube_min.x:
                    pos.x -= 1; self.auto_tiling(); pos.x += 1
                if pos.y == cube_min.y:
                    pos.y -= 1; self.auto_tiling(); pos.y += 1
                if pos.z == cube_min.z:
                    pos.z -= 1; self.auto_tiling(); pos.z += 1
                if pos.x == cube_max.x:
                    pos.x += 1; self.auto_tiling(); pos.x -= 1
                if pos.y == cube_max.y:
                    pos.y += 1; self.auto_tiling(); pos.y -= 1
                if pos.z == cube_max.z:
                    pos.z += 1; self.auto_tiling(); pos.z -= 1
            Tilemap3D.do_region(self, repaint_perimeter, cube_min, cube_max)
        else:
            Tilemap3D.do_region(self, func, *args, **kw)

    def new_auto_tile(self):
        # same as auto_tile but always create at center
        center, adjacent = self.get_occupied()
        bitmask = self.get_bitmask(adjacent)

        ruleset = self.rulesets[self.tileset]
        rule = ruleset.get(bitmask)

        if center:
            self.delete_tile(center[0])

        if rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)

    def auto_tiling(self):
        # check adjacent cells if occupied
        center, adjacent = self.get_occupied()
        if not center: return # nothing to repaint
        tileset = center[0].tileset
        if not tileset: return # just a normal object

        bitmask = self.get_bitmask(adjacent)
        ruleset = self.rulesets[tileset]
        rule = ruleset.get(bitmask)

        self.delete_tile(center[0])

        if rule:
            tile3d = self.create_tile(rule.tile3d)
            tile3d.rot = radians(rule.rot)
