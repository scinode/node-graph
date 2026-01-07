Workflow authoring
==================

`node-graph` supports two ways to build graphs: a direct API and a
context-manager style that feels closer to writing regular Python code.
The context-manager style also exposes zones such as ``If`` and ``While``
and a shared ``ctx`` object for passing values between tasks.

Context manager graphs
----------------------

Use the ``Graph`` context manager to build a workflow inline. Tasks are
added as you call them and outputs can be wired with ``.result``.

.. code-block:: python

   from node_graph import Graph, task

   @task()
   def add(x, y):
       return x + y

   @task()
   def multiply(x, y):
       return x * y

   with Graph("AddMultiply") as wg:
       the_sum = add(x=1, y=2).result
       wg.outputs.result = multiply(x=the_sum, y=3).result


Zones: If and While
-------------------

Zones allow you to gate or repeat a block of tasks based on a condition.
The condition itself is defined by a task result.

``ctx`` is a shared store for intermediate values. You can write to it
from one task and read it as input in another task.

.. code-block:: python

    @task()
    def smaller_than(x, y):
        return x < y

    @task()
    def add(x, y):
        return x + y

    @task()
    def is_even(x):
        return x % 2 == 0

    @task.graph()
    def while_with_if(index=0, limit=10,
                    total=0,
                    increment=1):

        graph = get_current_graph()
        graph.ctx.total = total
        graph.ctx.index = index
        condition = smaller_than(graph.ctx.index, limit).result

        with While(condition):
            is_even_cond = is_even(graph.ctx.index).result
            with If(is_even_cond) as if_zone:
                graph.ctx.total = add(x=graph.ctx.total, y=graph.ctx.index).result
            next_index = add(x=graph.ctx.index, y=increment).result
            graph.ctx.index = next_index
            if_zone >> next_index

        return graph.ctx.total

If and While are available for both context-manager graphs and ``@task.graph``
workflows.
