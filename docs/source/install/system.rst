.. _download_and_install:

===========================================
System-wide Installation
===========================================

.. note::
   SicNode is only tested on Linux systems.


SciNode
===========================================
The simplest way to install SciNode is to use pip.

.. code-block:: console

    pip install --upgrade --user scinode

If you want to use Celery_ as engine, run

.. code-block:: console

    pip install --upgrade --user scinode[celery]

MongoDB
===========================================

- Install locally
    One can install RabbitMQ on the computer locally. Please read the documentation for MongoDB_.

    One can check the status of RabbitMQ by:

    .. code-block:: console

        sudo systemctl status mongod
        # start the RabbitMQ service
        sudo systemctl start mongod
        # stop the RabbitMQ service
        sudo systemctl stop mongod

- Use docker
    For test and learning, one can use docker to run MongoDB. Start a mongodb container by:

    .. code-block:: console

        # run the image and add name to the container
        docker run -d -p 27017:27017 --name mongodb mongo
        # if you want to stop the mongodb container service
        docker stop mongodb
        # if you want to start the mongodb container service
        docker start mongodb

- Use cloud service
    For productive running, one need to use a clould MongoDB service. MongoDB provides a free cloud service with 500 MB storage. Please visit `MongoDB Atlas <https://www.mongodb.com/cloud/atlas/register?utm_content=rlsapostreg&utm_source=google&utm_campaign=gs_emea_rlsamulti_search_brand_dsa_atlas_desktop_rlsa_postreg&utm_term=&utm_medium=cpc_paid_search&utm_ad=&utm_ad_campaign_id=14412646473&adgroup=131761130372&gclid=Cj0KCQjwl92XBhC7ARIsAHLl9amfH46oB0MZNLoaA4nnjMT_-1x_ip56p2UQusc41A2RFeksjxAwI9YaAnRjEALw_wcB>`_

    .. note::
        It's better to allow access from all IP addresses. One can set it on the main page of the database by:

        .. code-block:: console

            1. On the left side of the screen, click on Network Access.
            2. Click the `Add IP Address` button.
            3. Click the `ALLOW ACCESS FROM ANYWHERE` button.
            4. Confirm.

RabbitMQ
=============
If you want to use Celery_ as engine, a RabbitMQ service is needed.

- Install locally
    One can install RabbitMQ on the computer locally. Please read the documentation for RabbitMQ_.

    One can check the status of RabbitMQ by:

    .. code-block:: console

        sudo systemctl status rabbitmq-server
        # start the RabbitMQ service
        sudo systemctl start rabbitmq-server
        # stop the RabbitMQ service
        sudo systemctl stop rabbitmq-server

- Use docker
    For test and learning, one can use docker to run RabbitMQ. Start a RabbitMQ container by:

    .. code-block:: console

        docker run -d -p 5672:5672 -p 15672:15672 --name rabbitmq rabbitmq:3-management
        # if you want to stop the rabbitmq container service
        docker stop rabbitmq
        # if you want to start the rabbitmq container service
        docker start rabbitmq

- Use cloud service
    For productive running, one need to use a clould RabbitMQ service. There are severl free cloud RabbitMQ service, e.g. https://www.cloudamqp.com/.


Remote Port Forwarding
===========================================
Instead of using a cloud MongoDB and RabbitMQ services, one can use a local MongoDB and RabbitMQ services and use remote port forwarding to connect to them. For example,

.. code-block:: console

    # on the local computer, forward the MongoDB port 27017 to the remote host
    ssh -R 27017:127.0.0.1:27017 -N -f user@remote_host

    # on the local computer, forward the RabbitMQ port 5672 to the remote host
    ssh -R 5672:127.0.0.1:5672 -N -f user@remote_host

Remote port forwarding through a jump server:

.. code-block:: console

    # Remote port forwarding through a jump server (J_IP) to a target server (T_IP)
    ssh -fNT -R 27017:127.0.0.1:27017 -J user@J_IP user@T_IP

.. note::
    The ssh session has a default timeout. In HPC, there are usually several login nodes (target server), one need to know the exact login node to forward the port to.

.. _MongoDb: https://www.mongodb.com/docs/manual/installation/
.. _RabbitMQ: https://www.rabbitmq.com/download.html
.. _Celery: https://docs.celeryq.dev/en/stable/
