
.. image:: /_static/images/node-graph-logo.png
   :alt: node-graph logo
   :align: center
   :width: 420px

node-graph is an open-source platform for designing node-based workflows with provenance you can trust.

**Why teams use node-graph**

- Python APIs for rapid workflow design
- Rich provenance tracking for audits, debugging, and review
- Flexible engines that run locally or plug into your own infrastructure


Getting started
---------------

Install the core package with pip:

.. code-block:: console

    pip install --upgrade --user node_graph


Then spin up your first graph:

.. code-block:: python

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


.. toctree::
   :maxdepth: 1
   :caption: Contents:

   autogen/quick_start
   autogen/annotate_inputs_outputs
   autogen/annotate_semantics
   autogen/zone
   concept/index
   yaml
   customize


Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
