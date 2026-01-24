"""
Links
=====

Links connect task outputs to task inputs. They can be between leaf sockets or
between namespaces, with a few rules to keep graphs predictable and type-safe.
"""

# %%
# Link rules
# ----------
#
# .. list-table:: Link rules
#    :header-rows: 1
#
#    * - Link type
#      - Allowed
#      - Notes
#    * - leaf -> leaf
#      - Yes
#      - type-checked
#    * - namespace -> namespace (both non-dynamic)
#      - Yes
#      - recursively links leaf sockets; shapes must match
#    * - namespace -> namespace (any dynamic)
#      - Yes
#      - recursively links leaf sockets; no shape check
#    * - leaf -> dynamic namespace
#      - Yes
#      - fan-in allowed
#    * - leaf -> non-dynamic namespace
#      - No
#      -
#    * - namespace -> leaf
#      - No
#      -
#
# Built-in sockets (names starting with "_") are ignored for namespace shape
# checks and are not linked recursively. The special ``_outputs`` socket is the
# top-level output namespace of a task; it can be dynamic or non-dynamic, and
# can be linked as a namespace shortcut.

# %%
# Basic leaf-to-leaf linking
# --------------------------
from node_graph import Graph, task


@task()
def add(x: int, y: int) -> int:
    return x + y


ng = Graph(name="link_example")
add1 = ng.add_task(add, "add1", x=1, y=2)
add2 = ng.add_task(add, "add2", x=add1.outputs.result, y=3)
ng.add_link(add1.outputs.result, add2.inputs.x)
ng

# %%
# Namespace-to-namespace linking
# ------------------------------
# When linking namespaces, node-graph recursively links all leaf sockets.
# For non-dynamic namespaces, structures must match (built-in sockets like
# ``_wait`` are ignored).
from node_graph.socket_spec import namespace


@task()
def make_pair(x: int, y: int) -> namespace(sum=int, product=int):
    return {"sum": x + y, "product": x * y}


@task()
def consume(data: namespace(sum=int, product=int)) -> int:
    return data["sum"] + data["product"]


ng_ns = Graph(name="namespace_link")
make = ng_ns.add_task(make_pair, "make", x=2, y=3)
take = ng_ns.add_task(consume, "take")
ng_ns.add_link(make.outputs, take.inputs.data)
ng_ns

# %%
# Dynamic namespace accepts leaf links
# -----------------------------------
# If the target namespace is dynamic, leaf sockets can be linked directly.
from node_graph.socket_spec import dynamic


@task()
def emit(x: int) -> int:
    return x


@task()
def collect(datas: dynamic(int)) -> int:
    return 0


ng_dyn = Graph(name="dynamic_namespace_link")
src1 = ng_dyn.add_task(emit, "emit1")
src2 = ng_dyn.add_task(emit, "emit2")
dst = ng_dyn.add_task(collect, "collect")
ng_dyn.add_link(src1.outputs.result, dst.inputs.datas)
ng_dyn.add_link(src2.outputs.result, dst.inputs.datas)
ng_dyn

# %%
# Top-level outputs namespace shortcut
# ------------------------------------
# If you link a top-level outputs namespace to a leaf, node-graph uses the
# built-in ``_outputs`` socket to represent the namespace as a whole.
ng_out = Graph(name="top_level_outputs")
producer = ng_out.add_task(make_pair, "producer", x=1, y=2)
ng_out.add_link(producer.outputs._outputs, ng_out.outputs)  # shortcut form
ng_out
