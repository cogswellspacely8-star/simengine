#!/usr/bin/env python3
"""
SimEngine Web UI — zero-dependency local server.
Run: python server.py
Open: http://localhost:8420
"""

import json, os, sys, time, copy, glob, math, statistics, re
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kernel import (
    DomainConfig, run_monte_carlo, evaluate_safety,
    compute_fitness, evolve, percentile, SAMPLERS, indicator_probability
)
from bayesian import update_config, update_parameter
from diagnostics import (
    convergence_analysis, sensitivity_analysis,
    deterministic_baseline, compare_to_baseline
)

try:
    import native as native_runtime
except Exception:
    native_runtime = None

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
                "context": data.get("context", {}),
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


def _get_native_backend():
    if native_runtime is None:
        return None
    try:
        return native_runtime.get_native_backend()
    except Exception:
        return None


def build_histograms(raw_metrics, stats, n_bins=40):
    native_backend = _get_native_backend()
    if native_backend is not None:
        try:
            return native_backend.build_histograms(raw_metrics, n_bins)
        except Exception:
            pass

    histograms = {}
    for metric, values in raw_metrics.items():
        if not values:
            continue
        sv = sorted(values)
        lo, hi = sv[0], sv[-1]
        if lo == hi:
            histograms[metric] = {"bins": [lo], "counts": [len(sv)], "lo": lo, "hi": hi}
            continue
        bin_width = (hi - lo) / n_bins
        bins = [lo + i * bin_width for i in range(n_bins)]
        counts = [0] * n_bins
        for v in sv:
            idx = min(int((v - lo) / bin_width), n_bins - 1)
            counts[idx] += 1
        histograms[metric] = {
            "bins": [round(b, 4) for b in bins],
            "counts": counts,
            "bin_width": round(bin_width, 4),
            "lo": round(lo, 2),
            "hi": round(hi, 2),
        }
    return histograms


def generate_narrative(stats, safety, config_data):
    lines = []
    context = config_data.get("context", {})

    if context.get("decision"):
        lines.append(f"**The question:** {context['decision']}")
        lines.append("")

    for mname, s in stats.items():
        label = mname.replace("_", " ").title()

        prob = indicator_probability(s)
        if prob is not None:
            lines.append(
                f"**{label}**: about {prob * 100:.0f}% chance across all simulated scenarios."
            )
            continue

        fmt = s.get("format", "number")
        if fmt == "dollar":
            median_str = f"${s['median']:,.0f}"
            p10_str = f"${s['p10']:,.0f}"
            p90_str = f"${s['p90']:,.0f}"
        elif fmt == "percent":
            median_str = f"{s['median']*100:.1f}%"
            p10_str = f"{s['p10']*100:.1f}%"
            p90_str = f"{s['p90']*100:.1f}%"
        else:
            median_str = f"{s['median']:,.1f}"
            p10_str = f"{s['p10']:,.1f}"
            p90_str = f"{s['p90']:,.1f}"

        lines.append(
            f"**{label}** is most likely {median_str} "
            f"(range: {p10_str} to {p90_str} in 80% of scenarios)."
        )

    if safety:
        lines.append("")
        if safety.get("all_passed", True):
            lines.append("All safety constraints pass. The current configuration is within acceptable risk bounds.")
        else:
            violations = []
            for c in safety.get("chance", []):
                if not c["passed"]:
                    violations.append(
                        f"There is a {c['actual_prob']*100:.0f}% chance of "
                        f"{c['metric'].replace('_',' ')} falling {c['condition']} "
                        f"{c['threshold']:,.0f} (limit: {c['max_prob']*100:.0f}%)"
                    )
            for c in safety.get("cvar", []):
                if not c["passed"]:
                    violations.append(
                        f"In the worst {c['alpha']*100:.0f}% of scenarios, "
                        f"{c['metric'].replace('_',' ')} averages "
                        f"${c['actual_cvar']:,.0f} (limit: ${c['min_cvar']:,.0f})"
                    )
            lines.append("**Risk warnings:**")
            for v in violations:
                lines.append(f"- {v}")

    if context.get("what_good_looks_like"):
        lines.append("")
        lines.append(f"**What good looks like:** {context['what_good_looks_like']}")

    return "\n".join(lines)


# Canonical config validation now lives in validation.py (shared with the LLM compiler).
from validation import validate_config


def handle_ask(body, _complete=None):
    """Natural-language question -> config -> run -> explanation.

    Returns (payload, status). The llm/ module is opt-in: if it cannot be
    imported or the backend is unreachable, this returns a clean error instead
    of taking down the rest of the server.
    """
    question = (body.get("question") or "").strip()
    if not question:
        return {"error": "Provide a 'question' describing your decision."}, 400
    try:
        from llm.ask import answer_question
        from llm.backends import LLMError
    except Exception as e:  # pragma: no cover - import-time failure is environmental
        return {"error": f"LLM module unavailable: {e}"}, 503
    try:
        res = answer_question(
            question,
            n_simulations=body.get("n_simulations"),
            seed=body.get("seed", 42),
            backend=body.get("backend"),
            model=body.get("model"),
            clarify=body.get("clarify", True),
            coverage=body.get("coverage", True),
            _complete=_complete,
        )
    except LLMError as e:
        return {"error": str(e), "backend_unavailable": True}, 503
    ok = res.get("valid") or res.get("needs_clarification")
    return res, (200 if ok else 422)


def handle_schema():
    """Serve the published JSON Schema for the domain config (the contract)."""
    path = os.path.join(os.path.dirname(__file__), "schema", "domain.schema.json")
    try:
        with open(path) as f:
            return json.load(f), 200
    except Exception as e:
        return {"error": f"schema unavailable: {e}"}, 404


def _ledger():
    from calibration import CalibrationLedger
    db = os.environ.get("SIMENGINE_LEDGER_DB", os.path.join(os.path.dirname(__file__), "forecasts.db"))
    return CalibrationLedger(db)


def handle_forecast_record(body):
    """Log a forecast (predicted probability of a future binary outcome)."""
    question = (body.get("question") or "").strip()
    if not question:
        return {"error": "Provide 'question'"}, 400
    try:
        prob = float(body.get("predicted_prob"))
    except (TypeError, ValueError):
        return {"error": "Provide numeric 'predicted_prob' in [0, 1]"}, 400
    if not 0.0 <= prob <= 1.0:
        return {"error": "predicted_prob must be in [0, 1]"}, 400
    fid = _ledger().record(question, prob, metric=body.get("metric"),
                           config_hash=body.get("config_hash"), resolve_by=body.get("resolve_by"))
    return {"id": fid, "question": question, "predicted_prob": prob,
            "resolve_by": body.get("resolve_by")}, 200


def handle_resolve(body):
    """Record the real outcome (0 or 1) for a logged forecast and return the score."""
    fid = body.get("id")
    if fid is None:
        return {"error": "Provide 'id'"}, 400
    try:
        outcome = int(body.get("outcome"))
    except (TypeError, ValueError):
        return {"error": "Provide 'outcome' (0 or 1)"}, 400
    led = _ledger()
    try:
        led.resolve(fid, outcome)
    except KeyError:
        return {"error": f"No forecast with id {fid}"}, 404
    except ValueError as e:
        return {"error": str(e)}, 400
    return {"id": fid, "outcome": outcome, "score": led.score()}, 200


def handle_forecasts_list():
    """All logged forecasts (pending + resolved) plus the running Brier/log-loss."""
    led = _ledger()
    return {"forecasts": led.all_forecasts(), "score": led.score()}, 200


def handle_llm_status(_get=None):
    """Report every backend + model (with readiness) so the UI can offer a full
    picker, not just the active backend. Returns (payload, status)."""
    from llm import backends
    active = os.environ.get("SIMENGINE_LLM_BACKEND", "ollama").lower()
    installed = backends.list_ollama_models(_get=_get)
    key_env = {"openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

    options = []
    for m in installed:
        options.append({"backend": "ollama", "model": m, "label": m + " — local", "ready": True, "needs": None})
    for b, models in backends.KNOWN_MODELS.items():
        env = key_env.get(b, "")
        ready = bool(os.environ.get(env)) or (b == "deepseek" and bool(os.environ.get("OPENAI_API_KEY")))
        for m in models:
            options.append({
                "backend": b, "model": m,
                "label": f"{m} — {b}" + ("" if ready else f" (needs {env})"),
                "ready": ready, "needs": None if ready else env,
            })

    configured = os.environ.get("SIMENGINE_LLM_MODEL") or backends.DEFAULT_MODELS.get(active, "qwen2.5")
    if active == "ollama":
        configured = backends.suggest_ollama_model(preferred=configured, _get=_get) or configured

    active_models = [o["model"] for o in options if o["backend"] == active]
    return {
        "active_backend": active,
        "default": {"backend": active, "model": configured},
        "options": options,
        "ollama_running": bool(installed),
        # backward-compatible fields
        "backend": active,
        "installed_models": installed,
        "model_options": active_models or [o["model"] for o in options],
        "default_model": configured,
        "backends": list(backends.DEFAULT_MODELS.keys()),
    }, 200


def save_domain(filename, data):
    """Save a domain config to the domains directory."""
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', filename.replace('.json', ''))
    path = os.path.join(DOMAIN_DIR, safe_name + ".json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return safe_name + ".json"


def generate_report_html(results, config_data):
    """Generate a standalone HTML report."""
    domain = results.get("domain", "Simulation")
    stats = results.get("stats", {})
    safety = results.get("safety", {})
    narrative = results.get("narrative", "")
    ts = time.strftime("%Y-%m-%d %H:%M")

    narrative_html = narrative.replace("**", "<strong>").replace("**", "</strong>")
    # Proper bold tag handling
    import re as _re
    narrative_html = _re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', narrative)
    narrative_html = narrative_html.replace("\n\n", "<br><br>").replace("\n", "<br>")
    narrative_html = _re.sub(r'^- ', '&bull; ', narrative_html, flags=_re.MULTILINE)

    rows = ""
    for mname, s in stats.items():
        f = s.get("format", "number")
        def _f(v):
            if f == "dollar": return f"${v:,.0f}"
            if f == "percent": return f"{v*100:.1f}%"
            return f"{v:,.2f}"
        rows += f"""<tr>
            <td style="font-weight:600">{mname.replace('_',' ').title()}</td>
            <td>{_f(s['median'])}</td><td>{_f(s['mean'])}</td>
            <td>{_f(s['p10'])}</td><td>{_f(s['p90'])}</td><td>{_f(s['std'])}</td>
        </tr>"""

    safety_rows = ""
    for c in safety.get("chance", []):
        status = "PASS" if c["passed"] else "FAIL"
        color = "#22c55e" if c["passed"] else "#ef4444"
        safety_rows += f"""<tr>
            <td><span style="color:{color};font-weight:700">{status}</span></td>
            <td>P({c['metric'].replace('_',' ')} {c['condition']} {c['threshold']:,.0f}) = {c['actual_prob']*100:.1f}%</td>
            <td>max {c['max_prob']*100:.0f}%</td>
        </tr>"""
    for c in safety.get("cvar", []):
        status = "PASS" if c["passed"] else "FAIL"
        color = "#22c55e" if c["passed"] else "#ef4444"
        safety_rows += f"""<tr>
            <td><span style="color:{color};font-weight:700">{status}</span></td>
            <td>CVaR({c['alpha']*100:.0f}%) {c['metric'].replace('_',' ')} = ${c['actual_cvar']:,.0f}</td>
            <td>min ${c['min_cvar']:,.0f}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SimEngine Report — {domain}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0a0e17; color: #e2e8f0; }}
h1 {{ font-size: 22px; border-bottom: 1px solid #2a3550; padding-bottom: 12px; }}
h2 {{ font-size: 14px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; margin-top: 30px; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }}
th {{ text-align: left; color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; padding: 8px; border-bottom: 1px solid #2a3550; }}
td {{ padding: 8px; border-bottom: 1px solid #1a2236; }}
.narrative {{ background: #111827; border: 1px solid #2a3550; border-radius: 8px; padding: 16px; margin: 16px 0; line-height: 1.7; }}
.meta {{ color: #64748b; font-size: 11px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; }}
.fitness {{ font-size: 36px; font-weight: 700; color: #60a5fa; }}
</style></head><body>
<h1>SimEngine Report: {domain}</h1>
<p class="meta">Generated {ts} | {results.get('n_simulations',0):,} simulations | {results.get('elapsed',0)}s</p>

<div class="fitness">Fitness: {results.get('fitness', 0):.1f}</div>

<h2>Narrative Summary</h2>
<div class="narrative">{narrative_html}</div>

<h2>Statistics</h2>
<table>
<tr><th>Metric</th><th>Median</th><th>Mean</th><th>P10</th><th>P90</th><th>Std Dev</th></tr>
{rows}
</table>

{"<h2>Safety Constraints</h2><table><tr><th>Status</th><th>Constraint</th><th>Limit</th></tr>" + safety_rows + "</table>" if safety_rows else ""}

<hr style="border-color:#2a3550;margin-top:40px">
<p class="meta">Generated by SimEngine v3.0 — Monte Carlo Simulation &amp; Decision Intelligence</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

        if path == "/api/schema":
            payload, status = handle_schema()
            self._json_response(payload, status)
            return

        if path == "/api/forecasts":
            payload, status = handle_forecasts_list()
            self._json_response(payload, status)
            return

        if path == "/api/llm/status":
            payload, status = handle_llm_status()
            self._json_response(payload, status)
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
                # Support both file-based and inline configs
                if body.get("config"):
                    data = body["config"]
                else:
                    filename = body.get("domain")
                    data = load_domain(filename)

                overrides = body.get("overrides", {})
                n_sims = body.get("n_simulations", None)
                seed = body.get("seed", 42)

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

                histograms = build_histograms(mc["raw_metrics"], mc["stats"])
                narrative = generate_narrative(mc["stats"], safety, data)

                result = {
                    "domain": mc["domain"],
                    "n_simulations": mc["n_simulations"],
                    "elapsed": round(elapsed, 2),
                    "stats": mc["stats"],
                    "trajectories": mc["trajectories"],
                    "histograms": histograms,
                    "safety": safety,
                    "fitness": fitness,
                    "narrative": narrative,
                    "context": data.get("context", {}),
                }
                self._json_response(result)
            except ValueError as e:
                # Client config error (e.g. unknown safety condition) — 400, matching /api/evolve.
                self._json_response({"error": str(e)}, 400)
            except Exception as e:
                import traceback
                traceback.print_exc()
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
                    "best_controls": result["best_controls"],
                    "best_stats": result["best"]["stats"],
                    "best_safety": result["best"]["safety"],
                    "history": result["history"],
                    "elapsed": round(elapsed, 1),
                })
            except ValueError as e:
                # Unoptimizable input (no fitness/tunable, bad config) — client error.
                self._json_response({"error": str(e)}, 400)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/ask":
            payload, status = handle_ask(body)
            self._json_response(payload, status)
            return

        if path == "/api/forecast":
            payload, status = handle_forecast_record(body)
            self._json_response(payload, status)
            return

        if path == "/api/resolve":
            payload, status = handle_resolve(body)
            self._json_response(payload, status)
            return

        if path == "/api/validate":
            try:
                config = body.get("config", {})
                errors = validate_config(config)
                self._json_response({
                    "valid": len(errors) == 0,
                    "errors": errors,
                })
            except Exception as e:
                self._json_response({"valid": False, "errors": [str(e)]})
            return

        if path == "/api/save-domain":
            try:
                config = body.get("config", {})
                filename = body.get("filename", config.get("name", "custom"))
                errors = validate_config(config)
                if errors:
                    self._json_response({"saved": False, "errors": errors}, 400)
                    return
                saved_name = save_domain(filename, config)
                self._json_response({"saved": True, "file": saved_name})
            except Exception as e:
                self._json_response({"saved": False, "errors": [str(e)]}, 500)
            return

        if path == "/api/update":
            try:
                filename = body.get("domain")
                observations = body.get("observations", {})
                data = load_domain(filename)
                updated_config, report = update_config(data, observations)

                # Run a quick simulation with updated params
                cfg = DomainConfig.from_dict(updated_config)
                mc = run_monte_carlo(cfg, seed=42, n_override=1000)
                safety = evaluate_safety(mc, cfg.safety) if cfg.safety else {}

                self._json_response({
                    "updated_config": updated_config,
                    "update_report": report,
                    "preview_stats": mc["stats"],
                    "preview_safety": safety,
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/report":
            try:
                results = body.get("results", {})
                config_data = body.get("config", {})
                html = generate_report_html(results, config_data)
                self._html_response(html)
            except Exception as e:
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/convergence":
            try:
                if body.get("config"):
                    data = body["config"]
                else:
                    data = load_domain(body.get("domain"))
                cfg = DomainConfig.from_dict(data)
                metric = body.get("metric")
                max_runs = body.get("max_runs", 10000)
                t0 = time.time()
                result = convergence_analysis(cfg, metric=metric, max_runs=max_runs)
                result["elapsed"] = round(time.time() - t0, 2)
                self._json_response(result)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/sensitivity":
            try:
                if body.get("config"):
                    data = body["config"]
                else:
                    data = load_domain(body.get("domain"))
                cfg = DomainConfig.from_dict(data)
                metric = body.get("metric")
                n_base = body.get("n_base", 1000)
                n_perturb = body.get("n_perturb", 10)
                t0 = time.time()
                result = sensitivity_analysis(
                    cfg, metric=metric, n_base=n_base, n_perturb=n_perturb
                )
                result["elapsed"] = round(time.time() - t0, 2)
                self._json_response(result)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json_response({"error": str(e)}, 500)
            return

        if path == "/api/baseline":
            try:
                if body.get("config"):
                    data = body["config"]
                else:
                    data = load_domain(body.get("domain"))
                cfg = DomainConfig.from_dict(data)
                n_sims = body.get("n_simulations", 5000)
                t0 = time.time()
                result = compare_to_baseline(cfg, n_simulations=n_sims)
                result["elapsed"] = round(time.time() - t0, 2)
                self._json_response(result)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json_response({"error": str(e)}, 500)
            return

        self._json_response({"error": "not found"}, 404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    # ThreadingHTTPServer so a slow /api/ask (local models take a while) never
    # blocks the UI from loading or other requests from being served.
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"SimEngine UI running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
