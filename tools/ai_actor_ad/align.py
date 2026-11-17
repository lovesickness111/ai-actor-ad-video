"""Syllable-level lip alignment (dub mode): warp a TTS phrase onto the timing of the actor's own (Omni) take of the
same words, so the dubbed voice follows the generated mouth movement.

    from align import align_phrase
    align_phrase(omni_wav, t0, t1, tts_wav, out_wav) -> (onset_s, duration_s)

Method: trim both takes to speech, MFCC (+deltas) per 10 ms, DTW between them, smooth the monotonic
time map (local rate kept within 0.55-1.8x), then a phase vocoder with a time-varying read position
renders the TTS on the actor's clock. Pitch and voice stay those of the TTS.
"""
import numpy as np
import librosa
import soundfile as sf

SR = 48000
HOP = 480          # 10 ms
NFFT = 2048
FEAT_SR = 16000
FEAT_HOP = 160     # 10 ms


def _speech(y, sr, top_db=32):
    _, (a, b) = librosa.effects.trim(y, top_db=top_db, frame_length=1024, hop_length=256)
    return a, b


def _feat(y):
    y16 = librosa.resample(y, orig_sr=SR, target_sr=FEAT_SR)
    m = librosa.feature.mfcc(y=y16, sr=FEAT_SR, n_mfcc=20, hop_length=FEAT_HOP, n_fft=512)[1:]
    m = (m - m.mean(1, keepdims=True)) / (m.std(1, keepdims=True) + 1e-6)
    return np.vstack([m, librosa.feature.delta(m)])


def _time_map(ref_feat, src_feat, n_out, n_src):
    """For each output (actor) frame, the fractional source (TTS) frame to read."""
    _, wp = librosa.sequence.dtw(X=ref_feat, Y=src_feat, metric="cosine")
    wp = wp[::-1]
    m = np.zeros(ref_feat.shape[1])
    for i in range(len(m)):
        m[i] = np.median(wp[wp[:, 0] == i, 1]) if np.any(wp[:, 0] == i) else np.nan
    idx = np.arange(len(m))
    good = ~np.isnan(m)
    m = np.interp(idx, idx[good], m[good])
    k = 7
    m = np.convolve(np.pad(m, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    # monotonic with bounded local rate, then pinned to the full source length
    step = np.clip(np.diff(m, prepend=m[0]), 0.55, 1.8)
    step[0] = 0
    m = np.cumsum(step)
    m = m / m[-1] * (src_feat.shape[1] - 1) if m[-1] > 0 else m
    out_idx = np.linspace(0, len(m) - 1, n_out)
    return np.interp(out_idx, idx, m) * (n_src - 1) / max(1, src_feat.shape[1] - 1)


def _vocoder(y, positions):
    D = librosa.stft(y, n_fft=NFFT, hop_length=HOP)
    D = np.pad(D, ((0, 0), (0, 2)))
    adv = np.linspace(0, np.pi * HOP, D.shape[0])
    phase = np.angle(D[:, 0])
    out = np.zeros((D.shape[0], len(positions)), dtype=complex)
    for t, pos in enumerate(positions):
        i = int(np.floor(pos)); a = pos - i
        c0, c1 = D[:, i], D[:, i + 1]
        out[:, t] = ((1 - a) * np.abs(c0) + a * np.abs(c1)) * np.exp(1j * phase)
        dp = np.angle(c1) - np.angle(c0) - adv
        dp -= 2 * np.pi * np.round(dp / (2 * np.pi))
        phase += adv + dp
    return librosa.istft(out, hop_length=HOP, n_fft=NFFT)


def align_phrase(omni_wav, t0, t1, tts_wav, out_wav, pad=0.25):
    ref, _ = librosa.load(omni_wav, sr=SR, mono=True, offset=max(0, t0 - pad), duration=(t1 - t0) + 2 * pad)
    a, b = _speech(ref, SR)
    onset = max(0, t0 - pad) + a / SR
    ref = ref[a:b]
    src, _ = librosa.load(tts_wav, sr=SR, mono=True)
    sa, sb = _speech(src, SR, top_db=40)
    src = src[sa:sb]
    n_out = int(np.ceil(len(ref) / HOP)) + 1
    n_src = int(np.ceil(len(src) / HOP)) + 1
    pos = _time_map(_feat(ref), _feat(src), n_out, n_src)
    y = _vocoder(src, pos)[:len(ref)]
    fade = int(0.01 * SR)
    y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(y)) or 1
    sf.write(out_wav, (y / peak * 0.89).astype(np.float32), SR)
    return onset, len(y) / SR
