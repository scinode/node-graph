from IPython.display import IFrame


def test_workgraph_widget(ng):
    """Save the workgraph"""
    value = ng.to_widget_value()
    assert len(value["nodes"]) == 3
    assert len(value["links"]) == 2
    # to_html
    data = ng.to_html()
    assert isinstance(data, IFrame)


def test_workgraph_task(ng):
    """Save the workgraph"""
    value = ng.nodes["add1"].to_widget_value()
    assert len(value["nodes"]) == 1
    assert len(value["nodes"]["add1"]["inputs"]) == len(ng.nodes["add1"].inputs)
    assert len(value["links"]) == 0
    # to html
    data = ng.nodes["add1"].to_html()
    assert isinstance(data, IFrame)
