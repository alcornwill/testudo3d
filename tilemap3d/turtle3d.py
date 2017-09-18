
import logging
import bpy
from .tilemap3d import Tilemap3D, round_vector
from math import radians, floor
from mathutils import Matrix, Vector

class Turtle3D(Tilemap3D):
    # turtle graphics (sort-of)
    # https://docs.python.org/3/library/turtle.html
    def __init__(self, *args, **kw):
        Tilemap3D.__init__(self, *args, **kw)
        self.w = 1 # width

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

    def goto(self, x, y):
        x = round(x)
        y = round(y)
        if self.state.paint:
            self.line(x, y)
        self.cursor.pos.x = x
        self.cursor.pos.y = y
        self.construct_select_cube()

    def setx(self, x):
        self.cursor.pos.x = x
        self.construct_select_cube()

    def sety(self, y):
        self.cursor.pos.y = y
        self.construct_select_cube()

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
        self.set_active_tile3d(name)

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

    def plot(self, x, y):
        self.cursor.pos.x = x
        self.cursor.pos.y = y
        self.dot()

    def circle(self, radius):
        x0 = self.getx()
        y0 = self.gety()
        x = radius
        y = 0
        err = 0

        while x >= y:
            self.plot(x0 + x, y0 + y)
            self.plot(x0 + y, y0 + x)
            self.plot(x0 - y, y0 + x)
            self.plot(x0 - x, y0 + y)
            self.plot(x0 - x, y0 - y)
            self.plot(x0 - y, y0 - x)
            self.plot(x0 + y, y0 - x)
            self.plot(x0 + x, y0 - y)

            y += 1
            if err <= 0:
                err += 2*y + 1
            if err > 0:
                x -= 1
                err -= 2*x + 1
        self.setx(x0)
        self.sety(y0)

    def line(self, x2, y2):
        x1, y1 = self.getx(), self.gety()
        x1 = int(x1)
        y1 = int(y1)
        x2 = int(x2)
        y2 = int(y2)

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0:
            step = 1 if dy > 0 else -1
            for y in range(y1, y2+step, step):
                self.plot(x1, y)
        elif dy == 0:
            step = 1 if dx > 0 else -1
            for x in range(x1, x2+step, step):
                self.plot(x, y1)
        else:
            if dy < 0:
                dy = -dy
                stepy = -1
            else:
                stepy = 1

            if dx < 0:
                dx = -dx
                stepx = -1
            else:
                stepx = 1

            if dx > dy:
                frac = dy - (dx >> 1)
                while x1 != x2:
                    if frac >= 0:
                        y1 = y1 + stepy
                        frac = frac - dx
                    x1 = x1 + stepx
                    frac = frac + dy
                    self.plot(x1, y1)
            else:
                frac = dx - (dy >> 1)
                while y1 != y2:
                    if frac >= 0:
                        x1 = x1 + stepx
                        frac = frac - dy
                    y1 = y1 + stepy
                    frac = frac + dx
                    self.plot(x1, y1)

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