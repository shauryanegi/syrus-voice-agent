# Syrus

Syrus is a concise, voice-first assistant built with LiveKit Agents and Google's Gemini realtime model. It uses the Aoede voice, accepts camera video for visual questions, and keeps a lightly witty, supportive persona.

## Capabilities

- Web search through DDGS for research and current information. DDGS selects its search backend automatically.
- Current conditions and today's forecast through Open-Meteo.
- English word definitions and pronunciations through Free Dictionary API.
- Built-in camera vision for images shared in the current session.

Syrus does not control a browser, open links, or take actions on websites.

## Setup

Install the LiveKit CLI and `uv`. Python 3.12 is used by the workshop, Docker image, and CI checks:

```console
uv python install 3.12
uv sync --python 3.12 --locked --dev
```

Copy `.env.example` to `.env.local` and provide your LiveKit project credentials and Google Gemini API key. The Google plugin reads `GOOGLE_API_KEY` from the environment.

```console
lk cloud auth
lk app env --write --destination .env.local
```

Add `GOOGLE_API_KEY` to `.env.local` as well. Keep `.env.local` private; it is ignored by Git and Docker.

The configured model is `gemini-3.1-flash-live-preview`, with the Aoede voice and `en-GB` language. Gemini handles turn detection and interruptions. The optional ai-coustics enhancer is currently disabled while isolating a native startup crash. Session audio recording is disabled to avoid a reported recorder/Gemini resampler race; transcripts, logs, and traces remain enabled. Input and output transcription are enabled by the Google plugin's defaults, but realtime-model transcripts can arrive after the spoken response. Review preview-model availability before running the demo or changing models.

## Run

Start the local development agent:

```console
lk agent dev
```

For a production worker:

```console
uv run src/agent.py start
```

## Tests and simulations

The unit tests mock external services, so they are repeatable and do not need network access:

```console
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Conversation simulations live in `scenarios.yaml` and exercise the persona, guardrails, and tool choice using fixed mock responses. Direct tool request and response handling is also covered by mocked tests, so those checks do not depend on external services. Run simulations with:

```console
lk agent simulate text --scenarios scenarios.yaml
```

Simulations use real, metered inference, while their tool responses come from the scenario fixtures. The GitHub Actions simulation workflow requires `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY` repository secrets.

GitHub Actions runs lint, formatting, and unit tests on pushes and pull requests to `main`. Start the Simulations workflow manually after adding the four repository secrets above. It is manual because it uses metered model inference.

Passing mocked tests does not prove that a live service is reachable. Before a demo, check one search, one weather lookup, and one definition over the actual workshop network.

## Deployment

The included Dockerfile builds the agent for deployment. Configure the same LiveKit and Google credentials in the deployment environment. See the [LiveKit Agents deployment guide](https://docs.livekit.io/deploy/agents/) for deployment options.

## Repository contents

`CLAUDE.md` contains the shared project guidance, and `GEMINI.md` points to it. Codex configuration, installed assistant skills, internal presenter notes, and build files stay local through `.gitignore`. The audience deck is in `presentations/`.
