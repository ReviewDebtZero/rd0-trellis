"""Record a page via CDP screencast into a constant-30fps 1920x1080 mp4. Usage in other scripts: await record(...)."""

import asyncio
import base64
import io
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
CAP = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)


def caption(im, text):
    if not text:
        return im
    import textwrap

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    lines = textwrap.wrap(text, 72)
    top = H - 66 - 54 * len(lines)
    d.rounded_rectangle(
        [140, top - 30, W - 140, H - 36], 22, fill=(5, 8, 20, 225), outline=(96, 165, 250, 255), width=3
    )
    for i, ln in enumerate(lines):
        w = d.textlength(ln, font=CAP)
        d.text(((W - w) / 2, top + 54 * i - 4), ln, font=CAP, fill=(248, 250, 252))
    im = im.convert("RGBA")
    im.alpha_composite(ov)
    return im.convert("RGB")


async def record(
    browser, url, out, seconds, actions=None, viewport=(1920, 1080), dsf=1, captions=None, scheme="dark"
):
    ctx = await browser.new_context(
        viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=dsf, color_scheme=scheme
    )
    pg = await ctx.new_page()
    await pg.goto("about:blank")
    cdp = await ctx.new_cdp_session(pg)
    frames = []

    def on(ev):
        frames.append((ev["metadata"]["timestamp"], ev["data"]))
        asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]}))

    cdp.on("Page.screencastFrame", on)
    await cdp.send(
        "Page.startScreencast",
        {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1},
    )
    await pg.goto(url, wait_until="load")
    import time

    t0 = time.time()
    if actions:
        await actions(pg)
    rest = seconds - (time.time() - t0)
    if rest > 0:
        await pg.wait_for_timeout(rest * 1000)
    await cdp.send("Page.stopScreencast")
    await ctx.close()
    frames.sort()
    start = frames[0][0]
    ff = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{W}x{H}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            out,
        ],
        stdin=subprocess.PIPE,
    )
    if captions and len(captions[0]) == 2:
        captions = [
            (t - start + 0.2, ((captions[i + 1][0] - start) if i + 1 < len(captions) else seconds) - 0.1, txt)
            for i, (t, txt) in enumerate(captions)
        ]
    j, _cur, cache = 0, None, {}
    n = int(seconds * FPS)
    for k in range(n):
        t = start + k / FPS
        while j < len(frames) and frames[j][0] <= t:
            j += 1
        idx = max(j - 1, 0)
        cap = ""
        if captions:
            for a, b, txt in captions:
                if a <= k / FPS < b:
                    cap = txt
        key = (idx, cap)
        if key not in cache:
            cache.clear()
            im = Image.open(io.BytesIO(base64.b64decode(frames[idx][1]))).convert("RGB")
            if im.size != (W, H):
                im = im.resize((W, H), Image.LANCZOS)
            cache[key] = caption(im, cap).tobytes()
        ff.stdin.write(cache[key])
    ff.stdin.close()
    ff.wait()
    return len(frames)
