
from test_script import *
import unittest

class T3DUnitTests(unittest.TestCase):
    # basic functional tests
    def paint_test(self):
        PaintTest().run_in_blender()

    def circle_test(self):
        CircleTest().run_in_blender()

    def line_test(self):
        LineTest().run_in_blender()

    def combined_test(self):
        CombinedTest().run_in_blender()

    def turtle_test(self):
        TurtleTest().run_in_blender()

if __name__ == '__main__':
    unittest.main()

