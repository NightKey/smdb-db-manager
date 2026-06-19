import asyncio
from abc import abstractmethod, ABC
from asyncio import Lock
from functools import wraps
from typing import Any, List, Tuple
from os import path, mkdir

import aiosqlite
from aiosqlite import Connection
from smdb_logger import Logger

from smdb_db_manager.utils import Timer, DBStatus, ClosedException, Version, DefaultTableNames

class DBManager(ABC):
    lock: Lock = Lock()
    db: Connection | None = None
    status: DBStatus
    logger: Logger
    data_path: str
    db_name: str

    # <editor-fold desc="Wrappers">
    @staticmethod
    def async_timed(func):
        """
        Times the provided async function's runtime.
        """
        @wraps(func)
        async def async_timed_wrapper(self: 'DBManager', *args, **kwargs):
            timer = Timer()
            result = await func(self, *args, **kwargs)
            self.logger.debug(f"Function {func.__name__} returned {result}")
            self.logger.trace(f"Function {func.__name__} finished under {timer.stop(1_000_000)} ms")
            return result

        return async_timed_wrapper

    @staticmethod
    def async_required_argument(arguments: List[str]):
        """
        Ensures at least one provided argument is present of the 'arguments' list provided.
        Should only be used with functions using multiple optional arguments, but requiring at least one to be present.
        """
        def async_required_argument_decorator(func):
            @wraps(func)
            async def wrapper(self: 'DBManager', *args, **kwargs):
                for argument in arguments:
                    if argument in kwargs:
                        break
                else:
                    raise KeyError(f"At least one of the following argument needs to be present: {arguments}")
                return await func(self, *args, **kwargs)

            return wrapper

        return async_required_argument_decorator

    @staticmethod
    def async_database_safe(func):
        """
        Handles waiting for the database to be running, and lock to be available to run the function provided,
        handling the database connection's closure when the function finishes or fails.
        This wrapper will fail the call when database is in 'stopping', 'stopped' or 'failed' status, so no threads will be hanging.
        """
        @wraps(func)
        async def async_database_safe_wrapper(cls: 'DBManager', *args, **kwargs):
            during_init: bool = getattr(func, "during_init", False)
            fail_value: Any = getattr(func, "fail_value", False)
            fail_exception_index: int | str | None = getattr(func, "fail_exception_index", None)
            if cls.status > DBStatus.RUNNING:
                cls.logger.exception(
                    ClosedException(f"Function {func.__name__} called after database was in {cls.status.name} state!"))
                return fail_value
            if cls.status != DBStatus.RUNNING and not during_init:
                cls.logger.trace(f"Called {func.__name__} called while db not ready, waiting")
                while cls.status < DBStatus.RUNNING:
                    await asyncio.sleep(0.5)
            cls.logger.trace(f"Acquiring lock for function {func.__name__}")
            await cls.lock.acquire()
            if cls.status > DBStatus.STOPPING:
                cls.logger.exception(
                    ClosedException(f"Function {func.__name__} called after database was in {cls.status.name} state!"))
                cls.lock.release()
                return fail_value
            cls.logger.debug(f"Running {func.__name__} with keyword arguments: {kwargs}")
            cls.db = await aiosqlite.connect(cls.db_path).__aenter__()
            await cls.db.execute("PRAGMA foreign_keys = ON")
            try:
                return await func(cls, *args, **kwargs)
            except BaseException as ex:
                cls.logger.error(f"Exception during {func.__name__}", ex)
                if fail_exception_index is not None:
                    if isinstance(fail_value, (list, tuple, dict)):
                        fail_value[fail_exception_index] = ex
                    else:
                        fail_value = ex
                return fail_value
            finally:
                cls.logger.debug(f"Closing db connection for {func.__name__}")
                await cls.db.close()
                cls.db = None
                cls.lock.release()
                cls.logger.trace(f"Lock released by {func.__name__}")

        return async_database_safe_wrapper

    @staticmethod
    def with_fail_value(fail_value: Any):
        """
        When provided before 'async_database_safe' wrapper, will ensure the fail case will be the provided value
        """
        def with_fail_value_decorator(func):
            func.fail_value = fail_value
            return func

        return with_fail_value_decorator

    @staticmethod
    def fail_with_exception(func):
        """
        When provided before 'async_database_safe' wrapper, will ensure the fail case will contain the raised exception - if present - on the -1st index or as the return value.
        The wrapper 'with_fail_value' is not needed for this to overwrite the result on a failure.
        """
        func.fail_exception_index = -1
        return func

    @staticmethod
    def async_during_init(func):
        """
        Overrides the "async_database_safe" wrapper's safety net of waiting for database to be running, so it can be used during initialization
        """
        func.during_init = True
        return func

    # </editor-fold>

    @property
    def db_path(self) -> str:
        return path.join(self.data_path, self.db_name)

    @property
    @abstractmethod
    def current_version(self) -> Version:
        pass

    def __init__(self, logger: Logger, data_path: str, db_name: str = "database.db", version: Version | None = None):
        """
        :param logger: 'smdb_logger' for detailed logging when using the wrappers
        :param data_path: The path for the data folder where the database will be held:
        :param db_name: The name of the database file.
        :param version: The version of the database to use. If not set, the database property 'current_version' will be used. Will be used to migrate to newer versions.
        """
        self.data_path = data_path
        self.db_name = db_name
        self.logger = logger
        self.status = DBStatus.STARTING
        self.init_task: asyncio.Task | None = None
        loop = asyncio.get_event_loop()
        if path.exists(self.db_path):
            self.init_task = loop.create_task(self.__ensure_version(version or self.current_version))
            return
        self.init_task = loop.create_task(self.__prepare_versioned_db(version or self.current_version))

    async def ensure_ready(self) -> None:
        """
        Will wait while the database is starting, then clean up the init_task, raising any exception that was raised during init.
        :return:None
        """
        while self.status == DBStatus.STARTING:
            await asyncio.sleep(0.1)
        if self.init_task is None: return
        _exception = self.init_task.exception()
        self.init_task = None
        if _exception is not None: raise _exception

    async def __ensure_version(self, version: Version):
        correct, current_version = await self.__check_version(version)
        if not correct:
            if isinstance(current_version, BaseException):
                self.status = DBStatus.FAILED
                raise current_version
            result = await self.migrate_db(current_version, version)
            if not result:
                self.status = DBStatus.FAILED
                raise Exception(f"Failed to migrate DB to version {version}")
            self.logger.info(f"Database at {path.abspath(self.db_path)} updated to version {version}")
            await self.update_version(version)
        await self.__finish_startup()

    @async_timed
    async def __prepare_versioned_db(self, version: Version):
        await self.lock.acquire()
        if not path.exists(self.data_path):
            mkdir(self.data_path)
        async with aiosqlite.connect(self.db_path) as db:
            self.logger.trace(f"Creating {DefaultTableNames.Version.value} table with value {version}")
            await db.execute(
                f"""
                    CREATE TABLE IF NOT EXISTS {DefaultTableNames.Version.value} (
                        major INTEGER NOT NULL,
                        minor INTEGER NOT NULL,
                        patch INTEGER NOT NULL,
                        PRIMARY KEY (major, minor, patch)
                    ) STRICT;
                    """
            )
            self.logger.trace(f"Inserting version to {DefaultTableNames.Version.value} table")
            await db.execute(
                f"""
                    INSERT INTO {DefaultTableNames.Version.value} (major, minor, patch)
                    VALUES (?, ?, ?);
                    """,
                version.to_db()
            )
            await db.commit()
        self.lock.release()
        await self.init_db()
        await self.__finish_startup()

    @async_database_safe
    @async_during_init
    @async_timed
    async def __finish_startup(self):
        self.status = DBStatus.RUNNING

    @async_database_safe
    @async_during_init
    @with_fail_value([None, None])
    @fail_with_exception
    @async_timed
    async def __check_version(self, version: Version) -> Tuple[bool, Version]:
        rows = await self.db.execute_fetchall(
            f"""
            SELECT major, minor, patch FROM {DefaultTableNames.Version.name}
            """
        )
        if len(rows) != 1:
            raise ValueError(f"Database version contained {len(rows)} element, but 1 was expected!\nElements: {rows}")
        db_version = Version.from_db(rows[0])
        if db_version > version:
            raise ValueError(f"DB version {db_version} is bigger than required version {version}")
        return db_version == version, db_version

    @async_database_safe
    @async_during_init
    @async_timed
    async def update_version(self, version: Version) -> bool:
        """
        Updates the database version to the new version.
        :param version:
        :return: True if the update was successful otherwise False
        """
        await self.db.execute(
            f"""
            UPDATE {DefaultTableNames.Version.value} 
            SET major = ?, minor = ?, patch = ?
            """,
            version.to_db()
        )
        await self.db.commit()
        return True

    @async_database_safe
    @with_fail_value(None)
    @async_timed
    async def get_version(self) -> Version | None:
        version = await self.db.execute_fetchall(
            f"""SELECT major, minor, patch FROM {DefaultTableNames.Version.value}"""
        )
        return Version.from_db(version[0])

    @async_timed
    async def close(self) -> None:
        """
        Sets the database to be closing, then waits for all pending operations to finish, and lastly, sets the database to be closed.
        Because the database connection is not held open, this flag is sufficient to close the database.
        """
        if self.status > DBStatus.RUNNING:
            self.logger.warning(f"Close called while status is {self.status.name}")
            return
        self.logger.info("Close called!")
        self.status = DBStatus.STOPPING
        self.logger.trace("Acquiring lock for close")
        await self.lock.acquire()
        self.status = DBStatus.STOPPED
        self.lock.release()
        self.logger.trace("Close lock released")

    @classmethod
    async def create[T: 'DBManager'](cls: type[T], logger: Logger, data_path: str, db_name: str = "database.db", version: Version | None = None) -> T:
        """
        Async wrapper for creating the class.
        :param logger: 'smdb_logger' for detailed logging when using the wrappers
        :param data_path: The path for the data folder where the database will be held
        :param db_name: The name of the database file.
        :param version: The version of the database to use. If not set, the database property 'current_version' will be used. Will be used to migrate to newer versions.
        :return: The class created"""
        result = cls(logger, data_path, db_name, version)
        await result.ensure_ready()
        return result

    @async_database_safe
    @async_during_init
    @async_timed
    @fail_with_exception
    @abstractmethod
    async def migrate_db(self, current: Version, target: Version) -> bool:
        """
        Will be called when version change was detected and migration is needed.
        The following decorators are needed for ease of use and safety:
            * @DBManager.async_database_safe
            * @DBManager.async_during_init
            * @DBManager.async_timed
            * @DBManager.fail_with_exception
        :param current: Version: The current version of the DB.
        :param target: Version: The target version to migrate to.
        :return: True if migration was successful otherwise False.
        """
        pass

    @async_database_safe
    @async_during_init
    @async_timed
    @fail_with_exception
    @abstractmethod
    async def init_db(self) -> None:
        """
        Will be called to initialize the db, create all the default tables and fill in any default values. Version table already created.
        The following decorators are needed for ease of use and safety:
            * @DBManager.async_database_safe
            * @DBManager.async_during_init
            * @DBManager.async_timed
            * @DBManager.fail_with_exception
        :return:None
        """
        pass
