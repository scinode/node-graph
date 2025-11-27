.. _yaml:


==============
YAML format
==============
node-graph supports defining a workflow using YAML files.


Build a workflow from YAML file
==================================

Create a `test.yaml` file, here is the content:

.. code-block:: yaml

  name: test_yaml
  description: 'This is a test to create a graph using yaml file.'
  metadata:
    version: node_graph@0.1.0
    platform: node_graph
  tasks:
    - identifier: node_graph.test_float
      name: float1
      inputs:
        value: 2.0
    - identifier: node_graph.test_add
      name: add1
      inputs:
        y: 3.0
  links:
    - .to_task: add1
      to_socket: "x"
      .from_task: float1
      from_socket: 0


Then, one can build a workflow from the `test.yaml` file by:

.. code-block:: python

    from node_graph import Graph
    ng = Graph.from_yaml("test_yaml.yaml")


Export graph to YAML file
====================================
One can export a graph to a YAML file by:

.. code-block:: python

    ng.to_yaml("test_yaml.yaml")
