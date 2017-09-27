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
from bpy_extras.view3d_utils import region_2d_to_vector_3d, region_2d_to_origin_3d
from math import ceil, sqrt, radians, degrees
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.geometry import intersect_line_plane
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
from .autotiler3d import AutoTiler3D, CUSTOM_PROP_TILESET

class Vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

ARROW = (Vector((-0.4, -0.4, 0)), Vector((0.4, -0.4, 0)), Vector((0, 0.6, 0)))
CIRCLE = (
    Vector((-5.9371814131736755e-08, 0.5000001192092896, 0.0)),
    Vector((-0.09754522144794464, 0.4903927743434906, 0.0)),
    Vector((-0.19134178757667542, 0.46193990111351013, 0.0)),
    Vector((-0.27778518199920654, 0.4157349467277527, 0.0)),
    Vector((-0.35355344414711, 0.35355353355407715, 0.0)),
    Vector((-0.4157348871231079, 0.2777852416038513, 0.0)),
    Vector((-0.46193981170654297, 0.1913418471813202, 0.0)),
    Vector((-0.49039268493652344, 0.0975453183054924, 0.0)),
    Vector((-0.5000000596046448, 1.802413009954762e-07, 0.0)),
    Vector((-0.4903927147388458, -0.09754496067762375, 0.0)),
    Vector((-0.46193984150886536, -0.19134150445461273, 0.0)),
    Vector((-0.4157348871231079, -0.27778494358062744, 0.0)),
    Vector((-0.35355344414711, -0.35355323553085327, 0.0)),
    Vector((-0.27778515219688416, -0.4157346785068512, 0.0)),
    Vector((-0.19134169816970825, -0.46193966269493103, 0.0)),
    Vector((-0.09754510223865509, -0.4903925061225891, 0.0)),
    Vector((1.0354887081120978e-07, -0.4999998211860657, 0.0)),
    Vector((0.09754530340433121, -0.49039244651794434, 0.0)),
    Vector((0.19134187698364258, -0.4619395136833191, 0.0)),
    Vector((0.2777853012084961, -0.41573449969291687, 0.0)),
    Vector((0.35355356335639954, -0.35355302691459656, 0.0)),
    Vector((0.4157349467277527, -0.27778467535972595, 0.0)),
    Vector((0.46193987131118774, -0.19134120643138885, 0.0)),
    Vector((0.49039265513420105, -0.0975445881485939, 0.0)),
    Vector((0.4999999403953552, 6.252919320104411e-07, 0.0)),
    Vector((0.4903924763202667, 0.0975458174943924, 0.0)),
    Vector((0.4619394838809967, 0.19134236872196198, 0.0)),
    Vector((0.4157344102859497, 0.2777857780456543, 0.0)),
    Vector((0.3535528779029846, 0.35355398058891296, 0.0)),
    Vector((0.2777844965457916, 0.4157353341579437, 0.0)),
    Vector((0.19134098291397095, 0.461940199136734, 0.0)),
    Vector((0.0975443497300148, 0.49039292335510254, 0.0)),
)
UP = Vector((0, 0, 1))
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

def draw_edges(edges, color=WHITE):
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

def draw_wire(poly, color):
    bgl.glBegin(bgl.GL_LINES)
    bgl.glColor4f(*color)
    for i in range(len(poly) - 1):
        draw_line_3d(poly[i], poly[i + 1])
    draw_line_3d(poly[-1], poly[0]) # close
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
    bpy.ops.object.empty_add()
    empty = bpy.context.object
    empty.name = group_name
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
    brush_size = IntProperty(
        name="Brush Size",
        description='Radius of brush',
        min=1,
        max=8,
        default=1
    )
    outline = BoolProperty(
        name='Outline',
        description='Use outline brush',
        default=False
    )
    tilesets = CollectionProperty(
        name='Tilesets',
        description='Tilesets (for auto-tiling)',
        type=TilesetPropertyGroup
    )
    tileset_idx_ = 0
    def getidx(self):
        return T3DProperties.tileset_idx_
    def setidx(self, value):
        T3DProperties.tileset_idx_ = value
        if T3DOperatorBase.running_modal:
            t3d.tileset = self.tilesets[self.tileset_idx]
    tileset_idx = IntProperty(
        default=0,
        get=getidx,
        set=setidx,
    )
    roomgen_name = StringProperty(
        name='Name',
        description='Name of tileset to be generated',
        default='Tileset'
    )
    user_layer_ = 0
    def get_user_layer(self):
        return T3DProperties.user_layer_
    def set_user_layer(self, value):
        T3DProperties.user_layer_ = value
        bpy.context.scene.layers[value] = True
        if T3DOperatorBase.running_modal:
            t3d.layer = value
    user_layer = IntProperty(
        name='Layer',
        min=0,
        max=9,
        description='Layer to work in',
        default=0,
        get=get_user_layer,
        set=set_user_layer
    )
    rename_from = StringProperty(
        name='From',
        description='Rename From'
    )
    rename_to = StringProperty(
        name='To',
        description='Rename To'
    )
    def get_down(self):
        if T3DOperatorBase.running_modal:
            return t3d.state.paint
        return False
    def set_down(self, value):
        if T3DOperatorBase.running_modal:
            t3d.state.paint = value
    down = BoolProperty(
        name='Down',
        default=False,
        get=get_down,
        set=set_down
    )

class TilesetActionsOperator(bpy.types.Operator):
    bl_idname = "view3d.t3d_tileset_actions"
    bl_label = "Tileset Actions"

    action = bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REMOVE', "Remove", "Remove Rules"),
            ('ADD', "Add", "Add Rules"),
        )
    )

    def invoke(self, context, event):
        prop = context.scene.t3d_prop
        idx = prop.tileset_idx

        try:
            item = prop.tilesets[idx]
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
            prop.tileset_idx = len(prop.tilesets) - 1

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
        layout.prop(prop, 'user_layer')

        row = layout.row()
        row.template_list('TilesetList', '', prop, 'tilesets', prop, 'tileset_idx', rows=3)

        col = row.column(align=True)
        col.enabled = not T3DOperatorBase.running_modal or t3d.manual_mode
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
        layout.operator(CursorToSelected.bl_idname)
        layout.operator(Goto3DCursor.bl_idname)
        layout.prop(prop, 'down')
        layout.prop(prop, 'outline')
        layout.prop(prop, 'brush_size')

    def display_selected_tile3d(self, context):
        obj = context.object
        text = obj.group if obj else 'None'
        self.layout.label("selected: {}".format(text))

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
        col = layout.column(align=True)
        col.operator(RenameTilesetOperator.bl_idname)
        row = col.row(align=True)
        row.prop(prop, 'rename_from', text='')
        row.prop(prop, 'rename_to', text='')
        layout.operator(MakeTilesRealOperator.bl_idname)
        layout.operator(AlignTiles.bl_idname)
        layout.operator(ConnectRoots.bl_idname)
        layout.operator(XmlExportOperator.bl_idname)

class T3DOperatorBase:
    running_modal = False

    def __init__(self):
        self._handle_3d = None
        self._handle_2d = None
        self.active_scene = None
        self.select_cube = None
        self.mousepaint = False
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
            KeyInput('Z', 'PRESS', self.handle_undo, ctrl=True),
            KeyInput('Z', 'PRESS', self.handle_redo, ctrl=True, shift=True),
            KeyInput('LEFTMOUSE', 'PRESS', self.handle_mousepaint),
            KeyInput('LEFTMOUSE', 'RELEASE', self.handle_mousepaint_end),
            KeyInput('TAB', 'PRESS', self.handle_toggle_mousepaint),
            KeyInput('RIGHT_BRACKET', 'PRESS', self.handle_inc_brush_size),
            KeyInput('LEFT_BRACKET', 'PRESS', self.handle_dec_brush_size),
        ]

    def __del__(self):
        self.on_quit()

    def on_quit(self):
        if not T3DOperatorBase.running_modal: return
        T3DOperatorBase.running_modal = False
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
        deselect_all()
        bpy.context.scene.objects.active = self.root

    @classmethod
    def poll(cls, context):
        return not T3DOperatorBase.running_modal

    def cancel(self, context):
        self.on_quit()

    def modal(self, context, event):
        context.area.tag_redraw()
        try:
            if mouseover_region(context.area, event):
                self.handle_raycast(event)
                result = self.handle_input(event)
                self.redraw_select_cube()
                self.on_update()
                return result
            return {'PASS_THROUGH'}
        except QuitError:
            self.on_quit()
            return {'FINISHED'}
        except Exception as e:
            self.on_quit()
            raise e

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
                result = keyinput.func()
                return result or {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}

    def handle_quit(self):
        if self.state.grab:
            self.end_grab(cancel=True)
        elif self.state.select:
            # cancel
            self.state.select = False
            self.select_cube_redraw = True
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
            self.brush_draw()

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
            self.brush_draw()

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

    def handle_undo(self):
        self.undo()

    def handle_redo(self):
        self.redo()

    def handle_select(self):
        if self.state.grab:
            return
        elif not self.state.select:
            self.start_select()
        else:
            # cancel
            self.end_select()

    def handle_raycast(self, event):
        if not self.mousepaint: return

        coord = event.mouse_region_x, event.mouse_region_y
        view_vector = region_2d_to_vector_3d(bpy.context.region, bpy.context.region_data, coord)
        ray_origin = region_2d_to_origin_3d(bpy.context.region, bpy.context.region_data, coord)

        pos, rot, scl = self.root.matrix_world.decompose()
        z = self.cursor.pos.z # z persists
        offset = Vector((0, 0, z))
        offset = rot * offset
        pos = pos + offset
        nml = rot * UP
        plane_pos = intersect_line_plane(ray_origin, ray_origin + view_vector, pos, nml)
        if not plane_pos: return # workaround for quad view?
        mat = self.root.matrix_world.inverted()
        plane_pos = mat * plane_pos
        round_vector(plane_pos)
        if plane_pos != self.lastpos:
            d = plane_pos - self.lastpos
            self.on_move(d)

    def handle_toggle_mousepaint(self):
        if self.mousepaint:
            self.handle_mousepaint_end()
        self.mousepaint = not self.mousepaint

    def handle_mousepaint(self):
        if not self.mousepaint: return {'PASS_THROUGH'}
        self.handle_paint()

    def handle_mousepaint_end(self):
        if not self.mousepaint: return {'PASS_THROUGH'}
        self.handle_paint_end()

    def handle_inc_brush_size(self):
        prop = bpy.context.scene.t3d_prop
        prop.brush_size += 1

    def handle_dec_brush_size(self):
        prop = bpy.context.scene.t3d_prop
        prop.brush_size -= 1

    def construct_select_cube(self):
        if self.state.select:
            cube_min, cube_max = self.select_cube_bounds()
        else:
            cube_min, cube_max = self.cursor.pos, self.cursor.pos
        self.select_cube = construct_cube_edges(cube_min.x - 0.5, cube_max.x + 0.5,
                                                cube_min.y - 0.5, cube_max.y + 0.5,
                                                cube_min.z, cube_max.z + 1.0)

    def draw_callback_3d(self, context):
        if context.scene != self.active_scene: return
        mat_world = self.root.matrix_world
        mat_scale = Matrix.Scale(self.tilesize_z, 4, Vector((0.0, 0.0, 1.0)))
        mat = mat_world * mat_scale

        bgl.glDisable(bgl.GL_DEPTH_TEST)

        color = (YELLOW if self.state.select else
                 CYAN if self.mousepaint else WHITE)
        t_cube = mat_transform_edges(mat, self.select_cube)
        draw_edges(t_cube, color)

        mat_rot = Matrix.Rotation(radians(self.cursor.rot), 4, 'Z')
        mat_trans = Matrix.Translation(self.cursor.pos)
        mat = mat_scale * mat_trans * mat_rot
        mat = mat_world * mat

        t_arrow = mat_transform(mat, ARROW)
        color = PURPLE if not self.state.grab else GREEN
        draw_poly(t_arrow, color)

        brush_size = context.scene.t3d_prop.brush_size
        if not self.state.grab and not self.state.select and brush_size > 1:
            brush_size = brush_size * 2 - 1
            mat_trans = Matrix.Translation(self.cursor.pos)
            mat_sx = Matrix.Scale(brush_size, 4, Vector((1.0, 0.0, 0.0)))
            mat_sy = Matrix.Scale(brush_size, 4, Vector((0.0, 1.0, 0.0)))
            mat = mat_trans *  mat_sx * mat_sy
            mat = mat_world * mat
            t_circle = mat_transform(mat, CIRCLE)
            draw_wire(t_circle, RED)

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

    def init(self):
        AutoTiler3D.init(self)
        self.validate_tilesets()
        self.validate_rules()

    def validate_tilesets(self):
        notfound = []
        for obj in bpy.data.objects:
            if CUSTOM_PROP_TILESET in obj:
                tileset = obj[CUSTOM_PROP_TILESET]
                if tileset not in self.rulesets and tileset not in notfound:
                    notfound.append(tileset)
        for tileset in notfound:
            self.report({'WARNING'}, 'Tileset "{}" present in scene but rules not found! (did you rename rules.txt file? use RenameTileset)'.format(tileset))

    def validate_rules(self):
        tiles = [group.name for group in bpy.data.groups]
        for name, value in self.rulesets.items():
            notfound = []
            for rule in value.rules.values():
                if rule.tile3d not in tiles and rule.tile3d not in notfound:
                    notfound.append(rule.tile3d)
            for tile3d in notfound:
                self.report({'WARNING'}, 'Tile "{}" not found in blend (did you link your tiles?)'.format(tile3d))

    def on_quit(self):
        AutoTiler3D.on_quit(self)
        T3DOperatorBase.on_quit(self)

    def error(self, msg):
        AutoTiler3D.error(self, msg)
        T3DOperatorBase.error(self, msg)

    def construct_select_cube(self):
        T3DOperatorBase.construct_select_cube(self)

class ConnectRoots(Operator):
    bl_idname = "view3d.connect_roots"
    bl_label = "Connect Roots"
    bl_description = "Connect two roots with constraints utility"

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT" and len(context.selected_objects) == 2

    def execute(self, context):
        selected = list(context.selected_objects)
        obj1 = context.scene.objects.active
        selected.remove(obj1)
        obj2 = selected[0]
        childof = obj2.constraints.new('CHILD_OF')
        childof.target = obj1
        childof.inverse_matrix = obj1.matrix_world.inverted()
        obj2.update_tag({'OBJECT'})
        context.scene.update()
        self.report({'INFO'}, 'roots connected')
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
    bl_label = "Line"
    bl_description = 'Draw a line to the 3D cursor'

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        # note: doesn't make sense when root rotated in x or y
        mat_world = t3d.root.matrix_world
        # todo is it mat * vec?
        pos = (context.space_data.cursor_location - t3d.root.location) * mat_world
        round_vector(pos)
        t3d.line(pos.x, pos.y)
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
        for child in t3d.root.children:
            vec = child.pos
            round_vector(vec)
            child.pos = vec

            rot = degrees(child.rot)
            rot = roundbase(rot, 90)
            child.rot = radians(rot)
        return {'FINISHED'}

class T3DSetupTilesOperator(Operator):
    bl_idname = 'view3d.t3d_setup_tiles'
    bl_label = 'Setup 3D Tiles'
    bl_description = 'Setup objects in scene as tiles (WARNING will delete all groups)'

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
    bl_description = 'Generate tileset from "Wall", "Floor" and "Ceiling" groups'

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
        self.make_tileset(name, 'Wall', 'Ceiling', 'Floor')
        return {'FINISHED'}

    def make_tileset(self, name, wall, ceiling, floor):
        if (wall not in bpy.data.groups or
            ceiling not in bpy.data.groups or
            floor not in bpy.data.groups):
            self.report({'WARNING'}, 'group "Wall", "Floor" or "Ceiling" not found, no tiles generated')
            return
        fp = bpy.data.filepath
        if not fp:
            self.report({'ERROR'}, 'Blend not saved, cannot save rules file')
            return

        scene = bpy.data.scenes.new(name=name)
        bpy.context.screen.scene = scene

        name = name.lower()

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
                empty.name = name + format(index, '02d')
                for obj in objs:
                    obj.parent = empty

                rule = (j << 4) | m
                rulestr = "{} {}\n".format(format(rule, '06b'), empty.name)
                lines.append(rulestr)

                index += 1

        blenddir = dirname(fp)
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

class RenameTilesetOperator(Operator):
    bl_idname = 'view3d.t3d_rename_tileset'
    bl_label = 'Rename Tileset'
    bl_description = 'If you renamed a rules file, fix your scene with this'

    @classmethod
    def poll(cls, context):
        return not T3DOperatorBase.running_modal

    def execute(self, context):
        prop = bpy.context.scene.t3d_prop
        from_ = prop.rename_from
        to = prop.rename_to
        changed = []
        for obj in bpy.data.objects:
            if CUSTOM_PROP_TILESET in obj:
                tileset = obj[CUSTOM_PROP_TILESET]
                if tileset == from_:
                    obj[CUSTOM_PROP_TILESET] = to
                    changed.append(obj)
        self.report({'INFO'}, '{} objects changed'.format(len(changed)))
        return {'FINISHED'}

class XmlExportOperator(Operator):
    # test
    bl_idname = 'view3d.t3d_xml_export'
    bl_label = 'Xml Export'
    bl_description = 'Export scene to custom T3D Xml format'

    def execute(self, context):
        import xml.etree.cElementTree as et
        fp = bpy.data.filepath
        if not fp:
            self.report({'ERROR'}, 'Blend not saved, cannot save xml file')
            return {'FINISHED'}
        blenddir = dirname(fp)
        path = join(blenddir, 'tiles.xml')

        # todo
        root = et.Element('Scene')

        tilesets = et.SubElement(root, 'Tilesets')
        tileset1 = et.SubElement(tilesets, 'Tileset1', name='tileset1')
        tile1 = et.SubElement(tileset1, 'Tile', name='tile1')
        tile2 = et.SubElement(tileset1, 'Tile', name='tile2')
        tile3 = et.SubElement(tileset1, 'Tile', name='tile3')
        tileset2 = et.SubElement(tilesets, 'Tileset2', name='tileset2')

        root1 = et.SubElement(root, 'Root', name='Root.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")
        tile1 = et.SubElement(root1, 'Tile', name='tile1.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile1', tileset='tileset1', layer="0")
        tile2 = et.SubElement(root1, 'Tile', name='tile1.002', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile1', tileset='tileset1', layer="1")
        tile3 = et.SubElement(root1, 'Tile', name='tile2.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile2', tileset='tileset1', layer="0")
        root2 = et.SubElement(root1, 'Root', name='Root.002', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")
        root3 = et.SubElement(root, 'Root', name='Root.003', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")

        tree = et.ElementTree(root)
        tree.write(path)

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
