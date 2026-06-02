from dataclasses import dataclass, _MISSING_TYPE
from typing import List, Dict, Any, Tuple, dataclass_transform

mapping = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
    bool: "INTEGER",
    None: "NULL"
}

@dataclass_transform(**{})
class DBObject:
    @classmethod
    def uniques(cls) -> List[str]:
        """
        The list of unique names.
        :return:
        """
        return []

    @classmethod
    def primaries(cls) -> List[str]:
        """
        The list of primary keys for the table.
        :return:
        """
        return []

    @classmethod
    def foreign(cls) -> Dict[str, Tuple[str, str, bool]]:
        """
        The list of foreign keys with their targets.
        example: {remote_id: [remote_name, id, on_delete_cascade]}
        :return:
        """
        return {}

    @classmethod
    def name(cls) -> str:
        """
        The name of the table. By default, the class name will be used.
        :return:
        """
        return cls.__name__

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        dataclass(cls)

    @classmethod
    def get_keys(cls) -> List[str]:
        return list(cls.__annotations__.keys())

    @classmethod
    def get_create(cls) -> str:
        result = []
        for key, value in cls.__dataclass_fields__.items():
            line = f"{key} {mapping[value.type]}"
            if isinstance(value.default, _MISSING_TYPE) and isinstance(value.default_factory, _MISSING_TYPE):
                line += " NOT NULL"
            if key in cls.uniques():
                line += " UNIQUE"
            result.append(line)
        for column, (table, remote_column, cascade) in cls.foreign().items():
            result.append(f"""CONSTRAINT {cls.name()}_{column}_fk 
\tFOREIGN KEY ({column}) 
\tREFERENCES {table}({remote_column}){'\n\tON DELETE CASCADE'if cascade else ''}""")
        if cls.primaries():
            result.append(f"""CONSTRAINT {cls.name()}_pk
\tPRIMARY KEY ({', '.join(column for column in cls.primaries())})""")
        return ',\n'.join(result) + "\n"

    def get_values(self) -> List[Any]:
        return list([getattr(self, x) for x in self.__class__.__annotations__.keys()])
