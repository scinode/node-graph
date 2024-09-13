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
Check the [docs](https://node_graph.readthedocs.io/en/latest/) and learn about the features.

## Examples
**A simple math calculation**

```python
from node_graph import NodeGraph
ng = NodeGraph(name="example")
float1 = ng.nodes.new("node_graph.float", value=2.0)
float2 = ng.nodes.new("node_graph.float", value=3.0)
add1 = ng.nodes.new("Operator", operator="+")
ng.links.new(float1.outputs[0], add1.inputs[0])
ng.links.new(float2.outputs[0], add1.inputs[1])
ntdata = ng.to_dict()
```

## License
[MIT](http://opensource.org/licenses/MIT)
