# Bretalon

AI-focused news and analysis publication.

- **Status:** Production
- **URL:** bretalon.com
- **Repo:** N/A (WordPress CMS, content via WP REST API)
- **Runtime:** GCP gcp-medium (34.145.179.226), WordPress
- **Owner:** Alan Apter (editor/reviewer)

## Architecture

- Content pipeline: Gemini Deep Research + Grok + GPT-4.1 write + AI Council (4 models)
- Featured images: Imagen 4 via google-genai API (model: imagen-4.0-generate-001)
- Image style: photorealistic editorial, 16:9, no faces/text/logos
- Publishing: WP REST API draft, Telegram approval gate, then publish
- Review: full article HTML emailed to Alan for approval before scheduling

## Key Rules

- Never publish before Alan approves
- Never two articles on the same day
- Schedule as future post, send for review first
- No em dashes in published content
- Featured image: read article first, craft specific visual metaphor
