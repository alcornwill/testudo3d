
from subprocess import call
import os
import sys

tests = {}
t3d = None
RESULTS_DIR = "results"
# NOTE: requires blender in PATH
COMMAND ='blender --background test.blend --python test_script.py -- --test {}'

def draw_pixel(x, y):
    from mathutils import Vector
    t3d.cursor_pos = Vector((x, y, 0.0))
    t3d.paint()

def circle(radius):
    # todo this could be T3D brush
    t3d.state.paint = True
    orig_pos = t3d.cursor_pos
    x0 = orig_pos.x
    y0 = orig_pos.y
    x = radius
    y = 0
    err = 0

    while x >= y:
        draw_pixel(x0 + x, y0 + y)
        draw_pixel(x0 + y, y0 + x)
        draw_pixel(x0 - y, y0 + x)
        draw_pixel(x0 - x, y0 + y)
        draw_pixel(x0 - x, y0 - y)
        draw_pixel(x0 - y, y0 - x)
        draw_pixel(x0 + y, y0 - x)
        draw_pixel(x0 + x, y0 - y)

        y += 1
        if err <= 0:
            err += 2*y + 1
        if err > 0:
            x -= 1
            err -= 2*x + 1

class T3DTest:
    name = None
    save_blend = False

    def run_in_blender(self):
        # invokes blender from command line, with itself as parameter!
        call(COMMAND.format(self.name), shell=True)

    def run(self):
        # run
        self.test_init()
        self.execute()
        self.test_end()

    def test_init(self):
        # wow this is so much nicer without all the try/except...
        import logging
        import tilemap3d
        global t3d
        t3d = tilemap3d.Tilemap3D(logging_level=logging.DEBUG)
        t3d.init()

    def execute(self):
        raise NotImplementedError()

    def test_end(self):
        import bpy
        if self.save_blend:
            if not os.path.exists(RESULTS_DIR):
                os.makedirs(RESULTS_DIR)
            blend_path = os.path.join(RESULTS_DIR, self.name + ".blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=False)

class PaintTest(T3DTest):
    name = "paint_test"
    save_blend = True

    def execute(self):
        # paint something
        t3d.active_tile3d = 'Suzanne'
        t3d.state.paint = True
        t3d.translate(0, 1, 0)

class CircleTest(T3DTest):
    name = "circle_test"
    save_blend = True

    def execute(self):
        t3d.active_tile3d = 'Suzanne'
        circle(radius=8)

class CombinedTest(T3DTest):
    name = "combined_test"
    save_blend = True

    def execute(self):
        t3d.active_tile3d = 'Suzanne'
        # test all features
        # features: paint, clear, copy, paste, grab
        # also box select, all features should work on multiple cells

        # paint
        t3d.translate(0, 1, 0)
        t3d.state.paint = True
        t3d.cdraw()
        t3d.state.paint = False
        t3d.translate(0, -1, 0)

        # grab
        t3d.translate(2, 0, 0)
        t3d.state.paint = True
        t3d.cdraw()
        t3d.state.paint = False
        t3d.start_grab()
        t3d.translate(0, 2, 0)
        t3d.rotate(90)
        t3d.end_grab()
        t3d.rotate(-90)
        t3d.translate(0, -2, 0)

        # copy
        t3d.translate(2, 0, 0)
        t3d.state.paint = True
        t3d.cdraw()
        t3d.state.paint = False
        t3d.copy()
        t3d.state.clear = True
        t3d.cdraw()
        t3d.state.clear = False
        t3d.translate(0, 2, 0)
        t3d.paste()
        t3d.translate(0, -2, 0)

        # box select fill
        t3d.translate(2, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.translate(0, -2, 0)

        # box select delete
        t3d.translate(2, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.translate(0, -2, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.state.clear = True
        t3d.end_select()
        t3d.state.clear = False
        t3d.translate(0, -2, 0)


def get_tests():
    global tests
    tests = { cls.name: cls for cls in T3DTest.__subclasses__() }

def parse_args():
    import argparse

    argv = sys.argv
    if "--" not in argv:
        argv = []
    else:
        argv = argv[argv.index("--") + 1:]  # get all args after "--"
    parser = argparse.ArgumentParser(description=COMMAND.format("[test_name]"))
    parser.add_argument("-t", "--test", dest="test_name", type=str, required=True,
                        help="name of test to run")
    args = parser.parse_args(argv)
    if not argv:
        parser.print_help()
        return
    if not args.test_name:
        print("Error: --test [test_name] argument not given, aborting.")
        parser.print_help()
        return
    if args.test_name not in tests:
        print("Error: --test {} is not a test".format(args.test_name))
        return
    return args

def main():
    get_tests()
    args = parse_args()
    if not args: return
    cls = tests[args.test_name]
    cls().run()
    print("tests finished, exiting")

if __name__ == "__main__":
    main()
