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

Define your new Node, Socket and Property in the folders ``nodes``, ``sockets`` and ``properties`` respectively. Define your executor, serialization methods in the folders ``executors`` and ``serialization``. For example, in the ``nodes.test.py`` file, define your test Node class.


Entry point
-------------------

In the ``pyproject.toml`` file of your packages, you should define the entry points for your nodes, sockets and properties. For example, if your package name is ``abc``, you should define the entry points like this:


.. code:: toml

    [project.entry-points."abc.task"]
    "abc.add" = "abc.nodes.test:Add"
    "abc.multiply" = "abc.nodes.test:Multiply"

    [project.entry-points."abc.property"]
    "abc.any" = "abc.properties.test:SocketAny"
    "abc.int" = "abc.properties.test:SocketInt"

    [project.entry-points."abc.socket"]
    "abc.any" = "abc.sockets.test:SocketAny"
    "abc.int" = "abc.sockets.test:SocketInt"



Installation
-------------------

Install your package locally:

.. code:: bash

    pip instal -e .

or publish your package to pypi, and install it using pip.
