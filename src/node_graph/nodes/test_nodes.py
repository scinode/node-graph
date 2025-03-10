from node_graph.node import Node


class TestFloat(Node):
    identifier = "node_graph.test_float"
    name = "TestFloat"
    catalog = "Test"

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property("node_graph.float", "value", default=0.0)

    def create_sockets(self):
        self.add_output("node_graph.float", "float")
        self.add_output("node_graph.any", "_outputs")

    def get_executor(self):
        executor = {
            "module_path": "node_graph.executors.test",
            "callable_name": "test_float",
        }
        return executor


class TestString(Node):
    identifier = "node_graph.test_string"
    name = "String"
    catalog = "Test"

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property("node_graph.string", "value", default="")

    def create_sockets(self):
        self.add_output("node_graph.string", "string")
        self.add_output("node_graph.any", "_outputs")

    def get_executor(self):
        executor = {
            "module_path": "node_graph.executors.test",
            "callable_name": "test_string",
        }
        return executor


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

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)

    def create_sockets(self):
        self.inputs._clear()
        self.outputs._clear()
        self.add_input("node_graph.float", "x")
        self.add_input("node_graph.float", "y")
        self.add_output("node_graph.float", "result")
        self.add_output("node_graph.any", "_outputs")

    def get_executor(self):
        executor = {
            "module_path": "node_graph.executors.test",
            "callable_name": "test_add",
        }
        return executor


class TestEnum(Node):

    identifier: str = "node_graph.test_enum"
    name = "Enum"
    catalog = "Test"

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property(
            "node_graph.enum",
            "function",
            options=[
                ["add", "test_add", "add function"],
                ["sqrt", "test_sqrt", "sqrt function"],
            ],
        )

    def create_sockets(self):
        self.inputs._clear()
        self.outputs._clear()
        self.add_output("node_graph.any", "result")
        self.add_output("node_graph.any", "_outputs")

    def get_executor(self):
        executor = {
            "module_path": "node_graph.executors.test",
            "callable_name": "test_enum",
        }
        return executor


class TestEnumUpdate(Node):

    identifier: str = "node_graph.test_enum_update"
    name = "EnumUpdate"
    catalog = "Test"

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property(
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
        self.inputs._clear()
        self.outputs._clear()
        if self.properties["function"].value in ["add"]:
            self.add_input("node_graph.float", "x")
            self.add_input("node_graph.float", "y")
        elif self.properties["function"].value in ["sqrt"]:
            self.add_input("node_graph.float", "x")
        self.add_output("node_graph.any", "result")
        self.add_output("node_graph.any", "_outputs")

    def get_executor(self):
        return {
            "module_path": "node_graph.executors.test",
            "callable_name": self.properties["function"].content,
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
        add1 = ng.add_node("node_graph.test_add", "add1")
        add2 = ng.add_node("node_graph.test_add", "add2")
        add3 = ng.add_node("node_graph.test_add", "add1")
        ng.add_link(add1.outputs[0], add3.inputs[0])
        ng.add_link(add2.outputs[0], add3.inputs[1])
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
