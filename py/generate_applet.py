"""
Generates a self-contained HTML applet illustrating how shooting angle
affects the distance a football flies before hitting the ground.

Run this script to (re)write the HTML file. All physics and interaction
logic lives in embedded JavaScript so the output is a single portable file.
"""

from pathlib import Path

OUTPUT_FILENAME = "football_trajectory_applet.html"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Football Angle vs. Distance</title>
<style>
  :root {
    --grass: #2e7d32;
    --grass-dark: #256428;
    --sky: #cfe8f7;
    --ink: #1b1b1b;
    --accent: #d84315;
    --line: #444;
  }
  body {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    background: #f4f4f2;
    color: var(--ink);
    margin: 0;
    padding: 24px;
  }
  h1 {
    font-size: 20px;
    margin: 0 0 16px 0;
  }
  .layout {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    align-items: flex-start;
  }
  .panel {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .panel h2 {
    font-size: 15px;
    margin: 0 0 10px 0;
    color: #555;
  }
  #gameSvg {
    background: var(--sky);
    border-radius: 6px;
    display: block;
  }
  #graphSvg {
    background: #fafafa;
    border-radius: 6px;
    display: block;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 12px;
    flex-wrap: wrap;
  }
  .controls label {
    font-size: 13px;
    white-space: nowrap;
  }
  input[type="range"] {
    width: 260px;
  }
  button {
    font-size: 14px;
    padding: 6px 16px;
    border-radius: 6px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button.secondary {
    background: #fff;
    color: var(--line);
    border: 1px solid #bbb;
  }
  .angle-readout {
    font-weight: 600;
    min-width: 42px;
    display: inline-block;
  }
  .last-shot {
    margin-top: 10px;
    font-size: 13px;
    color: #444;
  }
  .trace {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
    stroke-dasharray: 4 3;
  }
  .distance-marker line {
    stroke: var(--line);
    stroke-width: 1;
    stroke-dasharray: 3 2;
  }
  .distance-marker text {
    font-size: 12px;
    fill: var(--ink);
  }
  .axis path, .axis line {
    stroke: #888;
  }
  .axis text {
    font-size: 11px;
    fill: #555;
  }
  .shot-dot {
    fill: var(--accent);
    stroke: #7a2100;
    stroke-width: 0.5;
    opacity: 0.85;
  }
  .view-toggle {
    margin-bottom: 16px;
  }
  .panel.hidden {
    display: none;
  }
</style>
</head>
<body>

<h1>How does shooting angle affect distance?</h1>

<div class="view-toggle">
  <button class="secondary" id="viewToggleBtn">Show graph</button>
</div>

<div class="layout">

  <div class="panel" id="gamePanel">
    <h2>Game</h2>
    <svg id="gameSvg" width="700" height="320"></svg>
    <div class="controls">
      <label for="angleSlider">Angle: <span class="angle-readout" id="angleReadout">45&deg;</span></label>
      <input type="range" id="angleSlider" min="0" max="90" step="1" value="45">
      <button id="shootBtn">Shoot</button>
    </div>
    <div class="last-shot" id="lastShot"></div>
  </div>

  <div class="panel hidden" id="graphPanel">
    <h2>Graph &mdash; angle vs. distance</h2>
    <svg id="graphSvg" width="420" height="320"></svg>
    <div class="controls">
      <button class="secondary" id="clearGraphBtn">Clear graph</button>
      <span class="last-shot" id="shotCount">0 shots recorded</span>
    </div>
  </div>

</div>

<script>
(function () {
  "use strict";

  // ---- Physics constants ----
  var V0 = 22;      // initial speed, m/s (constant regardless of angle)
  var G  = 9.81;    // gravity, m/s^2

  var maxRange  = (V0 * V0) / G;        // range at 45 degrees
  var maxHeight = (V0 * V0) / (2 * G);  // height at 90 degrees

  // ---- Game panel setup ----
  var gameSvg  = document.getElementById("gameSvg");
  var GW = 700, GH = 320;
  var marginX = 40, marginTop = 20;
  var groundY = GH - 40;
  var startX  = marginX;

  var availW = GW - 2 * marginX;
  var availH = groundY - marginTop;
  var scale = Math.min(availW / maxRange, availH / maxHeight); // px per metre

  var NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs) {
    var el = document.createElementNS(NS, tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  // Ground
  gameSvg.appendChild(svgEl("line", {
    x1: 0, y1: groundY, x2: GW, y2: groundY,
    stroke: "#5d4037", "stroke-width": 3
  }));
  gameSvg.appendChild(svgEl("rect", {
    x: 0, y: groundY, width: GW, height: GH - groundY, fill: "#2e7d32"
  }));

  var BALL_R = 9;

  // Draws a small stylised soccer ball (white with a black centre pentagon
  // and seam lines) as a <g> positioned via a translate transform, so it
  // can be moved just by updating that transform.
  function makeSoccerBall(cx, cy) {
    var g = svgEl("g", { transform: "translate(" + cx + "," + cy + ")" });
    g.appendChild(svgEl("circle", {
      cx: 0, cy: 0, r: BALL_R, fill: "#fdfdfd", stroke: "#222", "stroke-width": 1.3
    }));
    var pr = BALL_R * 0.42;
    var pts = [];
    for (var i = 0; i < 5; i++) {
      var ang = -Math.PI / 2 + i * (2 * Math.PI / 5);
      pts.push((pr * Math.cos(ang)).toFixed(2) + "," + (pr * Math.sin(ang)).toFixed(2));
    }
    g.appendChild(svgEl("polygon", { points: pts.join(" "), fill: "#222" }));
    for (var j = 0; j < 5; j++) {
      var ang2 = -Math.PI / 2 + j * (2 * Math.PI / 5) + Math.PI / 5;
      var lx = BALL_R * 0.8 * Math.cos(ang2);
      var ly = BALL_R * 0.8 * Math.sin(ang2);
      g.appendChild(svgEl("line", {
        x1: 0, y1: 0, x2: lx.toFixed(2), y2: ly.toFixed(2), stroke: "#222", "stroke-width": 1
      }));
    }
    return g;
  }

  function moveBall(ballGroup, x, y) {
    ballGroup.setAttribute("transform", "translate(" + x + "," + y + ")");
  }

  // ---- Kicker figure (simple stick player standing behind the ball) ----
  var hipX = startX - 20;
  var hipY = groundY - 20;

  var kicker = svgEl("g", {});
  // head
  kicker.appendChild(svgEl("circle", {
    cx: hipX, cy: hipY - 26, r: 7, fill: "#f2c9a0", stroke: "#333", "stroke-width": 1
  }));
  // torso
  kicker.appendChild(svgEl("line", {
    x1: hipX, y1: hipY - 19, x2: hipX, y2: hipY,
    stroke: "#2b6cb0", "stroke-width": 5, "stroke-linecap": "round"
  }));
  // arms
  kicker.appendChild(svgEl("line", {
    x1: hipX, y1: hipY - 15, x2: hipX - 9, y2: hipY - 6,
    stroke: "#2b6cb0", "stroke-width": 3, "stroke-linecap": "round"
  }));
  kicker.appendChild(svgEl("line", {
    x1: hipX, y1: hipY - 15, x2: hipX + 7, y2: hipY - 21,
    stroke: "#2b6cb0", "stroke-width": 3, "stroke-linecap": "round"
  }));
  // standing (support) leg + foot. The ankle sits slightly forward of the
  // hip and the shoe is offset further forward still, so the toe points
  // toward the ball / kick direction (+x) rather than backward.
  var standAnkleX = hipX + 4;
  kicker.appendChild(svgEl("line", {
    x1: hipX, y1: hipY, x2: standAnkleX, y2: groundY,
    stroke: "#37474f", "stroke-width": 5, "stroke-linecap": "round"
  }));
  kicker.appendChild(svgEl("ellipse", { cx: standAnkleX + 5, cy: groundY, rx: 6, ry: 3, fill: "#111" }));

  // Kicking leg: a rotatable group pivoting around the hip. At rest
  // (rotation 0) the leg trails behind the hip on the ground, like a
  // player winding up, but the shoe is offset forward of the ankle so
  // the toe still points toward the ball even while cocked back.
  // Rotating counter-clockwise (negative angle) swings the whole leg
  // forward through where the ball sits and on into a follow-through,
  // toward positive x -- the direction the ball flies.
  var kickAnkleX = hipX - 9, kickAnkleY = hipY + 20;
  var kickLeg = svgEl("g", { transform: "rotate(0 " + hipX + " " + hipY + ")" });
  kickLeg.appendChild(svgEl("line", {
    x1: hipX, y1: hipY, x2: kickAnkleX, y2: kickAnkleY,
    stroke: "#37474f", "stroke-width": 5, "stroke-linecap": "round"
  }));
  kickLeg.appendChild(svgEl("ellipse", { cx: kickAnkleX + 5, cy: kickAnkleY, rx: 6, ry: 3, fill: "#111" }));
  kicker.appendChild(kickLeg);

  gameSvg.appendChild(kicker);

  function setKickAngle(angleDeg) {
    kickLeg.setAttribute("transform", "rotate(" + angleDeg + " " + hipX + " " + hipY + ")");
  }

  // Static ball at start
  var ball = makeSoccerBall(startX, groundY - BALL_R);
  gameSvg.appendChild(ball);

  // Angle indicator line (shows aim before shooting)
  var aimLine = svgEl("line", {
    x1: startX, y1: groundY - BALL_R, x2: startX + 60, y2: groundY - BALL_R,
    stroke: "#333", "stroke-width": 2
  });
  gameSvg.appendChild(aimLine);

  // Persistent trace + marker group (cleared at the start of each new shot)
  var traceGroup = svgEl("g", {});
  gameSvg.appendChild(traceGroup);

  function updateAim(angleDeg) {
    var rad = angleDeg * Math.PI / 180;
    var len = 60;
    var x2 = startX + len * Math.cos(rad);
    var y2 = (groundY - BALL_R) - len * Math.sin(rad);
    aimLine.setAttribute("x2", x2);
    aimLine.setAttribute("y2", y2);
  }

  // ---- Graph panel setup ----
  var graphSvg = document.getElementById("graphSvg");
  var GXW = 420, GXH = 320;
  var gMarginL = 46, gMarginB = 34, gMarginT = 14, gMarginR = 14;
  var plotW = GXW - gMarginL - gMarginR;
  var plotH = GXH - gMarginT - gMarginB;

  var xMaxDeg = 90;
  var yMaxDist = Math.ceil(maxRange / 10) * 10; // round up to nearest 10 m

  function gx(angleDeg) { return gMarginL + (angleDeg / xMaxDeg) * plotW; }
  function gy(dist)     { return gMarginT + plotH - (dist / yMaxDist) * plotH; }

  var axisGroup = svgEl("g", { "class": "axis" });
  graphSvg.appendChild(axisGroup);

  // Axes lines
  axisGroup.appendChild(svgEl("line", { x1: gMarginL, y1: gMarginT, x2: gMarginL, y2: gMarginT + plotH }));
  axisGroup.appendChild(svgEl("line", { x1: gMarginL, y1: gMarginT + plotH, x2: gMarginL + plotW, y2: gMarginT + plotH }));

  // X ticks every 15 degrees
  for (var a = 0; a <= xMaxDeg; a += 15) {
    var xpix = gx(a);
    axisGroup.appendChild(svgEl("line", { x1: xpix, y1: gMarginT + plotH, x2: xpix, y2: gMarginT + plotH + 5 }));
    var lbl = svgEl("text", { x: xpix, y: gMarginT + plotH + 18, "text-anchor": "middle" });
    lbl.textContent = a;
    axisGroup.appendChild(lbl);
  }
  var xAxisTitle = svgEl("text", { x: gMarginL + plotW / 2, y: GXH - 4, "text-anchor": "middle" });
  xAxisTitle.textContent = "angle (degrees)";
  axisGroup.appendChild(xAxisTitle);

  // Y ticks every 10 m
  for (var d = 0; d <= yMaxDist; d += 10) {
    var ypix = gy(d);
    axisGroup.appendChild(svgEl("line", { x1: gMarginL - 5, y1: ypix, x2: gMarginL, y2: ypix }));
    var lbly = svgEl("text", { x: gMarginL - 8, y: ypix + 4, "text-anchor": "end" });
    lbly.textContent = d;
    axisGroup.appendChild(lbly);
  }
  var yAxisTitle = svgEl("text", {
    x: 12, y: gMarginT + plotH / 2,
    "text-anchor": "middle",
    transform: "rotate(-90 12 " + (gMarginT + plotH / 2) + ")"
  });
  yAxisTitle.textContent = "distance (m)";
  axisGroup.appendChild(yAxisTitle);

  var dotsGroup = svgEl("g", {});
  graphSvg.appendChild(dotsGroup);

  var shotCountEl = document.getElementById("shotCount");
  var shotCount = 0;

  function addShotPoint(angleDeg, dist) {
    var dot = svgEl("circle", {
      cx: gx(angleDeg), cy: gy(dist), r: 4, "class": "shot-dot"
    });
    dotsGroup.appendChild(dot);
    shotCount += 1;
    shotCountEl.textContent = shotCount + (shotCount === 1 ? " shot recorded" : " shots recorded");
  }

  document.getElementById("clearGraphBtn").addEventListener("click", function () {
    while (dotsGroup.firstChild) dotsGroup.removeChild(dotsGroup.firstChild);
    shotCount = 0;
    shotCountEl.textContent = "0 shots recorded";
  });

  // ---- Slider + shoot logic ----
  var slider = document.getElementById("angleSlider");
  var angleReadout = document.getElementById("angleReadout");
  var shootBtn = document.getElementById("shootBtn");
  var lastShotEl = document.getElementById("lastShot");

  slider.addEventListener("input", function () {
    angleReadout.innerHTML = slider.value + "&deg;";
    updateAim(Number(slider.value));
  });
  updateAim(Number(slider.value));

  var animId = null;
  var kicking = false;

  // Swings the kicking leg from its wound-up rest pose, through the ball,
  // and into a follow-through. Calls onContact partway through the swing
  // (when the foot is roughly where the ball sits) so the ball launches
  // in sync with the kick, then calls onDone once the swing finishes.
  function playKick(onContact, onDone) {
    var duration = 260;
    var contactFrac = 0.45;
    var contacted = false;
    var t0 = null;

    function step(now) {
      if (t0 === null) t0 = now;
      var frac = Math.min((now - t0) / duration, 1);
      setKickAngle((-130 * frac).toFixed(1));

      if (!contacted && frac >= contactFrac) {
        contacted = true;
        onContact();
      }
      if (frac < 1) {
        requestAnimationFrame(step);
      } else {
        onDone();
      }
    }
    requestAnimationFrame(step);
  }

  function shoot() {
    if (kicking) return; // a kick/shot is already underway
    kicking = true;
    shootBtn.disabled = true;
    slider.disabled = true;

    playKick(launchBall, function () {}); // ball launches mid-swing; follow-through plays out on its own
  }

  function launchBall() {
    var angleDeg = Number(slider.value);
    var rad = angleDeg * Math.PI / 180;
    var flightTime = (2 * V0 * Math.sin(rad)) / G;
    var range = (V0 * V0 * Math.sin(2 * rad)) / G;

    // Clear previous trace/marker, keep the resting ball hidden while it flies
    while (traceGroup.firstChild) traceGroup.removeChild(traceGroup.firstChild);
    ball.style.visibility = "hidden";

    var flyingBall = makeSoccerBall(startX, groundY - BALL_R);
    var tracePath = svgEl("polyline", { points: "", "class": "trace" });
    traceGroup.appendChild(tracePath);
    traceGroup.appendChild(flyingBall);

    var points = [];
    var startTime = null;

    // Angle-dependent duration so slow lobs and flat shots both animate
    // over a comparable, watchable real-time interval.
    var animDurationMs = 900 + 500 * Math.sin(rad);

    function frame(now) {
      if (startTime === null) startTime = now;
      var elapsed = now - startTime;
      var frac = Math.min(elapsed / animDurationMs, 1);
      var t = frac * flightTime;

      var xm = V0 * Math.cos(rad) * t;
      var ym = V0 * Math.sin(rad) * t - 0.5 * G * t * t;
      if (ym < 0) ym = 0;

      var px = startX + xm * scale;
      var py = groundY - ym * scale;

      points.push(px + "," + py);
      tracePath.setAttribute("points", points.join(" "));
      moveBall(flyingBall, px, py);

      if (frac < 1) {
        animId = requestAnimationFrame(frame);
      } else {
        finishShot(angleDeg, range, flyingBall);
      }
    }

    animId = requestAnimationFrame(frame);
  }

  function finishShot(angleDeg, range, flyingBall) {
    animId = null;
    kicking = false;

    // Remove the flying ball, drop a distance marker at the landing spot,
    // then reset the resting ball and kicking leg for the next shot.
    if (flyingBall && flyingBall.parentNode) flyingBall.parentNode.removeChild(flyingBall);

    var landingPx = startX + range * scale;

    var marker = svgEl("g", { "class": "distance-marker" });
    marker.appendChild(svgEl("line", { x1: landingPx, y1: groundY, x2: landingPx, y2: groundY - 20 }));
    var label = svgEl("text", { x: landingPx, y: groundY - 26, "text-anchor": "middle" });
    label.textContent = range.toFixed(1) + " m";
    marker.appendChild(label);
    traceGroup.appendChild(marker);

    ball.style.visibility = "visible";
    moveBall(ball, startX, groundY - BALL_R);
    setKickAngle(0);

    lastShotEl.textContent = "Last shot: " + angleDeg + "° → " + range.toFixed(1) + " m";

    addShotPoint(angleDeg, range);

    shootBtn.disabled = false;
    slider.disabled = false;
  }

  shootBtn.addEventListener("click", shoot);

  // ---- View toggle (Game <-> Graph) ----
  var gamePanel = document.getElementById("gamePanel");
  var graphPanel = document.getElementById("graphPanel");
  var viewToggleBtn = document.getElementById("viewToggleBtn");
  var showingGraph = false;

  viewToggleBtn.addEventListener("click", function () {
    showingGraph = !showingGraph;
    gamePanel.classList.toggle("hidden", showingGraph);
    graphPanel.classList.toggle("hidden", !showingGraph);
    viewToggleBtn.textContent = showingGraph ? "Show game" : "Show graph";
  });
})();
</script>

</body>
</html>
"""


def main():
    out_dir = Path(__file__).resolve().parent.parent
    out_path = out_dir / OUTPUT_FILENAME
    out_path.write_text(HTML, encoding="utf-8")
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
