.. _yaml:


==============
YAML format
==============
NodeGraph supports defining a workflow using YAML files.


Build a workflow from YAML file
==================================

Create a `test.yaml` file, here is the content:

.. code-block:: yaml

  name: test_yaml
  description: 'This is a test to build a workflow using yaml file.'
  metadata:
    version: node_graph@0.1.0
    platform: node_graph
    worker_name: local
  nodes:
    - identifier: node_graph.test_float
      name: float1
      properties:
        - name: value
          value: 2.0
    - identifier: node_graph.test_float
      name: float2
      properties:
        - name: value
          value: 3.0
    - identifier: node_graph.test_add
      name: add1
  links:
    - to_node: add1
      to_socket: x
      from_node: float1
      from_socket: 0
    - to_node: add1
      to_socket: y
      from_node: float2
      from_socket: 0

Then, one can build a workflow from the `test.yaml` file by:

.. code-block:: python

    from node_graph import NodeGraph
    ng = NodeGraph.from_yaml("test_yaml.yaml")


Export node graph to YAML file
====================================
One can export a node graph to a YAML file by:

.. code-block:: python

    ng.to_yaml("test_yaml.yaml")
