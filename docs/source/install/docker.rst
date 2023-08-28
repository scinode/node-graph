.. _docker:


===========================================
Use Docker
===========================================
There is a `Docker <https://www.docker.com/>`__ image contains a pre-configured SciNode environment on `Docker Hub <https://hub.docker.com/r/superstar54/scinode>`__. One can use it for learning and testing purposes.



Start the `MongoDB <https://www.mongodb.com/docs/manual/installation/>`__ service by:

.. code-block:: console

    $ docker run -d --name mongodb mongo

Create a container named `scinode` by:

.. code-block:: console

    $ docker run -itd --name scinode --link mongodb:localhost superstar54/scinode

Run into `scinode` container in a interactive bash by:

.. code-block:: console

    $ docker exec -it scinode /bin/bash
