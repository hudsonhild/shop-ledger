<script>
(function () {
  "use strict";
  var svg = document.getElementById("plot");
  if (!svg || typeof SERIES === "undefined") return;

  var NS = "http://www.w3.org/2000/svg";
  var W = 760, H = 170, L = 44, R = 8, T = 12, B = 26;

  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    for (var key in attrs) node.setAttribute(key, attrs[key]);
    return node;
  }

  function short(n) {
    var abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return String(Math.round(n));
  }

  function draw(key) {
    var data = SERIES[key];
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (!data || !data.values || !data.values.length) return;

    var values = data.values;
    var max = Math.max.apply(null, values);
    var top = max <= 0 ? 1 : max * 1.12;
    var innerW = W - L - R, innerH = H - T - B;

    for (var i = 0; i <= 3; i++) {
      var y = T + (innerH / 3) * i;
      svg.appendChild(el("line", {
        x1: L, x2: W - R, y1: y, y2: y,
        stroke: "currentColor", "stroke-opacity": i === 3 ? 0.14 : 0.08
      }));
      var label = el("text", {
        x: 0, y: y + 4, "font-size": 10, fill: "currentColor",
        "fill-opacity": 0.5, "font-family": "Inter, sans-serif"
      });
      var v = top - (top / 3) * i;
      label.textContent = data.money ? "$" + short(v) : short(v);
      svg.appendChild(label);
    }

    // A single resolved day is the normal state on day two. Centre it rather
    // than pinning a lone marker to the left edge.
    var single = values.length === 1;
    var step = single ? 0 : innerW / (values.length - 1);
    var points = values.map(function (v, idx) {
      var x = single ? L + innerW / 2 : L + step * idx;
      var y = T + innerH - (v / top) * innerH;
      return [x, y];
    });

    svg.appendChild(el("polyline", {
      points: points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
      fill: "none", stroke: "#2563EB", "stroke-width": 1.5,
      "stroke-linejoin": "round", "stroke-linecap": "round",
      "vector-effect": "non-scaling-stroke"
    }));

    var last = points[points.length - 1];
    svg.appendChild(el("circle", { cx: last[0], cy: last[1], r: 3, fill: "#2563EB" }));
  }

  var cells = Array.prototype.slice.call(document.querySelectorAll(".cell"));
  cells.forEach(function (cell) {
    cell.addEventListener("click", function () {
      cells.forEach(function (other) { other.setAttribute("aria-pressed", "false"); });
      cell.setAttribute("aria-pressed", "true");
      draw(cell.dataset.key);
    });
  });

  var active = document.querySelector('.cell[aria-pressed="true"]') || cells[0];
  if (active) draw(active.dataset.key);
})();
</script>
