import time
import numpy as np
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
