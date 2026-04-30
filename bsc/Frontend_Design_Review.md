# Frontend Design Review — Justifications & Open Questions

A walk-through of every visible frontend component, what it does, why it is the way it is, and where a non-expert reviewer (or even a domain expert) is likely to get confused. The goal of this document is to give you talking points for your supervisor meeting and to flag the design decisions that need either (a) better in-app explanation or (b) a small technical change before submission.

The review is opinionated where it can be — it is your thesis, so you need to be able to defend or push back on every point.

---

## 1. Top-level layout (`app/page.js`)

**What it is.** A 3-region layout: left sidebar (`DatasetPanel`), center 3D viewer (`BrainViewer`), bottom strip (`Timeline`), plus a header with the active region readout and a "?" help modal.

**Why it makes sense.**
- This mirrors the layout convention of practically every neuroimaging viewer (FreeSurfer's Freeview, MNE's `Brain` viewer, BrainStorm, SPM). Reviewers familiar with the field will immediately recognise the structure: *what data am I looking at* (left), *the brain* (center), *time evolution* (bottom). Familiarity is itself a usability win.
- The center-of-attention is the brain, which is correct: ERD/ERS topography is the headline result of any motor-imagery study.
- The header keeps the **currently hovered region name** always visible, so the cognitive load of "what am I pointing at" is offloaded from the user's working memory.

**Things that need a defence.**
- The run-aggregation logic lives in `page.js` (lines 61–119) instead of in the backend export. The function recomputes per-channel × per-time averages every time the run set changes, in JavaScript. This is fine for 288 trials × 22 channels × ~1100 samples, but it's worth being honest about: the only reason it's in the frontend is to make the "Runs" toggle interactive without re-running the pipeline. A reviewer might ask: *"Why didn't you just export six pre-aggregated arrays from Python?"* The answer is that with 6 runs you'd need 2⁶ = 64 combinations to cover every subset; storing per-trial data and aggregating client-side is the cheaper representation. **This is a defensible decision** but you should be ready to articulate it.
- There is an approximation buried in there: `trials_per_run = ceil(n_trials / n_runs)`. The BCI Comp IV 2a protocol has 6 runs of 48 trials, but artifact rejection removes some, so trials are *not* perfectly evenly divisible by 6. The "Run 3" button therefore selects a *roughly correct* slice, not the actual run-3 trials. **This is a small but real correctness issue.** Either fix it (export run indices from MNE alongside the data) or document the approximation in the thesis.

---

## 2. `BrainViewer.jsx` — the 3D brain

**What it is.** A Three.js scene containing one PLY mesh (cortical surface from Marching Cubes on a NIfTI atlas), with vertex-color heatmap, SSAO post-processing, OrbitControls, raycaster-based hover, and an optional 3-camera split-screen.

**Why each piece exists.**

- **PLY mesh from Marching Cubes.** A surface mesh is the right primitive for cortical data because (a) ERD/ERS effects are cortical-surface phenomena, (b) hovering and per-vertex colouring map naturally to triangle meshes, and (c) PLY transports vertex colors with no extra step. A volumetric (NIfTI slice) viewer would have been a different thesis — comparable to an MRI viewer rather than an EEG/BCI viewer.
- **SSAO (Screen-Space Ambient Occlusion).** This is the single most important rendering decision in the project, and it is genuinely defensible. Without ambient occlusion the cortical sulci (the folds) become invisible — the brain looks like a smooth lump. SSAO darkens crevices, which makes the gyral/sulcal pattern legible *and gives the user 3D depth cues without requiring stereoscopy*. For a visual-graphics supervisor this is the headline graphics contribution.
- **Vertex colors instead of a texture atlas.** Vertex coloring is appropriate because the spatial resolution of EEG (a few cm) is far coarser than the mesh, so per-vertex colour with regional averaging is enough. A UV-mapped texture atlas would be massive overkill and would force you to maintain a UV unwrap.
- **OrbitControls with damping.** Standard, low risk, expected behaviour.
- **Raycaster hover → region name + value tooltip.** This is the right interaction for region inspection, and it solves a real problem: a non-expert reviewer cannot read a Destrieux atlas label off a coloured surface. The hover label is a *teaching* feature.
- **Diverging blue–grey–red colourmap.** This is the conventional ERD/ERS colormap (blue = power decrease = ERD, red = power increase = ERS). It is what Pfurtscheller & Lopes da Silva (1999) and most BCI literature use. Using anything else (e.g., viridis) would actively confuse domain readers.
- **Multi-view (3-up split: left hemi / top / right hemi).** This gives a quick "did the contralateral hemisphere light up like it's supposed to?" check without rotating. Motor imagery is fundamentally a contralateral phenomenon, so the side-by-side comparison is the *first thing* a BCI researcher would look for.

**Things a supervisor will ask about (and your answers).**

| Question | Answer / what to fix |
|---|---|
| **"In contrast mode the legend still says ERD/ERS but I see both blue and red regions — is the implementation broken?"** | No, the implementation is correct, but the **legend is misleading in this mode**. See §6 below — this is the most important UX issue in the project. |
| "Why is the brain darker in the multi-view than in the single view?" | Multi-view skips the SSAO post-process pass (`composer.render()` is replaced by three direct `renderer.render(...)` calls). This is a deliberate trade-off — running SSAO three times per frame at 1/3 viewport size is wasteful and the geometry is small enough that the views are still legible. Worth a sentence in the thesis. |
| "What happens to vertices that don't have any electrode mapped to them?" | They render as dark grey (rgb 0.12, 0.12, 0.12). This honestly communicates "no data here" — which is the correct visual claim, because EEG only sparsely covers the cortex. |
| "Why is the threshold a hard cutoff instead of a soft fade?" | Hard cutoff = clearer "above noise / below noise" visual partition. A soft alpha fade would look prettier but obscure where the threshold actually lies. Defensible either way; I'd keep the hard cut. |
| "Is the regional average a weighted average or unweighted?" | Unweighted: every channel that maps to a region contributes equally (`computeHeatmapColors`, line 65–67). For BCI Comp IV 2a this is fine because most regions get only 1–2 channels. Worth one sentence in the thesis. |

---

## 3. `DatasetPanel.jsx` — the left sidebar

**What it is.** Five sections, top to bottom: Dataset Details, Runs, Motor Imagery Classes, Frequency Band, Analysis Tools, Heatmap toggle.

**Why each section is there.**

- **Dataset Details + InfoPopup.** Tells the user what they're looking at without forcing them to read the thesis. The "?" popup carries the full description so the panel stays compact. Good.
- **Runs (R1–R6).** See §4 below — the value of this control is debatable.
- **Motor Imagery Classes.** Toggle buttons with class colour swatch and "clean / total" trial count. The colour swatch is critical: the same colour is used in the timeline curves, so the legend is *implicitly defined* the moment the user selects a class. This is good interaction design — the legend lives at the source of truth (the toggle).
- **Frequency Band (Mu / Beta).** Hard-coded to two buttons. This is correct for motor imagery: those are the two bands where ERD/ERS is robust. Adding theta/gamma/alpha would muddy the signal-to-noise story without adding scientific value for this dataset. Defensible.
- **Analysis Tools.**
  - *Contrast mode* checkbox + swap button: explained in §6.
  - *ERD threshold slider* (0–50%): noise rejection. Defensible.
  - *Multi-view* checkbox: see BrainViewer section above.
- **Heatmap toggle.** A separate, full-width button at the bottom — visually loud, which is correct because turning the heatmap off is a *major* mode change (you go from "data view" to "anatomy view"). The user would otherwise lose the heatmap and not know why.

**Things to defend / potentially fix.**

- **The Runs section assumes 6 runs and hardcodes the labels R1–R6.** If you ever swap to a different subject or dataset, this breaks. Cheap fix: derive `n_runs` from `eegData.dataset.n_runs` in the export. Worth doing before submission, since the alternative is "explain in the viva why the buttons don't update with the dataset."
- **The "Contrast Mode" checkbox is *only* enabled when exactly 2 classes are selected.** The disabled state shows the hint "Select exactly 2 classes". This is the right interaction (you can't subtract three things), but the state where the user has 3 classes selected, ticks an attractive-looking button, and gets a hint instead of an action is mildly confusing. Either: (a) auto-deselect to 2 when contrast is enabled, or (b) make the checkbox more obviously inert. Minor.
- **No "select all / deselect all" for runs.** Forgivable for 6 buttons, but the most common workflow is "all six runs" (the default), and the second-most-common is "compare runs 1–2 vs 5–6 to see learning effects". Currently both are tedious.

---

## 4. The "Runs" question — does this control actually deliver value?

**Short answer: only marginally, and only for a specific (interesting) experimental question.**

In BCI Comp IV 2a, the 6 runs are recorded in a single session in the same protocol. There are two reasons a user would want to filter by run:

1. **Investigating fatigue / attention drop-off** ("does the ERD weaken in late runs?"). This *is* a real research question. A subject's MI ability often drops as they get tired — visualising R1+R2 vs R5+R6 is a clean way to see it.
2. **Debugging / inspecting one specific run for a noisy electrode artifact.** Niche.

**Against keeping it:**
- Excluding runs reduces SNR. For most users the right answer is "all runs on, always", and the toggle just gives them a knob to make their plot worse without realising it.
- The aggregation is approximate (see §1) — the buttons are not actually selecting run-1 trials.
- Reviewers may ask "what scientific question does this answer for the average user?" and the honest answer is "not much, unless you specifically want to look at across-run effects."

**Recommendation.** Keep the control, but:
- Add a one-line label: *"Subset of recording blocks for cross-run comparison (e.g., fatigue effects). Default: all runs included."*
- Fix the trial→run assignment to use real run indices from MNE.
- Or: demote it from a top-level section to inside "Analysis Tools" so it's clearly an *advanced* knob.

**You can defend this either way to a supervisor.** The strongest defence is: "I exposed it because comparing early and late runs is a known way to investigate motor-imagery fatigue, and the framework is meant to be exploratory rather than prescriptive."

---

## 5. `Timeline.jsx` + `TimelineCurves.jsx` + `TimelineHeatmap.jsx`

**What it is.** A bottom strip with playback controls (play/pause, step, speed, zoom, scrubber), two visualisation tabs ("Curves" and "Heatmap"), a channel-mode dropdown, a stacked/overlay toggle, and a time slider.

**Why each piece exists.**

- **Playback.** EEG ERD/ERS is a temporal phenomenon — the whole point is that it builds up after the cue and decays. Animation makes that *visceral*. A static plot can show the same thing but does not communicate "this is happening live in time" to a non-expert. Keep.
- **Step / speed / zoom controls.** These are the standard scrubbing controls anyone who has used a video editor would recognise. The wheel-to-zoom with playhead-centered window (lines 70–80) is a small but high-quality interaction.
- **Curves vs Heatmap tabs.**
  - *Curves* answers: "what is the average power in this band over time, per class?" Best for comparing classes against each other.
  - *Heatmap* answers: "how does each individual electrode evolve over time?" Best for spotting which electrode/region is responsible for the average.
  - These are genuinely complementary, not redundant.
- **Channel mode (`motor` / `all` / `all_individual` / specific channel).**
  - `motor` (C3/Cz/C4) is the default because for motor imagery these three electrodes carry essentially all the diagnostic signal — anyone in the field will instantly approve this default.
  - `all` averages across the whole montage. Useful for "is there *any* widespread effect" but mostly low information.
  - `all_individual` shows every electrode as its own line; gated to one class because 22 lines × 4 classes = 88 lines, which is unreadable. See §7.
  - Specific channel: necessary for doing single-electrode quality checks.
- **Stacked vs overlay.**
  - Stacked: each class gets its own lane, so the y-axis baseline is comparable but the curves don't spatially overlap.
  - Overlay: all classes share one y-axis, so the user can directly visually compare amplitudes.
  - This is a real choice with no universally correct answer, so giving the user the toggle is the right call.
- **Cue line at t=0 + baseline shading for t<0.** Both are non-negotiable for ERD/ERS plots. Without them the user has no anchor for "what time means". You did this right.
- **Stacked layout reserves a separate "Diff" lane in contrast mode.** This is the right architectural choice — the difference curve is conceptually a *different signal* from the per-class curves, so giving it its own lane (with its own baseline shade) prevents the user from comparing it on the wrong axis.
- **Heatmap channel order.** `Fz, FC*, C*, CP*, P*, POz` is approximately anterior→posterior in the central row, with group dividers at the boundaries between FC/C/CP/P. This is the right ordering because it lets the user see "is the activation drifting forward or back over time?" — a montage-randomised ordering would destroy that signal.

**Things a non-expert reviewer will probably stumble on.**

- **What does "up" and "down" on the curves actually mean?** ERD is by definition a *power decrease*, which on the y-axis is plotted as a *negative number* (a downward dip). The curve going *down* therefore means the brain region is *more active*, which is counter-intuitive for anyone who hasn't internalised it. The help modal explains this in text but the timeline itself does not. Cheap fix: add a tiny "↓ ERD (active)  ↑ ERS (rest)" label on the y-axis of the curves view.
- **In contrast mode, the "Diff" curve up/down has yet another meaning.** "Diff > 0" means "Class 1 has higher ERD/ERS values than Class 2 at this time", which depending on the sign of the underlying signals can mean "Class 1 has weaker ERD" or "Class 2 has stronger ERD". This is the same trap as the brain heatmap (see §6).
- **Speed labels (0.5x, 1x, 2x, 4x) are relative to a 80 ms/frame baseline** — they are *not* relative to real biological time. So "1x" is not "1 second of brain time = 1 second of wall clock". Worth a one-line caveat in the thesis.

---

## 6. ⚠️ The most important issue: contrast mode legend semantics

This is the question your supervisor already asked you, and it is a real one. Here is the technically correct framing.

**What contrast mode actually computes.** Per channel and per time sample:

```
diff[i, t] = ERD/ERS_classA[i, t] − ERD/ERS_classB[i, t]
```

That is a **difference of percentages**, not a percentage itself. The result no longer has the meaning "this region desynchronised by X%". It has the meaning "this region was X percentage points more desynchronised in class A than in class B".

**Why both red and blue regions appear after subtraction.** Imagine left vs right hand:
- Right motor cortex (the side that *should* light up for left hand): in left-hand class it has, say, **−50% (strong ERD)**. In right-hand class it has **−10% (weak ERD)**. Difference = **−40% → blue**.
- Left motor cortex (the side that *should* light up for right hand): in left-hand class **−10%**, in right-hand class **−50%**. Difference = **+40% → red**.

So you correctly get a clean **bipolar pattern**: the side that owns class A is blue, the side that owns class B is red. **The implementation is correct.** The visual is exactly what a BCI researcher *wants* to see (it's effectively a "discriminability map" — the regions that are most informative for telling the two classes apart).

**Why it is misleading anyway.** The brain legend in `BrainViewer.jsx` (lines 462–477) still reads:
- Red = "Synchronization (power increase)"
- Blue = "Desynchronization (power decrease)"

In contrast mode **those labels are no longer true**. Red doesn't mean "this region synchronised" — it means "this region had less ERD in class 1 than in class 2". Blue doesn't mean "this region desynchronised" — it means "this region had more ERD in class 1 than in class 2".

A non-expert who reads the legend literally will form a false mental model and the framework will look broken when in fact it's behaving correctly.

**Recommended fix (small, high-value).**

In contrast mode, swap the legend text dynamically:

```
Red  →  "More ERD in {class 2 label}"   (or: "{class 1} less active here")
Blue →  "More ERD in {class 1 label}"   (or: "{class 2} less active here")
```

You can also add a one-line caption above the legend in contrast mode:
*"Showing (Class 1 − Class 2). Colours indicate which class is more desynchronised."*

This is a ~20-line frontend change, no backend impact, and it removes the single biggest misunderstanding the framework can produce.

**An optional second improvement** is to use a different colormap for contrast mode (e.g., purple↔orange) so the user has a *visual* cue that they are no longer looking at raw ERD/ERS. This is more invasive and arguably overkill — the legend rewrite is enough.

**For the thesis chapter** you can frame this as a known interpretive pitfall and document the chosen mitigation. That actually *strengthens* the thesis because it shows you anticipated the failure mode.

---

## 7. The "all electrodes for one class only" restriction

**What it is.** In the curves timeline, the `All channels (individual lines)` mode requires exactly one class to be selected (`Timeline.jsx` lines 186–200 + the auto-reset in lines 52–56).

**Why it exists.** With 22 EEG channels × 4 classes you would draw 88 lines on a single canvas, which is unreadable. With one class you draw 22 lines coloured in shades of that class — manageable, especially with the hover-to-highlight that you implemented (`TimelineCurves.jsx` lines 200–254).

**Is the restriction reasonable?** Yes, with a caveat.

- For the **default workflow** (compare classes), the all-individual mode is irrelevant and the restriction is invisible.
- For the **single-class deep-dive workflow** ("show me how every electrode behaved during left-hand imagery"), the restriction is correct.
- The edge case is **two classes side by side, each with all electrodes** — i.e., the user wants to see "all electrodes during left hand AND all electrodes during right hand at once". Currently impossible.

**Possible relaxations** (in increasing order of effort):
1. Allow all-individual with up to 2 classes when in *stacked* mode (each class gets its own lane, so 22 lines per lane is still readable). This is a one-line gating change.
2. Allow it for any number of classes in stacked mode, with a warning above 2.
3. Don't restrict at all but disable hover-highlight for >1 class.

**Recommendation.** Allow it for up to 2 classes in stacked mode, since stacked already gives each class its own visual region. This matches the "compare two classes" workflow which is the second-most-common after "look at one class in detail". Both of these are defensible decisions; the key is to *make* the decision and explain it in the thesis rather than leave it as an undocumented restriction.

---

## 8. `InfoPopup.jsx` — the "?" buttons

**What it is.** A small "?" icon next to every section header. Click → text bubble. Click outside → dismiss.

**Why.** Without the popups the panel would have to either (a) embed paragraphs of text inline (cluttering the UI) or (b) assume the user already knows what "Mu band" or "ERD" means (cluttering the user). The popup pattern lets the framework be *legible to a beginner without being noisy for an expert*. This is the right pattern for a teaching/exploration tool.

**Things to flag.**
- The popup text is hard-coded into each parent component as a prop string. For thesis-level work this is fine. For a real product you would want a separate i18n / docs file.
- The popups are text-only (no diagrams). For "ERD" specifically a tiny inline waveform-before/after diagram would be more informative than the text — but that's polish, not a defect.

---

## 9. The "Help / Theory" modal (in `page.js` lines 185–220)

**What it is.** A separate, full-screen-ish dialog with two cards (ERD explanation, Contralateral Control) and a How-to-Use list.

**Why it's there.** The single biggest thing a non-BCI reader needs to know about your framework is that **ERD = power decrease = activation**, which is counter-intuitive. Putting that in a modal that the user opens on first launch is the cheapest way to inoculate them against the "why is the active region drawn in blue?" misreading. Defensible.

**Things to flag.**
- The modal does not auto-open on first visit. New users may not notice the "?" button in the header. A single `useEffect` checking `localStorage` to auto-open it once would be a 5-line, high-value fix — and it's something a supervisor will probably ask about ("how does a new user know what they're looking at?").
- The Contrast Mode caveat (the §6 issue above) is **not** in the help modal. It should be — at least one sentence.

---

## 10. `ElectrodeSidebar.jsx`

**Status: present in the file system but not imported anywhere.** This is dead code from a previous iteration (the panel where you could click an electrode and see its time series). The hover-to-tooltip in the brain viewer subsumes it.

**Action item:** delete the file before submission. Leftover unused components are exactly the kind of thing that gets noticed in a thesis code review.

---

## 11. Summary of action items, in priority order

**Must-fix before submission.**

1. **Rewrite the brain legend in contrast mode** to read "More ERD in {class}" instead of "Synchronization / Desynchronization". This is the single most defensible UX improvement in this list. (§6)
2. **Fix or document the trials→runs approximation** in `page.js` line 83. Either export real run indices from the backend or add a thesis-level disclosure that the run buttons select an approximate slice. (§1, §4)
3. **Delete `ElectrodeSidebar.jsx`** since it is unused. (§10)

**Should-fix.**

4. **Add a contrast-mode caveat to the help modal.** One sentence explaining that the colours mean "more desynchronised in class X" rather than ERD/ERS. (§9)
5. **Auto-open the help modal on first launch** (with a `localStorage` flag). (§9)
6. **Add y-axis annotations to the curves view** so a new user understands "down = more active". (§5)
7. **Allow `All channels (individual lines)` mode for 2 classes in stacked layout.** (§7)

**Nice-to-have.**

8. **Document the SSAO trade-off** for multi-view (no ambient occlusion in split mode) in the thesis. (§2)
9. **Document the unweighted regional averaging** for the brain heatmap in the thesis. (§2)
10. **Add a "select all / clear all" affordance for the runs section**, or move it into Analysis Tools to mark it as advanced. (§3, §4)

---

## 12. Things to be ready to defend in the viva

- **Why a vertex-coloured surface mesh** instead of a volumetric MRI viewer or a topographic 2D scalp map? (Answer: ERD/ERS is fundamentally a cortical-surface phenomenon, and a 3D surface lets you simultaneously communicate anatomy and time-resolved activity in a way 2D scalp maps cannot.)
- **Why SSAO?** (Answer: cortical sulci are invisible without it, and they are essential anatomical landmarks for any reviewer reading the visualisation.)
- **Why Mu and Beta only?** (Answer: those are the two bands with reliable ERD in motor imagery; theta and gamma have lower SNR and are off-topic for BCI.)
- **Why a diverging blue–red colormap?** (Answer: it is the literature standard; Pfurtscheller & Lopes da Silva 1999 and most BCI papers use this convention. Departing from it would actively confuse domain readers.)
- **Why the help modal exists at all?** (Answer: ERD is counter-intuitive — the framework is intended to be usable by non-BCI viewers, so a one-click theory primer is the minimum viable onboarding.)
- **Why client-side run aggregation?** (Answer: storing 64 pre-aggregated combinations is wasteful when per-trial data is small enough to ship and aggregate live; it also keeps the run toggle interactive without re-running the Python pipeline.)
- **Why the contrast-mode bipolar pattern is correct, not a bug.** (See §6 — be ready to draw the (-50, -10) → -40 example on a whiteboard.)
- **What this framework offers that existing tools (MNE Brain, Freeview, BrainStorm) do not.** (Answer: it is web-based with no install, it co-locates the brain view with classifier-relevant timeline analysis, it specifically targets the motor-imagery BCI workflow rather than being a general-purpose viewer.)

---

*Generated for the BSc thesis frontend review. Intended as discussion material for the supervisor meeting, not as a finished design document.*
