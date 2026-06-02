import unittest
from dataclasses import dataclass
from typing import List

from smdb_db_manager.utils import DBObject

class TestClass(DBObject):
    test_a: int
    test_b: str
    test_c: float

    @classmethod
    def name(cls) -> str:
        return "Test_Class"

    @classmethod
    def uniques(cls) -> List[str]:
        return ["test_a", "test_c"]

    @classmethod
    def primaries(cls) -> List[str]:
        return ["test_a"]

class DBObjectTest(unittest.TestCase):
    def test_1_can_be_created(self):
        TestClass(1, "a", 2.0)
        self.assertTrue(True)

    def test_2_returns_correct_keys(self):
        empty = TestClass.get_keys()
        self.assertListEqual(["test_a", "test_b", "test_c"], empty)
        filled = TestClass(1, "a", 2.0).get_keys()
        self.assertListEqual(empty, filled)

    def test_3_returns_correct_create(self):
        empty = TestClass.get_create()
        self.assertEqual(f"""test_a INTEGER NOT NULL UNIQUE,\ntest_b TEXT NOT NULL,\ntest_c REAL NOT NULL UNIQUE,\nCONSTRAINT {TestClass.name()}_pk\n\tPRIMARY KEY (test_a)\n""", empty)
        filled = TestClass(1, "a", 2.0).get_create()
        self.assertEqual(empty, filled)

    def test_4_returns_values_correctly(self):
        result = TestClass(1, "a", 2.0).get_values()
        self.assertListEqual([1, "a", 2.0], result)