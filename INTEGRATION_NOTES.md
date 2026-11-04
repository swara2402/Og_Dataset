# Integration notes

This patch changes the standalone quality-editor CLI from OpenAI to Ollama.
The local/hosted provider is configured only through environment variables.

The source archive previously uploaded contains the website/docs and standalone
`local_humanizer.py`, but not the actual `Turnitout-core` backend. The bundled
`AGENTS.md` identifies that backend as a separate repository. Consequently,
this patch does not claim to have modified the deployed Streamlit application,
its 8-node cluster, or its UI. To wire this provider into those app modules,
the actual `Turnitout-core` source tree is required.

Do not copy the hosted model to every Streamlit worker. Keep inference in one
separate service and route jobs through an authenticated queue/gateway.
