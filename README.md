# Server Monitoring Discord Bot - Data Base Manager Reference

This document serves as a comprehensive guide for using the `DBManager` abstract base class. 
This manager provides a robust, thread-safe, and version-controlled mechanism for interacting with SQLite databases, ensuring data integrity across different parts of the Server Monitoring Discord Bot ecosystem and related projects.

---

# Quick Start Guide

1. Create a class with a super class `DBManager`.
2. Use the class method `DBManager.create(...)` to initialize and wait for the database connection to become fully operational.
3. Override `migrate_db` to handle schema/version upgrades, and override `init_db` to create and populate default tables.
4. To make creating database calls easier, there are wrappers to handle database opening and closing, handling exceptions with returning a value or raising the exception or timing the method.
These wrappers are logged with `smdb-logger`. To disable those logs, the logger provides a `log_disabled` value.

> [!IMPORTANT]
> If you are not using the `create` method, the initialization should be run using an already working async loop.

# Usable Methods Reference

The `DBManager` exposes several methods for database operations, version control, and lifecycle management.

| Function Name                                       | Arguments                                | Types                                          | Description                                                                                                                                                                                                     |
|:----------------------------------------------------|:-----------------------------------------|:-----------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [current_version](#current_version)                 |                                          |                                                | (Property) The current version of the database.                                                                                                                                                                 | 
| [create](#create)                                   | cls, logger, data_path, db_name, version | type[T], Logger, str, str, [Version](#version) | (Class Method) Asynchronous factory method to create and fully initialize aDBManagerinstance. When no version is provided, the class property [current_version](#current_version) will be used as default.      |
| [ensure_ready](#ensure_ready)                       |                                          |                                                | Waits until database status changes from `STARTING` to `RUNNING` or `FAILED`. Raisis the exception raised during initialization. Proviced for other initialization flow than the class method [create](#create) |
| [update_version](#update_version)                   | version                                  | [Version](#version)                            | Updates the database's version number to the provided version.                                                                                                                                                  |
| [get_version](#get_version)                         |                                          |                                                | Retrieves and returns the currently recorded version of the database.                                                                                                                                           |
| [close](#close)                                     |                                          |                                                | Gracefully stops and marks the database connection as closed/stopped.                                                                                                                                           |
| [migrate_db](#migrate_db)                           | current, target                          | [Version](#version), [Version](#version)       | (Abstract Method) Must be implemented by subclasses to handle schema and data migrations from the current version to the target version.                                                                        |
| [init_db](#init_db)                                 |                                          |                                                | (Abstract Method) Must be implemented by subclasses to perform all necessary initial setup, such as creating default tables and filling default data.                                                           |
| [async_database_safe](#async_database_safe)         | func                                     | Callable                                       | Decorator that handles acquiring the lock, checking database status, connecting, executing the wrapped function, and ensuring disconnection/lock release, with robust error handling.                           |
| [async_timed](#async_timed)                         | func                                     | Callable                                       | Decorator to time the execution of an async function.                                                                                                                                                           |
| [async_during_init](#async_during_init)             | func                                     | Callable                                       | Decorator helper to signal that a method is safe to run during the initial database setup phase.                                                                                                                |
| [async_required_argument](#async_required_argument) | arguments                                | List[str]                                      | Decorator to enforce that at least one provided keyword argument must be present from the specified list.                                                                                                       |
| [with_fail_value](#with_fail_value)                 | fail_value                               | Any                                            | Decorator helper to set a default failure value for decorated methods that use @async_database_safe.                                                                                                            |
| [fail_with_exception](#fail_with_exception)         | func                                     | Callable                                       | Decorator helper to indicate that a method failure should capture the exception.                                                                                                                                |
| [__prepare_versioned_db](#__prepare_versioned_db)   |                                          |                                                | (Internal) Handles initial creation of the version table and inserts the initial version.                                                                                                                       |
| [__ensure_version](#__ensure_version)               | version                                  | [Version](#version)                            | (Internal) Checks the database version against the required version and triggers migration if necessary.                                                                                                        |
| [__check_version](#__check_version)                 | version                                  | [Version](#version)                            | (Internal) Reads the current version from the database and compares it to the target version.                                                                                                                   |
| [__finish_startup](#__finish_startup)               |                                          |                                                | (Internal) Sets the database status to RUNNING once initialization is complete.                                                                                                                                 |
---

# Class and Initialization Methods

## current_version

This property is the default database version value. It needs to be overridden in subclasses to specify a different version.

## create
> [!NOTE]
> Signature: `create[T: DBManager](cls: type[T], logger: Logger, data_path: str, db_name: str = "database.db", version: Version = Version(0, 0, 1))`

This is the primary asynchronous entry point. 
It instantiates the class, runs the necessary version checks [__ensure_version](#__ensure_version), and awaits until the database connection is fully initialized and deemed `RUNNING`. 
It returns an instance of the derived class (`T`).

## ensure_ready
A utility method called by [create](#create). 
It waits asynchronously until the internal status transitions from `STARTING` to `RUNNING`. 
After waiting, it handles and re-raises any exception that occurred during the initial setup task (`init_task`).

# Core Database Operations

## update_version
> [!NOTE]
> Signature: `update_version(self, version: Version) -> bool`
    
Allows an explicit, programmatically controlled update of the database version number in the `Version` table. 
It executes an `UPDATE` query and commits the transaction. It returns `True` upon successful commitment.

## get_version
> [!NOTE]
> Signature `get_version(self) -> Version | None`

Reads the current version information from the `Version` table. 
It executes a `SELECT` query and uses `Version.from_db()` to reconstitute a `Version` object, which is returned or `None` if no record exists.

## close
> [!NOTE]
> Signature: `close(self) -> None`
    
Manages the shutdown sequence. It attempts to acquire the lock, sets the status to `STOPPING`, and then sets it to `STOPPED`. 
This signals other methods that database operations should cease.

# Abstract/Mandatory Overrides (Implementations Required)

## migrate_db
> [!NOTE]
> Signature: `migrate_db(self, current: Version, target: Version) -> bool`

This abstract method *must* be implemented by any subclass. It is responsible for all schema and data migration logic. 
You must use this when [__ensure_version](#__ensure_version) detects that `current` < `target`. It must return `True` if the migration completes successfully and `False` otherwise.

## init_db
> [!NOTE]
> Signature: `init_db(self) -> None`

This abstract method *must* be implemented. It is responsible for executing the initial setup: creating all application-specific tables (beyond the version table) and populating any mandatory default data required for the application to run.

# Decorator Guidance

## async_database_safe
**Decorator**
> [!IMPORTANT]
> **Use this on every method that touches the database.**
> This decorator should be the top decorator for all database operations

This wrapper manages the entire database interaction context: it acquires the lock, checks the operational status (`RUNNING`), establishes the connection (`self.db = await aiosqlite.connect(...)`), ensures foreign keys are active, runs the protected code in a `try...finally` block (guaranteeing the connection is closed and the lock is released), and handles exceptions.

## async_timed
**Decorator**

Wraps the function to measure and log the execution time in milliseconds. It is non-intrusive but excellent for profiling performance bottlenecks.

## async_during_init
**Decorator** 

This decorator must be stacked with [async_database_safe](#async_database_safe) when methods need to run during the startup phase (while the DB is not yet fully `RUNNING`).

## async_required_argument
**Decorator** 

Ensures that a decorated method gets at least one of the arguments provided. If neither argument is given, it raises an exception.

## with_fail_value
**Decorator** 

This decorator allows you to specify a value to be returned in case of failure. It's only needed with [async_database_safe](#async_database_safe).

## fail_with_exception
**Decorator** 

Similar to [with_fail_value](#with_fail_value). Instead of returning a value, it raises the exception returned by the wrapped call.

# Internal functions

> [!WARNING]
> These methods are only explained for the clarity of the base class. You should not use or modify them.

## __prepare_versioned_db
This method creates a database with a versions table and initializes it with the provided version number.
Then it calls [init_db](#init_db).
After that call finished, it calls [__finish_startup](#__finish_startup).

## __ensure_version
This method encapsulates the logic for version checking. 
It calls [__check_version](#__check_version) to read the stored version. 
If the stored version is older than the target version, it executes [migrate_db](#migrate_db) to upgrade the schema. 
If any step fails, it sets the status to `FAILED` and re-raises the exception. This ensures atomic version management.

## __check_version
This protected method queries the `Version` table to determine the current DB version. 
It compares this against the expected version provided. 
It raises `ValueError` if the count of records is incorrect or if the stored version is unexpectedly *newer* than the required version. 
It returns a tuple: (is_match, [Version](#version)).

## __finish_startup
This method is called after the database initialization and migration are complete.
It sets the status to `RUNNING`

---

# Additional classes

## Version
A model representing the current version of the database.
It uses [Semantic Versioning 2.0.0](https://semver.org/) compatible version numbering.

## DBStatus
This is an enum with the following values

- STARTING: The database is starting up.
- RUNNING: The database is running normally.
- STOPPING: The [close](#close) method was called and is waiting for all operations to finish
- STOPPED: The database has been stopped.
- FAILED: The database failed to start.
