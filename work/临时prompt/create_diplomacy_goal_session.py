"""Prepare one persisted Codex thread and Goal through the official stdio API."""

import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', required=True)
    parser.add_argument('--prompt', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.report.exists():
        raise RuntimeError('Session report already exists; do not create a duplicate thread.')
    prompt = args.prompt.read_text(encoding='utf-8-sig').strip()
    if not prompt.startswith('/goal '):
        raise RuntimeError('The launch prompt must begin with a /goal objective.')
    objective = prompt.split('\n\n', 1)[0][len('/goal '):].strip()
    if not objective or len(objective) > 4000:
        raise RuntimeError('Goal objective must contain 1-4000 characters.')

    process = subprocess.Popen(
        [args.codex, 'app-server', '--stdio', '-c', 'model_reasoning_effort="max"'],
        cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW,
    )
    messages = queue.Queue()
    errors = []

    def read_messages():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        messages.put(None)

    def read_errors():
        for line in process.stderr:
            errors.append(line)
            if len(errors) > 40:
                del errors[:-40]

    readers = [threading.Thread(target=read_messages), threading.Thread(target=read_errors)]
    for reader in readers:
        reader.start()
    sequence = 0

    def send(method, params, request_id=None):
        message = {'method': method, 'params': params}
        if request_id is not None:
            message['id'] = request_id
        process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        process.stdin.flush()

    def rpc(method, params):
        nonlocal sequence
        sequence += 1
        send(method, params, sequence)
        while True:
            message = messages.get(timeout=55)
            if message is None:
                raise RuntimeError('Codex app-server closed before replying.')
            if message.get('id') != sequence:
                continue
            if 'error' in message:
                raise RuntimeError(f'{method}: {message["error"]}')
            return message['result']

    try:
        rpc('initialize', {'clientInfo': {
            'name': 'eu4_goal_launcher', 'title': 'EU4 diplomacy development launcher', 'version': '1.0',
        }})
        send('initialized', {})
        started = rpc('thread/start', {
            'model': 'gpt-6.1-sol', 'cwd': str(root), 'ephemeral': False,
            'approvalPolicy': 'on-request', 'approvalsReviewer': 'auto_review',
            'sandbox': 'workspace-write', 'config': {'model_reasoning_effort': 'max'},
        })
        thread_id = started['thread']['id']
        report = {
            'thread_id': thread_id, 'model': started.get('model'),
            'reasoning_effort': started.get('reasoningEffort'), 'cwd': str(root),
            'codex': args.codex, 'prompt': str(args.prompt.resolve()),
            'thread_path': started['thread'].get('path'),
            'goal_status': 'not_set', 'started': False,
            'approval_policy': started.get('approvalPolicy'),
            'approvals_reviewer': started.get('approvalsReviewer'),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if report['model'] != 'gpt-6.1-sol' or report['reasoning_effort'] != 'max':
            raise RuntimeError('The server did not confirm the requested model and reasoning effort.')
        rpc('thread/name/set', {'threadId': thread_id, 'name': 'EU4 外交系统开发 · Sol Max'})
        rpc('thread/goal/set', {'threadId': thread_id, 'objective': objective,
                              'status': 'active', 'origin': 'user'})
        goal = rpc('thread/goal/get', {'threadId': thread_id})['goal']
        if goal['status'] != 'active' or goal['objective'] != objective:
            raise RuntimeError('The persisted Goal did not match the launch objective.')
        report.update(goal_status=goal['status'], goal_objective=objective,
                      token_budget=goal.get('tokenBudget'))
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: report[key] for key in
                          ('thread_id', 'model', 'reasoning_effort', 'goal_status', 'token_budget')},
                         ensure_ascii=False))
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)


if __name__ == '__main__':
    main()
