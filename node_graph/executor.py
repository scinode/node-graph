import dataclasses
from typing import Optional
import inspect


@dataclasses.dataclass
class NodeExecutor:

    use_module_path: bool = False
    module_path: Optional[str] = None
    callable_name: Optional[str] = None
    callable: Optional[str] = None
    type: Optional[str] = None
    graph_data: Optional[dict] = None
    metadata: Optional[dict] = None

    def __post_init__(self):

        self.inspect_module_path()
        self.inspect_callable()

    def inspect_module_path(self):
        if self.module_path is not None:
            self.use_module_path = True
        if not self.use_module_path:
            return
        if self.use_module_path and self.module_path is None:
            raise ValueError("module_path is required when use_module_path is True")

        if self.callable_name is None:
            self.module_path, self.callable_name = self.module_path.split(".", 1)

    def inspect_callable(self):
        import types

        if self.callable is None:
            return

        if isinstance(self.callable, (types.FunctionType, type)):
            # If callable is not defined locally
            if not (
                self.callable.__module__ == "__main__"
                or "." in self.callable.__qualname__.split(".", 1)[-1]
            ):
                self.module_path = self.callable.__module__
                self.callable_name = self.callable.__name__
                self.use_module_path = True
        elif inspect.isbuiltin(self.callable):
            # Handle built-in functions like math.sqrt
            if hasattr(self.callable, "__module__"):
                self.module_path = self.callable.__module__
            else:
                self.module_path = self.callable.__objclass__.__module__
            self.callable_name = self.callable.__name__
            self.use_module_path = True

    def to_dict(self):
        return dataclasses.asdict(self)
