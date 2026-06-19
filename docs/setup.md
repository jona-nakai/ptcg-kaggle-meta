# Deployment Setup

This project uses three services:

- Vercel hosts the React frontend and lightweight API routes.
- Supabase stores compact queryable meta data.
- Modal runs the scheduled Python Kaggle ingestion job.

The raw daily Kaggle episode dataset is downloaded only inside the worker's
temporary disk. The worker extracts compact rows and writes those to Supabase.

## Supabase

1. Create a Supabase project.
2. Open SQL Editor and run `supabase/schema.sql`.
3. Copy these values from Project Settings > API:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

The service-role key must stay server-side only. Do not expose it in React.

## Modal

Install and authenticate the Modal CLI locally:

```bash
python -m pip install -r requirements-worker.txt
modal setup
```

Create a Modal secret named `ptcg-kaggle-meta`:

```bash
modal secret create ptcg-kaggle-meta \
  SUPABASE_URL="https://YOUR_PROJECT_REF.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY" \
  KAGGLE_USERNAME="YOUR_KAGGLE_USERNAME" \
  KAGGLE_KEY="YOUR_KAGGLE_API_KEY" \
  KAGGLE_COMPETITION_HANDLE="pokemon-tcg-ai-battle"
```

Deploy the scheduled worker:

```bash
modal deploy --env=dev modal_app.py
```

Run it manually once:

```bash
modal run --env=dev modal_app.py
```

The deployed function runs at minute 15 every hour. It checks the Kaggle index,
downloads the latest daily dataset, parses compact battle/deck/card facts, and
upserts them into Supabase.

## Vercel

In Vercel project settings, set:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Then deploy normally:

```bash
npm install
npm run build
```

Vercel should use:

```text
Build Command: npm run build
Output Directory: dist
```

The frontend reads `/api/meta`, which reads the latest summary from Supabase.

## Local Data Commands

Preview the site:

```bash
npm run dev
```
