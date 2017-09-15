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
    "name": "Tilemap3D",
    "author": "Will Alcorn",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View > Tools > T3D",
    "description": "create 3D tilemaps",
    "warning": "",
    "wiki_url": "https://github.com/alcornwill/modular_building_tool",
    "category": "3D View",
}

import sys
import bpy
from math import ceil, sqrt
from mathutils import Vector, Quaternion, Euler, Matrix
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    Header
)
from .tilemap3d import *

addon_keymaps = []

class QuitError(Exception):
    # note: not an error
    pass

class KeyInput:
    def __init__(self, type_, value, func, ctrl=False, shift=False):
        self.type = type_
        self.value = value
        self.func = func
        self.ctrl = ctrl
        self.shift = shift

class Tilemap3DProperties(PropertyGroup):
    tile3d_library_path = StringProperty(
        name="Tile3D Library Path",
        description="Path to your tile3d library .blend file",
        subtype="FILE_PATH"
    )

class Tilemap3DPanel(Panel):
    bl_idname = "view3d.tilemap3d_panel"
    bl_label = "Tilemap3D Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        t3d = context.scene.t3d

        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.scale_x = 3.0
        sub.prop(t3d, 'tile3d_library_path', text="")
        row.operator(LinkTile3DLibrary.bl_idname)
        layout.operator(T3DPaintMode.bl_idname)
        layout.operator(SetActiveTile3D.bl_idname)
        layout.separator()
        layout.operator(ConnectObjects.bl_idname)
        layout.separator()
        layout.operator(T3DSetupTilesOperator.bl_idname)

class T3DPaintMode(Tilemap3D, Operator):
    """Modal operator for constructing modular scenes"""
    bl_idname = "view3d.t3d_paint_mode"
    bl_label = "T3D Paint Mode"

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
            KeyInput('X', 'PRESS', self.handle_clear),
            KeyInput('X', 'RELEASE', self.handle_delete_end),
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
            KeyInput('B', 'PRESS', self.handle_select)
        ]

    @classmethod
    def poll(cls, context):
        return not T3DPaintMode.running_modal

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
        if T3DPaintMode.running_modal: return {'CANCELLED'}
        T3DPaintMode.running_modal = True
        settings = context.scene.t3d
        if context.area.type == 'VIEW_3D':
            # init
            self.init()
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
        T3DPaintMode.running_modal = False

    def handle_quit(self):
        if self.state.grab:
            self.end_grab(cancel=True)
        elif self.state.select:
            # cancel
            self.state.select = False
            self.construct_select_cube()
        else:
            raise QuitError()

    # it's weird that the state management is split between Tilemap3D and PaintMode like this...
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

    def handle_grab(self):
        if not self.state.grab:
            self.start_grab()
        else:
            self.end_grab()

    def handle_copy(self):
        self.copy()
        self.report({'INFO'}, '({}) tiles copied to clipboard'.format("1" if self.clipboard else "0"))

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
    mat_scale = Matrix.Scale(self.tilesize_z, 4, Vector((0.0, 0.0, 1.0)))

    mat = mat_world * mat_scale

    color = YELLOW if self.state.select else WHITE
    t_cube = mat_transform_edges(mat, self.select_cube)
    draw_wire(t_cube, color)

    mat_rot = Matrix.Rotation(math.radians(self.cursor_rot), 4, 'Z')
    mat_trans = Matrix.Translation(self.cursor_pos)
    mat = mat_scale * mat_trans * mat_rot
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

    group = self.get_active_tile3d()
    if group is not None:
        draw_text_2d(group, size=15, color=GREY)

    # info
    vec3_str = "{}, {}, {}".format(int(self.cursor_pos.x), int(self.cursor_pos.y), int(self.cursor_pos.z))
    draw_text_2d("cursor pos: " + vec3_str, size=15, color=GREY)

    restore_gl_defaults()

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

class LinkTile3DLibrary(Operator):
    """Link all groups from linked library"""
    bl_idname = "view3d.link_tile3d_library"
    bl_label = "Link"

    def execute(self, context):
        t3d = context.scene.t3d
        with bpy.data.libraries.load(t3d.tile3d_library_path, link=True) as (data_src, data_dst):
            # link groups
            data_dst.groups = data_src.groups
            self.report({'INFO'}, 'linked {} groups'.format(len(data_src.groups)))
            # link src scene. assume only has one
            scene = data_src.scenes[0]
            data_dst.scenes = [scene] # will this link all groups anyway?
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

class SetActiveTile3D(Operator):
    # we need this because modal operator only works for one window
    bl_idname = "view_3d.object_picker"
    bl_label = "Set Active Module"

    tile3d = None

    @classmethod
    def poll(cls, context):
        if not T3DPaintMode.running_modal: return False
        obj = context.object
        if obj is None: return False
        # assume is group instance
        group = get_group(obj)
        if group is None:
            # else might be the linked object
            group = get_first_group_name(obj)
        SetActiveTile3D.tile3d = group
        return True

    def execute(self, context):
        t3d = Tilemap3D.instance
        t3d.set_active_tile3d(self.tile3d)
        update_3dviews()
        return {'FINISHED'}

def select_all():
    for obj in bpy.data.objects:
        obj.select = True

def deselect_all():
    for obj in bpy.data.objects:
        obj.select = False

class T3DSetupTilesOperator(bpy.types.Operator):
    """Setup 3D Tiles for tile library"""
    bl_idname = 'view3d.t3d_setup_tiles'
    bl_label = 'Setup 3D Tiles'

    def __init__(self):
        bpy.types.Operator.__init__(self)
        self.objects = None

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        self.setup_tiles()
        return {'FINISHED'}

    def remove_all_groups(self):
        select_all()
        for group in self.objects:
            bpy.ops.group.objects_remove_all()
        deselect_all()

    def create_groups(self):
        for obj in self.objects:
            group = bpy.data.groups.new(name=obj.name)
            group.name = obj.name  # insist
            group.objects.link(obj)
            group.dupli_offset = obj.location

    def layout_in_grid(self, border=2):
        dimx = ceil(sqrt(len(self.objects)))
        count = 0
        x = 0
        y = 0
        offset = ((dimx - 1) * border) / 2

        for obj in self.objects:
            obj.location.x = x - offset
            obj.location.y = y - offset
            count += 1
            x += border
            if count >= dimx:
                y += border
                x = 0
                count = 0

    def setup_tiles(self):
        self.objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        self.layout_in_grid()
        self.remove_all_groups()
        self.create_groups()

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.t3d = PointerProperty(type=Tilemap3DProperties)

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km.keymap_items.new(SetActiveTile3D.bl_idname, 'S', 'PRESS')
    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.Scene.t3d = None

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()

if __name__ == "__main__":
    register()