from node_graph.node import Node


class TestFloat(Node):
    identifier = "node_graph.test_float"
    name = "TestFloat"
    catalog = "Test"

    _executor = {
        "module": "scinode.executors.test",
        "name": "test_float",
    }

    kwargs = ["t", "value"]

    def create_properties(self):
        self.properties.new("node_graph.int", "t", default=1)
        self.properties.new("node_graph.float", "value", default=0.0)

    def create_sockets(self):
        self.outputs.new("node_graph.float", "float")


class TestString(Node):
    identifier = "node_graph.test_string"
    name = "String"
    catalog = "Test"

    _executor = {
        "module": "scinode.executors.test",
        "name": "test_string",
    }
    kwargs = ["t", "value"]

    def create_properties(self):
        self.properties.new("node_graph.int", "t", default=1)
        self.properties.new("node_graph.string", "value", default="")

    def create_sockets(self):
        self.outputs.new("node_graph.string", "string")


class TestAdd(Node):
    """TestAdd

    Inputs:
        t (int): delay time (s).
        x (float):
        y (float):

    Outputs:
        Result (float).

    """

    identifier: str = "node_graph.test_add"
    name = "TestAdd"
    catalog = "Test"

    _executor = {
        "module": "scinode.executors.test",
        "name": "test_add",
    }
    kwargs = ["t", "x", "y"]

    def create_properties(self):
        self.properties.new("node_graph.int", "t", default=1)

    def create_sockets(self):
        self.inputs.clear()
        self.outputs.clear()
        self.inputs.new("node_graph.float", "x")
        self.inputs.new("node_graph.float", "y")
        self.outputs.new("node_graph.float", "result")


class TestEnum(Node):

    identifier: str = "node_graph.test_enum"
    name = "Enum"
    catalog = "Test"

    _executor = {
        "module": "scinode.executors.test",
        "name": "test_enum",
    }
    kwargs = ["t", "function"]

    def create_properties(self):
        self.properties.new("node_graph.int", "t", default=1)
        self.properties.new(
            "node_graph.enum",
            "function",
            options=[
                ["add", "test_add", "add function"],
                ["sqrt", "test_sqrt", "sqrt function"],
            ],
        )

    def create_sockets(self):
        self.inputs.clear()
        self.outputs.clear()
        self.outputs.new("node_graph.any", "result")


class TestEnumUpdate(Node):

    identifier: str = "node_graph.test_enum_update"
    name = "EnumUpdate"
    catalog = "Test"

    def create_properties(self):
        self.properties.new("node_graph.int", "t", default=1)
        self.properties.new(
            "node_graph.enum",
            "function",
            default="add",
            options=[
                ["add", "test_add", "add function"],
                ["sqrt", "test_sqrt", "sqrt function"],
            ],
            update=self.create_sockets,
        )

    def create_sockets(self):
        self.inputs.clear()
        self.outputs.clear()
        if self.properties["function"].value in ["add"]:
            self.inputs.new("node_graph.float", "x")
            self.inputs.new("node_graph.float", "y")
            self.kwargs = ["t", "x", "y"]
        elif self.properties["function"].value in ["sqrt"]:
            self.inputs.new("node_graph.float", "x")
            self.kwargs = ["t", "x"]
        self.outputs.new("node_graph.any", "result")

    def get_executor(self):
        return {
            "module": "scinode.executors.test",
            "name": self.properties["function"].content,
            "type": "function",
        }


class TestAddGroup(Node):

    identifier: str = "TestAddGroup"
    name = "TestAddGroup"
    catalog = "Test"
    node_type: str = "GROUP"

    def get_default_node_group(self):
        from node_graph import NodeGraph

        ng = NodeGraph(
            name=self.name,
            uuid=self.uuid,
            parent_node=self.uuid,
            worker_name=self.worker_name,
            type="NODE_GROUP",
        )
        add1 = ng.nodes.new("node_graph.test_add", "add1")
        add2 = ng.nodes.new("node_graph.test_add", "add2")
        add3 = ng.nodes.new("node_graph.test_add", "add1")
        ng.links.new(add1.outputs[0], add3.inputs[0])
        ng.links.new(add2.outputs[0], add3.inputs[1])
        ng.group_properties = [
            ("add1.t", "t1"),
            ("add1.t", "t2"),
        ]
        ng.group_inputs = [
            ("add1.x", "x"),
            ("add2.x", "y"),
        ]
        ng.group_outputs = [("add3.result", "result")]
        return ng
