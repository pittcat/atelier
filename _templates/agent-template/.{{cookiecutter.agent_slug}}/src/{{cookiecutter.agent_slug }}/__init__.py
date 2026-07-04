"""{{ cookiecutter.agent_pascal }} 包入口。"""

from {{ cookiecutter.agent_slug }}.agent import agent

__all__ = ["agent"]
__version__ = "{{ cookiecutter.agent_version }}"
