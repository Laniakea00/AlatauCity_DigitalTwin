#!/usr/bin/env python3
"""Independent reviewer: Gemini 4 Argon (thinking high) checks a worker's change against its task.
usage: gemini_review.py --task task.md --repo /path/to/worktree [--base baseline] [--img a.png ...] [--out review.json]
Sends the task, the git diff against --base and the full text of every changed file (C#/shader/uss/json/md),
returns JSON {verdict: pass|fail, summary, issues:[{severity, file, line, problem, fix}]}."""
import argparse, json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from gemini import ask
ap = argparse.ArgumentParser()
ap.add_argument('--task', required=True); ap.add_argument('--repo', required=True); ap.add_argument('--base', default='baseline')
ap.add_argument('--img', nargs='*', default=[]); ap.add_argument('--out'); ap.add_argument('--model', default='gemini-4-argon')
ap.add_argument('--extra', default='')
a = ap.parse_args()
git = lambda *x: subprocess.run(['git', '-C', a.repo, *x], capture_output=True, text=True).stdout
base = git('rev-parse', a.base).strip() or a.base
diff = git('diff', base, '--', '.')
untracked = git('ls-files', '--others', '--exclude-standard').split()
changed = [f for f in git('diff', '--name-only', base).split() if os.path.exists(os.path.join(a.repo, f))] + untracked
ctx = []
budget = 900_000
for f in changed:
    if not f.endswith(('.cs', '.shader', '.cginc', '.uss', '.json', '.md', '.py', '.html', '.txt')): continue
    t = open(os.path.join(a.repo, f), encoding='utf-8', errors='replace').read()
    if len(t) > 250_000: t = t[:250_000] + '\n...[truncated]'
    if budget - len(t) < 0: break
    budget -= len(t); ctx.append(f'===== FILE {f} (after the change) =====\n{t}')
for f in untracked:
    diff += f'\n+++ new file {f}\n'
task = open(a.task, encoding='utf-8').read()
prompt = f"""You are the independent reviewer in a team: an orchestrator gave a task to a developer agent; you check the result before it goes to the client.
Project: a Unity 6000.0 (Built-in render pipeline, UI Toolkit, C# 9, WebGL 2 + Windows builds) digital twin of the new city Alatau City (Kazakhstan), shown to investors and the government.
The UI text is Russian; a runtime translator maps Russian strings to English/Kazakh. Data are open sources plus clearly labelled synthetic models; no claims of "real data".

Judge ONLY against the task and against correctness. Look for: compile errors (wrong Unity API, missing usings, wrong types), runtime errors (null refs, index errors, division by zero, infinite loops),
logic bugs, things the task asked for that are missing or faked, numbers/dates that contradict the task or each other, any remaining year 2025 shown as "now" or as the start of the timeline,
text that misleads an investor (unlabelled synthetic numbers presented as fact), broken WebGL compatibility (threads, System.IO on web, compute shaders), and edits outside the files the task allowed.
Do not nitpick style. Severity: blocker (must fix before shipping), major (should fix now), minor (optional).
Return JSON only: {{"verdict":"pass"|"fail","summary":"<2-4 sentences>","issues":[{{"severity":"blocker|major|minor","file":"...","line":0,"problem":"...","fix":"..."}}]}}
verdict is "fail" if there is any blocker or major issue.

===== TASK =====
{task}
{a.extra}
===== DIFF against the baseline =====
{diff[:400_000]}
===== CHANGED FILES (full text) =====
{chr(10).join(ctx)}
"""
out = ask(a.model, prompt, images=a.img, json_out=True, thinking='high')
try: res = json.loads(out)
except Exception: res = {'verdict': 'fail', 'summary': 'reviewer returned non-JSON', 'raw': out[:4000], 'issues': []}
s = json.dumps(res, ensure_ascii=False, indent=1)
if a.out: open(a.out, 'w', encoding='utf-8').write(s)
print(s)
