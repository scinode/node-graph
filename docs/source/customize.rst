.. _custom_nodegraph:

============================================
Customize your own NodeGraph
============================================

Package structure
-------------------

Your package should follow the following structure similar to this:

.. code:: console

    <your_package_name>/
    ├── __init__.py
    ├── nodes/
    │   ├── __init__.py
    │   ├── test.py
    │   ├── ...
    ├── properties/
    │   ├── __init__.py
    │   ├── test.py
    │   ├── ...
    ├── serializers/
    │   ├── __init__.py
    │   ├── test.py
    │   ├── ...
    ├── sockets/
    │   ├── __init__.py
    │   ├── test.py
    │   ├── ...

Define your new Node, Socket and Property in the folders ``nodes``, ``sockets`` and ``properties`` respectively. Define your executor, serialization methods in the folders ``executors`` and ``serialization``. For example, in the ``nodes.test.py`` file, define your test Node class. At the end of the file, create a list called ``node_list``, and add all Node classes into this list. Here is the `example file <https://github.com/scinode/scinode/blob/main/scinode/nodes/test.py>`_ from SciNode.

.. code:: console

    node_list = [
        TestFloat,
        TestAdd,
        TestMinus,
        TestSqrt,
    ]


Entry point
-------------------

In the ``setup.py`` file of your packages, you should define an entry point called ``scinode_node``. If you define a new socket type or property type, ``scinode_socket`` or ``scinode_property`` is needed too.


.. code:: Python

    entry_points={
        'your_package_name.node': [
            'test = your_package.nodes.test:node_list',
        ],
        'your_package_name.socket': [
            'test = your_package.sockets.test:socket_list',
        ],
        'your_package_name.property': [
            'test = your_package.properties.test:property_list',
        ]
        "your_package_name.cli": [
            'test = your_package.cli.test:test',
        ],
    },
    install_requires=[
        "node_graph"
    ],


Installation
-------------------

Install your package locally:

.. code:: bash

    pip instal -e .

or publish your package to pypi, and install it using pip.
