from typing import Dict
from node_graph.utils import list_to_dict
from node_graph.node import Node
import importlib


class BaseNodeFactory:
    """
    A base factory to create specialized subclasses of Node,
    embedding the 'ndata' (i.e., all relevant data).
    """

    is_node_factory: bool = True
    default_base_class = Node

    def __new__(cls, ndata: Dict):

        ndata.setdefault("metadata", {})
        BaseClass = ndata["metadata"].get("node_class", cls.default_base_class)
        if isinstance(BaseClass, Dict):
            module_path = BaseClass["module_path"]
            callable_name = BaseClass["callable_name"]
            module = importlib.import_module(module_path)
            BaseClass = getattr(module, callable_name)

        class_name = ndata["metadata"].get("class_name", "DynamicNode")

        class DynamicNode(BaseClass):
            """A specialized Node with the embedded ndata."""

            _ndata = ndata
            is_dynamic: bool = True

            def __init__(self, *args, **kwargs):
                self.identifier = self._ndata["identifier"]
                self.node_type = self._ndata.get("metadata", {}).get(
                    "node_type", "NORMAL"
                )
                self.catalog = self._ndata.get("metadata", {}).get("catalog", "Others")
                self._error_handlers = self._ndata.get("error_handlers", [])
                super().__init__(*args, **kwargs)
                self.group_inputs = ndata["metadata"].get("group_inputs", [])
                self.group_outputs = ndata["metadata"].get("group_outputs", [])

            def create_properties(self):
                properties = list_to_dict(self._ndata.get("properties", {}))
                for prop in properties.values():
                    prop.setdefault("identifier", BaseClass.PropertyPool.any)
                    self.add_property(**prop)

            def create_sockets(self):
                inputs = list_to_dict(self._ndata.get("inputs", {}))
                for inp in inputs.values():
                    if isinstance(inp, str):
                        inp = {"identifier": BaseClass.SocketPool.any, "name": inp}
                    kwargs = {}
                    if "property_data" in inp:
                        kwargs["property_data"] = inp.get("property_data", {})
                    if "sockets" in inp:
                        kwargs["sockets"] = inp.get("sockets", None)
                    self.add_input(
                        inp.get("identifier", BaseClass.SocketPool.any),
                        name=inp["name"],
                        metadata=inp.get("metadata", {}),
                        link_limit=inp.get("link_limit", 1),
                        **kwargs,
                    )

                outputs = list_to_dict(self._ndata.get("outputs", {}))
                for out in outputs.values():
                    kwargs = {}
                    if "sockets" in out:
                        kwargs["sockets"] = out.get("sockets", None)
                    if isinstance(out, str):
                        out = {"identifier": BaseClass.SocketPool.any, "name": out}
                    self.add_output(
                        out.get("identifier", BaseClass.SocketPool.any),
                        name=out["name"],
                        metadata=out.get("metadata", {}),
                        **kwargs,
                    )

            def get_executor(self):
                return self._ndata.get("executor", None)

            def get_metadata(self):
                metadata = super().get_metadata()
                metadata["node_class"] = {
                    "module_path": BaseClass.__module__,
                    "callable_name": BaseClass.__name__,
                }
                metadata["factory_class"] = {
                    "module_path": BaseNodeFactory.__module__,
                    "callable_name": BaseNodeFactory.__name__,
                }
                return metadata

            def __repr__(self) -> str:
                return (
                    f"{class_name}(name='{self.name}', properties=[{', '.join(repr(k) for k in self.get_property_names())}], "
                    f"inputs=[{', '.join(repr(k) for k in self.get_input_names())}], "
                    f"outputs=[{', '.join(repr(k) for k in self.get_output_names())}])"
                )

        return DynamicNode
