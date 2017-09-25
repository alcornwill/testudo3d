
from subprocess import call
import os
import sys

tests = {}
RESULTS_DIR = r"..\results"
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
        # from testudo3d import AutoTiler3D
        # t3d = AutoTiler3D(logging_level=logging.DEBUG)
        from testudo3d import Turtle3D
        t3d = Turtle3D(logging_level=logging.DEBUG)
        t3d.init()

    def execute(self):
        raise NotImplementedError()

    def test_end(self):
        import bpy
        if self.save_blend:
            if not os.path.exists(RESULTS_DIR):
                os.makedirs(RESULTS_DIR)
            blend_path = os.path.join(RESULTS_DIR, self.name + ".blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=False) # relative_remap doesn't work?

class CircleTest(T3DTest):
    name = "circle_test"
    save_blend = True

    def execute(self):
        t3d.cursor.tile3d = 'Suzanne'
        t3d.circfill(8)

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

        # Weed-1
        self.lsys(
            depth=3,
            length=7.5,
            angle=25,
            axiom='f',
            rules={'f':'f[-f]f[+f]f'}
        )

        # # Quadric-Koch-Island
        # self.lsys(
        #     depth=2,
        #     length=3,
        #     angle=90,
        #     axiom='f-f-f-f',
        #     rules={'f':'f-f+f+ff-f-f+f'}
        # )

        # # Sierpinski-Square
        # self.lsys(
        #     depth=2,
        #     length=2,
        #     angle=90,
        #     axiom='f-f-f-f',
        #     rules={'f':'ff[-f-f-f]f'}
        # )

    def lsys(self, depth, rules, angle, length, axiom):
        # l-system
        # The Computational Beauty of Nature, Gary William Flake, p76-92
        stack = []
        def right():
            t3d.right(angle)
        def left():
            t3d.left(angle)
        def forward():
            t3d.forward(length)
        def go():
            t3d.up()
            t3d.forward(length)
            t3d.down()
        def push():
            stack.append(t3d.cursor.copy())
        def pop():
            t3d.cursor = stack.pop()
        # hmm, how to get depth for |?

        # todo |, f[number], g[number]
        commands = {"-": right, "+": left, "f": forward, 'g': go,'[': push, ']': pop}
        axiom = self.replace(axiom, rules, depth)

        t3d.down()
        self.draw(axiom, commands)

    def replace_(self, seq, rules):
        newseq = ""
        for cmd in seq:
            newseq = newseq + rules.get(cmd, cmd)
        return newseq

    def replace(self, seq, rules, depth):
        for i in range(depth):
            seq = self.replace_(seq, rules)
        return seq

    def draw(self, sequence, commands):
        for command in sequence:
            commands[command]()

class CellularAutomataTest(T3DTest):
    name = "cellular_automata_test"
    save_blend = True

    def execute(self):
        from testudo3d.tilemap3d import Tile3DFinder, any
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
