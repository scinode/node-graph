from node_graph import Graph
import yaml


def test_export_yaml(ng):
    """Test yaml"""
    ng.name = "test_export_yaml"
    s = ng.to_yaml()
    ntdata = yaml.safe_load(s)
    assert len(ntdata["tasks"]) == 6


def test_load_yaml_file():
    """Test yaml"""
    ng = Graph.from_yaml("datas/test_yaml.yaml")
    assert len(ng.tasks) == 5
    assert ng.tasks.float1.inputs.value.value == 2.0
    assert ng.tasks.add1.inputs.y.value == 3.0
