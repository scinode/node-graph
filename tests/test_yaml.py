from node_graph import NodeGraph
import yaml


def test_export_yaml(nt):
    """Test yaml"""
    nt.name = "test_export_yaml"
    s = nt.to_yaml()
    ntdata = yaml.safe_load(s)
    assert len(ntdata["nodes"]) == 3


def test_load_yaml_file():
    """Test yaml"""
    nt = NodeGraph.from_yaml("datas/test_yaml.yaml")
    assert len(nt.nodes) == 2
    assert nt.nodes["float1"].properties["value"].value == 2.0
    assert nt.nodes["add1"].inputs["y"].value == 3.0
