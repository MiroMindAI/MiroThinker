from typing import Literal, TypedDict


class Config(TypedDict):
    name: str
    kind: Literal["streamable_http"]
    url: str


def hydrate_mcp_client_with_streamable_http(tool_list: list[str]) -> list[Config]:
    """
    assert all(tool.endswith("-http") for tool in tool_list)
    """
    configs: list[Config] = []
    # for tool_name in tool_list:
    #     if tool_name == "tool-google-search-http":
    #         config = Config(name=tool_name, kind="streamable_http", url="whatever")
    #     else:
    #         print("not supported")
    #         continue
    #     configs.append(config)

    return configs
