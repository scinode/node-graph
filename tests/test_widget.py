from IPython.display import IFrame


def test_nodegraph_widget(ng):
    """Test the nodegraph widget"""
    value = ng.to_widget_value()
    print("value", value["nodes"].keys())
    assert len(value["nodes"]) == 6
    assert len(value["links"]) == 2
    # to_html
    data = ng.to_html()
    assert isinstance(data, IFrame)


def test_nodegraph_node(ng):
    """Test the node widget"""
    value = ng.nodes["add1"].to_widget_value()
    assert len(value["nodes"]) == 1
    assert len(value["nodes"]["add1"]["inputs"]) == len(ng.nodes["add1"].inputs)
    assert len(value["links"]) == 0
    # to html
    data = ng.nodes["add1"].to_html()
    assert isinstance(data, IFrame)
