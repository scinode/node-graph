# NodeGraph
[![PyPI version](https://badge.fury.io/py/node-graph.svg)](https://badge.fury.io/py/node-graph)
[![CI](https://github.com/scinode/node-graph/actions/workflows/ci.yaml/badge.svg)](https://github.com/scinode/node-graph/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/scinode/node-graph/branch/main/graph/badge.svg)](https://codecov.io/gh/scinode/node-graph)
[![Docs status](https://readthedocs.org/projects/node-graph/badge)](http://node-graph.readthedocs.io/)



A platform for designing node-based workflows.


```console
    pip install --upgrade --user node_graph
```


## Documentation
Check the [docs](https://node-graph.readthedocs.io/en/latest/) and learn about the features.

## Examples
**A simple math calculation**

```python
from node_graph import NodeGraph, node

@node()
def add(x, y):
    return x + y

ng = NodeGraph(name="example")
add1 = ng.add_node(add, x=1, y=2)
add2 = ng.add_node(add, x=3)
ng.add_link(add1.outputs.result, add2.inputs.y)
ntdata = ng.to_dict()
```

## License
[MIT](http://opensource.org/licenses/MIT)
