from node_graph import Graph
from pathlib import Path
import yaml


def test_export_yaml(ng):
    """Test yaml"""
    ng.name = "test_export_yaml"
    s = ng.to_yaml()
    ntdata = yaml.safe_load(s)
    assert len(ntdata["tasks"]) == 6


def test_load_yaml_file():
    """Test yaml"""
    yaml_path = Path(__file__).parent / "datas" / "test_yaml.yaml"
    ng = Graph.from_yaml(str(yaml_path))
    assert len(ng.tasks) == 5
    assert ng.tasks.float1.inputs.value.value == 2.0
    assert ng.tasks.add1.inputs.y.value == 3.0
