"""
Task
====

This tutorial introduces the general features of a ``Task`` in the ``node_graph`` framework.

"""
# %%
# Define and register a custom task with a decorator
# --------------------------------------------------
#
# You can register a function as a ``Task`` with a decorator.

from node_graph import task, Graph


@task(
    identifier="MyAdd",
)
def myadd(x, y):
    return x + y


# use the task in a nodegraph
ng2 = Graph(name="test_decorator")
add1 = ng2.add_task(myadd, "add1", x=1, y=2)
add2 = ng2.add_task(myadd, "add2", x=3, y=add1.outputs.result)
ng2.to_html()

# %%
# Define a custom task class
# --------------------------
# You can also define a new task by extending the ``Task`` class.
# This is useful when you want to create a task with dynamic inputs/outputs based on properties.
from node_graph import Task, namespace
from node_graph.task_spec import TaskSpec
from node_graph.executor import RuntimeExecutor


class MyTask(Task):

    _default_spec = TaskSpec(
        identifier="my_package.tasks.my_node",
        catalog="Test",
        inputs=namespace(),
        outputs=namespace(
            result=object,
        ),
        executor=RuntimeExecutor.from_callable(pow),
        base_class_path="my_package.tasks.MyTask",
    )

    def create_properties(self):
        self.add_property("node_graph.int", "t", default=1)
        self.add_property(
            "node_graph.enum",
            "function",
            default="pow",
            options=[
                ["pow", "pow", "pow function"],
                ["sqrt", "sqrt", "sqrt function"],
            ],
            update=self.update_spec,
        )

    def update_spec(self):
        """Callback to update the task spec when properties change."""
        import importlib
        from dataclasses import replace

        if self.properties["function"].value in ["pow"]:
            input_spec = namespace(
                x=float,
                y=float,
            )
        elif self.properties["function"].value in ["sqrt"]:
            input_spec = namespace(
                x=float,
            )
        func = getattr(
            importlib.import_module("math"),
            self.properties["function"].content,
        )
        executor = RuntimeExecutor.from_callable(func)
        self.spec = replace(self.spec, inputs=input_spec, executor=executor)
        self._materialize_from_spec()


# %%
# Entry point
# -----------
#
# One can register the custom task so that it can be used by its identifier in a task graph.
#
# .. code-block:: bash
#
#     [project.entry-points."node_graph.task"]
#     "my_package.my_node" = "my_package.tasks:MyTask"
#
# Then you can create the task by its identifier:
#
# .. code-block:: python
#
#    ng = Graph(name="test_node_usage")
#    float1 = ng.add_task("my_package.my_node", name="float1", value=5)
