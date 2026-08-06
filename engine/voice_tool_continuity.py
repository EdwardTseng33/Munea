"""Small primitives for keeping a Live tool wait subordinate to the user.

No transcript or audio is retained here.  The bridge supplies only a boolean
voice-activity signal and can cancel a read-only lookup when the user resumes.
"""

import asyncio


class ToolWaitInterrupted(Exception):
    """Raised when the user resumes speaking before a tool has completed."""


def sustained_voice_ms(current_ms, above_threshold, frame_ms, trigger_ms=180):
    """Accumulate consecutive voice evidence and return ``(ms, triggered)``."""
    if not above_threshold:
        return 0.0, False
    total = max(0.0, float(current_ms or 0.0)) + max(0.0, float(frame_ms or 0.0))
    return total, total >= max(40.0, float(trigger_ms or 180.0))


async def run_interruptible(coro, user_activity_event, timeout_s):
    """Run a read-only tool until it completes, times out, or the user resumes.

    Cancellation is awaited so network work cannot leak beyond the call turn.
    The caller decides how to phrase the structured cancellation response.
    """
    tool_task = asyncio.create_task(coro)
    activity_task = asyncio.create_task(user_activity_event.wait())
    try:
        done, _ = await asyncio.wait(
            {tool_task, activity_task},
            timeout=max(0.05, float(timeout_s)),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if activity_task in done and activity_task.result():
            tool_task.cancel()
            await asyncio.gather(tool_task, return_exceptions=True)
            raise ToolWaitInterrupted()
        if tool_task in done:
            return await tool_task
        tool_task.cancel()
        await asyncio.gather(tool_task, return_exceptions=True)
        raise asyncio.TimeoutError()
    finally:
        activity_task.cancel()
        await asyncio.gather(activity_task, return_exceptions=True)
