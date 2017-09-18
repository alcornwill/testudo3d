
from subprocess import call
import os
import sys

tests = {}
RESULTS_DIR = "results"
# NOTE: requires blender in PATH
COMMAND ='blender --background test.blend --python test_script.py -- --test {}'

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
        import logging
        import tilemap3d
        t3d = tilemap3d.Turtle3D(logging_level=logging.DEBUG)
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
        t3d.cursor.tile3d = 'Suzanne'
        t3d.state.paint = True
        t3d.translate(0, 1, 0)

class CircleTest(T3DTest):
    name = "circle_test"
    save_blend = True

    def execute(self):
        t3d.cursor.tile3d = 'Suzanne'
        t3d.circle(8)

class CombinedTest(T3DTest):
    name = "combined_test"
    save_blend = True

    def execute(self):
        t3d.cursor.tile3d = 'Suzanne'
        # test all features
        # features: paint, delete, copy/paste, grab, fill region, clear region, copy/paste region, grab region

        # paint
        t3d.translate(0, 1, 0)
        t3d.paint()
        t3d.translate(0, -1, 0)

        # copy/paste
        t3d.translate(2, 0, 0)
        t3d.paint()
        t3d.copy()
        t3d.delete()
        t3d.translate(0, 2, 0)
        t3d.paste()
        t3d.translate(0, -2, 0)

        # grab
        t3d.translate(2, 0, 0)
        t3d.paint()
        t3d.start_grab()
        t3d.translate(0, 2, 0)
        t3d.rotate(90)
        t3d.end_grab()
        t3d.rotate(-90)
        t3d.translate(0, -2, 0)

        # fill region
        t3d.translate(2, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.translate(0, -2, 0)

        # clear region
        t3d.translate(2, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.translate(0, -2, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.clear()
        t3d.translate(0, -2, 0)

        # copy/paste region
        t3d.translate(2, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.start_select()
        t3d.translate(0, -2, 0)
        t3d.copy()
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.clear()
        t3d.translate(0, 2, 0)
        t3d.rotate(90)
        t3d.paste()
        t3d.rotate(-90)
        t3d.translate(0, -4, 0)

        # grab region
        t3d.translate(3, 0, 0)
        t3d.start_select()
        t3d.translate(0, 2, 0)
        t3d.fill()
        t3d.start_select()
        t3d.translate(0, -2, 0)
        t3d.start_grab()
        t3d.translate(0, 2, 0)
        t3d.rotate(90)
        t3d.end_grab()
        t3d.rotate(-90)
        t3d.translate(0, -2, 0)

class TurtleTest(T3DTest):
    name = "turtle_test"
    save_blend = True

    def execute(self):
        t3d.cursor.tile3d = 'Suzanne'
        # self.basic()
        self.snake_kolam()

    def basic(self):
        t3d.down()
        t3d.forward(7.5)
        t3d.left(45)
        t3d.forward(7.5)
        t3d.left(45)
        t3d.forward(7.5)

    def snake_kolam(self):
        # Python36\Lib\turtledemo\lindenmayer.py

        def r():
            t3d.right(45)

        def l():
            t3d.left(45)

        def f():
            t3d.forward(3)

        snake_rules = {"-":r, "+":l, "f":f, "b":"f+f+f--f--f+f+f"}
        snake_replacementRules = {"b": "b+f+b--f--b+f+b"}
        snake_start = "b--f--b--f"

        drawing = self.replace(snake_start, snake_replacementRules, 2)

        t3d.root_obj.location.x = 0.5
        t3d.root_obj.location.y = -0.5
        t3d.setx(1)
        t3d.sety(-36)
        t3d.down()
        self.draw(drawing, snake_rules)

    def replace(self, seq, replacementRules, n):
        for i in range(n):
            newseq = ""
            for element in seq:
                newseq = newseq + replacementRules.get(element,element)
            seq = newseq
        return seq

    def draw(self, commands, rules):
        for b in commands:
            result = rules[b]
            if callable(result):
                result()
            else:
                self.draw(result, rules)

class CellularAutomataTest(T3DTest):
    name = "cellular_automata_test"
    save_blend = True

    def execute(self):
        from tilemap3d.tilemap3d import Tile3DFinder, any
        from mathutils import Vector
        rule = 126
        width = 32
        time = 32

        hw = int(width/2)

        t3d.cursor.tile3d = 'Suzanne'
        t3d.paint()
        t3d.translate(-1, 0, 0)
        t3d.paint()
        for t in range(time):
            finder = Tile3DFinder()
            for x in range(-hw, hw, 1):
                a = finder.get_tiles_at(Vector((x-1, t, 0)))
                b = finder.get_tiles_at(Vector((x  , t, 0)))
                c = finder.get_tiles_at(Vector((x+1, t, 0)))
                a = any(a)
                b = any(b)
                c = any(c)
                value = a << 2 | b << 1 | c
                result = rule >> value & 1
                if result:
                    t3d.cursor.pos = Vector((x, t+1, 0))
                    t3d.paint()

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
