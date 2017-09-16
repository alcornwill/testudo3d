
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
        # wow this is so much nicer without all the try/except...
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
        t3d.active_tile3d = 'Suzanne'
        t3d.state.paint = True
        t3d.translate(0, 1, 0)

class CircleTest(T3DTest):
    name = "circle_test"
    save_blend = True

    def execute(self):
        t3d.active_tile3d = 'Suzanne'
        t3d.circle(8)

class LineTest(T3DTest):
    name = "line_test"
    save_blend = True

    def execute(self):
        t3d.active_tile3d = 'Suzanne'
        # t3d.line(0, 0, 9, 3)
        t3d.line(0, 0, 1, 9)

class CombinedTest(T3DTest):
    name = "combined_test"
    save_blend = True

    def execute(self):
        t3d.active_tile3d = 'Suzanne'
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
        t3d.active_tile3d = 'Suzanne'
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

        drawing = self.replace(snake_start, snake_replacementRules, 3)

        t3d.up()
        t3d.backward(25)
        t3d.down()
        self.draw(drawing, snake_rules)

    def replace(self, seq, replacementRules, n ):
        for i in range(n):
            newseq = ""
            for element in seq:
                newseq = newseq + replacementRules.get(element,element)
            seq = newseq
        return seq

    def draw(self, commands, rules ):
        for b in commands:
            try:
                rules[b]()
            except TypeError:
                try:
                    draw(rules[b], rules)
                except:
                    pass

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
