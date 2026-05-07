"""
Supervisor Package
总控Agent包
"""

from .agent import SupervisorAgent, SupervisorState
from .prompts import (
    SUPERVISOR_SYSTEM_PROMPT,
    TASK_ANALYSIS_PROMPT,
    RESULT_INTEGRATION_PROMPT,
    ERROR_HANDLING_PROMPT
)

__all__ = [
    'SupervisorAgent',
    'SupervisorState',
    'SUPERVISOR_SYSTEM_PROMPT',
    'TASK_ANALYSIS_PROMPT',
    'RESULT_INTEGRATION_PROMPT',
    'ERROR_HANDLING_PROMPT'
]
