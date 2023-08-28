.. _bash_node:

===========================================
Bash nodes
===========================================
:class:`~scinode.nodes.bash_node.BashNode` is used to execute commands in a Bash shell.


.. code-block:: console

    Node to run bash command.

    properties:
        command: bash command
        cwd: working directory

    inputs:
        dep: upstreaming dependencies

    outputs:
        Result: result of the bash command


.. code-block:: python

    from scinode import NodeTree
    from time import sleep

    nt = NodeTree(name="test_bash")
    bash1 = nt.nodes.new("BashNode", command = 'echo "hello world"')
    nt.launch()
    nt.wait()
    result = bash1.get_results()[0]["value"]
    print(f"results: {result}")

Working directory
-------------------
One can set the working directory by:

.. code-block:: python

    # set working directory
    bash1.inputs["cwd"].property.value = cwd


Create links
-------------------
BahsNode has a `dep` input socket which is used to add dependency from upstreaming nodes. Here we create two Bash nodes. The first one create a file `test_bash.md`. The scecond one add "Hello World" into the file.

.. code-block:: python

    from scinode import NodeTree
    from time import sleep

    nt = NodeTree(name="test_bash")
    bash1 = nt.nodes.new("BashNode", command='touch test_bash.md')
    bash2 = nt.nodes.new("BashNode", command='echo "Hello World" >> test_bash.md')
    nt.links.new(bash1.outputs[0], bash2.inputs["dep"])
    nt.launch()


List of all Methods
===================

.. automodule:: scinode.nodes.bash_node
   :members:
