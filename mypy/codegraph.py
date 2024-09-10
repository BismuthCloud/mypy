"""
Custom mypy addon to generate a graph of the codebase.
This includes:
  * Imports
  * Class defs
  * Class refs (inheritance, ivar/cvar types)
  * Function defs
  * Function refs

Since mypy is incremental, we can easily and quickly regenerate the graph when the codebase changes.

For implementation simplicity, this is tacked on to the side of mypy instead of being deeply integrated.
Specific points within mypy have hooks which call into this module to record the graph.
"""

import io
import json
import pathlib
import sys
from typing import TYPE_CHECKING, Any
from enum import Enum

if TYPE_CHECKING:
    from mypy.nodes import MypyFile


_output: io.TextIOBase | None = None
_filter_paths: list[str] = []
_module_map: dict[str, pathlib.Path] = {}


def enable(output_path: str, paths: list[str]):
    """
    Enable codegraph recording.
    """
    global _output, _filter_paths
    if output_path == "stdout":
        _output = sys.stdout
    else:
        _output = open(output_path, "w")
    _filter_paths = [pathlib.Path(p).resolve() for p in paths]


def _path_filter(p: pathlib.Path):
    return any(p.resolve().is_relative_to(filt) for filt in _filter_paths)


def _record(f: "MypyFile", j: dict[str, Any]):
    if _output and _path_filter(pathlib.Path(f.path)):
        json.dump(j | {"file": f.path}, _output)
        _output.write("\n")


def record_module(f: "MypyFile"):
    """
    Record a module definition - mainly used for dotted module name -> filename resolution (for filtering).
    """
    _module_map[f._fullname] = pathlib.Path(f.path)
    _record(f, {"type": "module", "module": f._fullname})


def record_import(f: "MypyFile", importer: str, importee: str):
    """
    Record an import statement.
    Called _before_ invalidation since the import graph has to be resolved before the SCCs can be determined.
    """
    _record(f, {"type": "import", "importer": importer, "importee": importee})


def record_invalidate(f: "MypyFile", module: str):
    """
    Record that a given module is invalidated.
    Marked when a SCC is determined to be stale and is about to be rechecked.
    """
    _record(f, {"type": "invalidate", "module": module})


def record_class_def(f: "MypyFile", fullname: str):
    _record(f, {"type": "class_def", "fullname": fullname})


class ClassRefKind(Enum):
    INHERITANCE = 1
    INSTANTIATION = 2
    # Below are TODO
    # class is used as a type in a function prototype (either args or return type)
    TYPE_IN_FUNCTION_PROTOTYPE = 3
    # type of an instance variable
    IVAR_TYPE = 4
    # type of a class variable
    CVAR_TYPE = 5
    # TODO: do we want a VAR_TYPE value for all uses of this class as the type of a variable?
    # TODO: could be interesting to experiment with ^ + rewriting all variable decls to have their explicit type
    # sorta like pseudo-inlay hints for the llm


def record_class_ref(f: "MypyFile", src: str, dst: str, kind: ClassRefKind):
    dst_module = dst.rsplit(".", 1)[0]
    if dst_module in _module_map and _path_filter(_module_map[dst_module]):
        _record(f, {"type": "class_ref", "src": src, "dst": dst, "kind": kind.name})


def record_function_def(f: "MypyFile", fullname: str):
    _record(f, {"type": "function_def", "fullname": fullname})


def record_function_call(f: "MypyFile", caller: str, callee: str):
    callee_module = callee.rsplit(".", 1)[0]
    if callee_module in _module_map and _path_filter(_module_map[callee_module]):
        _record(f, {"type": "call", "caller": caller, "callee": callee})
