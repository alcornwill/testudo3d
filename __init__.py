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
# noinspection PyUnresolvedReferences
from mathutils import Vector, Quaternion, Euler
# noinspection PyUnresolvedReferences
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
)
# noinspection PyUnresolvedReferences
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    Header
)
from .modular_building_tool import *

addon_keymaps = []

class QuitError(Exception):
    # not an error lol
    pass

class KeyInput:
    def __init__(self, type_, value, func, ctrl=False, shift=False):
        self.type = type_
        self.value = value
        self.func = func
        self.ctrl = ctrl
        self.shift = shift

class ModularBuildingToolProperties(PropertyGroup):
    metadata_path = StringProperty(
        name="Metadata Path",
        description="Path to metadata json file",
        subtype="FILE_PATH"
    )

    module_library_path = StringProperty(
        name="Module Library Path",
        description="Path to your module library .blend file",
        subtype="FILE_PATH"
    )

    module_type = StringProperty(
        name="Module Type",
        description="module type: 'floor', 'wall' or 'ceiling'"
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
        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.scale_x = 3.0
        sub.prop(mbt, 'module_library_path', text="")
        row.operator(LinkAllMesh.bl_idname)
        layout.operator(ModularBuildingMode.bl_idname)
        layout.operator(SetActiveModule.bl_idname)
        self.display_selected_module_type(context)
        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.scale_x = 3.0
        sub.prop(mbt, 'module_type')
        row.operator(SetModuleTypeOperator.bl_idname)
        layout.separator()
        layout.operator(ConnectObjects.bl_idname)

    def display_selected_module_type(self, context):
        active_object = context.active_object
        if active_object is not None:
            data = active_object.data
            if data is not None:
                current_type = None
                if CUSTOM_PROPERTY_TYPE in data:
                    current_type = data[CUSTOM_PROPERTY_TYPE]
                self.layout.label("Selected Module Type: {}".format(current_type))

class ModularBuildingMode(ModularBuildingTool, Operator):
    """Modal operator for constructing modular scenes"""
    bl_idname = "view3d.modular_building_mode"
    bl_label = "Modular Building Mode"

    running_modal = False

    def __init__(self):
        super().__init__()
        self._handle_3d = None
        self._handle_2d = None
        self.active_scene = None
        self.input_map = [
            KeyInput('ESC', 'PRESS', self.handle_quit),
            KeyInput('RET', 'PRESS', self.handle_paint),
            KeyInput('RET', 'RELEASE', self.handle_paint_end),
            KeyInput('X', 'PRESS', self.handle_clear, shift=True),
            KeyInput('X', 'PRESS', self.handle_delete),
            KeyInput('X', 'RELEASE', self.handle_delete_end),
            KeyInput('TAB', 'PRESS', lambda: self.handle_cycle_module(-1), ctrl=True),
            KeyInput('TAB', 'PRESS', lambda: self.handle_cycle_module(1), None),
            KeyInput('G', 'PRESS', self.handle_grab, None),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.translate(-1, 0, 0), ctrl=True),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.translate(1, 0, 0), ctrl=True),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.translate(0, 0, 1), ctrl=True),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.translate(0, 0, -1), ctrl=True),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0, repeat=4), shift=True),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0, repeat=4), shift=True),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1, repeat=4), shift=True),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1, repeat=4), shift=True),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0)),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0)),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1)),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1)),
            KeyInput('C', 'PRESS', self.handle_copy, ctrl=True),
            KeyInput('V', 'PRESS', self.paste, ctrl=True),
            KeyInput('B', 'PRESS', self.handle_select),
            KeyInput('ONE', 'PRESS', lambda: self.set_active_group(0)),
            KeyInput('TWO', 'PRESS', lambda: self.set_active_group(1)),
            KeyInput('THREE', 'PRESS', lambda: self.set_active_group(2)),
            KeyInput('FOUR', 'PRESS', lambda: self.set_active_group(3)),
            KeyInput('FIVE', 'PRESS', lambda: self.set_active_group(4)),
            KeyInput('SIX', 'PRESS', lambda: self.set_active_group(5)),
            KeyInput('SEVEN', 'PRESS', lambda: self.set_active_group(6)),
            KeyInput('EIGHT', 'PRESS', lambda: self.set_active_group(7)),
            KeyInput('NINE', 'PRESS', lambda: self.set_active_group(8)),
            KeyInput('ZERO', 'PRESS', lambda: self.set_active_group(9))
        ]

    @classmethod
    def poll(cls, context):
        return not ModularBuildingMode.running_modal

    def modal(self, context, event):
        context.area.tag_redraw()
        try:
            return self.handle_input(event)
        except QuitError:
            self.on_quit()
            return {'CANCELLED'}
        except:
            exc_type, exc_msg, exc_tb = sys.exc_info()
            self.error("Unexpected error line {}: {}".format(exc_tb.tb_lineno, exc_msg))
            self.on_quit()
            return {'CANCELLED'}

    def invoke(self, context, event):
        if ModularBuildingMode.running_modal: return {'CANCELLED'}
        ModularBuildingMode.running_modal = True
        settings = context.scene.mbt
        if context.area.type == 'VIEW_3D':
            # init
            self.init(settings.metadata_path)
            self.init_handlers(context)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

    def error(self, msg):
        super().error(msg)
        self.report({'ERROR'}, msg)

    def init_handlers(self, context):
        self.active_scene = context.scene
        args = (self, context)  # the arguments we pass the the callback
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)

    def on_quit(self):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
        ModularBuildingMode.running_modal = False

    def handle_quit(self):
        if self.state.grab:
            self.end_grab(cancel=True)
        elif self.state.select:
            # cancel
            self.state.select = False
            self.construct_select_cube()
        else:
            raise QuitError()

    # it's weird that the state management is split between ModularBuildingTool and ModularBuildingMode like this...
    def handle_paint(self):
        if self.state.grab:
            # behaves same as space
            self.end_grab()
        elif self.state.select:
            self.state.paint = True
            self.end_select()
            self.state.paint = False
        elif not self.state.paint:
            self.state.paint = True
            self.cdraw()

    def handle_paint_end(self):
        self.state.paint = False

    def handle_delete(self):
        if self.state.select:
            self.state.delete = True
            self.end_select()
            self.state.delete = False
        elif not self.state.grab and not self.state.delete:
            self.state.delete = True
            self.cdraw()

    def handle_clear(self):
        if self.state.select:
            self.state.clear = True
            self.end_select()
            self.state.clear = False
        elif not self.state.grab and not self.state.clear:
            self.state.clear = True
            self.cdraw()

    def handle_delete_end(self):
        self.state.delete = False
        self.state.clear = False

    def handle_cycle_module_group(self):
        if len(self.module_groups) <= 1:
            self.report({'INFO'}, 'no more module groups to cycle to')
        else:
            self.active_group += 1
            self.active_group %= len(self.module_groups)

    def handle_cycle_module(self, i):
        act_g = self.get_active_group()
        if act_g is not None:
            if len(act_g.modules) <= i:
                self.report({'INFO'}, 'no more modules to cycle to')
            else:
                act_g.active += i
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

    def handle_select(self):
        if not self.state.select:
            self.start_select()
        else:
            # cancel
            self.state.select = False
            self.construct_select_cube()

    def handle_input(self, event):
        for keyinput in self.input_map:
            if (keyinput.shift and not event.shift or
                keyinput.ctrl and not event.ctrl):
                continue
            if keyinput.type == event.type and keyinput.value == event.value:
                keyinput.func()
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

def draw_callback_3d(self, context):
    if context.scene != self.active_scene: return
    mat_world = self.root_obj.matrix_world

    mat = mat_world

    color = YELLOW if self.state.select else WHITE
    t_cube = mat_transform_edges(mat, self.select_cube)
    draw_wire(t_cube, color)

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
    if context.scene != self.active_scene: return
    # draw text
    text_cursor.x = 20
    text_cursor.y = 140

    group = self.get_active_group()
    if group is not None:
        group.painter.draw_ui()
    else:
        draw_text_2d("No modules found", size=15, color=RED)

    # info
    vec3_str = "{}, {}, {}".format(int(self.cursor_pos.x), int(self.cursor_pos.y), int(self.cursor_pos.z))
    draw_text_2d("cursor pos: " + vec3_str, size=15, color=GREY)

    restore_gl_defaults()

class SetModuleTypeOperator(Operator):
    """Set module type of selected objects"""
    bl_idname = "view3d.set_module_type"
    bl_label = "Set Module Type"

    @classmethod
    def poll(self, context):
        return context.object is not None

    def execute(self, context):
        mbt = context.scene.mbt
        selected = context.selected_objects
        for obj in selected:
            data = obj.data
            if data is not None:
                data[CUSTOM_PROPERTY_TYPE] = mbt.module_type
        return {'FINISHED'}

class ConnectObjects(Operator):
    """Connect two objects with constraints utility"""
    bl_idname = "view3d.connect_objects"
    bl_label = "Connect Objects"

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT" and len(context.selected_objects) == 2

    def execute(self, context):
        # obj1, obj2 = context.selected_objects
        obj1, obj2 = bpy.selection
        copy_location = obj1.constraints.new('COPY_LOCATION')
        copy_rotation = obj1.constraints.new('COPY_ROTATION')
        copy_location.target = obj2
        copy_rotation.target = obj2
        copy_location.use_offset = True
        copy_rotation.use_offset = True
        return {'FINISHED'}

class LinkAllMesh(Operator):
    """Link all meshes from module library"""
    bl_idname = "view3d.link_all_mesh"
    bl_label = "Link"

    def execute(self, context):
        mbt = context.scene.mbt
        with bpy.data.libraries.load(mbt.module_library_path, link=True) as (data_src, data_dst):
            # link meshes
            data_dst.meshes = data_src.meshes
            self.report({'INFO'}, 'linked {} meshes'.format(len(data_src.meshes)))
            # link src scene. assume only has one
            scene = data_src.scenes[0]
            data_dst.scenes = [scene]
        return {'FINISHED'}

class Selection(Header):
    # context.selected_objects doesn't respect selection order, so we have to do this...
    bl_label = "Selection"
    bl_space_type = "VIEW_3D"

    def __init__(self):
        self.select()

    # lol
    def draw(self, context):
        pass

    @staticmethod
    def select():
        selected = bpy.context.selected_objects
        n = len(selected)

        if n == 0:
            bpy.selection = []
        else:
            if n == 1:
                bpy.selection = []
                bpy.selection.append(selected[0])
            elif n > len(bpy.selection):
                for obj in selected:
                    if obj not in bpy.selection:
                        bpy.selection.append(obj)
            elif n < len(bpy.selection):
                for obj in bpy.selection:
                    if obj not in selected:
                        bpy.selection.remove(obj)

class SmartMove(Operator):
    bl_idname = "view3d.smart_move"
    bl_label = "Smart Move"

    running_modal = False
    bi = 1.0  # big increment
    si = 0.1  # small increment

    # todo override header (hide gizmo?)

    def __init__(self):
        self.original_pos = None
        self.original_rot = None
        self.last_rot = None
        self.input_map = [
            KeyInput('ESC', 'PRESS', self.handle_cancel),
            KeyInput('RIGHTMOUSE', 'PRESS', self.handle_cancel),
            KeyInput('RET', 'PRESS', self.handle_commit),
            KeyInput('LEFTMOUSE', 'PRESS', self.handle_commit),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.translate(-self.si, 0, 0), ctrl=True, shift=True),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.translate(self.si, 0, 0), ctrl=True, shift=True),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.translate(0, 0, self.si), ctrl=True, shift=True),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.translate(0, 0, -self.si), ctrl=True, shift=True),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.translate(-self.bi, 0, 0), ctrl=True),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.translate(self.bi, 0, 0), ctrl=True),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.translate(0, 0, self.bi), ctrl=True),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.translate(0, 0, -self.bi), ctrl=True),
            # KeyInput('LEFT_ARROW', 'PRESS', lambda: self.smart_move(-1, 0, repeat=4), shift=True),
            # KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.smart_move(1, 0, repeat=4), shift=True),
            # KeyInput('UP_ARROW', 'PRESS', lambda: self.smart_move(0, 1, repeat=4), shift=True),
            # KeyInput('DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -1, repeat=4), shift=True),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.smart_move(-self.si, 0), shift=True),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.smart_move(self.si, 0), shift=True),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.smart_move(0, self.si), shift=True),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -self.si), shift=True),
            KeyInput('LEFT_ARROW', 'PRESS', lambda: self.smart_move(-self.bi, 0)),
            KeyInput('RIGHT_ARROW', 'PRESS', lambda: self.smart_move(self.bi, 0)),
            KeyInput('UP_ARROW', 'PRESS', lambda: self.smart_move(0, self.bi)),
            KeyInput('DOWN_ARROW', 'PRESS', lambda: self.smart_move(0, -self.bi)),
        ]

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def invoke(self, context, event):
        if SmartMove.running_modal: return {'CANCELLED'}
        if context.area.type == 'VIEW_3D':
            self.init()
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

    def modal(self, context, event):
        context.area.tag_redraw()
        try:
            return self.handle_input(event)
        except QuitError:
            return self.quit()
        except:
            exc_type, exc_msg, exc_tb = sys.exc_info()
            logging.error("Unexpected error line {}: {}".format(exc_tb.tb_lineno, exc_msg))
            return self.quit()

    def quit(self):
        SmartMove.running_modal = False
        return {'CANCELLED'}

    def init(self):
        SmartMove.running_modal = True
        bpy.context.window_manager.modal_handler_add(self)
        self.original_pos = bpy.context.object.location.copy()
        self.original_rot = bpy.context.object.rotation_euler.copy()

    def handle_input(self, event):
        for keyinput in self.input_map:
            if (keyinput.shift and not event.shift or
                keyinput.ctrl and not event.ctrl):
                continue
            if keyinput.type == event.type and keyinput.value == event.value:
                keyinput.func()
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def handle_cancel(self):
        bpy.context.object.location = self.original_pos
        bpy.context.object.rotation_euler = self.original_rot
        raise QuitError()

    def handle_commit(self):
        raise QuitError()

    def translate(self, x, y, z):
        vec = Vector((x, y, z))
        vec.rotate(bpy.context.object.rotation_euler)
        bpy.ops.transform.translate(value=vec)

    def smart_move(self, x, y, repeat=1):
        # move in x or y, but only if already facing that direction
        mag = max(abs(x), abs(y))
        z = normalized_XY_to_Zrot_rad(x, y)
        rot = Euler((0.0, 0.0, z))
        # obj_rot = bpy.context.object.rotation_quaternion
        obj_rot = bpy.context.object.rotation_euler.to_quaternion()  # wtf
        dif = obj_rot.rotation_difference(rot.to_quaternion())
        if dif.angle < 0.01:
            # translate
            vec = Vector((0.0, mag, 0.0))
            vec.rotate(obj_rot)
            for i in range(repeat):
                bpy.ops.transform.translate(value=vec)
        else:
            # rotate
            bpy.context.object.rotation_euler = rot

class SetActiveModule(Operator):
    bl_idname = "view_3d.object_picker"
    bl_label = "Set Active Module"

    group = None
    module_ = None

    @classmethod
    def poll(cls, context):
        if not ModularBuildingMode.running_modal: return False
        obj = context.object
        if obj is None: return False
        data = obj.data
        if data is None: return False
        is_module = CUSTOM_PROPERTY_TYPE in data
        if not is_module: return False
        SetActiveModule.group = data[CUSTOM_PROPERTY_TYPE]
        SetActiveModule.module_ = data.name
        return True

    def execute(self, context):
        mbt = ModularBuildingTool.instance
        mbt.set_active_group_name(self.group)
        mbt.set_active_module_name(self.module_)
        update_3dviews()
        return {'FINISHED'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.mbt = PointerProperty(type=ModularBuildingToolProperties)

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km.keymap_items.new(SmartMove.bl_idname, 'K', 'PRESS')
    km.keymap_items.new(SetActiveModule.bl_idname, 'E', 'PRESS')

    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.Scene.mbt = None

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)

    addon_keymaps.clear()

if __name__ == "__main__":
    register()
