from node_graph.executor import NodeExecutor


def test_executor():
    e = NodeExecutor(module_path="math.sqrt")
    assert e.module_path == "math"
    assert e.callable_name == "sqrt"
    assert e.use_module_path is True
    # to_dict
    assert e.to_dict() == {
        "use_module_path": True,
        "module_path": "math",
        "callable_name": "sqrt",
        "callable": None,
        "type": None,
        "metadata": None,
    }


def test_executor_callable():
    from math import sqrt

    e = NodeExecutor(callable=sqrt)
    assert e.module_path == "math"
    assert e.callable_name == "sqrt"
    assert e.use_module_path is True
    # to_dict
    assert e.to_dict() == {
        "use_module_path": True,
        "module_path": "math",
        "callable_name": "sqrt",
        "callable": sqrt,
        "type": None,
        "metadata": None,
    }
