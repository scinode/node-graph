Execution engines
=================

Graph ships with local engine so you can run the graph locally in Python.

LocalEngine
------------

``LocalEngine`` executes a graph synchronously in-process and records runtime provenance as it goes.

.. code-block:: python

   from node_graph import Graph, task
   from node_graph.engine.local import LocalEngine

   @task()
   def add(x: float, y: float) -> float:
       return x + y

   ng = Graph()
   left = ng.add_task(add, "left", x=1, y=2)
   ng.add_task(add, "right", x=3, y=left.outputs.result)

   engine = LocalEngine(name="demo")
   results = engine.run(ng)
   print(results["right"]["result"])  # 6

The engine keeps a ``ProvenanceRecorder`` instance that captures process, data, and edge information for every task invocation. Nested subgraphs reuse the same recorder so you obtain a single provenance DAG per run. Provenance can be exported as JSON or GraphViz:

.. code-block:: python

   recorder = engine.recorder
   recorder.save_json("run.json")
   recorder.save_graphviz("run.dot")
