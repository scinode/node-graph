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
  description: 'This is a test to run SciNode using yaml file.'
  meta:
    version: node_graph@0.1.0
    platform: node_graph
    worker_name: local
  nodes:
    - identifier: Float
      name: float1
      properties:
        value: 2.0
    - identifier: Float
      name: float2
      properties:
        value: 3.0
    - identifier: Operator
      name: add1
      properties:
        operator: "+"
      inputs:
      - to_socket: x
        from_node: float1
        from_socket: 0
      - to_socket: y
        from_node: float2
        from_socket: 0

Then, one can build a workflow from the `test.yaml` file by:

.. code-block:: python

    from node_graph import NodeGraph
    ng = NodeGraph.from_yaml("test_yaml.yaml")


Export nodetree to YAML file
====================================
One can export a nodetree to a YAML file by:

.. code-block:: python

    ng.to_yaml("test_yaml.yaml")
