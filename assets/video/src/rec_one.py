import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright
from rec import record

HERE = Path(__file__).resolve().parent


async def main(name, page, secs):
    async with async_playwright() as p:
        b = await p.chromium.launch(
            executable_path="/opt/.devin/google-chrome.sh",
            headless=True,
            args=["--no-sandbox", "--force-color-profile=srgb"],
        )
        n = await record(b, (HERE / page).as_uri(), str(HERE / f"{name}.mp4"), secs)
        print(name, "frames", n)


asyncio.run(main(sys.argv[1], sys.argv[2], float(sys.argv[3])))
