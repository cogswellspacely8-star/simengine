#!/usr/bin/env python3
"""
SimEngine Web UI — zero-dependency local server.
Run: python server.py
Open: http://localhost:8420
"""

import json, os, sys, time, copy, glob
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kernel import (
    DomainConfig, run_monte_carlo, evaluate_safety,
    compute_fitness, evolve
)

DOMAIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "domains")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

def list_domains():
    results = []
    for f in sorted(glob.glob(os.path.join(DOMAIN_DIR, "*.json"))):
        name = os.path.basename(f)
        if name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            results.append({
                "file": name,
                "name": data.get("name", name),
                "description": data.get("description", ""),
                "n_simulations": data.get("n_simulations", 5000),
                "n_steps": data.get("n_steps", 12),
                "step_label": data.get("step_label", "step"),
            })
        except Exception:
            pass
    return results


def load_domain(filename):
    path = os.path.join(DOMAIN_DIR, os.path.basename(filename))
    with open(path) as f:
        return json.load(f)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # quiet logs

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, content):
        body = content.encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            html_path = os.path.join(STATIC_DIR, "index.html")
            with open(html_path) as f:
                self._html_response(f.read())
            return

        if path == "/api/domains":
            self._json_response(list_domains())
            return

        if path.startswith("/api/domain/"):
            filename = path.split("/api/domain/")[1]
            try:
                data = load_domain(filename)
                self._json_response(data)
            except FileNotFoundError:
                self._json_response({"error": "not found"}, 404)
            return

        self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/simulate":
            try:
                filename = body.get("domain")
                overrides = body.get("overrides", {})
                n_sims = body.get("n_simulations", None)
                seed = body.get("seed", 42)

                data = load_domain(filename)

                # Apply parameter overrides
                for key, value in overrides.items():
                    parts = key.split(".")
                    obj = data
                    for p in parts[:-1]:
                        obj = obj[p]
                    obj[parts[-1]] = value

                cfg = DomainConfig.from_dict(data)
                t0 = time.time()
                mc = run_monte_carlo(cfg, seed=seed, n_override=n_sims)
                elapsed = time.time() - t0

                safety = {}
                if cfg.safety:
                    safety = evaluate_safety(mc, cfg.safety)

                fitness = 0
                if cfg.fitness:
                    fitness = compute_fitness(mc, cfg.fitness, cfg.safety)

                result = {
                    "domain": mc["domain"],
                    "n_simulations": mc["n_simulations"],
                    "elapsed": round(elapsed, 2),
                    "stats": mc["stats"],
                    "trajectories": mc["trajectories"],
                    "safety": safety,
                    "fitness": fitness,
                }
                self._json_response(result)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/evolve":
            try:
                filename = body.get("domain")
                generations = body.get("generations", 10)
                population = body.get("population", 15)

                data = load_domain(filename)
                t0 = time.time()
                result = evolve(data, generations=generations,
                                population=population, workers=1, verbose=False)
                elapsed = time.time() - t0

                self._json_response({
                    "domain": result["domain"],
                    "best_fitness": result["best"]["fitness"],
                    "best_stats": result["best"]["stats"],
                    "best_safety": result["best"]["safety"],
                    "history": result["history"],
                    "elapsed": round(elapsed, 1),
                })
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        self._json_response({"error": "not found"}, 404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"SimEngine UI running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
