# Copyright 2025 Miromind.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os

mcp_tags = [
    "<use_mcp_tool>",
    "</use_mcp_tool>",
    "<server_name>",
    "</server_name>",
    "<arguments>",
    "</arguments>",
]

refusal_keywords = [
    "time constraint",
    "I’m sorry, but I can’t",
    "I'm sorry, I cannot solve",
]


def generate_mcp_system_prompt(date, mcp_servers):
    formatted_date = date.strftime("%Y-%m-%d")

    # Start building the template, now follows https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview#tool-use-system-prompt
    template = f"""In this environment you have access to a set of tools you can use to answer the user's question. 

You only have access to the tools provided below. You can only use one tool per message, and will receive the result of that tool in the user's next response. You use tools step-by-step to accomplish a given task, with each tool-use informed by the result of the previous tool-use. Today is: {formatted_date}

# Tool-Use Formatting Instructions 

Tool-use is formatted using XML-style tags. The tool-use is enclosed in <use_mcp_tool></use_mcp_tool> and each parameter is similarly enclosed within its own set of tags.

The Model Context Protocol (MCP) connects to servers that provide additional tools and resources to extend your capabilities. You can use the server's tools via the `use_mcp_tool`.

Description: 
Request to use a tool provided by a MCP server. Each MCP server can provide multiple tools with different capabilities. Tools have defined input schemas that specify required and optional parameters.

Parameters:
- server_name: (required) The name of the MCP server providing the tool
- tool_name: (required) The name of the tool to execute
- arguments: (required) A JSON object containing the tool's input parameters, following the tool's input schema, quotes within string must be properly escaped, ensure it's valid JSON

Usage:
<use_mcp_tool>
<server_name>server name here</server_name>
<tool_name>tool name here</tool_name>
<arguments>
{{
"param1": "value1",
"param2": "value2 \\"escaped string\\""
}}
</arguments>
</use_mcp_tool>

Important Notes:
- Tool-use must be placed **at the end** of your response, **top-level**, and not nested within other tags.
- Always adhere to this format for the tool use to ensure proper parsing and execution.

String and scalar parameters should be specified as is, while lists and objects should use JSON format. Note that spaces for string values are not stripped. The output is not expected to be valid XML and is parsed with regular expressions.
Here are the functions available in JSONSchema format:

"""
    use_cn_prompt = os.getenv("USE_CN_PROMPT", "0")
    if use_cn_prompt == "1":
        template = f"""在此环境中，你可以使用一组工具来回答用户的问题。 

你只能使用下面提供的工具。每条消息只能使用一个工具，并且会在用户的下一条回复中收到该工具的结果。你需要按照“逐步”方式使用工具，每次使用工具都应基于上一步的结果。今天的日期是：{formatted_date}

# 工具使用格式说明

工具调用采用 XML 风格的标签格式。工具调用用 <use_mcp_tool></use_mcp_tool> 包裹，每个参数也需要用各自的标签包裹。

模型上下文协议（MCP）可以连接到提供额外工具和资源的服务器，从而扩展你的能力。你可以通过 `use_mcp_tool` 使用服务器提供的工具。

说明：
请求使用 MCP 服务器提供的工具。每个 MCP 服务器可以提供多个具备不同功能的工具。工具有定义好的输入模式（input schema），用来指定必填和可选参数。

参数：
- server_name：（必填）提供工具的 MCP 服务器名称
- tool_name：（必填）要执行的工具名称
- arguments：（必填）一个 JSON 对象，包含该工具的输入参数。需要符合工具的输入模式；字符串中的引号必须正确转义，确保 JSON 有效。

用法示例：
<use_mcp_tool>
<server_name>这里写服务器名称</server_name>
<tool_name>这里写工具名称</tool_name>
<arguments>
{{
"param1": "value1",
"param2": "value2 \\"已转义的字符串\\""
}}
</arguments>
</use_mcp_tool>

重要说明：
- 工具调用必须放在回复的**最后**，处于**顶层**，不能嵌套在其他标签里。
- 必须严格遵循该格式，以确保能够正确解析和执行。

字符串和基本参数可以直接写出；列表和对象则必须使用 JSON 格式。注意字符串值中的空格不会被自动去掉。输出结果不要求是合法 XML，而是通过正则表达式解析。

以下是可用的函数，使用 JSONSchema 格式表示：

"""

    # Add MCP servers section
    if mcp_servers and len(mcp_servers) > 0:
        for server in mcp_servers:
            template += f"\n## Server name: {server['name']}\n"

            if "tools" in server and len(server["tools"]) > 0:
                for tool in server["tools"]:
                    # Skip tools that failed to load (they only have 'error' key)
                    if "error" in tool and "name" not in tool:
                        continue
                    template += f"### Tool name: {tool['name']}\n"
                    template += f"Description: {tool['description']}\n"
                    template += f"Input JSON schema: {tool['schema']}\n"

    # Add the full objective system prompt
    if use_cn_prompt == "0":
        template += """
# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

"""
    else:
        template += """
# 总体目标

你需要通过迭代的方式完成给定任务，将其分解为清晰的步骤，并有条理地逐步解决。

"""

    return template


def generate_no_mcp_system_prompt(date):
    formatted_date = date.strftime("%Y-%m-%d")
    use_cn_prompt = os.getenv("USE_CN_PROMPT", "0")

    if use_cn_prompt == "0":
        # Start building the template, now follows https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview#tool-use-system-prompt
        template = """In this environment you have access to a set of tools you can use to answer the user's question. """

        template += f" Today is: {formatted_date}\n"

        template += """
Important Notes:
- Tool-use must be placed **at the end** of your response, **top-level**, and not nested within other tags.
- Always adhere to this format for the tool use to ensure proper parsing and execution.

String and scalar parameters should be specified as is, while lists and objects should use JSON format. Note that spaces for string values are not stripped. The output is not expected to be valid XML and is parsed with regular expressions.
"""

        # Add the full objective system prompt
        template += """
# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

"""
    else:
        template = """在此环境中，你可以使用一组工具来回答用户的问题。"""
        template += f" 今天的日期是：{formatted_date}\n"
        template += """
重要说明:
- 工具调用必须放在回复的**最后**，处于**顶层**，不能嵌套在其他标签里。
- 必须严格遵循该格式，以确保能够正确解析和执行。

字符串和基本参数可以直接写出；列表和对象则必须使用 JSON 格式。注意字符串值中的空格不会被自动去掉。输出结果不要求是合法 XML，而是通过正则表达式解析。
"""
        template += """
# 总体目标

你需要通过迭代的方式完成给定任务，将其分解为清晰的步骤，并有条理地逐步解决。

"""
    return template


def generate_agent_specific_system_prompt(agent_type=""):
    use_cn_prompt = os.getenv("USE_CN_PROMPT", "0")
    if agent_type == "main":
        if use_cn_prompt == "0":
            system_prompt = """\n
# Agent Specific Objective

You are a task-solving agent that uses tools step-by-step to answer the user's question. Your goal is to provide complete, accurate and well-reasoned answers using additional tools.

"""
        else:
            system_prompt = """\n
# 代理特定目标

你是一个任务解决型代理，会逐步使用工具来回答用户的问题。你的目标是借助额外工具，提供完整、准确且有理有据的答案。

"""

    elif agent_type == "agent-browsing" or agent_type == "browsing-agent":
        if use_cn_prompt == "0":
            system_prompt = """# Agent Specific Objective

You are an agent that performs the task of searching and browsing the web for specific information and generating the desired answer. Your task is to retrieve reliable, factual, and verifiable information that fills in knowledge gaps.
Do not infer, speculate, summarize broadly, or attempt to fill in missing parts yourself. Only return factual content.
"""
        else:
            system_prompt = """# 代理特定目标

你是一个代理，负责在网络上搜索和浏览特定信息，并生成所需的答案。你的任务是检索可靠、真实、可验证的信息，用来弥补知识空白。  
不要推断、不要猜测、不要宽泛总结，也不要自行补全缺失的部分。只返回事实内容。  
"""
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return system_prompt.strip()


def generate_agent_summarize_prompt(task_description, task_failed=False, agent_type=""):
    if agent_type == "main":
        summarize_prompt = (
            "Summarize the above conversation, and output the FINAL ANSWER to the original question.\n\n"
            "If a clear answer has already been provided earlier in the conversation, do not rethink or recalculate it — "
            "simply extract that answer and reformat it to match the required format below.\n"
            "If a definitive answer could not be determined, make a well-informed educated guess based on the conversation.\n\n"
            "The original question is repeated here for reference:\n\n"
            f'"{task_description}"\n\n'
            "Wrap your final answer in \\boxed{}.\n"
            "Your final answer should be:\n"
            "- a number, OR\n"
            "- as few words as possible, OR\n"
            "- a comma-separated list of numbers and/or strings.\n\n"
            "ADDITIONALLY, your final answer MUST strictly follow any formatting instructions in the original question — "
            "such as alphabetization, sequencing, units, rounding, decimal places, etc.\n"
            "If you are asked for a number, express it numerically (i.e., with digits rather than words), don't use commas, and DO NOT INCLUDE UNITS such as $ or USD or percent signs unless specified otherwise.\n"
            "If you are asked for a string, don't use articles or abbreviations (e.g. for cities), unless specified otherwise. Don't output any final sentence punctuation such as '.', '!', or '?'.\n"
            "If you are asked for a comma-separated list, apply the above rules depending on whether the elements are numbers or strings.\n"
            "Do NOT include any punctuation such as '.', '!', or '?' at the end of the answer.\n"
            "Do NOT include any invisible or non-printable characters in the answer output."
        )
        use_cn_prompt = os.getenv("USE_CN_PROMPT", "0")
        if use_cn_prompt == "1":
            summarize_prompt = (
                "请总结以上对话，并输出对原始问题的【最终答案】。\n\n"
                "如果在对话中已经给出了清晰的答案，请不要重新思考或重新计算——"
                "只需提取该答案，并将其重新格式化为符合下述要求的形式。\n"
                "如果无法确定唯一答案，请基于对话内容作出合理的推测。\n\n"
                "原始问题在此重述，供你参考：\n\n"
                f'"{task_description}"\n\n'
                "请将你的最终答案包裹在 \\boxed{} 中。\n"
                "最终答案必须是以下格式之一：\n"
                "- 一个数字，或\n"
                "- 尽可能少的词语，或\n"
                "- 一个由逗号分隔的数字和/或字符串列表。\n\n"
                "此外，你的最终答案必须严格遵循原始问题中的格式要求——"
                "例如字母顺序、排列顺序、单位、四舍五入、保留小数位等。\n"
                "如果问题要求给出数字，请直接用阿拉伯数字表示，不要写成文字，不要使用千分位逗号，也不要包含任何单位符号（如 $、USD、%），除非问题中明确要求。\n"
                "如果问题要求给出字符串，请不要加冠词或缩写（例如城市名），除非问题中明确要求。答案结尾不要使用任何句号（.）、感叹号（!）、问号（?）。\n"
                "如果问题要求给出逗号分隔的列表，请根据元素是数字还是字符串分别应用以上规则。\n"
                "不要在答案输出中包含任何标点（如 .、!、?）结尾，也不要包含任何不可见或不可打印的字符。"
            )
    elif agent_type == "agent-browsing":
        summarize_prompt = (
            "This is a direct instruction to you (the assistant), not the result of a tool call.\n\n"
            "We are now ending this session, and your conversation history will be deleted. "
            "You must NOT initiate any further tool use. This is your final opportunity to report "
            "*all* of the information gathered during the session.\n\n"
            "The original task is repeated here for reference:\n\n"
            f'"{task_description}"\n\n'
            "Summarize the above search and browsing history. Output the FINAL RESPONSE and detailed supporting information of the task given to you.\n\n"
            "If you found any useful facts, data, quotes, or answers directly relevant to the original task, include them clearly and completely.\n"
            "If you reached a conclusion or answer, include it as part of the response.\n"
            "If the task could not be fully answered, do NOT make up any content. Instead, return all partially relevant findings, "
            "Search results, quotes, and observations that might help a downstream agent solve the problem.\n"
            "If partial, conflicting, or inconclusive information was found, clearly indicate this in your response.\n\n"
            "Your final response should be a clear, complete, and structured report.\n"
            "Organize the content into logical sections with appropriate headings.\n"
            "Do NOT include any tool call instructions, speculative filler, or vague summaries.\n"
            "Focus on factual, specific, and well-organized information."
        )
        use_cn_prompt = os.getenv("USE_CN_PROMPT", "0")
        if use_cn_prompt == "1":
            summarize_prompt = (
                "这是对你的直接指令（面向助理），不是工具调用的结果。\n\n"
                "我们现在将结束本次会话，你的对话历史将被删除。你不得再发起任何工具调用。这是你最后一次机会报告本次会话中收集到的*所有*信息。\n\n"
                "原始任务在此重述，供你参考：\n\n"
                f'"{task_description}"\n\n'
                "请总结以上搜索和浏览记录。输出任务的【最终回复】以及详细的支持信息。\n\n"
                "如果你发现了任何有用的事实、数据、引用或与原始任务直接相关的答案，请清晰完整地包含在内。\n"
                "如果你得出了结论或答案，请将其写入报告。\n"
                "如果任务未能完全回答，请不要编造内容。相反，请返回所有部分相关的发现、搜索结果、引用和观察，这些可能帮助后续的智能体解决问题。\n"
                "如果你发现的信息是部分的、相互矛盾的或不确定的，请在报告中明确指出。\n\n"
                "你的最终回复应当是一个清晰、完整、结构化的报告。\n"
                "请将内容组织成逻辑清晰的章节，并配上合适的小标题。\n"
                "不要包含任何工具调用指令、模糊的总结或无根据的推测。\n"
                "请专注于事实、具体内容和有条理的组织。"
            )
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return summarize_prompt.strip()
