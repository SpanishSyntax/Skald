"""Terminal UI interface for Skald, powered by Prism with fallback support."""

from __future__ import annotations

import sys
from typing import Any, Callable, Sequence

try:
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

    ui = UI(app_name="skald", icon="🎙️", badge_color="1;36")
except ImportError:
    # Graceful fallback if prism is not available in bare environments
    def detect_color_support() -> bool:
        return sys.stdout.isatty()

    def strip_ansi(text: str) -> str:
        import re
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    def visual_len(text: str) -> int:
        return len(strip_ansi(text))

    def get_terminal_columns() -> int:
        import shutil
        return shutil.get_terminal_size((80, 24)).columns

    def add_color_args(parser: Any) -> None:
        parser.add_argument(
            "--color",
            choices=["auto", "always", "never"],
            default="auto",
            help="Color output mode (default: auto)",
        )
        parser.add_argument(
            "--no-color",
            action="store_true",
            help="Disable color output",
        )

    def handle_color_args(args: Any) -> None:
        pass

    def apply_color_args(args: Any) -> None:
        pass

    def handle_version_arg(parser: Any, version: str) -> None:
        parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {version}")

    def add_agent_args(parser: Any) -> None:
        parser.add_argument("-A", "--agent", action="store_true", help="Agent output mode")
        parser.add_argument("--json", action="store_true", help="JSON output mode")

    def handle_agent_args(args: Any) -> None:
        pass

    def apply_agent_args(args: Any) -> None:
        pass

    def render_panel(
        title: str,
        lines: Sequence[str] | str,
        border_color: str = "0;36",
        width: int = 76,
        styler: Any = None,
        stream: Any = None,
    ) -> None:
        out = stream or sys.stdout
        body_lines = lines.splitlines() if isinstance(lines, str) else list(lines)
        box_w = min(width, max(36, get_terminal_columns() - 2))
        inner_w = box_w - 4
        title_clean = strip_ansi(title)
        title_seg = f" {title} " if title else ""
        top_fill = max(1, box_w - 3 - len(title_clean) - (2 if title else 0))
        top = f"\033[{border_color}m╭─\033[0m{f'\033[1m{title_seg}\033[0m' if title else ''}\033[{border_color}m{'─' * top_fill}╮\033[0m"
        bottom = f"\033[{border_color}m╰{'─' * (box_w - 2)}╯\033[0m"
        side = f"\033[{border_color}m│\033[0m"
        print(top, file=out)
        for raw_line in body_lines:
            vis = visual_len(raw_line)
            if vis <= inner_w:
                pad = " " * (inner_w - vis)
                print(f"{side} {raw_line}{pad} {side}", file=out)
            else:
                plain = strip_ansi(raw_line)
                clipped = plain[: max(0, inner_w - 3)] + "..."
                pad = " " * max(0, inner_w - len(clipped))
                print(f"{side} {clipped}{pad} {side}", file=out)
        print(bottom, file=out)

    def render_error_panel(
        title: str,
        lines: Sequence[str] | str,
        styler: Any = None,
        stream: Any = None,
    ) -> None:
        out = stream or sys.stderr
        styled_title = f"\033[1;31m✘ {title}\033[0m"
        render_panel(title=styled_title, lines=lines, border_color="1;31", stream=out)

    def prompt_input(message: str, default: str = "", **kwargs: Any) -> str:
        prompt_str = f"{message} [{default}]: " if default else f"{message}: "
        try:
            val = input(prompt_str).strip()
            return val or default
        except (EOFError, KeyboardInterrupt):
            return default

    def confirm_input(message: str, default: bool = False, **kwargs: Any) -> bool:
        hint = "Y/n" if default else "y/N"
        try:
            val = input(f"{message} ({hint}): ").strip().lower()
            if not val:
                return default
            return val in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return default

    def select_menu(title: str, options: Sequence[Any], default_index: int = 0, **kwargs: Any) -> str:
        items = []
        for opt in options:
            if isinstance(opt, (list, tuple)):
                items.append((str(opt[0]), str(opt[1])))
            else:
                items.append((str(opt), str(opt)))
        if not items:
            return ""
        print(f"\n\033[1m{title}\033[0m")
        for idx, (k, lbl) in enumerate(items, 1):
            print(f"  {idx}) {lbl}")
        try:
            ans = input(f"Select option [1-{len(items)}]: ").strip()
            if ans.isdigit() and 1 <= int(ans) <= len(items):
                return items[int(ans) - 1][0]
            return items[default_index][0]
        except (EOFError, KeyboardInterrupt):
            return ""

    def multiselect_menu(title: str, options: Sequence[Any], **kwargs: Any) -> list[str]:
        return []

    class FallbackUI:
        def __init__(self, app_name: str = "skald", icon: str = "🎙️") -> None:
            self.app_name = app_name
            self.icon = icon
            self.stream = sys.stdout

        def badge(self) -> str:
            return f"\033[1;36m[{self.icon} {self.app_name}]\033[0m"

        def bold(self, text: str) -> str:
            return f"\033[1m{text}\033[0m"

        def dim(self, text: str) -> str:
            return f"\033[2m{text}\033[0m"

        def blue(self, text: str) -> str:
            return f"\033[34m{text}\033[0m"

        def cyan(self, text: str) -> str:
            return f"\033[36m{text}\033[0m"

        def bold_cyan(self, text: str) -> str:
            return f"\033[1;36m{text}\033[0m"

        def green(self, text: str) -> str:
            return f"\033[32m{text}\033[0m"

        def bold_green(self, text: str) -> str:
            return f"\033[1;32m{text}\033[0m"

        def yellow(self, text: str) -> str:
            return f"\033[33m{text}\033[0m"

        def red(self, text: str) -> str:
            return f"\033[31m{text}\033[0m"

        def magenta(self, text: str) -> str:
            return f"\033[35m{text}\033[0m"

        def success(self, msg: str) -> None:
            print(f"{self.badge()} \033[32m✓\033[0m {msg}")

        def info(self, msg: str) -> None:
            print(f"{self.badge()} \033[36mℹ\033[0m {msg}")

        def warn(self, msg: str) -> None:
            print(f"{self.badge()} \033[33m⚠\033[0m {msg}")

        def error(self, msg: str) -> None:
            print(f"{self.badge()} \033[31m✗\033[0m {msg}", file=sys.stderr)

        def set_color_mode(self, mode: str) -> None:
            pass

        def panel(
            self,
            title: str,
            lines: Sequence[str] | str,
            border_color: str = "0;36",
            width: int = 76,
        ) -> None:
            render_panel(title=title, lines=lines, border_color=border_color, width=width, stream=sys.stdout)

        def error_panel(self, title: str, lines: Sequence[str] | str) -> None:
            render_error_panel(title=title, lines=lines)

        def select(
            self,
            title: str,
            options: Sequence[Any],
            default_index: int = 0,
        ) -> str:
            return select_menu(title=title, options=options, default_index=default_index)

        def prompt(self, message: str, default: str = "") -> str:
            return prompt_input(message=message, default=default)

        def confirm(self, message: str, default: bool = False) -> bool:
            return confirm_input(message=message, default=default)

    ui = FallbackUI()
    Spinner = Any  # type: ignore
    spinner_context = None  # type: ignore


__all__ = [
    "ui",
    "UI",
    "Spinner",
    "spinner_context",
    "add_color_args",
    "apply_color_args",
    "handle_color_args",
    "handle_version_arg",
    "add_agent_args",
    "apply_agent_args",
    "handle_agent_args",
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
]
