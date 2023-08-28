class SerializeNone:
    def get_serialize(self):
        serialize = {"path": "scinode.serialization.built_in", "name": "serialize_none"}
        return serialize

    def get_deserialize(self):
        deserialize = {
            "path": "scinode.serialization.built_in",
            "name": "deserialize_none",
        }
        return deserialize


class SerializeJson:
    def get_serialize(self):
        serialize = {
            "path": "scinode.serialization.built_in",
            "name": "serialize_json",
        }
        return serialize

    def get_deserialize(self):
        deserialize = {
            "path": "scinode.serialization.built_in",
            "name": "deserialize_json",
        }
        return deserialize


class SerializePickle:
    def get_serialize(self):
        serialize = {
            "path": "scinode.serialization.built_in",
            "name": "serialize_pickle",
        }
        return serialize

    def get_deserialize(self):
        deserialize = {
            "path": "scinode.serialization.built_in",
            "name": "deserialize_pickle",
        }
        return deserialize


def serialize_none(data):
    return data


def deserialize_none(data):
    return data


def serialize_json(data):
    import json

    data = json.dumps(data)
    return data


def deserialize_json(data):
    import json

    data = json.loads(data)
    return data


def serialize_pickle(data):
    import pickle

    data = pickle.dumps(data)
    return data


def deserialize_pickle(data):
    import pickle

    data = pickle.loads(data)
    return data
