from typing import Any, Dict
import json
import pickle


class SerializeNone:
    def get_serialize(self) -> Dict[str, str]:
        serialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "serialize_none",
        }
        return serialize

    def get_deserialize(self) -> Dict[str, str]:
        deserialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "deserialize_none",
        }
        return deserialize


class SerializeJson:
    def get_serialize(self) -> Dict[str, str]:
        serialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "serialize_json",
        }
        return serialize

    def get_deserialize(self) -> Dict[str, str]:
        deserialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "deserialize_json",
        }
        return deserialize


class SerializePickle:
    def get_serialize(self) -> Dict[str, str]:
        serialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "serialize_pickle",
        }
        return serialize

    def get_deserialize(self) -> Dict[str, str]:
        deserialize: Dict[str, str] = {
            "path": "node_graph.serializer",
            "name": "deserialize_pickle",
        }
        return deserialize


def serialize_none(data: Any) -> Any:
    return data


def deserialize_none(data: Any) -> Any:
    return data


def serialize_json(data: Any) -> str:

    data = json.dumps(data)
    return data


def deserialize_json(data: str) -> Any:

    data = json.loads(data)
    return data


def serialize_pickle(data: Any) -> bytes:

    data = pickle.dumps(data)
    return data


def deserialize_pickle(data: bytes) -> Any:

    data = pickle.loads(data)
    return data
