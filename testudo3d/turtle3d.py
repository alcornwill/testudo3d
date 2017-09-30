
import logging
import bpy
from .tilemap3d import Tilemap3D
from .autotiler3d import AutoTiler3D
from mathutils import Matrix, Vector

class Turtle3D(Tilemap3D):
    # turtle graphics (sort-of)
    # https://docs.python.org/3/library/turtle.html
    def __init__(self):
        pass

    def goto(self, x, y):
        self._goto(x, y)
        self.select_cube_redraw = True

    def forward(self, i):
        vec = Vector((0, i, 0))
        forward = self.cursor.forward
        vec = self.cursor.pos + forward * vec
        self.goto(vec.x, vec.y)

    def backward(self, i):
        self.forward(-i)

    def left(self, r):
        self.rotate(-r)

    def right(self, r):
        self.rotate(r)

    def setheading(self, r):
        self.cursor.rot = r

    def setx(self, x):
        self.cursor.pos.x = x
        self.select_cube_redraw = True

    def sety(self, y):
        self.cursor.pos.y = y
        self.select_cube_redraw = True

    def getx(self):
        return self.cursor.pos.x

    def gety(self):
        return self.cursor.pos.y

    def dot(self):
        self.paint()

    def down(self):
        self.state.paint = True

    def up(self):
        self.state.paint = False

    #def width(self, w):
    #    ...

    def settile3d(self, name):
        self.set_tile3d(name)

    def home(self):
        self.goto(0, 0)
        self.setheading(0)

    def position(self):
        return self.cursor.pos

    def heading(self):
        return self.cursor.rot

    def undo(self):
        # todo
        # hmm, it always cancels the modal operator?
        # bpy.ops.ed.undo() # won't undo cursor position
        pass

    def redo(self):
        # bpy.ops.ed.redo()
        pass

    def isdown(self):
        return self.state.paint

    def fill(self):
        state = self.state.paint
        self.state.paint = True
        self.end_select()
        self.state.paint = state

    def clear(self):
        state = self.state.delete
        self.state.delete = True
        self.end_select()
        self.state.delete = state
        # state = State(delete=True)
        # self.do_with_state(state, self.end_select)
        # ?

class ManualTurtle3D(Tilemap3D, Turtle3D):
    def __init__(self):
        Tilemap3D.__init__(self)
        Turtle3D.__init__(self)

class AutoTurtle3D(AutoTiler3D, Turtle3D):
    def __init__(self):
        Tilemap3D.__init__(self)
        AutoTiler3D.__init__(self)