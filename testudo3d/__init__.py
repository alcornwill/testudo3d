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
    "name": "Testudo3D",
    "author": "Will Alcorn",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View > Tools > T3D",
    "description": "create 3D tilemaps",
    "warning": "",
    "wiki_url": "https://github.com/alcornwill/testudo3d",
    "category": "3D View",
}

import sys
from os.path import splitext, basename, dirname, join
import logging
import bpy
import bgl
import blf
from math import ceil, sqrt, radians, degrees
from mathutils import Vector, Quaternion, Euler, Matrix
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    Header,
    UIList
)

from .tilemap3d import init_object_props, update_3dviews, get_first_group_name, round_vector, roundbase
from .turtle3d import Turtle3D
from .autotiler3d import AutoTiler3D

class Vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

ARROW = (Vector((-0.4, -0.4, 0)), Vector((0.4, -0.4, 0)), Vector((0, 0.6, 0)))
# ARROW = (Vector((-0.4, 0.1, 0)), Vector((0.4, 0.1, 0)), Vector((0, 0.45, 0)))
RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)
CYAN = (0.0, 1.0, 1.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
YELLOW = (1.0, 1.0, 0.0, 1.0)
PURPLE = (1.0, 0.0, 1.0, 1.0)
GREY = (0.5, 0.5, 0.5, 1.0)
FONT_ID = 0  # hmm

addon_keymaps = []

text_cursor = Vec2(0, 0)  # used for UI


def writelines(path, lines):
    with open(path, 'w') as f:
        f.writelines(lines)

def draw_line_3d(start, end):
    bgl.glVertex3f(*start)
    bgl.glVertex3f(*end)

def draw_wire(edges, color=WHITE):
    bgl.glBegin(bgl.GL_LINES)
    bgl.glColor4f(*color)
    for start, end in edges:
        draw_line_3d(start, end)
    bgl.glEnd()

def draw_poly(poly, color):
    bgl.glBegin(bgl.GL_POLYGON)
    bgl.glColor4f(*color)
    for i in range(len(poly) - 1):
        draw_line_3d(poly[i], poly[i + 1])
    bgl.glEnd()

def mat_transform(mat, poly):
    return [mat * v for v in poly]

def mat_transform_edges(mat, edges):
    return [(mat * start, mat * end) for start, end in edges]

def draw_text_2d(text, size=20, color=WHITE):
    bgl.glColor4f(*color)
    text_cursor.y -= size + 3  # behaves like command line
    blf.position(FONT_ID, text_cursor.x, text_cursor.y, 0)
    blf.size(FONT_ID, size, 72)
    blf.draw(FONT_ID, text)

def restore_gl_defaults():
    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def mouseover_region(area, event):
    x, y = event.mouse_x, event.mouse_y
    for region in area.regions:
        if region.type == 'WINDOW':
            if (x >= region.x and
                y >= region.y and
                x < region.width + region.x and
                y < region.height + region.y):
                return True
    return False

def make_linked_duplicate(src):
    obj = src.copy()
    if src.data:
        obj.data = src.data.copy()
    bpy.context.scene.objects.link(obj)
    return obj

def create_group_instance(group_name):
    group = bpy.data.groups[group_name]
    bpy.ops.object.empty_add(name=group_name)
    empty = bpy.context.object
    empty.dupli_type = 'GROUP'
    empty.dupli_group = group
    return empty

def select_all(objs=None):
    objs = objs or bpy.data.objects
    for obj in objs:
        obj.select = True

def deselect_all(objs=None):
    objs = objs or bpy.data.objects
    for obj in objs:
        obj.select = False

def get_children(obj, children=None):
    # recursive
    if not children:
        children = []
    children += obj.children
    for child in obj.children:
        get_children(child, children)
    return children

def construct_cube_edges(x_min, x_max, y_min, y_max, z_min, z_max):
    a = Vector((x_min, y_min, z_min))
    b = Vector((x_max, y_min, z_min))
    c = Vector((x_max, y_max, z_min))
    d = Vector((x_min, y_max, z_min))
    e = Vector((x_min, y_min, z_max))
    f = Vector((x_max, y_min, z_max))
    g = Vector((x_max, y_max, z_max))
    h = Vector((x_min, y_max, z_max))

    return [
        (a, b),
        (b, c),
        (c, d),
        (d, a),

        (e, f),
        (f, g),
        (g, h),
        (h, e),

        (a, e),
        (b, f),
        (c, g),
        (d, h)
    ]

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

class TilesetList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(item.tileset_name)
        row.prop(item, 'path', text="")

class TilesetPropertyGroup(PropertyGroup):
    # todo allow use text data-block
    path = StringProperty(
        name="Rules Path",
        description="Path to your rules.txt file (for auto-tiling)",
        subtype="FILE_PATH",
        default='//tileset1.txt'
    )
    def get_tileset_name(self):
        name, ext = splitext(basename(self.path))
        return name
    tileset_name = property(get_tileset_name)

class T3DProperties(PropertyGroup):
    tile3d_library_path = StringProperty(
        name="Tile3D Library Path",
        description="Path to your tile3d library .blend file",
        subtype="FILE_PATH"
    )
    circle_radius = IntProperty(
        name="Circle Radius",
        description='Radius of circle',
        default=5
    )
    tilesets = CollectionProperty(
        name='Tilesets',
        description='Tilesets (for auto-tiling)',
        type=TilesetPropertyGroup
    )
    idx = 0
    def getidx(self):
        return T3DProperties.idx
    def setidx(self, value):
        T3DProperties.idx = value
        t3d.tileset = self.tilesets[self.tileset_idx]
    tileset_idx = IntProperty(
        default=0,
        get=getidx,
        set=setidx,
    )
    roomgen_name = StringProperty(
        name='Name',
        description='Name of tileset to be generated',
        default='tileset'
    )

class TilesetActionsOperator(bpy.types.Operator):
    bl_idname = "view3d.t3d_tileset_actions"
    bl_label = "Tileset Actions"

    action = bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", ""),
            ('ADD', "Add", ""),
        )
    )

    def invoke(self, context, event):
        prop = context.scene.t3d_prop
        idx = prop.tileset_idx

        try:
            item = prop.tilesets[idx]
            print("happened")
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(prop.tilesets) - 1:
                item_next = prop.tilesets[idx+1].name
                prop.tileset_idx += 1
            elif self.action == 'UP' and idx >= 1:
                item_prev = prop.tilesets[idx-1].name
                prop.tileset_idx -= 1
            elif self.action == 'REMOVE':
                prop.tileset_idx -= 1
                prop.tilesets.remove(idx)
        if self.action == 'ADD':
            item = prop.tilesets.add()
            prop.tileset_idx += 1

        return {"FINISHED"}

class T3DToolsPanel(Panel):
    bl_idname = "view3d.t3d_tools_panel"
    bl_label = "Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        layout.operator(ManualModeOperator.bl_idname)
        layout.operator(AutoModeOperator.bl_idname)

        row = layout.row()
        row.template_list('TilesetList', '', prop, 'tilesets', prop, 'tileset_idx', rows=3)

        col = row.column(align=True)
        col.enabled = not T3DOperatorBase.running_modal or not t3d.manual_mode
        col.operator(TilesetActionsOperator.bl_idname, icon='ZOOMIN', text="").action = 'ADD'
        col.operator(TilesetActionsOperator.bl_idname, icon='ZOOMOUT', text="").action = 'REMOVE'
        col.separator()
        col.operator(TilesetActionsOperator.bl_idname, icon='TRIA_UP', text="").action = 'UP'
        col.operator(TilesetActionsOperator.bl_idname, icon='TRIA_DOWN', text="").action = 'DOWN'

class T3DDrawingPanel(Panel):
    bl_idname = "view3d.t3d_drawing_panel"
    bl_label = "Drawing"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        self.display_selected_tile3d(context)
        layout.operator(SetActiveTile3D.bl_idname)
        row = layout.row(align=True)
        row.operator(T3DDown.bl_idname)
        row.operator(T3DUp.bl_idname)
        layout.operator(CursorToSelected.bl_idname)
        layout.operator(Goto3DCursor.bl_idname)
        row = layout.row(align=True)
        row.operator(T3DCircle.bl_idname)
        row.prop(prop, 'circle_radius')

    def display_selected_tile3d(self, context):
        obj = context.object
        if obj:
            self.layout.label("selected: {}".format(obj.group))

class T3DUtilsPanel(Panel):
    bl_idname = "view3d.t3d_utils_panel"
    bl_label = "Utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.scale_x = 3.0
        sub.prop(prop, 'tile3d_library_path', text="")
        row.operator(LinkTile3DLibrary.bl_idname)
        layout.operator(T3DSetupTilesOperator.bl_idname)
        col = layout.column(align=True)
        col.operator(RoomGenOperator.bl_idname)
        col.prop(prop, 'roomgen_name', text='')
        layout.operator(MakeTilesRealOperator.bl_idname)
        layout.operator(AlignTiles.bl_idname)
        layout.operator(ConnectObjects.bl_idname)

class T3DOperatorBase:
    running_modal = False

    last_pos = None # todo store on Empty custom properties
    last_rot = None
    last_tile3d = None

    def __init__(self):
        self._handle_3d = None
        self._handle_2d = None
        self.active_scene = None
        self.select_cube = None
        self.input_map = [
            KeyInput('ESC', 'PRESS', self.handle_quit),
            KeyInput('RET', 'PRESS', self.handle_paint),
            KeyInput('RET', 'RELEASE', self.handle_paint_end),
            KeyInput('X', 'PRESS', self.handle_delete),
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
            KeyInput('V', 'PRESS', self.handle_paste, ctrl=True),
            KeyInput('B', 'PRESS', self.handle_select),
            KeyInput('Z', 'PRESS', self.undo, ctrl=True),
            KeyInput('Z', 'PRESS', self.redo, ctrl=True, shift=True)
        ]

    def __del__(self):
        self.on_quit()

    def on_quit(self):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
        T3DOperatorBase.running_modal = False
        deselect_all()
        bpy.context.scene.objects.active = self.root_obj

    @classmethod
    def poll(cls, context):
        return not T3DOperatorBase.running_modal

    def cancel(self, context):
        self.on_quit()

    def modal(self, context, event):
        context.area.tag_redraw()
        try:
            if mouseover_region(context.area, event):
                return self.handle_input(event)
            return {'PASS_THROUGH'}
        except QuitError:
            self.on_quit()
            return {'FINISHED'}
        except:
            exc_type, exc_msg, exc_tb = sys.exc_info()
            self.error("Unexpected error line {}: {}".format(exc_tb.tb_lineno, exc_msg))
            self.on_quit()
            return {'CANCELLED'}

    def invoke(self, context, event):
        if T3DOperatorBase.running_modal: return {'CANCELLED'}
        T3DOperatorBase.running_modal = True
        if context.area.type == 'VIEW_3D':
            # init
            self.init()
            self.init_handlers(context)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

    def error(self, msg):
        self.report({'ERROR'}, msg)

    def init_handlers(self, context):
        self.active_scene = context.scene
        args = (context,)  # the arguments we pass the the callback
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)

    def handle_input(self, event):
        for keyinput in self.input_map:
            if (keyinput.shift and not event.shift or
                keyinput.ctrl and not event.ctrl):
                continue
            if keyinput.type == event.type and keyinput.value == event.value:
                keyinput.func()
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def handle_quit(self):
        if self.state.grab:
            self.end_grab(cancel=True)
        elif self.state.select:
            # cancel
            self.state.select = False
            self.construct_select_cube()
        else:
            raise QuitError()

    def handle_paint(self):
        if self.state.grab:
            self.end_grab()
        elif self.state.select:
            self.state.paint = True
            self.end_select()
            self.state.paint = False
        elif not self.state.paint:
            self.state.paint = True
            self._cdraw()

    def handle_paint_end(self):
        self.state.paint = False
        bpy.ops.ed.undo_push()

    def handle_delete(self):
        if self.state.select:
            self.state.delete = True
            self.end_select()
            self.state.delete = False
        elif not self.state.grab and not self.state.delete:
            self.state.delete = True
            self._cdraw()

    def handle_delete_end(self):
        self.state.delete = False
        bpy.ops.ed.undo_push()

    def handle_grab(self):
        if not self.manual_mode:
            # todo
            self.report({'WARNING'}, 'Grab not implemented for Auto Mode')
            return
        if not self.state.grab:
            self.start_grab()
        else:
            self.end_grab()
            bpy.ops.ed.undo_push()

    def handle_copy(self):
        self.copy()
        self.report({'INFO'}, '({}) tiles copied to clipboard'.format(len(self.clipboard) if self.clipboard else "0"))

    def handle_paste(self):
        self.paste()
        bpy.ops.ed.undo_push()

    def handle_select(self):
        if self.state.grab:
            return
        elif not self.state.select:
            self.start_select()
        else:
            # cancel
            self.end_select()

    def construct_select_cube(self):
        logging.debug('construct select cube')
        if self.state.select:
            cube_min, cube_max = self.select_cube_bounds()
        else:
            cube_min, cube_max = self.cursor.pos, self.cursor.pos
        self.select_cube = construct_cube_edges(cube_min.x - 0.5, cube_max.x + 0.5,
                                                cube_min.y - 0.5, cube_max.y + 0.5,
                                                cube_min.z, cube_max.z + 1.0)

    def draw_callback_3d(self, context):
        if context.scene != self.active_scene: return
        mat_world = self.root_obj.matrix_world
        mat_scale = Matrix.Scale(self.tilesize_z, 4, Vector((0.0, 0.0, 1.0)))
        mat = mat_world * mat_scale

        bgl.glDisable(bgl.GL_DEPTH_TEST)

        color = YELLOW if self.state.select else WHITE
        t_cube = mat_transform_edges(mat, self.select_cube)
        draw_wire(t_cube, color)

        mat_rot = Matrix.Rotation(radians(self.cursor.rot), 4, 'Z')
        mat_trans = Matrix.Translation(self.cursor.pos)
        mat = mat_scale * mat_trans * mat_rot
        mat = mat_world * mat

        t_arrow = mat_transform(mat, ARROW)
        color = PURPLE if not self.state.grab else GREEN
        draw_poly(t_arrow, color)

        restore_gl_defaults()

    def draw_callback_2d(self, context):
        if context.scene != self.active_scene: return
        # draw text
        text_cursor.x = 20
        text_cursor.y = 140

        tile3d = self.cursor.tile3d
        text = tile3d if tile3d else 'No Active Tile'
        draw_text_2d(text, size=20, color=WHITE)

        # info
        vec3_str = "{}, {}, {}".format(int(self.cursor.pos.x), int(self.cursor.pos.y), int(self.cursor.pos.z))
        draw_text_2d("cursor pos: " + vec3_str, size=15, color=GREY)

        restore_gl_defaults()

class ManualModeOperator(Turtle3D, T3DOperatorBase, Operator):
    """Manually position tiles"""
    bl_idname = "view3d.t3d_manual"
    bl_label = "Manual Mode"

    def __init__(self):
        Turtle3D.__init__(self)
        T3DOperatorBase.__init__(self)

    def on_quit(self):
        Turtle3D.on_quit(self)
        T3DOperatorBase.on_quit(self)

    def error(self, msg):
        Turtle3D.error(self, msg)
        T3DOperatorBase.error(self, msg)

    def construct_select_cube(self):
        T3DOperatorBase.construct_select_cube(self)

class AutoModeOperator(AutoTiler3D, T3DOperatorBase, Operator):
    """Automatically generate tiles from terrain"""
    bl_idname = "view3d.t3d_auto"
    bl_label = "Auto Mode"

    @classmethod
    def poll(cls, context):
        prop = context.scene.t3d_prop
        try:
            tileset = prop.tilesets[prop.tileset_idx]
        except IndexError:
            return False
        return T3DOperatorBase.poll(context)

    def __init__(self):
        AutoTiler3D.__init__(self)
        T3DOperatorBase.__init__(self)

    def on_quit(self):
        AutoTiler3D.on_quit(self)
        T3DOperatorBase.on_quit(self)

    def error(self, msg):
        AutoTiler3D.error(self, msg)
        T3DOperatorBase.error(self, msg)

    def construct_select_cube(self):
        T3DOperatorBase.construct_select_cube(self)

class ConnectObjects(Operator):
    """Connect two objects with constraints utility"""
    bl_idname = "view3d.connect_objects"
    bl_label = "Connect Objects"

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT" and len(context.selected_objects) == 2

    def execute(self, context):
        selected = list(context.selected_objects)
        obj1 = context.scene.objects.active
        selected.remove(obj1)
        obj2 = selected[0]
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
        t3d = context.scene.t3d_prop
        with bpy.data.libraries.load(t3d.tile3d_library_path, link=True) as (data_src, data_dst):
            # link groups
            data_dst.groups = data_src.groups
            self.report({'INFO'}, 'linked {} groups'.format(len(data_src.groups)))
            # link scenes
            data_dst.scenes = data_src.scenes
        return {'FINISHED'}

class SetActiveTile3D(Operator):
    # we need this because modal operator only works for one window
    bl_idname = "view_3d.t3d_set_active_tile3d"
    bl_label = "Set Active Tile3D"

    tile3d = None

    @classmethod
    def poll(cls, context):
        if not T3DOperatorBase.running_modal: return False
        if not t3d.manual_mode: return False
        obj = context.object
        if obj is None: return False
        # assume is group instance
        group = obj.group
        if group is None:
            # else might be the linked object
            group = get_first_group_name(obj)
        SetActiveTile3D.tile3d = group
        return True

    def execute(self, context):
        t3d.cursor.tile3d = self.tile3d
        update_3dviews()
        return {'FINISHED'}

class CursorToSelected(Operator):
    bl_idname = "view_3d.t3d_cursor_to_selected"
    bl_label = "Cursor To Selected"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal and context.object

    def execute(self, context):
        t3d.cursor.pos = context.object.pos
        t3d.construct_select_cube()
        return {'FINISHED'}

class Goto3DCursor(Operator):
    bl_idname = "view_3d.t3d_goto_3dcursor"
    bl_label = "Goto 3D Cursor"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        pos = context.space_data.cursor_location
        round_vector(pos)
        t3d.goto(pos.x, pos.y) # note: 2D only...
        return {'FINISHED'}

class T3DDown(Operator):
    bl_idname = "view_3d.t3d_down"
    bl_label = "Down"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        t3d.down()
        return {'FINISHED'}

class T3DUp(Operator):
    bl_idname = "view_3d.t3d_up"
    bl_label = "Up"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        t3d.up()
        return {'FINISHED'}

class T3DCircle(Operator):
    bl_idname = "view_3d.t3d_circle"
    bl_label = "Circle"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        radius = context.scene.t3d_prop.circle_radius
        t3d.circle(radius=radius)
        return {'FINISHED'}

class AlignTiles(Operator):
    bl_idname = 'view_3d.t3d_align_tiles'
    bl_label = 'Align Tiles'
    bl_description = 'Align tiles to grid'

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        # for every child, align to grid
        for child in t3d.root_obj.children:
            vec = child.pos
            round_vector(vec)
            child.pos = vec

            rot = degrees(child.rot)
            rot = roundbase(rot, 90)
            child.rot = radians(rot)
        return {'FINISHED'}

class T3DSetupTilesOperator(Operator):
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
        deselect_all()
        select_all(self.objects)
        bpy.ops.group.objects_remove_all()
        deselect_all()

    def create_groups(self):
        for obj in self.objects:
            children = get_children(obj)
            group = bpy.data.groups.new(name=obj.name)
            group.name = obj.name  # insist
            group.objects.link(obj)
            for child in children:
                group.objects.link(child)
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

    def rename_objects(self):
        # if contains whitespace replace with underscore
        for obj in self.objects:
            if ' ' in obj.name:
                obj.name = obj.name.replace(' ', '_')

    def setup_tiles(self):
        self.objects = [obj for obj in bpy.context.scene.objects if not obj.parent and not obj.hide]
        self.rename_objects()
        self.layout_in_grid()
        self.remove_all_groups()
        self.create_groups()

class RoomGenOperator(Operator):
    bl_idname = 'view3d.t3d_room_gen'
    bl_label = 'Room Gen'
    bl_description = 'Generate tileset from "Wall", "Floor" and "Ceiling"'

    masks = (
        0b0000,
        0b0001,
        0b0011,
        0b0101,
        0b0111,
        0b1111
    )

    def execute(self, context):
        name = context.scene.t3d_prop.roomgen_name
        self.make_tileset(name, 'Wall', 'Ceiling', 'Floor') # make wall, floor, ceiling configurable?
        return {'FINISHED'}

    def make_tileset(self, name, wall, ceiling, floor):
        index = 0
        lines = []
        for j in range(4):
            c = j & 0b01
            f = j & 0b10
            for m in self.masks:
                objs = []
                # walls
                for i in range(4):
                    w = m & 1 << i
                    if not w:
                        obj = create_group_instance(wall)
                        obj.rotation_euler.z = radians(i * -90)
                        objs.append(obj)
                # ceiling
                if not c:
                    obj = create_group_instance(ceiling)
                    objs.append(obj)
                # floor
                if not f:
                    obj = create_group_instance(floor)
                    objs.append(obj)

                if not objs: continue
                bpy.ops.object.empty_add()
                empty = bpy.context.object
                empty.name = name + format(index, '03d')
                for obj in objs:
                    obj.parent = empty

                rule = (j << 4) | m
                rulestr = "{} {}\n".format(format(rule, '06b'), empty.name)
                lines.append(rulestr)

                index += 1

        blenddir = dirname(bpy.data.filepath)
        writelines(join(blenddir, name + '.txt'), lines)

class MakeTilesRealOperator(Operator):
    bl_idname = 'view3d.t3d_make_tiles_real'
    bl_label = 'Make Tiles Real'
    bl_description = 'Edit details on one tile without affecting the rest (destructive)'

    @classmethod
    def poll(cls, context):
        return not T3DOperatorBase.running_modal

    def execute(self, context):
        # todo operate on all tiles (custom property t3d_tile)
        # for now, operates on selected (maybe better anyway)
        selected = bpy.context.selected_objects
        for tile in selected:
            pos = tile.location.copy()
            rot = tile.rotation_euler.copy()
            group = tile.dupli_group
            for obj in group.objects:
                if tile.name.startswith(obj.name): continue # ignore root empty
                new = make_linked_duplicate(obj)
                new.parent = None
                new.location = new.location + pos
                new.rotation_euler.rotate(rot)
            bpy.data.objects.remove(tile, do_unlink=True)
        return {'FINISHED'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.t3d_prop = PointerProperty(type=T3DProperties)
    init_object_props()

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km.keymap_items.new(SetActiveTile3D.bl_idname, 'S', 'PRESS')
    # you could do this for all controls, then they'd be configurable
    # but then you'd have to create thousands of operators?
    # (there is a 'modal keymap'?. can't find documentation)
    # https://docs.blender.org/api/blender_python_api_2_70_5/bpy.types.KeyMapItem.html#bpy.types.KeyMapItem
    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.Scene.t3d_prop = None

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()

if __name__ == "__main__":
    register()
