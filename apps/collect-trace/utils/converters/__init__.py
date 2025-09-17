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

from .convert_non_oai_to_chatml import (
    convert_to_json_chatml,
    extract_and_save_chat_history,
)
from .convert_oai_to_chatml import (
    extract_message_history_from_log,
    oai_tool_message_to_chat_message,
    process_log_file,
    save_chatml_to_files,
)
from .convert_to_chatml_auto_batch import (
    batch_process_files,
    determine_conversion_method,
    get_llm_provider,
    process_single_file,
)

__all__ = [
    # OAI conversion functions
    "oai_tool_message_to_chat_message",
    "extract_message_history_from_log",
    "save_chatml_to_files",
    "process_log_file",
    # Non-OAI conversion functions
    "convert_to_json_chatml",
    "extract_and_save_chat_history",
    # Auto batch conversion functions
    "get_llm_provider",
    "determine_conversion_method",
    "process_single_file",
    "batch_process_files",
]
