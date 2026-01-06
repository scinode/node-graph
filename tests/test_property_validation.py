from node_graph.property import TaskProperty
from node_graph.properties.builtins import PropertyIntVector


class GetListWrapper:
    def __init__(self, values):
        self._values = list(values)

    def get_list(self):
        return list(self._values)


def test_validation_adapter_allows_custom_unwrap():
    def unwrap_get_list(value):
        if hasattr(value, "get_list") and callable(value.get_list):
            return value.get_list()
        return TaskProperty.NOT_ADAPTED

    TaskProperty.register_validation_adapter(unwrap_get_list)
    try:
        prop = PropertyIntVector(name="v", size=3)
        wrapped = GetListWrapper([1, 2, 3])
        prop.value = wrapped
        assert prop.value is wrapped
    finally:
        TaskProperty.unregister_validation_adapter(unwrap_get_list)
