from node_graph import NodeGraph
import yaml


def test_export_yaml(ng):
    """Test yaml"""
    ng.name = "test_export_yaml"
    s = ng.to_yaml()
    ntdata = yaml.safe_load(s)
    assert len(ntdata["nodes"]) == 3


def test_load_yaml_file():
    """Test yaml"""
    ng = NodeGraph.from_yaml("datas/test_yaml.yaml")
    assert len(ng.nodes) == 2
    assert ng.nodes.float1.properties.value.value == 2.0
    assert ng.nodes.add1.inputs.y.socket_value == 3.0
