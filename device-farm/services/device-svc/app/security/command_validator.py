# Command Validator - Security validation for ADB shell commands
import re
from typing import Tuple, Optional, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class AllowedCommand:
    """Represents an allowed command pattern"""
    pattern: str
    description: str
    requires_device: bool = True
    example: str = ""


class CommandValidator:
    """
    Validates and sanitizes shell commands for safe execution on devices.

    Uses a whitelist approach - only explicitly allowed commands can be executed.
    All other commands are rejected to prevent command injection attacks.
    """

    # Whitelist of allowed command patterns with regex matching
    ALLOWED_COMMANDS: List[AllowedCommand] = [
        # System information
        AllowedCommand(
            pattern=r"^getprop\s+[\w.]+$",
            description="Get system property",
            example="getprop ro.product.model"
        ),
        AllowedCommand(
            pattern=r"^getprop$",
            description="Get all system properties",
            example="getprop"
        ),
        AllowedCommand(
            pattern=r"^dumpsys\s+battery$",
            description="Get battery information",
            example="dumpsys battery"
        ),
        AllowedCommand(
            pattern=r"^dumpsys\s+window\s+displays$",
            description="Get display information",
            example="dumpsys window displays"
        ),
        AllowedCommand(
            pattern=r"^dumpsys\s+cpuinfo$",
            description="Get CPU information",
            example="dumpsys cpuinfo"
        ),
        AllowedCommand(
            pattern=r"^dumpsys\s+meminfo$",
            description="Get memory information",
            example="dumpsys meminfo"
        ),
        AllowedCommand(
            pattern=r"^dumpsys\s+activity\s+packages$",
            description="Get activity package information",
            example="dumpsys activity packages"
        ),

        # Package management
        AllowedCommand(
            pattern=r"^pm\s+list\s+packages(-[a-z])?$",
            description="List installed packages",
            example="pm list packages"
        ),
        AllowedCommand(
            pattern=r"^pm\s+path\s+[\w.]+$",
            description="Get package path",
            example="pm path com.example.app"
        ),
        AllowedCommand(
            pattern=r"^pm\s+dump\s+[\w.]+$",
            description="Dump package information",
            example="pm dump com.example.app"
        ),

        # Application management
        AllowedCommand(
            pattern=r"^am\s+force-stop\s+[\w.]+$",
            description="Force stop an application",
            example="am force-stop com.example.app"
        ),
        AllowedCommand(
            pattern=r"^am\s+start\s+-n\s+[\w.]+/[\w.]+$",
            description="Start an activity",
            example="am start -n com.example.app/.MainActivity"
        ),
        AllowedCommand(
            pattern=r"^am\s+start\s+-a\s+[\w.]+$",
            description="Start an activity by action",
            example="am start -a android.intent.action.VIEW"
        ),

        # Input events
        AllowedCommand(
            pattern=r"^input\s+tap\s+\d+\s+\d+$",
            description="Tap screen at coordinates",
            example="input tap 500 500"
        ),
        AllowedCommand(
            pattern=r"^input\s+swipe\s+\d+\s+\d+\s+\d+\s+\d+(\s+\d+)?$",
            description="Swipe gesture",
            example="input swipe 100 500 500 500 300"
        ),
        AllowedCommand(
            pattern=r"^input\s+keyevent\s+\d+$",
            description="Send key event",
            example="input keyevent 4"  # KEYCODE_BACK
        ),
        AllowedCommand(
            pattern=r"^input\s+text\s+'[^']*'$",
            description="Input text (single quoted)",
            example="input text 'hello'"
        ),

        # Screen capture
        AllowedCommand(
            pattern=r"^screencap\s+-p\s+/sdcard/[\w./]+\.png$",
            description="Take screenshot to file",
            example="screencap -p /sdcard/screenshot.png"
        ),
        AllowedCommand(
            pattern=r"^screencap\s+-p$",
            description="Take screenshot to stdout",
            example="screencap -p"
        ),

        # File operations (limited)
        AllowedCommand(
            pattern=r"^ls\s+-[la]+\s+/sdcard/[\w./]*$",
            description="List files in allowed directory",
            example="ls -la /sdcard/"
        ),
        AllowedCommand(
            pattern=r"^cat\s+/proc/[\w./]+$",
            description="Read proc file",
            example="cat /proc/meminfo"
        ),
        AllowedCommand(
            pattern=r"^rm\s+/sdcard/[\w./]+\.png$",
            description="Remove temporary screenshot file",
            example="rm /sdcard/screenshot.png"
        ),

        # Settings
        AllowedCommand(
            pattern=r"^settings\s+get\s+(global|secure|system)\s+[\w.]+$",
            description="Get system setting",
            example="settings get global airplane_mode_on"
        ),

        # Logcat
        AllowedCommand(
            pattern=r"^logcat\s+-d\s+-t\s+\d+$",
            description="Get recent logcat entries",
            example="logcat -d -t 100"
        ),
        AllowedCommand(
            pattern=r"^logcat\s+-d$",
            description="Get all logcat entries",
            example="logcat -d"
        ),
    ]

    # Dangerous patterns that should always be rejected
    DANGEROUS_PATTERNS: List[str] = [
        r'[;&|`$]',           # Shell metacharacters for command chaining
        r'\$\(',              # Command substitution $(...)
        r'`[^`]+`',           # Backtick command substitution
        r'\.\./',             # Path traversal
        r'>|>>',              # Output redirection
        r'<',                 # Input redirection
        r'\(\s*\)',           # Subshell
        r'\[\s*\]',           # Bash test construct
        r'\{[^}]*\}',         # Brace expansion
        r'!\s*\w',            # History expansion
        r'\bxargs\b',         # xargs command
        r'\bexec\b',          # exec command
        r'\beval\b',          # eval command
        r'\bsource\b',        # source command
        r'\bexport\b',        # export command
        r'\balias\b',         # alias command
        r'\bunset\b',         # unset command
        r'\bmkfifo\b',        # named pipe
        r'\bnc\b',            # netcat
        r'\bncat\b',          # ncat
        r'\btelnet\b',        # telnet
        r'\bssh\b',           # ssh
        r'\bscp\b',           # scp
        r'\bwget\b',          # wget
        r'\bcurl\b',          # curl
        r'\bdd\b',            # dd command (dangerous)
        r'\bfdisk\b',         # fdisk
        r'\bmkfs\b',          # mkfs
        r'\bmount\b',         # mount
        r'\bumount\b',        # umount
        r'\biptables\b',      # iptables
        r'\bip6tables\b',     # ip6tables
        r'\bchmod\b',         # chmod (potential security risk)
        r'\bchown\b',         # chown
        r'\bsu\b',            # su command
        r'\bsudo\b',          # sudo
        r'\bshutdown\b',      # shutdown
        r'\breboot\b',        # reboot
        r'\binit\b',          # init
        r'\bkill\b',          # kill
        r'\bkillall\b',       # killall
        r'\b rm\s+-rf\b',     # rm -rf
        r'\b rm\s+-r\b',      # rm -r
        r'\bformat\b',        # format
    ]

    @classmethod
    def validate(cls, command: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a command against the whitelist and check for dangerous patterns.

        Args:
            command: The shell command to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if command is valid
            - (False, error_message) if command is invalid
        """
        if not command or not command.strip():
            return False, "Empty command"

        command = command.strip()

        # First check for dangerous patterns - always reject these
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                sanitized = cls.sanitize_for_logging(command)
                logger.warning(f"Rejected command with dangerous pattern: {sanitized}")
                return False, f"Command contains dangerous pattern"

        # Check against whitelist
        for allowed in cls.ALLOWED_COMMANDS:
            if re.match(allowed.pattern, command):
                logger.info(f"Command validated: {allowed.description}")
                return True, None

        # Command not in whitelist
        sanitized = cls.sanitize_for_logging(command)
        logger.warning(f"Command not in whitelist: {sanitized}")
        return False, f"Command not allowed. Command must match one of the allowed patterns."

    @classmethod
    def sanitize_for_logging(cls, command: str) -> str:
        """
        Remove potentially sensitive data from command for safe logging.

        Args:
            command: The command to sanitize

        Returns:
            Sanitized command string safe for logging
        """
        # Redact common sensitive patterns
        sanitized = command
        sensitive_patterns = [
            (r'password[=\s]+\S+', 'password=[REDACTED]'),
            (r'token[=\s]+\S+', 'token=[REDACTED]'),
            (r'key[=\s]+\S+', 'key=[REDACTED]'),
            (r'secret[=\s]+\S+', 'secret=[REDACTED]'),
            (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
        ]

        for pattern, replacement in sensitive_patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        return sanitized

    @classmethod
    def get_allowed_commands_help(cls) -> str:
        """
        Get a formatted help string of all allowed commands.

        Returns:
            Formatted string with allowed commands and examples
        """
        lines = ["Allowed commands:"]
        for cmd in cls.ALLOWED_COMMANDS:
            lines.append(f"  - {cmd.description}")
            if cmd.example:
                lines.append(f"    Example: {cmd.example}")
        return "\n".join(lines)
