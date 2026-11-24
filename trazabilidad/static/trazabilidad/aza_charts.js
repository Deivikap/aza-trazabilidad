(function () {
  "use strict";

  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_) {
      return null;
    }
  }

  function setupCanvas(canvas, heightPx) {
    var dpr = window.devicePixelRatio || 1;
    var width = Math.max(canvas.parentElement ? canvas.parentElement.clientWidth : 480, 260);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(heightPx * dpr);
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, heightPx);
    return { ctx: ctx, w: width, h: heightPx };
  }

  function drawEmpty(ctx, w, h, msg) {
    ctx.fillStyle = "#6c757d";
    ctx.font = "13px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(msg || "Sin datos para graficar", w / 2, h / 2);
  }

  function drawEstados(canvas) {
    var data = readJson(canvas.dataset.source);
    var c = setupCanvas(canvas, 200);
    var ctx = c.ctx, w = c.w, h = c.h;
    if (!data) return drawEmpty(ctx, w, h);
    var total = (data.aprobadas || 0) + (data.rechazadas || 0) + (data.sin_receta || 0);
    if (total === 0) return drawEmpty(ctx, w, h, "Sin inspecciones registradas");

    var rows = [
      { label: "[OK] Aprobado", val: data.aprobadas || 0, color: "#1b5e20", bg: "#e8f5e9" },
      { label: "[!] Rechazado", val: data.rechazadas || 0, color: "#b71c1c", bg: "#fdecea" },
      { label: "Sin receta", val: data.sin_receta || 0, color: "#7a5800", bg: "#fff8e1" }
    ];
    var left = 115, right = 74, barW = Math.max(w - left - right, 80);
    var top = 26, rowH = 52;

    rows.forEach(function (r, idx) {
      var y = top + idx * rowH;
      var pct = Math.round((r.val * 1000) / total) / 10;
      var fillW = Math.round((r.val / total) * barW);

      ctx.fillStyle = "#212529";
      ctx.font = "600 12px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(r.label, left - 10, y + 14);

      ctx.fillStyle = r.bg;
      ctx.fillRect(left, y, barW, 28);
      ctx.strokeStyle = "#dee2e6";
      ctx.strokeRect(left, y, barW, 28);

      if (fillW > 0) {
        ctx.fillStyle = r.color;
        ctx.fillRect(left, y, Math.max(fillW, 4), 28);
      }

      ctx.fillStyle = "#212529";
      ctx.font = "600 12px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(r.val + " (" + pct + "%)", left + barW + 8, y + 14);
    });
  }

  function drawAngulo(canvas) {
    var pts = readJson(canvas.dataset.source);
    var c = setupCanvas(canvas, 220);
    var ctx = c.ctx, w = c.w, h = c.h;
    if (!pts || !pts.length) return drawEmpty(ctx, w, h, "Sin mediciones angulares");

    var pad = { l: 48, r: 18, t: 20, b: 36 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;

    var vals = pts.map(function (p) { return p.angulo; });
    pts.forEach(function (p) {
      if (p.min !== null && p.min !== undefined) vals.push(p.min);
      if (p.max !== null && p.max !== undefined) vals.push(p.max);
    });
    var minV = Math.min.apply(null, vals);
    var maxV = Math.max.apply(null, vals);
    if (minV === maxV) { minV -= 1; maxV += 1; }
    var margin = (maxV - minV) * 0.12;
    minV -= margin;
    maxV += margin;

    function xOf(i) {
      if (pts.length === 1) return pad.l + pw / 2;
      return pad.l + (i / (pts.length - 1)) * pw;
    }
    function yOf(v) {
      return pad.t + ((maxV - v) / (maxV - minV)) * ph;
    }

    // Rejilla horizontal
    ctx.strokeStyle = "#e9ecef";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#495057";
    ctx.font = "11px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (var g = 0; g <= 4; g++) {
      var v = minV + ((maxV - minV) * g) / 4;
      var yg = yOf(v);
      ctx.beginPath();
      ctx.moveTo(pad.l, yg);
      ctx.lineTo(w - pad.r, yg);
      ctx.stroke();
      ctx.fillText(v.toFixed(1) + "°", pad.l - 6, yg);
    }

    // Líneas de tolerancia de referencia si todas las muestras comparten límites o usando último límite disponible
    var ref = null;
    for (var k = pts.length - 1; k >= 0; k--) {
      if (pts[k].min !== null && pts[k].max !== null) { ref = pts[k]; break; }
    }
    if (ref) {
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = "#6c757d";
      ctx.lineWidth = 1;
      [ref.min, ref.max].forEach(function (lim) {
        var yl = yOf(lim);
        ctx.beginPath();
        ctx.moveTo(pad.l, yl);
        ctx.lineTo(w - pad.r, yl);
        ctx.stroke();
      });
      ctx.restore();
    }

    // Línea de evolución angular
    ctx.strokeStyle = "#0f4761";
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach(function (p, i) {
      var x = xOf(i), y = yOf(p.angulo);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Puntos coloreados según estado original
    pts.forEach(function (p, i) {
      var x = xOf(i), y = yOf(p.angulo);
      ctx.fillStyle = p.estado === "RECHAZADO" ? "#c62828" : (p.estado === "SIN_RECETA" ? "#f9a825" : "#2e7d32");
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    // Etiquetas eje X (primero, medio, último)
    ctx.fillStyle = "#495057";
    ctx.font = "11px system-ui, -apple-system, sans-serif";
    ctx.textBaseline = "top";
    var idxs = pts.length <= 3 ? pts.map(function (_, i) { return i; }) : [0, Math.floor((pts.length - 1) / 2), pts.length - 1];
    idxs.forEach(function (i) {
      ctx.textAlign = i === 0 ? "left" : (i === pts.length - 1 ? "right" : "center");
      ctx.fillText(pts[i].hora, xOf(i), h - pad.b + 8);
    });
  }

  function drawTurnos(canvas) {
    var rows = readJson(canvas.dataset.source);
    var c = setupCanvas(canvas, 200);
    var ctx = c.ctx, w = c.w, h = c.h;
    if (!rows || !rows.length) return drawEmpty(ctx, w, h, "Sin datos por turno");

    var pad = { l: 42, r: 16, t: 42, b: 34 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;
    var maxVal = Math.max.apply(null, rows.map(function (r) { return r.total; }).concat([1]));

    // Leyenda superior
    ctx.font = "11px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#0f4761"; ctx.fillRect(pad.l, 8, 12, 10);
    ctx.fillStyle = "#212529"; ctx.fillText("Total", pad.l + 16, 13);
    ctx.fillStyle = "#c62828"; ctx.fillRect(pad.l + 64, 8, 12, 10);
    ctx.fillStyle = "#212529"; ctx.fillText("Rechazadas", pad.l + 80, 13);

    var groupW = pw / rows.length;
    var barW = Math.min(34, groupW * 0.32);

    rows.forEach(function (r, idx) {
      var cx = pad.l + idx * groupW + groupW / 2;
      var hTot = (r.total / maxVal) * ph;
      var hRec = (r.rechazadas / maxVal) * ph;
      var yBase = pad.t + ph;

      ctx.fillStyle = "#0f4761";
      ctx.fillRect(cx - barW - 2, yBase - hTot, barW, hTot);
      ctx.fillStyle = "#c62828";
      ctx.fillRect(cx + 2, yBase - hRec, barW, hRec);

      ctx.fillStyle = "#212529";
      ctx.font = "600 11px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(String(r.total), cx - barW / 2 - 2, yBase - hTot - 3);
      ctx.fillText(String(r.rechazadas), cx + barW / 2 + 2, yBase - hRec - 3);

      ctx.fillStyle = "#495057";
      ctx.font = "11px system-ui, -apple-system, sans-serif";
      ctx.textBaseline = "top";
      ctx.fillText(r.turno, cx, yBase + 8);
    });
  }

  function drawEfectividad(canvas) {
    var rows = readJson(canvas.dataset.source);
    var c = setupCanvas(canvas, 210);
    var ctx = c.ctx, w = c.w, h = c.h;
    if (!rows || !rows.length) return drawEmpty(ctx, w, h, "Sin datos en el período seleccionado");

    var left = 110, right = 88, barW = Math.max(w - left - right, 80);
    var top = 26, rowH = 56;
    rows.forEach(function (r, idx) {
      var y = top + idx * rowH;
      var pct = r.efectividad || 0;
      var fillW = Math.round((pct / 100) * barW);
      var color = pct >= 85 ? "#1b5e20" : (pct >= 65 ? "#b45309" : "#b71c1c");

      ctx.fillStyle = "#212529";
      ctx.font = "600 12px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(r.turno, left - 10, y + 14);

      ctx.fillStyle = "#f1f5f9";
      ctx.fillRect(left, y, barW, 28);
      ctx.strokeStyle = "#cbd5e1";
      ctx.strokeRect(left, y, barW, 28);

      if (fillW > 0) {
        ctx.fillStyle = color;
        ctx.fillRect(left, y, Math.max(fillW, 4), 28);
      }

      ctx.fillStyle = "#212529";
      ctx.font = "600 12px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(pct + "% (" + r.aprobadas + "/" + r.total + ")", left + barW + 8, y + 14);
    });
  }

  function renderAll() {
    document.querySelectorAll("canvas[data-chart='estados']").forEach(drawEstados);
    document.querySelectorAll("canvas[data-chart='angulo']").forEach(drawAngulo);
    document.querySelectorAll("canvas[data-chart='turnos']").forEach(drawTurnos);
    document.querySelectorAll("canvas[data-chart='efectividad']").forEach(drawEfectividad);
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderAll();

    document.querySelectorAll("[data-print-report]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        window.print();
      });
    });

    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        if (!window.confirm(form.dataset.confirm)) {
          ev.preventDefault();
        }
      });
    });
  });

  window.addEventListener("resize", renderAll);
})();
