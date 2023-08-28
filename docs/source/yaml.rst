.. _yaml:


==============
YAML format
==============
Scinode supports defining and executing a workflow using YAML files and the command-line interface.


Launch workflow from YAML file
==================================

Create a `test.yaml` file, here is the content:

.. code-block:: yaml

  name: test_yaml
  description: 'This is a test to run SciNode using yaml file.'
  meta:
    version: scinode@0.1.0
    platform: scinode
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

Open a terminal, and launch the nodetree from `test.yaml`:

.. code-block:: console

    $ scinode nodetree launch-from-yaml test.yaml


Export nodetree to YAML file
====================================
One can export a nodetree to a YAML file by:

.. code-block:: console

    $ # nodetree with index 1
    $ scinode nodetree export 1 --filename "test.yaml"

Edit node
================

One can edit a node using command-line. The node data will be shown in a YAML format.

.. code-block:: console

    $ # edit node with index 2
    $ scinode node edit 2

.. note::

    One can not edit the properties has a type `General`.
