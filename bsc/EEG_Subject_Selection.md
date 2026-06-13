# EEG subject & reference selection

The viewer loads **one** EEG session as its default. This note documents, and
makes reproducible, why that session is **subject A03, training session (A03T)**,
processed with a **surface-Laplacian (CSD) reference**.

Reproduce with: `python -m backend.eeg.select_subject`
(applies the production pipeline to every T-session GDF in `data/eeg/`).

## Why a surface Laplacian (CSD), not a common average reference (CAR)

ERD/ERS is the *relative* band-power change from a pre-cue baseline. Its sign
depends strongly on the spatial reference:

- **CAR** over only these 22 fronto-centro-parietal electrodes (no
  occipital/temporal coverage) is spatially biased. When a class
  (de)synchronises montage-wide it shifts the common average and leaks that
  common-mode power into *every* channel. Empirically this **inverts feet's true
  central ERD into a spurious, all-channel ERS** — a physiologically impossible
  uniform-sign map across the whole montage.
- **CSD / surface Laplacian** is reference-free and spatially sharpening. It
  localises focal sensorimotor (de)synchronisation, recovering feet's vertex ERD
  and crisp contralateral hand ERD.

The ERD/ERS *formula itself* (Hilbert power → epoch → ratio-of-means vs baseline,
the standard Pfurtscheller method) was verified correct independently; only the
reference was changed.

## Subject ranking (production pipeline, CSD, mu band, MI window 0.5–3.5 s)

Score = contralateral hand ERD depth (`left→C4` + `right→C3`, more negative is
better) with penalties for wrong lateralisation and a positive (ERS) feet vertex.
Lower is cleaner.

| subj | score | left→C4 | right→C3 | feet Cz | L-contra | R-contra | clean | dropped |
|------|------:|--------:|---------:|--------:|:--------:|:--------:|------:|--------:|
| **A03** | **−118.9** | −51.2 | −67.7 | **−20.9** | ✓ | ✓ | 270 | 18 |
| A09 | −92.1 | −58.9 | −33.2 | −17.9 | ✓ | ✓ | 237 | 51 |
| A08 | −66.4 | −34.3 | −32.1 | −33.0 | ✓ | ✓ | 264 | 24 |
| A07 | −38.3 | −48.0 | −40.3 | −21.5 | ✓ | ✗ | 271 | 17 |
| A05 | −0.2 | −23.2 | −7.0 | +19.3 | ✓ | ✓ | 262 | 26 |
| A06 | +3.7 | −15.3 | −11.0 | +14.2 | ✓ | ✓ | 219 | 69 |
| A01 | +38.6 | −15.6 | −25.7 | **+8.4** | ✓ | ✗ | 273 | 15 |
| A04 | +82.5 | +12.1 | −9.5 | +9.6 | ✗ | ✓ | 262 | 26 |
| A02 | +116.9 | +29.6 | +7.3 | +36.5 | ✗ | ✓ | 270 | 18 |

**A03 is the cleanest by a wide margin:** deep contralateral hand ERD
(right-hand C3 −68 %), correct-sign central feet ERD (Cz −21 %), correct
lateralisation for both hands. The previously shipped subject **A01** ranks 7th —
its feet vertex is **+8.4 % (ERS, wrong sign)** even under CSD and its right-hand
lateralisation is ambiguous, which is why switching subject (not only reference)
was necessary.

## Validation

- **Pipeline ↔ official data:** processing A01T from the canonical GDF reproduces
  the official BCI IV 2a MATLAB (`.mat`) export's ERD/ERS **to the decimal**
  (≤0.1 %), confirming our GDF processing is faithful.
- **Held-out replication:** A03's pattern replicates on the independent
  **evaluation session A03E** (left-hand C4 −46, right-hand C3 −71, feet central
  ERD), so the choice is not an overfit to one session. (E-session labels and
  per-trial artifact flags come from the `.mat` export; the production pipeline
  itself reads only the GDF.)

## Shipped result (A03T, CSD)

| band | left hand | right hand | feet | tongue |
|------|-----------|------------|------|--------|
| mu   | ERD −31 %, C4 −52 | ERD −35 %, C3 −68 | **ERD central, Cz −20** | mild ERS +17 |
| beta | ERD −32 % | ERD −34 %, C3 −57 | **ERD, Cz −34** | ~flat +1 |

Tongue remains a mild ERS: it is the noisiest motor-imagery class (glossokinetic /
jaw movement), and A03's is the least contaminated among the clean subjects.
