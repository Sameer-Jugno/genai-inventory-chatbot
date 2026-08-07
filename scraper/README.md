# Secondary feeder (ADR-007)

Generic HTML fetch only. Output goes under `uploads/{vendor}/` so the same
S3 → Lambda pipeline indexes scraped pages — no parallel indexing path.

```bash
python scraper/fetch.py 'https://example.com/catalog' --out-dir scraper/out
aws s3 cp scraper/out/<vendor>/<page>.html s3://$DATA_BUCKET/uploads/<vendor>/
```
