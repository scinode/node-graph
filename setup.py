import pathlib
from setuptools import setup, find_packages


def test_suite():
    import unittest

    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover("tests", pattern="test_*.py")
    return test_suite


# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

setup(
    name="node_graph",
    version="0.0.7",
    description="Create node-based workflow",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/scinode/node-graph",
    author="Xing Wang",
    author_email="xingwang1991@gmail.com",
    license="MIT License",
    classifiers=[],
    packages=find_packages(),
    entry_points={
        "node_graph.node": [
            "test = node_graph.nodes.test_nodes:node_list",
        ],
        "node_graph.socket": [
            "built_in = node_graph.sockets.builtin:socket_list",
        ],
        "node_graph.property": [
            "built_in = node_graph.properties.builtin:property_list",
        ],
    },
    install_requires=[
        "numpy",
        "click",
        "pyyaml",
        "colorama",
        "termcolor",
        "cloudpickle",
    ],
    package_data={},
    include_package_data=True,
    python_requires=">=3.9",
    test_suite="setup.test_suite",
)
