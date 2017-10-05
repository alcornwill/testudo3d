
import logging
import bpy
import bgl
import blf
from bpy_extras.view3d_utils import region_2d_to_vector_3d, region_2d_to_origin_3d
from math import ceil, sqrt, radians, degrees
from mathutils import Vector, Quaternion, Euler, Matrix
from mathutils.geometry import intersect_line_plane
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    Header,
    UIList
)

from .tilemap3d import Tilemap3D, round_vector
from .autotiler3d import AutoTiler3D

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
RED = (1.0, 0.0, 0.0, 1.0)
GREEN = (0.0, 1.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)
CYAN = (0.0, 1.0, 1.0, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)
YELLOW = (1.0, 1.0, 0.0, 1.0)
PURPLE = (1.0, 0.0, 1.0, 1.0)
DARK_PURPLE = (0.5, 0.0, 0.5, 1.0)
GREY = (0.5, 0.5, 0.5, 1.0)
FONT_ID = 0  # hmm

text_cursor = Vec2(0, 0)  # used for UI

def clamp(a, b, c):
    return max(b, min(a, c))

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

def select_all(objs=None):
    objs = objs or bpy.data.objects
    for obj in objs:
        obj.select = True

def deselect_all(objs=None):
    objs = objs or bpy.data.objects
    for obj in objs:
        obj.select = False

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

class T3DOperatorBase:
    running_modal = False

    def __init__(self):
        self._handle_3d = None
        self._handle_2d = None
        self.active_scene = None
        self.select_cube = None
        self.mousepaint = False
        self.lastcoord = None
        self.tile_under_cursor = False
        self.input_map = [
            KeyInput('ESC', 'PRESS', self.handle_quit),
            KeyInput('RET', 'PRESS', self.handle_paint),
            KeyInput('RET', 'RELEASE', self.handle_paint_end),
            KeyInput('X', 'PRESS', self.handle_delete),
            KeyInput('X', 'RELEASE', self.handle_delete_end),
            # SHIFT + X delete all layers?
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
            KeyInput('RIGHT_BRACKET', 'PRESS', self.handle_inc_layer, shift=True),
            KeyInput('LEFT_BRACKET', 'PRESS', self.handle_dec_layer, shift=True),
            KeyInput('RIGHT_BRACKET', 'PRESS', self.handle_inc_brush_size),
            KeyInput('LEFT_BRACKET', 'PRESS', self.handle_dec_brush_size),
        ]

    # def __del__(self):
    #     self.on_quit()

    def on_quit(self):
        if not T3DOperatorBase.running_modal: return
        T3DOperatorBase.running_modal = False
        try:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
        except ValueError:
            pass # not set yet
        deselect_all()
        bpy.context.scene.objects.active = self.root

    @classmethod
    def poll(cls, context):
        return not T3DOperatorBase.running_modal

    def cancel(self, context):
        self.on_quit()

    def modal(self, context, event):
        if not self.running_modal:
            self.on_quit()
            return {'FINISHED'}
        context.area.tag_redraw()
        try:
            if mouseover_region(context.area, event):
                self.handle_raycast(event)
                result = self.handle_input(event)
                self.redraw_select_cube()
                self.on_update()
                self.tile_under_cursor = self.get_tile3d() # todo only update when necessary
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
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

        try:
            self.init()
        except Exception as e:
            self.report({'ERROR'}, str(e))
            self.on_quit()
            # todo if invoke after error, StructRNA of type ... has been removed
            return {'CANCELLED'}
        self.construct_select_cube()
        self.init_handlers(context)
        T3DOperatorBase.running_modal = True
        return {'RUNNING_MODAL'}

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
        # self.undo()
        pass

    def handle_redo(self):
        # self.redo()
        pass

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
        if coord == self.lastcoord: return
        self.lastcoord = coord
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
        self.prop.brush_size += 1

    def handle_dec_brush_size(self):
        self.prop.brush_size -= 1

    def handle_inc_layer(self):
        self.prop.user_layer += 1
        self.prop.user_layer = clamp(self.prop.user_layer, 0, 19)

    def handle_dec_layer(self):
        self.prop.user_layer -= 1
        self.prop.user_layer = clamp(self.prop.user_layer, 0, 19)

    def redraw_select_cube(self):
        if self.select_cube_redraw:
            self.construct_select_cube()
            self.select_cube_redraw = False

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
        color = (GREEN if self.state.grab else
                 PURPLE if self.tile_under_cursor else DARK_PURPLE)
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

        if self.manual_mode: # hacky
            tile3d = self.cursor.tile3d
            text = tile3d if tile3d else 'No Active Tile'
            color = WHITE if tile3d else RED
        else:
            text = self.tileset
            color = YELLOW
        draw_text_2d(text, size=20, color=color)

        # info
        vec3_str = "{}, {}, {}".format(int(self.cursor.pos.x), int(self.cursor.pos.y), int(self.cursor.pos.z))
        draw_text_2d("cursor pos: " + vec3_str, size=15, color=GREY)

        if self.state.select:
            w, d, h = self.select_cube_dim()
            text = "{}, {}, {}".format(w, d, h)
            draw_text_2d('select dim: ' + text, size=15, color=GREY)

        restore_gl_defaults()

class ManualModeOperator(Tilemap3D, T3DOperatorBase, Operator):
    """Manually position tiles"""
    bl_idname = "view3d.t3d_manual"
    bl_label = "Manual Mode"

    def __init__(self):
        Tilemap3D.__init__(self)
        T3DOperatorBase.__init__(self)

    @classmethod
    def poll(cls, context):
        prop = context.scene.t3d_prop
        try:
            tileset = prop.tilesets[prop.tileset_idx]
        except IndexError:
            return False
        return T3DOperatorBase.poll(context)

    def on_quit(self):
        Tilemap3D.on_quit(self)
        T3DOperatorBase.on_quit(self)

    def error(self, msg):
        Tilemap3D.error(self, msg)
        T3DOperatorBase.error(self, msg)

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
        if not tileset.rules: return False
        return T3DOperatorBase.poll(context)

    def __init__(self):
        AutoTiler3D.__init__(self)
        T3DOperatorBase.__init__(self)

    def init(self):
        AutoTiler3D.init(self)
        self.validate_rules()

    def validate_rules(self):
        for name, ruleset in self.rulesets.items():
            tileset = self.tilesets[name]
            notfound = []
            for rule in ruleset.rules.values():
                for tile3d in rule.tiles:
                    if tile3d not in tileset.tiles and tile3d not in notfound:
                        notfound.append(tile3d)
            if ruleset.default:
                for tile3d in ruleset.default.tiles:
                    if tile3d not in tileset.tiles and tile3d not in notfound:
                        notfound.append(tile3d)
            for tile3d in notfound:
                self.report({'WARNING'}, 'Tile "{}" not found in tileset "{}"'.format(tile3d, name))
            if notfound:
                raise Exception('invalid rules')

    def on_quit(self):
        AutoTiler3D.on_quit(self)
        T3DOperatorBase.on_quit(self)

    def error(self, msg):
        AutoTiler3D.error(self, msg)
        T3DOperatorBase.error(self, msg)