"""Apply exact, asserted chart changes to the guarded source checkout."""
from pathlib import Path
import ast
import shutil

ROOT = Path(r'C:\Users\g_med\.codex\worktrees\guarded-research\GNET')
def replace(name, old, new):
    path = ROOT / name
    content = path.read_text(encoding='utf-8')
    assert content.count(old) == 1, (name, old[:100], content.count(old))
    before = ast.parse(content) if path.suffix == '.py' else None
    path.write_text(content.replace(old, new), encoding='utf-8')
    if before:
        names = lambda tree: [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        assert names(before) == names(ast.parse(path.read_text(encoding='utf-8'))), name

replace('gnet_jobs/contracts.py', "'page_size':{**POSITIVE,'maximum':20},'max_points':{**POSITIVE,'minimum':20,'maximum':500},", "'page_size':{**POSITIVE,'maximum':20},'max_points':{**POSITIVE,'minimum':20,'maximum':500},\n    'chart_offset':{**NONNEGATIVE,'maximum':1000000},")
replace('gnet_broker/ts_primary_view.py', 'def native_chart(bars_path, selected, max_points, window_trades=None):', 'def native_chart(bars_path, selected, max_points, window_trades=None, chart_offset=0):')
replace('gnet_broker/ts_primary_view.py', "    start = max(1, min(t['signal_row'] for t in window_trades) - 5)\n    stops = [(t['exit_row'] if t['status'] == 'closed' else t['entry_row'] + 20) for t in window_trades]\n    stop = max(max(stops), max(t['entry_row'] for t in window_trades)) + 5\n    if stop - start + 1 > max_points:\n        raise ContractError('viewport_limit', 'Selected TS trade spans more bars than the chart cap; select a shorter trade')", "    start = max(1, min(t['signal_row'] for t in window_trades) - 5) + chart_offset\n    stop = start + max_points - 1")
replace('gnet_broker/ts_primary_view.py', "    candles = []\n    with Path(bars_path)", "    candles = []\n    has_more = False\n    with Path(bars_path)")
replace('gnet_broker/ts_primary_view.py', '            if index > stop:\n                break', '            if index > stop:\n                has_more = True\n                break')
replace('gnet_broker/ts_primary_view.py', "    overlay = {**selected, 'signal_price': available[anchor]['close'],\n        'signal_stamp': available[anchor]['stamp'],", "    overlay = {**selected, 'chart_has_more': has_more, 'signal_price': available.get(anchor, {}).get('close'),\n        'signal_stamp': available.get(anchor, {}).get('stamp'),")
replace('gnet_broker/ts_primary_view.py', "request.payload.get('max_points', 2000), chart_window)", "request.payload.get('max_points', 500), chart_window, request.payload.get('chart_offset', 0))")
replace('gnet_broker/ts_primary_view.py', "'page': page, 'chart': candles, 'selected': overlay, 'matching_count': total,", "'page': page, 'chart': candles, 'selected': overlay, 'chart_has_more': bool(overlay and overlay['chart_has_more']), 'matching_count': total,")
replace('gnet_broker/ts_primary_view.html', 'data.payload.max_points||2000', 'data.payload.max_points||500')
replace('gnet_broker/dataset_chart_page.html', '<option>100</option><option>200</option><option>500</option>', '<option>100</option><option>200</option><option selected>500</option>')
replace('gnet_jobs/client_deploy.py', "'gnet_broker/final_workbench.js',", "'gnet_broker/final_workbench.js','gnet_broker/scrolling_bar_viewer.js','gnet_broker/lightweight_charts.js',")
replace('gnet_jobs/view_server.py', '"/research/assets/engine-candle-colors.js"):', '"/research/assets/engine-candle-colors.js", "/research/assets/scrolling-bar-viewer.js", "/research/assets/lightweight-charts.js"):')
replace('gnet_jobs/view_server.py', '                        "/research/assets/engine-candle-colors.js": ("engine_candle_colors.js", "text/javascript; charset=utf-8"),', '                        "/research/assets/engine-candle-colors.js": ("engine_candle_colors.js", "text/javascript; charset=utf-8"),\n                        "/research/assets/scrolling-bar-viewer.js": ("scrolling_bar_viewer.js", "text/javascript; charset=utf-8"),\n                        "/research/assets/lightweight-charts.js": ("lightweight_charts.js", "text/javascript; charset=utf-8"),')
replace('gnet_jobs/view_server.py', '                    if len(content) > 65536:\n                        raise ContractError("output_limit", "Workbench asset exceeds byte cap")', '                    if len(content) > (524288 if name == "lightweight_charts.js" else 65536):\n                        raise ContractError("output_limit", "Workbench asset exceeds byte cap")')
replace('gnet_jobs/view_server.py', '                self.send(200, content, "text/html; charset=utf-8")\n            except (ContractError, OSError):', '                if parts[2] in ("native_trades.html", "viewer.html", "dataset_chart.html"):\n                    marker = b"</body>"\n                    if content.count(marker) != 1:\n                        raise ContractError("report_shape", "Report body marker differs")\n                    scripts = b\'<script src="/research/assets/lightweight-charts.js"></script><script src="/research/assets/scrolling-bar-viewer.js"></script>\'\n                    content = content.replace(marker, scripts + marker, 1)\n                self.send(200, content, "text/html; charset=utf-8")\n            except (ContractError, OSError):')
shutil.copyfile(Path(__file__).with_name('scrolling_bar_viewer.js'), ROOT/'gnet_broker/scrolling_bar_viewer.js')
print('Patched all three viewer routes; top-level Python definitions preserved.')
