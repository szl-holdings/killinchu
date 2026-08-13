/* Three.js r160 compatibility for deferred globe/graph UMD bundles. */
(function () {
  "use strict";
  if (typeof THREE === "undefined" || THREE.Timer) return;

  function Timer() {
    this._previousTime = 0;
    this._currentTime = 0;
    this._delta = 0;
    this._elapsed = 0;
    this._timescale = 1;
    this._usePageVisibility = false;
  }

  Timer.prototype.getDelta = function () { return this._delta; };
  Timer.prototype.getElapsed = function () { return this._elapsed; };
  Timer.prototype.getTimescale = function () { return this._timescale; };
  Timer.prototype.setTimescale = function (value) {
    this._timescale = value;
    return this;
  };
  Timer.prototype.reset = function () {
    this._currentTime = typeof performance !== "undefined" ? performance.now() : Date.now();
    return this;
  };
  Timer.prototype.dispose = function () { return this; };
  Timer.prototype.connect = function () { return this; };
  Timer.prototype.disconnect = function () { return this; };
  Timer.prototype.update = function (timestamp) {
    this._previousTime = this._currentTime;
    this._currentTime = timestamp !== undefined
      ? timestamp
      : (typeof performance !== "undefined" ? performance.now() : Date.now());
    var delta = (this._currentTime - this._previousTime) / 1000;
    if (!isFinite(delta) || delta < 0) delta = 0;
    if (delta > 0.2) delta = 0.2;
    this._delta = delta * this._timescale;
    this._elapsed += this._delta;
    return this;
  };

  THREE.Timer = Timer;
})();
