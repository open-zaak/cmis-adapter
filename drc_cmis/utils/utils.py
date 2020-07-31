from decimal import Decimal

from django.utils.crypto import get_random_string as _get_random_string


def get_random_string(number: int = 6) -> str:
    allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return _get_random_string(length=number, allowed_chars=allowed_chars)


def build_query_filters(
    filters: dict,
    object_type: str = None,
    filter_string: str = "",
    strip_end: bool = False,
):
    """Build filters for SQL query"""
    from drc_cmis.utils.mapper import mapper

    if filters:
        for key, value in filters.items():
            if object_type is None:
                if mapper(key):
                    key = mapper(key)
                elif mapper(key, type="connection"):
                    key = mapper(key, type="connection")
                elif mapper(key, type="gebruiksrechten"):
                    key = mapper(key, type="gebruiksrechten")
                elif mapper(key, type="oio"):
                    key = mapper(key, type="oio")
            else:
                key = mapper(key, type=object_type)

            if value and value in ["NULL", "NOT NULL"]:
                filter_string += f"{key} IS {value} AND "
            elif isinstance(value, Decimal):
                filter_string += f"{key} = {value} AND "
            elif isinstance(value, list):
                if len(value) == 0:
                    continue
                filter_string += "( "
                for item in value:
                    sub_filter_string = build_query_filters({key: item}, strip_end=True)
                    filter_string += f"{sub_filter_string} OR "
                filter_string = filter_string[:-3]
                filter_string += " ) AND "
            elif value:
                filter_string += f"{key} = '{value}' AND "

    if strip_end and filter_string[-4:] == "AND ":
        filter_string = filter_string[:-4]

    return filter_string
