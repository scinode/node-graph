# Register the nodes
from scinode.utils.decorator import node

# MyFloat node
@node(
    identifier="MyFloat",
    args=["value"],
    properties=[["Float", "value"]],
    outputs=[["Float", "float"]],
)
def float_node(value):
    return value


# MyAdd node
@node(
    identifier="MyAdd",
    args=["x", "y"],
    inputs=[["Float", "x"], ["Float", "y"]],
    outputs=[["Float", "Results"]],
)
def add_node(x, y):
    return x + y
