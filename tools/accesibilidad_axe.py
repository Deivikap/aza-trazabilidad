"""Auditoría de accesibilidad automatizada (axe-core, reglas WCAG 2.x A/AA) sobre las pantallas principales.
Requiere: servidor en :8765, Playwright y `npm i axe-core` (ruta en AXE_JS)."""
import asyncio, json, os, sys
from playwright.async_api import async_playwright
B, PW = "http://127.0.0.1:8765", "Demo-AZA-2026-xyz"
AXE = open(os.environ.get("AXE_JS", "/tmp/axe/node_modules/axe-core/axe.min.js")).read()
PAGINAS = [("login", "/login/", None), ("dashboard", "/", "supervisor_demo"), ("historial", "/historial/", "supervisor_demo"),
           ("detalle", "/inspecciones/1/", "supervisor_demo"), ("trazabilidad", "/trazabilidad/", "supervisor_demo"),
           ("alarmas", "/alarmas/", "supervisor_demo"), ("usuarios", "/administracion/usuarios/", "admin_demo"),
           ("auditoria", "/administracion/auditoria/", "admin_demo")]


async def main():
    resultado = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for nombre, url, usuario in PAGINAS:
            ctx = await br.new_context(viewport={"width": 1440, "height": 900}, bypass_csp=True); pg = await ctx.new_page()
            if usuario:
                await pg.goto(B + "/login/"); await pg.fill("#id_username", usuario); await pg.fill("#id_password", PW); await pg.click("button.btn-aza")
            await pg.goto(B + url)
            await pg.add_script_tag(content=AXE)
            r = await pg.evaluate("axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})")
            v = [{"id": x["id"], "impacto": x["impact"], "nodos": len(x["nodes"]), "ayuda": x["help"],
                  "detalle": [(n["target"], n["any"][0]["message"] if n["any"] else n["failureSummary"][:160]) for n in x["nodes"]]} for x in r["violations"]]
            resultado.append({"pagina": nombre, "reglas_aprobadas": len(r["passes"]), "violaciones": v})
            print(f"{nombre:13s} aprobadas={len(r['passes']):3d} violaciones={len(v)} " + ", ".join(f"{x['id']}({x['impacto']},{x['nodos']})" for x in v))
            await ctx.close()
        await br.close()
    json.dump(resultado, open("evidencias/axe.json", "w"), ensure_ascii=False, indent=1)

asyncio.run(main())
