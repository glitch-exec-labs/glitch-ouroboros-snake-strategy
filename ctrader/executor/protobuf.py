"""
Vendored from spotware/OpenApiPy (MIT licence).
Source: https://github.com/spotware/OpenApiPy/blob/main/ctrader_open_api/protobuf.py
Commit: main branch, April 2026.

Adaptation: relative imports replaced with absolute paths so this module
works outside the ctrader_open_api package. Logic is otherwise unchanged.
To update: diff against upstream and re-apply this header + import change.
"""
import re


class Protobuf:
    _protos = dict()
    _names = dict()
    _abbr_names = dict()

    @classmethod
    def populate(cls):
        from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as o1
        from ctrader_open_api.messages import OpenApiMessages_pb2 as o2

        for name in dir(o1) + dir(o2):
            if not name.startswith("Proto"):
                continue

            m = o1 if hasattr(o1, name) else o2
            klass = getattr(m, name)
            try:
                pt = klass().payloadType
            except Exception:
                continue
            cls._protos[pt] = klass
            cls._names[klass.__name__] = pt
            abbr_name = re.sub(r'^Proto(OA)?(.*)', r'\2', klass.__name__)
            cls._names[abbr_name] = pt
        return cls._protos

    @classmethod
    def get(cls, payload, fail=True, **params):
        if not cls._protos:
            cls.populate()

        if payload in cls._protos:
            return cls._protos[payload](**params)

        for d in [cls._names, cls._abbr_names]:
            if payload in d:
                payload = d[payload]
                return cls._protos[payload](**params)

        if fail:
            raise IndexError("Invalid payload: " + str(payload))
        return None

    @classmethod
    def get_type(cls, payload) -> int:
        """Return the integer payloadType for a message name or type."""
        return cls.get(payload).payloadType

    @classmethod
    def extract(cls, message):
        """Deserialise a ProtoMessage wrapper into its inner proto message."""
        payload = cls.get(message.payloadType)
        payload.ParseFromString(message.payload)
        return payload
