#!/usr/bin/env python3
"""Release-facing name for the real call-path fake phone gate."""

import asyncio

from voice_avatar_direct_e2e import main


if __name__ == "__main__":
    asyncio.run(main())
