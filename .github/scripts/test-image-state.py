#!/usr/bin/env python3
"""Local-only behavioral checks of the anonymous immutable-tag registry checker."""
import http.server
import os
import pathlib
import subprocess
import sys
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
        calls.append((registry, kind, self.path, self.command,
                      {name.lower(): value for name, value in self.headers.items()}))
        raw_response = plans.get((registry, 'raw_manifest'))
        if kind == 'manifest' and raw_response is not None:
            self.wfile.write(raw_response)
            return
        plan = plans.get((registry, kind), [200])
        status = plan.pop(0) if len(plan) > 1 else plan[0]
        for code, digests in plans.get((registry, 'informational'), []) if kind == 'manifest' else []:
            self.send_response_only(code)
            for digest in digests:
                self.send_header('Docker-Content-Digest', digest)
            self.end_headers()
        self.send_response(status)
        if 300 <= status < 400:
            self.send_header('Location', base + '/redirected')
        if kind == 'manifest' and status == 200:
            digest = plans.get((registry, 'digest'), DIGEST)
            if digest is not None:
                for value in digest if isinstance(digest, list) else [digest]:
                    self.send_header('Docker-Content-Digest', value)
        self.end_headers()
        if kind == 'token':
            self.wfile.write(plans.get((registry, 'body'), b'{"token":"private-test-token"}'))

server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
count = 0

def run(name, expected, newplans=None, *, hub=True, wait=False, extra=None, argv=None, expected_fields=None):
    global plans, count
    plans = newplans or {}
    calls.clear()
    env = os.environ.copy()
    # Keep loopback stubs local even on hosts configured with HTTP proxies.
    env.update(NO_PROXY='127.0.0.1', no_proxy='127.0.0.1')
    env.update(GHCR_IMAGE='ghcr.io/example/image', DOCKERHUB_USERNAME='example',
        DOCKERHUB_IMAGE='docker.io/example/image', IMAGE_STATE_RETRY_DELAY='0',
        IMAGE_STATE_WAIT_SECONDS='2', IMAGE_STATE_WAIT_INTERVAL='1',
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
        for field, value in (expected_fields or {}).items():
            assert fields[field] == value, (name, field, fields[field], value)
        for registry, kind, path, method, headers in calls:
            parsed = urllib.parse.urlsplit(path)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            assert registry in ('ghcr', 'hub'), (name, 'redirect followed', path)
            if kind == 'token':
                assert method == 'GET' and parsed.path == f'/{registry}/token'
                expected_query = {'scope': ['repository:example/image:pull']}
                if registry == 'hub':
                    expected_query['service'] = ['registry.docker.io']
                assert query == expected_query, (name, query)
                assert 'authorization' not in headers, (name, headers)
            else:
                assert method == 'HEAD' and parsed.path == f'/{registry}/v2/example/image/manifests/27.0.2-jdk27-debian-trixie'
                assert query == {}
                assert headers.get('authorization') == 'Bearer private-test-token'
                assert {value.strip() for value in headers.get('accept', '').split(',')} == {
                    'application/vnd.oci.image.index.v1+json',
                    'application/vnd.docker.distribution.manifest.list.v2+json',
                    'application/vnd.oci.image.manifest.v1+json',
                    'application/vnd.docker.distribution.manifest.v2+json',
                }

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

def baseline_cases():
    global count
    run('matching digests', 'published', expected_fields={'ghcr_digest': DIGEST, 'dockerhub_digest': DIGEST, 'ghcr_status': 'present', 'dockerhub_status': 'present'})
    run('different digests', 'inconsistent', {('hub','digest'):OTHER}, expected_fields={'ghcr_digest': DIGEST, 'dockerhub_digest': OTHER})
    run('GHCR present only', 'inconsistent', {('hub','manifest'):[404]}, expected_fields={'ghcr_digest': DIGEST, 'dockerhub_digest': '', 'ghcr_status': 'present', 'dockerhub_status': 'absent'})
    run('Hub present only', 'inconsistent', {('ghcr','manifest'):[404]}, expected_fields={'ghcr_digest': '', 'dockerhub_digest': DIGEST, 'ghcr_status': 'absent', 'dockerhub_status': 'present'})
    run('both absent', 'absent', {('ghcr','manifest'):[404], ('hub','manifest'):[404]}, expected_fields={'ghcr_digest': '', 'dockerhub_digest': '', 'ghcr_status': 'absent', 'dockerhub_status': 'absent'})
    run('Hub disabled warning', 'published', hub=False, expected_fields={'ghcr_digest': DIGEST, 'dockerhub_digest': ''})
    run('Hub disabled absent', 'absent', {('ghcr','manifest'):[404]}, hub=False)
    for kind in ['token','manifest']:
        for status in [301,302,303,304,307,308,401,403,404 if kind=='token' else 400]:
            seen, _ = run(f'{kind} HTTP {status}', 'error', {('ghcr',kind):[status]})
            assert sum(r=='ghcr' and k==kind for r,k,_,_,_ in seen) == 1
        for status in [429,500]:
            seen, _ = run(f'{kind} exhausted HTTP {status}', 'error', {('ghcr',kind):[status]})
            assert sum(r=='ghcr' and k==kind for r,k,_,_,_ in seen) == 4
        seen, _ = run(f'{kind} recovered retry', 'published', {('ghcr',kind):[429,500,200]})
        assert sum(r=='ghcr' and k==kind for r,k,_,_,_ in seen) == 3
    run('refused token connection', 'error', extra={'GHCR_TOKEN_URL':'http://127.0.0.1:1/token'})
    run('refused manifest connection', 'error', extra={'GHCR_REGISTRY_URL':'http://127.0.0.1:1'})
    seen, _ = run('ordinary 404 is immediate', 'absent', {('ghcr','manifest'):[404],('hub','manifest'):[404]})
    assert sum(k=='manifest' for _,k,_,_,_ in seen)==2
    seen, _ = run('wait eventually appears', 'published', {('ghcr','manifest'):[404,200]}, wait=True)
    assert sum(r=='ghcr' and k=='manifest' for r,k,_,_,_ in seen)==2
    started=time.monotonic()
    seen, _ = run('wait stops at deadline', 'absent', {('ghcr','manifest'):[404]}, wait=True, hub=False)
    assert 0.5 < time.monotonic()-started < 4
    # Bash SECONDS has one-second resolution; the bounded poll may issue two or three HEADs.
    assert 2 <= sum(r=='ghcr' and k=='manifest' for r,k,_,_,_ in seen) <= 3
    run('wait never retries token 404', 'error', {('ghcr','token'):[404]}, wait=True)
    for body in [b'{}', b'{"token":null}', b'{"token":42}', b'{"token":"private-test-token\\n"}', b'invalid']:
        run(f'invalid token {body!r}', 'error', {('ghcr','body'):body})
    run('invalid timing configuration', 'error', extra={'IMAGE_STATE_WAIT_INTERVAL':'08'})
    run('access_token accepted', 'published', {('ghcr','body'):b'{"access_token":"private-test-token"}'})
    for digest in [None, 'sha256:no', DIGEST+' extra']:
        run(f'invalid digest {digest!r}', 'error', {('ghcr','digest'):digest}, expected_fields={'ghcr_status': 'error', 'ghcr_digest': '', 'dockerhub_digest': DIGEST})
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

def regression_cases():
    global count
    failures = []
    cases = [
        ('final header block wins over 100 and 103', 'published', {
            ('ghcr', 'informational'): [(100, [OTHER]), (103, [OTHER])],
        }, {'ghcr_digest': DIGEST, 'dockerhub_digest': DIGEST}),
        ('conflicting earlier headers are ignored', 'published', {
            ('ghcr', 'informational'): [(103, [DIGEST, OTHER])],
        }, {'ghcr_digest': DIGEST}),
        ('earlier digest cannot replace missing final digest', 'error', {
            ('ghcr', 'informational'): [(103, [DIGEST])],
            ('ghcr', 'digest'): None,
        }, {'ghcr_status': 'error', 'ghcr_digest': ''}),
        ('identical final duplicates are accepted', 'published', {
            ('ghcr', 'digest'): [DIGEST, DIGEST],
        }, {'ghcr_digest': DIGEST}),
        ('case-varied duplicate digests normalize consistently', 'published', {
            ('ghcr', 'digest'): [DIGEST, 'sha256:' + 'A' * 64],
        }, {'ghcr_digest': DIGEST}),
        ('conflicting final duplicates are rejected', 'error', {
            ('ghcr', 'digest'): [DIGEST, OTHER],
        }, {'ghcr_status': 'error', 'ghcr_digest': ''}),
        ('identical final duplicates after informational block', 'published', {
            ('ghcr', 'informational'): [(103, [OTHER])],
            ('ghcr', 'digest'): [DIGEST, DIGEST],
        }, {'ghcr_digest': DIGEST}),
        ('digest without optional whitespace is accepted', 'published', {
            ('ghcr', 'raw_manifest'): f'HTTP/1.1 200 OK\r\nDocker-Content-Digest:{DIGEST}\r\n\r\n'.encode(),
        }, {'ghcr_digest': DIGEST}),
        ('identical duplicates without optional whitespace are accepted', 'published', {
            ('ghcr', 'raw_manifest'): f'HTTP/1.1 200 OK\r\nDocker-Content-Digest:{DIGEST}\r\nDocker-Content-Digest:{DIGEST}\r\n\r\n'.encode(),
        }, {'ghcr_digest': DIGEST}),
        ('conflicting unspaced duplicate is rejected', 'error', {
            ('ghcr', 'raw_manifest'): f'HTTP/1.1 200 OK\r\nDocker-Content-Digest: {DIGEST}\r\nDocker-Content-Digest:{OTHER}\r\n\r\n'.encode(),
        }, {'ghcr_status': 'error', 'ghcr_digest': ''}),
    ]
    for name, state, plan, fields in cases:
        try:
            run(name, state, plan, expected_fields=fields)
        except AssertionError as error:
            failures.append((name, str(error)))
    for image in ['index.docker.io/example/image', 'quay.io/example/image', 'localhost/example/image', 'example.com:5000/example/image', 'docker.io/quay.io/example/image']:
        name = f'host-like Hub image rejected: {image}'
        try:
            seen, _ = run(name, 'error', extra={'DOCKERHUB_IMAGE': image})
            assert not seen, (name, seen)
        except AssertionError as error:
            failures.append((name, str(error)))
    # A dot in the repository component is still a valid Hub image path. Rejecting
    # a registry-looking first component must not reject all dots in the path.
    # Resolver-only invocation avoids requests to a differently named stub route.
    for image, expected in [('example/image.name', 'example/image.name'), ('docker.io/example/image.name', 'example/image.name')]:
        result = subprocess.run(['bash', '-c',
            'source "$1"; GHCR_IMAGE=ghcr.io/example/image; DOCKERHUB_USERNAME=example; DOCKERHUB_IMAGE=$2; resolve_registry_images; printf "%s" "$DOCKERHUB_IMAGE"',
            'test', SCRIPT, image], capture_output=True, text=True)
        assert result.returncode == 0 and result.stdout == expected and result.stderr == ''
        count += 1
        print(f'PASS dotted Hub repository accepted: {image}')
    for name, error in failures:
        print(f'FAIL {name}: {error}')
    assert not failures, f'{len(failures)} regression cases failed'

try:
    if '--regressions-only' not in sys.argv[1:]:
        baseline_cases()
    regression_cases()
    print(f'{count} cases passed')
finally:
    server.shutdown()
