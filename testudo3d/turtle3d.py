
import logging
import bpy
from .tilemap3d import Tilemap3D, round_vector
from .autotiler3d import AutoTiler3D
from mathutils import Matrix, Vector

def invalidate(func):
    # invalidate the finder
    # (this method can create or destroy tiles)
    # normally the modal operator does this after every user input...
    # it's not very smart but it's simple
    # todo touch() and touched[], if cell touched then invalidate
    def wrap(*args, **kw):
        func(*args, **kw)
        t3d.finder.invalidate()
    return wrap

class Turtle3D:
    # turtle graphics (sort-of)
    # https://docs.python.org/3/library/turtle.html
    def __init__(self, cls, *args, **kw):
        cls(*args, **kw) # create t3d

    @invalidate
    def paint(self):
        t3d.paint()

    @invalidate
    def delete(self):
        t3d.delete()

    @invalidate
    def brush_draw(self):
        t3d.brush_draw()

    @invalidate
    def rotate(self, rot):
        t3d.rotate(rot)

    @invalidate
    def translate(self, x, y, z):
        t3d.translate(x, y, z)

    def copy(self):
        t3d.copy()

    @invalidate
    def paste(self):
        t3d.paste()

    def start_select(self):
        t3d.start_select()

    @invalidate
    def end_select(self):
        t3d.end_select()

    @invalidate
    def start_grab(self):
        t3d.start_grab()

    @invalidate
    def end_grab(self):
        t3d.end_grab()

    @invalidate
    def circle(self, r):
        t3d.circle(r)

    @invalidate
    def circfill(self, r):
        t3d.circfill(r)

    @invalidate
    def line(self, x, y):
        t3d.line(x, y)

    @invalidate
    def goto(self, x, y, z=None):
        z = z if z is not None else t3d.cursor.pos.z
        vec = Vector((x, y, z)) - t3d.cursor.pos
        t3d.on_move(vec)

    @invalidate
    def forward(self, i):
        vec = Vector((0, i, 0))
        forward = t3d.cursor.forward
        vec = t3d.cursor.pos + forward * vec
        t3d.line(vec.x, vec.y)

    @invalidate
    def backward(self, i):
        t3d.forward(-i)

    @invalidate
    def left(self, r):
        t3d.rotate(-r)

    @invalidate
    def right(self, r):
        t3d.rotate(r)

    @invalidate
    def setheading(self, r):
        t3d.cursor.rot = r

    @invalidate
    def setx(self, x):
        t3d.cursor.pos.x = x
        t3d.select_cube_redraw = True

    @invalidate
    def sety(self, y):
        t3d.cursor.pos.y = y
        t3d.select_cube_redraw = True

    def getx(self):
        return t3d.cursor.pos.x

    def gety(self):
        return t3d.cursor.pos.y

    @invalidate
    def dot(self):
        t3d.paint()

    def down(self):
        t3d.state.paint = True

    def up(self):
        t3d.state.paint = False

    def settile(self, name):
        t3d.cursor.tile3d = name

    def gettile(self):
        return t3d.cursor.tile3d

    def getlayer(self):
        return t3d.prop.user_layer

    @invalidate
    def setlayer(self, layer):
        t3d.prop.user_layer = layer

    def isoccupied(self):
        return bool(t3d.get_tile3d())

    @invalidate
    def home(self):
        self.goto(0, 0)
        self.setheading(0)

    def position(self):
        return t3d.cursor.pos

    def heading(self):
        return t3d.cursor.rot

    def undo(self):
        # todo
        # hmm, it always cancels the modal operator?
        # bpy.ops.ed.undo() # won't undo cursor position
        pass

    def redo(self):
        # bpy.ops.ed.redo()
        pass

    def isdown(self):
        return t3d.state.paint

    @invalidate
    def fill(self):
        state = t3d.state.paint
        t3d.state.paint = True
        t3d.end_select()
        t3d.state.paint = state

    @invalidate
    def clear(self):
        state = t3d.state.delete
        t3d.state.delete = True
        t3d.end_select()
        t3d.state.delete = state
        # state = State(delete=True)
        # self.do_with_state(state, self.end_select)
        # ?

class ManualTurtle3D(Turtle3D):
    def __init__(self, *args, **kw):
        Turtle3D.__init__(self, Tilemap3D, *args, **kw)

class AutoTurtle3D(Turtle3D):
    def __init__(self, *args, **kw):
        Turtle3D.__init__(self, AutoTiler3D, *args, **kw)