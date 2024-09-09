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
import sys
from typing import TYPE_CHECKING, Any
from enum import Enum

if TYPE_CHECKING:
    from mypy.checker import TypeChecker
    from mypy.nodes import Context

# TODO: decorator usage? treat as call by the function?

_output: io.TextIOBase | None = None


def enable(output_path: str):
    global _output
    """
    Enable codegraph recording.
    """
    if output_path == "stdout":
        _output = sys.stdout
    else:
        _output = open(output_path, "w")


def _record(j: dict[str, Any]):
    if _output:
        json.dump(j, _output)
        _output.write("\n")


def record_invalidate(module: str):
    """
    Record that a given module is invalidated.
    Marked when a SCC is determined to be stale and is about to be rechecked.
    """
    _record({"type": "invalidate", "module": module})


def record_import(importer: str, importee: str):
    _record({"type": "import", "importer": importer, "importee": importee})


def record_class_def(module: str, name: str):
    _record({"type": "class_def", "module": module, "name": name})


class ClassRefSource(Enum):
    INHERITANCE = 1
    INSTANTIATION = 2
    # class is used as a type in a function prototype (either args or return type)
    TYPE_IN_FUNCTION_PROTOTYPE = 3
    # type of an instance variable
    IVAR_TYPE = 4
    # type of a class variable
    CVAR_TYPE = 5
    # TODO: do we want a VAR_TYPE value for all uses of this class as the type of a variable?
    # TODO: could be interesting to experiment with ^ + rewriting all variable decls to have their explicit type
    # sorta like pseudo-inlay hints for the llm


def record_class_ref(src: str, dst: str, kind: ClassRefSource):
    _record({"type": "class_ref", "src": src, "dst": dst, "kind": kind.name})


def record_function_def(fullname: str):
    _record({"type": "function_def", "fullname": fullname})


def record_function_call(chk: "TypeChecker", callee: str, context: "Context"):
    """
    Record a function call.
    Called from ExpressionChecker.
    """
    # FQN
    caller = chk.tscope.current_full_target()
    # Module object this call is in
    module = chk.modules[chk.tscope.module]
    # TODO: filter by file
    _record({"type": "call", "caller": caller, "callee": callee})
