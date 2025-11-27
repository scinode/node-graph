<div align="center">
  <img src="docs/source/_static/images/node-graph-logo.png" alt="ndoe-graph logo" width="220" />

  <p><strong>Build data-driven workflows with clean provenance and a friendly syntax.</strong></p>

  <p>
    <a href="https://badge.fury.io/py/node-graph"><img src="https://badge.fury.io/py/node-graph.svg" alt="PyPI version"></a>
    <a href="https://github.com/scinode/node-graph/actions/workflows/ci.yaml"><img src="https://github.com/scinode/node-graph/actions/workflows/ci.yaml/badge.svg" alt="CI status"></a>
    <a href="https://codecov.io/gh/scinode/node-graph"><img src="https://codecov.io/gh/scinode/node-graph/branch/main/graph/badge.svg" alt="codecov"></a>
    <a href="https://node-graph.readthedocs.io/"><img src="https://readthedocs.org/projects/node-graph/badge" alt="Docs status"></a>
  </p>
</div>


## Documentation
Please refer to [online docs](https://node-graph.readthedocs.io/en/latest/).

## Examples
**A simple math calculation**

```python
from node_graph import task

@task()
def add(x, y):
    return x + y

@task()
def multiply(x, y):
    return x * y

@task.graph()
def AddMultiply(x, y, z):
    the_sum = add(x=x, y=y).result
    return multiply(x=the_sum, y=z).result

```

## Engines and provenance
Explore different execution engines in [node-graph-engine](https://github.com/scinode/node-graph-engine).

Run the above graph locally with the `LocalEngine` and export the provenance graph:

```python
from node_graph.engine.local import LocalEngine

graph = AddMultiply.build(x=1, y=2, z=3)

engine = LocalEngine()
results = engine.run(graph)
# export provenance for visualization
engine.recorder.save_graphviz_svg("add_multiply.svg")
```


<p align="center">
<img src="docs/source/_static/images/add_multiply.svg" height="600" alt="Provenance graph example"/>
</p>

## License
[MIT](http://opensource.org/licenses/MIT)
