"""验证修复: report_progress 三条消息均被客户端接收。

预期服务器已在 localhost:8000/mcp 运行 (echo 工具)。
断言:
  1. context.info 产生的日志通知通过 message_handler 被接收
  2. context.report_progress (3 次) 通过 progress_callback 被接收
  3. echo 工具最终返回 is_error=False 且文本正确
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = _PROJECT_ROOT / "src" / "client.py"
PYTHON_EXE = sys.executable

EXPECTED_LOG_LINE = "Processing file 1/3"
EXPECTED_PROGRESS_LINES = [
    "Processing file 2/3",
    "Processing file 3/3",
    "File processing completed",
]
EXPECTED_TOOL_TEXT = "Here is the file conent: Hello, World!"


def run_client_and_capture() -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYTHON_EXE, str(CLIENT_PATH)],
        cwd=str(CLIENT_PATH.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    try:
        rc, stdout, stderr = run_client_and_capture()
    except subprocess.TimeoutExpired as exc:
        print("TEST FAIL: client timed out")
        print("stdout:\n", exc.stdout)
        print("stderr:\n", exc.stderr)
        return 2

    print("=== client stdout ===")
    print(stdout)
    if stderr:
        print("=== client stderr ===")
        print(stderr, file=sys.stderr)

    failed = False
    checks: list[tuple[str, bool]] = []

    checks.append(("exit code == 0", rc == 0))

    # Logging notification (from context.info) via message_handler
    checks.append((
        f"logging notification '{EXPECTED_LOG_LINE}' in message_handler",
        EXPECTED_LOG_LINE in stdout,
    ))

    # Progress notifications (from context.report_progress x3) via progress_callback
    for msg in EXPECTED_PROGRESS_LINES:
        checks.append((
            f"progress callback sees {msg!r}",
            msg in stdout,
        ))

    # Final tool result
    checks.append((
        f"echo tool result contains: {EXPECTED_TOOL_TEXT}",
        EXPECTED_TOOL_TEXT in stdout and "is_error=False" in stdout,
    ))

    # No TypeError in stderr (previous bug)
    checks.append((
        "no 'object NoneType can't be used in await' error",
        "NoneType can't be used in 'await' expression" not in (stderr + stdout),
    ))
    checks.append((
        "no 'notification callback ... raised' traceback",
        not (
            ("notification callback" in stderr and "raised" in stderr)
            or ("notification callback" in stdout and "raised" in stdout)
        ),
    ))

    print("\n=== 测试用例结果 ===")
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            failed = True

    # 3 条 progress 必须独立计数 (不能只出现一次)
    progress_count = stdout.count("Progress:")
    checks_counted = (
        "三条 progress 回调独立触发",
        progress_count == len(EXPECTED_PROGRESS_LINES),
    )
    name, ok = checks_counted
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name} (实际触发次数={progress_count}, 期望={len(EXPECTED_PROGRESS_LINES)})")
    if not ok:
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
