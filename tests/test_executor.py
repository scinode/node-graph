from node_graph.executor import NodeExecutor
import inspect


def test_executor():
    e = NodeExecutor(module_path="math.sqrt")
    assert e.module_path == "math"
    assert e.callable_name == "sqrt"
    assert e.mode == "module"
    assert e.executor(4) == 2


def test_executor_callable():
    from math import sqrt

    e = NodeExecutor.from_callable(sqrt)
    assert e.callable_name == "sqrt"
    assert e.module_path == "math"
    assert e.mode == "module"
    assert e.pickled_callable is None
    e.executor(4) == 2
    e = NodeExecutor.from_callable(sqrt, register_pickle_by_value=True)
    assert e.callable_name == "sqrt"
    assert e.module_path == "math"
    assert e.mode == "pickled_callable"
    assert e.pickled_callable is not None
    e.executor(4) == 2


def test_executor_source_code():
    def add(x, y):
        return x + y

    e = NodeExecutor.from_callable(add)
    assert e.callable_name == "add"
    assert e.mode == "pickled_callable"
    e.executor(4, 5) == 9
    assert e.source_code == inspect.getsource(add)


def test_executor_from_node_graph(ng):
    e = NodeExecutor.from_graph(ng)
    assert e.mode == "graph"
    assert e.graph_data == ng.to_dict()
    assert e.executor is None
