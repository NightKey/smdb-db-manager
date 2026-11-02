import asyncio
import os
import unittest
from os import path, remove
import atexit

from smdb_logger import Logger, LEVEL

from smdb_db_manager import DBManager
from smdb_db_manager.utils import Version


class TestDB(DBManager):
    @property
    def current_version(self) -> Version:
        return Version(0, 0, 1)

    @DBManager.async_database_safe
    @DBManager.async_during_init
    @DBManager.async_timed
    @DBManager.fail_with_exception
    async def init_db(self) -> None:
        self.logger.info("Init db called for TestDB")

    @DBManager.async_database_safe
    @DBManager.async_during_init
    @DBManager.async_timed
    @DBManager.fail_with_exception
    async def migrate_db(self, current: Version, target: Version) -> bool:
        self.logger.info("Migrate db called for TestDB")
        if target == Version(0, 3, 0):
            raise Exception("Migration error")
        elif target == Version(0, 4, 0):
            await self.run_sql_update_script_unsafe("data/create.sql")
        return True

_logger = Logger(log_to_console=True, level=LEVEL.TRACE, use_caller_name=True)

class SMDBDBMTest(unittest.TestCase):

    def test_1_can_create_object(self):
        _logger.header("TEST 1")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db"))
        loop.run_until_complete(db.close())
        self.assertTrue(True)

    def test_2_can_start_with_database_created(self):
        _logger.header("TEST 2")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db"))
        loop.run_until_complete(db.close())
        self.assertTrue(True)

    def test_3_can_update_version(self):
        _logger.header("TEST 3")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db"))
        self.assertTrue(loop.run_until_complete(db.update_version(Version(0, 1, 0))))

    def test_4_fails_when_required_version_smaller_than_already_present(self):
        _logger.header("TEST 4")
        loop = asyncio.new_event_loop()
        with (self.assertRaises(ValueError)):
            loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db"))

    def test_5_ensure_can_migrate_database(self):
        _logger.header("TEST 5")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db", version=Version(0, 2, 0)))
        self.assertEqual(Version(0, 2, 0), loop.run_until_complete(db.get_version()))

    def test_6_ensure_migration_failure_saves_db(self):
        _logger.header("TEST 6")
        loop = asyncio.new_event_loop()
        with self.assertRaises(Exception):
            loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db", version=Version(0, 3, 0)))
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db", version=Version(0, 2, 0)))
        loop.run_until_complete(db.ensure_ready())
        self.assertEqual(Version(0, 2, 0), loop.run_until_complete(db.get_version()))

    def test_7_ensure_can_use_sql_file_update_for_migration(self):
        _logger.header("TEST 7")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db", version=Version(0, 4, 0)))
        self.assertEqual(Version(0, 4, 0), loop.run_until_complete(db.get_version()))
        rows = loop.run_until_complete(db.run_sql_fetch_script("data/read.sql"))
        self.assertEqual(1, rows[0][0])
        self.assertEqual("TEST", rows[0][1])

    def test_8_ensure_fails_when_path_not_in_the_db_folder(self):
        _logger.header("TEST 8")
        loop = asyncio.new_event_loop()
        db = loop.run_until_complete(TestDB.create(_logger, './data', db_name="testDB.db"))
        with open("test.sql", "w") as f:
            f.write("")
        result = loop.run_until_complete(db.run_sql_update_script("test.sql"))
        self.assertTrue(isinstance(result, Exception))
        self.assertEqual("Path test.sql is outside of allowed path of /Data/GitHub/smdb-db-manager/test/data/testDB.db", str(result))
        os.remove("test.sql")

    @classmethod
    def tearDownClass(cls):
        if path.exists(path.join('.', "testDB.db")):
            remove(path.join('.', "testDB.db"))

atexit.register(SMDBDBMTest.tearDownClass)