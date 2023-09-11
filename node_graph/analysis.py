def get_nt_short_data(ngdata):
    from copy import deepcopy

    ngdata_short = deepcopy(ngdata)
    for name, node in ngdata["nodes"].items():
        if node["metadata"]["node_type"] in ["REF"]:
            node["state"] = "FINISHED"
            node["action"] = "NONE"
        ngdata_short["nodes"][name] = {
            "name": node["name"],
            "identifier": node["metadata"]["identifier"],
            "node_type": node["metadata"]["node_type"],
            "uuid": node["uuid"],
            "state": node["state"],
            "action": node["action"],
        }
    return ngdata_short


class NodeGraphAnalysis:
    """Analyze the node graph."""

    def __init__(self, ngdata=None) -> None:
        """
        Args:
            ngdata (dict): node graph ngdata
        """
        if ngdata is not None:
            self.links = ngdata["links"]
            self.ctrl_links = ngdata["ctrl_links"]
            self.nodes = ngdata["nodes"]
            self.nnode = len(self.nodes)
            self.set_node_index()
            self.get_input_output()

    def get_input_output(self):
        """build inputs and outputs for each node

        Returns:
            _type_: _description_
        """
        # inputs
        inputs = {name: {} for name in self.nodes.keys()}
        for link in self.links:
            if link["to_socket"] not in inputs[link["to_node"]]:
                inputs[link["to_node"]][link["to_socket"]] = [link["from_node"]]
            else:
                inputs[link["to_node"]][link["to_socket"]].append(link["from_node"])
        self.inputs = inputs
        # ctrl_inputs
        ctrl_inputs = {name: {} for name in self.nodes.keys()}
        ctrl_input_links = {name: {} for name in self.nodes.keys()}
        for i, link in enumerate(self.ctrl_links):
            if link["to_socket"] not in ctrl_inputs[link["to_node"]]:
                ctrl_inputs[link["to_node"]][link["to_socket"]] = [link["from_node"]]
                ctrl_input_links[link["to_node"]][link["to_socket"]] = [i]
            else:
                ctrl_inputs[link["to_node"]][link["to_socket"]].append(
                    link["from_node"]
                )
                ctrl_input_links[link["to_node"]][link["to_socket"]].append(i)
        self.ctrl_inputs = ctrl_inputs
        self.ctrl_input_links = ctrl_input_links
        # outputs
        outputs = {name: {} for name in self.nodes.keys()}
        for link in self.links:
            if link["from_socket"] not in outputs[link["from_node"]]:
                outputs[link["from_node"]][link["from_socket"]] = [link["to_node"]]
            else:
                outputs[link["from_node"]][link["from_socket"]].append(link["to_node"])
        self.outputs = outputs
        # ctrl_outputs
        ctrl_outputs = {name: {} for name in self.nodes.keys()}
        ctrl_output_links = {name: {} for name in self.nodes.keys()}
        for i, link in enumerate(self.ctrl_links):
            if link["from_socket"] not in ctrl_outputs[link["from_node"]]:
                ctrl_outputs[link["from_node"]][link["from_socket"]] = [link["to_node"]]
                ctrl_output_links[link["from_node"]][link["from_socket"]] = [i]
            else:
                ctrl_outputs[link["from_node"]][link["from_socket"]].append(
                    link["to_node"]
                )
                ctrl_output_links[link["from_node"]][link["from_socket"]].append(i)
        self.ctrl_outputs = ctrl_outputs
        self.ctrl_output_links = ctrl_output_links


class ConnectivityAnalysis(NodeGraphAnalysis):
    """Analyze the node graph based on sparse matrix representations.
    1) child nodes
    2) input nodes

    Args:
        NodeGraphAnalysis (_type_): _description_
    """

    def __init__(self, ngdata=None) -> None:
        if not self.is_short_data(ngdata):
            ngdata = get_nt_short_data(ngdata)
        super().__init__(ngdata)

    def is_short_data(self, ngdata):
        flag = True
        for name, node in ngdata["nodes"].items():
            if node.get("metadata"):
                flag = False
                break
        return flag

    def set_node_index(self):
        """Set index for all nodes
        This index will be used to construct the sparse matrix.
        """
        i = 0
        ordered_nodes = []
        for name, node in self.nodes.items():
            node["index"] = i
            i += 1
            ordered_nodes.append(name)
        self.ordered_nodes = ordered_nodes

    def build_graph(self, non_to_nodes=[], non_from_nodes=[], ctrl_link=[]):
        """Build Compressed Sparse Row matrix

        1) special care for control nodes.

        Args:
            non_to_nodes (list, optional): link to these nodes will be ingored.
                Defaults to [].
            non_from_nodes (list, optional): link from these nodes will be ingored.
            Defaults to [].
        """
        from scipy.sparse import csr_matrix

        row = []
        col = []
        data = []
        for link in self.links:
            if link["to_node"] in non_to_nodes:
                continue
            if link["from_node"] in non_from_nodes:
                continue
            row.append(self.nodes[link["from_node"]]["index"])
            col.append(self.nodes[link["to_node"]]["index"])
            data.append(1)
        # control links
        for i in ctrl_link:
            link = self.ctrl_links[i]
            if link["to_node"] in non_to_nodes:
                continue
            if link["from_node"] in non_from_nodes:
                continue
            row.append(self.nodes[link["from_node"]]["index"])
            col.append(self.nodes[link["to_node"]]["index"])
            data.append(1)
        graph = csr_matrix((data, (row, col)), shape=(self.nnode, self.nnode))
        self.graph = graph
        return graph

    def build_children(self):
        """Build lists of child nodes for all nodes.
        #TODO find a better algorithm.
        """
        child_node = {}
        control_node = {}
        graph = self.build_graph()
        for name, node in self.nodes.items():
            child_node[name] = self.get_connected_nodes(graph=graph, start_node=name)
            control_node[name] = self.build_children_control(name, node)
        return child_node, control_node

    def build_children_scatter(self, name, node):
        """Find child nodes for scatter node."""
        non_from_nodes = []
        # print("socket: ", self.inputs[name])
        if "Stop" in self.inputs[name]:
            non_from_nodes.extend(self.inputs[name]["Stop"])
        graph = self.build_graph(non_from_nodes=non_from_nodes)
        # print("graph: ", graph)
        children = self.get_connected_nodes(graph=graph, start_node=name)
        return children

    def build_children_control(self, name, node):
        """Find child nodes for control node."""
        non_from_nodes = []
        # all nodes have a control links back to this node will used as a stop nodes
        # so that their child nodes will not be considered.
        for socket in self.ctrl_inputs[name]:
            non_from_nodes.extend(self.ctrl_inputs[name][socket])
        children = {}
        # print("node: ", node)
        # print("non_from_nodes: ", non_from_nodes)
        for socket in self.ctrl_outputs[name].keys():
            if socket == "exit":
                continue
            ctrl_output_links = self.ctrl_output_links[name].get(socket, [])
            graph = self.build_graph(
                non_from_nodes=non_from_nodes, ctrl_link=ctrl_output_links
            )
            # print("graph: ", graph)
            children[socket] = self.get_connected_nodes(graph=graph, start_node=name)
        return children

    def get_connected_nodes(self, graph=None, start_node=None):
        """Get subgraph start from "start_node"

        Args:
            graph (_type_, optional): _description_. Defaults to None.
            start_node (str, optional): _description_. name of start node.

        Returns:
            all_children_nodes (dict): _description_
        """
        from scipy.sparse.csgraph import breadth_first_order

        if graph is None:
            graph = self.graph
        # print(graph)
        i_start = self.nodes[start_node]["index"]
        node_array = breadth_first_order(
            csgraph=graph,
            i_start=i_start,
            directed=True,
            return_predecessors=False,
        )
        # print(graph)
        # print(start_node, i_start)
        # print(node_array)
        all_children_nodes = [self.ordered_nodes[i] for i in node_array[1:]]
        return all_children_nodes

    def build_connectivity(self):
        """Build connectivity.
        1) children
        2) inputs

        Returns:
            _type_: _description_
        """
        child_node, control_node = self.build_children()
        connectivity = {
            "child_node": child_node,
            "control_node": control_node,
            "input_node": self.inputs,
            "output_node": self.outputs,
            "ctrl_input_node": self.ctrl_inputs,
            "ctrl_input_link": self.ctrl_input_links,
            "ctrl_output_node": self.ctrl_outputs,
            "ctrl_output_link": self.ctrl_output_links,
        }
        return connectivity


class DifferenceAnalysis:
    """Analyze the difference between two node graphs.
    1) new nodes
    2) change node input socket

    Note:
    If you want to change node property, please reset the node first.
    """

    def __init__(self, nt1=None, nt2=None) -> None:
        """
        Args:
            nt1 (dict): NodeGraph data
            nt2 (dict): NodeGraph data
        """
        self.nt1 = nt1
        self.nt2 = nt2
        nodes1 = self.nt1["nodes"].keys()
        nodes2 = self.nt2["nodes"].keys()
        self.intersection = set(nodes2).intersection(set(nodes1))
        self.new_nodes = set(nodes2) - set(nodes1)

    def check_node_uuid(self):
        """Find new and modified nodes based on uuid."""
        # new node
        # modified node
        modified = set()
        for name in self.intersection:
            if self.nt2["nodes"][name]["uuid"] != self.nt1["nodes"][name]["uuid"]:
                modified.add(name)
        return set(modified)

    def check_property(self):
        """check property"""
        modified = set()
        for name in self.intersection:
            inputs1 = self.nt1["nodes"][name]["properties"]
            inputs2 = self.nt2["nodes"][name]["properties"]
            for key in inputs1:
                try:
                    if inputs1[key]["value"] != inputs2[key]["value"]:
                        print(f"key {key} changes")
                        modified.add(name)
                except Exception as e:
                    pass
                # value is a array
                try:
                    if not (inputs1[key]["value"] == inputs2[key]["value"]).all():
                        print(f"key {key} changes")
                        modified.add(name)
                except Exception as e:
                    pass
        return set(modified)

    def check_socket(self):
        """Find new and modified nodes based on input."""
        # new node
        nc1 = ConnectivityAnalysis(self.nt1)
        nc2 = ConnectivityAnalysis(self.nt2)
        modified_input = set()
        for name in self.intersection:
            sockets1 = set(nc1.inputs[name].keys())
            sockets2 = set(nc2.inputs[name].keys())
            if sockets2 != sockets1:
                modified_input.add(name)
                continue
            for socket in sockets1:
                nodes1 = set(nc1.inputs[name][socket])
                nodes2 = set(nc2.inputs[name][socket])
                if nodes2 != nodes1:
                    modified_input.add(name)
                    break
        return set(modified_input)

    def check_node_metadata(self):
        """Check the node metadata.
        This data will not affect the calculation of the node.
        e.g. position, description
        """
        # update position node
        modified = set()
        for name in self.intersection:
            for key in ["position", "description"]:
                if self.nt2["nodes"][name][key] != self.nt1["nodes"][name][key]:
                    modified.add(name)
        return set(modified)

    def build_difference(self):
        """Build difference.
        1) children
        2) inputs
        Returns:
            _type_: _description_
        """
        self.modified_nodes = set()
        self.modified_nodes.update(self.check_node_uuid())
        self.modified_nodes.update(self.check_property())
        modified_input = self.check_socket()
        self.modified_nodes.update(modified_input)
        self.update_metadata = self.check_node_metadata()
        # print("new_nodes: ", self.new_nodes)
        # print("modified_nodes: ", self.modified_nodes)
        return (
            self.new_nodes,
            self.modified_nodes,
            self.update_metadata,
        )
