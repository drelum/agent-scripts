"""Cobertura visual rrweb; lacunas explícitas, sem atribuir DOM a tempo não gravado."""
import json
import math
import subprocess
import time

import bundles
import lab


GAP_WINDOW = 'recording-gap'
GAP_LIMIT = 'Cartões Sem gravação disponível são marcadores locais, não telas vistas pelo usuário; não permitem inferir erro, intenção ou frustração nesse intervalo.'


def intervals(source, windows):
    """União dos intervalos com snapshot completo; inatividade dentro deles não é lacuna."""
    covered = []
    for events in windows.values():
        snapshots = [event['timestamp'] for event in events if event['type'] == 2]
        if not snapshots:
            raise ValueError('Aba sem snapshot completo; não substituir falha por cartão.')
        covered.append((min(snapshots), max(event['timestamp'] for event in events)))
    if not covered:
        raise ValueError('Sessão sem snapshots completos.')
    merged = []
    for begin, end in sorted(covered):
        if end < begin or begin < source['start'] or end > source['end']:
            raise ValueError('Cobertura visual fora da sessão.')
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((begin, end))
    result, previous = [], merged[0][0]
    for begin, end in merged:
        if begin > previous:
            result.append({'kind': 'recording_gap', 'from_ms': previous, 'to_ms': begin})
        if end > begin:
            result.append({'kind': 'recording', 'from_ms': begin, 'to_ms': end})
        previous = end
    if previous < source['end']:
        result.append({'kind': 'recording_gap', 'from_ms': previous, 'to_ms': source['end']})
    return result


def plan(source, windows, chunk_seconds):
    result = []
    coverage = intervals(source, windows)
    for part in coverage:
        begin = (part['from_ms'] - source['start']) / 1000
        end = (part['to_ms'] - source['start']) / 1000
        while begin < end - 0.000001:
            duration = min(chunk_seconds, end - begin)
            result.append({'start': begin, 'duration': duration, 'kind': part['kind']})
            begin += duration
    return result, [part for part in coverage if part['kind'] == 'recording_gap']


def render_gap(source, windows, job, fps, stage, renderer):
    """Mesmo MP4 indexado: cartão explícito, encode direto, sem replay de DOM inexistente."""
    target = source['start'] + job['start'] * 1000
    end = target + job['duration'] * 1000
    gaps = [part for part in intervals(source, windows) if part['kind'] == 'recording_gap']
    if not any(target >= gap['from_ms'] - 0.001 and end <= gap['to_ms'] + 0.001 for gap in gaps):
        raise ValueError('Cartão só é permitido dentro de lacuna comprovada pelos snapshots.')
    if not 1 <= fps <= 30 or not 0 < job['duration'] <= 600:
        raise ValueError('FPS/duração do cartão inválidos.')
    count = math.ceil(job['duration'] * fps)
    began = time.monotonic()
    stage.mkdir(parents=True, mode=0o700)
    movie = stage / 'clip.mp4'
    filters = ','.join([
        "drawtext=text='Sem gravação disponível':fontsize=42:fontcolor=0x302b26:x=(w-tw)/2:y=h/2-65",
        "drawtext=text='Este intervalo não possui snapshots.':fontsize=24:fontcolor=0x625b52:x=(w-tw)/2:y=h/2+5",
    ])
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
        f'color=c=0xebe6dc:s=1366x768:r={fps}', '-vf', filters, '-frames:v', str(count),
        '-c:v', 'libx264', '-threads', '2', '-filter_threads', '1', '-pix_fmt', 'yuv420p',
        '-crf', '18', str(movie)], check=True, capture_output=True, timeout=180)
    encode_s = time.monotonic() - began
    probe = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams',
        '-of', 'json', str(movie)], check=True, capture_output=True, text=True, timeout=180).stdout)
    stream = next(row for row in probe['streams'] if row['codec_type'] == 'video')
    if int(stream['nb_read_frames']) != count or abs(float(stream['duration']) - count / fps) > 0.05:
        raise ValueError('Cartão codificado diverge do índice.')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(movie), '-f', 'null', '-'],
                   check=True, capture_output=True, timeout=180)
    frames = [{'index': index, 'video_s': index / fps,
               'session_ms': target + index * 1000 / fps,
               'session_s': job['start'] + index / fps, 'window': GAP_WINDOW,
               'visual_state': 'missing_recording', 'clock_source': 'declared_recording_gap',
               'capture_virtual_ms': None, 'capture_sha256': None} for index in range(count)]
    exported = {'schema': 1, 'status': 'complete', 'dataset': source['name'], 'fps': fps,
        'selected_window': None, 'renderer_sha256': renderer, 'start_s': job['start'],
        'requested_duration_s': job['duration'], 'encoded_duration_s': count / fps,
        'timeline_gaps': [], 'recording_gaps': [{'from_ms': target, 'to_ms': end}],
        'frames': frames, 'events_sha256': source['events_sha256'], 'video_sha256': bundles.sha(movie),
        'total_ms': (time.monotonic() - began) * 1000, 'width': 1366, 'height': 768,
        'limitations': [GAP_LIMIT], 'timings': {'gap_encode_ms': encode_s * 1000}}
    lab.write_json(stage / 'export.json', exported)
    return exported
