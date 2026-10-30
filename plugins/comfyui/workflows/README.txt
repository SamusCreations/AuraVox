ComfyUI Workflows for AuraVox
=============================

AuraVox automatically discovers and converts workflows saved in your ComfyUI installation (`user/default/workflows`). This folder is for additional workflows you want to add manually:

- In ComfyUI: open the Workflow menu → Export (API) and save the `.json` file here, or
- In AuraVox: go to Shared Settings → Plugins → ComfyUI → "Import workflow".

Standard ComfyUI workflow files (saved via regular "Save") are also supported and converted automatically.
Once added, go to Shared Settings → Plugins → ComfyUI, assign the workflow to a task (image generation, image editing, or video generation), and review the mapped inputs (prompt, seed, resolution, reference image, etc.).
