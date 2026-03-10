### 📅 Phase 1: Development (The "Vertical Slice" Approach)

*Goal: Every sprint delivers a working, demonstrable piece of the software.*

**Sprint 1: Mar 2 – Mar 15 | The "Skeleton" (Basic Data Flow)**

* **Concept:** Prove you can get *any* data from Python to the Browser.
* **Backend (Python):**
* Create the "Converter Script": Read a single `.gdf` file using MNE-Python.


* Export a small "dummy" JSON file containing just 10 seconds of raw signal and random electrode coordinates.


* **Frontend (React/Three.js):**
* Set up the standard Vite + Three.js scene.


* Write the loader to parse that JSON file.
* Render simple spheres (placeholders) at the coordinates specified in the JSON.


* **🎉 Presentation Demo:** "I have established the data pipeline. You are looking at a web scene generated entirely from a Python-processed data file."

**Sprint 2: Mar 16 – Mar 29 | The "Brain & Signal" (Real Assets)**

* **Concept:** Replace placeholders with real assets and physics.
* **Backend:**
* Implement the bandpass filter (8–30 Hz) to isolate Mu/Beta rhythms.


* Refine the JSON export to include the full recording session.
* Export the standard 10-20 system channel locations.




* **Frontend:**
* Import the **Skull-stripped Brain Mesh** (GLTF/GLB) you prepared.


* Map the 22 electrode spheres to the correct positions on the mesh surface.


* **🎉 Presentation Demo:** "Here is the actual patient's cortex. The electrodes are mapped to the 10-20 system, and the data driving them is filtered for Motor Imagery."

**Sprint 3: Mar 30 – Apr 12 | The "Animation" (Visualizing Activity)**

* **Concept:** Make it move.
* **Backend:**
* (Optional) Pre-calculate "Activity Power" per channel if doing raw signal rendering is too noisy on the frontend.


* **Frontend:**
* Implement the **Animation Loop**: Update the color/size of the electrode spheres every frame based on the signal array.
* Optimize performance to handle the 250 Hz sampling rate smoothly.




* **🎉 Presentation Demo:** "This is a real-time replay of neural activity. You can see the brain 'lighting up' as the recording plays."

**Sprint 4: Apr 13 – Apr 26 | The "Dashboard" (Interaction & Sync)**

* **Concept:** Add user control and context.
* **Frontend:**
* Implement the "Time-Travel" scrubber (slider) to jump to specific timestamps.


* Add the synchronized 2D charts (Canvas/Chart.js) to show voltage over time.


* **Crucial:** Final debugging and **Code Freeze**.


* **🎉 Presentation Demo:** "This is the complete tool. I can pause, scrub through the timeline, and inspect the specific 'Left Hand' vs 'Right Hand' trials."

---

### ✍️ Phase 2: Writing & Documentation

*Since you have been building "Vertical Slices," you can take screenshots for your thesis throughout the process, rather than waiting until the end.*

**Sprint 5: Apr 27 – May 10 | Structure & Methodology**

* **Writing:**
* Draft **Section 3 (Methodology):** Describe the "Pre-process & Load" architecture and the JSON data structure.
* Draft **Section 1 (Introduction):** Motivation for web-based BCI tools.




* **Milestone:** You now have the text describing *what* you built.

**Sprint 6: May 11 – May 24 | Implementation & Evaluation**

* **Writing:**
* Draft **Section 4 (Implementation Steps):** Detail the challenge of mapping 2D electrode coords to a 3D brain model.
* Draft **Section 5 (Expected Outcome):** Use your finished prototype to write the qualitative evaluation (User Experience, FPS performance).




* **Milestone:** You have the text describing *how* it works and *how well* it performs.

**Sprint 7: May 25 – Jun 7 | Full Draft Assembly**

* **Writing:**
* Write the **Abstract** and **Research Objectives**.


* Combine all sections into the final LaTeX document.
* **Action:** Send the full PDF to your supervisor for feedback.



**Sprint 8: Jun 8 – Jun 21 | Review & Polish**

* **Action:**
* Apply supervisor corrections.
* Final check of the Bibliography (`references.bib`).


* Verify formatting (margins, fonts) matches the `preamble.tex` guidelines.





**Sprint 9: Jun 22 – Jun 30 | Submission**

* **Action:** Final compilation and submission of the Bachelor Thesis.