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
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple
from enum import Enum

if TYPE_CHECKING:
    from mypy.nodes import MypyFile


_output: Optional[io.TextIOBase] = None
_filter_path: Optional[pathlib.Path] = None
_file_map: Dict[str, pathlib.Path] = {}


def enable(output_path: str, root: str) -> None:
    """
    Enable codegraph recording.
    """
    global _output, _filter_path
    _output = open(output_path, "w")
    _filter_path = pathlib.Path(root).resolve()


def _path_filter(path: pathlib.Path) -> bool:
    if _filter_path is None:
        return False
    return str(path.resolve()).startswith(str(_filter_path))


def _record(f: "MypyFile", j: Dict[str, Any]) -> None:
    path = pathlib.Path(f.path).resolve()
    if _output and _filter_path and _path_filter(path):
        j["file"] = str(path.relative_to(_filter_path))
        json.dump(j, _output)
        _output.write("\n")
        _output.flush()


def record_module(f: "MypyFile") -> None:
    """
    Record a module definition - mainly used for dotted module name -> filename resolution (for filtering).
    """
    _file_map[f._fullname] = pathlib.Path(f.path)
    _record(f, {"type": "module", "module": f._fullname})


def record_import(f: "MypyFile", importer: str, importee: str) -> None:
    """
    Record an import statement.
    Called _before_ invalidation since the import graph has to be resolved before the SCCs can be determined.
    """
    _record(f, {"type": "import", "importer": importer, "importee": importee})


def record_invalidate(f: Optional["MypyFile"], module: str) -> None:
    """
    Record that a given module is invalidated.
    Marked when a SCC is determined to be stale and is about to be rechecked.
    """
    if f is not None:
        _record(f, {"type": "invalidate", "module": module})


def record_class_def(f: "MypyFile", fullname: str, line_range: Tuple[int, Optional[int]]) -> None:
    _file_map[fullname] = pathlib.Path(f.path)
    _record(f, {"type": "class_def", "fullname": fullname, "line_range": line_range})


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


def record_class_ref(f: "MypyFile", src: str, dst: str, kind: ClassRefKind) -> None:
    dst_module = dst.rsplit(".", 1)[0]
    if dst_module in _file_map and _path_filter(_file_map[dst_module]):
        _record(f, {"type": "class_ref", "src": src, "dst": dst, "kind": kind.name})


def record_function_def(
    f: "MypyFile", fullname: str, line_range: Tuple[int, Optional[int]]
) -> None:
    _record(f, {"type": "function_def", "fullname": fullname, "line_range": line_range})


def record_function_call(f: "MypyFile", caller: str, callee: str) -> None:
    # misnomer, either module or class
    callee_module = callee.rsplit(".", 1)[0]
    if callee_module in _file_map and _path_filter(_file_map[callee_module]):
        _record(f, {"type": "call", "caller": caller, "callee": callee})
