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
    "location": "space bar search (for now)",
    "description": "build structures quickly out of reusable modules",
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
from mathutils import Vector

class vec2:
    def __init__(self, x, y):
        self.x = x
        self.y = y

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

class ModularBuildingTool:
    def __init__(self):
        self.paint=False

room_info = {}
ROOM_MODES = ("Active Module", "Weighted Random", "Dither")

# todo hmm we need a tool panel, with 'metadata path' text input and browse button
#   and maybe select active root_obj
metadata_path = "C:/Program Files/Blender Foundation/Blender/2.78/scripts/addons/modular_building_tool_metadata.json"
# todo reload option
with open(metadata_path) as metadata_file:
    metadata = json.load(metadata_file)
        
# used for UI
text_cursor = vec2(0,0)

root_obj = None

# use fake user meshes as modules (useful for linking from a library of modules)
# sorts modules when script is run (may want 'refresh modules' button)
module_groups = {} # each group contains a list of modules
active_group = 0
modules = {}

# the state
paint = False
clear = False
delete = False
grab = False
grabbed = []
# used to restore the properties of modules when a grab operation is canceled
original_pos = Vector()
original_rots = []
clipboard = []
clipboard_rots = []

cursor_pos = Vector((0,0,0))
#cursor_tilt = 0  # may be useful for slopes (like rollarcoaster tycoon)
cursor_rot = 0

ARROW = (Vector((-0.4, -0.4, 0)), Vector((0.4, -0.4, 0)), Vector((0, 0.6, 0)))
RED = (1.0, 0.0, 0.0, 0.7)
GREEN = (0.0, 1.0, 0.0, 0.7)
BLUE = (0.0, 0.0, 1.0, 0.7)
WHITE = (1.0, 1.0, 1.0, 1)
YELLOW = (1.0, 1.0, 0.0, 1)

def update_3dview():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

def get_modules_at_cursor():
    return get_objects_at(cursor_pos)

def get_objects_at(pos):
    # get objects near pos, relative to root_obj
    rel_pos = root_obj.matrix_world.inverted() * pos
    childs = root_obj.children
    size = len(childs)
    kd = mathutils.kdtree.KDTree(size)

    for i, child in enumerate(childs):
        kd.insert(child.location, i)
    kd.balance()

    return [childs[index] for pos, index, dist in kd.find_range(rel_pos, 0.5)]


def get_key(dict, key, default=None):
    if key in dict:
        return dict[key]
    return default

def find_with_name(lst, name):
    for item in lst:
        if item.name == name:
            return item

def set_group_name(meshdata, value):
    meshdata["MBT"] = value

def get_group_name(meshdata):
    return meshdata["MBT"]

def init_modules():
    global room_info
    #initialize modules list
    # get all fake user meshes (useful for linking a module library)
    #meshes = [m for m in bpy.data.meshes if m.use_fake_user]
    module_groups['wall']=ModuleGroup('wall', thin=True)
    module_groups['floor']=ModuleGroup('floor')
    #module_groups.append(ModuleGroup('ceiling'))
    room_info = {
        "wall": [],
        "floor": []
    }
    for m_name, value in metadata.items():
        try:
            mesh = bpy.data.meshes[m_name]
        except KeyError:
            print('WARNING: mesh "{}" not found'.format(m_name))
            continue
        if mesh is None:
            print('WARNING: mesh "{}" not found'.format(m_name))
            continue
        g_name = value["type"]
        group = module_groups[g_name]
        module = Module(mesh, m_name, g_name)
        modules[m_name] = module
        group.modules.append(module)
        set_group_name(mesh, g_name)
        weight = value["weight"]
        room_info[g_name].append((mesh, weight))  # used for room paint
    # add 'room' paint
    room = ModuleGroup("room")
    room.modules = [None] * 3 # hack
    module_groups['room'] = room

def init_root_obj():
    global root_obj
    root_obj = bpy.context.scene.objects.active # should be exactly one selected object... todo check
    if root_obj is None:
        bpy.ops.object.empty_add()
        root_obj = bpy.context.scene.objects.active

def draw_line_3d(start, end):
    bgl.glVertex3f(*start)
    bgl.glVertex3f(*end)

def draw_poly(poly, color, width=1):
    bgl.glLineWidth(width)
    bgl.glColor4f(*color)
    for i in range(len(poly)-1):
        draw_line_3d(poly[i], poly[i+1])
    #close
    draw_line_3d(poly[len(poly)-1], poly[0])

def mat_transform(mat, poly):
    t_poly = []
    for v in poly:
        t_poly.append(mat * v)
    return t_poly
    
def draw_callback_3d(self, context):
    bgl.glEnable(bgl.GL_BLEND)    
    
    mat_world = root_obj.matrix_world
    mat_rot = mathutils.Matrix.Rotation(math.radians(cursor_rot), 4, 'Z')
    mat_trans = mathutils.Matrix.Translation(cursor_pos)   
   
    mat = mat_trans * mat_rot   
    mat = mat_world * mat
    
    color = BLUE
    if grab:
        color = GREEN
    t_arrow = mat_transform(mat, ARROW)

    bgl.glBegin(bgl.GL_LINES)
    draw_poly(t_arrow, color)
    bgl.glEnd()

    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def draw_text_2d(text, size=20, color=WHITE):
    font_id = 0  # XXX, need to find out how best to get this.
    bgl.glColor4f(*color)
    blf.position(font_id, text_cursor.x, text_cursor.y, 0)
    blf.size(font_id, size, 72)
    blf.draw(font_id, text)
    text_cursor.y -= size + 5 # behaves like command line
    
def draw_callback_2d(self, context):
    global text_cursor
    bgl.glEnable(bgl.GL_BLEND)

    # draw text
    text_cursor.x = 20
    text_cursor.y = 200

    act_g = get_active_group()
    if act_g is not None:
        if act_g.name == "room":
            draw_text_2d("room", size=15, color=YELLOW)
            draw_text_2d(ROOM_MODES[act_g.active], size=20, color=YELLOW)
        else:
            act = act_g.active_module()
            draw_text_2d(act.g_name, size=15) # group name
            draw_text_2d(act.name) # module name
    else:
        draw_text_2d("No modules found", size=15, color=RED)

    # info
    color = WHITE
    draw_text_2d("cursor pos: {}, {}, {}".format(int(cursor_pos.x), int(cursor_pos.y), int(cursor_pos.z)), size=15, color=color)
    #draw_text_2d("modules at cursor: {}".format(len(cell.modules)), size=12, color=green)
    #draw_text_2d("cell occupied: {}".format(cell.occupied), size=12, color=green)
        
    bgl.glEnd()
    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)
    bgl.glEnable(bgl.GL_DEPTH_TEST)
    bgl.glColor4f(0.0, 0.0, 0.0, 1.0)

def weighted_choice(choices):
    total = sum(w for c, w in choices)
    r = random.uniform(0, total)
    upto = 0
    for c, w in choices:
        if upto + w >= r:
            return c
        upto += w
    assert False, "Shouldn't get here"
    
def clear_at_cursor():
    delete_modules(get_modules_at_cursor())
    
def delete_module(m):
    bpy.data.objects.remove(m, True)
    update_3dview()

def delete_modules(modules_):
    # use this when you can, saves calling update_3dview
    for m in modules_:
        bpy.data.objects.remove(m, True)
    update_3dview()

adjacency_vectors = (
    Vector((1,0,0)),
    Vector((-1,0,0)),
    Vector((0,1,0)),
    Vector((0,-1,0)),
    Vector((0,0,1)),
    Vector((0,0,-1))
)
    
def adjacent_occupied():
    return [len(get_objects_at(cursor_pos + vec)) > 0 for vec in adjacency_vectors]
    
def room_get_module(type_):
    act_g = get_active_group()  # should always be 'room'...
    # todo ability to define custom rooms with metadata
    if module_groups["room"].active == 0:
        # active module
        return module_groups[type_].active_module().data
    elif act_g.active == 1:
        # weighted random
        return weighted_choice(room_info[type_])
    elif act_g.active == 2:
        # dither
        idx = int(cursor_pos.x + cursor_pos.y + cursor_pos.z)
        idx %= len(room_info[type_])
        return room_info[type_][idx][0]
        
def room_paint():
    global cursor_rot    
    clear_at_cursor()
    orig_curs_rot = cursor_rot
    occupied = adjacent_occupied()
    #paint walls
    if "wall" in room_info:
        for i in range(4):
            if not occupied[i]:
                vec = adjacency_vectors[i]
                rot = normalized_XY_to_Zrot(vec.x, vec.y)
                cursor_rot = rot
                wall = room_get_module("wall")            
                create_obj(wall)
            else:
                # todo delete adjacent cell adjacent walls
                pass
    #paint floor
    if "floor" in room_info:
        if not occupied[5]:
            floor = room_get_module("floor")
            create_obj(floor)
    #paint ceiling
    if "ceiling" in room_info:
        if not occupied[4]:
            floor = room_get_module("ceiling")
            create_obj(floor)
    #restore cursor rot
    cursor_rot = orig_curs_rot
    
def repaint_adjacent():
    global cursor_pos
    # todo 'with StoreCursorPos'?
    orig_curs_pos = cursor_pos
    occupied = adjacent_occupied()
    for i, vec in enumerate(adjacency_vectors):
        if occupied[i]:
            cursor_pos = orig_curs_pos + vec
            room_paint()
    cursor_pos = orig_curs_pos
    
def cursor_paint():
    #todo abstract 'paint_func' so object oriented
    # Painter?
    if paint:
        act_g = get_active_group()
        if act_g.name == "room":
            room_paint()
            # repaint adjacent cells (could be optimized to just delete walls, which is all it does for now, but that might change in the future anyway)
            repaint_adjacent()
        else:
            # normal paint
            act = act_g.active_module()
            if act is not None:
                create_obj(act.data)
    elif delete:
        # delete
        act_g = get_active_group()
        if act_g.name == "room":
            clear_at_cursor()
            repaint_adjacent()
        else:
            # delete only modules of same type
            match = [x for x in get_modules_at_cursor() if get_group_name(x.data) == act_g.name]
            if act_g.thin:
                # only delete if facing same as cursor rot
                for m in match:
                    if int(m.rotation_euler.z) == cursor_rot:
                        delete_module(m)
                        break
            else:
                if len(match) > 0:
                    delete_module(match[0])  # should only be one... todo use custom error
    elif clear:
        clear_at_cursor()
        
def rotate(rot):
    global cursor_rot
    cursor_rot = cursor_rot + rot
    for x in grabbed:
        x.rotation_euler[2] = x.rotation_euler[2] + math.radians(rot)
    cursor_paint()

def translate(x, y, z):
    # translate the cursor and paint (?)
    global cursor_pos
    translation = Vector((x, y, z))
    mat_rot = mathutils.Matrix.Rotation(math.radians(cursor_rot), 4, 'Z')
    
    translation = mat_rot * translation
    cursor_pos = cursor_pos + translation
    # round cursor_pos to nearest integer
    cursor_pos.x = round(cursor_pos.x)
    cursor_pos.y = round(cursor_pos.y)
    cursor_pos.z = round(cursor_pos.z)
    if grab:
        for x in grabbed:            
            x.location = x.location + translation
    cursor_paint()

def paint_at(pos, modules_):
    # call this when creating or moving a module. it replaces overlapping modules
    to_delete = []
    for m in modules_:
        g_to = get_group_name(m.data)
        mod_list = get_objects_at(pos)
        for x in mod_list:
            g_from = get_group_name(x.data)
            if g_to == g_from and x != m:
                # module is already occupied with module of same group, may have to delete
                g = module_groups[g_to]
                if g.thin:
                    # only delete if x has same rotation as m (rounded to nearest ordinal direction...)
                    if int(round(math.degrees(x.rotation_euler[2]))) != cursor_rot: # todo needs rotation parameter?
                        continue # don't delete existing
                # delete existing module
                to_delete.append(x)
                break # there shouldn't be any more of this module in the cell... todo else raise error
    delete_modules(to_delete)

def end_grab(cancel=False):
    global grab
    global grabbed
    grab = False
    pos = cursor_pos
    if cancel:
        pos = original_pos
        for x in range(len(grabbed)):
            # reset transform of grabbed
            o = grabbed[x]
            rot = original_rots[x]
            o.location = original_pos
            o.rotation_euler.z = rot
    paint_at(pos, grabbed)
    grabbed.clear()
    original_rots.clear()

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

def create_obj(data):
    #creates object with data at cursor
    #create a cube then change it to a whatever
    obj = create_cube(position=cursor_pos, rotz=cursor_rot)
    cube = obj.data
    obj.data = data
    obj.name = data.name
    bpy.data.meshes.remove(cube, True)  # clean up the cube mesh data
    obj.parent = root_obj
    paint_at(cursor_pos, (obj,))
    return obj
     
def get_active_group():
    if len(module_groups) > 0:
        return list(module_groups.values())[active_group]
     
def get_active_module():
    act_g = get_active_group()
    if act_g is not None:
        return act_g.modules[act_g.active]
     
def normalized_XY_to_Zrot(x, y):
    rot = 0
    # todo actually normalize xy and make it less shit
    if x > 0:
        rot = 270
    elif y > 0:
        rot = 0
    elif x < 0:
        rot = 90
    elif y < 0:
        rot = 180 
    return rot
     
def smart_move(x, y):
    # move in x or y, but only if already facing that direction
    rot = normalized_XY_to_Zrot(x, y)
    if cursor_rot == rot:
        translate(0, 1, 0)
    else:       
        rotate(rot - cursor_rot)

def start_grab():
    global grab, grabbed, original_pos
    grab = True
    grabbed = get_modules_at_cursor()
    original_pos = cursor_pos
    for x in grabbed:
        original_rots.append(x.rotation_euler.z)

class ModalDrawOperator(bpy.types.Operator):
    bl_idname = "view3d.modal_operator"
    bl_label = "Modular Building Tool"

    def __init__(self):
        super().__init__()
        self._handle_3d = None
        self._handle_2d = None

    def modal(self, context, event):
        global cursor_rot, paint, delete, clear, grab, grabbed, original_pos, original_rot, clipboard, active_group
        context.area.tag_redraw()
        try:
            # todo assume RUNNING_MODAL?
            # also can use map like ('RET', 'PRESS', func)?
            #   (modifiers...)
            if 'ESC' == event.type and 'PRESS' == event.value:
                if grab:
                    end_grab(cancel=True)
                    return {'RUNNING_MODAL'}
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
                return {'CANCELLED'}
            elif 'RET' == event.type and 'PRESS' == event.value:
                if grab:
                    #behaves same as space
                    end_grab()
                elif not paint:
                    paint = True                    
                    cursor_paint()
                return {'RUNNING_MODAL'}
            elif 'RET' == event.type and 'RELEASE' == event.value:
                paint = False
                return {'RUNNING_MODAL'}
            elif event.shift and 'X' == event.type and 'PRESS' == event.value:
                if grab:
                    return # would be weird
                if not clear:
                    clear = True
                    cursor_paint()
                return {'RUNNING_MODAL'}
            elif 'X' == event.type and 'PRESS' == event.value:
                if grab:
                    return # would be weird
                if not delete:
                    delete = True
                    cursor_paint()
                return {'RUNNING_MODAL'}
            elif 'X' == event.type and 'RELEASE' == event.value:
                delete = False
                clear = False
                return {'RUNNING_MODAL'}
            elif event.ctrl and 'TAB' == event.type and 'PRESS' == event.value:
                if len(module_groups) <= 1:
                    self.report({'INFO'}, 'no more module groups to cycle to')
                else:
                    active_group += 1
                    active_group %= len(module_groups)
                return {'RUNNING_MODAL'}
            elif 'TAB' == event.type and 'PRESS' == event.value:
                act_g = get_active_group()
                if act_g is not None:
                    if len(act_g.modules) <= 1:
                        self.report({'INFO'}, 'no more modules to cycle to')
                    else:
                        act_g.active += 1
                        act_g.active %= len(act_g.modules)                  
                else:
                    self.report({'INFO'}, 'no more modules to cycle to')
                return {'RUNNING_MODAL'}
            elif 'G' == event.type and 'PRESS' == event.value:
                if not grab:
                    start_grab()
                else:
                    end_grab()
                return {'RUNNING_MODAL'}
            elif event.ctrl and 'LEFT_ARROW' == event.type and 'PRESS' == event.value:
                translate(-1, 0, 0)
                return {'RUNNING_MODAL'}        
            elif event.ctrl and 'RIGHT_ARROW' == event.type and 'PRESS' == event.value:
                translate(1, 0, 0)
                return {'RUNNING_MODAL'}
            
            elif 'LEFT_ARROW' == event.type and 'PRESS' == event.value:            
                smart_move(-1, 0)
                #Rotate(-90)
                return {'RUNNING_MODAL'}        
            elif 'RIGHT_ARROW' == event.type and 'PRESS' == event.value:
                smart_move(1, 0)
                #Rotate(90)
                return {'RUNNING_MODAL'}
            
            elif event.ctrl and 'UP_ARROW' == event.type and 'PRESS' == event.value:
                translate(0, 0, 1)
                return {'RUNNING_MODAL'}
            elif event.ctrl and 'DOWN_ARROW' == event.type and 'PRESS' == event.value:
                translate(0, 0, -1)
                return {'RUNNING_MODAL'}
            
            elif 'UP_ARROW' == event.type and 'PRESS' == event.value:
                #Translate(0, -1, 0)
                smart_move(0, 1)
                return {'RUNNING_MODAL'}
            elif 'DOWN_ARROW' == event.type and 'PRESS' == event.value:
                smart_move(0, -1)
                #Translate(0, 1, 0)
                return {'RUNNING_MODAL'}
                
            elif event.ctrl and 'C' == event.type and 'PRESS' == event.value:
                # copy
                clipboard = get_modules_at_cursor()
                clipboard_rots.clear()
                for x in clipboard:
                    clipboard_rots.append(x.rotation_euler.z)
                self.report({'INFO'}, '({}) modules copied to clipboard'.format(len(clipboard)))
                return {'RUNNING_MODAL'}
            elif event.ctrl and 'V' == event.type and 'PRESS' == event.value:
                #paste
                for x in range(len(clipboard)):
                    o = clipboard[x]
                    new = create_obj(o.data)
                    new.rotation_euler.z = clipboard_rots[x]
                return {'RUNNING_MODAL'}
        except:
            exc_type, exc_msg, exc_tb = sys.exc_info()
            print("Unexpected error line {}: {}".format(exc_tb.tb_lineno, exc_msg))
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
            bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
            return {'CANCELLED'}       
        
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            # the arguments we pass the the callback
            args = (self, context)
            # Add the region OpenGL drawing callback
            # draw in view space with 'POST_VIEW' and 'PRE_VIEW'
            self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
            self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')

            context.window_manager.modal_handler_add(self)
            
            init_modules()
            init_root_obj()

            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}           
            
def register():    
    bpy.utils.register_class(ModalDrawOperator)

def unregister():
    bpy.utils.unregister_class(ModalDrawOperator)

if __name__ == "__main__":
    register()