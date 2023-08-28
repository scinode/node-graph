.. _data:

============
Data
============
All the results of the nodes are stored in the `data` collection in the MongoDB database. Thus one can query the database to fine the data you are interested.

Data type
--------------
The type of the data is specified in the socket.


Command line
--------------

.. code-block:: console

    $ # list all node
    $ scinode data list
    $ # list all node with indentifier ASEAtoms
    $ scinode data list -i "ASEAtoms"
    $ # show the detail of node with index 1
    $ scinode data show 1

Query data
--------------

.. code-block:: python

    from scinode.orm import load_profile, Data
    load_profile()
    datas = Data.objects(name__contains = "atoms")
    # Prints out the names of all the Data in the database
    for data in Data.objects:
        print(data.name)
    # find all the Data that its name contains the string "Symbols"
    datas = Data.objects(name__contains = "Symbols")

For more information, please refer to the `MongoDB query manual <https://docs.mongoengine.org/guide/querying.html>`_ for the query syntax.
