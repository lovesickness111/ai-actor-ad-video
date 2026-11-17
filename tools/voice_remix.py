"""Remix a Gemini library voice into a custom one: same speaker, permanent
traits changed (accent, age, pitch...). The new voice is stored in the API
key's project; its `voice_...` id goes into ad.json characters.<id>.voices.gemini. Needs the same
keys as tts.py (local/secrets.env) and a paid-tier Gemini project.

.venv/Scripts/python.exe tools/voice_remix.py en-us-riko "Give the speaker a Northern Vietnamese (Hanoi) accent" --preview projects/<p>/voice_test/remix_riko.wav
.venv/Scripts/python.exe tools/voice_remix.py --list
.venv/Scripts/python.exe tools/voice_remix.py --delete voice_abc123
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from gemini_tts import load_env


def call(method, path, body=None):
    base = os.environ.get('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com/').rstrip('/')
    request = urllib.request.Request(
        f'{base}/v1beta/{path}', json.dumps(body).encode() if body else None,
        {'Content-Type': 'application/json', 'x-goog-api-key': os.environ['GEMINI_API_KEY']}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read() or '{}')
    except urllib.error.HTTPError as e:
        raise SystemExit(f'Gemini HTTP {e.code}: {e.read().decode(errors="replace")[:800]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base_voice', nargs='?', help='library id (en-us-riko), prebuilt name or a voice_... id')
    parser.add_argument('instruction', nargs='?', help='the change to make, relative to the base voice')
    parser.add_argument('--preview', help='save the preview clip the API returns to this .wav')
    parser.add_argument('--list', action='store_true', help='list the custom voices stored in the project')
    parser.add_argument('--delete', metavar='VOICE_ID')
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding='utf-8')  # the Windows console codepage can't print Vietnamese
    load_env()
    if args.list:
        for v in call('GET', 'voices?type=prompted&page_size=200').get('voices', []):
            prompted = v.get('prompted', {})
            print(f"{v['id']}  base={prompted.get('base_voice')}  {prompted.get('input')}")
        return
    if args.delete:
        call('DELETE', f'voices/{args.delete}')
        print('deleted', args.delete)
        return
    if not (args.base_voice and args.instruction):
        parser.error('base_voice and instruction are required')
    voice = call('POST', 'voices', {'store': True, 'voice': {
        'model': os.environ['GEMINI_TTS_MODEL'], 'type': 'prompted',
        'prompted': {'base_voice': args.base_voice, 'input': args.instruction}}})
    if args.preview:
        Path(args.preview).write_bytes(base64.b64decode(voice['sample_audio']['data']))
    print(voice['id'])


if __name__ == '__main__':
    main()
