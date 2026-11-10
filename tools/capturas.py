import asyncio
from playwright.async_api import async_playwright
B="http://127.0.0.1:8765"; PW="Demo-AZA-2026-xyz"
async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        async def sesion(user, paginas):
            ctx = await br.new_context(viewport={"width":1440,"height":900})
            pg = await ctx.new_page()
            await pg.goto(B+"/login/"); await pg.screenshot(path=f"docs/capturas/login.png") if user=="admin_demo" else None
            await pg.fill("#id_username", user); await pg.fill("#id_password", PW); await pg.click("button.btn-aza")
            for nombre, url in paginas:
                await pg.goto(B+url); await pg.screenshot(path=f"docs/capturas/{user.split('_')[0]}_{nombre}.png")
            await ctx.close()
        await sesion("admin_demo",[("dashboard","/"),("usuarios","/administracion/usuarios/"),("recetas","/administracion/recetas/"),("auditoria","/administracion/auditoria/"),("lotes","/administracion/lotes/")])
        await sesion("supervisor_demo",[("dashboard","/"),("historial","/historial/"),("detalle","/inspecciones/1/"),("trazabilidad","/trazabilidad/"),("alarmas","/alarmas/")])
        await sesion("operador_demo",[("dashboard","/"),("403","/administracion/usuarios/")])
        await br.close()
asyncio.run(main())
