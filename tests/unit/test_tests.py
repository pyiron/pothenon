import unittest

import pothenon


class TestVersion(unittest.TestCase):
    def test_version(self):
        version = pothenon.__version__
        print(version)
        self.assertTrue(version.startswith("0"))
