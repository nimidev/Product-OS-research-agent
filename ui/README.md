<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/07e7ef18-9448-487b-80cc-cf76e396b06e

## Run Locally

**Prerequisites:** Node.js

1. Install dependencies:
   `npm install`
2. Configure `.env.local`:
   - `VITE_RESEARCH_API_URL=http://localhost:8000`
3. Run the app:
   `npm run dev`

## US-003 Notes

- Chat uses Research Agent REST API `POST /search_memories`.
- Integration setup is Monday-first for Phase 1.
- Non-Monday providers are visible as "Coming Soon".
