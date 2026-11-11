"""Terminal UI interface for Skald, powered directly by Prism."""

from __future__ import annotations

from prism import (
    UI,
    Spinner,
    add_agent_args,
    add_color_args,
    apply_agent_args,
    apply_color_args,
    confirm_input,
    detect_color_support,
    get_agent_env,
    get_json_env,
    get_terminal_columns,
    handle_agent_args,
    handle_color_args,
    handle_version_arg,
    multiselect_menu,
    prompt_input,
    render_error_panel,
    render_help,
    render_panel,
    select_menu,
    spinner_context,
    strip_ansi,
    visual_len,
)

try:
    from prism import get_toon_env
except ImportError:
    get_toon_env = None  # type: ignore

ui = UI(app_name="skald", icon="🎙️", badge_color="1;36")

__all__ = [
    "ui",
    "UI",
    "Spinner",
    "spinner_context",
    "add_agent_args",
    "apply_agent_args",
    "handle_agent_args",
    "add_color_args",
    "apply_color_args",
    "handle_color_args",
    "handle_version_arg",
    "render_help",
    "render_panel",
    "render_error_panel",
    "prompt_input",
    "confirm_input",
    "select_menu",
    "multiselect_menu",
    "detect_color_support",
    "strip_ansi",
    "visual_len",
    "get_terminal_columns",
    "get_agent_env",
    "get_json_env",
]
