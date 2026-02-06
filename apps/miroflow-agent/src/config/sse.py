from typing import Literal, TypedDict


class Config(TypedDict):
    name: str
    kind: Literal["sse"]
    url: str


def hydrate_mcp_client_with_sse_transport(tool_list: list[str]) -> list[Config]:
    """
    assert all(tool.endswith("-sse") for tool in tool_list)
    """
    configs: list[Config] = []
    # for tool_name in tool_list:
    #     if tool_name == "tool-google-search-sse":
    #         config = Config(name=tool_name, kind="sse", url="whatever")
    #     else:
    #         print("not supported")
    #         continue
    #     configs.append(config)

    return configs
