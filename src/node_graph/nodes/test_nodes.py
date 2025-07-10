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
        self.add_input(
            "node_graph.any", "_wait", link_limit=100000, metadata={"arg_type": "none"}
        )
        self.add_output("node_graph.float", "result")
        self.add_output("node_graph.any", "_outputs")
        self.add_output(
            "node_graph.any", "_wait", link_limit=100000, metadata={"arg_type": "none"}
        )

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
