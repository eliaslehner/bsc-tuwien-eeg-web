# TO DO
## 1 - Adapt: Edge Case UI 
On Default when the frontend is loaded it selects all four motor imagery classes, now when the user deselects all of them one by one after every class was deselected the last class that was deselected still shows up in the timeline. Should be "No Class selected".

## 2 - Implement: Skeletons Implementation
To improve user experience especially when opening and using the frontend, without the use of skeletons, the UI can drastically change upon succesfully loading of the data. To keep the layout from shifting and improving UX, I will add skeletons for each component (Dataset Details, Brain Viewer, Timeline).

## 3 - Adapt: Layout Optimization
As of now the brain viewer gets the most screen space but the timeline could use more and the details component could benefit from more width.

## 4 - Question: Mobile View
Should I add the possibility to make this application useable on mobile devices? Yes if this application would be used commercially and is setup with webserver otherwise researchers wont use this application with mobile devices.

## 5 - Implement: Controls for Brain Viewer
Controls like centering the brain from a top view perspective so when pressed it automatically animates to the wanted position. Or maybe a button that reset the brain viewers changes like rotation or zoom to default.

## 6 - Implement: Details
I think the web application could benefit from a better detailed description. Maybe merge all `?` buttons to one general one and place it in the navbar on the far right side. When pressed the pop-up spans a good amount and presents the user a detailed guide on how this website works and where to find what. Or should I leave the `?` buttons as is for fast and short explanations and add a `How it works` text button into the nav bar that links to a page e.g. `/guide` where the user can read in a more well presented manner the actual implementation of this application.

## 7 - Question: More Details
Should I add a `/about` page where I write about this thesis in a more theoretical way rather than the guide, which is more practical, and provide like short blocks of text where things like struggles and problems, similar to the written thesis part will be. And also include supervisors and outgoing links?

## 8 - Adapt: Process all EEG Files
Process all EEG files and then provide the ability to load different datasets from a dropdown in the frontend. This way we can also analyze different runs with each other. Evaluate things like the ability to classify motor imagery tasks across participants with comparing e.g., intensity.

## 9 - Implement: Docker Compose
For easier use of this application I will create a docker file that will run and serve both frontend and backend.

## 10 - Question: New Modality/Feature
The first paper that was given to me as a reference that had a really good CT machine and took a long time to render. Did that brainmodel that was processed also contain the neuronical paths. Like would it be possible to process the brain to just have a brain map model of the neurons and their network.

## 11 - Adapt: Initial State
When the frontend is first executed the inital state of the frontends settings do not match, so e.g., the `HEATMAP ON` button should be displaying `OFF` as the regions model is visible. Also rename to `Brain Activity` or something similar.