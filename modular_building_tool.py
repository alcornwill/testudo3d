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

ROOM_MODES = ("Active Module", "Weighted Random", "Dither")
# todo room should derive 'Painter', modes should derive 'PainterMode'?
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

def find_with_name(lst, name):
    for item in lst:
        if item.name == name:
            return item

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
        self.g_name = group_name
        
class ModuleGroup:
    def __init__(self, name, thin=False):
        self.name = name
        self.active = 0
        self.modules = []
        self.thin = thin
        
    def active_module(self):
        return self.modules[self.active]

class QuitError(Exception):
    # not an error lol
    pass

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
        default = "C:\\Users\\alcor_000\\Projects\\modular_building_tool\\metadata.json",
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

class ModularBuildingTool:
    def __init__(self):
        self._handle_3d = None
        self._handle_2d = None
        self.room_info = {}
        self.metadata = None
        self.root_obj = None
        self.module_groups = {}  # each group contains a list of modules
        self.active_group = 0
        self.modules = {}
        self.cursor_pos = Vector((0, 0, 0))
        # self.cursor_tilt = 0  # may be useful for slopes (like rollarcoaster tycoon)
        self.cursor_rot = 0
        # state
        self.paint = False
        self.clear = False
        self.delete = False
        self.grab = False
        self.grabbed = []
        # used to restore the properties of modules when a grab operation is canceled
        self.original_pos = Vector()
        self.original_rots = []
        self.clipboard = []
        self.clipboard_rots = []
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
            ['LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0), None],
            ['RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0), None],
            ['UP_ARROW', 'PRESS', lambda: self.translate(0, 0, 1), 'CTRL'],
            ['DOWN_ARROW', 'PRESS', lambda: self.translate(0, 0, -1), 'CTRL'],
            ['UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1), None],
            ['DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1), None],
            ['C', 'PRESS', self.handle_copy, 'CTRL'],
            ['V', 'PRESS', self.handle_paste, 'CTRL'],
        ]

    def init_handlers(self, context):
        # the arguments we pass the the callback
        args = (self, context)
        # Add the region OpenGL drawing callback
        # draw in view space with 'POST_VIEW' and 'PRE_VIEW'
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)

    def init_metadata(self, metadata_path):
        # todo handle errors
        with open(metadata_path) as metadata_file:
            self.metadata = json.load(metadata_file)

    def init_modules(self):
        #initialize modules list
        self.module_groups['wall']=ModuleGroup('wall', thin=True)
        self.module_groups['floor']=ModuleGroup('floor')
        #self.module_groups.append(ModuleGroup('ceiling'))
        self.room_info = {
            "wall": [],
            "floor": []
        }
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
            group = self.module_groups[g_name]
            module_ = Module(mesh, m_name, g_name)
            self.modules[m_name] = module_
            group.modules.append(module_)
            set_group_name(mesh, g_name)
            weight = value["weight"]
            self.room_info[g_name].append((mesh, weight))  # used for room paint
        # add 'room' paint
        room = ModuleGroup("room")
        room.modules = [None] * 3 # hack
        self.module_groups['room'] = room

    def init_root_obj(self):
        self.root_obj = bpy.context.object
        if self.root_obj is None:
            bpy.ops.object.empty_add()
            self.root_obj = bpy.context.scene.objects.active

    def on_quit(self):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')

    def get_modules(self):
        return self.get_modules_at(self.cursor_pos)

    def get_modules_at(self, pos):
        # get objects near pos, relative to root_obj
        rel_pos = self.root_obj.matrix_world.inverted() * pos
        childs = self.root_obj.children
        size = len(childs)
        kd = mathutils.kdtree.KDTree(size)

        for i, child in enumerate(childs):
            kd.insert(child.location, i)
        kd.balance()
        return [childs[index] for pos, index, dist in kd.find_range(rel_pos, 0.5)]

    def blender_report(self, level, msg):
        raise NotImplementedError()

    def handle_quit(self):
        if self.grab:
            self.end_grab(cancel=True)
            return
        raise QuitError()

    def handle_paint(self):
        if self.grab:
            # behaves same as space
            self.end_grab()
        elif not self.paint:
            self.paint = True
            self.cursor_paint()

    def handle_paint_end(self):
        self.paint = False

    def handle_delete(self):
        if not self.grab and not self.delete:
            self.delete = True
            self.cursor_paint()

    def handle_clear(self):
        if not self.grab and not self.clear:
            self.clear = True
            self.cursor_paint()

    def handle_delete_end(self):
        self.delete = False
        self.clear = False

    def handle_cycle_module_group(self):
        if len(self.module_groups) <= 1:
            self.blender_report({'INFO'}, 'no more module groups to cycle to')
        else:
            self.active_group += 1
            self.active_group %= len(self.module_groups)

    def handle_cycle_module(self):
        act_g = self.get_active_group()
        if act_g is not None:
            if len(act_g.modules) <= 1:
                self.blender_report({'INFO'}, 'no more modules to cycle to')
            else:
                act_g.active += 1
                act_g.active %= len(act_g.modules)
        else:
            self.blender_report({'INFO'}, 'no more modules to cycle to')

    def handle_grab(self):
        if not self.grab:
            self.start_grab()
        else:
            self.end_grab()

    def handle_copy(self):
        # copy
        self.clipboard = self.get_modules()
        self.clipboard_rots.clear()
        for x in self.clipboard:
            self.clipboard_rots.append(x.rotation_euler.z)
        self.blender_report({'INFO'}, '({}) modules copied to clipboard'.format(len(self.clipboard)))

    def handle_paste(self):
        # paste
        for x in range(len(self.clipboard)):
            o = self.clipboard[x]
            new = self.create_obj(o.data)
            new.rotation_euler.z = self.clipboard_rots[x]

    def handle_input(self, event):
        for type_, value, func, modifier in self.input_map:
            if modifier == 'SHIFT' and not event.shift or\
                modifier == 'CTRL' and not event.ctrl or\
                modifier == 'ALT' and not event.alt:
                continue
            if type_ == event.type and value == event.value:
                func()
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def clear_at_cursor(self):
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
        return [len(self.get_modules_at(self.cursor_pos + vec)) > 0 for vec in ADJACENCY_VECTORS]

    def room_get_module(self, type_):
        act_g = self.get_active_group()  # should always be 'room'...
        # todo ability to define custom rooms with metadata
        if self.module_groups["room"].active == 0:
            # active module
            return self.module_groups[type_].active_module().data
        elif act_g.active == 1:
            # weighted random
            return weighted_choice(self.room_info[type_])
        elif act_g.active == 2:
            # dither
            # (does this work when pos negative?)
            idx = int(self.cursor_pos.x + self.cursor_pos.y + self.cursor_pos.z)
            idx %= len(self.room_info[type_])
            return self.room_info[type_][idx][0]

    def room_paint(self):
        self.clear_at_cursor()
        occupied = self.adjacent_occupied()
        original_rot = self.cursor_rot
        #paint walls
        if "wall" in self.room_info:
            for i in range(4):
                if not occupied[i]:
                    vec = ADJACENCY_VECTORS[i]
                    self.cursor_rot = normalized_XY_to_Zrot(vec.x, vec.y)
                    wall = self.room_get_module("wall")
                    self.create_obj(wall)
                else:
                    # todo delete adjacent cell adjacent walls
                    pass
        #paint floor
        if "floor" in self.room_info:
            if not occupied[5]:
                floor = self.room_get_module("floor")
                self.create_obj(floor)
        #paint ceiling
        if "ceiling" in self.room_info:
            if not occupied[4]:
                floor = self.room_get_module("ceiling")
                self.create_obj(floor)
        self.cursor_rot = original_rot

    def repaint_adjacent(self):
        with RestoreCursorPos(self):
            orig_curs_pos = self.cursor_pos
            occupied = self.adjacent_occupied()
            for i, vec in enumerate(ADJACENCY_VECTORS):
                if occupied[i]:
                    self.cursor_pos = orig_curs_pos + vec
                    self.room_paint()

    def cursor_paint(self):
        #todo abstract 'paint_func' so object oriented
        # Painter?
        if self.paint:
            act_g = self.get_active_group()
            if act_g.name == "room":
                self.room_paint()
                # repaint adjacent cells (could be optimized to just delete walls, which is all it does for now, but that might change in the future anyway)
                self.repaint_adjacent()
            else:
                # normal paint
                act = act_g.active_module()
                if act is not None:
                    self.create_obj(act.data)
        elif self.delete:
            # delete
            act_g = self.get_active_group()
            if act_g.name == "room":
                self.clear_at_cursor()
                self.repaint_adjacent()
            else:
                # delete only modules of same type
                match = [x for x in self.get_modules() if get_group_name(x.data) == act_g.name]
                if act_g.thin:
                    # only delete if facing same as cursor rot
                    for m in match:
                        if int(m.rotation_euler.z) == self.cursor_rot:
                            self.delete_module(m)
                            break
                else:
                    if len(match) > 0:
                        self.delete_module(match[0])  # should only be one
        elif self.clear:
            self.clear_at_cursor()

    def rotate(self, rot):
        # rotate the cursor and paint
        self.cursor_rot = self.cursor_rot + rot
        for x in self.grabbed:
            x.rotation_euler[2] = x.rotation_euler[2] + math.radians(rot)
        self.cursor_paint()

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
        if self.grab:
            for x in self.grabbed:
                x.location = x.location + translation
        self.cursor_paint()

    def smart_move(self, x, y):
        mag = magnitude(x, y)
        # move in x or y, but only if already facing that direction
        rot = normalized_XY_to_Zrot(x, y)
        if self.cursor_rot == rot:
            self.translate(0, int(mag), 0)
        else:
            self.rotate(rot - self.cursor_rot)

    def paint_at_cursor(self, modules_):
        # todo want to rename 'paint'...
        self.paint_at(self.cursor_pos, self.cursor_rot, modules_)

    def paint_at(self, pos, rot, modules_):
        # call this when creating or moving a module. it replaces overlapping modules
        to_delete = []
        for m in modules_:
            g_to = get_group_name(m.data)
            mod_list = self.get_modules_at(pos)
            for x in mod_list:
                g_from = get_group_name(x.data)
                if g_to == g_from and x != m:
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
        self.grab = True
        self.grabbed = self.get_modules()
        self.original_pos = self.cursor_pos
        for x in self.grabbed:
            self.original_rots.append(x.rotation_euler.z)

    def end_grab(self, cancel=False):
        self.grab = False
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
        self.paint_at(pos, rot, self.grabbed)
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
        self.paint_at_cursor((obj,))
        return obj

    def get_active_group(self):
        if len(self.module_groups) > 0:
            return list(self.module_groups.values())[self.active_group]

    def get_active_module(self):
        act_g = self.get_active_group()
        if act_g is not None:
            return act_g.modules[act_g.active]

class ModularBuildingMode(ModularBuildingTool, Operator):
    bl_idname = "view3d.modular_building_mode"
    bl_label = "Modular Building Mode"

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

    def invoke(self, context, event):
        settings = context.scene.mbt
        if context.area.type == 'VIEW_3D':
            # init
            self.init_handlers(context)
            # (reload every time invoked. too slow?)
            self.init_metadata(settings.metadata_path)
            self.init_modules()
            self.init_root_obj()
            return {'RUNNING_MODAL'}
        else:
            self.blender_report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

    def blender_report(self, level, msg):
        self.report(level, msg)

def draw_callback_3d(self, context):
    mat_world = self.root_obj.matrix_world
    mat_rot = mathutils.Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
    mat_trans = mathutils.Matrix.Translation(self.cursor_pos)
    mat = mat_trans * mat_rot
    mat = mat_world * mat
    t_arrow = mat_transform(mat, ARROW)
    color = PURPLE if not self.grab else GREEN
    bgl.glDisable(bgl.GL_DEPTH_TEST)
    draw_poly(t_arrow, color)

    restore_gl_defaults()

def draw_callback_2d(self, context):
    # draw text
    text_cursor.x = 20
    text_cursor.y = 130

    act_g = self.get_active_group()
    if act_g is not None:
        if act_g.name == "room":
            draw_text_2d("room", size=15, color=YELLOW)
            draw_text_2d(ROOM_MODES[act_g.active], size=20, color=YELLOW)
        else:
            act = act_g.active_module()
            draw_text_2d(act.g_name, size=15)  # group name
            draw_text_2d(act.name)  # module name
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

    def invoke(self, context, event):
        obj1, obj2 = context.selected_objects
        copy_location = obj1.constraints.new('COPY_LOCATION')
        copy_rotation = obj1.constraints.new('COPY_ROTATION')
        copy_location.target = obj2
        copy_rotation.target = obj2
        copy_rotation.use_offset = True
        return {'PASS_THROUGH'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.mbt = PointerProperty(type=ModularBuildingToolProperties)

def unregister():
    bpy.utils.unregister_module(__name__)
    del bpy.types.Scene.mbt

if __name__ == "__main__":
    register()