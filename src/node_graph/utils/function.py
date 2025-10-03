from __future__ import annotations

from typing import Any
import inspect

__all__ = ["prepare_function_inputs", "is_function_like"]


def is_function_like(obj: Any) -> bool:
    return inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isbuiltin(obj)


def prepare_function_inputs(func, *call_args, **call_kwargs):
    """Prepare inputs from a callable's signature and provided args/kwargs.

    - POSITIONAL_ONLY and POSITIONAL_OR_KEYWORD are consumed from *call_args
    - VAR_POSITIONAL (*args) not supported (raises)
    - Existing **call_kwargs win over args
    """
    inputs = dict(call_kwargs or {})
    if func is not None:
        arguments = list(call_args)
        orginal_func = func._callable if hasattr(func, "_callable") else func
        for name, parameter in inspect.signature(orginal_func).parameters.items():
            if parameter.kind in [
                parameter.POSITIONAL_ONLY,
                parameter.POSITIONAL_OR_KEYWORD,
            ]:
                try:
                    inputs[name] = arguments.pop(0)
                except IndexError:
                    pass
            elif parameter.kind is parameter.VAR_POSITIONAL:
                # not supported
                raise ValueError("VAR_POSITIONAL is not supported.")
    return inputs
