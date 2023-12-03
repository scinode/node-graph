from node_graph.collection import NodeCollection, LinkCollection
from uuid import uuid1
from node_graph.nodes import node_pool


class NodeGraph:
    """NodeGraph is a collection of nodes and links.

    Attributes:

    uuid: str
        uuid of this nodegraph.
    state: str
        state of this nodegraph.
    action: str
        action of this nodegraph.
    platform: str
        platform that used to creat this nodegraph.

    Examples:

    >>> from node_graph import NodeGraph
    >>> nt = NodeGraph(name="my_first_nodegraph")

    add nodes:

    >>> float1 = nt.nodes.new("TestFloat", name = "float1")
    >>> add1 = nt.nodes.new("TestAdd", name = "add1")

    add links:

    >>> nt.links.new(float1.outputs[0], add1.inputs[0])

    Export to dict:

    >>> nt.to_dict()

    """

    # This is the entry point of the nodes
    node_pool = node_pool

    platform: str = "node_graph"
    uuid: str = ""
    type: str = "NORMAL"
    group_properties = []
    group_inputs = []
    group_outputs = []

    def __init__(
        self,
        name="NodeGraph",
        uuid=None,
        type="NORMAL",
    ) -> None:
        """_summary_

        Args:
            name (str, optional): name of the nodegraph.
                Defaults to "NodeGraph".
            uuid (str, optional): uuid of the nodegraph.
                Defaults to None.
        """
        self.name = name
        self.uuid = uuid or str(uuid1())
        self.type = type
        self.nodes = NodeCollection(self, pool=self.node_pool)
        self.links = LinkCollection(self)
        self.ctrl_links = LinkCollection(self)
        self.state = "CREATED"
        self.action = "NONE"
        self.description = ""
        self.log = ""

    def launch(self):
        """Launch the nodegraph."""

    def save(self):
        """Save nodegraph to database."""

    def to_dict(self, short=False):
        """To dict

        Returns:
            dict: nodegraph data
        """
        from node_graph.version import __version__

        metadata = self.get_metadata()
        nodes = self.nodes_to_dict(short=short)
        links = self.links_to_dict()
        ctrl_links = self.ctrl_links_to_dict()
        data = {
            "version": "node_graph@{}".format(__version__),
            "uuid": self.uuid,
            "name": self.name,
            "state": self.state,
            "action": self.action,
            "error": "",
            "metadata": metadata,
            "nodes": nodes,
            "links": links,
            "ctrl_links": ctrl_links,
            "description": self.description,
            "log": self.log,
        }
        return data

    def get_metadata(self):
        """metadata to dict"""
        metadata = {
            "type": self.type,
            "platform": self.platform,
            "group_properties": self.group_properties,
            "group_inputs": self.group_inputs,
            "group_outputs": self.group_outputs,
        }
        return metadata

    def nodes_to_dict(self, short=False):
        """nodes to dict"""
        # save all relations using links
        nodes = {}
        for node in self.nodes:
            if short:
                nodes[node.name] = node.to_dict(short=short)
            else:
                nodes[node.name] = node.to_dict()
        return nodes

    def links_to_dict(self):
        """links to dict"""
        # save all relations using links
        links = []
        for link in self.links:
            links.append(link.to_dict())
        return links

    def ctrl_links_to_dict(self):
        """ctrl_links to dict"""
        # save all relations using ctrl_links
        ctrl_links = []
        for link in self.ctrl_links:
            ctrl_links.append(link.to_dict())
        return ctrl_links

    def to_yaml(self):
        """Export to a yaml format data.
        Results of the nodes are not exported."""
        import yaml

        data = self.to_dict()
        for name, node in data["nodes"].items():
            node.pop("results", None)
        s = yaml.dump(data, sort_keys=False)
        return s

    def update(self):
        """Update node graph."""

    def update_nodes(self, data):
        for node in self.nodes:
            node.state = data[node.name]["state"]
            node.counter = data[node.name]["counter"]
            node.action = data[node.name]["action"]
            node.update()

    @classmethod
    def from_dict(cls, ntdata):
        """Rebuild nodegraph from dict ntdata.

        Args:
            ntdata (dict): data of the nodegraph.

        Returns:
            Nodedtree: a nodegraph
        """
        import cloudpickle as pickle

        # subnodegraph
        nt = cls(
            name=ntdata["name"],
            uuid=ntdata.get("uuid"),
        )
        # print("from_dict: ", nt.uuid)
        for key in ["state", "action", "description"]:
            if ntdata.get(key):
                setattr(nt, key, ntdata.get(key))
        # read all the metadata
        for key in [
            "group_properties",
            "group_inputs",
            "group_outputs",
        ]:
            if ntdata["metadata"].get(key):
                setattr(nt, key, ntdata["metadata"].get(key))
        for name, ndata in ntdata["nodes"].items():
            # register the node created by decorator
            if ndata.get("executor", {}).get("is_pickle", False):
                node_class = pickle.loads(ndata["node_class"])
            else:
                node_class = cls.node_pool[ndata["metadata"]["identifier"]]
            node = nt.nodes.new(
                node_class,
                name=name,
                uuid=ndata.pop("uuid", None),
            )
            node.update_from_dict(ndata)
        # re-build links
        for link in ntdata.get("links", []):
            nt.links.new(
                nt.nodes[link["from_node"]].outputs[link["from_socket"]],
                nt.nodes[link["to_node"]].inputs[link["to_socket"]],
            )
        # re-build control links
        for link in ntdata.get("ctrl_links", []):
            nt.ctrl_links.new(
                nt.nodes[link["from_node"]].ctrl_outputs[link["from_socket"]],
                nt.nodes[link["to_node"]].ctrl_inputs[link["to_socket"]],
            )
        return nt

    @classmethod
    def from_yaml(cls, filename=None, string=None):
        """Build nodegraph from yaml file.

        Args:
            filename (str, optional): _description_. Defaults to None.
            string (str, optional): _description_. Defaults to None.

        Returns:
            NodeGraph: _description_
        """
        import yaml
        from node_graph.utils import yaml_to_dict

        # load data
        if filename:
            with open(filename, "r") as f:
                ntdata = yaml.safe_load(f)
        elif string:
            ntdata = yaml.safe_load(string)
        else:
            raise Exception("Please specific a filename or yaml string.")
        ntdata = yaml_to_dict(ntdata)
        nt = cls.from_dict(ntdata)
        return nt

    def copy(self, name=None):
        """Copy nodegraph.

        The nodes and links are copied.

        """
        name = f"{self.name}_copy" if name is None else name
        nt = self.__class__(name=name, uuid=None)
        # should pass the nodegraph to the nodes as parent
        nt.nodes = self.nodes.copy(parent=nt)
        # create links
        for link in self.links:
            nt.links.new(
                nt.nodes[link.from_node.name].outputs[link.from_socket.name],
                nt.nodes[link.to_node.name].inputs[link.to_socket.name],
            )
        return nt

    def copy_using_dict(self):
        """Copy nodegraph using dict data.

        Fist export the nodegraph to dict data.
        Then reset uuid of nodegraph and nodes.
        Finally, rebuild the nodegraph from dict data.
        """
        ntdata = self.to_dict()
        # copy nodes
        # reset uuid for nodegraph
        ntdata["uuid"] = str(uuid1())
        # reset uuid for nodes
        for name, node in ntdata["nodes"].items():
            node["uuid"] = str(uuid1())
        nodegraph = self.from_dict(ntdata)
        # copy links
        # TODO the uuid of the socket inside the links should be udpated.
        # print("copy nodegraph: ", nodegraph)
        return nodegraph

    @classmethod
    def load(cls, uuid):
        """Load data from database."""

    def copy_subset(self, node_list, name=None, add_ref=True):
        """Copy a subset of a nodegraph.

        Args:
            node_list (list of string): names of the nodes to be copied.
            name (str, optional): name of the new nodegraph. Defaults to None.

        Returns:
            NodeGraph: A new NodeGraph
        """

        nt = self.__class__(name=name, uuid=None)
        for node in node_list:
            nt.nodes.append(self.nodes[node].copy(nodegraph=nt))
        # copy links
        for link in self.links:
            # create ref node for input node that is not in the new nodegraph
            if (
                add_ref
                and link.from_node.name not in nt.nodes.keys()
                and link.to_node.name in nt.nodes.keys()
            ):
                nt.nodes.append(
                    self.nodes[link.from_node.name].copy(nodegraph=nt, is_ref=True)
                )
            # add link if both nodes are in the new nodegraph
            if (
                link.from_node.name in nt.nodes.keys()
                and link.to_node.name in nt.nodes.keys()
            ):
                nt.links.new(
                    nt.nodes[link.from_node.name].outputs[link.from_socket.name],
                    nt.nodes[link.to_node.name].inputs[link.to_socket.name],
                )
        return nt

    def __getitem__(self, keys):
        """Get a sub-nodegraph by the names of nodes."""
        nt = self.copy_subset(keys)
        return nt

    def __iadd__(self, other):
        self.nodes.extend(other.nodes.copy(parent=self))
        # create links
        for link in other.links:
            self.links.new(
                self.nodes[link.from_node.name].outputs[link.from_socket.name],
                self.nodes[link.to_node.name].inputs[link.to_socket.name],
            )
        return self

    def __add__(self, other):
        """Sum of two nodegraph."""
        self += other
        return self

    def delete_nodes(self, node_list):
        """_summary_

        Args:
            node_list (_type_): _description_
        """
        for name in node_list:
            # remove links connected to the node
            link_index = []
            for index, link in enumerate(self.links):
                if link.from_node.name == name or link.to_node.name == name:
                    link_index.append(index)
            del self.links[link_index]
            # remove the node
            self.nodes.delete(name)

    def wait(self, timeout=50):
        """Wait for nodegraph to finish."""
        import time

        start = time.time()
        self.update()
        while self.state not in ("PAUSED", "FINISHED", "FAILED", "CANCELLED"):
            time.sleep(0.5)
            self.update()
            if time.time() - start > timeout:
                return

    def __repr__(self) -> str:
        s = ""
        s += 'NodeGraph(name="{}, uuid="{}")\n'.format(self.name, self.uuid)
        return s
