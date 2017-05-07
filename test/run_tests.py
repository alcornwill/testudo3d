
# noinspection PyUnresolvedReferences
from test_script import CircleTest, PaintTest, CombinedTest
import unittest

class MbtUnitTests(unittest.TestCase):
    # basic functional tests
    def circle_test(self):
        CircleTest().run_in_blender()

    def paint_test(self):
        PaintTest().run_in_blender()

    def combined_test(self):
        CombinedTest().run_in_blender()

if __name__ == '__main__':
    unittest.main()
