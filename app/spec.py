import keyword
import re

from pydantic import BaseModel, Field, field_validator, model_validator


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")
_SERVER = re.compile(r"[a-z][a-z0-9-]{1,40}")


class InputField(BaseModel):
    name: str = Field(min_length=1, description="Argument name the generated tool will require. A short identifier, such as city.")
    type: str = Field(description="JSON type of that argument: string, number, or boolean.")

    @field_validator("name")
    @classmethod
    def input_name(cls, value: str) -> str:
        if not _IDENT.fullmatch(value):
            raise ValueError("input name must be a short identifier")
        if keyword.iskeyword(value):
            raise ValueError("input name cannot be a Python keyword")
        return value

    @field_validator("type")
    @classmethod
    def input_type(cls, value: str) -> str:
        if value not in {"string", "number", "boolean"}:
            raise ValueError("type must be string, number, or boolean")
        return value


class ToolIn(BaseModel):
    name: str = Field(min_length=1, description="Tool name the MCP client will call. A short identifier, such as add_note.")
    purpose: str = Field(min_length=1, max_length=200, description="One line shown as the tool description. The generated stub returns this text plus the arguments.")
    inputs: list[InputField] = Field(default_factory=list, description="Arguments the tool requires. An empty list means the tool takes no arguments.")

    @field_validator("name")
    @classmethod
    def tool_name(cls, value: str) -> str:
        if not _IDENT.fullmatch(value):
            raise ValueError("tool name must be a short identifier")
        if keyword.iskeyword(value):
            raise ValueError("tool name cannot be a Python keyword")
        return value

    @model_validator(mode="after")
    def unique_inputs(self) -> "ToolIn":
        names = [item.name for item in self.inputs]
        if len(names) != len(set(names)):
            raise ValueError("input names must be unique")
        return self


class SpecIn(BaseModel):
    server_name: str = Field(min_length=2, description="Folder name inside the zip, and the MCP server name. Lowercase letters, digits, and hyphens.")
    tools: list[ToolIn] = Field(min_length=1, description="At least one tool. A blank tool name is rejected.")

    @field_validator("server_name")
    @classmethod
    def server_name_ok(cls, value: str) -> str:
        if not _SERVER.fullmatch(value):
            raise ValueError("server name must be lowercase letters, digits, and hyphens")
        return value

    @model_validator(mode="after")
    def unique_tools(self) -> "SpecIn":
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("tool names must be unique")
        return self
