from node_graph.analysis import NodeGraphAnalysis


def test_get_input_output_links(ng_complex):
    ng = ng_complex
    analysis = NodeGraphAnalysis(ng)

    # n1 has no incoming links, 1 outgoing link to n2
    in_links_n1 = analysis.get_input_links(ng.nodes.n1)
    out_links_n1 = analysis.get_output_links(ng.nodes.n1)
    assert len(in_links_n1) == 0
    assert len(out_links_n1) == 3
    assert out_links_n1[0] == ng.nodes.n2.name

    in_links_n3 = analysis.get_input_links(ng.nodes.n3)
    out_links_n3 = analysis.get_output_links(ng.nodes.n3)
    assert len(in_links_n3) == 1
    assert in_links_n3[0] == ng.nodes.n1.name
    assert len(out_links_n3) == 2
    assert out_links_n3[0] == ng.nodes.n4.name

    in_links_n5 = analysis.get_input_links(ng.nodes.n5)
    out_links_n5 = analysis.get_output_links(ng.nodes.n5)
    assert len(in_links_n5) == 2
    assert in_links_n5[0] == ng.nodes.n3.name
    assert len(out_links_n5) == 0


def test_get_direct_children(ng_complex):
    ng = ng_complex
    analysis = NodeGraphAnalysis(ng)
    assert analysis.get_direct_children(ng.nodes.n1) == [
        ng.nodes.n2.name,
        ng.nodes.n3.name,
        ng.nodes.n4.name,
    ]
    assert analysis.get_direct_children(ng.nodes.n2) == []
    assert analysis.get_direct_children(ng.nodes.n3) == [
        ng.nodes.n4.name,
        ng.nodes.n5.name,
    ]


def test_get_all_descendants(ng_complex):
    ng = ng_complex
    analysis = NodeGraphAnalysis(ng)
    desc_n1 = analysis.get_all_descendants(ng.nodes.n1)
    assert set(desc_n1) == {
        ng.nodes.n2.name,
        ng.nodes.n3.name,
        ng.nodes.n4.name,
        ng.nodes.n5.name,
    }

    desc_n3 = analysis.get_all_descendants(ng.nodes.n3)
    assert set(desc_n3) == {ng.nodes.n4.name, ng.nodes.n5.name}

    desc_n5 = analysis.get_all_descendants(ng.nodes.n5)
    assert desc_n5 == []


def test_compare_graphs_no_diff(ng_complex):
    """
    Two identical graphs => no added/removed/changed nodes
    """
    ng1 = ng_complex
    ng2 = ng_complex  # Same structure

    diff = NodeGraphAnalysis.compare_graphs(ng1, ng2)
    assert diff["added_nodes"] == []
    assert diff["removed_nodes"] == []
    assert diff["modified_nodes"] == []


def test_compare_graphs_with_changes(ng_complex, func_with_namespace_socket):
    """
    Make some changes in graph2:
      - add a new node
      - change input links of an existing node
      - change input socket value
    """
    ng1 = ng_complex
    ng2 = ng_complex.copy()

    # 1) Add a new node in ng2
    ng2.add_node(func_with_namespace_socket, name="extra_node")
    ng2.add_link(ng2.nodes.n2.outputs.sum, ng2.nodes.extra_node.inputs.a)

    # 2) Change the input link of node "n4"
    # we need to remove the old link from n1->n4
    old_link = [
        lk for lk in ng2.links if lk.to_node.name == "n4" and lk.from_node.name == "n1"
    ][0]
    del ng2.links[old_link.name]
    ng2.add_link(ng2.nodes.n2.outputs.sum, ng2.nodes.n4.inputs.a)

    # 3) Change an input socket value on n5
    ng2.nodes.n3.inputs.a.value = 999

    diff = NodeGraphAnalysis.compare_graphs(ng1, ng2)
    print("diff", diff)
    # "extra_node" is new
    assert "extra_node" in diff["added_nodes"]
    assert diff["removed_nodes"] == []
    assert "n3" in diff["modified_nodes"]
    assert "n4" in diff["modified_nodes"]
    # n1 not changed
    assert "n1" not in diff["modified_nodes"]


def test_zone(ng_with_zone):
    """
    Two identical graphs => no added/removed/changed nodes
    """
    analysis = NodeGraphAnalysis(ng_with_zone)
    zones = analysis.build_zone()
    assert zones["zone1"]["input_tasks"] == ["n1"]
    assert zones["zone2"]["input_tasks"] == ["zone1"]
    assert zones["n3"]["input_tasks"] == ["zone1"]
    assert zones["n5"]["input_tasks"] == ["zone2"]
