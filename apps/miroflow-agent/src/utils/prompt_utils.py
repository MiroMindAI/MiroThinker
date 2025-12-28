# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

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
    template += """
# General Objective

You accomplish a given task iteratively, breaking it down into clear steps and working through them methodically.

"""

    return template


def generate_no_mcp_system_prompt(date):
    formatted_date = date.strftime("%Y-%m-%d")

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
    return template


def generate_agent_specific_system_prompt(agent_type=""):
    if agent_type == "main":
        system_prompt = """\n
# Agent Specific Objective

You are a task-solving agent that uses tools step-by-step to answer the user's question. Your goal is to provide complete, accurate and well-reasoned answers using additional tools.

"""
    elif agent_type == "agent-browsing" or agent_type == "browsing-agent":
        system_prompt = """# Agent Specific Objective

You are an agent that performs the task of searching and browsing the web for specific information and generating the desired answer. Your task is to retrieve reliable, factual, and verifiable information that fills in knowledge gaps.
Do not infer, speculate, summarize broadly, or attempt to fill in missing parts yourself. Only return factual content.
"""
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
    return system_prompt.strip()


def generate_agent_summarize_prompt(task_description, agent_type=""):
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
            "Do NOT include any invisible or non-printable characters in the answer output.\n\n"
            "You must absolutely not perform any MCP tool call, tool invocation, search, scrape, code execution, or similar actions.\n"
            "You can only answer the original question based on the information already retrieved and your own internal knowledge.\n"
            "If you attempt to call any tool, it will be considered a mistake."
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
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return summarize_prompt.strip()
