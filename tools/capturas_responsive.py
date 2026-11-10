"""Capturas responsive (RNF-09) del dashboard y el historial en 1920, 768 y 390 px. Requiere el servidor en :8765 y Playwright."""
import asyncio
from playwright.async_api import async_playwright
B, PW = "http://127.0.0.1:8765", "Demo-AZA-2026-xyz"
ANCHOS = {"escritorio_1920": (1920, 1080), "tablet_768": (768, 1024), "movil_390": (390, 844)}


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for nombre, (w, h) in ANCHOS.items():
            ctx = await br.new_context(viewport={"width": w, "height": h})
            pg = await ctx.new_page()
            await pg.goto(B + "/login/")
            await pg.fill("#id_username", "supervisor_demo"); await pg.fill("#id_password", PW); await pg.click("button.btn-aza")
            for pagina, url in (("dashboard", "/"), ("historial", "/historial/"), ("alarmas", "/alarmas/"), ("trazabilidad", "/trazabilidad/")):
                await pg.goto(B + url)
                desborde = await pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                print(f"{nombre} {pagina}: desborde horizontal = {desborde}")
                await pg.screenshot(path=f"docs/capturas/responsive_{pagina}_{nombre}.png", full_page=False)
            await ctx.close()
        await br.close()

asyncio.run(main())
