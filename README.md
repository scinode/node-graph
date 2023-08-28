# NodeGraph

[![Unit test](https://github.com/scinode/node_graph/actions/workflows/unit_test.yaml/badge.svg)](https://github.com/scinode/node_graph/actions/workflows/unit_test.yaml)

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
nt = NodeGraph(name="example")
float1 = nt.nodes.new("Float", value=2.0)
float2 = nt.nodes.new("Float", value=3.0)
add1 = nt.nodes.new("Operator", operator="+")
nt.links.new(float1.outputs[0], add1.inputs[0])
nt.links.new(float2.outputs[0], add1.inputs[1])
ntdata = nt.to_dict()
```

## License
[MIT](http://opensource.org/licenses/MIT)
