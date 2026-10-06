#!/usr/bin/env python3
"""Local-only behavioral checks of the anonymous immutable-tag registry checker."""
import http.server
import os
import pathlib
import subprocess
import tempfile
import threading
import time
import urllib.parse

SCRIPT = str(pathlib.Path(__file__).with_name('image-state.sh'))
DIGEST = 'sha256:' + 'a' * 64
OTHER = 'sha256:' + 'b' * 64
calls = []
plans = {}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_GET(self):
        self.respond('token')
    def do_HEAD(self):
        self.respond('manifest')
    def respond(self, kind):
        registry = self.path.split('/')[1]
        calls.append((registry, kind, self.path))
        plan = plans.get((registry, kind), [200])
        status = plan.pop(0) if len(plan) > 1 else plan[0]
        self.send_response(status)
        if kind == 'manifest' and status == 200:
            digest = plans.get((registry, 'digest'), DIGEST)
            if digest is not None:
                self.send_header('Docker-Content-Digest', digest)
        self.end_headers()
        if kind == 'token':
            self.wfile.write(plans.get((registry, 'body'), b'{"token":"private-test-token"}'))

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
count = 0

def run(name, expected, newplans=None, *, hub=True, wait=False, extra=None, argv=None):
    global plans, count
    plans = newplans or {}
    calls.clear()
    env = os.environ.copy()
    env.update(GHCR_IMAGE='ghcr.io/example/image', DOCKERHUB_USERNAME='example',
        DOCKERHUB_IMAGE='docker.io/example/image', IMAGE_STATE_RETRY_DELAY='0',
        IMAGE_STATE_WAIT_SECONDS='1', IMAGE_STATE_WAIT_INTERVAL='1',
        GHCR_TOKEN_URL=base+'/ghcr/token', GHCR_REGISTRY_URL=base+'/ghcr',
        DOCKERHUB_TOKEN_URL=base+'/hub/token', DOCKERHUB_REGISTRY_URL=base+'/hub')
    if not hub:
        env.pop('DOCKERHUB_USERNAME', None)
    env.update(extra or {})
    with tempfile.TemporaryDirectory() as folder:
        output = pathlib.Path(folder)/'output'
        summary = pathlib.Path(folder)/'summary'
        env.update(GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
        args = argv if argv is not None else (['--wait'] if wait else []) + ['27.0.2-jdk27-debian-trixie']
        result = subprocess.run([SCRIPT] + args, env=env, capture_output=True, text=True, timeout=15)
        assert result.stdout == expected+'\n', (name, result.stdout, result.stderr)
        assert (result.returncode != 0) == (expected == 'error'), (name, result.returncode)
        assert 'private-test-token' not in result.stderr+result.stdout
        fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
        assert set(fields) == {'state','ghcr_status','ghcr_digest','dockerhub_status','dockerhub_digest','ghcr_image','dockerhub_image'}
        assert fields['state'] == expected
        assert 'GHCR | ' in summary.read_text()
        if not hub and not extra and argv is None:
            assert '::warning::' in result.stderr
            assert 'checked registries: GHCR only' in result.stderr
            assert 'Docker Hub | ' not in summary.read_text()
            assert fields['dockerhub_status'] == 'disabled'
            assert fields['dockerhub_image'] == ''
        if expected == 'error':
            assert 'Re-run' not in result.stderr and 'copy' not in result.stderr
        count += 1
        print(f'PASS {name}')
        return list(calls), result

run('matching digests', 'published')
run('different digests', 'inconsistent', {('hub','digest'):OTHER})
run('GHCR present only', 'inconsistent', {('hub','manifest'):[404]})
run('Hub present only', 'inconsistent', {('ghcr','manifest'):[404]})
run('both absent', 'absent', {('ghcr','manifest'):[404], ('hub','manifest'):[404]})
run('Hub disabled warning', 'published', hub=False)
run('Hub disabled absent', 'absent', {('ghcr','manifest'):[404]}, hub=False)
for kind in ['token','manifest']:
    for status in [401,403,404 if kind=='token' else 400]:
        seen, _ = run(f'{kind} HTTP {status}', 'error', {('ghcr',kind):[status]})
        assert sum(r=='ghcr' and k==kind for r,k,_ in seen) == 1
    for status in [429,500]:
        seen, _ = run(f'{kind} exhausted HTTP {status}', 'error', {('ghcr',kind):[status]})
        assert sum(r=='ghcr' and k==kind for r,k,_ in seen) == 4
    seen, _ = run(f'{kind} recovered retry', 'published', {('ghcr',kind):[429,500,200]})
    assert sum(r=='ghcr' and k==kind for r,k,_ in seen) == 3
run('refused token connection', 'error', extra={'GHCR_TOKEN_URL':'http://127.0.0.1:1/token'})
run('refused manifest connection', 'error', extra={'GHCR_REGISTRY_URL':'http://127.0.0.1:1'})
seen, _ = run('ordinary 404 is immediate', 'absent', {('ghcr','manifest'):[404],('hub','manifest'):[404]})
assert sum(k=='manifest' for _,k,_ in seen)==2
seen, _ = run('wait eventually appears', 'published', {('ghcr','manifest'):[404,200]}, wait=True)
assert sum(r=='ghcr' and k=='manifest' for r,k,_ in seen)==2
started=time.monotonic()
seen, _ = run('wait stops at deadline', 'absent', {('ghcr','manifest'):[404]}, wait=True, hub=False)
assert 0.4 < time.monotonic()-started < 3
assert sum(r=='ghcr' and k=='manifest' for r,k,_ in seen)==2
run('wait never retries token 404', 'error', {('ghcr','token'):[404]}, wait=True)
for body in [b'{}', b'{"token":null}', b'{"token":42}', b'{"token":"private-test-token\\n"}', b'invalid']:
    run(f'invalid token {body!r}', 'error', {('ghcr','body'):body})
run('invalid timing configuration', 'error', extra={'IMAGE_STATE_WAIT_INTERVAL':'08'})
run('access_token accepted', 'published', {('ghcr','body'):b'{"access_token":"private-test-token"}'})
for digest in [None, 'sha256:no', DIGEST+' extra']:
    run(f'invalid digest {digest!r}', 'error', {('ghcr','digest'):digest})
for invalid in ['', 'a:b', '-tag', 'a'*129]:
    seen, _=run(f'invalid tag {invalid!r}', 'error', argv=[invalid])
    assert not seen
for image in ['example/image', 'ghcr.io/', 'ghcr.io/Example/image', 'ghcr.io/example/image:tag', 'ghcr.io/example/image\nstate=absent']:
    seen,_=run(f'invalid image {image!r}', 'error', extra={'GHCR_IMAGE':image})
    assert not seen
# Source must be silent and do no registry requests; resolver updates both names.
calls.clear()
result=subprocess.run(['bash','-c','source "$1"; GHCR_IMAGE=ghcr.io/example/image; DOCKERHUB_USERNAME=example; DOCKERHUB_IMAGE=docker.io/example/image; resolve_registry_images; printf "%s|%s" "$GHCR_IMAGE" "$DOCKERHUB_IMAGE"','test',SCRIPT], capture_output=True,text=True)
assert result.returncode==0 and result.stdout=='ghcr.io/example/image|example/image' and result.stderr=='' and not calls
count+=1
print('PASS silent sourceable resolver')
server.shutdown()
print(f'{count} cases passed')
