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

If the Modal worker logs a Kaggle 403, create a fresh Kaggle API token for the
same account, update `KAGGLE_USERNAME` and `KAGGLE_KEY` in this secret, and make
sure that account has accepted any required competition or dataset terms on
Kaggle.

Deploy the scheduled worker:

```bash
modal deploy --env=dev modal_app.py
```

Run this again any time the ingestion or archetype code changes. Modal's hourly
schedule runs the last deployed bundle, so local code changes do not affect the
scheduled worker until you deploy them.

Run it manually once:

```bash
modal run --env=dev modal_app.py
```

The deployed function runs at minute 15 every hour. It checks the Kaggle index,
downloads the latest daily dataset, parses compact battle/deck/card facts, and
upserts them into Supabase.

On scheduled runs, the worker downloads only the small
`pokemon-tcg-ai-battle-episodes-index` dataset first. It compares the dates in
that index to dates already completed in Supabase. A date is treated as complete
only when it has both a `daily_datasets` row and an `archetype_runs` row for the
current archetype algorithm version. If every indexed date is complete, the
worker skips the large daily episode dataset download.

Passing a date manually still forces that date to be downloaded and recomputed:

```bash
modal run --env=dev modal_app.py --date 2026-06-19
```

Check that every ingested date has an archetype run:

```bash
npm run check:archetypes
```

If a date is missing, backfill it manually:

```bash
modal run --env=dev modal_app.py --date 2026-06-19
```

Then deploy the worker so future scheduled runs use the current code:

```bash
modal deploy --env=dev modal_app.py
```

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

## Local Development

For normal local development, run two terminals.

Terminal 1 starts the local Python API server:

```bash
npm run dev:api
```

Terminal 2 starts the Vite frontend:

```bash
npm run dev
```

Vite proxies `/api/*` to the Python API server on `127.0.0.1:8000`, so the
frontend can call `/api/meta` just like it does in production.

The local API server reads `.env` and `.env.local`, so these need to exist
locally:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

You can still use Vercel's local dev server when you need to test Vercel's
runtime specifically:

```bash
vercel dev
```

For `vercel dev`, the API route also needs these environment variables:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

If `.env.local` already exists from the Vercel CLI, add these two lines to it.
Do not commit `.env.local`.

## Card Images

Card images are extracted from the Kaggle-provided PDF in the neighboring
`pokemon-ai` checkout and uploaded to Supabase Storage.

First run the updated `supabase/schema.sql` in Supabase SQL Editor so the
`cards` table has:

```text
image_path
image_url
image_updated_at
```

Then run a dry-run extraction count:

```bash
modal run --env=dev modal_card_assets.py --action dry-run
```

If the dry-run reports the same number of PDF images and unique CSV card rows,
upload the images:

```bash
modal run --env=dev modal_card_assets.py --action upload
```

The importer creates a public Supabase Storage bucket named `card-images`, writes
images to paths like `cards/en/1227.webp`, and updates `cards.image_url`.

For a small test upload first:

```bash
modal run --env=dev modal_card_assets.py --action upload --limit 10
```
