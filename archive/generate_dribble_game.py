"""
Generates a self-contained HTML arcade game: dribble a football past
defenders and a goalkeeper to score. Unlike the angle/trajectory applets,
this one is real-time and keyboard-controlled, drawn on an HTML canvas.

Run this script to (re)write the HTML file.
"""

from pathlib import Path

OUTPUT_FILENAME = "football_dribble_game.html"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Football Dribble</title>
<style>
  :root {
    --pitch: #2e8b3d;
    --pitch-line: #eafff0;
    --ink: #1b1b1b;
    --accent: #d84315;
    --good: #2e7d32;
    --bad: #c62828;
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
  .panel {
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    display: inline-block;
  }
  #pitch {
    background: var(--pitch);
    border-radius: 6px;
    display: block;
    outline: none;
  }
  .controls {
    margin-top: 10px;
    font-size: 13px;
    color: #555;
  }
  .status-line {
    margin-top: 8px;
    font-size: 14px;
    color: #444;
  }
  .status-line .result {
    font-weight: 700;
  }
  .result.good {
    color: var(--good);
  }
  .result.bad {
    color: var(--bad);
  }
  button {
    font-size: 14px;
    padding: 6px 16px;
    border-radius: 6px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    cursor: pointer;
    margin-top: 8px;
  }
</style>
</head>
<body>

<h1>Dribble past the defenders and score!</h1>

<div class="panel">
  <canvas id="pitch" width="800" height="500" tabindex="0"></canvas>
  <div class="controls">
    Move with the Arrow keys / W/A/S/D, or by dragging your finger on the
    touchpad (the player heads toward the pointer). Wherever the pointer
    last was is also your aim -- shown as a dashed line from the ball -- so
    you can run one way and shoot another. Click or press Space to shoot.
    Beat the three red defenders in the open field. There are two shaded
    safe zones the defenders can never enter -- one part-way across the
    pitch to catch your breath, and one right in front of goal where
    it's just you against the keeper.
  </div>
  <div class="status-line" id="statusLine">Move the pointer on the pitch to steer, or use Arrow keys/WASD. Click or press Space to shoot.</div>
  <div class="status-line" id="scoreLine">Goals: 0 / Attempts: 0</div>
  <button id="restartBtn">Restart</button>
</div>

<script>
(function () {
  "use strict";

  var canvas = document.getElementById("pitch");
  var ctx = canvas.getContext("2d");
  var W = canvas.width, H = canvas.height;

  var MARGIN = 20;
  var FIELD_LEFT = MARGIN, FIELD_RIGHT = W - MARGIN;
  var FIELD_TOP = MARGIN, FIELD_BOTTOM = H - MARGIN;

  var GOAL_TOP = H / 2 - 60, GOAL_BOTTOM = H / 2 + 60;
  var GOAL_LINE_X = FIELD_RIGHT;
  var GOAL_DEPTH = 20;

  var START_X = 90, START_Y = H / 2;

  // Defenders never set foot inside these strips: one part-way across the
  // pitch to catch your breath after the flank defenders, and one right
  // in front of the keeper where it's just you against the goalkeeper.
  var SAFE_ZONES = [
    { x1: 360, x2: 420 },            // midfield breather
    { x1: GOAL_LINE_X - 90, x2: GOAL_LINE_X } // in front of the goal
  ];

  function isInSafeZone(x) {
    return SAFE_ZONES.some(function (z) { return x >= z.x1 && x <= z.x2; });
  }

  // Keeps a defender from ever stepping inside a safe zone: if its next
  // step would land inside one, it's stopped right at the edge it was
  // approaching from instead.
  function clampOutOfSafeZones(newX, prevX) {
    for (var i = 0; i < SAFE_ZONES.length; i++) {
      var z = SAFE_ZONES[i];
      if (newX > z.x1 && newX < z.x2) {
        return (prevX <= z.x1) ? z.x1 : z.x2;
      }
    }
    return newX;
  }

  var PLAYER_SPEED = 220;    // px/s
  var DEFENDER_SPEED = 128;  // px/s
  var KEEPER_SPEED = 170;    // px/s
  var SHOT_SPEED = 480;      // px/s -- how fast a struck ball travels
  var DRIBBLE_OFFSET = 17;   // px the ball sits ahead of the player while dribbling
  var PLAYER_R = 11, DEFENDER_R = 11, KEEPER_R = 12, BALL_R = 7;
  var TACKLE_DIST = PLAYER_R + BALL_R + 4;   // how close a defender must get to the ball to win it
  var KEEPER_CATCH_DIST = KEEPER_R + BALL_R + 6;
  var COLLECT_DIST = PLAYER_R + BALL_R + 4;  // how close you must get to reclaim a shot that's bounced back

  var statusLine = document.getElementById("statusLine");
  var scoreLine = document.getElementById("scoreLine");
  var restartBtn = document.getElementById("restartBtn");

  // ---- Entities ----
  // Two flankers plus one straight up the middle, so a straight run at
  // goal always runs into someone -- you have to actually juke around
  // them, spread across the open middle of the pitch.
  function makeDefenders() {
    return [
      { homeX: 300, homeY: 170, x: 300, y: 170 },
      { homeX: 300, homeY: 330, x: 300, y: 330 },
      { homeX: 480, homeY: 250, x: 480, y: 250 }
    ];
  }

  var player, ball, defenders, keeper;
  var goals = 0, attempts = 0;
  var invulnerableUntil = 0; // timestamp (ms) -- ignore collisions until then, right after a reset
  var gameStarted = false;   // defenders stay put until you make your first move
  var bigMessage = null;     // { text, color, until } -- big banner shown after each round ends

  // keepPlayer: true after a shot/tackle -- the player holds their ground
  // and the ball comes back to them, rather than being sent all the way
  // back to the kickoff spot. Only a full Restart resets the player too.
  function resetPositions(keepPlayer) {
    if (!keepPlayer || !player) {
      player = { x: START_X, y: START_Y, facing: 0 };
    }
    ball = {
      x: player.x + Math.cos(player.facing) * DRIBBLE_OFFSET,
      y: player.y + Math.sin(player.facing) * DRIBBLE_OFFSET,
      mode: "dribble", vx: 0, vy: 0, bounced: false
    };
    defenders = makeDefenders();
    keeper = { x: GOAL_LINE_X - 10, y: H / 2 };
    invulnerableUntil = performance.now() + 500;
    gameStarted = false;
  }
  resetPositions(false);

  // ---- Input ----
  var keys = {};
  var MOVE_KEYS = {
    ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0],
    w: [0, -1], s: [0, 1], a: [-1, 0], d: [1, 0],
    W: [0, -1], S: [0, 1], A: [-1, 0], D: [1, 0]
  };

  function onKeyDown(e) {
    if (MOVE_KEYS[e.key]) {
      keys[e.key] = true;
      gameStarted = true; // defenders wake up the moment a movement key is pressed
      e.preventDefault();
    } else if (e.code === "Space") {
      shoot();
      e.preventDefault();
    }
  }
  function onKeyUp(e) {
    if (MOVE_KEYS[e.key]) {
      keys[e.key] = false;
      e.preventDefault();
    }
  }

  // Which way a shot would currently go: toward the mouse/touchpad
  // pointer if it's been used at all (so you can run one way and place
  // the shot somewhere else entirely), otherwise whichever way you're
  // facing from your last move.
  function aimAngle() {
    if (mouse.active) {
      return Math.atan2(mouse.y - player.y, mouse.x - player.x);
    }
    return player.facing;
  }

  // Strike the ball toward the current aim direction, sending it off on
  // its own at SHOT_SPEED instead of staying glued to the player. Only
  // has an effect while a ball is being dribbled.
  function shoot() {
    if (ball.mode !== "dribble") return;
    var angle = aimAngle();
    ball.mode = "flying";
    ball.bounced = false; // only reclaimable by touch after it's bounced off a touchline
    ball.vx = Math.cos(angle) * SHOT_SPEED;
    ball.vy = Math.sin(angle) * SHOT_SPEED;
  }
  // Listening on both document and window covers browsers/embedded
  // viewers that route keyboard events slightly differently.
  document.addEventListener("keydown", onKeyDown);
  document.addEventListener("keyup", onKeyUp);
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);

  canvas.addEventListener("click", function () { canvas.focus(); shoot(); });
  // Try to grab keyboard focus as soon as the page loads -- some viewers
  // (e.g. an embedded preview) give focus to the page shell rather than
  // the canvas until something inside it is clicked.
  window.addEventListener("load", function () { canvas.focus(); });
  canvas.focus();

  // ---- Mouse / touchpad steering: move the pointer around the pitch and
  // the player heads toward it -- no keyboard needed. Keyboard input, if
  // used, always takes priority over the pointer for that frame.
  var mouse = { x: 0, y: 0, active: false };
  var MOUSE_DEADZONE = 5; // px -- stop chasing the pointer once this close, to avoid jitter
  var lastMouseX = null, lastMouseY = null; // our own previous sample, used to detect real dragging

  function updateMouseFromEvent(e) {
    var rect = canvas.getBoundingClientRect();
    mouse.x = (e.clientX - rect.left) * (canvas.width / rect.width);
    mouse.y = (e.clientY - rect.top) * (canvas.height / rect.height);
    mouse.active = true;

    // Only an actual drag of the pointer counts as "playing" and wakes the
    // defenders -- the cursor merely landing on the canvas (e.g. right
    // after the page loads, or the focusing click) shouldn't trigger
    // anything. We compare against our own last sample rather than the
    // browser's movementX/Y, which can report a large jump on the very
    // first event and wake things up on their own.
    if (lastMouseX !== null) {
      var moved = Math.abs(mouse.x - lastMouseX) + Math.abs(mouse.y - lastMouseY);
      if (moved > 3) gameStarted = true;
    }
    lastMouseX = mouse.x;
    lastMouseY = mouse.y;
  }
  canvas.addEventListener("mousemove", updateMouseFromEvent);
  canvas.addEventListener("mouseleave", function () {
    mouse.active = false;
    lastMouseX = null; // forget it, so re-entering isn't treated as a drag
    lastMouseY = null;
  });

  function inputVector() {
    var dx = 0, dy = 0;
    for (var k in keys) {
      if (keys[k] && MOVE_KEYS[k]) {
        dx += MOVE_KEYS[k][0];
        dy += MOVE_KEYS[k][1];
      }
    }
    var len = Math.hypot(dx, dy);
    if (len > 0) { dx /= len; dy /= len; return { x: dx, y: dy }; }

    if (mouse.active) {
      var mdx = mouse.x - player.x, mdy = mouse.y - player.y;
      var mlen = Math.hypot(mdx, mdy);
      if (mlen > MOUSE_DEADZONE) { return { x: mdx / mlen, y: mdy / mlen }; }
    }
    return { x: 0, y: 0 };
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // ---- Round outcomes ----
  function endRound(kind) {
    attempts += 1;
    var text, cls;
    if (kind === "goal") {
      goals += 1;
      text = "GOAL!";
      cls = "good";
    } else if (kind === "tackled") {
      text = "Tackled! Try again.";
      cls = "bad";
    } else if (kind === "saved") {
      text = "Saved by the keeper!";
      cls = "bad";
    } else {
      text = "Out of play.";
      cls = "bad";
    }
    statusLine.innerHTML = "<span class=\"result " + cls + "\">" + text + "</span>";
    scoreLine.textContent = "Goals: " + goals + " / Attempts: " + attempts;

    bigMessage = {
      text: kind === "goal" ? "GOAL!" : "GAME OVER",
      color: kind === "goal" ? "#2e7d32" : "#c62828",
      until: performance.now() + 2000
    };

    // Every round -- goal or game over -- sends you back to the kickoff
    // spot to start the next attempt fresh.
    resetPositions(false);
  }

  restartBtn.addEventListener("click", function () {
    goals = 0;
    attempts = 0;
    statusLine.textContent = "Restarted. Go get 'em!";
    scoreLine.textContent = "Goals: 0 / Attempts: 0";
    bigMessage = null;
    resetPositions(false); // Restart sends you back to the kickoff spot
  });

  // ---- Update ----
  var lastTime = null;

  function update(now) {
    if (lastTime === null) lastTime = now;
    var dt = Math.min((now - lastTime) / 1000, 0.05); // clamp so a slow frame can't teleport things
    lastTime = now;

    var move = inputVector();
    if (move.x !== 0 || move.y !== 0) {
      player.facing = Math.atan2(move.y, move.x);
    }
    player.x = clamp(player.x + move.x * PLAYER_SPEED * dt, FIELD_LEFT, FIELD_RIGHT);
    player.y = clamp(player.y + move.y * PLAYER_SPEED * dt, FIELD_TOP, FIELD_BOTTOM);

    if (ball.mode === "dribble") {
      ball.x = player.x + Math.cos(player.facing) * DRIBBLE_OFFSET;
      ball.y = player.y + Math.sin(player.facing) * DRIBBLE_OFFSET;
    } else {
      // A struck ball travels on its own, bouncing off the touchlines.
      ball.x += ball.vx * dt;
      ball.y += ball.vy * dt;
      if (ball.y < FIELD_TOP) { ball.y = FIELD_TOP; ball.vy = Math.abs(ball.vy); ball.bounced = true; }
      if (ball.y > FIELD_BOTTOM) { ball.y = FIELD_BOTTOM; ball.vy = -Math.abs(ball.vy); ball.bounced = true; }
      if (ball.x < FIELD_LEFT) {
        endRound("out");
        return;
      }

      // Once a shot has bounced off a touchline, you can chase it down
      // and get it back -- otherwise it's committed until it scores,
      // goes out, or a defender wins it.
      if (ball.bounced && Math.hypot(player.x - ball.x, player.y - ball.y) < COLLECT_DIST) {
        ball.mode = "dribble";
        ball.x = player.x + Math.cos(player.facing) * DRIBBLE_OFFSET;
        ball.y = player.y + Math.sin(player.facing) * DRIBBLE_OFFSET;
        statusLine.textContent = "Got it back!";
        return;
      }
    }

    // Defenders stand completely still until you make your first move --
    // no need to size them up before you've even started. Once awake,
    // they attack: always charging straight at the ball rather than
    // waiting for you to wander into range, but never into a safe zone.
    if (gameStarted) {
      defenders.forEach(function (d) {
        var ballIsSafe = isInSafeZone(ball.x);
        var targetX = ballIsSafe ? d.homeX : ball.x;
        var targetY = ballIsSafe ? d.homeY : ball.y;
        var dx = targetX - d.x, dy = targetY - d.y;
        var len = Math.hypot(dx, dy);
        var prevX = d.x;
        if (len > 1) {
          d.x += (dx / len) * DEFENDER_SPEED * dt;
          d.y += (dy / len) * DEFENDER_SPEED * dt;
        }
        d.x = clampOutOfSafeZones(d.x, prevX);
      });
    }

    // Keeper tracks the ball's height, staying on the goal line.
    var targetKeeperY = clamp(ball.y, GOAL_TOP + KEEPER_R, GOAL_BOTTOM - KEEPER_R);
    var dyk = targetKeeperY - keeper.y;
    if (Math.abs(dyk) > 1) {
      keeper.y += Math.sign(dyk) * Math.min(Math.abs(dyk), KEEPER_SPEED * dt);
    }

    if (now < invulnerableUntil) return;

    // Tackles
    for (var i = 0; i < defenders.length; i++) {
      var d = defenders[i];
      if (Math.hypot(d.x - ball.x, d.y - ball.y) < TACKLE_DIST) {
        endRound("tackled");
        return;
      }
    }

    // Ball crossing the goal line
    if (ball.x >= GOAL_LINE_X) {
      if (ball.y >= GOAL_TOP && ball.y <= GOAL_BOTTOM) {
        if (Math.hypot(keeper.x - ball.x, keeper.y - ball.y) < KEEPER_CATCH_DIST) {
          endRound("saved");
        } else {
          endRound("goal");
        }
      } else {
        endRound("out");
      }
    }
  }

  // ---- Draw ----
  function drawPitch() {
    ctx.fillStyle = "#2e8b3d";
    ctx.fillRect(0, 0, W, H);

    // Safe zone shading: strips where the field defenders never set foot.
    ctx.fillStyle = "rgba(255,255,255,0.12)";
    SAFE_ZONES.forEach(function (z) {
      ctx.fillRect(z.x1, FIELD_TOP, z.x2 - z.x1, FIELD_BOTTOM - FIELD_TOP);
    });

    ctx.strokeStyle = "#eafff0";
    ctx.lineWidth = 2;
    ctx.strokeRect(FIELD_LEFT, FIELD_TOP, FIELD_RIGHT - FIELD_LEFT, FIELD_BOTTOM - FIELD_TOP);

    // true halfway line + centre circle (just pitch markings)
    var midX = (FIELD_LEFT + FIELD_RIGHT) / 2;
    ctx.beginPath();
    ctx.moveTo(midX, FIELD_TOP);
    ctx.lineTo(midX, FIELD_BOTTOM);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(midX, H / 2, 45, 0, Math.PI * 2);
    ctx.stroke();

    // safe-zone boundaries (dashed), each with its own label
    SAFE_ZONES.forEach(function (z) {
      ctx.save();
      ctx.setLineDash([8, 6]);
      ctx.beginPath();
      ctx.moveTo(z.x1, FIELD_TOP);
      ctx.lineTo(z.x1, FIELD_BOTTOM);
      ctx.moveTo(z.x2, FIELD_TOP);
      ctx.lineTo(z.x2, FIELD_BOTTOM);
      ctx.stroke();
      ctx.restore();

      ctx.save();
      ctx.fillStyle = "rgba(255,255,255,0.8)";
      ctx.font = "10px -apple-system, sans-serif";
      ctx.textAlign = "center";
      ctx.translate((z.x1 + z.x2) / 2, H / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText("SAFE ZONE", 0, 0);
      ctx.restore();
    });

    // goal mouth + net
    ctx.strokeRect(GOAL_LINE_X, GOAL_TOP, GOAL_DEPTH, GOAL_BOTTOM - GOAL_TOP);
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.lineWidth = 1;
    for (var gy = GOAL_TOP; gy <= GOAL_BOTTOM; gy += 12) {
      ctx.beginPath();
      ctx.moveTo(GOAL_LINE_X, gy);
      ctx.lineTo(GOAL_LINE_X + GOAL_DEPTH, gy);
      ctx.stroke();
    }
    for (var gx = GOAL_LINE_X; gx <= GOAL_LINE_X + GOAL_DEPTH; gx += 10) {
      ctx.beginPath();
      ctx.moveTo(gx, GOAL_TOP);
      ctx.lineTo(gx, GOAL_BOTTOM);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawPerson(x, y, facing, radius, jerseyColor) {
    ctx.save();
    ctx.translate(x, y);
    // body
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.fillStyle = jerseyColor;
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.35)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    // facing indicator
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(facing) * (radius + 6), Math.sin(facing) * (radius + 6));
    ctx.strokeStyle = "rgba(0,0,0,0.6)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();
  }

  function drawBall(x, y) {
    ctx.save();
    ctx.translate(x, y);
    ctx.beginPath();
    ctx.arc(0, 0, BALL_R, 0, Math.PI * 2);
    ctx.fillStyle = "#fdfdfd";
    ctx.fill();
    ctx.strokeStyle = "#222";
    ctx.lineWidth = 1.1;
    ctx.stroke();
    var pr = BALL_R * 0.42;
    ctx.beginPath();
    for (var i = 0; i < 5; i++) {
      var ang = -Math.PI / 2 + i * (2 * Math.PI / 5);
      var px = pr * Math.cos(ang), py = pr * Math.sin(ang);
      if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = "#222";
    ctx.fill();
    ctx.restore();
  }

  function drawAimLine() {
    if (ball.mode !== "dribble" || !mouse.active) return;
    var angle = aimAngle();
    var len = 55;
    ctx.save();
    ctx.setLineDash([5, 5]);
    ctx.strokeStyle = "rgba(255,255,255,0.8)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(ball.x, ball.y);
    ctx.lineTo(ball.x + Math.cos(angle) * len, ball.y + Math.sin(angle) * len);
    ctx.stroke();
    ctx.restore();
  }

  function drawBigMessage(now) {
    if (!bigMessage || now >= bigMessage.until) return;
    ctx.save();
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(0, H / 2 - 46, W, 92);
    ctx.font = "bold 56px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = bigMessage.color;
    ctx.fillText(bigMessage.text, W / 2, H / 2);
    ctx.restore();
  }

  function draw(now) {
    drawPitch();
    defenders.forEach(function (d) { drawPerson(d.x, d.y, 0, DEFENDER_R, "#c62828"); });
    drawPerson(keeper.x, keeper.y, 0, KEEPER_R, "#f9d71c");
    drawPerson(player.x, player.y, player.facing, PLAYER_R, "#1565c0");
    drawBall(ball.x, ball.y);
    drawAimLine();
    drawBigMessage(now);
  }

  function loop(now) {
    update(now);
    draw(now);
    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);
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
