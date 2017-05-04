
from subprocess import call
import os
import sys

tests = {}
mbt = None
RESULTS_DIR = "results"
# NOTE: requires blender in PATH
COMMAND ='blender --background debug.blend --python test_script.py -- --test {}'

def draw_pixel(x, y):
    # noinspection PyUnresolvedReferences
    from mathutils import Vector
    mbt.cursor_pos = Vector((x, y, 0.0))
    mbt.paint()

def circle(radius):
    # todo this could be MBT brush
    mbt.state.paint = True
    orig_pos = mbt.cursor_pos
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

class MbtTest:
    name = None
    save_blend = False
    metadata_path = None

    def run_in_blender(self):
        # invokes blender from command line, with itself as parameter!

        call(COMMAND.format(self.name), shell=True)

    def run(self):
        # run
        self.test_init()
        self.logic()
        self.test_end()

    def test_init(self):
        # wow this is so much nicer without all the try/except...
        import logging
        import modular_building_tool
        global mbt
        mbt = modular_building_tool.ModularBuildingTool(logging_level=logging.DEBUG)
        mbt.init(self.metadata_path)

    def logic(self):
        raise NotImplementedError()

    def test_end(self):
        import bpy
        if self.save_blend:
            if not os.path.exists(RESULTS_DIR):
                os.makedirs(RESULTS_DIR)
            blend_path = os.path.join(RESULTS_DIR, self.name + ".blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=False)

class PaintTest(MbtTest):
    name = "paint_test"
    save_blend = True
    metadata_path = "metadata.json"

    def logic(self):
        # paint something
        mbt.state.paint = True
        mbt.translate(0, 1, 0)

class CircleTest(MbtTest):
    name = "circle_test"
    save_blend = True
    metadata_path = "metadata.json"

    def logic(self):
        circle(radius=8)

class CombinedTest(MbtTest):
    name = "combined_test"
    save_blend = True
    metadata_path = "metadata.json"

    def logic(self):
        # for each module and module group, test features
        for i in range(len(mbt.module_groups)):
            mbt.active_group = i
            group = mbt.get_active_group()
            for j in range(len(group.modules)):
                group.active = j

                # paint
                mbt.translate(0, 1, 0)
                mbt.paint()
                mbt.translate(0, -1, 0)

                # grab
                mbt.translate(2, 0, 0)
                mbt.paint()
                mbt.start_grab()
                mbt.translate(0, 2, 0)
                mbt.rotate(90)
                mbt.end_grab()
                mbt.rotate(-90)
                mbt.translate(0, -2, 0)

                # copy
                mbt.translate(2, 0, 0)
                mbt.paint()
                mbt.copy()
                mbt.delete()
                mbt.translate(0, 2, 0)
                mbt.paste()
                mbt.translate(0, -2, 0)

                # box select fill
                mbt.translate(2, 0, 0)
                mbt.start_select()
                mbt.translate(0, 1, 0)
                mbt.fill()
                mbt.translate(0, -1, 0)

                # reset
                mbt.cursor_pos.x = 0
                mbt.translate(0, 0, 4)

            # reset
            mbt.cursor_pos.x = 0
            mbt.cursor_pos.z = 0
            mbt.translate(0, -4, 0)

def get_tests():
    global tests
    tests = { cls.name: cls for cls in MbtTest.__subclasses__() }

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
