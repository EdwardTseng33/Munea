#!/usr/bin/env python3
"""Release-facing name for the real call-path fake phone gate."""

import asyncio
import sys

from voice_avatar_direct_e2e import main


if __name__ == "__main__":
    if "--runs" not in sys.argv:
        sys.argv.extend(["--runs", "3"])
    asyncio.run(main())
