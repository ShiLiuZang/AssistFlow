from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from jsonschema import Draft202012Validator
from referencing import Registry as RefRegistry
from typing import Literal

@dataclass(frozen=True)
class ToolSpec:
    name: str
    invoke: Callable
    description: str
    schema: dict
    permission: Literal["read", "write"] = "read"

class Registry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        Draft202012Validator.check_schema(spec.schema)
        if not spec.name.strip():
            raise ValueError("工具名称不能为空")
        if spec.name in self._specs:
            raise ValueError(f"工具已注册：{spec.name}")
        if not spec.description.strip():
            raise ValueError("工具的描述不能为空")
        if not isinstance(spec.schema, dict) or spec.schema.get("type") != "object":
            raise ValueError("工具参数 Schema 必须是对象")
        if spec.schema.get("additionalProperties") is not False:
            raise ValueError("工具参数 Schema 必须禁止额外字段")
        if spec.permission not in {"read", "write"}:
            raise ValueError("工具权限必须是 read 或 write")
        self._specs[spec.name] = replace(spec, schema=deepcopy(spec.schema))

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def model_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": deepcopy(spec.schema),
                },
            }
            for spec in self._specs.values()
        ]

    def execution_tools(self) -> dict[str, Callable]:
        return {
            name: spec.invoke
            for name, spec in self._specs.items()
        }


def validate_args(spec: ToolSpec, args: object) -> None:
    Draft202012Validator(
        spec.schema,
        registry=RefRegistry(),
    ).validate(args)
