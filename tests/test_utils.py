from node_graph.utils import validate_socket_data


def test_validate_socket_data():
    """Test the validate_socket_data function to ensure it correctly validates socket data."""
    input_list = ["sum", "diff"]
    result = validate_socket_data(input_list)
    assert result == {"sum": {}, "diff": {}}
