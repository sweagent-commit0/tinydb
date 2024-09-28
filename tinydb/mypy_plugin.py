from typing import TypeVar, Optional, Callable, Dict
from mypy.nodes import NameExpr
from mypy.options import Options
from mypy.plugin import Plugin, DynamicClassDefContext
T = TypeVar('T')
CB = Optional[Callable[[T], None]]
DynamicClassDef = DynamicClassDefContext

class TinyDBPlugin(Plugin):

    def __init__(self, options: Options):
        super().__init__(options)
        self.named_placeholders: Dict[str, str] = {}