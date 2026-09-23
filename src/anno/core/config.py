from pathlib import Path

import yaml

from .errors import AnnoError
from .project import confined


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise AnnoError(f"Duplicate data.yaml key: {key}", "INVALID_PROJECT")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def classes(root: Path) -> dict[int, str]:
    path = confined(root / "dataset/data.yaml", root)
    if not path.is_file():
        raise AnnoError("Missing dataset/data.yaml", "INVALID_PROJECT")
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except yaml.YAMLError as error:
        raise AnnoError(f"Invalid dataset/data.yaml: {error}", "INVALID_PROJECT") from error
    names = doc.get("names") if isinstance(doc, dict) else None
    if isinstance(names, list):
        result = dict(enumerate(names))
    elif isinstance(names, dict):
        result = {}
        for key, value in names.items():
            if isinstance(key, bool) or not (
                isinstance(key, int) or isinstance(key, str) and key.isdecimal()
            ):
                raise AnnoError("Class IDs must be nonnegative integers", "INVALID_PROJECT")
            index = int(key)
            if index in result:
                raise AnnoError("Duplicate normalized class ID", "INVALID_PROJECT")
            result[index] = value
    else:
        raise AnnoError("data.yaml names must be a nonempty list or mapping", "INVALID_PROJECT")
    if (
        not result
        or sorted(result) != list(range(len(result)))
        or any(not isinstance(v, str) or not v.strip() for v in result.values())
    ):
        raise AnnoError("Classes require contiguous IDs from 0 and nonempty string names", "INVALID_PROJECT")
    if len(set(result.values())) != len(result):
        raise AnnoError("Class names must be unique", "INVALID_PROJECT")
    if "nc" in doc and (type(doc["nc"]) is not int or doc["nc"] != len(result)):
        raise AnnoError("data.yaml nc does not match names", "INVALID_PROJECT")
    return result
