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

bl_info = {
    "name": "Modular Building Tool",
    "author": "Will Alcorn",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View > Tools > MBT",
    "description": "create modular scenes",
    "warning": "",
    "wiki_url": "https://github.com/alcornwill/modular_building_tool",
    "category": "3D View",
}

import sys
import bpy
import bgl
import blf
import json
import mathutils
import math
import random
#noinspection PyUnresolvedReferences
from mathutils import Vector
#noinspection PyUnresolvedReferences
from bpy.props import (StringProperty,
                       BoolProperty,
                       IntProperty,
                       FloatProperty,
                       EnumProperty,
                       PointerProperty,
                       )
#noinspection PyUnresolvedReferences
from bpy.types import (Panel,
                       Operator,
                       PropertyGroup,
                       )

class Vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

text_cursor = Vec2(0, 0)  # used for UI
SEARCH_RANGE = 0.5
ARROW = (Vector((-0.4, -0.4, 0)), Vector((0.4, -0.4, 0)), Vector((0, 0.6, 0)))
RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
YELLOW = (1.0, 1.0, 0.0, 1.0)
PURPLE = (1.0, 0.0, 1.0, 1.0)
FONT_ID = 0  # hmm

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

def weighted_choice(choices):
    total = sum(w for c, w in choices)
    r = random.uniform(0, total)
    upto = 0
    for c, w in choices:
        if upto + w >= r:
            return c
        upto += w
    assert False, "Shouldn't get here"

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

def update_3dviews():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def draw_line_3d(start, end):
    bgl.glVertex3f(*start)
    bgl.glVertex3f(*end)

def draw_poly(poly, color):
    bgl.glBegin(bgl.GL_POLYGON)
    bgl.glColor4f(*color)
    for i in range(len(poly) - 1):
        draw_line_3d(poly[i], poly[i + 1])
    bgl.glEnd()

def mat_transform(mat, poly):
    return [mat * v for v in poly]

def draw_text_2d(text, size=20, color=WHITE):
    bgl.glColor4f(*color)
    blf.position(FONT_ID, text_cursor.x, text_cursor.y, 0)
    blf.size(FONT_ID, size, 72)
    blf.draw(FONT_ID, text)
    text_cursor.y -= size + 5  # behaves like command line

def restore_gl_defaults():
    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def create_cube(position=None, rotz=None, scale=None):
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.scene.objects.active
    if position is not None:
        cube.location=position
    if rotz is not None:
        cube.rotation_euler = mathutils.Euler((0,0,math.radians(rotz)))
    if scale is not None:
        cube.scale = scale
    return cube

def set_group_name(meshdata, value):
    meshdata["MBT"] = value

def get_group_name(meshdata):
    return meshdata["MBT"]

class Module:
    def __init__(self, data, name, group_name):
        self.data = data
        self.name = name
        self.group_name = group_name
        
class ModuleGroup:
    def __init__(self, name, painter, thin=False):
        self.name = name
        self.painter = painter
        self.active = 0
        self.modules = []
        self.thin = thin

        # init
        self.painter.init(self)

    def active_module(self):
        return self.modules[self.active]

class RestoreCursorPos:
    # lets us edit the cursor pos and restore original value nicely
    def __init__(self, mbt):
        self.mbt = mbt
        self.original_pos = None

    def __enter__(self):
        self.original_pos = self.mbt.cursor_pos

    def __exit__(self, exc_type, exc_value, traceback):
        self.mbt.cursor_pos = self.original_pos

class ModularBuildingToolProperties(PropertyGroup):
    metadata_path = StringProperty(
        name = "Metadata Path",
        description = "Path to metadata json file",
        subtype = "FILE_PATH"
      )

class ModularBuildingToolPanel(Panel):
    bl_idname = "view3d.modular_building_tool_panel"
    bl_label = "Modular Building Tool Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "MBT"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        mbt = context.scene.mbt

        layout.prop(mbt, 'metadata_path', text="")
        layout.operator(ModularBuildingMode.bl_idname)

class Painter:
    mbt = None

    def __init__(self):
        self.group = None

    def init(self, group):
        self.group = group

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
                if int(m.rotation_euler.z) == self.mbt.cursor_rot:
                    self.mbt.delete_module(m)
                    break
        else:
            if len(match) > 0:
                self.mbt.delete_module(match[0])  # should only be one

    def clear(self):
        self.mbt.clear()

    def draw_ui(self):
        module_ = self.group.active_module()
        draw_text_2d(module_.group_name, size=15)
        draw_text_2d(module_.name)

class RoomPainter(Painter):
    room_modes = ("Active Module", "Weighted Random", "Dither")

    def init(self, group):
        super().init(group)
        self.group.modules = [None] * 3  # hack

    def paint(self):
        self.room_paint()
        # repaint adjacent cells (could be optimized to just delete walls, which is all it does for now, but that might change in the future anyway)
        self.repaint_adjacent()

    def delete(self):
        self.mbt.clear()
        self.mbt.repaint_adjacent()

    def room_paint(self):
        self.mbt.clear()
        occupied = self.mbt.adjacent_occupied()
        original_rot = self.mbt.cursor_rot
        #paint walls
        if "wall" in self.mbt.weight_info:
            for i in range(4):
                if not occupied[i]:
                    vec = ADJACENCY_VECTORS[i]
                    self.mbt.cursor_rot = normalized_XY_to_Zrot(vec.x, vec.y)
                    wall = self.room_get_module("wall")
                    self.mbt.create_obj(wall)
                else:
                    # todo delete adjacent cell adjacent walls
                    pass
        #paint floor
        if "floor" in self.mbt.weight_info:
            if not occupied[5]:
                floor = self.room_get_module("floor")
                self.mbt.create_obj(floor)
        #paint ceiling
        if "ceiling" in self.mbt.weight_info:
            if not occupied[4]:
                floor = self.room_get_module("ceiling")
                self.mbt.create_obj(floor)
        self.mbt.cursor_rot = original_rot

    def repaint_adjacent(self):
        with RestoreCursorPos(self.mbt):
            orig_curs_pos = self.mbt.cursor_pos
            occupied = self.mbt.adjacent_occupied()
            for i, vec in enumerate(ADJACENCY_VECTORS):
                if occupied[i]:
                    self.mbt.cursor_pos = orig_curs_pos + vec
                    self.room_paint()

    def room_get_module(self, type_):
        # todo define custom room modes with metadata
        if self.mbt.module_groups["room"].active == 0:
            # active module
            return self.mbt.module_groups[type_].active_module().data
        elif self.group.active == 1:
            # weighted random
            return weighted_choice(self.mbt.weight_info[type_])
        elif self.group.active == 2:
            # dither
            # (does this work when pos negative?)
            idx = int(self.mbt.cursor_pos.x + self.mbt.cursor_pos.y + self.mbt.cursor_pos.z)
            idx %= len(self.mbt.weight_info[type_])
            return self.mbt.weight_info[type_][idx][0]

    def draw_ui(self):
        draw_text_2d("room", size=15, color=YELLOW)
        draw_text_2d(self.room_modes[self.group.active], size=20, color=YELLOW)

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
        # get objects near pos, relative to root_obj
        rel_pos = self.mbt.root_obj.matrix_world.inverted() * pos
        return [self.childs[index] for pos, index, dist in self.kd.find_range(rel_pos, SEARCH_RANGE)]

class ModularBuildingModeState:
    # hmm, should be in ModularBuildingMode?
    paint = False
    clear = False
    delete = False
    grab = False

class ModularBuildingTool:
    def __init__(self):
        self.weight_info = {}
        self.metadata = None
        self.root_obj = None
        self.module_groups = {}
        self.active_group = 0
        self.modules = {}
        self.cursor_pos = Vector((0, 0, 0))
        # self.cursor_tilt = 0  # may be useful for slopes (like rollarcoaster tycoon)
        self.cursor_rot = 0
        self.state = ModularBuildingModeState()
        self.grabbed = []
        # used to restore the properties of modules when a grab operation is canceled
        self.original_pos = Vector()
        self.original_rots = []
        self.clipboard = []
        self.clipboard_rots = []

        Painter.mbt = self
        ModuleFinder.mbt = self

    def init_metadata(self, metadata_path):
        with open(metadata_path) as metadata_file:
            self.metadata = json.load(metadata_file)

    def init_module_groups(self):
        #initialize modules list
        self.module_groups['wall']=ModuleGroup('wall', Painter(), thin=True)
        self.module_groups['floor']=ModuleGroup('floor', Painter())
        #self.module_groups.append(ModuleGroup('ceiling'))
        self.module_groups['room'] = ModuleGroup("room", RoomPainter())

    def init_modules(self):
        for m_name, value in self.metadata.items():
            try:
                mesh = bpy.data.meshes[m_name]
            except KeyError:
                print('WARNING: mesh "{}" not found'.format(m_name))
                continue
            if mesh is None:
                print('WARNING: mesh "{}" not found'.format(m_name))
                continue
            g_name = value["type"]
            try:
                group = self.module_groups[g_name]
            except KeyError:
                # create
                group = ModuleGroup(g_name, Painter())  # todo properties?
                self.module_groups[g_name] = group
            module_ = Module(mesh, m_name, g_name)
            self.modules[m_name] = module_
            group.modules.append(module_)
            set_group_name(mesh, g_name)
            weight = get_key(value, 'weight', 1.0)
            try:
                self.weight_info[g_name].append((mesh, weight))  # used for room paint
            except KeyError:
                self.weight_info[g_name] = []

    def init_root_obj(self):
        self.root_obj = bpy.context.object
        if self.root_obj is None:
            bpy.ops.object.empty_add()
            self.root_obj = bpy.context.scene.objects.active

    def get_modules(self):
        finder = ModuleFinder()
        return finder.get_modules_at(self.cursor_pos)

    def clear(self):
        self.delete_modules(self.get_modules())

    def delete_module(self, m):
        bpy.data.objects.remove(m, True)
        update_3dviews()

    def delete_modules(self, modules_):
        # use this when you can, saves calling update_3dview
        for m in modules_:
            bpy.data.objects.remove(m, True)
        update_3dviews()

    def adjacent_occupied(self):
        finder = ModuleFinder()
        return [len(finder.get_modules_at(self.cursor_pos + vec)) > 0 for vec in ADJACENCY_VECTORS]

    def paint(self):
        group = self.get_active_group()
        if self.state.paint:
            group.painter.paint()
        elif self.state.delete:
            group.painter.delete()
        elif self.state.clear:
            group.painter.clear()

    def rotate(self, rot):
        # rotate the cursor and paint
        self.cursor_rot = self.cursor_rot + rot
        for x in self.grabbed:
            x.rotation_euler[2] = x.rotation_euler[2] + math.radians(rot)
        self.paint()

    def translate(self, x, y, z):
        # translate the cursor and paint
        translation = Vector((x, y, z))
        mat_rot = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')

        translation = mat_rot * translation
        self.cursor_pos = self.cursor_pos + translation
        # round cursor_pos to nearest integer
        self.cursor_pos.x = round(self.cursor_pos.x)
        self.cursor_pos.y = round(self.cursor_pos.y)
        self.cursor_pos.z = round(self.cursor_pos.z)
        if self.state.grab:
            for x in self.grabbed:
                x.location = x.location + translation
        self.paint()

    def smart_move(self, x, y, repeat=1):
        # move in x or y, but only if already facing that direction
        mag = magnitude(x, y)
        rot = normalized_XY_to_Zrot(x, y)
        if self.cursor_rot == rot:
            for i in range(repeat):
                self.translate(0, int(mag), 0)
        else:
            self.rotate(rot - self.cursor_rot)

    def on_paint(self, module_):
        self.on_paint_at(self.cursor_pos, self.cursor_rot, module_)

    def on_paint_at(self, pos, rot, module_):
        # call this when creating or moving a module. it replaces overlapping modules
        to_delete = []
        g_to = get_group_name(module_.data)
        finder = ModuleFinder()
        mod_list = finder.get_modules_at(pos)
        for x in mod_list:
            g_from = get_group_name(x.data)
            if g_to == g_from and x != module_:
                # module is already occupied with module of same group, may have to delete
                g = self.module_groups[g_to]
                if g.thin:
                    # only delete if x has same rotation as m (rounded to nearest ordinal direction...)
                    if int(round(math.degrees(x.rotation_euler[2]))) != rot:
                        continue # don't delete existing
                # delete existing module
                to_delete.append(x)
                break  # should only be one
        self.delete_modules(to_delete)

    def start_grab(self):
        self.state.grab = True
        self.grabbed = self.get_modules()
        self.original_pos = self.cursor_pos
        for x in self.grabbed:
            self.original_rots.append(x.rotation_euler.z)

    def end_grab(self, cancel=False):
        self.state.grab = False
        pos = self.cursor_pos
        rot = self.cursor_rot
        if cancel:
            pos = self.original_pos
            #rot = self.original_rot  # todo this is why it is broken?
            for x in range(len(self.grabbed)):
                # reset transform of grabbed
                o = self.grabbed[x]
                rot = self.original_rots[x]
                o.location = self.original_pos
                o.rotation_euler.z = rot
        for g in self.grabbed:
            self.on_paint_at(pos, rot, g)
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
        self.on_paint(obj)
        return obj

    def get_active_group(self):
        if len(self.module_groups) > 0:
            return list(self.module_groups.values())[self.active_group]

    def get_active_module(self):
        act_g = self.get_active_group()
        if act_g is not None:
            return act_g.modules[act_g.active]

    def copy(self):
        self.clipboard = self.get_modules()
        self.clipboard_rots.clear()
        for x in self.clipboard:
            self.clipboard_rots.append(x.rotation_euler.z)

    def paste(self):
        for x in range(len(self.clipboard)):
            o = self.clipboard[x]
            new = self.create_obj(o.data)
            new.rotation_euler.z = self.clipboard_rots[x]

class QuitError(Exception):
    # not an error lol
    pass

class ModularBuildingMode(ModularBuildingTool, Operator):
    bl_idname = "view3d.modular_building_mode"
    bl_label = "Modular Building Mode"

    def __init__(self):
        super().__init__()
        self._handle_3d = None
        self._handle_2d = None
        self.input_map = [
            ['ESC', 'PRESS', self.handle_quit, None],
            ['RET', 'PRESS', self.handle_paint, None],
            ['RET', 'RELEASE', self.handle_paint_end, None],
            ['X', 'PRESS', self.handle_clear, 'SHIFT'],
            ['X', 'PRESS', self.handle_delete, None],
            ['X', 'RELEASE', self.handle_delete_end, None],
            ['TAB', 'PRESS', self.handle_cycle_module_group, 'CTRL'],
            ['TAB', 'PRESS', self.handle_cycle_module, None],
            ['G', 'PRESS', self.handle_grab, None],
            ['LEFT_ARROW', 'PRESS', lambda: self.translate(-1, 0, 0), 'CTRL'],
            ['RIGHT_ARROW', 'PRESS', lambda: self.translate(1, 0, 0), 'CTRL'],
            ['LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0, repeat=4), 'SHIFT'],
            ['RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0, repeat=4), 'SHIFT'],
            ['LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0), None],
            ['RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0), None],
            ['UP_ARROW', 'PRESS', lambda: self.translate(0, 0, 1), 'CTRL'],
            ['DOWN_ARROW', 'PRESS', lambda: self.translate(0, 0, -1), 'CTRL'],
            ['UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1, repeat=4), 'SHIFT'],
            ['DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1, repeat=4), 'SHIFT'],
            ['UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1), None],
            ['DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1), None],
            ['C', 'PRESS', self.handle_copy, 'CTRL'],
            ['V', 'PRESS', self.paste, 'CTRL'],
        ]

    def modal(self, context, event):
        context.area.tag_redraw()
        try:
            return self.handle_input(event)
        except QuitError:
            self.on_quit()
            return {'CANCELLED'}
        except:
            exc_type, exc_msg, exc_tb = sys.exc_info()
            print("Unexpected error line {}: {}".format(exc_tb.tb_lineno, exc_msg))
            return {'CANCELLED'}

    def invoke(self, context, event):
        settings = context.scene.mbt
        if context.area.type == 'VIEW_3D':
            # init
            try:
                self.init_metadata(settings.metadata_path)
            except FileNotFoundError:
                self.blender_report({'ERROR'}, 'metadata file not found {}'.format(settings.metadata_path))
                return {'CANCELLED'}
            except json.decoder.JSONDecodeError as error:
                self.blender_report({'ERROR'}, 'invalid json {}'.format(settings.metadata_path))
                print(error)
                return {'CANCELLED'}

            self.init_module_groups()

            try:
                self.init_modules()
            except (KeyError, ValueError, AttributeError):
                self.report({'ERROR'}, 'metadata format error {}'.format(settings.metadata_path))
                return {'CANCELLED'}

            self.init_root_obj()
            self.init_handlers(context)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

    def init_handlers(self, context):
        args = (self, context)  # the arguments we pass the the callback
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)

    def on_quit(self):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')

    def handle_quit(self):
        if self.state.grab:
            self.end_grab(cancel=True)
            return
        raise QuitError()

    def handle_paint(self):
        if self.state.grab:
            # behaves same as space
            self.end_grab()
        elif not self.state.paint:
            self.state.paint = True
            self.paint()

    def handle_paint_end(self):
        self.state.paint = False

    def handle_delete(self):
        if not self.state.grab and not self.state.delete:
            self.state.delete = True
            self.paint()

    def handle_clear(self):
        if not self.state.grab and not self.state.clear:
            self.state.clear = True
            self.paint()

    def handle_delete_end(self):
        self.state.delete = False
        self.state.clear = False

    def handle_cycle_module_group(self):
        if len(self.module_groups) <= 1:
            self.report({'INFO'}, 'no more module groups to cycle to')
        else:
            self.active_group += 1
            self.active_group %= len(self.module_groups)

    def handle_cycle_module(self):
        act_g = self.get_active_group()
        if act_g is not None:
            if len(act_g.modules) <= 1:
                self.report({'INFO'}, 'no more modules to cycle to')
            else:
                act_g.active += 1
                act_g.active %= len(act_g.modules)
        else:
            self.report({'INFO'}, 'no more modules to cycle to')

    def handle_grab(self):
        if not self.state.grab:
            self.start_grab()
        else:
            self.end_grab()

    def handle_copy(self):
        self.copy()
        self.report({'INFO'}, '({}) modules copied to clipboard'.format(len(self.clipboard)))

    def handle_input(self, event):
        for type_, value, func, modifier in self.input_map:
            if modifier == 'SHIFT' and not event.shift or \
                                    modifier == 'CTRL' and not event.ctrl or \
                                    modifier == 'ALT' and not event.alt:
                continue
            if type_ == event.type and value == event.value:
                func()
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

def draw_callback_3d(self, context):
    mat_world = self.root_obj.matrix_world
    mat_rot = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
    mat_trans = mathutils.Matrix.Translation(self.cursor_pos)
    mat = mat_trans * mat_rot
    mat = mat_world * mat
    t_arrow = mat_transform(mat, ARROW)
    color = PURPLE if not self.state.grab else GREEN
    bgl.glDisable(bgl.GL_DEPTH_TEST)
    draw_poly(t_arrow, color)

    restore_gl_defaults()

def draw_callback_2d(self, context):
    # draw text
    text_cursor.x = 20
    text_cursor.y = 130

    group = self.get_active_group()
    if group is not None:
        group.painter.draw_ui()
    else:
        draw_text_2d("No modules found", size=15, color=RED)

    # info
    vec3_str = "{}, {}, {}".format(int(self.cursor_pos.x), int(self.cursor_pos.y), int(self.cursor_pos.z))
    draw_text_2d("cursor pos: " + vec3_str, size=15, color=WHITE)

    restore_gl_defaults()

class ConnectPortals(Operator):
    # connect portals utility
    bl_idname = "view3d.connect_portals"
    bl_label = "Connect Portals"

    @classmethod
    def poll(self, context):
        return len(context.selected_objects) == 2

    def execute(self, context):
        obj1, obj2 = context.selected_objects
        copy_location = obj1.constraints.new('COPY_LOCATION')
        copy_rotation = obj1.constraints.new('COPY_ROTATION')
        copy_location.target = obj2
        copy_rotation.target = obj2
        copy_rotation.use_offset = True
        return {'FINISHED'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.mbt = PointerProperty(type=ModularBuildingToolProperties)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.Scene.mbt = None

if __name__ == "__main__":
    register()