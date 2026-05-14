import asyncio
import unittest
from os import path, remove

from smdb_logger import Logger, LEVEL

from smdb_db_manager import DBManager
from smdb_db_manager.utils import Version


class TestDB(DBManager):
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
        loop.run_until_complete(db.ensure_ready())
        self.assertTrue(loop.run_until_complete(db.update_version(Version(0, 1, 0))))

    def test_4_fails_when_required_version_smaller_than_already_present(self):
        _logger.header("TEST 4")
        loop = asyncio.new_event_loop()
        with (self.assertRaises(ValueError)):
            loop.run_until_complete(TestDB.create(_logger, '.', db_name="testDB.db"))

    @classmethod
    def tearDownClass(cls):
        remove(path.join('.', "testDB.db"))
