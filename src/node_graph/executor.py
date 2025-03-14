import dataclasses
from typing import Optional, Callable, Dict, Any, Union
import inspect
import base64
import importlib
import cloudpickle


def serialize_callable(
    func: Callable, register_pickle_by_value: bool = False, include_source: bool = True
) -> Dict[str, Any]:
    """
    Serialize a callable (function, class, etc.) to a dictionary with:
      - optional source code
      - pickled representation
      - callable name

    Args:
        func (Callable): The callable to inspect and serialize.
        register_pickle_by_value (bool, optional): Whether to register the
            callable's module with cloudpickle for pickling by value. Defaults
            to False.
        include_source (bool, optional): Whether to include the callable's
            source code in the output. Defaults to False.

    Returns:
        Dict[str, Any]: A dictionary containing the source code (if requested),
            the name of the callable, a base64-encoded pickled representation,
            and a mode key set to "pickled_callable".
    """
    import types

    if not isinstance(func, (types.FunctionType, types.BuiltinFunctionType, type)):
        raise TypeError("Provided object is not a callable function or class.")

    # Attempt to retrieve source code if requested
    if include_source:
        try:
            source_code = inspect.getsource(func)
        except (OSError, TypeError):
            source_code = "Failed to retrieve source code."
    else:
        source_code = ""
    callable_name = func.__name__
    if func.__module__ == "__main__" or "." in func.__qualname__.split(".", 1)[-1]:
        mode = "pickled_callable"
        pickled_data = cloudpickle.dumps(func)
        # Base64 encode the pickled callable
        pickled_callable = base64.b64encode(pickled_data).decode("utf-8")
        module_path = None
    else:
        # Optionally register the module for pickling by value
        if register_pickle_by_value:
            module_path = func.__module__
            module = importlib.import_module(module_path)
            cloudpickle.register_pickle_by_value(module)
            pickled_data = cloudpickle.dumps(func)
            # Unregister after pickling
            cloudpickle.unregister_pickle_by_value(module)
            mode = "pickled_callable"
            pickled_callable = base64.b64encode(pickled_data).decode("utf-8")
        else:
            # Global callable (function/class), store its module and name for reference
            mode = "module"
            module_path = func.__module__
            pickled_callable = None

    return {
        "mode": mode,
        "module_path": module_path,
        "pickled_callable": pickled_callable,
        "callable_name": callable_name,
        "source_code": source_code,
    }


@dataclasses.dataclass
class NodeExecutor:
    """
    A class that encapsulates different ways of representing and executing
    a callable or computational graph.

    Attributes:
        mode (Optional[str]): Can be "module", "graph", or "pickled_callable".
        module_path (Optional[str]): If the mode is "module", the path to the
            module (e.g. 'my_package.my_module').
        callable_name (Optional[str]): If the mode is "module", the name of
            the callable within the module.
        callable_kind (Optional[str]): A free-form string for additional context
            (replaces 'type' to avoid overshadowing built-in `type`).
        graph_data (Optional[dict]): If the mode is "graph", a dictionary
            representing the graph.
        pickled_callable (Optional[str]): If the mode is "pickled_callable",
            a base64-encoded serialized callable.
        source_code (Optional[str]): Optional source code (if captured).
        metadata (Optional[dict]): Additional metadata or context.
    """

    mode: Optional[str] = None  # "module", "graph", "pickled_callable"
    module_path: Optional[str] = None
    callable_name: Optional[str] = None
    callable_kind: Optional[str] = None
    graph_data: Optional[dict] = None
    pickled_callable: Optional[str] = None
    source_code: Optional[str] = None
    metadata: Optional[dict] = None

    def __post_init__(self):
        """
        Post-initialization hook that inspects and normalizes
        module_path/callable_name if mode is 'module'.
        """
        self._normalize_module_mode()

    @classmethod
    def from_callable(
        cls,
        func: Callable,
        register_pickle_by_value: bool = False,
        include_source: bool = True,
    ) -> "NodeExecutor":
        """
        Factory method that creates a NodeExecutor from a callable by serializing
        it with cloudpickle (and optionally including source code).

        Args:
            func (Callable): The callable to be wrapped by NodeExecutor.
            register_pickle_by_value (bool, optional): Whether to register the
                callable's module for cloudpickle by-value serialization.
            include_source (bool, optional): Whether to include the callable's
                source code in the serialized data.

        Returns:
            NodeExecutor: An instance of NodeExecutor initialized in
                "pickled_callable" mode.
        """
        executor_data = serialize_callable(
            func,
            register_pickle_by_value=register_pickle_by_value,
            include_source=include_source,
        )
        return cls(**executor_data)

    @classmethod
    def from_graph(cls, graph: Any) -> "NodeExecutor":
        """
        Factory method that creates a NodeExecutor from a graph-like object that
        can be converted to a dictionary.

        Args:
            graph (Any): An object that implements a `to_dict()` method.

        Returns:
            NodeExecutor: An instance of NodeExecutor in "graph" mode.
        """
        graph_data = graph.to_dict()
        return cls(mode="graph", graph_data=graph_data)

    def _normalize_module_mode(self) -> None:
        """
        Ensure the NodeExecutor is properly configured for "module" mode if
        `module_path` is set. Automatically splits the module_path to extract
        the callable name if `callable_name` is None.
        """
        if self.module_path is not None and self.mode is None:
            self.mode = "module"

        if self.mode != "module":
            return

        if self.module_path is None:
            raise ValueError("module_path is required when mode is 'module'.")

        # If there's no explicit callable_name, try splitting the module_path
        if self.callable_name is None:
            parts = self.module_path.split(".")
            if len(parts) < 2:
                raise ValueError(
                    "module_path must contain at least one dot to separate "
                    "the module from the callable (e.g. 'mymodule.myfunc')"
                )
            self.callable_name = parts[-1]
            self.module_path = ".".join(parts[:-1])

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert this NodeExecutor instance to a dictionary.

        Returns:
            dict: A dictionary representation of this NodeExecutor.
        """
        return dataclasses.asdict(self)

    @property
    def executor(self) -> Union[Callable, None]:
        """
        Dynamically retrieve the actual callable (function/class/method/etc.)
        based on the NodeExecutor's mode.

        - "module": Imports the specified module and returns the callable by name.
        - "pickled_callable": Unpickles and returns the callable.
        - "graph": Returns None (not a direct callable).
        - otherwise: Returns None.

        Returns:
            Callable or None: The resolved callable, or None if unavailable.
        """
        if self.mode == "module":
            # Attempt to import the module and retrieve the callable
            try:
                module = importlib.import_module(self.module_path)
                return getattr(module, self.callable_name)
            except (ImportError, AttributeError) as e:
                raise ImportError(
                    f"Failed to import '{self.module_path}' or find "
                    f"callable '{self.callable_name}'. Error: {e}"
                ) from e

        elif self.mode == "pickled_callable":
            if not self.pickled_callable:
                return None
            pickled_data = base64.b64decode(self.pickled_callable.encode("utf-8"))
            return cloudpickle.loads(pickled_data)

        # If it's a graph or another mode, we do not have a direct executor
        return None
